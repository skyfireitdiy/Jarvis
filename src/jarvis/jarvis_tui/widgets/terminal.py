"""终端面板组件"""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, RichLog
from textual.message import Message


class TerminalPanel(Vertical):
    """终端面板"""

    class CommandSent(Message):
        """命令发送事件"""

        def __init__(self, command: str) -> None:
            super().__init__()
            self.command = command

    def __init__(self, id: str) -> None:
        super().__init__(id=id)

    def compose(self) -> ComposeResult:
        """构建终端面板"""
        yield RichLog(id="terminal-output", wrap=True, highlight=True)
        yield Input(placeholder="输入命令...", id="terminal-input")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """处理命令输入"""
        if event.input.id == "terminal-input":
            command = event.value.strip()
            if command:
                self.post_message(self.CommandSent(command))
                event.input.value = ""

    def write_output(self, text: str, style: str = "") -> None:
        """写入输出内容"""
        output = self.query_one("#terminal-output", RichLog)
        if style:
            output.write(f"[{style}]{text}[/{style}]")
        else:
            output.write(text)

    def write_error(self, text: str) -> None:
        """写入错误信息"""
        self.write_output(text, "red")

    def write_success(self, text: str) -> None:
        """写入成功信息"""
        self.write_output(text, "green")

    def clear_output(self) -> None:
        """清空输出"""
        output = self.query_one("#terminal-output", RichLog)
        output.clear()
