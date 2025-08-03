# -*- coding: utf-8 -*-
"""prompt_builder 单元测试"""
from unittest.mock import Mock
import pytest

from jarvis.jarvis_agent.prompt_builder import build_action_prompt


class TestPromptBuilder:
    """prompt_builder 函数的测试"""
    
    @pytest.fixture
    def mock_handler(self):
        """创建模拟的输出处理器"""
        handler = Mock()
        handler.name.return_value = "TestTool"
        handler.prompt.return_value = """This is a test tool.
It does something useful.

Parameters:
- param1: description
- param2: description"""
        return handler
    
    def test_build_action_prompt_empty_handlers(self):
        """测试空的处理器列表"""
        result = build_action_prompt([])
        
        # 验证基本结构
        assert "<actions>" in result
        assert "# 🧰 可用操作" in result
        assert "<overview>" in result
        assert "## Action List" in result
        assert "[]" in result  # 空列表
        assert "</overview>" in result
        assert "<details>" in result
        assert "# 📝 Action Details" in result
        assert "</details>" in result
        assert "<rules>" in result
        assert "# ❗ 重要操作使用规则" in result
        assert "</rules>" in result
        assert "</actions>" in result
    
    def test_build_action_prompt_single_handler(self, mock_handler):
        """测试单个处理器"""
        result = build_action_prompt([mock_handler])
        
        # 验证处理器名称在概览中
        assert "[TestTool]" in result
        
        # 验证处理器详情
        assert "## TestTool" in result
        assert "This is a test tool." in result
        assert "It does something useful." in result
        assert "Parameters:" in result
        assert "- param1: description" in result
        assert "- param2: description" in result
        
        # 验证缩进（每行前面有3个空格）
        assert "   This is a test tool." in result
        assert "   It does something useful." in result
    
    def test_build_action_prompt_multiple_handlers(self):
        """测试多个处理器"""
        # 创建三个模拟处理器
        handler1 = Mock()
        handler1.name.return_value = "Tool1"
        handler1.prompt.return_value = "Tool 1 description"
        
        handler2 = Mock()
        handler2.name.return_value = "Tool2"
        handler2.prompt.return_value = "Tool 2 description"
        
        handler3 = Mock()
        handler3.name.return_value = "Tool3"
        handler3.prompt.return_value = "Tool 3 description"
        
        handlers = [handler1, handler2, handler3]
        result = build_action_prompt(handlers)
        
        # 验证概览列表
        assert "[Tool1, Tool2, Tool3]" in result
        
        # 验证每个工具的详情
        assert "## Tool1" in result
        assert "   Tool 1 description" in result
        assert "## Tool2" in result
        assert "   Tool 2 description" in result
        assert "## Tool3" in result
        assert "   Tool 3 description" in result
    
    def test_build_action_prompt_with_empty_lines(self):
        """测试处理器描述中包含空行的情况"""
        handler = Mock()
        handler.name.return_value = "EmptyLineTool"
        handler.prompt.return_value = """First line

Third line

Fifth line"""
        
        result = build_action_prompt([handler])
        
        # 验证空行被保留但不添加缩进
        lines = result.split('\n')
        
        # 找到工具描述的部分
        tool_section_start = False
        for i, line in enumerate(lines):
            if "## EmptyLineTool" in line:
                tool_section_start = True
                # 检查接下来的几行
                assert lines[i+1].strip() == "First line"
                assert lines[i+2].strip() == ""  # 空行
                assert lines[i+3].strip() == "Third line"
                assert lines[i+4].strip() == ""  # 空行
                assert lines[i+5].strip() == "Fifth line"
                break
        
        assert tool_section_start, "Tool section not found"
    
    def test_build_action_prompt_with_leading_trailing_whitespace(self):
        """测试处理器描述带有前后空白的情况"""
        handler = Mock()
        handler.name.return_value = "WhitespaceTool"
        handler.prompt.return_value = "\n\n  Tool description  \n\n"
        
        result = build_action_prompt([handler])
        
        # 验证前后空白被去除
        assert "## WhitespaceTool" in result
        assert "   Tool description" in result
        # 确保没有多余的空行
        assert "\n\n\n" not in result
    
    def test_build_action_prompt_rules_content(self):
        """测试规则部分的内容"""
        result = build_action_prompt([])
        
        # 验证所有规则都存在
        assert "1. 一次对话只能使用一个操作，否则会出错" in result
        assert "2. 严格按照每个操作的格式执行" in result
        assert "3. 等待操作结果后再进行下一个操作" in result
        assert "4. 处理完结果后再调用新的操作" in result
        assert "5. 如果对操作使用不清楚，请请求帮助" in result
