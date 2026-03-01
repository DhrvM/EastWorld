"""Environment — simulation orchestrator for multi-synth interactions."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from artifacts import Artifact, artifact_context_block
from synth.models import SynthMessage


class Environment:
    """An in-memory environment that orchestrates synth interactions.

    Manages synth registration, tool execution, event logging,
    and the autonomous simulation loop.
    """

    def __init__(
        self,
        objective: str = "Interact naturally.",
        max_turns: int = 50,
        env_id: str | None = None,
        observer: Callable[[str, dict], None] | None = None,
    ) -> None:
        self.id = env_id or str(uuid.uuid4())
        self.objective = objective
        self.max_turns = max_turns
        self.current_turn = 0
        self.status = "INITIALIZING"

        self.synths: dict[str, Any] = {}          # synth_id -> Synth
        self.tools: dict[str, dict] = {}           # tool_name -> {schema, function}
        self.event_logs: list[dict] = []           # transcript
        self.conversation: list[SynthMessage] = [] # shared message history
        self.artifacts: list[Artifact] = []        # user-provided context artifacts
        self.observer = observer
        self._opened = False

    def set_observer(self, observer: Callable[[str, dict], None] | None) -> None:
        self.observer = observer

    # ── Synth Management ─────────────────────────────────────────────────

    def add_synth(self, synth: Any) -> str:
        """Register a Synth into the environment."""
        sid = synth.synth_id
        synth.env_id = self.id

        # Validate tools — strip any the environment doesn't have
        valid = [t for t in synth.allowed_tools if t in self.tools]
        if len(valid) != len(synth.allowed_tools):
            stripped = set(synth.allowed_tools) - set(valid)
            print(f"  ⚠ {synth.synth_name}: tools {stripped} not in environment, stripped.")
        synth.allowed_tools = valid

        # Always grant the recommend_tool system tool
        if "recommend_tool" in self.tools and "recommend_tool" not in synth.allowed_tools:
            synth.allowed_tools.append("recommend_tool")

        self.synths[sid] = synth
        self._log("system", "SYSTEM_ALERT", {
            "message": f"{synth.synth_name} ({sid}) joined the environment."
        })
        self._observe(
            "ENV_SYNTH_ADDED",
            {
                "env_id": self.id,
                "synth_id": sid,
                "synth_name": synth.synth_name,
                "allowed_tools": list(synth.allowed_tools),
                "allowed_connections": list(synth.allowed_connections),
                "summary": f"{synth.synth_name} joined environment",
            },
        )
        return sid

    # ── Tool Management ──────────────────────────────────────────────────

    def add_artifact(self, artifact: Artifact) -> str:
        """Register a user-provided artifact for this environment."""
        self.artifacts.append(artifact)
        self._log("human", "ARTIFACT_INGESTED", {"artifact": artifact.to_dict()})
        self._observe(
            "ENV_ARTIFACT_INGESTED",
            {
                "env_id": self.id,
                "artifact_id": artifact.artifact_id,
                "artifact_type": artifact.artifact_type,
                "title": artifact.title,
                "summary": f"artifact ingested: {artifact.title}",
            },
        )
        return artifact.artifact_id

    def add_artifacts(self, artifacts: list[Artifact]) -> None:
        for artifact in artifacts:
            self.add_artifact(artifact)

    def register_tool(
        self,
        name: str,
        description: str,
        parameters: dict,
        function: Callable,
    ) -> None:
        """Register a tool that synths can call."""
        self.tools[name] = {
            "schema": {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                },
            },
            "function": function,
        }
        self._observe(
            "ENV_TOOL_REGISTERED",
            {
                "env_id": self.id,
                "tool_name": name,
                "summary": f"tool registered: {name}",
            },
        )

    def grant_tool(self, synth_id: str, tool_name: str, granted_by: str = "system") -> bool:
        """Dynamically grant a tool to a synth at runtime."""
        synth = self.synths.get(synth_id)
        if not synth or tool_name not in self.tools:
            return False
        if tool_name in synth.allowed_tools:
            return True  # Already has it

        synth.allowed_tools.append(tool_name)
        self._log("system", "TOOL_GRANTED", {
            "tool": tool_name,
            "granted_to": synth_id,
            "granted_by": granted_by,
        })
        self._observe(
            "ENV_TOOL_GRANTED",
            {
                "env_id": self.id,
                "tool": tool_name,
                "granted_to": synth_id,
                "granted_by": granted_by,
                "summary": f"{granted_by} granted {tool_name} to {synth_id}",
            },
        )
        return True

    # ── Simulation Engine ────────────────────────────────────────────────

    def run_simulation(
        self,
        rounds: int | None = None,
        callback: Callable[[str, str], None] | None = None,
    ) -> None:
        """Run the autonomous simulation loop.

        Parameters
        ----------
        rounds : int | None
            Number of rounds (full loops over all synths). Defaults to max_turns.
        callback : callable | None
            ``(sender_id, text) -> None`` called for each message, useful for
            live printing.
        """
        max_rounds = rounds or self.max_turns
        self._ensure_running()
        for _ in range(max_rounds):
            if self.status == "TERMINATED":
                break
            had_activity = self.run_round(callback=callback)
            if not had_activity:
                if callback:
                    callback("system", "[Conversation naturally concluded — all synths skipped]")
                self._observe(
                    "ENV_CONVERSATION_CONCLUDED",
                    {
                        "env_id": self.id,
                        "round": self.current_turn,
                        "summary": "all synths skipped, ending run",
                    },
                )
                break
        self.finish()

    def run_round(
        self,
        callback: Callable[[str, str], None] | None = None,
    ) -> bool:
        """Run exactly one round over all synths."""
        self._ensure_running()
        if self.status == "TERMINATED":
            return False

        self._seed_and_open_if_needed(callback=callback)
        synth_list = list(self.synths.values())
        if not synth_list:
            return False

        round_num = self.current_turn + 1
        self._observe(
            "ENV_ROUND_START",
            {
                "env_id": self.id,
                "round": round_num,
                "conversation_len": len(self.conversation),
                "summary": f"round {round_num} start",
            },
        )

        round_had_activity = False
        objective = self._build_full_objective()
        for synth in synth_list:
            if self.conversation and self.conversation[-1].name == synth.synth_id:
                continue
            if not self._can_synth_reply(synth):
                continue
            try:
                msg = self._run_synth_turn(synth, objective)
                if msg:
                    round_had_activity = True
                    if callback:
                        callback(synth.synth_id, msg.content)
            except Exception as e:
                err = f"[ERROR] {synth.synth_id}: {e}"
                self._log(synth.synth_id, "ERROR", {"error": str(e)})
                if callback:
                    callback("system", err)

        self.current_turn = round_num
        self._observe(
            "ENV_ROUND_END",
            {
                "env_id": self.id,
                "round": round_num,
                "had_activity": round_had_activity,
                "conversation_len": len(self.conversation),
                "summary": f"round {round_num} end",
            },
        )
        return round_had_activity

    def finish(self) -> None:
        """Mark run as completed."""
        self.status = "COMPLETED"
        self._observe(
            "ENV_RUN_END",
            {
                "env_id": self.id,
                "rounds_completed": self.current_turn,
                "total_events": len(self.event_logs),
                "summary": "simulation completed",
            },
        )

    def _ensure_running(self) -> None:
        if self.status == "INITIALIZING":
            self.status = "RUNNING"
            self._observe(
                "ENV_RUN_START",
                {
                    "env_id": self.id,
                    "max_rounds": self.max_turns,
                    "synth_count": len(self.synths),
                    "summary": f"simulation starting with {len(self.synths)} synths",
                },
            )

    def _build_full_objective(self) -> str:
        participant_info = "\n".join(
            f"- {s.synth_name} ({s.synth_id}): {s.persona_prompt[:150]}..."
            for s in self.synths.values()
        )
        full_objective = (
            f"{self.objective}\n\n"
            f"People in the room:\n{participant_info}\n\n"
            f"Conversation so far has {len(self.conversation)} messages."
        )
        artifact_context = artifact_context_block(self.artifacts)
        if artifact_context:
            full_objective += (
                "\n\nExternal artifacts shared by the human user:\n"
                f"{artifact_context}\n"
                "Use these artifacts as primary evidence in your discussion."
            )
        return full_objective

    def _seed_and_open_if_needed(
        self,
        callback: Callable[[str, str], None] | None = None,
    ) -> None:
        if not self.conversation:
            self.conversation.append(
                SynthMessage(
                    role="system",
                    content=f"[ENVIRONMENT]: {self.objective}",
                    name="system",
                )
            )

        if self._opened:
            return
        synth_list = list(self.synths.values())
        if not synth_list or len(self.conversation) > 1:
            self._opened = True
            return

        opener = synth_list[0]
        try:
            opening = self._call_synth_initiate(opener)
            self.conversation.append(opening)
            self._log(opener.synth_id, "MESSAGE", {"text": opening.content})
            if callback:
                callback(opener.synth_id, opening.content)
        except Exception as e:
            self._log(opener.synth_id, "ERROR", {"error": str(e)})
        finally:
            self._opened = True

    def _can_synth_reply(self, synth: Any) -> bool:
        """Check whether synth is allowed to respond based on last speaker."""
        if not self.conversation:
            return True

        last_speaker = self.conversation[-1].name
        if not last_speaker:
            return True
        if last_speaker in {"system", "human"}:
            return True
        if last_speaker == synth.synth_id:
            return False

        try:
            allowed = bool(synth.can_message(last_speaker))
        except Exception:
            allowed = last_speaker in set(getattr(synth, "allowed_connections", []))
        if not allowed:
            self._observe(
                "ENV_REPLY_BLOCKED",
                {
                    "env_id": self.id,
                    "synth_id": synth.synth_id,
                    "last_speaker": last_speaker,
                    "summary": f"{synth.synth_id} blocked from replying to {last_speaker}",
                },
            )
        return allowed

    def _run_synth_turn(self, synth: Any, objective: str) -> SynthMessage | None:
        """Run a single synth's cognitive turn with tool support."""
        tool_schemas = self._get_tool_schemas_for(synth)

        def tool_executor(tool_name: str, arguments: dict) -> str:
            """Callback passed to synth.step() for inline tool execution."""
            if tool_name == "recommend_tool":
                return self._handle_recommend_tool(synth.synth_id, arguments)
            return self._execute_tool(synth.synth_id, tool_name, arguments)

        result = self._call_synth_step(
            synth,
            conversation=self.conversation,
            tools=tool_schemas,
            objective=objective,
            tool_executor=tool_executor,
        )

        if result.skip:
            return None

        if result.message:
            self.conversation.append(result.message)
            self._log(synth.synth_id, "MESSAGE", {"text": result.message.content})
            return result.message

        return None

    # ── Tool Execution ───────────────────────────────────────────────────

    def _get_tool_schemas_for(self, synth: Any) -> list[dict] | None:
        """Build the list of OpenAI tool schemas this synth can use."""
        schemas = []
        for tool_name in synth.allowed_tools:
            if tool_name in self.tools:
                # For recommend_tool, inject current state into description
                if tool_name == "recommend_tool":
                    schemas.append(self._build_recommend_schema())
                else:
                    schemas.append(self.tools[tool_name]["schema"])
        return schemas if schemas else None

    def _build_recommend_schema(self) -> dict:
        """Build the recommend_tool schema with current env state."""
        available_tools = [t for t in self.tools.keys() if t != "recommend_tool"]
        synth_ids = list(self.synths.keys())
        return {
            "type": "function",
            "function": {
                "name": "recommend_tool",
                "description": (
                    f"Share a tool with another person so they can use it too. "
                    f"Available tools to share: {available_tools}. "
                    f"People: {synth_ids}"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tool_name": {
                            "type": "string",
                            "description": "Name of the tool to share",
                        },
                        "target_synth_id": {
                            "type": "string",
                            "description": "ID of the person to share with",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Why you're sharing this tool",
                        },
                    },
                    "required": ["tool_name", "target_synth_id", "reason"],
                },
            },
        }

    def _execute_tool(self, synth_id: str, tool_name: str, arguments: dict) -> str:
        """Execute a tool and return the result as a string."""
        tool = self.tools.get(tool_name)
        if not tool:
            return json.dumps({"error": f"Tool '{tool_name}' not found"})

        self._log(synth_id, "TOOL_CALL", {"tool": tool_name, "arguments": arguments})
        self._observe(
            "ENV_TOOL_EXECUTION_START",
            {
                "env_id": self.id,
                "synth_id": synth_id,
                "tool": tool_name,
                "arguments": arguments,
                "summary": f"{synth_id} calling tool {tool_name}",
            },
        )

        try:
            result = tool["function"](**arguments)
            if not isinstance(result, str):
                result = json.dumps(result, indent=2)
            self._log(synth_id, "TOOL_RESULT", {
                "tool": tool_name, "result": result[:500]
            })
            self._observe(
                "ENV_TOOL_EXECUTION_RESULT",
                {
                    "env_id": self.id,
                    "synth_id": synth_id,
                    "tool": tool_name,
                    "result_preview": result[:220],
                    "summary": f"tool {tool_name} completed",
                },
            )
            return result
        except Exception as e:
            error = json.dumps({"error": str(e)})
            self._log(synth_id, "TOOL_RESULT", {"tool": tool_name, "error": str(e)})
            self._observe(
                "ENV_TOOL_EXECUTION_ERROR",
                {
                    "env_id": self.id,
                    "synth_id": synth_id,
                    "tool": tool_name,
                    "error": str(e),
                    "summary": f"tool {tool_name} failed",
                },
            )
            return error

    def _handle_recommend_tool(self, from_id: str, arguments: dict) -> str:
        """Handle the recommend_tool special action."""
        target_id = arguments.get("target_synth_id", "")
        tool_name = arguments.get("tool_name", "")
        reason = arguments.get("reason", "")

        if target_id not in self.synths:
            return json.dumps({"error": f"Person '{target_id}' not found"})

        success = self.grant_tool(target_id, tool_name, granted_by=from_id)
        if success:
            # Add a visible system message so everyone sees
            sys_msg = SynthMessage(
                role="assistant",
                content=(
                    f"[📢 {from_id} shared the tool '{tool_name}' with "
                    f"{target_id}. Reason: {reason}]"
                ),
                name="system",
            )
            self.conversation.append(sys_msg)
            return json.dumps({
                "status": "success",
                "message": f"Tool '{tool_name}' shared with {target_id}",
            })
        return json.dumps({"error": f"Could not share tool '{tool_name}'"})

    # ── Event Logging ────────────────────────────────────────────────────

    def _log(self, actor_id: str, event_type: str, payload: dict) -> None:
        event = {
            "id": str(uuid.uuid4()),
            "actor_id": actor_id,
            "event_type": event_type,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.event_logs.append(event)
        self._observe(
            "ENV_EVENT_LOGGED",
            {
                "env_id": self.id,
                "actor_id": actor_id,
                "event_type": event_type,
                "payload": payload,
                "summary": f"logged {event_type}",
            },
        )

    def get_transcript(self) -> str:
        """Get a human-readable transcript of all events."""
        lines = []
        for event in self.event_logs:
            actor = event["actor_id"]
            etype = event["event_type"]
            p = event["payload"]

            if etype == "MESSAGE":
                lines.append(f"{actor}: {p['text']}")
            elif etype == "TOOL_CALL":
                lines.append(f"  [{actor} → {p['tool']}({json.dumps(p['arguments'])})]")
            elif etype == "TOOL_RESULT":
                result = p.get("result", p.get("error", ""))
                lines.append(f"  [{actor} ← {result[:200]}]")
            elif etype == "TOOL_GRANTED":
                lines.append(
                    f"  [🔧 {p['granted_by']} shared '{p['tool']}' with {p['granted_to']}]"
                )
            elif etype == "SYSTEM_ALERT":
                lines.append(f"[SYSTEM] {p['message']}")
            elif etype == "ARTIFACT_INGESTED":
                artifact = p.get("artifact", {})
                lines.append(
                    f"[ARTIFACT] {artifact.get('artifact_type', 'document')} - "
                    f"{artifact.get('title', 'Untitled')}"
                )
            elif etype == "ERROR":
                lines.append(f"[ERROR] {actor}: {p.get('error', '')}")

        return "\n".join(lines)

    def get_stats(self) -> dict:
        """Get summary statistics of the simulation."""
        msg_count = sum(1 for e in self.event_logs if e["event_type"] == "MESSAGE")
        tool_calls = sum(1 for e in self.event_logs if e["event_type"] == "TOOL_CALL")
        tool_grants = sum(1 for e in self.event_logs if e["event_type"] == "TOOL_GRANTED")
        ingested_artifacts = sum(
            1 for e in self.event_logs if e["event_type"] == "ARTIFACT_INGESTED"
        )
        msgs_per_synth = {}
        for e in self.event_logs:
            if e["event_type"] == "MESSAGE":
                actor = e["actor_id"]
                msgs_per_synth[actor] = msgs_per_synth.get(actor, 0) + 1
        return {
            "total_events": len(self.event_logs),
            "messages": msg_count,
            "tool_calls": tool_calls,
            "tool_shares": tool_grants,
            "artifacts_ingested": ingested_artifacts,
            "rounds": self.current_turn,
            "messages_per_synth": msgs_per_synth,
        }

    # ── Persistence & Replay ──────────────────────────────────────────────

    def to_snapshot(self) -> dict:
        """Serialize environment state for lightweight persistence."""
        return {
            "id": self.id,
            "objective": self.objective,
            "max_turns": self.max_turns,
            "current_turn": self.current_turn,
            "status": self.status,
            "conversation": [
                {"role": m.role, "content": m.content, "name": m.name}
                for m in self.conversation
            ],
            "event_logs": list(self.event_logs),
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
        }

    def save_snapshot(self, path: str) -> str:
        """Persist a snapshot JSON file and return the resolved path."""
        output_path = Path(path).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(self.to_snapshot(), indent=2), encoding="utf-8")
        return str(output_path)

    @classmethod
    def load_snapshot(cls, path: str) -> "Environment":
        """Load an environment snapshot for transcript replay/analysis."""
        input_path = Path(path).expanduser().resolve()
        payload = json.loads(input_path.read_text(encoding="utf-8"))

        env = cls(
            objective=payload.get("objective", "Interact naturally."),
            max_turns=payload.get("max_turns", 50),
            env_id=payload.get("id"),
        )
        env.current_turn = payload.get("current_turn", 0)
        env.status = payload.get("status", "COMPLETED")
        env.conversation = [
            SynthMessage(
                role=m.get("role", "assistant"),
                content=m.get("content", ""),
                name=m.get("name"),
            )
            for m in payload.get("conversation", [])
        ]
        env.event_logs = payload.get("event_logs", [])
        env.artifacts = [Artifact.from_dict(a) for a in payload.get("artifacts", [])]
        return env

    def replay_events(
        self,
        callback: Callable[[str, str], None] | None = None,
    ) -> None:
        """Replay event log messages in order for quick run playback."""
        if callback is None:
            return

        for event in self.event_logs:
            actor = event.get("actor_id", "system")
            etype = event.get("event_type")
            payload = event.get("payload", {})

            if etype == "MESSAGE":
                callback(actor, payload.get("text", ""))
            elif etype == "SYSTEM_ALERT":
                callback("system", payload.get("message", ""))
            elif etype == "TOOL_GRANTED":
                callback(
                    "system",
                    f"{payload.get('granted_by')} shared '{payload.get('tool')}' "
                    f"with {payload.get('granted_to')}",
                )

    def _call_synth_initiate(self, synth: Any) -> SynthMessage:
        try:
            return synth.initiate(observer=self._observe)
        except TypeError as e:
            if "unexpected keyword argument 'observer'" in str(e):
                return synth.initiate()
            raise

    def _call_synth_step(
        self,
        synth: Any,
        *,
        conversation: list[SynthMessage],
        tools: list[dict] | None,
        objective: str,
        tool_executor: Callable[[str, dict], str],
    ) -> Any:
        try:
            return synth.step(
                conversation,
                tools=tools,
                objective=objective,
                tool_executor=tool_executor,
                observer=self._observe,
            )
        except TypeError as e:
            if "unexpected keyword argument 'observer'" in str(e):
                return synth.step(
                    conversation,
                    tools=tools,
                    objective=objective,
                    tool_executor=tool_executor,
                )
            raise

    def _observe(self, event_type: str, payload: dict) -> None:
        if self.observer is None:
            return
        try:
            self.observer(event_type, payload)
        except Exception:
            # Observability should never interrupt simulation.
            return