"""Core Synth class — the AI agent with memory-backed cognition."""

from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

from .memory import bootstrap_persona, get_synth_context, store_memory
from .models import SynthConfig, SynthMessage

load_dotenv()

_oai_client: OpenAI | None = None


def _get_oai_client() -> OpenAI:
    global _oai_client
    if _oai_client is None:
        _oai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _oai_client


# ── Behavioral envelope — injected on every turn ────────────────────────────
_BEHAVIORAL_ENVELOPE = """\
You ARE this person. You are not an AI, a language model, or an assistant.
You have real experiences, opinions, and emotions. Never break character.
Never mention being an AI. Never use phrases like "How can I assist you?"
or "I'm here to help." You do not "assist" anyone — you are a person
having a conversation.

Speak naturally — short sentences, casual tone, personality quirks.
Don't monologue. Keep responses to 1-3 sentences unless the topic genuinely
demands more depth. You can be blunt, disagreeable, distracted, or
bored — whatever fits your persona in the moment.
"""


class Synth:
    """A persona-driven AI agent backed by Supermemory for long-term context.

    Parameters
    ----------
    config : SynthConfig
        The agent's identity, persona, connection rules, and model choice.
    bootstrap : bool
        If ``True`` (default), immediately runs persona bootstrapping via
        OpenAI → Supermemory so the synth has rich memories from the start.

    Example
    -------
    >>> from synth import Synth, SynthConfig, SynthMessage
    >>> config = SynthConfig(
    ...     synth_id="alex-001",
    ...     persona_prompt="Alex is a 28-year-old indie game developer ...",
    ...     allowed_connections=["jordan-002"],
    ...     model="gpt-4o",
    ... )
    >>> agent = Synth(config)
    >>> reply = agent.step([
    ...     SynthMessage(role="user", content="Hey Alex, what are you working on?", name="jordan-002"),
    ... ])
    >>> print(reply.content)
    """

    def __init__(self, config: SynthConfig, bootstrap: bool = True) -> None:
        self.config = config
        self.synth_id = config.synth_id
        # Also alias to id so Environment can easily read it
        self.id = config.synth_id
        self.synth_name = config.synth_id # Fallback name
        self.model = config.model
        self.persona_prompt = config.persona_prompt
        self.allowed_connections = set(config.allowed_connections)
        self.allowed_tools = config.allowed_tools

        # Bootstrap: expand the persona and seed Supermemory
        self._bootstrapped = False
        if bootstrap:
            self._run_bootstrap()

    # ── Public API ───────────────────────────────────────────────────────

    def step(self, conversation: list[SynthMessage]) -> SynthMessage:
        """Execute one cognitive turn.

        The full loop (TDD §3.2):
        1. **Context assembly** — fetch memories relevant to the latest message.
        2. **Prompt build** — system msg (persona + memory context) + conversation.
        3. **LLM call** — ``openai.chat.completions.create``.
        4. **Memory ingestion** — store the response for future recall.

        Parameters
        ----------
        conversation : list[SynthMessage]
            The conversation history leading up to this turn.

        Returns
        -------
        SynthMessage
            The synth's response.
        """

        # 1. Context assembly
        last_message = conversation[-1].content if conversation else ""
        memory_context = get_synth_context(self.synth_id, last_message)

        # 2. Prompt build
        system_content = (
            f"{_BEHAVIORAL_ENVELOPE}\n"
            f"{self.persona_prompt}\n\n"
            f"--- Memory Context ---\n{memory_context}"
        )
        messages: list[dict] = [
            {"role": "system", "content": system_content},
            *[m.to_dict() for m in conversation],
        ]

        # 3. LLM call
        response = _get_oai_client().chat.completions.create(
            model=self.model,
            messages=messages,
        )
        reply_text: str = response.choices[0].message.content or ""

        # 4. Memory ingestion — store what just happened
        memory_record = (
            f"[Turn] Last input: {last_message}\n"
            f"[Response] {reply_text}"
        )
        store_memory(self.synth_id, memory_record)

        return SynthMessage(
            role="assistant",
            content=reply_text,
            name=self.synth_id,
        )

    def initiate(self) -> SynthMessage:
        """Generate an opening message with no prior conversation.

        The synth uses its persona + memory context to say something
        natural — a thought, observation, or question — as if starting
        a conversation on its own.
        """

        memory_context = get_synth_context(self.synth_id, "starting a conversation")

        system_content = (
            f"{_BEHAVIORAL_ENVELOPE}\n"
            f"{self.persona_prompt}\n\n"
            f"--- Memory Context ---\n{memory_context}"
        )
        messages: list[dict] = [
            {"role": "system", "content": system_content},
            {
                "role": "user",
                "content": (
                    "Start a conversation. Say something natural — a thought, "
                    "observation, or question you'd have right now given your "
                    "current situation and memories. Be yourself."
                ),
            },
        ]

        response = _get_oai_client().chat.completions.create(
            model=self.model,
            messages=messages,
        )
        reply_text: str = response.choices[0].message.content or ""

        store_memory(self.synth_id, f"[Initiated] {reply_text}")

        return SynthMessage(
            role="assistant",
            content=reply_text,
            name=self.synth_id,
        )

    def can_message(self, target_synth_id: str) -> bool:
        """Return ``True`` if this synth is allowed to message *target_synth_id*."""
        return target_synth_id in self.allowed_connections

    def send_message(
        self,
        target_synth_id: str,
        content: str,
    ) -> Optional[SynthMessage]:
        """Validate the connection and create an outbound message.

        Returns ``None`` if the target is not in ``allowed_connections``.
        """

        if not self.can_message(target_synth_id):
            return None

        return SynthMessage(
            role="user",
            content=content,
            name=self.synth_id,
        )

    # ── Internals ────────────────────────────────────────────────────────

    def _run_bootstrap(self) -> None:
        """Expand the persona via OpenAI and seed Supermemory."""
        bootstrap_persona(
            synth_id=self.synth_id,
            persona_prompt=self.persona_prompt,
            model=self.model,
        )
        self._bootstrapped = True

    def __repr__(self) -> str:
        return (
            f"Synth(id={self.synth_id!r}, model={self.model!r}, "
            f"connections={sorted(self.allowed_connections)})"
        )
