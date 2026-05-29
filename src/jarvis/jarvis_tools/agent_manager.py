# -*- coding: utf-8 -*-
"""Agent 管理工具 - 用于管理 Agent 之间的通信和协作"""

from typing import Any, Dict, Optional
from jarvis.jarvis_utils.globals import add_input_buffer


class AgentManagerTool:
    """Agent 管理工具，支持多种操作：

    1. **send_to**: 向指定 Agent 发送消息
    2. 未来可扩展更多 action（如：list_agents, get_status 等）

    **重要提示**：
    - 每次调用只能执行一种操作
    - 参数根据操作类型而有所不同
    """

    name = "agent_manager"
    description = """Agent 管理工具，用于管理 Agent 之间的通信和协作。

支持的操作：
1. **send_to**: 向指定 Agent 发送消息，消息会被添加到目标 Agent 的输入缓冲区

**重要提示**：
- 每次调用只能执行一种操作（send_to 等）
- 参数根据操作类型而有所不同"""

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["send_to"],
                "description": "操作类型：send_to（向 Agent 发送消息）",
            },
            # send_to 操作的参数
            "agent_id": {
                "type": "string",
                "description": "目标 Agent 的 ID 或名称",
            },
            "message": {
                "type": "string",
                "description": "要发送的消息内容",
            },
        },
        "required": ["action", "message"],
    }

    def execute(
        self, action: str, agent_id: Optional[str] = None, message: str = "", **kwargs
    ) -> Dict[str, Any]:
        """执行 Agent 管理操作

        参数:
            action: 操作类型 (send_to)
            agent_id: 目标 Agent ID（可选）
            message: 消息内容
            **kwargs: 其他参数

        返回:
            Dict[str, Any]: 执行结果
        """
        try:
            if action == "send_to":
                return self._send_to(agent_id, message)
            else:
                return {
                    "success": False,
                    "error": f"Unknown action: {action}",
                }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    def _send_to(self, agent_id: Optional[str], message: str) -> Dict[str, Any]:
        """向指定 Agent 发送消息

        参数:
            agent_id: 目标 Agent ID（可选）
            message: 消息内容

        返回:
            Dict[str, Any]: 发送结果
        """
        if not message:
            return {
                "success": False,
                "error": "message is required",
            }

        # 构建消息格式：Agent xxxx 发来消息：yyyyy
        if agent_id:
            formatted_message = f"Agent {agent_id} 发来消息：{message}"
        else:
            formatted_message = f"Agent 发来消息：{message}"

        # 添加到输入缓冲区
        add_input_buffer(formatted_message)

        return {
            "success": True,
            "data": {
                "agent_id": agent_id,
                "message": message,
                "formatted_message": formatted_message,
            },
        }
