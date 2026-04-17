"""聊天面板组件"""

from typing import Optional
from textual.app import ComposeResult
from textual.containers import Vertical, ScrollableContainer
from textual.widgets import Static, Markdown

from ..chat import ChatManager, Message, MessageRole


class MessageWidget(Static):
    """消息组件"""

    _message_counter = 0

    def __init__(self, message: Message) -> None:
        super().__init__()
        self.message = message
        MessageWidget._message_counter += 1
        self.message_id = MessageWidget._message_counter

    def compose(self) -> ComposeResult:
        """构建消息显示"""
        # 根据角色设置样式
        if self.message.role == MessageRole.USER:
            align = "right"
            prefix = "你: "
        elif self.message.role == MessageRole.SYSTEM:
            align = "center"
            prefix = "系统: "
        else:
            align = "left"
            prefix = "Jarvis: "

        # 使用Markdown渲染内容
        content = f"{prefix}{self.message.content}"
        yield Markdown(content, classes=f"message-{align}")


class ChatPanel(ScrollableContainer):
    """聊天面板"""

    def __init__(self, chat_manager: ChatManager, id: str) -> None:
        super().__init__(id=id)
        self.chat_manager = chat_manager
        self.current_agent_id: Optional[str] = None

    def compose(self) -> ComposeResult:
        """构建聊天面板"""
        yield Vertical(id="messages-container")

    def on_mount(self) -> None:
        """挂载后设置消息更新回调"""
        self.chat_manager.set_message_update_callback(self.on_message_update)

    def set_agent(self, agent_id: str) -> None:
        """设置当前Agent并加载消息"""
        self.current_agent_id = agent_id
        self.load_messages()

    def load_messages(self) -> None:
        """加载消息"""
        container = self.query_one("#messages-container", Vertical)
        container.remove_children()

        if not self.current_agent_id:
            return

        messages = self.chat_manager.get_messages(self.current_agent_id)
        for message in messages:
            widget = MessageWidget(message)
            container.mount(widget)

        # 滚动到底部
        self.scroll_end(animate=False)

    def on_message_update(self, agent_id: str, message: Message) -> None:
        """消息更新回调"""
        if agent_id != self.current_agent_id:
            return

        container = self.query_one("#messages-container", Vertical)

        # 查找是否已有该消息的widget（流式更新）
        if message.is_streaming and container.children:
            last_widget = container.children[-1]
            if isinstance(last_widget, MessageWidget):
                if (
                    last_widget.message.is_streaming
                    and last_widget.message.role == message.role
                ):
                    # 更新现有widget
                    last_widget.message = message
                    last_widget.refresh()
                    self.scroll_end(animate=False)
                    return

        # 添加新消息
        widget = MessageWidget(message)
        container.mount(widget)
        self.scroll_end(animate=True)

    def clear_messages(self) -> None:
        """清空消息"""
        container = self.query_one("#messages-container", Vertical)
        container.remove_children()
