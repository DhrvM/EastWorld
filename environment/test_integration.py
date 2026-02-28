import sys
from pathlib import Path

# Add project root to path to import local modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from environment.main import Environment
from synth.models import SynthConfig
from synth import Synth


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

# We'll create a mock Synth class to avoid triggering OpenAI/Supermemory calls during a simple state test
# since those require real API keys and internet dependency.
class TestSynth:
    def __init__(self, config: SynthConfig):
        self.config = config
        self.id = config.synth_id
        self.synth_name = config.synth_id 
        self.allowed_connections = set(config.allowed_connections)
        self.allowed_tools = config.allowed_tools

def run_integration():
    print("Initializing In-Memory Environment with a subset of tools...")
    env = Environment(
        objective="Find out the secret code.",
        active_tools=["execute_python"] # Exclude 'read_file' and 'web_search'
    )

    print(f"\nEnvironment created. ID: {env.id}")
    print(f"Objective: {env.objective}")
    print(f"Active Tools: {list(env.tools.keys())}")

    # Create Alice config who wants to use execute_python (allowed) and read_file (not allowed)
    alex_config = SynthConfig(
        synth_id="Alex-01",
        persona_prompt=ALEX_PERSONA,
        allowed_tools=["execute_python", "read_file"],
        allowed_connections=["Bob-02"]
    )
    
    # Create Bob config who wants only to execute python
    gina_config = SynthConfig(
        synth_id="Gina-02",
        persona_prompt=GINA_PERSONA,
        allowed_tools=["execute_python"],
        allowed_connections=["Alice-01"]
    )

    alex = Synth(alex_config)
    gina = Synth(gina_config)

    print("\nAdding Alex to Environment...")
    env.add_synth(alex)
    
    print("Adding Gina to Environment...")
    env.add_synth(gina)

    print("\nEnvironment Synths:")
    for s_id, s in env.synths.items():
        print(f" - ID: {s_id}")
        print(f"   Tools: {s.allowed_tools}")
        print(f"   Connections: {s.allowed_connections}")

    print("\nTesting Tool Execution:")
    # Alice tries to use execute_python (should work)
    print("Alex executing 'execute_python':")
    res1 = env.execute_tool("Alex-01", "execute_python", {"code": "print('Hello')"})
    print(f"Result: {res1}")

    # Alice tries to use read_file (should be stripped by Environment since it's not active)
    print("\nAlex executing 'read_file':")
    res2 = env.execute_tool("Alex-01", "read_file", {"path": "/tmp/secret.txt"})
    print(f"Result: {res2}")

    print("\nEvent Transcript length:", len(env.event_logs))
    for log in env.event_logs:
        print(f" - {log['event_type']} by {log['actor_id']}: {log['payload']}")

if __name__ == "__main__":
    run_integration()
