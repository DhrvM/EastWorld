"""EastWorld — Demo Entry Point

Run the full simulation: bootstrap synths, run the autonomous simulation,
then drop into GOD mode or direct synth chat.

Usage:
    python main.py
"""

import sys
import os
import json

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


# ── Personas ─────────────────────────────────────────────────────────────────

PERSONAS = [
    SynthConfig(
        synth_id="Maya-CEO",
        synth_name="Maya",
        persona_prompt=(
            "You are Maya, a 32-year-old CEO of a fintech startup called PayFlow. "
            "You're building a payment orchestration platform and need to ship fast. "
            "You're pragmatic, metrics-driven, and always evaluating new developer tools. "
            "You recently discovered API X (a payment orchestration API) and have been "
            "testing it. You're impressed by its speed and multi-provider routing. "
            "You speak directly, value efficiency, and love sharing useful tools with "
            "other founders. You're data-oriented and back claims with numbers."
        ),
        allowed_connections=["Jake-CTO", "Priya-CEO", "Leo-CEO", "Sam-CEO"],
        allowed_tools=["api_x"],  # Maya starts with API X access
    ),
    SynthConfig(
        synth_id="Jake-CTO",
        synth_name="Jake",
        persona_prompt=(
            "You are Jake, a 29-year-old CTO of an edtech startup called LearnLoop. "
            "You're skeptical of third-party APIs — you've been burned before by vendor "
            "lock-in and unexpected pricing changes. You prefer building in-house when "
            "possible. To convince you, someone needs to show you benchmarks, reliability "
            "data, and a clean developer experience. You're technically sharp, ask probing "
            "questions about architecture, and respect honest technical assessments. "
            "You're currently struggling with payment integration for your course marketplace."
        ),
        allowed_connections=["Maya-CEO", "Priya-CEO", "Leo-CEO", "Sam-CEO"],
        allowed_tools=[],  # No API X access initially
    ),
    SynthConfig(
        synth_id="Priya-CEO",
        synth_name="Priya",
        persona_prompt=(
            "You are Priya, a 35-year-old CEO of a healthtech startup called MedSecure. "
            "You're laser-focused on compliance (HIPAA, SOC2, GDPR). Every tool you evaluate "
            "must pass your compliance checklist. You're methodical, detail-oriented, and "
            "cautious about adopting new tools without proper security documentation. "
            "You're building a patient billing system and need a payment solution, "
            "but it must be PCI DSS Level 1 compliant. You ask about security certifications "
            "before anything else."
        ),
        allowed_connections=["Maya-CEO", "Jake-CTO", "Leo-CEO", "Sam-CEO"],
        allowed_tools=[],
    ),
    SynthConfig(
        synth_id="Leo-CEO",
        synth_name="Leo",
        persona_prompt=(
            "You are Leo, a 26-year-old founder of a social commerce startup called BuzzMarket. "
            "You're a growth hacker at heart — always looking for tools that move fast and "
            "scale. You love trying new APIs and integrating them in a weekend. You're "
            "enthusiastic, move quickly, and care most about developer experience and time-to-"
            "integration. You don't overthink compliance — speed is king. You're building "
            "an in-app marketplace with payments and need a solution ASAP."
        ),
        allowed_connections=["Maya-CEO", "Jake-CTO", "Priya-CEO", "Sam-CEO"],
        allowed_tools=[],
    ),
    SynthConfig(
        synth_id="Sam-CEO",
        synth_name="Sam",
        persona_prompt=(
            "You are Sam, a 38-year-old founder of a B2B SaaS startup called DevDash. "
            "You build developer tooling and have strong opinions about API design. "
            "You evaluate tools through the lens of DX (developer experience): is the "
            "documentation good? Are the error messages clear? Is the SDK idiomatic? "
            "You're building a billing/subscription management feature and need payment "
            "infrastructure. You're thoughtful, mentor-ish, and often help other founders "
            "think through technical decisions."
        ),
        allowed_connections=["Maya-CEO", "Jake-CTO", "Priya-CEO", "Leo-CEO"],
        allowed_tools=[],
    ),
]


# ── Tool Definitions ─────────────────────────────────────────────────────────

def api_x_tool(action: str = "get_docs", endpoint: str = "") -> dict:
    """Simulated API X tool with realistic responses."""
    responses = {
        "get_docs": {
            "name": "API X — Payment Orchestration",
            "version": "2.1.0",
            "description": (
                "A modern payment orchestration API with multi-provider "
                "routing, automatic failover, and smart retries."
            ),
            "key_features": [
                "Multi-PSP routing (Stripe, Adyen, Braintree, PayPal)",
                "Automatic failover with <100ms switching",
                "Smart retry with exponential backoff",
                "PCI DSS Level 1 compliant",
                "SOC 2 Type II certified",
                "HIPAA BAA available on Enterprise plan",
                "Webhook management and event streaming",
                "Built-in analytics and conversion tracking",
                "SDKs: Python, Node, Go, Ruby, Java",
            ],
            "supported_currencies": 135,
            "uptime_sla": "99.99%",
            "avg_latency_ms": 45,
            "p99_latency_ms": 120,
        },
        "test_endpoint": {
            "status": "success",
            "endpoint": endpoint or "/v1/payments",
            "response_time_ms": 38,
            "result": {
                "payment_id": "pay_abc123xyz",
                "status": "completed",
                "amount": 4999,
                "currency": "USD",
                "provider": "stripe",
                "failover_triggered": False,
                "retry_count": 0,
            },
        },
        "get_pricing": {
            "plans": [
                {
                    "name": "Startup",
                    "price": "$49/mo",
                    "transactions": "10,000/mo",
                    "features": ["2 PSPs", "Basic routing", "Email support"],
                },
                {
                    "name": "Growth",
                    "price": "$199/mo",
                    "transactions": "100,000/mo",
                    "features": [
                        "All PSPs", "Smart routing", "Priority support",
                        "Analytics dashboard",
                    ],
                },
                {
                    "name": "Enterprise",
                    "price": "Custom",
                    "transactions": "Unlimited",
                    "features": [
                        "All Growth features", "HIPAA BAA", "Dedicated CSM",
                        "Custom SLA", "On-premise option",
                    ],
                },
            ],
        },
        "check_compliance": {
            "certifications": [
                "PCI DSS Level 1",
                "SOC 2 Type II",
                "ISO 27001",
                "GDPR compliant (EU data residency available)",
            ],
            "hipaa": "Available on Enterprise plan with signed BAA",
            "data_residency": ["US", "EU", "APAC"],
            "encryption": "AES-256 at rest, TLS 1.3 in transit",
            "audit_logs": "Full audit trail, 7-year retention",
        },
    }
    return responses.get(action, {"error": f"Unknown action: {action}"})


