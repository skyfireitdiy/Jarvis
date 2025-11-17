# -*- coding: utf-8 -*-
"""tool_executor 单元测试"""
from unittest.mock import Mock, patch, call
import pytest

from jarvis.jarvis_agent.tool_executor import execute_tool_call


class TestToolExecutor:
    """tool_executor 函数的测试"""
    
    @pytest.fixture
    def mock_agent(self):
        """创建模拟的 Agent 对象"""
        agent = Mock()
        agent.execute_tool_confirm = False  # 默认不需要确认
        agent.output_handler = []
        return agent
    
    @pytest.fixture
    def mock_handler(self):
        """创建模拟的输出处理器"""
        handler = Mock()
        handler.name.return_value = "MockTool"
        handler.can_handle.return_value = True
        handler.handle.return_value = (True, "Success result")
        return handler
    
    def test_no_matching_handler(self, mock_agent):
        """测试没有匹配的处理器"""
        # 设置一个不匹配的处理器
        handler = Mock()
        handler.can_handle.return_value = False
        mock_agent.output_handler = [handler]
        
        result = execute_tool_call("some command", mock_agent)
        
        assert result == (False, "")
        handler.can_handle.assert_called_once_with("some command")
    
    def test_single_handler_execution(self, mock_agent, mock_handler):
        """测试单个处理器的执行"""
        mock_agent.output_handler = [mock_handler]
        
        with patch('builtins.print') as mock_print:
            result = execute_tool_call("test command", mock_agent)
        
        # 验证结果
        assert result == (True, "Success result")
        
        # 验证调用
        mock_handler.can_handle.assert_called_once_with("test command")
        mock_handler.handle.assert_called_once_with("test command", mock_agent)
        
        # 验证打印输出
        mock_print.assert_has_calls([
            call("🔧 正在执行MockTool..."),
            call("✅ MockTool执行完成")
        ])
    
    @patch('jarvis.jarvis_agent.tool_executor.print')
    def test_multiple_handlers_error(self, mock_print, mock_agent):
        """测试多个处理器匹配时的错误"""
        # 创建两个都匹配的处理器
        handler1 = Mock()
        handler1.can_handle.return_value = True
        handler1.name.return_value = "Tool1"
        
        handler2 = Mock()
        handler2.can_handle.return_value = True
        handler2.name.return_value = "Tool2"
        
        mock_agent.output_handler = [handler1, handler2]
        
        result = execute_tool_call("test command", mock_agent)
        
        # 验证结果
        assert result[0] is False
        assert "检测到多个操作" in result[1]
        assert "Tool1" in result[1]
        assert "Tool2" in result[1]
        
        # 验证警告输出
        mock_print.assert_called_once()
        args = mock_print.call_args[0]
        assert "检测到多个操作" in args[0]
    
    @patch('jarvis.jarvis_agent.tool_executor.user_confirm')
    def test_execution_with_confirmation_yes(self, mock_confirm, mock_agent, mock_handler):
        """测试需要确认且用户确认的情况"""
        mock_agent.execute_tool_confirm = True
        mock_agent.output_handler = [mock_handler]
        mock_confirm.return_value = True
        
        with patch('builtins.print'):
            result = execute_tool_call("test command", mock_agent)
        
        # 验证结果
        assert result == (True, "Success result")
        
        # 验证确认调用
        mock_confirm.assert_called_once_with("需要执行MockTool确认执行？", True)
        
        # 验证工具执行
        mock_handler.handle.assert_called_once()
    
    @patch('jarvis.jarvis_agent.tool_executor.user_confirm')
    def test_execution_with_confirmation_no(self, mock_confirm, mock_agent, mock_handler):
        """测试需要确认但用户拒绝的情况"""
        mock_agent.execute_tool_confirm = True
        mock_agent.output_handler = [mock_handler]
        mock_confirm.return_value = False
        
        result = execute_tool_call("test command", mock_agent)
        
        # 验证结果
        assert result == (False, "")
        
        # 验证确认调用
        mock_confirm.assert_called_once()
        
        # 验证工具未执行
        mock_handler.handle.assert_not_called()
    
    def test_handler_execution_failure(self, mock_agent, mock_handler):
        """测试处理器执行失败的情况"""
        mock_agent.output_handler = [mock_handler]
        mock_handler.handle.return_value = (False, "Execution failed")
        
        with patch('builtins.print'):
            result = execute_tool_call("test command", mock_agent)
        
        # 验证结果
        assert result == (False, "Execution failed")
    
    def test_mixed_handlers_only_one_matches(self, mock_agent):
        """测试多个处理器但只有一个匹配的情况"""
        # 创建三个处理器，只有一个匹配
        handler1 = Mock()
        handler1.can_handle.return_value = False
        
        handler2 = Mock()
        handler2.can_handle.return_value = True
        handler2.name.return_value = "MatchingTool"
        handler2.handle.return_value = (True, "Result")
        
        handler3 = Mock()
        handler3.can_handle.return_value = False
        
        mock_agent.output_handler = [handler1, handler2, handler3]
        
        with patch('builtins.print'):
            result = execute_tool_call("test command", mock_agent)
        
        # 验证结果
        assert result == (True, "Result")
        
        # 验证所有处理器都被检查
        handler1.can_handle.assert_called_once()
        handler2.can_handle.assert_called_once()
        handler3.can_handle.assert_called_once()
        
        # 验证只有匹配的处理器被执行
        handler2.handle.assert_called_once()
        handler1.handle.assert_not_called()
        handler3.handle.assert_not_called()
