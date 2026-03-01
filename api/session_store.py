"""In-memory session management for EastWorld API."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any
import os
from tavily import TavilyClient

from environment.main import Environment
from god import God
from observability import build_observer
from synth import Synth, SynthConfig, SynthMessage
from synth.memory import store_memory
from artifacts import Artifact, artifact_to_memory_blob


@dataclass
class Session:
    env: Environment
    synths: dict[str, Synth]
    god: Any
    trace_path: Path
    mock_mode: bool = False


class MockSynth:
    """Offline synth for local smoke testing."""

    def __init__(self, config: SynthConfig) -> None:
        self.synth_id = config.synth_id
        self.id = config.synth_id
        self.synth_name = config.synth_name
        self.persona_prompt = config.persona_prompt
        self.allowed_connections = list(config.allowed_connections)
        self.allowed_tools = list(config.allowed_tools)
        self.model = config.model

    def can_message(self, target_synth_id: str) -> bool:
        return target_synth_id in self.allowed_connections

    def initiate(self, observer=None) -> SynthMessage:
        if observer:
            observer(
                "SYNTH_INITIATE_RESPONSE",
                {
                    "synth_id": self.synth_id,
                    "summary": f"{self.synth_id} mock initiated",
                },
            )
        return SynthMessage(
            role="assistant",
            content=f"{self.synth_name} here. Ready to discuss the task.",
            name=self.synth_id,
        )

    def step(
        self,
        conversation: list[SynthMessage],
        *,
        tools=None,
        objective=None,
        tool_executor=None,
        observer=None,
    ):
        from synth.models import StepResult

        last = conversation[-1].content if conversation else "No context"
        content = (
            f"{self.synth_name}: Based on the artifacts, I think we should focus on "
            f"the main risks and next actions. [source: conversation] "
            f"Responding to: {last[:120]}"
        )
        if observer:
            observer(
                "SYNTH_RESPONSE",
                {"synth_id": self.synth_id, "content_preview": content[:140]},
            )
        return StepResult(
            message=SynthMessage(
                role="assistant",
                content=content,
                name=self.synth_id,
            )
        )


class MockGod:
    """Offline GOD analysis for local smoke tests."""

    def __init__(self, environment: Environment) -> None:
        self.env = environment

    def ask(self, question: str) -> str:
        stats = self.env.get_stats()
        return (
            "Mock GOD analysis:\n"
            f"- question: {question}\n"
            f"- rounds: {stats['rounds']}\n"
            f"- messages: {stats['messages']}\n"
            f"- artifacts_ingested: {stats['artifacts_ingested']}"
        )


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create_session(
        self,
        *,
        objective: str,
        active_tools: list[str],
        synth_configs: list[SynthConfig],
        bootstrap_synths: bool = True,
        mock_mode: bool = False,
    ) -> Session:
        env = Environment(objective=objective, max_turns=1000)
        observer = build_observer(run_id=env.id, trace_dir="runs/traces", console=False)
        env.set_observer(observer.emit)

        # Register tools selected by the frontend
        for tool in active_tools:
            if tool == "execute_python":
                env.register_tool(
                    name="execute_python",
                    description="Execute Python code in a secure sandbox and return the stdout/stderr.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "code": {
                                "type": "string",
                                "description": "The Python code snippet to execute. Must print results to stdout."
                            }
                        },
                        "required": ["code"]
                    },
                    function=self._tool_execute_python
                )
            elif tool == "read_file":
                env.register_tool(
                    name="read_file",
                    description="Read the text content of a local file.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Absolute or relative path to the file to read."
                            }
                        },
                        "required": ["file_path"]
                    },
                    function=self._tool_read_file
                )
            elif tool == "create_file":
                env.register_tool(
                    name="create_file",
                    description="Create a new local file with the provided text content.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the file to create."
                            },
                            "content": {
                                "type": "string",
                                "description": "The text content to write to the file."
                            }
                        },
                        "required": ["file_path", "content"]
                    },
                    function=self._tool_create_file
                )
            elif tool == "web_search":
                env.register_tool(
                    name="web_search",
                    description="Search the web (mocked fallback if no search API is configured).",
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The query string to search for."
                            }
                        },
                        "required": ["query"]
                    },
                    function=self._tool_web_search
                )

        # System tool to allow social sharing when external tools are present.
        env.register_tool(
            name="recommend_tool",
            description="Share a tool with another person so they get access to it.",
            parameters={
                "type": "object",
                "properties": {
                    "tool_name": {"type": "string"},
                    "target_synth_id": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["tool_name", "target_synth_id", "reason"],
            },
            function=lambda **kwargs: {"status": "ok"},
        )

        synths: dict[str, Synth] = {}
        synth_cls = MockSynth if mock_mode else Synth
        for cfg in synth_configs:
            synth = synth_cls(cfg) if mock_mode else synth_cls(cfg, bootstrap=bootstrap_synths)
            env.add_synth(synth)
            synths[cfg.synth_id] = synth

        god = MockGod(env) if mock_mode else God(env)
        session = Session(
            env=env,
            synths=synths,
            god=god,
            trace_path=Path("runs/traces") / f"{env.id}.jsonl",
            mock_mode=mock_mode,
        )
        self._sessions[env.id] = session
        return session

    def get(self, env_id: str) -> Session:
        if env_id not in self._sessions:
            raise KeyError(f"Unknown environment id: {env_id}")
        return self._sessions[env_id]

    def list_ids(self) -> list[str]:
        return list(self._sessions.keys())

    def add_artifacts(self, env_id: str, artifacts: list[Artifact]) -> None:
        session = self.get(env_id)
        session.env.add_artifacts(artifacts)
        if session.mock_mode:
            return
        for synth in session.synths.values():
            for artifact in artifacts:
                store_memory(synth.synth_id, artifact_to_memory_blob(artifact))

    def user_chat(self, env_id: str, synth_id: str, user_input: str) -> dict:
        session = self.get(env_id)
        env = session.env
        if synth_id not in session.synths:
            raise KeyError(f"Unknown synth id: {synth_id}")

        synth = session.synths[synth_id]
        human_msg = SynthMessage(role="user", content=user_input, name="human")
        env.conversation.append(human_msg)
        env._log("human", "MESSAGE", {"text": user_input})

        tool_schemas = env._get_tool_schemas_for(synth)

        def tool_executor(tool_name: str, args: dict) -> str:
            return env._execute_tool(synth.synth_id, tool_name, args)

        result = synth.step(
            env.conversation,
            tools=tool_schemas,
            objective=env.objective,
            tool_executor=tool_executor,
            observer=env._observe,
        )

        if result.message:
            env.conversation.append(result.message)
            env._log(synth.synth_id, "MESSAGE", {"text": result.message.content})
            return {"message": result.message.content, "skip": False}
        return {"message": "", "skip": bool(result.skip)}

    def read_trace_events(self, env_id: str, limit: int = 100) -> list[dict]:
        session = self.get(env_id)
        path = session.trace_path
        if not path.exists():
            return []

        lines = path.read_text(encoding="utf-8").splitlines()
        slice_lines = lines[-max(1, limit):]
        events: list[dict] = []
        for raw in slice_lines:
            try:
                events.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
        return events

    # --- Tool Implementations ---

    def _tool_execute_python(self, code: str) -> dict:
        import sys
        import io
        import contextlib
        import traceback
        
        output_buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(output_buffer), contextlib.redirect_stderr(output_buffer):
                exec(code, {})
            return {"status": "success", "output": output_buffer.getvalue()}
        except Exception as e:
            return {"status": "error", "error": str(e), "traceback": traceback.format_exc(), "partial_output": output_buffer.getvalue()}

    def _tool_read_file(self, file_path: str) -> dict:
        import os
        try:
            if not os.path.exists(file_path):
                return {"status": "error", "error": f"File '{file_path}' does not exist."}
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            return {"status": "success", "content": content}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _tool_create_file(self, file_path: str, content: str) -> dict:
        import os
        try:
            # Create directories if they don't exist
            os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return {"status": "success", "message": f"Successfully created/written to '{file_path}'."}
        except Exception as e:
            return {"status": "error", "error": str(e)}
            
    def _tool_web_search(self, query: str) -> dict:
        

        try:
            tavily_api_key = os.getenv("TAVILY_API_KEY")
            if not tavily_api_key:
                return {"status": "error", "error": "TAVILY_API_KEY not found in environment variables."}
            
            client = TavilyClient(api_key=tavily_api_key)
            response = client.search(query=query, search_depth="advanced")
            
            results = []
            for item in response.get("results", []):
                results.append(f"Title: {item.get('title')}\nURL: {item.get('url')}\nContent: {item.get('content')}")
            
            return {
                "status": "success",
                "results": results
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
