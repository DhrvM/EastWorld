"""Routing integration smoke test for connection-aware Environment turns."""

from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from environment.main import Environment
from synth.models import StepResult, SynthMessage


class RoutingMockSynth:
    def __init__(self, synth_id: str, allowed_connections: list[str]):
        self.synth_id = synth_id
        self.id = synth_id
        self.synth_name = synth_id
        self.persona_prompt = f"Routing test persona {synth_id}"
        self.allowed_connections = allowed_connections
        self.allowed_tools = []

    def can_message(self, target_synth_id: str) -> bool:
        return target_synth_id in self.allowed_connections

    def initiate(self) -> SynthMessage:
        return SynthMessage(role="assistant", content=f"Opening from {self.synth_id}", name=self.synth_id)

    def step(
        self,
        conversation: list[SynthMessage],
        *,
        tools=None,
        objective=None,
        tool_executor=None,
    ) -> StepResult:
        return StepResult(
            message=SynthMessage(
                role="assistant",
                content=f"{self.synth_id} replies",
                name=self.synth_id,
            )
        )


def run_routing_integration() -> None:
    env = Environment(objective="Validate allowed connection routing.", max_turns=3)
    alex = RoutingMockSynth("Alex-01", allowed_connections=["Gina-02"])
    gina = RoutingMockSynth("Gina-02", allowed_connections=["Alex-01"])
    charlie = RoutingMockSynth("Charlie-03", allowed_connections=[])

    env.add_synth(alex)
    env.add_synth(gina)
    env.add_synth(charlie)
    env.run_simulation(rounds=2, callback=lambda s, t: print(f"{s}: {t}"))

    transcript = env.get_transcript()
    print("\n--- Transcript ---")
    print(transcript)
    print("\n--- Routing note ---")
    print("Charlie should be mostly silent because he cannot reply to anyone.")


if __name__ == "__main__":
    run_routing_integration()
