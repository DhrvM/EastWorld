"""EastWorld — Demo Entry Point

Run the full simulation: bootstrap synths, run the autonomous simulation,
then drop into GOD mode or direct synth chat.

Usage:
    python main.py
"""

import sys
import os
import json
import re

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from artifacts import (
    Artifact,
    ArtifactIngestionError,
    artifact_to_memory_blob,
    ingest_artifact_from_file,
    ingest_artifact_from_text,
)
from observability import build_observer
from synth import Synth, SynthConfig, SynthMessage
from synth.memory import store_memory
from environment.main import Environment
from god import God


# ── Tool Definitions ─────────────────────────────────────────────────────────
TOOL_DEFINITIONS: list[dict] = []


# ── Main ─────────────────────────────────────────────────────────────────────

def print_header():
    print("\n" + "=" * 60)
    print("  🌐 EastWorld — Synthetic User Simulation")
    print("=" * 60)
    print()


def run_demo():
    print_header()
    replay_path = input(
        "Replay a previous run snapshot? Enter path or press Enter for new run: "
    ).strip()
    if replay_path:
        _replay_snapshot_mode(replay_path)
        return

    synth_configs = _collect_synth_configs()
    objective = _collect_task_objective()

    # ── 1. Create Environment ─────────────────────────────────────────
    env = Environment(objective=objective, max_turns=1000)
    observer = _setup_observability(env.id)
    env.set_observer(observer.emit)
    user_artifacts = _collect_user_artifacts()
    if user_artifacts:
        env.add_artifacts(user_artifacts)

    # Register tools
    for tool_def in TOOL_DEFINITIONS:
        env.register_tool(
            name=tool_def["name"],
            description=tool_def["description"],
            parameters=tool_def["parameters"],
            function=tool_def["function"],
        )

    # ── 2. Bootstrap & Register Synths ─────────────────────────────────
    print("📡 Bootstrapping synths (seeding personas into memory)...\n")
    synths_by_name: dict[str, Synth] = {}
    for i, config in enumerate(synth_configs, 1):
        print(f"  [{i}/{len(synth_configs)}] {config.synth_name}...", end=" ", flush=True)
        synth = Synth(config, bootstrap=True)
        env.add_synth(synth)
        for artifact in user_artifacts:
            store_memory(synth.synth_id, artifact_to_memory_blob(artifact))
        synths_by_name[config.synth_name.lower()] = synth
        print("✓")

    print(f"\n✅ {len(synth_configs)} synths ready. Environment ID: {env.id[:8]}...")
    print(f"\n🎯 Task:\n{objective}\n")

    # ── 3. Interactive Simulation Control ──────────────────────────────
    print(f"\n{'─' * 60}")
    print("  🚀 Interactive simulation started")
    print("  Run as many rounds as you want; use menu anytime.")
    print(f"{'─' * 60}\n")

    def on_message(sender: str, text: str):
        if sender == "system":
            print(f"  💬 {text}")
        else:
            name = env.synths[sender].synth_name if sender in env.synths else sender
            print(f"  {name}: {text}\n")

    god = God(env)
    print(f"\n{'=' * 60}")
    print("  🎮 Simulation Control Menu")
    print("=" * 60)

    while True:
        print("\n  1. ▶️ Run one round")
        print("  2. ⏩ Run N rounds")
        print("  3. 🔮 GOD Mode (mid-simulation)")
        print("  4. 💬 Talk to a specific synth (mid-simulation)")
        print("  5. 📥 Add artifact")
        print("  6. 📊 View stats")
        print("  7. 📜 View full transcript")
        print("  8. 💾 Save run snapshot")
        print("  9. ✅ End simulation and exit\n")

        choice = input("  Choose [1-9]: ").strip()

        if choice == "1":
            had_activity = env.run_round(callback=on_message)
            if not had_activity:
                print("  [system] No synths responded this round.")
        elif choice == "2":
            rounds = _prompt_positive_int("  Run how many rounds? ", default=3)
            for _ in range(rounds):
                had_activity = env.run_round(callback=on_message)
                if not had_activity:
                    print("  [system] No synths responded; stopping early.")
                    break
        elif choice == "3":
            _god_mode(god)
        elif choice == "4":
            _direct_chat(synths_by_name, env)
        elif choice == "5":
            new_artifacts = _collect_user_artifacts()
            if new_artifacts:
                env.add_artifacts(new_artifacts)
                for synth in env.synths.values():
                    for artifact in new_artifacts:
                        store_memory(synth.synth_id, artifact_to_memory_blob(artifact))
        elif choice == "6":
            stats = env.get_stats()
            print(f"\n{'─' * 60}")
            print(f"  📊 Live Simulation Stats")
            print(f"{'─' * 60}")
            print(f"  Rounds: {stats['rounds']} | Messages: {stats['messages']} | "
                  f"Tool calls: {stats['tool_calls']} | Tools shared: {stats['tool_shares']}")
            print(f"  Artifacts ingested: {stats['artifacts_ingested']}")
            print(f"  Messages per synth: {stats['messages_per_synth']}")
        elif choice == "7":
            print(f"\n{'─' * 40}")
            print(env.get_transcript())
            print(f"{'─' * 40}")
        elif choice == "8":
            _save_snapshot_prompt(env)
        elif choice == "9":
            env.finish()
            stats = env.get_stats()
            print(f"\n{'─' * 60}")
            print(f"  📊 Final Simulation Summary")
            print(f"{'─' * 60}")
            print(f"  Rounds: {stats['rounds']} | Messages: {stats['messages']} | "
                  f"Tool calls: {stats['tool_calls']} | Tools shared: {stats['tool_shares']}")
            print(f"  Artifacts ingested: {stats['artifacts_ingested']}")
            print("\n  👋 Goodbye!\n")
            break
        else:
            print("  Invalid choice.")


