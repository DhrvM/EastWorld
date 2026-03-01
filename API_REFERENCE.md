# EastWorld API Reference

This document is the authoritative reference for the EastWorld HTTP API served by `api/server.py`.

It is written for application developers, hackathon judges, and operators who need exact request/response behavior.

## 1. API Overview

EastWorld exposes a local-first FastAPI backend for running synthetic-user simulations.

Primary capabilities:

- create simulation sessions with task + synth roster
- ingest artifacts via JSON text or file upload (`.txt`, `.md`, `.pdf`)
- run one or multiple simulation rounds
- send user messages to a specific synth
- query GOD-mode analysis
- retrieve stats, transcript/event logs, and trace stream

## 2. Runtime and Service Metadata

- Framework: FastAPI
- Module entrypoint: `api.server:app`
- Default local command:
  - `uvicorn api.server:app --reload --host 127.0.0.1 --port 8000`
- OpenAPI docs:
  - Swagger UI: `/docs`
  - ReDoc: `/redoc`

### 2.1 CORS

Current CORS policy allows all origins, methods, and headers:

- `allow_origins=["*"]`
- `allow_methods=["*"]`
- `allow_headers=["*"]`
- `allow_credentials=True`

For production deployment, tighten this policy to known frontend origins.

### 2.2 UI Hosting Behavior

- If `web/index.html` exists, `GET /` returns that file.
- If not, `GET /` returns JSON service metadata.
- Static web content is mounted at `/web` when `web/` exists.

## 3. Authentication and Security

Current state:

- No authentication or authorization is enforced.
- Any caller can create/read/operate sessions on this process.

Production recommendation:

- Add API key or JWT auth.
- Scope access by tenant/user.
- Introduce per-session ownership checks.
- Add request-size limits and upload scanning policies.

## 4. Session Model

Simulation state is held in memory (`SessionStore`) and keyed by `env_id`.

Each session contains:

- `env`: `Environment` runtime
- `synths`: synth instances by synth_id
- `god`: `God` (or `MockGod` in mock mode)
- `trace_path`: path to JSONL trace file
- `mock_mode`: whether OpenAI/Supermemory are bypassed

Implications:

- state is process-local and ephemeral
- server restart clears sessions
- not horizontally scalable without shared state

## 5. Data Contracts

## 5.1 Shared Concepts

- `env_id`: unique simulation identifier (UUID string)
- `synth_id`: generated stable ID per synth name
- `artifact_type`: one of:
  - `email`
  - `api_doc`
  - `product_idea`
  - `document`

## 5.2 Request Models

### `SynthInput`

```json
{
  "name": "Ava",
  "persona": "You are Ava, a practical PM."
}
```

### `CreateSimulationRequest`

```json
{
  "task": "Discuss launch risks and GTM strategy from artifacts.",
  "synths": [
    { "name": "Ava", "persona": "..." },
    { "name": "Noah", "persona": "..." }
  ],
  "bootstrap_synths": true,
  "mock_mode": false
}
```

### `RunRoundsRequest`

```json
{
  "rounds": 3
}
```

Constraints:

- integer, `1 <= rounds <= 100`

### `ChatRequest`

```json
{
  "text": "What is the biggest launch blocker?"
}
```

### `GodQueryRequest`

```json
{
  "question": "Summarize top 3 action items and groundedness score."
}
```

### `AddTextArtifactRequest`

```json
{
  "artifact_type": "product_idea",
  "title": "Onboarding Copilot",
  "content": "Build an onboarding copilot for B2B SaaS..."
}
```

## 5.3 Response Model (typed)

### `CreateSimulationResponse`

```json
{
  "env_id": "b3a7f2d2-3be7-49f5-a3db-8b77a1245a6f",
  "synth_ids": ["Ava", "Noah"],
  "trace_path": "runs/traces/b3a7f2d2-3be7-49f5-a3db-8b77a1245a6f.jsonl"
}
```

Most other endpoints return JSON dict payloads documented below.

## 6. Endpoints

All paths are relative to host base URL, e.g. `http://127.0.0.1:8000`.

## 6.1 Service and Discovery

### `GET /`

Returns:

- `FileResponse` serving `web/index.html` when present, OR
- JSON:

