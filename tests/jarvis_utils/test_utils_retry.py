# -*- coding: utf-8 -*-
"""jarvis_utils.utils 重试函数单元测试"""

import pytest
from unittest.mock import patch

from jarvis.jarvis_utils.utils import while_success, while_true


class TestWhileSuccess:
    """测试 while_success 函数"""

    def test_success_on_first_try(self):
        """测试第一次就成功"""
        def test_func():
            return "success"
        
        result = while_success(test_func)
        assert result == "success"

    def test_success_after_retries(self):
        """测试重试后成功"""
        call_count = [0]
        
        def test_func():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("Not ready yet")
            return "success"
        
        result = while_success(test_func, max_retries=5)
        assert result == "success"
        assert call_count[0] == 3

    def test_max_retries_exceeded(self):
        """测试超过最大重试次数"""
        def test_func():
            raise ValueError("Always fails")
        
        result = while_success(test_func, max_retries=3)
        assert result is None

    @patch("jarvis.jarvis_utils.utils.time.sleep")
    def test_sleep_between_retries(self, mock_sleep):
        """测试重试之间会休眠"""
        call_count = [0]
        
        def test_func():
            call_count[0] += 1
            if call_count[0] < 2:
                raise ValueError("Not ready")
            return "success"
        
        result = while_success(test_func, sleep_time=0.5, max_retries=3)
        assert result == "success"
        # 应该休眠一次（第一次失败后）
        assert mock_sleep.call_count == 1
        mock_sleep.assert_called_with(0.5)

    def test_custom_sleep_time(self):
        """测试自定义休眠时间"""
        call_count = [0]
        
        def test_func():
            call_count[0] += 1
            if call_count[0] < 2:
                raise ValueError("Not ready")
            return "success"
        
        with patch("jarvis.jarvis_utils.utils.time.sleep") as mock_sleep:
            result = while_success(test_func, sleep_time=1.0, max_retries=3)
            assert result == "success"
            mock_sleep.assert_called_with(1.0)

    def test_return_none_on_failure(self):
        """测试失败时返回 None"""
        def test_func():
            raise RuntimeError("Always fails")
        
        result = while_success(test_func, max_retries=2)
        assert result is None


class TestWhileTrue:
    """测试 while_true 函数"""

    def test_true_on_first_try(self):
        """测试第一次就返回 True"""
        def test_func():
            return True
        
        result = while_true(test_func)
        assert result is True

    def test_true_after_retries(self):
        """测试重试后返回 True"""
        call_count = [0]
        
        def test_func():
            call_count[0] += 1
            return call_count[0] >= 3
        
        result = while_true(test_func, max_retries=5)
        assert result is True
        assert call_count[0] == 3

    def test_false_after_max_retries(self):
        """测试超过最大重试次数后返回 False"""
        def test_func():
            return False
        
        result = while_true(test_func, max_retries=3)
        assert result is False

    @patch("jarvis.jarvis_utils.utils.time.sleep")
    def test_sleep_between_retries(self, mock_sleep):
        """测试重试之间会休眠"""
        call_count = [0]
        
        def test_func():
            call_count[0] += 1
            return call_count[0] >= 2
        
        result = while_true(test_func, sleep_time=0.5, max_retries=3)
        assert result is True
        # 应该休眠一次（第一次返回False后）
        assert mock_sleep.call_count == 1
        mock_sleep.assert_called_with(0.5)

    def test_exception_propagates(self):
        """测试异常会传播（不捕获）"""
        def test_func():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError, match="Test error"):
            while_true(test_func, max_retries=3)

    def test_custom_sleep_time(self):
        """测试自定义休眠时间"""
        call_count = [0]
        
        def test_func():
            call_count[0] += 1
            return call_count[0] >= 2
        
        with patch("jarvis.jarvis_utils.utils.time.sleep") as mock_sleep:
            result = while_true(test_func, sleep_time=2.0, max_retries=3)
            assert result is True
            mock_sleep.assert_called_with(2.0)

