# -*- coding: utf-8 -*-
"""工具预筛选（_preselect_tools）与 ToolRegistry.prompt 预筛逻辑单测"""

from unittest.mock import patch

from jarvis.jarvis_tools.registry import (
    ToolRegistry,
    _preselect_tools,
    _TOOL_PRESELECT_THRESHOLD,
)


def _mk_tool(name, desc):
    return {
        "name": name,
        "description": desc,
        "parameters": {"type": "object", "properties": {}},
    }


def _mk_tools():
    return [
        _mk_tool("read_code", "读取源代码文件内容"),
        _mk_tool("write_file", "写入文件"),
        _mk_tool("search_web", "搜索互联网信息"),
        _mk_tool("execute_script", "执行脚本命令"),
        _mk_tool("memory", "管理记忆"),
    ]


def test_preselect_matches_relevant_tools():
    tools = _mk_tools()
    out = _preselect_tools("读取文件内容", tools)
    names = [t["name"] for t in out]
    # 匹配"读取"的 read_code 应被选中
    assert "read_code" in names
    # 不相关的工具（如 search_web）不应出现在结果里
    assert "search_web" not in names


def test_preselect_empty_context_returns_all():
    tools = _mk_tools()
    out = _preselect_tools("", tools)
    assert out == tools


def test_preselect_no_match_returns_all():
    tools = _mk_tools()
    # 无任何关键词命中任何工具描述
    out = _preselect_tools("xyzzy_nonsense_qq", tools)
    assert out == tools


def test_preselect_top_n_limits():
    tools = _mk_tools()
    out = _preselect_tools("文件", tools, top_n=1)
    assert len(out) <= 1


def test_preselect_exception_returns_all():
    tools = _mk_tools()
    with patch("jieba.cut", side_effect=Exception("boom")):
        out = _preselect_tools("读取文件", tools)
    assert out == tools


def test_prompt_no_task_context_keeps_all():
    """无 task_context 时 prompt 全量注入（不预筛）"""
    r = ToolRegistry()
    all_tools = r.get_all_tools()
    p = r.prompt()
    # 所有工具名都应出现在 prompt 里
    for t in all_tools:
        assert t["name"] in p


def test_prompt_below_threshold_no_preselect():
    """工具数未超阈值时即使有 task_context 也不预筛"""
    r = ToolRegistry()
    assert len(r.get_all_tools()) <= _TOOL_PRESELECT_THRESHOLD
    p1 = r.prompt()
    p2 = r.prompt("读取文件并编辑")
    assert p1 == p2


def test_prompt_above_threshold_preselects_and_keeps_required():
    """工具数超阈值时启用预筛，且必选工具 execute_script 始终保留"""
    r = ToolRegistry()
    # 构造超阈值场景：mock get_all_tools 返回大量工具
    many_tools = _mk_tools() * 30  # 150 个工具，超过阈值 50
    with patch.object(r, "get_all_tools", return_value=many_tools):
        p = r.prompt("读取文件")
    # 必选工具 execute_script 应始终保留
    assert "execute_script" in p
    # 匹配"读取"的 read_code 应被保留
    assert "read_code" in p
    # 不相关的 search_web 不应出现在预筛后的 prompt 里
    assert "search_web" not in p