```json
{
  "service": "EastWorld API",
  "status": "ok",
  "hint": "Open /web after creating UI"
}
```

### `GET /api/health`

Returns:

```json
{
  "ok": true,
  "time": "2026-03-01T02:40:00.000000+00:00"
}
```

## 6.2 Simulation Lifecycle

### `POST /api/simulations`

Creates a new simulation session.

Behavior:

- synth IDs are sanitized from names (`A-Za-z0-9_-`) with collision suffixing
- full-mesh connections are auto-created
- `recommend_tool` is registered by default
- observer/trace logging is attached
- uses `Synth` or `MockSynth` based on `mock_mode`

Response: `CreateSimulationResponse`.

Common errors:

- `422`: request schema/validation failure

### `GET /api/simulations`

Returns known session IDs:

```json
{
  "env_ids": ["..."]
}
```

### `GET /api/simulations/{env_id}`

Returns simulation metadata:

```json
{
  "status": "ok",
  "env_id": "...",
  "objective": "...",
  "synths": [
    {
      "synth_id": "Ava",
      "name": "Ava",
      "persona_prompt": "..."
    }
  ],
  "mock_mode": true
}
```

Errors:

- `404` if `env_id` not found

## 6.3 Artifact Ingestion

### `POST /api/simulations/{env_id}/artifacts/text`

Adds artifact from JSON text payload.

Request body: `AddTextArtifactRequest`.

Response:

```json
{
  "status": "ok",
  "artifact_id": "..."
}
```

Errors:

- `404`: unknown `env_id`
- `400`: invalid artifact type/title/content

### `POST /api/simulations/{env_id}/artifacts/upload`

Multipart upload endpoint.

Form fields:

- `file` (required)
- `artifact_type` (required)
- `title` (optional)

Accepted suffixes:

- `.txt`
- `.md`
- `.pdf`

Response:

```json
{
  "status": "ok",
  "artifact_id": "...",
  "title": "..."
}
```

Errors:

- `404`: unknown `env_id`
- `400`: unsupported type, parse failure, missing PDF dependency, etc.

## 6.4 Simulation Execution

### `POST /api/simulations/{env_id}/rounds/one`

Runs exactly one round.

Response:

```json
{
  "status": "ok",
  "had_activity": true,
  "round": 3,
  "stats": { "...": "..." }
}
```

### `POST /api/simulations/{env_id}/rounds/many`

Runs up to `rounds` rounds; may stop early if no activity.

Request: `RunRoundsRequest`

Response:

```json
{
  "status": "ok",
  "executed_rounds": 3,
  "current_round": 5,
  "stats": { "...": "..." }
}
```

Errors for round endpoints:

- `404`: unknown `env_id`

## 6.5 User and GOD Interaction

### `POST /api/simulations/{env_id}/chat/{synth_id}`

Sends a user message to one synth and executes immediate response turn.

Request: `ChatRequest`

Response:

```json
{
  "status": "ok",
  "message": "Synth reply...",
  "skip": false
}
```

Errors:

- `404`: unknown `env_id` or `synth_id`
- `400`: runtime/model/tool errors

### `POST /api/simulations/{env_id}/god`

Runs GOD analysis for a question.

Request: `GodQueryRequest`

Response:

```json
{
  "status": "ok",
  "answer": "..."
}
```

Errors:

- `404`: unknown `env_id`
- `400`: runtime/model errors

## 6.6 Read Models (Stats, Transcript, Events, Traces)

### `GET /api/simulations/{env_id}/stats`

Returns:

```json
{
  "status": "ok",
  "stats": {
    "total_events": 42,
    "messages": 16,
    "tool_calls": 3,
    "tool_shares": 1,
    "artifacts_ingested": 2,
    "rounds": 4,
    "messages_per_synth": {
      "Ava": 8,
      "Noah": 8
    }
  }
}
```

### `GET /api/simulations/{env_id}/transcript`

Returns:

- `transcript`: human-readable text transcript
- `events`: raw event array (`env.event_logs`)

### `GET /api/simulations/{env_id}/events?since={offset}`

Incremental event polling.

Parameters:

- `since` (default `0`): 0-based offset into event list

Response:

```json
{
  "status": "ok",
  "events": [ ... ],
  "next_offset": 17
}
```

