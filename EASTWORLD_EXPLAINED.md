# EastWorld Explained

This document explains how EastWorld works end-to-end: what modules exist, how the simulation runs, how synths think and use tools, how artifacts are ingested, how observability works, and what is currently missing.

## 1) What EastWorld Is

EastWorld is a synthetic environment simulator where persona-driven agents ("synths") discuss a scenario and can use tools. A human user can provide artifacts (emails, API docs, product ideas, documents), and synths use those artifacts as context during discussion.

Core outcomes:

- autonomous multi-agent conversation loop
- tool usage and tool sharing between synths
- long-term memory with Supermemory
- post-run analytics (GOD mode)
- run snapshots and replay
- real-time observability traces

## 2) Project Structure

- `main.py`  
  Main CLI/TUI entrypoint. Handles startup, artifact input, simulation execution, menu, GOD mode, direct synth chat, snapshot save/replay.

- `environment/main.py`  
  In-memory orchestrator for synths, tools, simulation rounds, logging, stats, routing checks, replay, and observer hooks.

- `synth/synth.py`  
  Core agent cognition loop: builds prompt, retrieves memory context, calls OpenAI, executes tools, stores memory, returns response/skip.

- `synth/memory.py`  
  Supermemory integration: persona bootstrap, context retrieval, memory writes.

- `synth/models.py`  
  Data models: `SynthConfig`, `SynthMessage`, `StepResult`.

- `artifacts/models.py` and `artifacts/ingest.py`  
  Canonical artifact model + ingestion/validation from text/file + context formatting helpers.

- `prompt.py`  
  Centralized prompt definitions/builders used by all OpenAI calls.

- `god.py`  
  Omniscient analysis assistant over transcript/stats.

- `observability/logger.py`  
  Real-time structured event sink (console + JSONL traces).

- `environment/test_integration.py`, `environment/test_chat_integration.py`, `synth/test/*`  
  Smoke/integration and interactive scripts.

## 3) Runtime Flow (Main User Journey)

When running `python main.py`:

1. Optional snapshot replay prompt appears.
2. New simulation path:
   - Environment is created.
   - Observability is attached (live trace + JSONL output).
   - User optionally ingests artifacts (`text` or `file`).
   - Tools are registered (`recommend_tool` and any user-defined tools).
   - Synths are bootstrapped and added to environment.
   - Artifact memory blobs are injected into each synth's memory.
3. Simulation rounds run.
4. Post-simulation menu:
   - GOD mode Q/A
   - direct chat with a synth
   - transcript view
   - snapshot save
   - exit

## 4) Synth Cognition (How an Agent "Thinks")

`Synth.step(...)` in `synth/synth.py` does:

1. Get latest conversation message.
2. Retrieve memory context from Supermemory via `get_synth_context(...)`.
3. Build system prompt using `build_synth_system_prompt(...)` from `prompt.py`.
4. Call OpenAI Chat Completions.
5. If model emits tool calls:
   - execute each tool via callback,
   - append tool outputs as tool messages,
   - re-call model (loop up to `_MAX_TOOL_ROUNDS`).
6. If output contains `[SKIP]`, synth skips turn.
7. Otherwise store turn memory and return a `SynthMessage`.

`Synth.initiate(...)` is similar but uses `SYNTH_INITIATION_USER_PROMPT`.

## 5) Environment Orchestration (How the World Runs)

`Environment.run_simulation(...)` in `environment/main.py`:

- sets status to `RUNNING`
- builds objective context with participant summaries and ingested artifacts
- seeds system message if needed
- optionally asks first synth to open conversation
- loops by rounds and synths
- enforces "no self reply"
- enforces routing via `allowed_connections` (`_can_synth_reply`)
- executes synth turns
- ends when all synths skip or round limit reached
- sets status to `COMPLETED`

Event logs are stored in `self.event_logs` and converted to readable text via `get_transcript()`.

## 6) Tools System

Tools are registered dynamically with:

- name
- description
- JSON schema (`parameters`)
- Python function implementation

At runtime:

