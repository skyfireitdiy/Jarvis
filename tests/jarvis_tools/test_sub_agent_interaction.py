# -*- coding: utf-8 -*-
"""子 Agent 交互模式继承的单测。

验证 SubAgentTool / SubCodeAgentTool 创建子 Agent 时，non_interactive
按父 Agent 的交互配置条件性继承：
- 父 Agent 可交互（non_interactive 非 True 且 auto_complete 非 True）→ 子 Agent 可交互
- 父 Agent 非交互（non_interactive=True）→ 子 Agent 非交互
- 父 Agent 自动完成（auto_complete=True）→ 子 Agent 非交互

实现说明：通过 patch 真实 Agent/CodeAgent 类的 __init__ 来捕获构造参数，
而不是替换类对象本身——因为 sub_code_agent 内部用
`isinstance(parent_agent, CodeAgent)` 做类型校验，替换类对象会破坏该检查。
"""

from unittest.mock import MagicMock, patch

import pytest

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_code_agent.code_agent import CodeAgent
from jarvis.jarvis_tools import sub_agent as sub_agent_mod
from jarvis.jarvis_tools import sub_code_agent as sub_code_agent_mod


class _FakeParent:
    """最小可用的通用父 Agent 替身，仅暴露被继承的属性。"""

    def __init__(self, non_interactive=None, auto_complete=None):
        self.non_interactive = non_interactive
        self.auto_complete = auto_complete
        self.model = MagicMock()
        self.model.get_messages.return_value = []

    def get_tool_registry(self):
        return None

    def add_memory_tags(self, tags):
        pass


class _FakeCodeParent(CodeAgent):
    """真继承 CodeAgent 的父替身，绕过 __init__ 以便通过 isinstance 校验。"""

    def __init__(self, non_interactive=None, auto_complete=None):
        self.non_interactive = non_interactive
        self.auto_complete = auto_complete
        self.model = MagicMock()
        self.model.get_messages.return_value = []

    def get_tool_registry(self):
        return None

    def add_memory_tags(self, tags):
        pass


def _capture_non_interactive(cls, tool, parent):
    """调用 tool.execute，捕获子 Agent 构造时的 non_interactive 实参。

    patch 目标类的 __init__，记录 kwargs 后不执行真实初始化，并让实例带上
    子 Agent 需要的方法（run/get_memory_tags/get_tool_registry 等）。
    """
    captured = {}

    def fake_init(self, *args, **kwargs):
        captured.update(kwargs)
        self.run = MagicMock(return_value="done")
        self.get_memory_tags = MagicMock(return_value=[])
        self.get_tool_registry = MagicMock(return_value=None)
        self.set_user_data = MagicMock()
        self.set_use_tools = MagicMock()

    with patch.object(cls, "__init__", fake_init):
        result = tool.execute({"task": "t", "agent": parent})

    assert result["success"] is True, result
    assert captured, "子 Agent 未被构造"
    return captured.get("non_interactive")


@pytest.mark.parametrize(
    "parent_non_interactive,parent_auto_complete,expected",
    [
        # 父可交互：子 Agent 必须可交互（这是本次修复的核心）
        (False, False, False),
        (False, None, False),
        (None, False, False),
        # 父存在但两属性均未设置 → 视为可交互
        (None, None, False),
        # 父非交互 → 子非交互
        (True, False, True),
        # 父自动完成 → 子非交互
        (False, True, True),
        (None, True, True),
    ],
)
def test_sub_agent_inherits_interaction(
    parent_non_interactive, parent_auto_complete, expected
):
    parent = _FakeParent(parent_non_interactive, parent_auto_complete)
    tool = sub_agent_mod.SubAgentTool()
    got = _capture_non_interactive(Agent, tool, parent)
    assert got is expected


@pytest.mark.parametrize(
    "parent_non_interactive,parent_auto_complete,expected",
    [
        (False, False, False),
        (False, None, False),
        (None, False, False),
        (None, None, False),
        (True, False, True),
        (False, True, True),
        (None, True, True),
    ],
)
def test_sub_code_agent_inherits_interaction(
    parent_non_interactive, parent_auto_complete, expected
):
    parent = _FakeCodeParent(parent_non_interactive, parent_auto_complete)
    tool = sub_code_agent_mod.SubCodeAgentTool()
    got = _capture_non_interactive(CodeAgent, tool, parent)
    assert got is expected


def test_sub_agent_no_parent_is_interactive():
    """未提供父 Agent 时无可继承的非交互依据，子 Agent 保持可交互。"""
    tool = sub_agent_mod.SubAgentTool()
    got = _capture_non_interactive(Agent, tool, None)
    assert got is False