### `GET /api/simulations/{env_id}/traces?limit={n}`

Reads recent trace events from JSONL.

Parameters:

- `limit` (default `100`)

Response:

```json
{
  "status": "ok",
  "traces": [ ... ]
}
```

## 7. Error Model

Standard HTTP exceptions are returned by FastAPI:

- `404 Not Found` for unknown IDs
- `400 Bad Request` for runtime validation/parsing failures
- `422 Unprocessable Entity` for schema validation errors

Typical body:

```json
{
  "detail": "error message"
}
```

## 8. Grounding and Prompting Behavior

Runtime enforces grounding-oriented guidance:

- synth prompt asks for `[source: ...]` when artifact-backed
- synth prompt asks for `[uncertain: ...]` when evidence is missing
- GOD analysis prompt requests groundedness evaluation and scoring

Grounding signals are emitted in traces (`SYNTH_GROUNDING_CHECK`).

## 9. Observability and Trace Semantics

Each simulation has a trace file:

- `runs/traces/<env_id>.jsonl`

Each line is JSON with:

- `timestamp`
- `run_id`
- `event_type`
- `payload`

High-value events include:

- `ENV_RUN_START`, `ENV_ROUND_START`, `ENV_ROUND_END`, `ENV_RUN_END`
- `LLM_REQUEST`, `LLM_RESPONSE`
- `ENV_TOOL_EXECUTION_START`, `ENV_TOOL_EXECUTION_RESULT`
- `SYNTH_GROUNDING_CHECK`

## 10. Mock Mode vs Live Mode

`mock_mode=true` (recommended for offline demos/tests):

- uses `MockSynth` and `MockGod`
- does not require OpenAI or Supermemory access
- deterministic-ish local behavior for smoke tests

`mock_mode=false`:

- uses real `Synth` + `God`
- requires keys and external model/memory APIs

## 11. Example End-to-End Workflow

1. Create simulation
2. Upload artifacts
3. Run 1-3 rounds
4. Chat with synth
5. Ask GOD question
6. Poll transcript/events/traces

## 11.1 cURL Quickstart

Create session:

```bash
curl -X POST http://127.0.0.1:8000/api/simulations \
  -H "Content-Type: application/json" \
  -d "{\"task\":\"Discuss launch risks\",\"mock_mode\":true,\"bootstrap_synths\":false,\"synths\":[{\"name\":\"Ava\",\"persona\":\"You are Ava, a practical PM.\"},{\"name\":\"Noah\",\"persona\":\"You are Noah, a skeptical engineer.\"}]}"
```

Upload text artifact:

```bash
curl -X POST http://127.0.0.1:8000/api/simulations/<env_id>/artifacts/text \
  -H "Content-Type: application/json" \
  -d "{\"artifact_type\":\"product_idea\",\"title\":\"Onboarding Copilot\",\"content\":\"Build onboarding copilot for B2B SaaS\"}"
```

Run one round:

```bash
curl -X POST http://127.0.0.1:8000/api/simulations/<env_id>/rounds/one
```

Chat with synth:

```bash
curl -X POST http://127.0.0.1:8000/api/simulations/<env_id>/chat/Ava \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"What is our biggest risk?\"}"
```

Ask GOD:

```bash
curl -X POST http://127.0.0.1:8000/api/simulations/<env_id>/god \
  -H "Content-Type: application/json" \
  -d "{\"question\":\"Give top 3 actions and groundedness score\"}"
```

Read traces:

```bash
curl "http://127.0.0.1:8000/api/simulations/<env_id>/traces?limit=50"
```

## 12. Productionization Checklist

Current API is hackathon-ready but not production-hardened. To promote:

- authentication/authorization
- persistent backing store (sessions, artifacts, events, traces)
- strict CORS and CSRF posture
- request limits and upload size constraints
- background job queue for long-running rounds
- structured logging sink (ELK/OpenTelemetry) in addition to JSONL
- retries/circuit breakers around model/memory providers
- contract tests and load tests
- API versioning strategy (e.g., `/v1`)

## 13. Source of Truth

For behavior details, see:

- `api/server.py`
- `api/session_store.py`
- `artifacts/upload.py`
- `environment/main.py`
