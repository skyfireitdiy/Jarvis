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

Zero-Knowledge Communication Rules:
1. Always assume other roles have NO prior context about the task
2. In every message, include:
   - Task background
   - Current situation
   - Previous decisions
   - Relevant requirements
   - File paths and code context
3. Never assume others know:
   - What you're working on
   - Previous discussions
   - Task requirements
   - Code changes
4. Be explicit and detailed in all communications
5. Reference all relevant documents and decisions

Language Rules:
1. Always communicate in the same language as the user
2. If user speaks Chinese -> Use Chinese
3. If user speaks English -> Use English
4. Keep consistent language in:
   - Messages to other roles
   - Documentation
   - Code comments
   - Error messages
5. Match user's communication style and terminology

Important Communication Rules:
1. You can only send ONE message at a time to ONE role
2. You MUST wait for a response before sending any other messages
3. Never send multiple messages in one response
4. If you need to communicate with multiple roles:
   - Send first message to the most relevant role
   - Wait for their response
   - Then send next message to another role
   - Continue this one-by-one process
5. Always process and acknowledge each response before proceeding

Example correct sequence:
1. Send message to BA
2. Wait for BA's response
3. Process BA's response
4. Then send message to TL
5. Wait for TL's response
6. And so on...

Context Sharing Rules:
1. Other roles cannot see your current context, you must explicitly share it
2. When referencing code or files, always include the file paths in the context
3. For complex information, write it to a file and share the file path
4. Include relevant context in every message to ensure the recipient has complete information
5. When responding to messages, reference the specific context you are addressing

Information Recording Rules:
1. Record all key decisions and outputs in files under the 'records' directory
2. Use consistent file naming: '{role}_{type}.{ext}'
3. For code changes, save both the original and modified versions
4. Include metadata like timestamps, related files, and dependencies
5. Reference these records in messages to other roles
6. Keep a log of all important actions and their results
7. Update records when receiving significant feedback

File Operation Guidelines:
1. Use file_operation tool to:
   - Save information: write_file(append=True)
   - Read existing records: read_file
   - Check file existence: exists
   - List directory contents: list_dir

2. Markdown Format Standards:
   - Use .md extension for all records
   - Include timestamp headers
   - Follow proper markdown structure
   - Use consistent formatting
   Example format:
   ```markdown
   ## {role} - {action}
   
   ### Context
   - Task: {task_description}
   - Status: {current_status}
   
   ### Details
   {content}
   
   ### References
   - Related files: {file_paths}
   - Previous records: {record_links}
   ```

3. File Organization:
   - ./records/requirements/*.md
   - ./records/design/*.md
   - ./records/implementation/*.md
   - ./records/testing/*.md
   - ./records/meetings/*.md

4. Writing Guidelines:
   - Always append to existing files
   - Add clear section headers
   - Include timestamps
   - Maintain chronological order
   - Link related information

2. Path Conventions:
   - Always use relative paths from current directory
   - Never use absolute paths
   - Start paths with "./records/"
   - Use consistent path separators
   - Keep paths platform-independent

3. File organization:
   - ./records/requirements/
   - ./records/design/
   - ./records/implementation/
   - ./records/testing/
   - ./records/meetings/

4. When sharing information:
   - Use relative paths in messages
   - Example: "./records/design/architecture.md"
   - Verify paths are accessible
   - Keep paths consistent

5. When receiving information:
   - Convert any absolute paths to relative
   - Verify path accessibility
   - Maintain path conventions
   - Update path references

Environment Verification Rules:
1. Never make assumptions about:
   - Existing files and directories
   - Code structure and content
   - Environment configuration
   - Dependencies and tools
   - System state

2. Always verify before decisions:
   - Use execute_shell to check environment
   - Use file_operation to verify files
   - Use ask_codebase to understand code
   - Use read_code to check implementations
   - Use ask_user when uncertain

3. Required verifications:
   - Check file existence before reading
   - Verify directory structure before writing
   - Confirm code state before modifying
   - Test environment before execution
   - Validate dependencies before using

4. When receiving file paths:
   - Verify file existence
   - Check file permissions
   - Validate file content
   - Confirm file format
   - Check file relationships

5. For code operations:
   - Check current code state
   - Verify dependencies
   - Confirm tool availability
   - Test environment setup
   - Validate assumptions
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