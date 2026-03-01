"""Integration smoke test for Environment using local mock synths only."""

from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from artifacts import ingest_artifact_from_text
from environment.main import Environment
from synth.models import StepResult, SynthMessage


class MockSynth:
    def __init__(
        self,
        synth_id: str,
        *,
        allowed_connections: list[str],
        allowed_tools: list[str] | None = None,
    ) -> None:
        self.synth_id = synth_id
        self.id = synth_id
        self.synth_name = synth_id
        self.persona_prompt = f"Mock persona for {synth_id}"
        self.allowed_connections = allowed_connections
        self.allowed_tools = allowed_tools or []

    def can_message(self, target_synth_id: str) -> bool:
        return target_synth_id in self.allowed_connections

    def initiate(self) -> SynthMessage:
        return SynthMessage(
            role="assistant",
            content=f"Hi, {self.synth_name} here. Let's discuss the artifacts.",
            name=self.synth_id,
        )

    def step(
        self,
        conversation: list[SynthMessage],
        *,
        tools=None,
        objective=None,
        tool_executor=None,
    ) -> StepResult:
        last = conversation[-1].content if conversation else "No context"
        if "nothing to add" in last.lower():
            return StepResult(skip=True)
        return StepResult(
            message=SynthMessage(
                role="assistant",
                content=f"{self.synth_name} responding to: {last[:80]}",
                name=self.synth_id,
            )
        )


def run_integration() -> None:
    env = Environment(
        objective="Discuss whether we should launch this product idea.",
        max_turns=4,
    )
    env.register_tool(
        name="echo_tool",
        description="Echoes text back.",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        function=lambda text: {"echo": text},
    )

    artifact = ingest_artifact_from_text(
        artifact_type="product_idea",
        title="AI-first onboarding copilot",
        content=(
            "Build an onboarding copilot that analyzes product docs and "
            "suggests personalized setup steps for each new user."
        ),
    )
    env.add_artifact(artifact)

    maya = MockSynth("Maya-01", allowed_connections=["Jake-02"], allowed_tools=["echo_tool"])
    jake = MockSynth("Jake-02", allowed_connections=["Maya-01"], allowed_tools=[])
    env.add_synth(maya)
    env.add_synth(jake)

    print(f"Environment {env.id} running...")
    env.run_simulation(rounds=3, callback=lambda sender, text: print(f"{sender}: {text}"))

    runs_dir = project_root / "runs"
    runs_dir.mkdir(exist_ok=True)
    snapshot_path = runs_dir / "integration-smoke.json"
    saved = env.save_snapshot(str(snapshot_path))
    replay_env = Environment.load_snapshot(saved)

    print("\n--- Stats ---")
    print(env.get_stats())
    print("\n--- Transcript ---")
    print(replay_env.get_transcript())


if __name__ == "__main__":
    run_integration()
