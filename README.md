# EastWorld

EastWorld is a synthetic environment simulator for product exploration with
persona-driven synthetic users ("synths"). You can provide artifacts
(emails, API docs, product ideas), run a multi-agent discussion, and inspect
the transcript or ask GOD-mode analysis questions.

## Current Capabilities

- Multi-synth simulation loop with event logs and transcript stats.
- Persona bootstrapping and long-term memory via Supermemory.
- Tool-calling inside synth turns (OpenAI function calling format).
- Artifact ingestion from pasted text or local files.
- Post-run GOD mode for transcript-level analysis.
- Snapshot save/load for replaying prior runs.
- Real-time observability stream with JSONL trace logs.

## Quick Start

1. Create and activate a Python virtual environment.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Create `.env` with:
   - `OPENAI_API_KEY=...`
   - `SUPERMEMORY_API_KEY=...`
4. Run:
   - `python main.py`

At startup you can:
- load a previous run snapshot, or
- start a new run and optionally attach artifacts.

## Artifact Ingestion (MVP)

When starting a new run, the CLI prompts:
- `text`: paste content and end with `END`
- `file`: provide a local file path
- `skip`: continue without artifacts

Supported artifact types:
- `email`
- `api_doc`
- `product_idea`
- `document`

## Useful Scripts

- `python main.py` — main demo flow
- `python environment/test_integration.py` — environment smoke test (mock synths)
- `python environment/test_chat_integration.py` — routing smoke test
- `python synth/test/test_single_synth.py` — direct single-synth interactive test
- `python synth/test/test_multi_synth.py` — threaded group chat test

## Snapshot Replay

From `main.py` post-simulation menu:
- choose **Save run snapshot** to write JSON under `runs/` (or custom path)

At startup:
- provide a snapshot path to replay prior events/transcript without rerunning.

## Observability

Running `python main.py` now enables live trace output by default.

- Console stream: `[trace][EVENT_TYPE][actor] summary`
- Structured trace file: `runs/traces/<env_id>.jsonl`

Trace events include:
- environment lifecycle (`ENV_RUN_START`, `ENV_ROUND_START`, `ENV_RUN_END`)
- synth cognition (`SYNTH_TURN_START`, `SYNTH_MEMORY_CONTEXT`, `LLM_REQUEST`, `LLM_RESPONSE`)
- tool flow (`SYNTH_TOOL_INTENT`, `ENV_TOOL_EXECUTION_START`, `ENV_TOOL_EXECUTION_RESULT`)
- transcript writes (`ENV_EVENT_LOGGED`)
- routing and skip signals (`ENV_REPLY_BLOCKED`, `SYNTH_SKIP`)
