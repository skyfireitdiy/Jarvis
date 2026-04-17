"""主界面模块"""

from typing import Optional
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from ..auth import AuthManager
from ..connection import ConnectionManager, ConnectionState
from ..agents import AgentManager
from ..chat import ChatManager
from ..widgets.sidebar import Sidebar
from ..widgets.chat import ChatPanel
from ..widgets.input import InputPanel
from ..widgets.terminal import TerminalPanel


class MainScreen(Screen):
    """主界面"""

    BINDINGS = [
        ("ctrl+q", "quit", "退出"),
        ("ctrl+t", "toggle_terminal", "终端"),
        ("ctrl+n", "new_agent", "新建Agent"),
        ("ctrl+l", "logout", "注销"),
        ("ctrl+r", "reconnect", "重连"),
    ]

    def __init__(
        self,
        auth_manager: AuthManager,
        connection_manager: ConnectionManager,
        agent_manager: AgentManager,
        chat_manager: ChatManager,
    ) -> None:
        super().__init__()
        self.auth_manager = auth_manager
        self.connection_manager = connection_manager
        self.agent_manager = agent_manager
        self.chat_manager = chat_manager
        self.show_terminal = False
        self._gateway_host: Optional[str] = None
        self._gateway_port: Optional[int] = None

    def compose(self) -> ComposeResult:
        """构建界面布局"""
        yield Header()
        yield Container(
            Horizontal(
                Sidebar(self.agent_manager, id="sidebar"),
                Vertical(
                    Static("连接中...", id="connection-status"),
                    ChatPanel(self.chat_manager, id="chat-panel"),
                    InputPanel(id="input-panel"),
                    id="main-content",
                ),
                TerminalPanel(id="terminal-panel"),
                id="main-container",
            )
        )
        yield Footer()

    def on_mount(self) -> None:
        """界面挂载后的初始化"""
        # 隐藏终端面板
        terminal = self.query_one("#terminal-panel", TerminalPanel)
        terminal.display = False

        # 注册消息处理器
        self._register_message_handlers()

        # 启动连接
        self.run_worker(self.connect())

    def _register_message_handlers(self) -> None:
        """注册消息处理器"""
        self.connection_manager.register_message_handler("output", self._handle_output)
        self.connection_manager.register_message_handler(
            "agent_list", self._handle_agent_list
        )
        self.connection_manager.register_message_handler("error", self._handle_error)

    async def _handle_output(self, data: dict) -> None:
        """处理输出消息"""
        agent_id = data.get("_agent_id", "")
        self.chat_manager.handle_output(agent_id, data)

        # 更新聊天面板
        chat_panel = self.query_one("#chat-panel", ChatPanel)
        if agent_id == self.agent_manager.get_current_agent_id():
            chat_panel.load_messages()

    async def _handle_agent_list(self, data: dict) -> None:
        """处理Agent列表消息"""
        agents_data = data.get("agents", [])
        self.agent_manager.process_agent_list(agents_data)

        # 刷新侧边栏
        sidebar = self.query_one("#sidebar", Sidebar)
        sidebar.refresh_agent_list()

    async def _handle_error(self, data: dict) -> None:
        """处理错误消息"""
        error_msg = data.get("message", "未知错误")
        self.notify(f"错误: {error_msg}", severity="error", timeout=5)

    def _update_connection_status(
        self, state: ConnectionState, message: str = ""
    ) -> None:
        """更新连接状态显示"""
        status = self.query_one("#connection-status", Static)
        if state == ConnectionState.CONNECTED:
            status.update("[green]● 已连接[/green]")
        elif state == ConnectionState.CONNECTING:
            status.update("[yellow]● 连接中...[/yellow]")
        elif state == ConnectionState.ERROR:
            status.update(f"[red]● 连接错误: {message}[/red]")
        else:
            status.update("[dim]● 未连接[/dim]")

    async def connect(self) -> None:
        """建立WebSocket连接"""
        token = self.auth_manager.get_token()
        if not token:
            self.notify("未登录，请先登录", severity="warning")
            self.app.switch_screen("login")
            return

        # 从auth_manager获取网关地址（需要存储）
        gateway_url = getattr(self.auth_manager, "_gateway_url", None)
        if not gateway_url:
            self.notify("未设置网关地址", severity="warning")
            self.app.switch_screen("login")
            return

        # 解析网关地址
        if ":" in gateway_url:
            host, port_str = gateway_url.rsplit(":", 1)
            try:
                port = int(port_str)
            except ValueError:
                port = 8000
        else:
            host = gateway_url
            port = 8000

        self._gateway_host = host
        self._gateway_port = port

        self._update_connection_status(ConnectionState.CONNECTING)

        try:
            success = await self.connection_manager.connect_gateway(host, port, token)
            if success:
                self._update_connection_status(ConnectionState.CONNECTED)
                self.notify("连接成功", severity="information", timeout=2)
            else:
                self._update_connection_status(ConnectionState.ERROR, "连接失败")
                self.notify("连接失败，请检查网络或重试", severity="error")
        except Exception as e:
            self._update_connection_status(ConnectionState.ERROR, str(e))
            self.notify(f"连接异常: {e}", severity="error")

    async def _send_message(self, content: str) -> None:
        """发送消息到当前Agent"""
        agent_id = self.agent_manager.get_current_agent_id()
        if not agent_id:
            self.notify("请先选择一个Agent", severity="warning")
            return

        if not self.connection_manager.is_agent_connected(agent_id):
            self.notify("Agent未连接", severity="warning")
            return

        # 添加用户消息到聊天记录
        self.chat_manager.add_user_message(agent_id, content)

        # 更新聊天面板
        chat_panel = self.query_one("#chat-panel", ChatPanel)
        chat_panel.load_messages()

        # 发送消息
        try:
            await self.connection_manager.send_to_agent(
                agent_id, {"type": "input", "content": content}
            )
        except Exception as e:
            self.notify(f"发送失败: {e}", severity="error")

    def on_input_panel_message_sent(self, event: InputPanel.MessageSent) -> None:
        """处理输入面板消息发送事件"""
        self.run_worker(self._send_message(event.content))

    def on_sidebar_agent_selected(self, event: Sidebar.AgentSelected) -> None:
        """处理Agent选中事件"""
        if event.agent_id == "__new__":
            self.run_worker(self.create_agent())
        else:
            self.agent_manager.set_current_agent(event.agent_id)
            # 连接到Agent
            self.run_worker(self._connect_to_agent(event.agent_id))

    def on_sidebar_agent_deleted(self, event: Sidebar.AgentDeleted) -> None:
        """处理Agent删除事件"""
        self.run_worker(self._delete_agent(event.agent_id))

    async def _connect_to_agent(self, agent_id: str) -> None:
        """连接到指定Agent"""
        if not self._gateway_host or not self._gateway_port:
            return

        token = self.auth_manager.get_token()
        if not token:
            return

        try:
            success = await self.connection_manager.connect_agent(
                agent_id, self._gateway_host, self._gateway_port, token
            )
            if success:
                # 加载Agent的消息
                chat_panel = self.query_one("#chat-panel", ChatPanel)
                chat_panel.set_agent(agent_id)
            else:
                self.notify(f"连接Agent {agent_id} 失败", severity="error")
        except Exception as e:
            self.notify(f"连接Agent异常: {e}", severity="error")

    async def _delete_agent(self, agent_id: str) -> None:
        """删除Agent"""
        try:
            # 断开连接
            await self.connection_manager.disconnect_agent(agent_id)
            # 从管理器中移除
            self.agent_manager.remove_agent(agent_id)
            # 刷新侧边栏
            sidebar = self.query_one("#sidebar", Sidebar)
            sidebar.refresh_agent_list()
            self.notify("Agent已删除", severity="information", timeout=2)
        except Exception as e:
            self.notify(f"删除Agent失败: {e}", severity="error")

    def action_toggle_terminal(self) -> None:
        """切换终端面板显示"""
        self.show_terminal = not self.show_terminal
        terminal = self.query_one("#terminal-panel", TerminalPanel)
        terminal.display = self.show_terminal

    def action_new_agent(self) -> None:
        """创建新Agent"""
        self.run_worker(self.create_agent())

    async def create_agent(self) -> None:
        """创建新Agent"""
        try:
            # 生成Agent名称
            agent_count = len(self.agent_manager.get_agents())
            agent_name = f"Agent-{agent_count + 1}"

            # 创建Agent（需要调用API）
            # 这里简化处理，直接添加到本地
            from ..agents import AgentInfo
            import uuid

            agent = AgentInfo(
                agent_id=str(uuid.uuid4())[:8], name=agent_name, work_dir="/tmp"
            )
            self.agent_manager.add_agent(agent)

            # 刷新侧边栏
            sidebar = self.query_one("#sidebar", Sidebar)
            sidebar.refresh_agent_list()

            self.notify(f"已创建 {agent_name}", severity="information", timeout=2)
        except Exception as e:
            self.notify(f"创建Agent失败: {e}", severity="error")

    def action_reconnect(self) -> None:
        """重新连接"""
        self.run_worker(self.connect())

    def action_logout(self) -> None:
        """注销登录"""
        self.run_worker(self._logout())

    async def _logout(self) -> None:
        """执行注销"""
        try:
            await self.connection_manager.disconnect_all()
        except Exception:
            pass
        self.auth_manager.clear_token()
        self.app.switch_screen("login")
