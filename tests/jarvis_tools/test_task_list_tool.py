# -*- coding: utf-8 -*-
"""task_list_manager 工具的纯逻辑 helper 单测"""

from jarvis.jarvis_tools.task_list_manager import task_list_manager


def _tool():
    return task_list_manager.__new__(task_list_manager)


def test_build_iteration_task_content_first_iteration_unchanged():
    t = _tool()
    out = t._build_iteration_task_content("任务内容", 1, [])
    assert out == "任务内容"


def test_build_iteration_task_content_appends_latest_feedback():
    t = _tool()
    out = t._build_iteration_task_content("任务内容", 2, ["第一轮反馈", "第二轮反馈"])
    assert "任务内容" in out
    assert "第二轮反馈" in out
    assert "修复问题" in out
