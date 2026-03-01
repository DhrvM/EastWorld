"""In-memory session management for EastWorld API."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

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
        synth_configs: list[SynthConfig],
        bootstrap_synths: bool = True,
        mock_mode: bool = False,
    ) -> Session:
        env = Environment(objective=objective, max_turns=1000)
        observer = build_observer(run_id=env.id, trace_dir="runs/traces", console=False)
        env.set_observer(observer.emit)

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
