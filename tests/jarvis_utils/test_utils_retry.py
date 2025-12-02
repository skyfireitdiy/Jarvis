# -*- coding: utf-8 -*-
"""jarvis_utils.utils 重试函数单元测试"""

import pytest
from unittest.mock import patch

from jarvis.jarvis_utils.utils import while_success, while_true, _reset_retry_count


class TestWhileSuccess:
    """测试 while_success 函数"""

    def setup_method(self):
        """每个测试前重置重试计数器"""
        _reset_retry_count()

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

        result = while_success(test_func)
        assert result == "success"
        assert call_count[0] == 3

    def test_max_retries_exceeded(self):
        """测试超过最大重试次数"""

        def test_func():
            raise ValueError("Always fails")

        with pytest.raises(ValueError, match="Always fails"):
            while_success(test_func)

    @patch("jarvis.jarvis_utils.utils.time.sleep")
    def test_sleep_between_retries(self, mock_sleep):
        """测试重试之间会休眠，使用指数退避"""
        call_count = [0]

        def test_func():
            call_count[0] += 1
            if call_count[0] < 2:
                raise ValueError("Not ready")
            return "success"

        result = while_success(test_func)
        assert result == "success"
        # 应该休眠一次（第一次失败后），等待时间为 2^(1-1) = 1s
        assert mock_sleep.call_count == 1
        mock_sleep.assert_called_with(1.0)

    @patch("jarvis.jarvis_utils.utils.time.sleep")
    def test_exponential_backoff(self, mock_sleep):
        """测试指数退避机制"""
        call_count = [0]

        def test_func():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("Not ready")
            return "success"

        result = while_success(test_func)
        assert result == "success"
        # 第1次失败后等待 2^(1-1) = 1s
        # 第2次失败后等待 2^(2-1) = 2s
        assert mock_sleep.call_count == 2
        assert mock_sleep.call_args_list[0][0][0] == 1.0  # 第一次等待1s
        assert mock_sleep.call_args_list[1][0][0] == 2.0  # 第二次等待2s


class TestWhileTrue:
    """测试 while_true 函数"""

    def setup_method(self):
        """每个测试前重置重试计数器"""
        _reset_retry_count()

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

        result = while_true(test_func)
        assert result is True
        assert call_count[0] == 3

    def test_false_after_max_retries(self):
        """测试超过最大重试次数后返回 False"""

        def test_func():
            return False

        result = while_true(test_func)
        assert result is False

    @patch("jarvis.jarvis_utils.utils.time.sleep")
    def test_sleep_between_retries(self, mock_sleep):
        """测试重试之间会休眠，使用指数退避"""
        call_count = [0]

        def test_func():
            call_count[0] += 1
            return call_count[0] >= 2

        result = while_true(test_func)
        assert result is True
        # 应该休眠一次（第一次返回False后），等待时间为 2^(1-1) = 1s
        assert mock_sleep.call_count == 1
        mock_sleep.assert_called_with(1.0)

    def test_exception_propagates(self):
        """测试异常会传播（不捕获）"""

        def test_func():
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            while_true(test_func)

    @patch("jarvis.jarvis_utils.utils.time.sleep")
    def test_exponential_backoff(self, mock_sleep):
        """测试指数退避机制"""
        call_count = [0]

        def test_func():
            call_count[0] += 1
            return call_count[0] >= 3

        result = while_true(test_func)
        assert result is True
        # 第1次返回False后等待 2^(1-1) = 1s
        # 第2次返回False后等待 2^(2-1) = 2s
        assert mock_sleep.call_count == 2
        assert mock_sleep.call_args_list[0][0][0] == 1.0  # 第一次等待1s
        assert mock_sleep.call_args_list[1][0][0] == 2.0  # 第二次等待2s


class TestSharedRetryCounter:
    """测试两个函数共享重试计数器"""

    def setup_method(self):
        """每个测试前重置重试计数器"""
        _reset_retry_count()

    def test_shared_counter_between_functions(self):
        """测试 while_true 和 while_success 共享重试计数器"""
        call_count = [0]

        def inner_func():
            call_count[0] += 1
            if call_count[0] < 2:
                raise ValueError("Not ready")
            return "success"

        def outer_func():
            # while_success 失败2次后，计数器为2
            # while_true 再失败时，计数器会继续增加
            result = while_success(inner_func)
            return result is not None

        # 第一次调用 while_success 会失败1次，然后成功
        # 计数器会被重置
        result = while_true(outer_func)
        assert result is True
