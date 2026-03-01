"""Core Synth class — the AI agent with memory-backed cognition."""

from __future__ import annotations

import json
import os
import time
from typing import Callable

from dotenv import load_dotenv
from openai import OpenAI

from prompt import SYNTH_INITIATION_USER_PROMPT, build_synth_system_prompt
from .memory import bootstrap_persona, get_synth_context, store_memory
from .models import SynthConfig, SynthMessage, StepResult

load_dotenv()

_oai_client: OpenAI | None = None


def _get_oai_client() -> OpenAI:
    global _oai_client
    if _oai_client is None:
        _oai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _oai_client


_MAX_TOOL_ROUNDS = 5  # Safety cap on consecutive tool calls per turn


class Synth:
    """A persona-driven AI agent backed by Supermemory for long-term context."""

    def __init__(self, config: SynthConfig, bootstrap: bool = True) -> None:
        self.config = config
        self.synth_id = config.synth_id
        self.id = config.synth_id
        self.synth_name = config.synth_name
        self.model = config.model
        self.persona_prompt = config.persona_prompt
        self.allowed_connections = list(config.allowed_connections)
        self.allowed_tools = list(config.allowed_tools)

        self._bootstrapped = False
        if bootstrap:
            self._run_bootstrap()

    # ── Public API ───────────────────────────────────────────────────────

    def step(
        self,
        conversation: list[SynthMessage],
        *,
        tools: list[dict] | None = None,
        objective: str | None = None,
        tool_executor: Callable[[str, dict], str] | None = None,
        observer: Callable[[str, dict], None] | None = None,
    ) -> StepResult:
        """Execute one cognitive turn with optional tool calling.

        Parameters
        ----------
        conversation : list[SynthMessage]
            The shared conversation history.
        tools : list[dict] | None
            OpenAI-format tool schemas available to this synth.
        objective : str | None
            Environment objective to inject into the system prompt.
        tool_executor : callable | None
            Callback ``(tool_name, arguments) -> result_string``.
            If provided, tool calls are executed inline and the LLM
            is re-prompted with results. If ``None``, tool calls are
            returned in the StepResult for external handling.

        Returns
        -------
        StepResult
        """
        last_message = conversation[-1].content if conversation else ""
        _emit_observation(
            observer,
            "SYNTH_TURN_START",
            {
                "synth_id": self.synth_id,
                "model": self.model,
                "conversation_len": len(conversation),
                "tool_count": len(tools or []),
                "summary": f"{self.synth_id} turn start, messages={len(conversation)}",
            },
        )
        memory_context = get_synth_context(self.synth_id, last_message)
        _emit_observation(
            observer,
            "SYNTH_MEMORY_CONTEXT",
            {
                "synth_id": self.synth_id,
                "memory_chars": len(memory_context),
                "last_message_preview": (last_message[:120] + "...") if len(last_message) > 120 else last_message,
                "summary": f"memory loaded ({len(memory_context)} chars)",
            },
        )

        # Build system prompt
        system_content = build_synth_system_prompt(
            persona_prompt=self.persona_prompt,
            objective=objective,
            memory_context=memory_context,
        )

        # Build messages
        messages: list[dict] = [
            {"role": "system", "content": system_content},
            *[m.to_dict() for m in conversation],
        ]

        # Tool-calling loop
        for loop_idx in range(_MAX_TOOL_ROUNDS):
            kwargs: dict = {"model": self.model, "messages": messages}
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            _emit_observation(
                observer,
                "LLM_REQUEST",
                {
                    "synth_id": self.synth_id,
                    "model": self.model,
                    "loop_idx": loop_idx,
                    "message_count": len(messages),
                    "tools_enabled": bool(tools),
                    "tool_names": [
                        t.get("function", {}).get("name", "")
                        for t in (tools or [])
                        if isinstance(t, dict)
                    ],
                    "last_message_preview": (
                        messages[-1].get("content", "")[:180] + "..."
                        if messages and len(messages[-1].get("content", "")) > 180
                        else (messages[-1].get("content", "") if messages else "")
                    ),
                    "summary": f"llm request loop={loop_idx}",
                },
            )

            call_started = time.perf_counter()
            response = _get_oai_client().chat.completions.create(**kwargs)
            latency_ms = int((time.perf_counter() - call_started) * 1000)
            choice = response.choices[0]
            usage = getattr(response, "usage", None)
            _emit_observation(
                observer,
                "LLM_RESPONSE",
                {
                    "synth_id": self.synth_id,
                    "model": self.model,
                    "loop_idx": loop_idx,
                    "latency_ms": latency_ms,
                    "usage": {
                        "prompt_tokens": getattr(usage, "prompt_tokens", None),
                        "completion_tokens": getattr(usage, "completion_tokens", None),
                        "total_tokens": getattr(usage, "total_tokens", None),
                    } if usage is not None else None,
                    "content_preview": (
                        (choice.message.content or "")[:220] + "..."
                        if len(choice.message.content or "") > 220
                        else (choice.message.content or "")
                    ),
                    "tool_calls": [
                        tc.function.name for tc in (choice.message.tool_calls or [])
                    ],
                    "summary": f"llm response latency={latency_ms}ms",
                },
            )

            # ── Handle tool calls ────────────────────────────────────
            if choice.message.tool_calls:
                if tool_executor is None:
                    # Return tool calls for external handling
                    return StepResult(
                        tool_calls=[
                            {
                                "id": tc.id,
                                "name": tc.function.name,
                                "arguments": _safe_json_parse(tc.function.arguments),
                            }
                            for tc in choice.message.tool_calls
                        ]
                    )

                # Execute tools inline and loop
                # Append the assistant message (with tool_calls) to thread
                messages.append({
                    "role": "assistant",
                    "content": choice.message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in choice.message.tool_calls
                    ],
                })

                for tc in choice.message.tool_calls:
                    args = _safe_json_parse(tc.function.arguments)
                    _emit_observation(
                        observer,
                        "SYNTH_TOOL_INTENT",
                        {
                            "synth_id": self.synth_id,
                            "tool": tc.function.name,
                            "arguments": args,
                            "summary": f"tool intent {tc.function.name}",
                        },
                    )
                    try:
                        result = tool_executor(tc.function.name, args)
                    except Exception as e:
                        result = f"Error executing tool: {e}"
                        _emit_observation(
                            observer,
                            "SYNTH_TOOL_EXECUTOR_ERROR",
                            {
                                "synth_id": self.synth_id,
                                "tool": tc.function.name,
                                "error": str(e),
                                "summary": f"tool executor error {tc.function.name}",
                            },
                        )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": str(result),
                    })

                continue  # Re-prompt with tool results

            # ── Handle text response ─────────────────────────────────
            text: str = choice.message.content or ""

            if "[SKIP]" in text:
                _emit_observation(
                    observer,
                    "SYNTH_SKIP",
                    {
                        "synth_id": self.synth_id,
                        "reason": "model emitted [SKIP]",
                        "summary": f"{self.synth_id} skipped turn",
                    },
                )
                return StepResult(skip=True)

            # Memory ingestion
            store_memory(
                self.synth_id,
                f"[Turn] Last input: {last_message}\n[Response] {text}",
            )
            _emit_observation(
                observer,
                "SYNTH_RESPONSE",
                {
                    "synth_id": self.synth_id,
                    "content_preview": (text[:220] + "...") if len(text) > 220 else text,
                    "summary": f"{self.synth_id} produced response",
                },
            )

            return StepResult(
                message=SynthMessage(
                    role="assistant", content=text, name=self.synth_id
                )
            )

        # Exhausted tool rounds — treat as skip
        _emit_observation(
            observer,
            "SYNTH_SKIP",
            {
                "synth_id": self.synth_id,
                "reason": "tool loop exhausted",
                "summary": f"{self.synth_id} skipped after tool loop cap",
            },
        )
        return StepResult(skip=True)

    def initiate(
        self,
        observer: Callable[[str, dict], None] | None = None,
    ) -> SynthMessage:
        """Generate an opening message with no prior conversation."""
        _emit_observation(
            observer,
            "SYNTH_INITIATE_START",
            {
                "synth_id": self.synth_id,
                "model": self.model,
                "summary": f"{self.synth_id} initiating conversation",
            },
        )
        memory_context = get_synth_context(self.synth_id, "starting a conversation")

        system_content = build_synth_system_prompt(
            persona_prompt=self.persona_prompt,
            objective=None,
            memory_context=memory_context,
        )
        messages: list[dict] = [
            {"role": "system", "content": system_content},
            {
                "role": "user",
                "content": SYNTH_INITIATION_USER_PROMPT,
            },
        ]

        call_started = time.perf_counter()
        response = _get_oai_client().chat.completions.create(
            model=self.model, messages=messages
        )
        latency_ms = int((time.perf_counter() - call_started) * 1000)
        reply_text: str = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        _emit_observation(
            observer,
            "SYNTH_INITIATE_RESPONSE",
            {
                "synth_id": self.synth_id,
                "latency_ms": latency_ms,
                "usage": {
                    "prompt_tokens": getattr(usage, "prompt_tokens", None),
                    "completion_tokens": getattr(usage, "completion_tokens", None),
                    "total_tokens": getattr(usage, "total_tokens", None),
                } if usage is not None else None,
                "content_preview": (
                    reply_text[:220] + "..." if len(reply_text) > 220 else reply_text
                ),
                "summary": f"{self.synth_id} opening message ready",
            },
        )
        store_memory(self.synth_id, f"[Initiated] {reply_text}")

        return SynthMessage(role="assistant", content=reply_text, name=self.synth_id)

    def can_message(self, target_synth_id: str) -> bool:
        return target_synth_id in self.allowed_connections

    # ── Internals ────────────────────────────────────────────────────────

    def _run_bootstrap(self) -> None:
        bootstrap_persona(
            synth_id=self.synth_id,
            persona_prompt=self.persona_prompt,
            model=self.model,
        )
        self._bootstrapped = True

    def __repr__(self) -> str:
        return (
            f"Synth(id={self.synth_id!r}, name={self.synth_name!r}, "
            f"model={self.model!r}, tools={self.allowed_tools})"
        )


def _safe_json_parse(s: str) -> dict:
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return {}


def _emit_observation(
    observer: Callable[[str, dict], None] | None,
    event_type: str,
    payload: dict,
) -> None:
    if observer is None:
        return
    try:
        observer(event_type, payload)
    except Exception:
        # Observability must never break the simulation.
        return
