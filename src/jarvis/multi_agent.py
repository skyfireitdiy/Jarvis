

from typing import Dict, List, Optional

from jarvis.agent import Agent


class AgentConfig:
    def __init__(self, **config):
        self.system_prompt = config.get('system_prompt', '')
        self.name = config.get('name', 'Jarvis')
        self.description = config.get('description', '')
        self.is_sub_agent = config.get('is_sub_agent', False)
        self.tool_registry = config.get('tool_registry', [])
        self.platform = config.get('platform')
        self.model_name = config.get('model_name')
        self.summary_prompt = config.get('summary_prompt')
        self.auto_complete = config.get('auto_complete', False)
        self.output_handler_before_tool = config.get('output_handler_before_tool')
        self.output_handler_after_tool = config.get('output_handler_after_tool')
        self.input_handler = config.get('input_handler')
        self.max_context_length = config.get('max_context_length')
        self.execute_tool_confirm = config.get('execute_tool_confirm')

class MultiAgent:
    def __init__(self, configs: List[AgentConfig], main_agent_name: str):
        self.agents_config = configs
        self.agents = {}
        self.init_agents()
        self.main_agent_name = main_agent_name

    def init_agents(self):
        for agent_config in self.agents_config:
            agent = Agent(system_prompt=agent_config.system_prompt,
                          name=agent_config.name,
                          description=agent_config.description,
                          model_name=agent_config.model_name,
                          platform=agent_config.platform,
                          max_context_length=agent_config.max_context_length,
                          support_send_msg=True,
                          execute_tool_confirm=agent_config.execute_tool_confirm,
                          input_handler=agent_config.input_handler,
                          output_handler_before_tool=agent_config.output_handler_before_tool,
                          output_handler_after_tool=agent_config.output_handler_after_tool,
                          use_methodology=False,
                          record_methodology=False,
                          need_summary=False,
                          auto_complete=agent_config.auto_complete,
                          summary_prompt=agent_config.summary_prompt,
                          is_sub_agent=agent_config.is_sub_agent,
                          tool_registry=agent_config.tool_registry,
                          )
            agent.system_prompt += "You can send message to following agents: " + "\n".join([f"{c.name}: {c.description}" for c in self.agents_config])
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
                    msg = self.agents[last_agent].run(f"The agent {msg['to']} is not found, agent list: {self.agents.keys()}")
                    continue
                last_agent = self.agents[msg['to']]
                msg = self.agents[msg['to']].run(prompt)
        return ""
