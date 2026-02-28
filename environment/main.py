import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

# Global Registry of all available tools in SynthSpace
GLOBAL_TOOLS = {
    "execute_python": {
        "schema": {
            "type": "function",
            "function": {
                "name": "execute_python",
                "description": "Execute python code.",
                "parameters": {"type": "object", "properties": {"code": {"type": "string"}}}
            }
        },
        "function": lambda code: f"Executed: {code}"  # Placeholder for actual E2B execution
    },
    "read_file": {
        "schema": {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read file from paths.",
                "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}
            }
        },
        "function": lambda path: f"Content of {path}"
    },
    "web_search": {
        "schema": {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web.",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}}
            }
        },
        "function": lambda query: f"Search results for {query}"
    }
}

class Environment:
    def __init__(self, id: str = None, objective: str = "Survive and interact.", active_tools: List[str] = None):
        """
        Initialize an in-memory Environment for multi-agent interaction.
        
        Args:
            id: Optional ID for the environment.
            objective: The main goal or task of this specific environment.
            active_tools: List of tool names from GLOBAL_TOOLS to enable for this environment.
        """
        self.id = id or str(uuid.uuid4())
        self.status = "INITIALIZING"
        self.max_turns = 100
        self.current_turn = 0
        self.created_at = datetime.utcnow().isoformat()
        self.objective = objective
        
        self.synths = {}          # synth_id -> synth object/dict
        self.tools = {}           # active tools for this environment
        self.event_logs = []      # in-memory transcript of events
        
        # Load requested active tools from the global registry
        if active_tools:
            for t in active_tools:
                if t in GLOBAL_TOOLS:
                    self.tools[t] = GLOBAL_TOOLS[t]
                else:
                    print(f"Warning: Tool '{t}' not found in global registry.")
        else:
            # Default to all tools if none specified
            self.tools = GLOBAL_TOOLS.copy()

    def add_synth(self, synth: Any):
        """
        Add a Synth agent to the environment.
        `synth` can be a Synth class instance or a dictionary.
        It must expose an `id` and optionally `allowed_tools` and `allowed_connections`.
        """
        # Handle dicts or object instances
        is_dict = isinstance(synth, dict)
        synth_id = synth.get("id", str(uuid.uuid4())) if is_dict else getattr(synth, "id", str(uuid.uuid4()))
        synth_name = synth.get("synth_name", "Unknown Synth") if is_dict else getattr(synth, "synth_name", "Unknown Synth")
        allowed_tools = synth.get("allowed_tools", []) if is_dict else getattr(synth, "allowed_tools", [])
        
        # Validate that the synth's allowed tools are within the environment's active tools
        valid_tools = [t for t in allowed_tools if t in self.tools]
        if valid_tools != allowed_tools:
            print(f"Warning: Some tools for synth {synth_name} are not permitted in this environment's active toolset.")
            if is_dict:
                synth["allowed_tools"] = valid_tools
            else:
                setattr(synth, "allowed_tools", valid_tools)
        
        # Assign ID if missing initially and link to environment
        if is_dict:
            synth["id"] = synth_id
            synth["env_id"] = self.id
        else:
            setattr(synth, "id", synth_id)
            setattr(synth, "env_id", self.id)
            
        self.synths[synth_id] = synth
        
        self.log_event(
            actor_id="system", 
            event_type="SYSTEM_ALERT", 
            payload={"message": f"Synth {synth_name} joined the environment."}
        )
        return synth_id

    def register_tool(self, tool_name: str, schema: dict, function: callable):
        """
        Dynamically register a tool to this specific environment at runtime.
        """
        self.tools[tool_name] = {
            "schema": schema,
            "function": function
        }

    def log_event(self, actor_id: str, event_type: str, payload: Dict[str, Any]):
        """
        Log an event (message or tool use) to the in-memory transcript.
        event_types: MESSAGE, TOOL_CALL, TOOL_RESULT, SYSTEM_ALERT
        """
        event = {
            "id": str(uuid.uuid4()),
            "actor_id": actor_id,
            "event_type": event_type,
            "payload": payload,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.event_logs.append(event)
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
            
        is_dict = isinstance(sender, dict)
        allowed_connections = sender.get("allowed_connections", []) if is_dict else getattr(sender, "allowed_connections", [])
        
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
        
        return payload

    def execute_tool(self, synth_id: str, tool_name: str, arguments: dict):
        """
        Execute a registered tool on behalf of a Synth.
        Ensures the synth has permission to use the tool.
        """
        synth = self.synths.get(synth_id)
        if not synth:
            return {"error": "Synth not found"}
            
        is_dict = isinstance(synth, dict)
        synth_name = synth.get("synth_name", "Unknown Synth") if is_dict else getattr(synth, "synth_name", "Unknown Synth")
        allowed_tools = synth.get("allowed_tools", []) if is_dict else getattr(synth, "allowed_tools", [])
        
        if tool_name not in allowed_tools:
            return {"error": f"Tool '{tool_name}' not permitted for synth '{synth_name}'"}
            
        tool = self.tools.get(tool_name)
        if not tool:
            return {"error": f"Tool '{tool_name}' not active in the environment"}
            
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
            
        if self.current_turn >= self.max_turns:
            self.status = "TERMINATED"
            print(f"Environment {self.id} reached max turns.")
            return False

        # Placeholder: This is where iterating over synths or external event queues happens
        # For each active synth, we would assemble context and prompt their LLM
        
        self.current_turn += 1
        return True