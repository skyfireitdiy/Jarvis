"""文件查看面板组件"""

from typing import Optional
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Static, Button, Label
from textual.reactive import reactive
from textual.message import Message

from ..file_manager import FileManager


class FileViewer(Container):
    """文件查看面板"""

    DEFAULT_CSS = """
    FileViewer {
        height: 100%;
        width: 100%;
        border: solid $primary;
        background: $surface;
    }
    
    FileViewer .file-header {
        height: 3;
        width: 100%;
        background: $primary;
        color: $text;
        padding: 0 1;
    }
    
    FileViewer .file-content {
        height: 1fr;
        width: 100%;
        overflow: auto;
        padding: 1;
    }
    
    FileViewer .file-path {
        width: 1fr;
        text-align: left;
    }
    
    FileViewer .file-controls {
        width: auto;
        align: right middle;
    }
    """

    file_path = reactive("")
    file_content = reactive("")
    is_editable = reactive(False)

    def __init__(self, file_manager: FileManager, id: Optional[str] = None):
        super().__init__(id=id)
        self.file_manager = file_manager
        self.current_agent_id: Optional[str] = None

    def compose(self) -> ComposeResult:
        with Container(classes="file-header"):
            with Horizontal():
                yield Label("", classes="file-path", id="file-path-label")
                with Container(classes="file-controls"):
                    yield Button("编辑", id="edit-button", variant="primary")
                    yield Button(
                        "保存", id="save-button", variant="success", disabled=True
                    )
                    yield Button("关闭", id="close-button", variant="error")
        yield Static("", classes="file-content", id="file-content-viewer")

    def watch_file_path(self, old_path: str, new_path: str) -> None:
        """文件路径变化时更新显示"""
        if new_path:
            self.query_one("#file-path-label", Label).update(new_path)
            self.run_worker(self.load_file_content())

    def watch_file_content(self, old_content: str, new_content: str) -> None:
        """文件内容变化时更新显示"""
        self.query_one("#file-content-viewer", Static).update(new_content)

    async def load_file_content(self) -> None:
        """加载文件内容"""
        if not self.file_path or not self.current_agent_id:
            return

        content = await self.file_manager.read_file(
            self.current_agent_id, self.file_path
        )
        if content is not None:
            self.file_content = content
        else:
            self.file_content = "无法读取文件内容"

    def set_agent(self, agent_id: str) -> None:
        """设置当前Agent"""
        self.current_agent_id = agent_id

    def open_file(self, path: str) -> None:
        """打开文件"""
        self.file_path = path
        self.is_editable = False
        self.query_one("#save-button", Button).disabled = True
        self.query_one("#edit-button", Button).disabled = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """处理按钮点击事件"""
        button_id = event.button.id
        if button_id == "edit-button":
            self.is_editable = True
            self.query_one("#save-button", Button).disabled = False
            self.query_one("#edit-button", Button).disabled = True
        elif button_id == "save-button":
            self.run_worker(self.save_file())
        elif button_id == "close-button":
            self.close_file()

    async def save_file(self) -> None:
        """保存文件"""
        if not self.file_path or not self.current_agent_id:
            return

        # 获取当前内容（这里简化处理，实际应该从编辑器获取）
        content = self.file_content
        success = await self.file_manager.write_file(
            self.current_agent_id, self.file_path, content
        )
        if success:
            self.is_editable = False
            self.query_one("#save-button", Button).disabled = True
            self.query_one("#edit-button", Button).disabled = False
            self.post_message(self.FileSaved(self.file_path))
        else:
            self.post_message(self.FileSaveError(self.file_path))

    def close_file(self) -> None:
        """关闭文件"""
        self.file_path = ""
        self.file_content = ""
        self.is_editable = False
        self.post_message(self.FileClosed())

    class FileSaved(Message):
        """文件保存成功消息"""

        def __init__(self, path: str) -> None:
            self.path = path
            super().__init__()

    class FileSaveError(Message):
        """文件保存失败消息"""

        def __init__(self, path: str) -> None:
            self.path = path
            super().__init__()

    class FileClosed(Message):
        """文件关闭消息"""

        pass
