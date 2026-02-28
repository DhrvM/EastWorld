"""Data models for the Synth architecture."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SynthConfig:
    """Configuration for a single Synth agent.

    Parameters
    ----------
    synth_id : str
        Unique identifier — also used as the Supermemory container_tag.
    persona_prompt : str
        Rich persona description.  The more detail (historic conversations,
        past decisions, preferences, personality quirks) the more lifelike the
        synth will be during bootstrapping.
    allowed_connections : list[str]
        IDs of other synths this agent is allowed to message.
    allowed_tools : list[str]
        Names of the tools this synth is allowed to execute.
    model : str
        OpenAI model name to use for this synth (default ``gpt-4o``).
    """

    synth_id: str
    persona_prompt: str
    allowed_connections: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    model: str = "gpt-4o"

    def __post_init__(self) -> None:
        import re
        if not re.match(r"^[A-Za-z0-9_-]+$", self.synth_id):
            raise ValueError(
                f"synth_id {self.synth_id!r} is invalid — only alphanumeric "
                f"characters, hyphens, and underscores are allowed "
                f"(Supermemory containerTag constraint)."
            )


@dataclass
class SynthMessage:
    """A single message in a synth conversation.

    Parameters
    ----------
    role : str
        One of ``"system"``, ``"user"``, ``"assistant"``.
    content : str
        The text body of the message.
    name : str | None
        Optional sender identifier (e.g. the synth_id of whoever sent it).
    """

    role: str
    content: str
    name: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to the dict format expected by the OpenAI API."""
        msg: dict = {"role": self.role, "content": self.content}
        if self.name:
            msg["name"] = self.name
        return msg
