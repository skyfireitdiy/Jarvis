import re
from typing import Any, Dict, List, Optional, Tuple

import yaml

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_agent.output_handler import OutputHandler
from jarvis.jarvis_utils.output import OutputType, PrettyOutput


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
        return f"""
# 🤖 多智能体消息处理系统
您是多智能体系统的一部分，通过结构化消息进行通信。

# 🎯 核心规则
## 关键操作规则
- 每轮只能执行一个操作：
  - 要么使用一个工具（文件操作、询问用户等）
  - 要么发送一条消息给其他智能体
  - 切勿在同一轮中同时进行这两种操作

## 消息流控制
- 发送消息后等待响应
- 处理响应后再进行下一步操作
- 切勿同时发送多条消息
- 切勿将消息与工具调用混合使用

# 📝 消息格式
```
<SEND_MESSAGE>
to: 智能体名称    # 目标智能体名称
content: |
    消息内容    # 消息内容
    可使用多行    # 如果需要
    保持正确的缩进
</SEND_MESSAGE>
```

# 🔄 操作顺序
1. 选择最重要的操作
   - 评估优先级
   - 选择一个操作
   - 执行该操作

2. 等待响应
   - 处理结果/响应
   - 计划下一步操作
   - 等待下一轮

3. 处理响应
   - 处理收到的消息
   - 需要时回复发送者
   - 根据响应继续任务

# 👥 可用智能体
{chr(10).join([f"- {c.name}: {c.description}" for c in self.agents_config])}

# ❗ 重要规则
1. 每轮只能执行一个操作
2. 等待响应
3. 处理后再进行下一步
4. 回复消息
5. 需要时转发任务

# 💡 提示
- 第一个操作将被执行
- 额外的操作将被忽略
- 总是先处理响应
- 需要时发送消息以继续任务
- 处理并回复收到的消息
"""

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
                          output_handler=[*agent_config.output_handler, self],
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
                    PrettyOutput.print(f"未找到智能体 {msg['to']}，正在重试...", OutputType.WARNING)
                    msg = self.agents[last_agent].run(f"未找到智能体 {msg['to']}，可用智能体列表: {self.agents.keys()}")
                    continue
                PrettyOutput.print(f"{last_agent} 正在向 {msg['to']} 发送消息...", OutputType.INFO)
                last_agent = self.agents[msg['to']].name
                msg = self.agents[msg['to']].run(prompt)
        return ""