import re
from typing import Any, Dict, List, Optional, Tuple

import yaml

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_agent.output_handler import OutputHandler
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_utils.input import get_multiline_input
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import ct, ot, init_env


class MultiAgent(OutputHandler):
    def __init__(self, agents_config: List[Dict], main_agent_name: str):
        self.agents_config = agents_config
        self.agents = {}
        self.init_agents()
        self.main_agent_name = main_agent_name

    def prompt(self) -> str:
        return f"""
# 多智能体消息发送

## 交互原则与策略
### 消息处理规范
- **单一操作原则**：每轮只执行一个操作（工具调用或消息发送）
- **完整性原则**：确保消息包含所有必要信息，避免歧义
- **明确性原则**：清晰表达意图、需求和期望结果
- **上下文保留**：在消息中包含足够的背景信息

### 消息格式标准
```
{ot("SEND_MESSAGE")}
to: 智能体名称    # 目标智能体名称
content: |
    # 消息主题

    ## 背景信息
    [提供必要的上下文和背景]

    ## 具体需求
    [明确表达期望完成的任务]

    ## 相关资源
    [列出相关文档、数据或工具]

    ## 期望结果
    [描述期望的输出格式和内容]

    ## 下一步计划
    [描述下一步的计划和行动]
{ct("SEND_MESSAGE")}
```

或者：

```
{ot("SEND_MESSAGE")}
to: 智能体名称    # 目标智能体名称
content: |
    # 消息主题

    ## 任务结果
    [任务完成结果，用于反馈]
{ct("SEND_MESSAGE")}
```

## 可用智能体资源
{chr(10).join([f"- **{c['name']}**: {c.get('description', '')}" for c in self.agents_config])}
"""

    def can_handle(self, response: str) -> bool:
        return len(self._extract_send_msg(response)) > 0


    def handle(self, response: str, agent: Any) -> Tuple[bool, Any]:
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
        data = re.findall(ot("SEND_MESSAGE")+r'\n(.*?)\n'+ct("SEND_MESSAGE"), content, re.DOTALL)
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
        for config in self.agents_config:
            output_handler = config.get('output_handler', [])
            if len(output_handler) == 0:
                output_handler = [
                    ToolRegistry(),
                    self,
                ]
            else:
                output_handler.append(self)
            config['output_handler'] = output_handler
            agent = Agent(**config)
            self.agents[config['name']] = agent

    def run(self, user_input: str) -> str:
        last_agent = self.main_agent_name
        msg = self.agents[self.main_agent_name].run(user_input)
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
                    PrettyOutput.print(f"未找到智能体 {msg['to']}，正在重试...", OutputType.WARNING)
                    msg = self.agents[last_agent].run(f"未找到智能体 {msg['to']}，可用智能体列表: {self.agents.keys()}")
                    continue
                PrettyOutput.print(f"{last_agent} 正在向 {msg['to']} 发送消息...", OutputType.INFO)
                last_agent = self.agents[msg['to']].name
                msg = self.agents[msg['to']].run(prompt)
        return ""

