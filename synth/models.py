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
        Rich persona description.
    synth_name : str
        Human-readable display name. Defaults to synth_id.
    allowed_connections : list[str]
        IDs of other synths this agent is allowed to message.
    allowed_tools : list[str]
        Names of the tools this synth is allowed to execute.
    model : str
        OpenAI model name (default ``gpt-4o``).
    """

    synth_id: str
    persona_prompt: str
    synth_name: str = ""
    allowed_connections: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    model: str = "gpt-4o"

    def __post_init__(self) -> None:
        import re
        if not re.match(r"^[A-Za-z0-9_-]+$", self.synth_id):
            raise ValueError(
                f"synth_id {self.synth_id!r} is invalid — only alphanumeric "
                f"characters, hyphens, and underscores are allowed."
            )
        if not self.synth_name:
            self.synth_name = self.synth_id


@dataclass
class SynthMessage:
    """A single message in a synth conversation."""

    role: str
    content: str
    name: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to the dict format expected by the OpenAI API."""
        msg: dict = {"role": self.role, "content": self.content}
        if self.name:
            msg["name"] = self.name
        return msg


@dataclass
class StepResult:
    """Result of a single cognitive step.

    Exactly one of ``message``, ``skip=True``, or ``tool_calls`` will be set.
    """

    message: Optional[SynthMessage] = None
    tool_calls: Optional[list] = None
    skip: bool = False