def _god_mode(god: God):
    """Interactive GOD mode — ask questions about the simulation."""
    print(f"\n  {'─' * 50}")
    print("  🔮 GOD MODE — Ask anything. Type 'back' to return.\n")

    while True:
        try:
            question = input("  You: ").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if not question or question.lower() in ("back", "exit", "quit"):
            break

        print("  ⏳ Analyzing...\n")
        answer = god.ask(question)
        print(f"  GOD: {answer}\n")


def _direct_chat(synths_by_name: dict, env: Environment):
    """Chat directly with a specific synth, with simulation context."""
    names = list(synths_by_name.keys())
    print(f"\n  Available synths: {', '.join(n.title() for n in names)}")
    name = input("  Who do you want to talk to? ").strip().lower()

    if name not in synths_by_name:
        print(f"  Unknown synth. Choose from: {', '.join(names)}")
        return

    synth = synths_by_name[name]
    print(f"\n  💬 Chatting with {synth.synth_name}. Type 'back' to return.\n")

    # Use the simulation conversation as context
    chat_conversation = list(env.conversation)

    while True:
        try:
            user_input = input(f"  You: ").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if not user_input or user_input.lower() in ("back", "exit", "quit"):
            break

        chat_conversation.append(
            SynthMessage(role="user", content=user_input, name="human")
        )

        # Get tool schemas for this synth
        tool_schemas = env._get_tool_schemas_for(synth)

        def tool_executor(tool_name, args):
            return env._execute_tool(synth.synth_id, tool_name, args)

        result = synth.step(
            chat_conversation,
            tools=tool_schemas,
            objective=env.objective,
            tool_executor=tool_executor,
            observer=env._observe,
        )

        if result.message:
            chat_conversation.append(result.message)
            print(f"\n  {synth.synth_name}: {result.message.content}\n")
        elif result.skip:
            print(f"\n  {synth.synth_name}: *shrugs*\n")
        else:
            print(f"\n  {synth.synth_name}: (no response)\n")


def _collect_synth_configs() -> list[SynthConfig]:
    print("🧬 Define your synth roster.")
    synth_count = _prompt_positive_int("  How many synths do you want? ", default=3)

    entries: list[tuple[str, str]] = []
    for i in range(1, synth_count + 1):
        print(f"\n  Synth {i}/{synth_count}")
        name = input("  Name: ").strip() or f"Synth{i}"
        persona = _prompt_multiline(
            "  Persona prompt (end with a line containing only 'END'):"
        ).strip()
        if not persona:
            persona = (
                f"You are {name}, a thoughtful synthetic user. You discuss the task "
                "naturally, ask questions, and provide specific opinions."
            )
        entries.append((name, persona))

    synth_ids: list[str] = []
    configs: list[SynthConfig] = []
    for idx, (name, persona) in enumerate(entries, 1):
        synth_id = _make_synth_id(name, idx, set(synth_ids))
        synth_ids.append(synth_id)
        configs.append(
            SynthConfig(
                synth_id=synth_id,
                synth_name=name,
                persona_prompt=persona,
                allowed_connections=[],
                allowed_tools=[],
            )
        )

    # Full-mesh by default so every synth can reply to every other synth.
    for cfg in configs:
        cfg.allowed_connections = [sid for sid in synth_ids if sid != cfg.synth_id]
    return configs


