"""聊天模块 - 消息收发和流式输出处理"""

import logging
from typing import List, Optional, Dict, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class MessageRole(Enum):
    """消息角色"""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class MessageType(Enum):
    """消息类型"""

    TEXT = "text"
    STREAM = "stream"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"


@dataclass
class Message:
    """消息"""

    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    agent_id: str = ""
    message_type: MessageType = MessageType.TEXT
    agent_name: str = ""
    model_name: str = ""
    is_streaming: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class ChatManager:
    """聊天管理器"""

    def __init__(self):
        # 每个Agent的消息历史
        self._messages: Dict[str, List[Message]] = {}
        # 流式消息（正在接收中）
        self._streaming_messages: Dict[str, Message] = {}
        # 消息更新回调
        self._on_message_update: Optional[Callable] = None

    def set_message_update_callback(self, callback: Callable) -> None:
        """设置消息更新回调"""
        self._on_message_update = callback

    def get_messages(self, agent_id: str) -> List[Message]:
        """获取Agent的消息列表"""
        return self._messages.get(agent_id, [])

    def add_user_message(self, agent_id: str, content: str) -> Message:
        """添加用户消息"""
        message = Message(
            role=MessageRole.USER,
            content=content,
            agent_id=agent_id,
            message_type=MessageType.TEXT,
        )

        if agent_id not in self._messages:
            self._messages[agent_id] = []

        self._messages[agent_id].append(message)
        return message

    def add_assistant_message(
        self, agent_id: str, content: str, agent_name: str = "", model_name: str = ""
    ) -> Message:
        """添加助手消息"""
        message = Message(
            role=MessageRole.ASSISTANT,
            content=content,
            agent_id=agent_id,
            message_type=MessageType.TEXT,
            agent_name=agent_name,
            model_name=model_name,
        )

        if agent_id not in self._messages:
            self._messages[agent_id] = []

        self._messages[agent_id].append(message)
        return message

    def add_system_message(self, agent_id: str, content: str) -> Message:
        """添加系统消息"""
        message = Message(
            role=MessageRole.SYSTEM,
            content=content,
            agent_id=agent_id,
            message_type=MessageType.TEXT,
        )

        if agent_id not in self._messages:
            self._messages[agent_id] = []

        self._messages[agent_id].append(message)
        return message

    def handle_stream_start(self, agent_id: str, payload: Dict[str, Any]) -> None:
        """处理流式输出开始

        与web版本对齐:
        - 创建流式消息占位
        - 记录agent_name和model_name
        """
        context = payload.get("context", {})
        agent_name = context.get("agent_name", payload.get("agent_name", ""))
        model_name = context.get("model_name", "")

        streaming_message = Message(
            role=MessageRole.ASSISTANT,
            content="",
            agent_id=agent_id,
            message_type=MessageType.STREAM,
            agent_name=agent_name,
            model_name=model_name,
            is_streaming=True,
        )

        self._streaming_messages[agent_id] = streaming_message

        if agent_id not in self._messages:
            self._messages[agent_id] = []

        self._messages[agent_id].append(streaming_message)

        logger.debug(f"[STREAM] Start for agent {agent_id}")

        if self._on_message_update:
            self._on_message_update(agent_id, streaming_message)

    def handle_stream_chunk(self, agent_id: str, payload: Dict[str, Any]) -> None:
        """处理流式输出块

        与web版本对齐:
        - 追加内容到流式消息
        - 触发UI更新
        """
        streaming_message = self._streaming_messages.get(agent_id)
        if streaming_message:
            streaming_message.content += payload.get("text", "")

            if self._on_message_update:
                self._on_message_update(agent_id, streaming_message)
        else:
            logger.warning(
                f"[STREAM] Received chunk but no streaming message found for agent: {agent_id}"
            )

    def handle_stream_end(self, agent_id: str, payload: Dict[str, Any]) -> None:
        """处理流式输出结束

        与web版本对齐:
        - 完成流式消息
        - 保存到历史
        """
        streaming_message = self._streaming_messages.get(agent_id)
        if streaming_message:
            streaming_message.is_streaming = False
            streaming_message.message_type = MessageType.TEXT

            del self._streaming_messages[agent_id]

            logger.debug(f"[STREAM] End for agent {agent_id}")

            if self._on_message_update:
                self._on_message_update(agent_id, streaming_message)

    def handle_output(self, agent_id: str, payload: Dict[str, Any]) -> None:
        """处理输出消息

        根据output_type分发到不同的处理函数
        """
        output_type = payload.get("output_type")

        if output_type == "STREAM_START":
            self.handle_stream_start(agent_id, payload)
        elif output_type == "STREAM_CHUNK":
            self.handle_stream_chunk(agent_id, payload)
        elif output_type == "STREAM_END":
            self.handle_stream_end(agent_id, payload)
        elif output_type == "TEXT":
            # 普通文本输出
            text = payload.get("text", "")
            agent_name = payload.get("agent_name", "")
            self.add_assistant_message(agent_id, text, agent_name)

            if self._on_message_update:
                self._on_message_update(agent_id, self._messages[agent_id][-1])
        else:
            logger.debug(f"[OUTPUT] Unknown output type: {output_type}")

    async def load_history_messages(
        self, agent_id: str, limit: int = 50, before: Optional[str] = None
    ) -> List[Message]:
        """加载历史消息

        Args:
            agent_id: Agent ID
            limit: 加载数量限制
            before: 加载此时间之前的消息

        Returns:
            List[Message]: 消息列表
        """
        # 这个方法需要通过connection_manager调用API
        # 这里返回本地缓存的消息
        messages = self._messages.get(agent_id, [])
        if before:
            # 过滤before时间之前的消息
            from datetime import datetime

            try:
                before_time = datetime.fromisoformat(before)
                messages = [m for m in messages if m.timestamp < before_time]
            except ValueError:
                logger.warning(f"Invalid before time format: {before}")

        # 限制返回数量
        return messages[-limit:] if len(messages) > limit else messages

    def get_message_count(self, agent_id: str) -> int:
        """获取Agent消息数量"""
        return len(self._messages.get(agent_id, []))

    def export_messages(self, agent_id: str, format: str = "json") -> str:
        """导出消息

        Args:
            agent_id: Agent ID
            format: 导出格式 (json/markdown/text)

        Returns:
            str: 导出内容
        """
        import json

        messages = self._messages.get(agent_id, [])

        if format == "json":
            return json.dumps(
                [
                    {
                        "role": m.role.value,
                        "content": m.content,
                        "timestamp": m.timestamp.isoformat(),
                        "agent_name": m.agent_name,
                        "message_type": m.message_type.value,
                    }
                    for m in messages
                ],
                ensure_ascii=False,
                indent=2,
            )
        elif format == "markdown":
            lines = []
            for m in messages:
                role = "User" if m.role == MessageRole.USER else "Assistant"
                lines.append(
                    f"### {role} ({m.timestamp.strftime('%Y-%m-%d %H:%M:%S')})\n"
                )
                lines.append(f"{m.content}\n")
            return "\n".join(lines)
        elif format == "text":
            lines = []
            for m in messages:
                role = "User" if m.role == MessageRole.USER else "Assistant"
                lines.append(f"[{role}] {m.content}")
            return "\n".join(lines)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def clear_messages(self, agent_id: str) -> None:
        """清空Agent的消息"""
        if agent_id in self._messages:
            self._messages[agent_id].clear()
        if agent_id in self._streaming_messages:
            del self._streaming_messages[agent_id]

    def clear_all(self) -> None:
        """清空所有消息"""
        self._messages.clear()
        self._streaming_messages.clear()

    async def send_message(self, message: str, agent_id: Optional[str] = None) -> None:
        """发送消息到Agent

        Args:
            message: 消息内容
            agent_id: Agent ID，如果为None则使用当前Agent
        """
        # 这个方法在TUI版本中主要由UI层调用
        # 实际发送逻辑在connection_manager中处理
        # 这里只负责添加用户消息到聊天记录
        if agent_id is None:
            # 如果没有指定agent_id，需要从外部获取当前Agent
            # 这里暂时留空，由调用方处理
            logger.warning("send_message called without agent_id")
            return

        # 添加用户消息
        self.add_user_message(agent_id, message)
        logger.debug(f"Message sent to agent {agent_id}: {message[:50]}...")
