"""Canonical artifact model used by the simulation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid


@dataclass
class Artifact:
    """A user-provided artifact that synths can discuss."""

    artifact_type: str
    title: str
    content: str
    source: str = "user_input"
    metadata: dict = field(default_factory=dict)
    artifact_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "title": self.title,
            "content": self.content,
            "source": self.source,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "Artifact":
        return cls(
            artifact_type=payload.get("artifact_type", "document"),
            title=payload.get("title", "Untitled artifact"),
            content=payload.get("content", ""),
            source=payload.get("source", "user_input"),
            metadata=payload.get("metadata", {}),
            artifact_id=payload.get("artifact_id", str(uuid.uuid4())),
            created_at=payload.get(
                "created_at", datetime.now(timezone.utc).isoformat()
            ),
        )
