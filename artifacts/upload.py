"""Upload helpers for artifact files."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from .ingest import ingest_artifact_from_text
from .models import Artifact


def ingest_uploaded_artifact(
    *,
    filename: str,
    raw_bytes: bytes,
    content_type: str,
    artifact_type: str,
    title: str | None = None,
) -> Artifact:
    """Parse uploaded bytes into a normalized Artifact."""
    suffix = Path(filename).suffix.lower()
    normalized_title = (title or "").strip() or Path(filename).name
    content = _extract_text(filename=filename, raw_bytes=raw_bytes, content_type=content_type, suffix=suffix)

    return ingest_artifact_from_text(
        artifact_type=artifact_type,
        title=normalized_title,
        content=content,
        source="upload",
        metadata={
            "filename": filename,
            "content_type": content_type,
            "suffix": suffix,
        },
    )


def _extract_text(*, filename: str, raw_bytes: bytes, content_type: str, suffix: str) -> str:
    if suffix in {".txt", ".md"}:
        return raw_bytes.decode("utf-8", errors="ignore")
    if suffix == ".pdf":
        return _extract_pdf_text(raw_bytes)
    raise ValueError(
        f"Unsupported file type for {filename!r}. Only .txt, .md, and .pdf are supported."
    )


def _extract_pdf_text(raw_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader
    except Exception as e:
        raise RuntimeError(
            "PDF support requires pypdf. Install dependencies with `pip install -r requirements.txt`."
        ) from e

    reader = PdfReader(BytesIO(raw_bytes))
    pages: list[str] = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    text = "\n".join(pages).strip()
    if not text:
        return "[No extractable text found in PDF]"
    return text
