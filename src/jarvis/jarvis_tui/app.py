"""Jarvis TUI 主应用"""

import logging
from textual.app import App

from .auth import AuthManager
from .connection import ConnectionManager
from .agents import AgentManager
from .chat import ChatManager
from .screens.login import LoginScreen
from .screens.main import MainScreen

logger = logging.getLogger(__name__)


class JarvisTUI(App):
    """Jarvis TUI 应用"""

    CSS_PATH = "styles.css"
    TITLE = "Jarvis TUI"

    def __init__(self) -> None:
        super().__init__()
        # 初始化管理器
        self.auth_manager = AuthManager()
        self.connection_manager = ConnectionManager()
        self.agent_manager = AgentManager()
        self.chat_manager = ChatManager()

        # 注册屏幕
        self.install_screen(LoginScreen(self.auth_manager), name="login")
        self.install_screen(
            MainScreen(
                self.auth_manager,
                self.connection_manager,
                self.agent_manager,
                self.chat_manager,
            ),
            name="main",
        )

    def on_mount(self) -> None:
        """应用挂载后的初始化"""
        # 默认显示登录界面
        self.push_screen("login")

    def action_quit(self) -> None:
        """退出应用"""
        self.connection_manager.disconnect_all()
        self.exit()