def _collect_task_objective() -> str:
    print("\n📝 Define what synths should discuss.")
    print("   Enter the task/objective. End with a line containing only 'END'.")
    task = _prompt_multiline("  Task: ").strip()
    if not task:
        task = "Discuss the provided artifacts and derive actionable feedback."
    return task


def _collect_user_artifacts() -> list[Artifact]:
    """Collect optional user artifacts for the simulation."""
    print("📥 Optional: attach user artifacts (emails/docs/product ideas).")
    print("   Press Enter to skip.")

    artifacts: list[Artifact] = []
    while True:
        choice = input("  Add artifact? [text/file/skip]: ").strip().lower()
        if choice in {"", "skip", "no", "n"}:
            break
        if choice not in {"text", "file"}:
            print("  Invalid choice. Use 'text', 'file', or 'skip'.")
            continue

        artifact = _prompt_single_artifact(choice)
        if artifact is not None:
            artifacts.append(artifact)
            print(f"  ✓ Added {artifact.artifact_type}: {artifact.title}")

    if artifacts:
        print(f"  Collected {len(artifacts)} artifact(s).\n")
    else:
        print("  No artifacts added.\n")
    return artifacts


def _prompt_single_artifact(mode: str) -> Artifact | None:
    artifact_type = input(
        "  Type [email/api_doc/product_idea/document]: "
    ).strip().lower()
    title = input("  Title: ").strip()
    try:
        if mode == "file":
            file_path = input("  File path: ").strip()
            return ingest_artifact_from_file(
                artifact_type=artifact_type,
                title=title,
                file_path=file_path,
            )

        print("  Paste content below. End with a line containing only 'END'.")
        lines: list[str] = []
        while True:
            line = input()
            if line.strip() == "END":
                break
            lines.append(line)
        return ingest_artifact_from_text(
            artifact_type=artifact_type,
            title=title,
            content="\n".join(lines),
        )
    except ArtifactIngestionError as exc:
        print(f"  Could not ingest artifact: {exc}")
    except OSError as exc:
        print(f"  File read error: {exc}")
    return None


def _prompt_multiline(prompt: str) -> str:
    print(prompt)
    lines: list[str] = []
    while True:
        line = input()
        if line.strip() == "END":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def _make_synth_id(name: str, index: int, existing: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")
    if not base:
        base = f"Synth_{index}"
    candidate = base
    suffix = 2
    while candidate in existing:
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


def _prompt_positive_int(prompt: str, default: int = 1) -> int:
    while True:
        raw = input(prompt).strip()
        if not raw:
            return default
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
        print("  Please enter a positive integer.")


def _save_snapshot_prompt(env: Environment) -> None:
    default_name = f"runs/{env.id}.json"
    path = input(f"  Snapshot path [{default_name}]: ").strip() or default_name
    saved_path = env.save_snapshot(path)
    print(f"  ✓ Saved snapshot: {saved_path}")


def _setup_observability(env_id: str):
    print("🛰️ Observability: real-time tracing is enabled.")
    observer = build_observer(run_id=env_id, trace_dir="runs/traces", console=True)
    print(f"   Trace file: runs/traces/{env_id}.jsonl\n")
    return observer


def _replay_snapshot_mode(snapshot_path: str) -> None:
    try:
        env = Environment.load_snapshot(snapshot_path)
    except OSError as exc:
        print(f"\n  Could not load snapshot: {exc}\n")
        return
    except json.JSONDecodeError as exc:
        print(f"\n  Invalid snapshot JSON: {exc}\n")
        return

    print(f"\n  Loaded snapshot for environment: {env.id[:8]}...")
    print(f"  Objective: {env.objective}\n")
    print("  Replaying event stream:\n")

    def on_event(sender: str, text: str):
        if sender == "system":
            print(f"  [SYSTEM] {text}")
        else:
            print(f"  {sender}: {text}")

    env.replay_events(callback=on_event)
    print("\n  Transcript:\n")
    print(env.get_transcript())


if __name__ == "__main__":
    run_demo()