TOOL_DEFINITIONS = [
    {
        "name": "api_x",
        "description": (
            "API X — A payment orchestration API. Use this to explore "
            "and test the API. Actions: 'get_docs' (see features & capabilities), "
            "'test_endpoint' (test a specific endpoint), 'get_pricing' "
            "(see pricing plans), 'check_compliance' (see security certifications)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["get_docs", "test_endpoint", "get_pricing", "check_compliance"],
                    "description": "Action to perform",
                },
                "endpoint": {
                    "type": "string",
                    "description": "Specific endpoint to test (for test_endpoint action)",
                },
            },
            "required": ["action"],
        },
        "function": api_x_tool,
    },
]


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

    # ── 1. Create Environment ─────────────────────────────────────────
    objective = (
        "You are five startup founders sharing a co-working space. "
        "Each of you is building a product that needs payment infrastructure. "
        "Chat naturally — share what you're working on, what tools you're using, "
        "ask each other for advice. Maya has been testing a new API called 'API X' "
        "and may share her experience. Be yourselves — agree, disagree, ask questions, "
        "be skeptical or enthusiastic based on your personality."
    )

    env = Environment(objective=objective, max_turns=50)
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

    # Register the recommend_tool system tool
    env.register_tool(
        name="recommend_tool",
        description="Share a tool with another person so they get access to it.",
        parameters={
            "type": "object",
            "properties": {
                "tool_name": {"type": "string", "description": "Tool to share"},
                "target_synth_id": {"type": "string", "description": "Person to share with"},
                "reason": {"type": "string", "description": "Why you're sharing"},
            },
            "required": ["tool_name", "target_synth_id", "reason"],
        },
        function=lambda **kwargs: {"status": "ok"},
    )

    # ── 2. Bootstrap & Register Synths ─────────────────────────────────
    print("📡 Bootstrapping synths (seeding personas into memory)...\n")
    synths_by_name: dict[str, Synth] = {}
    for i, config in enumerate(PERSONAS, 1):
        print(f"  [{i}/{len(PERSONAS)}] {config.synth_name}...", end=" ", flush=True)
        synth = Synth(config, bootstrap=True)
        env.add_synth(synth)
        for artifact in user_artifacts:
            store_memory(synth.synth_id, artifact_to_memory_blob(artifact))
        synths_by_name[config.synth_name.lower()] = synth
        print("✓")

    print(f"\n✅ {len(PERSONAS)} synths ready. Environment ID: {env.id[:8]}...")

    # ── 3. Run Simulation ──────────────────────────────────────────────
    sim_rounds = 6
    print(f"\n{'─' * 60}")
    print(f"  🚀 Running simulation ({sim_rounds} rounds)")
    print(f"{'─' * 60}\n")

    def on_message(sender: str, text: str):
        if sender == "system":
            print(f"  💬 {text}")
        else:
            name = env.synths[sender].synth_name if sender in env.synths else sender
            print(f"  {name}: {text}\n")

    env.run_simulation(rounds=sim_rounds, callback=on_message)

    # ── 4. Post-Simulation Summary ─────────────────────────────────────
    stats = env.get_stats()
    print(f"\n{'─' * 60}")
    print(f"  📊 Simulation Complete")
    print(f"{'─' * 60}")
    print(f"  Rounds: {stats['rounds']} | Messages: {stats['messages']} | "
          f"Tool calls: {stats['tool_calls']} | Tools shared: {stats['tool_shares']}")
    print(f"  Artifacts ingested: {stats['artifacts_ingested']}")
    print(f"  Messages per synth: {stats['messages_per_synth']}")

    # ── 5. Interactive Post-Sim Menu ───────────────────────────────────
    god = God(env)

    print(f"\n{'=' * 60}")
    print("  🎮 Post-Simulation Menu")
    print("=" * 60)

    while True:
        print("\n  1. 🔮 GOD Mode (ask anything about the simulation)")
        print("  2. 💬 Talk to a specific synth")
        print("  3. 📜 View full transcript")
        print("  4. 💾 Save run snapshot")
        print("  5. 🚪 Exit\n")

        choice = input("  Choose [1-5]: ").strip()

        if choice == "1":
            _god_mode(god)
        elif choice == "2":
            _direct_chat(synths_by_name, env)
        elif choice == "3":
            print(f"\n{'─' * 40}")
            print(env.get_transcript())
            print(f"{'─' * 40}")
        elif choice == "4":
            _save_snapshot_prompt(env)
        elif choice == "5":
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