- synth sees only allowed tools (`_get_tool_schemas_for`)
- tool calls are executed by `_execute_tool(...)`
- tool call/result events are logged
- synths can share tools via special `recommend_tool` flow, handled by `_handle_recommend_tool(...)`

## 7) Artifact Ingestion Pipeline

Artifacts are first-class objects (`Artifact`) with:

- `artifact_type`
- `title`
- `content`
- `source`
- `metadata`
- IDs/timestamps

Ingestion:

- `ingest_artifact_from_text(...)`
- `ingest_artifact_from_file(...)`

Usage in simulation:

- stored in `Environment.artifacts`
- added to objective context via `artifact_context_block(...)`
- logged as `ARTIFACT_INGESTED`
- also injected into each synth memory as `[Artifact]` blobs

## 8) Prompts Centralization

All OpenAI prompt text now lives in `prompt.py`:

- `SYNTH_BEHAVIORAL_ENVELOPE`
- `SYNTH_INITIATION_USER_PROMPT`
- `BOOTSTRAP_PERSONA_SYSTEM_PROMPT`
- `build_synth_system_prompt(...)`
- `build_god_system_prompt(...)`

This gives one place to tune behavior/prompt engineering.

## 9) Observability (Real-Time Trace)

`SimulationObserver` emits structured events:

- console line: `[trace][EVENT][actor] summary`
- JSONL line per event to: `runs/traces/<env_id>.jsonl`

Observed events include:

- environment lifecycle: `ENV_RUN_START`, `ENV_ROUND_START`, `ENV_ROUND_END`, `ENV_RUN_END`
- synth lifecycle: `SYNTH_TURN_START`, `SYNTH_MEMORY_CONTEXT`, `SYNTH_RESPONSE`, `SYNTH_SKIP`
- OpenAI operations: `LLM_REQUEST`, `LLM_RESPONSE` (includes latency + token usage if present)
- tools: `SYNTH_TOOL_INTENT`, `ENV_TOOL_EXECUTION_START`, `ENV_TOOL_EXECUTION_RESULT`, `ENV_TOOL_EXECUTION_ERROR`
- routing: `ENV_REPLY_BLOCKED`
- logging: `ENV_EVENT_LOGGED`

Observability is "best effort": failures in observer sink are caught so simulation never crashes because of logging.

## 10) Snapshots and Replay

`Environment` supports:

- `to_snapshot()`
- `save_snapshot(path)`
- `load_snapshot(path)`
- `replay_events(callback)`

Snapshot includes objective, status, turn count, conversation, event logs, and artifacts.

## 11) GOD Mode

`God.ask(question)`:

- loads transcript + stats + participant summary
- builds system prompt via `build_god_system_prompt(...)`
- asks OpenAI for analytical answers
- retains chat history for follow-up questions in same session

## 12) Data Models

Key models:

- `SynthConfig`: identity/persona/model + permissions
- `SynthMessage`: role/content/name message format
- `StepResult`: one of message/tool_calls/skip
- `Artifact`: canonical user-input knowledge unit

## 13) Testing and Validation Paths

Useful scripts:

- `python environment/test_integration.py`  
  Environment smoke test with mock synths.

- `python environment/test_chat_integration.py`  
  Routing-focused smoke test.

- `python synth/test/test_single_synth.py`  
  Interactive single-agent test.

- `python synth/test/test_multi_synth.py`  
  Interactive multi-agent thread test.

## 14) Current Limitations

EastWorld is currently an in-memory, CLI-first system.

Known gaps:

- no HTTP API/web UI layer
- no durable DB persistence for production workloads
- no true hidden chain-of-thought visibility (only observable request/response/tool traces)
- no advanced scheduling/planning between synths (simple round-robin loop)

## 15) Extension Ideas (Next)

- add API server (FastAPI) for remote runs and artifact uploads
- persist runs/events/artifacts to database
- add trace filters and per-synth dashboards
- add richer artifact adapters (URL ingest, email provider, docs parser)
- add experiment configs for reproducible benchmark runs

