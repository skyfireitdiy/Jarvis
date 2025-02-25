


import re
from typing import Any, Dict, List, Optional, Tuple

import yaml

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_agent.output_handler import OutputHandler
from jarvis.jarvis_utils import OutputType, PrettyOutput


class AgentConfig:
    def __init__(self, **config):
        self.system_prompt = config.get('system_prompt', '')
        self.name = config.get('name', 'Jarvis')
        self.description = config.get('description', '')
        self.is_sub_agent = config.get('is_sub_agent', False)
        self.output_handler = config.get('output_handler', [])
        self.platform = config.get('platform')
        self.model_name = config.get('model_name')
        self.summary_prompt = config.get('summary_prompt')
        self.auto_complete = config.get('auto_complete', False)
        self.input_handler = config.get('input_handler')
        self.max_context_length = config.get('max_context_length')
        self.execute_tool_confirm = config.get('execute_tool_confirm')

class MultiAgent(OutputHandler):
    def __init__(self, configs: List[AgentConfig], main_agent_name: str):
        self.agents_config = configs
        self.agents = {}
        self.init_agents()
        self.main_agent_name = main_agent_name

    def prompt(self) -> str:
        return """
        - Send Message Rules
            !!! CRITICAL ACTION RULES !!!
            You can ONLY perform ONE action per turn:
            - ENSURE USE ONLY ONE TOOL EVERY TURN (file_operation, ask_user, etc.)
            - OR SEND ONE MESSAGE TO ANOTHER AGENT
            - NEVER DO BOTH IN THE SAME TURN
            
            2. Message Format:
            <SEND_MESSAGE>
            to: agent_name  # Target agent name
            content: |
                message_content  # Message content, multi-line must be separated by newlines
            </SEND_MESSAGE>
            
            3. Message Handling:
                - After sending a message, WAIT for response
                - Process response before next action
                - Never send multiple messages at once
                - Never combine message with tool calls
            
            4. If Multiple Actions Needed:
                a. Choose most important action first
                b. Wait for response/result
                c. Plan next action based on response
                d. Execute next action in new turn
            
        - Remember:
            - First action will be executed
            - Additional actions will be IGNORED
            - Always process responses before new actions
            - You should send message to other to continue the task if you are nothing to do
            - If you receive a message from other agent, you should handle it and reply to sender

        You can send message to following agents: """ + "\n".join([f"{c.name}: {c.description}" for c in self.agents_config])

    def can_handle(self, response: str) -> bool:
        return len(self._extract_send_msg(response)) > 0


    def handle(self, response: str) -> Tuple[bool, Any]:
        send_messages = self._extract_send_msg(response)
        if len(send_messages) > 1:
            return False, f"Send multiple messages, please only send one message at a time."
        if len(send_messages) == 0:
            return False, ""
        return True, send_messages[0]
        
    def name(self) -> str:
        return "SEND_MESSAGE"
        
    
    @staticmethod
    def _extract_send_msg(content: str) -> List[Dict]:
        """Extract send message from content.
        
        Args:
            content: The content containing send message
        """
        data = re.findall(r'<SEND_MESSAGE>(.*?)</SEND_MESSAGE>', content, re.DOTALL)
        ret = []
        for item in data:
            try:
                msg = yaml.safe_load(item)
                if 'to' in msg and 'content' in msg:
                    ret.append(msg)
            except Exception as e:
                continue
        return ret

    def init_agents(self):
        for agent_config in self.agents_config:
            agent = Agent(system_prompt=agent_config.system_prompt,
                          name=agent_config.name,
                          description=agent_config.description,
                          model_name=agent_config.model_name,
                          platform=agent_config.platform,
                          max_context_length=agent_config.max_context_length,
                          execute_tool_confirm=agent_config.execute_tool_confirm,
                          input_handler=agent_config.input_handler,
                          use_methodology=False,
                          record_methodology=False,
                          need_summary=False,
                          auto_complete=agent_config.auto_complete,
                          summary_prompt=agent_config.summary_prompt,
                          is_sub_agent=agent_config.is_sub_agent,
                          output_handler=[agent_config.output_handler, self],
                          )
            
            self.agents[agent_config.name] = agent

    def run(self, user_input: str, file_list: Optional[List[str]] = None) -> str:
        last_agent = self.main_agent_name
        msg = self.agents[self.main_agent_name].run(user_input, file_list)
        while msg:
            if isinstance(msg, str):
                return msg
            elif isinstance(msg, Dict):
                prompt  = f"""
Please handle this message:
from: {last_agent}
content: {msg['content']}
"""
                if msg['to'] not in self.agents:
                    PrettyOutput.print(f"没有找到{msg['to']}，重试...", OutputType.WARNING)
                    msg = self.agents[last_agent].run(f"The agent {msg['to']} is not found, agent list: {self.agents.keys()}")
                    continue
                PrettyOutput.print(f"{last_agent} 发送消息给 {msg['to']}...", OutputType.INFO)
                last_agent = self.agents[msg['to']].name
                msg = self.agents[msg['to']].run(prompt)
        return ""
