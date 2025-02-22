from abc import ABC
from typing import Dict, Any, List, Optional, Callable, Union
from jarvis.agent import Agent
from jarvis.jarvis_dev.message import Message, MessageType
from jarvis.jarvis_tools.registry import ToolRegistry

class TeamRole(ABC):
    """Base class for team roles"""
    
    def __init__(self, name: str, system_prompt: str, message_handler: Callable[[Message], Dict[str, Any]]):
        self.name = name
        self.message_handler = message_handler
        
        # Add message format to system prompt
        message_info = """
You can send messages to other roles using this format:
<SEND_MESSAGE>
to: role_name  # ProductManager/BusinessAnalyst/TechLead/SystemAnalyst/Developer/QualityAssurance
type: message_type  # question/feedback/update/confirm/reject
content: message content
context:  # optional
  key1: value1
  key2: value2
</SEND_MESSAGE>
"""
        system_prompt += message_info

        # Initialize agent
        self.agent = Agent(
            system_prompt=system_prompt,
            name=name,
            platform=self._get_platform(),
            tool_registry=self._get_tools(),
            auto_complete=False,
            is_sub_agent=True,
            output_handler_after_tool=[self._handle_output],
            use_methodology=False,
            record_methodology=False,
            need_summary=False,
            execute_tool_confirm=False,
        )

    def send_message(self, to_role: str, msg_type: MessageType, 
                    content: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        message = Message(
            from_role=self.name,
            to_role=to_role,
            msg_type=msg_type,
            content=content,
            context=context
        )
        result = self.message_handler(message)
        return result if result is not None else {
            "success": False,
            "error": "Message handler returned None"
        }
    
    def _get_platform(self):
        """Get agent platform"""
        raise NotImplementedError()
        
    def _get_tools(self):
        """Get base tools for all roles"""
        return ToolRegistry()

    def handle_message(self, message: Message) -> Dict[str, Any]:
        """Handle incoming message from other roles"""
        try:
            # Create message handling prompt
            prompt = f"""Please handle this message from {message.from_role}:

Message Type: {message.msg_type.value}
Content: {message.content}

Context:
{message.context}

Please provide:
1. Your understanding of the message
2. Your response or action
3. Any questions or concerns
4. Next steps if any"""

            # Get response
            result = self.agent.run(prompt)
            
            return {
                "success": True,
                "response": result
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to handle message: {str(e)}"
            } 

    def _handle_output(self, output: str) -> str:
        """Handle agent output and extract messages"""
        import re
        import yaml
        
        # Extract messages
        msg_matches = re.finditer(r'<SEND_MESSAGE>\s*(.*?)\s*</SEND_MESSAGE>', output, re.DOTALL)
        for match in msg_matches:
            try:
                msg_yaml = yaml.safe_load(match.group(1))
                message = Message(
                    from_role=self.name,
                    to_role=msg_yaml["to"],
                    msg_type=MessageType(msg_yaml["type"]),
                    content=msg_yaml["content"],
                    context=msg_yaml.get("context")
                )
                self.message_handler(message)
            except:
                pass
            
        return output 