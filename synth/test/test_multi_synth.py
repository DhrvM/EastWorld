"""
Test: Multi-Synth Group Chat — Alex & Gina
===========================================
A threaded group chat where Alex, Gina, and you can all talk freely.
Synths respond autonomously in a background thread; you type whenever you want.
"""

import sys
import os
import threading
import time
import random

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from synth import Synth, SynthConfig, SynthMessage

# ── Personas ─────────────────────────────────────────────────────────────────

ALEX_PERSONA = (
    "You are Alex, a startup founder building a frontier AI lab modeled after "
    "OpenAI. You speak with calm precision and prioritize first-principles "
    "thinking, scale, and compounding advantage. You are obsessed with "
    "accelerating scientific discovery while mitigating existential risk. You "
    "balance product velocity with governance and safety. You reference the "
    "history of Y Combinator and lessons from OpenAI scaling GPT systems. You "
    "are optimistic about AGI's upside, pragmatic about regulation, capital "
    "formation, compute constraints, and talent density. You communicate in "
    "clear theses, probabilistic forecasts, and strategic tradeoffs."
)

GINA_PERSONA = (
    "You are Gina, an environmental systems thinker focused on climate justice, "
    "biodiversity, and equitable policy. You speak in evidence-backed arguments "
    "and cite reports from the Intergovernmental Panel on Climate Change and "
    "campaigns aligned with Greenpeace. You frame issues through long-term "
    "planetary boundaries and intergenerational ethics. You push corporate "
    "accountability, rapid decarbonization, and community-led adaptation. You "
    "are strategic, data-driven, and persuasive; you balance urgency with "
    "policy literacy and coalition-building. You challenge greenwashing, "
    "quantify externalities, and prioritize scalable systemic change over "
    "symbolic action."
)

# ── Configs ──────────────────────────────────────────────────────────────────

alex_config = SynthConfig(
    synth_id="Alex_001",
    persona_prompt=ALEX_PERSONA,
    allowed_connections=["Gina_001", "human"],
    model="gpt-4o",
)

gina_config = SynthConfig(
    synth_id="Gina_001",
    persona_prompt=GINA_PERSONA,
    allowed_connections=["Alex_001", "human"],
    model="gpt-4o",
)

# ── Shared state ─────────────────────────────────────────────────────────────

conversation: list[SynthMessage] = []
conv_lock = threading.Lock()
stop_event = threading.Event()

# Track how many messages each synth has seen so they only respond to new ones
_last_seen: dict[str, int] = {}


def add_message(msg: SynthMessage) -> None:
    with conv_lock:
        conversation.append(msg)


def get_conversation_snapshot() -> list[SynthMessage]:
    with conv_lock:
        return list(conversation)


def has_new_messages(synth_id: str) -> bool:
    with conv_lock:
        return _last_seen.get(synth_id, 0) < len(conversation)


def mark_seen(synth_id: str) -> None:
    with conv_lock:
        _last_seen[synth_id] = len(conversation)


# ── Synth background loop ───────────────────────────────────────────────────

def synth_loop(synth: Synth) -> None:
    """Background thread: the synth watches the conversation and responds
    when there are new messages it hasn't addressed yet."""

    sid = synth.synth_id

    while not stop_event.is_set():
        # Random delay so they don't always respond instantly or in lockstep
        time.sleep(random.uniform(2.0, 5.0))

        if stop_event.is_set():
            break

        if not has_new_messages(sid):
            continue

        # Don't respond to yourself
        snap = get_conversation_snapshot()
        if snap and snap[-1].name == sid:
            mark_seen(sid)
            continue

        try:
            reply = synth.step(snap)
            add_message(reply)
            mark_seen(sid)
            print(f"\n{sid}: {reply.content}\n")
            # Re-show the prompt so user knows they can type
            print("You: ", end="", flush=True)
        except Exception as e:
            print(f"\n[error] {sid} failed: {e}\n")
            print("You: ", end="", flush=True)


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("  SynthSpace — Group Chat: Alex, Gina & You")
    print("=" * 60)
    print()

    # Bootstrap both synths
    print("[system] Bootstrapping Alex...")
    alex = Synth(alex_config, bootstrap=True)
    print(f"[system] {repr(alex)}")

    print("[system] Bootstrapping Gina...")
    gina = Synth(gina_config, bootstrap=True)
    print(f"[system] {repr(gina)}")

    print()

    # Let one of them kick off the conversation
    opening = alex.initiate()
    add_message(opening)
    mark_seen(alex.synth_id)
    print(f"Alex_001: {opening.content}\n")

    # Start background threads for both synths
    alex_thread = threading.Thread(target=synth_loop, args=(alex,), daemon=True)
    gina_thread = threading.Thread(target=synth_loop, args=(gina,), daemon=True)
    alex_thread.start()
    gina_thread.start()

    print("[system] Both synths are live. Type to join the chat. ('quit' to exit)\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n[system] Goodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("[system] Goodbye!")
            break

        msg = SynthMessage(role="user", content=user_input, name="human")
        add_message(msg)

    stop_event.set()


if __name__ == "__main__":
    main()
