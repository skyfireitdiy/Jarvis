# -*- coding: utf-8 -*-
"""方法论自动提取功能测试"""

import pytest
from unittest.mock import MagicMock, patch


class TestMethodologyExtractionConfig:
    """测试方法论自动提取配置项"""

    def test_is_enable_auto_methodology_extraction_default_false(self):
        """测试默认情况下方法论自动提取是关闭的"""
        from jarvis.jarvis_utils.config import is_enable_auto_methodology_extraction
        from jarvis.jarvis_utils.config import GLOBAL_CONFIG_DATA

        # 清除配置
        if "auto_methodology_extraction" in GLOBAL_CONFIG_DATA:
            del GLOBAL_CONFIG_DATA["auto_methodology_extraction"]

        assert is_enable_auto_methodology_extraction() is False

    def test_is_enable_auto_methodology_extraction_when_enabled(self):
        """测试启用方法论自动提取时返回True"""
        from jarvis.jarvis_utils.config import is_enable_auto_methodology_extraction
        from jarvis.jarvis_utils.config import GLOBAL_CONFIG_DATA

        # 设置配置
        GLOBAL_CONFIG_DATA["auto_methodology_extraction"] = True

        try:
            assert is_enable_auto_methodology_extraction() is True
        finally:
            # 清理
            del GLOBAL_CONFIG_DATA["auto_methodology_extraction"]

    def test_is_enable_auto_methodology_extraction_when_disabled(self):
        """测试禁用方法论自动提取时返回False"""
        from jarvis.jarvis_utils.config import is_enable_auto_methodology_extraction
        from jarvis.jarvis_utils.config import GLOBAL_CONFIG_DATA

        # 设置配置
        GLOBAL_CONFIG_DATA["auto_methodology_extraction"] = False

        try:
            assert is_enable_auto_methodology_extraction() is False
        finally:
            # 清理
            del GLOBAL_CONFIG_DATA["auto_methodology_extraction"]


class TestTaskAnalyzerMethodologyExtraction:
    """测试TaskAnalyzer中的方法论提取功能"""

    @pytest.fixture
    def mock_agent(self):
        """创建模拟的Agent对象"""
        agent = MagicMock()
        agent.original_user_input = "实现一个用户登录功能"
        agent.model = MagicMock()
        agent.model._history = [
            {"role": "user", "content": "实现一个用户登录功能"},
            {
                "role": "assistant",
                "content": "1. 首先创建用户模型\n2. 实现登录接口\n3. 添加验证逻辑",
            },
            {
                "role": "assistant",
                "content": '<TOOL_CALL>{"name": "edit_file", "arguments": {}}</TOOL_CALL>',
            },
        ]
        agent.get_event_bus = MagicMock(return_value=MagicMock())
        agent.get_user_data = MagicMock(return_value=False)
        agent.use_analysis = False
        return agent

    def test_try_extract_methodology_disabled_by_default(self, mock_agent):
        """测试默认情况下不执行方法论提取"""
        from jarvis.jarvis_agent.task_analyzer import TaskAnalyzer
        from jarvis.jarvis_utils.config import GLOBAL_CONFIG_DATA

        # 确保配置关闭
        if "auto_methodology_extraction" in GLOBAL_CONFIG_DATA:
            del GLOBAL_CONFIG_DATA["auto_methodology_extraction"]

        analyzer = TaskAnalyzer(mock_agent)
        analyzer._methodology_extraction_done = False

        # 调用方法
        analyzer._try_extract_methodology()

        # 验证标志被设置
        assert analyzer._methodology_extraction_done is True

    def test_try_extract_methodology_skips_if_already_done(self, mock_agent):
        """测试如果已经执行过则跳过"""
        from jarvis.jarvis_agent.task_analyzer import TaskAnalyzer

        analyzer = TaskAnalyzer(mock_agent)
        analyzer._methodology_extraction_done = True

        # 调用方法（应该直接返回）
        analyzer._try_extract_methodology()

        # 验证标志仍然为True
        assert analyzer._methodology_extraction_done is True

    def test_collect_execution_steps(self, mock_agent):
        """测试收集执行步骤"""
        from jarvis.jarvis_agent.task_analyzer import TaskAnalyzer

        analyzer = TaskAnalyzer(mock_agent)
        steps = analyzer._collect_execution_steps()

        # 验证收集到了步骤
        assert len(steps) > 0
        assert any("创建用户模型" in step for step in steps)

    def test_collect_tool_calls_as_dicts(self, mock_agent):
        """测试收集工具调用记录"""
        from jarvis.jarvis_agent.task_analyzer import TaskAnalyzer

        analyzer = TaskAnalyzer(mock_agent)
        tool_calls = analyzer._collect_tool_calls_as_dicts()

        # 验证收集到了工具调用
        assert len(tool_calls) > 0
        assert any(tc.get("name") == "edit_file" for tc in tool_calls)

    def test_collect_tool_calls_deduplication(self, mock_agent):
        """测试工具调用去重"""
        from jarvis.jarvis_agent.task_analyzer import TaskAnalyzer

        # 添加重复的工具调用
        mock_agent.model._history.append(
            {
                "role": "assistant",
                "content": '<TOOL_CALL>{"name": "edit_file", "arguments": {}}</TOOL_CALL>',
            }
        )

        analyzer = TaskAnalyzer(mock_agent)
        tool_calls = analyzer._collect_tool_calls_as_dicts()

        # 验证去重
        names = [tc.get("name") for tc in tool_calls]
        assert names.count("edit_file") == 1

    def test_get_existing_methodologies(self, mock_agent):
        """测试获取现有方法论列表"""
        from jarvis.jarvis_agent.task_analyzer import TaskAnalyzer

        analyzer = TaskAnalyzer(mock_agent)

        with patch(
            "jarvis.jarvis_utils.methodology._load_all_methodologies"
        ) as mock_load:
            mock_load.return_value = [
                ("问题类型1", "内容1"),
                ("问题类型2", "内容2"),
            ]
            methodologies = analyzer._get_existing_methodologies()

        # 验证返回的方法论列表
        assert "问题类型1" in methodologies
        assert "问题类型2" in methodologies

    @patch("jarvis.jarvis_tools.methodology.MethodologyTool")
    def test_save_methodology_success(self, mock_tool_class, mock_agent):
        """测试保存方法论成功"""
        from jarvis.jarvis_agent.task_analyzer import TaskAnalyzer

        mock_tool = MagicMock()
        mock_tool.execute.return_value = {"success": True, "stdout": "保存成功"}
        mock_tool_class.return_value = mock_tool

        analyzer = TaskAnalyzer(mock_agent)
        result = {
            "problem_type": "用户登录功能开发",
            "content": "# 方法论内容",
            "quality_score": 80,
        }

        # 调用保存方法
        analyzer._save_methodology(result)

        # 验证调用了工具
        mock_tool.execute.assert_called_once()
        call_args = mock_tool.execute.call_args[0][0]
        assert call_args["operation"] == "add"
        assert call_args["problem_type"] == "用户登录功能开发"
        assert call_args["scope"] == "project"

    @patch("jarvis.jarvis_tools.methodology.MethodologyTool")
    def test_save_methodology_failure(self, mock_tool_class, mock_agent):
        """测试保存方法论失败"""
        from jarvis.jarvis_agent.task_analyzer import TaskAnalyzer

        mock_tool = MagicMock()
        mock_tool.execute.return_value = {"success": False, "stderr": "保存失败"}
        mock_tool_class.return_value = mock_tool

        analyzer = TaskAnalyzer(mock_agent)
        result = {
            "problem_type": "用户登录功能开发",
            "content": "# 方法论内容",
            "quality_score": 80,
        }

        # 调用保存方法（不应抛出异常）
        analyzer._save_methodology(result)

        # 验证调用了工具
        mock_tool.execute.assert_called_once()


