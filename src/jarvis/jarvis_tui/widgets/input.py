"""输入组件 - 消息输入框"""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, TextArea
from textual.message import Message


class InputPanel(Horizontal):
    """输入面板"""

    class MessageSent(Message):
        """消息发送事件"""

        def __init__(self, content: str) -> None:
            super().__init__()
            self.content = content

    def __init__(self, id: str) -> None:
        super().__init__(id=id)

    def compose(self) -> ComposeResult:
        """构建输入面板"""
        yield TextArea(id="message-input", placeholder="输入消息...")
        yield Button("发送", id="send-button", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """处理发送按钮点击"""
        if event.button.id == "send-button":
            self.send_message()

    def on_key(self, event) -> None:
        """处理按键事件"""
        # 检测Ctrl+Enter发送
        if event.key == "enter" and event.ctrl:
            self.send_message()
            event.prevent_default()

    def send_message(self) -> None:
        """发送消息"""
        text_area = self.query_one("#message-input", TextArea)
        content = text_area.text.strip()

        if content:
            self.post_message(self.MessageSent(content))
            text_area.text = ""
