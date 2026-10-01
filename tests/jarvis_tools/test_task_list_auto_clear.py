# -*- coding: utf-8 -*-
"""测试：创建任务列表时自动清除历史任务列表

需求：在创建任务列表（add_tasks 自动创建）时，自动清除历史任务列表，
因为创建新列表通常意味着之前的任务已完成。
"""

from unittest.mock import Mock

from jarvis.jarvis_tools.task_list_manager import task_list_manager


def _make_tool():
    """构造未初始化 __init__ 的 tool 实例（仅测 helper 逻辑）"""
    return task_list_manager.__new__(task_list_manager)


def _make_task_info():
    """构造一个合法的 tasks_info 列表"""
    return [
        {
            "task_name": "任务A",
            "task_desc": "描述A",
            "expected_output": "1) 输出A",
            "agent_type": "main",
        }
    ]


def _make_agent(old_task_list_id="old_list_001", is_sub_agent=False):
    """构造 mock agent，默认已有历史任务列表且为主 Agent"""
    agent = Mock()
    agent.name = "test_agent"

    def fake_get_user_data(key):
        if key == "__task_list_id__":
            return old_task_list_id
        if key == "__is_sub_agent__":
            return is_sub_agent
        return None

    agent.get_user_data.side_effect = fake_get_user_data
    agent.set_user_data.return_value = None
    agent.delete_user_data.return_value = None
    return agent


def _make_task_list_manager(existing=True, delete_success=True):
    """构造 mock task_list_manager"""
    tlm = Mock()
    if existing:
        tlm.get_task_list.return_value = Mock()  # 非 None，表示旧列表仍存在
    else:
        tlm.get_task_list.return_value = None
    tlm.delete_task_list.return_value = (
        delete_success,
        None if delete_success else "删除失败",
    )
    tlm.create_task_list.return_value = ("new_list_002", True, None)
    tlm.add_tasks.return_value = (["task-1"], True, None)
    return tlm


class TestAutoClearOnCreate:
    """创建任务列表时自动清除历史任务列表"""

    def test_existing_task_list_auto_cleared_and_new_created(self):
        """已有历史任务列表时，add_tasks 自动清除旧列表并创建新列表"""
        tool = _make_tool()
        agent = _make_agent(old_task_list_id="old_list_001")
        tlm = _make_task_list_manager(existing=True, delete_success=True)

        result = tool._handle_add_tasks(
            args={
                "tasks_info": _make_task_info(),
                "main_goal": "新目标",
            },
            task_list_manager=tlm,
            agent_id="test_agent",
            is_main_agent=True,
            agent=agent,
        )

        assert result["success"] is True
        # 旧列表被删除
        tlm.delete_task_list.assert_called_once_with("old_list_001", True)
        # 新列表被创建
        tlm.create_task_list.assert_called_once()
        # 任务被添加
        tlm.add_tasks.assert_called_once()
        # Agent 上的残留状态被清除
        agent.delete_user_data.assert_any_call("__running_task_id__")

    def test_no_existing_task_list_does_not_delete(self):
        """没有历史任务列表时，不调用 delete_task_list"""
        tool = _make_tool()
        agent = _make_agent(old_task_list_id=None)
        tlm = _make_task_list_manager(existing=False)

        result = tool._handle_add_tasks(
            args={
                "tasks_info": _make_task_info(),
                "main_goal": "新目标",
            },
            task_list_manager=tlm,
            agent_id="test_agent",
            is_main_agent=True,
            agent=agent,
        )

        assert result["success"] is True
        tlm.delete_task_list.assert_not_called()
        tlm.create_task_list.assert_called_once()

    def test_sub_agent_cannot_auto_clear(self):
        """子 Agent 无权自动清除历史任务列表，返回失败"""
        tool = _make_tool()
        agent = _make_agent(old_task_list_id="old_list_001", is_sub_agent=True)
        tlm = _make_task_list_manager(existing=True)

        result = tool._handle_add_tasks(
            args={
                "tasks_info": _make_task_info(),
                "main_goal": "新目标",
            },
            task_list_manager=tlm,
            agent_id="test_agent",
            is_main_agent=False,
            agent=agent,
        )

        assert result["success"] is False
        assert "无权自动清除" in result["stderr"]
        # 未删除、未创建新列表
        tlm.delete_task_list.assert_not_called()
        tlm.create_task_list.assert_not_called()

    def test_delete_failure_returns_error(self):
        """删除历史任务列表失败时返回错误，不创建新列表"""
        tool = _make_tool()
        agent = _make_agent(old_task_list_id="old_list_001")
        tlm = _make_task_list_manager(existing=True, delete_success=False)

        result = tool._handle_add_tasks(
            args={
                "tasks_info": _make_task_info(),
                "main_goal": "新目标",
            },
            task_list_manager=tlm,
            agent_id="test_agent",
            is_main_agent=True,
            agent=agent,
        )

        assert result["success"] is False
        assert "自动清除历史任务列表失败" in result["stderr"]
        tlm.create_task_list.assert_not_called()
