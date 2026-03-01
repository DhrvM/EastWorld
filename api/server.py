"""FastAPI backend for EastWorld local web demo."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import uuid

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from artifacts import ingest_artifact_from_text
from api.session_store import SessionStore
from synth import SynthConfig


class SynthInput(BaseModel):
    name: str = Field(min_length=1)
    persona: str = Field(min_length=1)


class CreateSimulationRequest(BaseModel):
    task: str = Field(min_length=1)
    synths: list[SynthInput] = Field(min_length=1)
    bootstrap_synths: bool = True
    mock_mode: bool = False


class CreateSimulationResponse(BaseModel):
    env_id: str
    synth_ids: list[str]
    trace_path: str


class RunRoundsRequest(BaseModel):
    rounds: int = Field(default=1, ge=1, le=100)


class ChatRequest(BaseModel):
    text: str = Field(min_length=1)


class GodQueryRequest(BaseModel):
    question: str = Field(min_length=1)


class AddTextArtifactRequest(BaseModel):
    artifact_type: str
    title: str
    content: str


app = FastAPI(title="EastWorld API", version="0.1.0")
store = SessionStore()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

web_dir = Path("web").resolve()
if web_dir.exists():
    app.mount("/web", StaticFiles(directory=str(web_dir), html=True), name="web")


def _make_synth_id(name: str, index: int, existing: set[str]) -> str:
    import re

    base = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")
    if not base:
        base = f"Synth_{index}"
    candidate = base
    suffix = 2
    while candidate in existing:
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


def _build_full_mesh_configs(synths: list[SynthInput]) -> list[SynthConfig]:
    synth_ids: list[str] = []
    configs: list[SynthConfig] = []

    for idx, s in enumerate(synths, 1):
        synth_id = _make_synth_id(s.name, idx, set(synth_ids))
        synth_ids.append(synth_id)
        configs.append(
            SynthConfig(
                synth_id=synth_id,
                synth_name=s.name,
                persona_prompt=s.persona,
                allowed_connections=[],
                allowed_tools=[],
            )
        )
    for cfg in configs:
        cfg.allowed_connections = [sid for sid in synth_ids if sid != cfg.synth_id]
    return configs


@app.get("/")
def root():
    index = web_dir / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"service": "EastWorld API", "status": "ok", "hint": "Open /web after creating UI"}


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "time": datetime.now(timezone.utc).isoformat()}


@app.post("/api/simulations", response_model=CreateSimulationResponse)
def create_simulation(payload: CreateSimulationRequest) -> CreateSimulationResponse:
    synth_configs = _build_full_mesh_configs(payload.synths)
    session = store.create_session(
        objective=payload.task,
        synth_configs=synth_configs,
        bootstrap_synths=payload.bootstrap_synths,
        mock_mode=payload.mock_mode,
    )
    return CreateSimulationResponse(
        env_id=session.env.id,
        synth_ids=list(session.synths.keys()),
        trace_path=str(session.trace_path),
    )


@app.get("/api/simulations")
def list_simulations() -> dict:
    return {"env_ids": store.list_ids()}


@app.get("/api/simulations/{env_id}")
def get_simulation(env_id: str) -> dict:
    try:
        session = store.get(env_id)
        return {
            "status": "ok",
            "env_id": session.env.id,
            "objective": session.env.objective,
            "synths": [
                {
                    "synth_id": s.synth_id,
                    "name": s.synth_name,
                    "persona_prompt": s.persona_prompt,
                }
                for s in session.synths.values()
            ],
            "mock_mode": session.mock_mode,
        }
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/simulations/{env_id}/artifacts/text")
def add_text_artifact(env_id: str, payload: AddTextArtifactRequest) -> dict:
    try:
        artifact = ingest_artifact_from_text(
            artifact_type=payload.artifact_type,
            title=payload.title,
            content=payload.content,
        )
        store.add_artifacts(env_id, [artifact])
        return {"status": "ok", "artifact_id": artifact.artifact_id}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/simulations/{env_id}/artifacts/upload")
def upload_artifact(
    env_id: str,
    file: UploadFile = File(...),
    artifact_type: str = Form(...),
    title: str | None = Form(default=None),
) -> dict:
    from artifacts.upload import ingest_uploaded_artifact

    try:
        content = file.file.read()
        artifact = ingest_uploaded_artifact(
            filename=file.filename or f"artifact-{uuid.uuid4()}.txt",
            raw_bytes=content,
            content_type=file.content_type or "",
            artifact_type=artifact_type,
            title=title,
        )
        store.add_artifacts(env_id, [artifact])
        return {"status": "ok", "artifact_id": artifact.artifact_id, "title": artifact.title}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/simulations/{env_id}/rounds/one")
def run_one_round(env_id: str) -> dict:
    try:
        session = store.get(env_id)
        had_activity = session.env.run_round()
        return {
            "status": "ok",
            "had_activity": had_activity,
            "round": session.env.current_turn,
            "stats": session.env.get_stats(),
        }
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/simulations/{env_id}/rounds/many")
def run_many_rounds(env_id: str, payload: RunRoundsRequest) -> dict:
    try:
        session = store.get(env_id)
        executed = 0
        for _ in range(payload.rounds):
            had_activity = session.env.run_round()
            executed += 1
            if not had_activity:
                break
        return {
            "status": "ok",
            "executed_rounds": executed,
            "current_round": session.env.current_turn,
            "stats": session.env.get_stats(),
        }
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/simulations/{env_id}/chat/{synth_id}")
def chat_with_synth(env_id: str, synth_id: str, payload: ChatRequest) -> dict:
    try:
        result = store.user_chat(env_id, synth_id, payload.text)
        return {"status": "ok", **result}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/simulations/{env_id}/god")
def god_query(env_id: str, payload: GodQueryRequest) -> dict:
    try:
        session = store.get(env_id)
        answer = session.god.ask(payload.question)
        return {"status": "ok", "answer": answer}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/simulations/{env_id}/stats")
def simulation_stats(env_id: str) -> dict:
    try:
        session = store.get(env_id)
        return {"status": "ok", "stats": session.env.get_stats()}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/simulations/{env_id}/transcript")
def simulation_transcript(env_id: str) -> dict:
    try:
        session = store.get(env_id)
        return {
            "status": "ok",
            "transcript": session.env.get_transcript(),
            "events": session.env.event_logs,
        }
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/simulations/{env_id}/events")
def simulation_events(env_id: str, since: int = 0) -> dict:
    try:
        session = store.get(env_id)
        events = session.env.event_logs[max(0, since):]
        return {
            "status": "ok",
            "events": events,
            "next_offset": max(0, since) + len(events),
        }
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/simulations/{env_id}/traces")
def simulation_traces(env_id: str, limit: int = 100) -> dict:
    try:
        traces = store.read_trace_events(env_id, limit=limit)
        return {"status": "ok", "traces": traces}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
