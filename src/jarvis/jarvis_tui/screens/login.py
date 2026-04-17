"""登录界面模块"""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Label, Static

from ..auth import (
    AuthManager,
    AuthenticationError,
    ConnectionError as AuthConnectionError,
)


class LoginScreen(Screen):
    """登录界面"""

    BINDINGS = [("escape", "app.quit", "退出")]

    def __init__(self, auth_manager: AuthManager) -> None:
        super().__init__()
        self.auth_manager = auth_manager
        self.gateway_url = "localhost:8000"
        self.error_message = Static("", id="error-message")

    def compose(self) -> ComposeResult:
        """构建界面布局"""
        yield Container(
            Vertical(
                Static("Jarvis TUI 登录", id="title"),
                Horizontal(
                    Label("服务器地址:"),
                    Input(
                        placeholder="localhost:8000",
                        value=self.gateway_url,
                        id="server-input",
                    ),
                    id="server-row",
                ),
                Horizontal(
                    Label("密码:"),
                    Input(placeholder="请输入密码", password=True, id="password-input"),
                    id="password-row",
                ),
                self.error_message,
                Button("登录", id="login-button", variant="primary"),
                id="login-form",
            ),
            id="login-container",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """处理按钮点击事件"""
        if event.button.id == "login-button":
            self.run_worker(self.login())

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """处理输入框回车事件"""
        if event.input.id == "password-input":
            self.run_worker(self.login())

    async def login(self) -> None:
        """执行登录操作"""
        server_input = self.query_one("#server-input", Input)
        password_input = self.query_one("#password-input", Input)

        server_url = server_input.value.strip()
        password = password_input.value

        if not server_url:
            self.show_error("请输入服务器地址")
            return

        if not password:
            self.show_error("请输入密码")
            return

        try:
            await self.auth_manager.login(server_url, password)
            self.app.switch_screen("main")
        except AuthenticationError as e:
            self.show_error(f"认证失败: {e}")
        except AuthConnectionError as e:
            self.show_error(f"连接失败: {e}")
        except Exception as e:
            self.show_error(f"未知错误: {e}")

    def show_error(self, message: str) -> None:
        """显示错误信息"""
        self.error_message.update(message)
        self.error_message.add_class("error")
