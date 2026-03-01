"""Helpers for ingesting and formatting user artifacts."""

from __future__ import annotations

from pathlib import Path

from .models import Artifact


class ArtifactIngestionError(ValueError):
    pass


def ingest_artifact_from_text(
    *,
    artifact_type: str,
    title: str,
    content: str,
    source: str = "user_input",
    metadata: dict | None = None,
) -> Artifact:
    artifact_type = (artifact_type or "").strip().lower()
    title = (title or "").strip()
    content = (content or "").strip()

    if artifact_type not in {"email", "api_doc", "product_idea", "document"}:
        raise ArtifactIngestionError(
            "artifact_type must be one of: email, api_doc, product_idea, document"
        )
    if not title:
        raise ArtifactIngestionError("title cannot be empty")
    if not content:
        raise ArtifactIngestionError("content cannot be empty")

    return Artifact(
        artifact_type=artifact_type,
        title=title,
        content=content,
        source=source,
        metadata=metadata or {},
    )


def ingest_artifact_from_file(
    *,
    artifact_type: str,
    title: str,
    file_path: str,
    source: str = "local_file",
    metadata: dict | None = None,
) -> Artifact:
    path = Path(file_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise ArtifactIngestionError(f"file not found: {path}")
    content = path.read_text(encoding="utf-8")
    file_metadata = {"file_path": str(path)}
    if metadata:
        file_metadata.update(metadata)
    return ingest_artifact_from_text(
        artifact_type=artifact_type,
        title=title,
        content=content,
        source=source,
        metadata=file_metadata,
    )


def artifact_to_memory_blob(artifact: Artifact) -> str:
    return (
        f"[Artifact]\n"
        f"type: {artifact.artifact_type}\n"
        f"title: {artifact.title}\n"
        f"source: {artifact.source}\n"
        f"content:\n{artifact.content}"
    )


def artifact_context_block(artifacts: list[Artifact], *, max_chars: int = 3000) -> str:
    if not artifacts:
        return ""

    chunks: list[str] = []
    remaining = max_chars
    for index, artifact in enumerate(artifacts, 1):
        chunk = (
            f"Artifact {index}\n"
            f"- type: {artifact.artifact_type}\n"
            f"- title: {artifact.title}\n"
            f"- source: {artifact.source}\n"
            f"- content: {artifact.content}\n"
        )
        if remaining <= 0:
            break
        if len(chunk) <= remaining:
            chunks.append(chunk)
            remaining -= len(chunk)
            continue

        chunks.append(chunk[:remaining] + "...")
        remaining = 0
        break

    return "\n".join(chunks)