class TestMethodologyExtractionIntegration:
    """方法论提取集成测试"""

    @pytest.fixture
    def mock_agent_with_history(self):
        """创建带有丰富历史记录的模拟Agent"""
        agent = MagicMock()
        agent.original_user_input = "实现一个完整的用户认证系统"
        agent.model = MagicMock()
        agent.model._history = [
            {"role": "user", "content": "实现一个完整的用户认证系统"},
            {
                "role": "assistant",
                "content": """我将按以下步骤实现：
1. 设计用户数据模型
2. 实现注册接口
3. 实现登录接口
4. 添加JWT令牌验证
5. 编写单元测试""",
            },
            {
                "role": "assistant",
                "content": '<TOOL_CALL>{"name": "read_code", "arguments": {}}</TOOL_CALL>',
            },
            {
                "role": "assistant",
                "content": '<TOOL_CALL>{"name": "edit_file", "arguments": {}}</TOOL_CALL>',
            },
            {
                "role": "assistant",
                "content": '<TOOL_CALL>{"name": "execute_script", "arguments": {}}</TOOL_CALL>',
            },
        ]
        agent.get_event_bus = MagicMock(return_value=MagicMock())
        agent.get_user_data = MagicMock(return_value=False)
        agent.use_analysis = False
        return agent

    def test_extract_and_save_methodology_flow(self, mock_agent_with_history):
        """测试完整的方法论提取和保存流程"""
        from jarvis.jarvis_agent.task_analyzer import TaskAnalyzer
        from jarvis.jarvis_utils.config import GLOBAL_CONFIG_DATA

        # 启用方法论自动提取
        GLOBAL_CONFIG_DATA["auto_methodology_extraction"] = True

        try:
            analyzer = TaskAnalyzer(mock_agent_with_history)

            # 收集执行步骤
            steps = analyzer._collect_execution_steps()
            # 步骤提取逻辑会过滤掉一些不符合条件的行
            # 只要能提取到一些步骤即可
            assert len(steps) >= 1  # 至少有1个步骤

            # 收集工具调用
            tool_calls = analyzer._collect_tool_calls_as_dicts()
            assert len(tool_calls) == 3  # 3个不同的工具

            # 验证工具名称
            tool_names = [tc.get("name") for tc in tool_calls]
            assert "read_code" in tool_names
            assert "edit_file" in tool_names
            assert "execute_script" in tool_names

        finally:
            # 清理
            del GLOBAL_CONFIG_DATA["auto_methodology_extraction"]
