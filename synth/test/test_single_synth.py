"""
Test: Single Synth — Alex
=========================
Bootstraps a single synth with a rich persona, then drops into an
interactive terminal chat so you can talk to Alex directly.
"""

import sys
import os

# Ensure project root is on the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from synth import Synth, SynthConfig, SynthMessage

# ── Configuration ────────────────────────────────────────────────────────────

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

config = SynthConfig(
    synth_id="Test_001",
    persona_prompt=ALEX_PERSONA,
    allowed_connections=[],
    model="gpt-4o",
)


def main() -> None:
    print("=" * 60)
    print("  SynthSpace — Interactive Chat with Alex")
    print("=" * 60)
    print()

    # ── Bootstrap ────────────────────────────────────────────────────────
    print("[system] Bootstrapping Alex's persona into Supermemory...")
    alex = Synth(config, bootstrap=True)
    print(f"[system] {repr(alex)}")
    print("[system] Ready.\n")

    # Let Alex speak first
    opening = alex.initiate()
    print(f"Alex: {opening.content}\n")
    conversation: list[SynthMessage] = [opening]

    print("[system] Type your messages below. (Ctrl+C or 'quit' to exit)\n")

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

        conversation.append(SynthMessage(role="user", content=user_input))

        reply = alex.step(conversation)
        print(f"\nAlex: {reply.content}\n")

        conversation.append(reply)


if __name__ == "__main__":
    main()
