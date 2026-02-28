import asyncio
import sys
from pathlib import Path

# Add project root to path to import local modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from environment.main import Environment
from chatroom.main import Agent, ChatSystem, ChatRoom
from synth.models import SynthConfig
from synth import Synth

ALEX_PERSONA = (
    "You are Alex, a startup founder building a frontier AI lab modeled after OpenAI."
)

GINA_PERSONA = (
    "You are Gina, an environmental systems thinker focused on climate justice."
)

CHARLIE_PERSONA = (
    "You are Charlie, an eccentric digital artist."
)

async def run_chat_integration():
    print("--- 1. Initializing Environment & ChatSystem ---")
    env = Environment(
        objective="Discuss the intersection of AI and Climate tech.",
        active_tools=["execute_python"] 
    )
    chat_system = ChatSystem()

    print(f"Environment ID: {env.id}")

    # Create Synth configs
    alex_config = SynthConfig(
        synth_id="Alex-01",
        persona_prompt=ALEX_PERSONA,
        allowed_tools=["execute_python"],
        allowed_connections=["Gina-02", "Charlie-03"] # Knows Gina and Charlie
    )
    
    gina_config = SynthConfig(
        synth_id="Gina-02",
        persona_prompt=GINA_PERSONA,
        allowed_tools=["execute_python"],
        allowed_connections=["Alex-01"] # Knows only Alex
    )

    charlie_config = SynthConfig(
        synth_id="Charlie-03",
        persona_prompt=CHARLIE_PERSONA,
        allowed_tools=[],
        allowed_connections=["Gina-02"] # Thinks he knows Gina, but Gina doesn't know him
    )

    # Instantiate Synths (This avoids OpenAI bootstrap by using Mock if you want, or actual if you have keys)
    # We will use the actual Synths but bypass step() to simulate messaging
    alex = Synth(alex_config, bootstrap=False)
    gina = Synth(gina_config, bootstrap=False)
    charlie = Synth(charlie_config, bootstrap=False)

    print("\n--- 2. Registering Synths to Environment and ChatSystem ---")
    
    # 2a. Add to environment (validates tools)
    env.add_synth(alex)
    env.add_synth(gina)
    env.add_synth(charlie)

    # 2b. Wrap them in ChatRoom Agents
    alex_agent = Agent(synth=alex)
    gina_agent = Agent(synth=gina)
    charlie_agent = Agent(synth=charlie)

    chat_system.register_agent(alex_agent)
    chat_system.register_agent(gina_agent)
    chat_system.register_agent(charlie_agent)

    print("Synths registered. Launching async listeners...")
    
    # Start listeners
    tasks = [
        asyncio.create_task(alex_agent.listen()), 
        asyncio.create_task(gina_agent.listen()),
        asyncio.create_task(charlie_agent.listen())
    ]

    print("\n--- 3. Simulating Concurrent Interactions ---", flush=True)

    # Alex autos joins / creates a room
    room_alex = await chat_system.auto_join_room(alex_agent)
    print(f"[Main thread] Alex joined {room_alex.name}")

    # Gina autos joins (Should find Alex -> Joins Room_Alex)
    room_gina = await chat_system.auto_join_room(gina_agent)
    print(f"[Main thread] Gina joined {room_gina.name}")

    # Charlie autos joins (His connections: Gina. Is Gina in a room? Yes! Charlie joins)
    room_charlie = await chat_system.auto_join_room(charlie_agent)
    print(f"[Main thread] Charlie joined {room_charlie.name}")

    # Allow system messages to flush
    await asyncio.sleep(0.1)

    print("\n--- 4. Broadcasting Messages ---", flush=True)
    # Maintain a conversation history shared in the "room"
    conversation_history = []

    # Alex initiates the conversation
    alex_msg = alex.initiate()
    conversation_history.append(alex_msg)
    await alex_agent.send_message(room_alex, alex_msg.content)

    # Gina responds
    gina_msg = gina.step(conversation_history)
    conversation_history.append(gina_msg)
    await gina_agent.send_message(room_gina, gina_msg.content)

    # Charlie chimes in
    charlie_msg = charlie.step(conversation_history)
    conversation_history.append(charlie_msg)
    await charlie_agent.send_message(room_charlie, charlie_msg.content)

    await asyncio.sleep(0.1)

    # Let's verify environmental logging from the chat. 
    # Usually this hook goes inside the Agent.send_message or ChatRoom.broadcast directly.
    # We'll simulate the Environment hook intercepting the chat text payload:
    env.broadcast_message("Alex-01", "Gina, what do you think about using AI to optimize grids?", ["Gina-02"])

    print("\n--- 5. Verifying Environment State Logs ---")
    print(f"Total environment events: {len(env.event_logs)}")
    for log in env.event_logs[-1:]: # Just checking the last message hook
        print(f" - Logged event: {log['event_type']} from {log['actor_id']} -> {log['payload']['text']} to {log['payload']['recipients']}")

    # Clean up
    for t in tasks:
        t.cancel()

if __name__ == "__main__":
    asyncio.run(run_chat_integration())
