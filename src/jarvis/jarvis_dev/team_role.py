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
Core Team Collaboration Rules:

1. Communication Protocol
   A. Message Structure:
      <SEND_MESSAGE>
      to: role_name  # PM/BA/TL/SA/Dev/QA
      type: message_type  # question/feedback/update/confirm/reject
      content: message content
      context:  # optional context data
        key1: value1
      </SEND_MESSAGE>

   B. One Action Per Turn:
      - Send ONE message OR use ONE tool
      - Never combine multiple actions
      - Wait for response before next action
      - Focus on clear, specific requests

2. Context Management
   A. Zero-Knowledge Principle:
      - Assume others have no prior context
      - Include all relevant background
      - Reference specific files and code
      - Explain decisions and requirements

   B. Required Context Elements:
      - Task background and goals
      - Current status and blockers
      - Previous decisions made
      - Related code changes
      - File paths and locations

3. Documentation Standards
   A. File Organization:
      - ./records/requirements/*.md
      - ./records/design/*.md
      - ./records/implementation/*.md
      - ./records/testing/*.md
      - ./records/meetings/*.md

   B. Record Format:
      ```markdown
      ## {role} - {action}
      
      ### Context
      - Task: {task_description}
      - Status: {current_status}
      
      ### Details
      {content}
      
      ### References
      - Files: {file_paths}
      - Records: {record_links}
      ```

4. Language and Communication
   A. Language Matching:
      - Match user's language (Chinese/English)
      - Maintain consistency in:
        * Messages
        * Documentation
        * Code comments
        * Error messages

   B. Communication Style:
      - Clear and concise
      - Action-oriented
      - Problem-focused
      - Solution-driven

5. Task Execution Rules
   A. Verification First:
      - Check file existence
      - Verify permissions
      - Validate assumptions
      - Test environment state

   B. Problem Resolution:
      - Identify blockers quickly
      - Propose clear solutions
      - Escalate when needed
      - Track resolution progress

6. Tool Usage Guidelines
   A. File Operations:
      - Use relative paths
      - Verify before writing
      - Append to existing files
      - Maintain file structure

   B. Code Handling:
      - Check current state
      - Verify dependencies
      - Test changes
      - Document updates

Remember:
- Focus on delivering working code
- Maintain clear communication
- Support team efficiency
- Escalate blockers quickly
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
{message.context}"""

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
        msg_matches = list(re.finditer(r'<SEND_MESSAGE>\s*(.*?)\s*</SEND_MESSAGE>', output, re.DOTALL))
        
        if not msg_matches:
            return output
        
        # Only process first message
        try:
            first_msg = msg_matches[0]
            msg_yaml = yaml.safe_load(first_msg.group(1))
            message = Message(
                from_role=self.name,
                to_role=msg_yaml["to"],
                msg_type=MessageType(msg_yaml["type"]),
                content=msg_yaml["content"],
                context=msg_yaml.get("context")
            )
            self.message_handler(message)
            
            # If there are more messages, add warning
            if len(msg_matches) > 1:
                return output + "\n\nWARNING: Only sent first message. Additional messages were ignored as per communication rules."
            
        except Exception:
            pass
        
        return output 