# -*- coding: utf-8 -*-
import re
from typing import Any, Dict, List, Optional, Tuple, Union

import yaml

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_agent.output_handler import OutputHandler
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.tag import ct, ot


class MultiAgent(OutputHandler):
    def __init__(self, agents_config: List[Dict], main_agent_name: str):
        self.agents_config = agents_config
        self.agents_config_map = {c["name"]: c for c in agents_config}
        self.agents: Dict[str, Agent] = {}
        self.main_agent_name = main_agent_name
        self.original_question: Optional[str] = None

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
content: |2
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
content: |2
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
            return (
                False,
                f"Send multiple messages, please only send one message at a time.",
            )
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
        if ot("SEND_MESSAGE") in content and ct("SEND_MESSAGE") not in content:
            content += "\n" + ct("SEND_MESSAGE")
        data = re.findall(
            ot("SEND_MESSAGE") + r"\n(.*?)\n" + ct("SEND_MESSAGE"), content, re.DOTALL
        )
        ret = []
        for item in data:
            try:
                msg = yaml.safe_load(item)
                if "to" in msg and "content" in msg:
                    ret.append(msg)
            except Exception as e:
                continue
        return ret

    def _get_agent(self, name: str) -> Union[Agent, None]:
        if name in self.agents:
            return self.agents[name]

        if name not in self.agents_config_map:
            return None

        config = self.agents_config_map[name].copy()

        if name != self.main_agent_name and self.original_question:
            system_prompt = config.get("system_prompt", "")
            config[
                "system_prompt"
            ] = f"{system_prompt}\n\n# 原始问题\n{self.original_question}"

        output_handler = config.get("output_handler", [])
        if len(output_handler) == 0:
            output_handler = [
                ToolRegistry(),
                self,
            ]
        else:
            if not any(isinstance(h, MultiAgent) for h in output_handler):
                output_handler.append(self)
        config["output_handler"] = output_handler

        agent = Agent(**config)
        self.agents[name] = agent
        return agent

    def run(self, user_input: str) -> str:
        self.original_question = user_input
        last_agent_name = self.main_agent_name

        agent = self._get_agent(self.main_agent_name)
        if not agent:
            # This should not happen if main_agent_name is correctly configured
            return f"主智能体 {self.main_agent_name} 未找到"

        msg: Any = agent.run(user_input)

        while msg:
            if isinstance(msg, str):
                return msg

            if not isinstance(msg, Dict):
                # Should not happen if agent.run() returns str or Dict
                PrettyOutput.print(f"未知消息类型: {type(msg)}", OutputType.WARNING)
                break

            prompt = f"""
Please handle this message:
from: {last_agent_name}
content: {msg['content']}
"""
            to_agent_name = msg.get("to")
            if not to_agent_name:
                return f"消息中未指定 `to` 字段"

            if to_agent_name not in self.agents_config_map:
                PrettyOutput.print(
                    f"未找到智能体 {to_agent_name}，正在重试...", OutputType.WARNING
                )
                agent = self._get_agent(last_agent_name)
                if not agent:
                    return f"智能体 {last_agent_name} 未找到"
                msg = agent.run(
                    f"未找到智能体 {to_agent_name}，可用智能体列表: {list(self.agents_config_map.keys())}"
                )
                continue

            PrettyOutput.print(
                f"{last_agent_name} 正在向 {to_agent_name} 发送消息...", OutputType.INFO
            )

            agent = self._get_agent(to_agent_name)
            if not agent:
                return f"智能体 {to_agent_name} 未找到"

            last_agent_name = agent.name
            msg = agent.run(prompt)
        return ""
