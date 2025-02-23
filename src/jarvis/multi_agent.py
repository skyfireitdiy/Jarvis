

from typing import Dict, List, Optional

from jarvis.agent import Agent


class MultiAgent:
    def __init__(self, agents_config: Dict, main_agent_name: str):
        self.agents_config = agents_config
        self.agents = {}
        self.init_agents()
        self.main_agent_name = main_agent_name

    def init_agents(self):
        for agent_config in self.agents_config:
            agent = Agent(**agent_config)
            self.agents[agent_config['name']] = agent

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
                last_agent = self.agents[msg['to']]
                msg = self.agents[msg['to']].run(prompt)
        return ""
