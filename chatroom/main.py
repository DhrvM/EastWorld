import asyncio
import uuid
from typing import List, Dict, Set, Optional

class Agent:
    def __init__(self, id: str, name: str, connections: List[str]):
        """
        id: Unique identifier
        name: Human-readable name
        connections: List of agent IDs this agent is allowed to communicate with
        """
        self.id = id
        self.name = name
        self.connections = set(connections)
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.current_room: Optional[str] = None

    async def send_message(self, room: ChatRoom, content: str):
        """Send a message to a room concurrently."""
        await room.broadcast(self, content)

    async def listen(self):
        """Continuously listen for messages in the inbox."""
        try:
            while True:
                message = await self.inbox.get()
                print(f"[{self.name} receives] {message}", flush=True)
                self.inbox.task_done()
        except asyncio.CancelledError:
            pass

class ChatRoom:
    def __init__(self, name: str):
        self.id = str(uuid.uuid4())
        self.name = name
        self.participants: Dict[str, Agent] = {}
        # Avoid race conditions on participant mutations
        self._lock = asyncio.Lock()

    async def add_participant(self, agent: Agent):
        async with self._lock:
            if agent.id not in self.participants:
                self.participants[agent.id] = agent
                agent.current_room = self.id
                await self._broadcast_system_message(f"*** {agent.name} joined the room ***")

    async def remove_participant(self, agent: Agent):
        async with self._lock:
            if agent.id in self.participants:
                del self.participants[agent.id]
                agent.current_room = None
                await self._broadcast_system_message(f"*** {agent.name} left the room ***")

    async def _broadcast_system_message(self, content: str):
        """Internal helper to broadcast system alerts without locking again."""
        for participant in self.participants.values():
            await participant.inbox.put(f"[System - {self.name}]: {content}")

    async def broadcast(self, sender: Agent, content: str):
        async with self._lock:
            if sender.id not in self.participants:
                return # Can't send to a room you aren't in
            
            message = f"[{self.name}] {sender.name}: {content}"
            # Send message to everyone concurrently
            for participant in self.participants.values():
                if participant.id != sender.id:
                    await participant.inbox.put(message)

class ChatSystem:
    def __init__(self):
        self.rooms: Dict[str, ChatRoom] = {}
        self.agents: Dict[str, Agent] = {}
        self._lock = asyncio.Lock()

    def register_agent(self, agent: Agent):
        self.agents[agent.id] = agent

    async def create_room(self, name: str) -> ChatRoom:
        async with self._lock:
            room = ChatRoom(name)
            self.rooms[room.id] = room
            return room

    async def auto_join_room(self, agent: Agent) -> ChatRoom:
        """
        Attempts to join a room where a connection is already present.
        Creates a new room if none exists.
        """
        async with self._lock:
            # 1. Search existing rooms for connections
            for room in self.rooms.values():
                for participant_id in room.participants:
                    if participant_id in agent.connections:
                        await room.add_participant(agent)
                        return room
            
            # 2. No connection found in any room, create a new one
            new_room = ChatRoom(f"Room_{agent.name}")
            self.rooms[new_room.id] = new_room
            await new_room.add_participant(agent)
            return new_room

    async def invite_agent(self, inviter: Agent, invitee_id: str, room: ChatRoom):
        """
        Invite another agent to a room. Validates connections.
        """
        if invitee_id not in inviter.connections:
            await inviter.inbox.put(f"[System]: You are not permitted to invite {invitee_id}.")
            return
            
        invitee = self.agents.get(invitee_id)
        if not invitee:
            await inviter.inbox.put(f"[System]: Invitee {invitee_id} not found.")
            return

        # Auto-join the invitee to the room
        await room.add_participant(invitee)
        await inviter.inbox.put(f"[System]: Successfully invited {invitee.name} to {room.name}.")

async def test_scenario():
    system = ChatSystem()
    
    # Create agents with connections mapping IDs
    alice = Agent(id="a1", name="Alice", connections=["b1", "c1"])
    bob = Agent(id="b1", name="Bob", connections=["a1"])
    charlie = Agent(id="c1", name="Charlie", connections=["a1"])
    dave = Agent(id="d1", name="Dave", connections=[]) # Nobody allowed

    for a in [alice, bob, charlie, dave]:
        system.register_agent(a)

    # Start listening tasks
    tasks = [asyncio.create_task(a.listen()) for a in [alice, bob, charlie, dave]]

    print("--- Scenario Starts ---", flush=True)

    # Bob starts/creates a room (since no connection is anywhere)
    room_bob = await system.auto_join_room(bob)

    # Alice looks for a room. Since Bob (a connection) is in Room_Bob, she joins it automatically
    room_alice = await system.auto_join_room(alice)

    # Alice invites Charlie
    await system.invite_agent(alice, "c1", room_alice)

    # Communications
    await alice.send_message(room_alice, "Hello everyone!")
    await charlie.send_message(room_alice, "Hi Alice, Hi Bob!")
    await bob.send_message(room_alice, "Hey Alice, this is Bob.")

    # Dave tries to join (nobody knows him) -> creates his own room
    room_dave = await system.auto_join_room(dave)

    # Alice tries to invite Dave (not in her connections) -> fails
    await system.invite_agent(alice, "d1", room_alice)

    # Wait for all inboxes to be fully processed
    await asyncio.sleep(0.5)
    
    # Cancel listeners
    for t in tasks:
        t.cancel()

if __name__ == "__main__":
    asyncio.run(test_scenario())
