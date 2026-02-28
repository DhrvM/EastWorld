import os
import uuid
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_KEY")

if url and key:
    client: Client = create_client(url, key)
else:
    client = None
    print("Warning: Supabase credentials not found.")
    exit(1)

class Environment:
    def __init__(self, id: str = None):
        """
        Initialize an Environment for multi-agent interaction.
        If an id is provided, it loads the environment from the database,
        otherwise it creates a new one.
        """
        self.id = id or str(uuid.uuid4())
        self.status = "INITIALIZING"
        self.max_turns = 100
        self.current_turn = 0
        self.created_at = datetime.utcnow().isoformat()
        
        self.synths = {}          # synth_id -> synth db record
        self.tools = {}           # tool_name -> tool function/schema
        
        if id and client:
            self._load_state()
        elif client:
            self._save_state()

    def _load_state(self):
        """Load environment state and synths from Supabase."""
        response = client.table("environments").select("*").eq("id", self.id).execute()
        if response.data:
            data = response.data[0]
            self.status = data.get("status")
            self.max_turns = data.get("max_turns")
            self.current_turn = data.get("current_turn")
            
        synths_response = client.table("synths").select("*").eq("env_id", self.id).execute()
        for synth in synths_response.data:
            self.synths[synth["id"]] = synth

    def _save_state(self):
        """Save or update environment state in Supabase."""
        if not client: return
        data = {
            "id": self.id,
            "status": self.status,
            "max_turns": self.max_turns,
            "current_turn": self.current_turn,
            "created_at": self.created_at
        }
        client.table("environments").upsert(data).execute()

    def add_synth(self, synth_data: Dict[str, Any]):
        """
        Add a Synth agent to the environment.
        synth_data should contain 'synth_name', 'supermemory_user_id', 
        'persona_prompt', 'allowed_tools', and 'allowed_connections'.
        """
        synth_id = synth_data.get("id", str(uuid.uuid4()))
        synth_data["id"] = synth_id
        synth_data["env_id"] = self.id
        self.synths[synth_id] = synth_data
        
        if client:
            client.table("synths").upsert(synth_data).execute()
            self.log_event(
                actor_id="system", 
                event_type="SYSTEM_ALERT", 
                payload={"message": f"Synth {synth_data.get('synth_name')} joined the environment."}
            )
        return synth_id

    def register_tool(self, tool_name: str, schema: dict, function: callable):
        """
        Register a tool that agents in the environment can access if permitted.
        """
        self.tools[tool_name] = {
            "schema": schema,
            "function": function
        }

    def log_event(self, actor_id: str, event_type: str, payload: Dict[str, Any]):
        """
        Log an event (message or tool use) to the transcript.
        event_types: MESSAGE, TOOL_CALL, TOOL_RESULT, SYSTEM_ALERT
        """
        event = {
            "id": str(uuid.uuid4()),
            "env_id": self.id,
            "actor_id": actor_id,
            "event_type": event_type,
            "payload": payload
        }
        if client:
            client.table("event_logs").insert(event).execute()
        return event

    def broadcast_message(self, sender_id: str, message: str, recipient_ids: Optional[List[str]] = None):
        """
        A medium for agents to communicate. 
        If recipient_ids is provided, it acts as a direct message (if permitted).
        Otherwise it's a broadcast to allowed_connections.
        """
        sender = self.synths.get(sender_id)
        if not sender:
            raise ValueError(f"Sender {sender_id} not found in this environment.")
            
        allowed_connections = sender.get("allowed_connections") or []
        
        # Determine actual recipients
        if recipient_ids:
            actual_recipients = [r for r in recipient_ids if r in allowed_connections]
        else:
            actual_recipients = allowed_connections
            
        payload = {
            "text": message,
            "recipients": actual_recipients
        }
        
        # Log the message event
        self.log_event(actor_id=sender_id, event_type="MESSAGE", payload=payload)
        self.current_turn += 1
        self._save_state()
        
        return payload

    def execute_tool(self, synth_id: str, tool_name: str, arguments: dict):
        """
        Execute a registered tool on behalf of a Synth.
        Ensures the synth has permission to use the tool.
        """
        synth = self.synths.get(synth_id)
        if not synth:
            return {"error": "Synth not found"}
            
        allowed_tools = synth.get("allowed_tools") or []
        if tool_name not in allowed_tools:
            return {"error": f"Tool '{tool_name}' not permitted for synth '{synth.get('synth_name')}'"}
            
        tool = self.tools.get(tool_name)
        if not tool:
            return {"error": f"Tool '{tool_name}' not registered in the environment"}
            
        # Log the tool call
        self.log_event(actor_id=synth_id, event_type="TOOL_CALL", payload={"tool_name": tool_name, "arguments": arguments})
        
        try:
            # Execute the tool
            result = tool["function"](**arguments)
            # Log the result
            self.log_event(actor_id=synth_id, event_type="TOOL_RESULT", payload={"tool_name": tool_name, "result": result})
            return result
        except Exception as e:
            error_payload = {"tool_name": tool_name, "error": str(e)}
            self.log_event(actor_id=synth_id, event_type="TOOL_RESULT", payload=error_payload)
            return error_payload

    def run_step(self):
        """
        Advance the environment by one active turn/step.
        This would trigger the Next Synth to act (the Cognitive Loop).
        """
        if self.status != "RUNNING":
            self.status = "RUNNING"
            self._save_state()
            
        if self.current_turn >= self.max_turns:
            self.status = "TERMINATED"
            self._save_state()
            print(f"Environment {self.id} reached max turns.")
            return False

        # Placeholder: This is where iterating over synths or external event queues happens
        # For each active synth, we would assemble context and prompt their LLM
        
        self.current_turn += 1
        self._save_state()
        return True