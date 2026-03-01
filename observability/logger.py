"""Real-time simulation observability helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ObserverFn = Callable[[str, dict], None]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=True, default=str)


def _preview_text(value: Any, max_chars: int = 120) -> str:
    text = str(value or "")
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


class SimulationObserver:
    """Writes structured events to JSONL and optional live console."""

    def __init__(
        self,
        *,
        run_id: str,
        output_path: str | None = None,
        console: bool = True,
    ) -> None:
        self.run_id = run_id
        self.console = console
        self.output_path = (
            Path(output_path).expanduser().resolve() if output_path else None
        )
        if self.output_path is not None:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event_type: str, payload: dict) -> None:
        event = {
            "timestamp": _utc_now(),
            "run_id": self.run_id,
            "event_type": event_type,
            "payload": payload,
        }

        if self.output_path is not None:
            with self.output_path.open("a", encoding="utf-8") as f:
                f.write(_safe_json(event) + "\n")

        if self.console:
            actor = payload.get("actor_id") or payload.get("synth_id") or "system"
            summary = payload.get("summary")
            if not summary:
                summary = _preview_text(
                    payload.get("text")
                    or payload.get("content")
                    or payload.get("message")
                    or payload
                )
            print(f"[trace][{event_type}][{actor}] {summary}")


def build_observer(
    *,
    run_id: str,
    trace_dir: str = "runs/traces",
    console: bool = True,
) -> SimulationObserver:
    trace_path = Path(trace_dir).expanduser().resolve() / f"{run_id}.jsonl"
    return SimulationObserver(run_id=run_id, output_path=str(trace_path), console=console)
