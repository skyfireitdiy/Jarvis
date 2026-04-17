"""侧边栏组件 - Agent列表管理"""

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Button, Static, ListView, ListItem, Label
from textual.message import Message

from ..agents import AgentManager, AgentInfo


class AgentItem(ListItem):
    """Agent列表项"""

    def __init__(self, agent: AgentInfo, is_selected: bool = False) -> None:
        super().__init__()
        self.agent = agent
        self.is_selected = is_selected

    def compose(self) -> ComposeResult:
        """构建列表项"""
        prefix = "● " if self.is_selected else "  "
        yield Label(f"{prefix}{self.agent.name}")


class Sidebar(Vertical):
    """侧边栏组件"""

    class AgentSelected(Message):
        """Agent选中事件"""

        def __init__(self, agent_id: str) -> None:
            super().__init__()
            self.agent_id = agent_id

    class AgentDeleted(Message):
        """Agent删除事件"""

        def __init__(self, agent_id: str) -> None:
            super().__init__()
            self.agent_id = agent_id

    def __init__(self, agent_manager: AgentManager, id: str) -> None:
        super().__init__(id=id)
        self.agent_manager = agent_manager

    def compose(self) -> ComposeResult:
        """构建侧边栏布局"""
        yield Static("Agents", classes="sidebar-title")
        yield ListView(id="agent-list")
        yield Horizontal(
            Button("新建", id="new-agent-btn", variant="success"),
            Button("删除", id="delete-agent-btn", variant="error"),
            classes="sidebar-buttons",
        )

    def on_mount(self) -> None:
        """挂载后刷新列表"""
        self.refresh_agent_list()

    def refresh_agent_list(self) -> None:
        """刷新Agent列表"""
        agent_list = self.query_one("#agent-list", ListView)
        agent_list.clear()

        selected_id = self.agent_manager.get_current_agent_id()

        for agent in self.agent_manager.get_agents():
            is_selected = agent.agent_id == selected_id
            item = AgentItem(agent, is_selected)
            agent_list.append(item)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """处理列表选中事件"""
        if isinstance(event.item, AgentItem):
            agent_id = event.item.agent.agent_id
            self.agent_manager.set_current_agent(agent_id)
            self.post_message(self.AgentSelected(agent_id))
            self.refresh_agent_list()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """处理按钮点击事件"""
        if event.button.id == "new-agent-btn":
            self.post_message(self.AgentSelected("__new__"))
        elif event.button.id == "delete-agent-btn":
            selected_id = self.agent_manager.get_current_agent_id()
            if selected_id:
                self.post_message(self.AgentDeleted(selected_id))
