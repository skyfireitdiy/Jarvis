# -*- coding: utf-8 -*-
"""pytest 配置文件"""

import sys
import os
import pytest
from unittest.mock import Mock

# 将项目根目录添加到 Python 路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


@pytest.fixture(scope="session")
def test_data_dir():
    """测试数据目录"""
    return os.path.join(os.path.dirname(__file__), "test_data")


@pytest.fixture(scope="function")
def temp_dir(tmp_path):
    """临时目录 fixture，每个测试函数都会获得一个新的临时目录"""
    return tmp_path


@pytest.fixture(autouse=True)
def reset_globals():
    """自动重置全局状态，防止测试之间的干扰"""

    yield

    # 测试后清理全局状态
    # 如果有需要重置的全局变量或单例，在这里处理


@pytest.fixture(scope="function")
def sample_code_file():
    """示例代码文件 fixture"""
    return """
def hello_world():
    print("Hello, World!")
    return True


class Calculator:
    def add(self, a, b):
        return a + b
"""


@pytest.fixture(scope="function")
def sample_project_structure():
    """示例项目结构 fixture"""
    return {
        "src": {"main.py": "print('Hello')", "utils.py": "def helper(): pass"},
        "tests": {"test_main.py": "def test_main(): pass"},
    }


@pytest.fixture(scope="function")
def mock_openai_response():
    """模拟OpenAI响应"""

    def _create_mock_response(content: str = "Test response"):
        mock = Mock()
        mock.choices = [Mock(message=Mock(content=content))]
        return mock

    return _create_mock_response


@pytest.fixture(scope="function")
def mock_anthropic_response():
    """模拟Anthropic响应"""

    def _create_mock_response(content: str = "Test response"):
        mock = Mock()
        mock.content = [Mock(type="text", text=content)]
        return mock

    return _create_mock_response


@pytest.fixture(scope="function")
def performance_thresholds():
    """性能阈值配置"""
    return {
        "code_generation_max_time": 5.0,  # 秒
        "code_analysis_max_time": 3.0,  # 秒
        "max_memory_mb": 100,  # MB
    }


@pytest.fixture(scope="function")
def regression_test_data():
    """回归测试数据"""
    return {
        "critical_functions": [
            "jarvis_agent",
            "code_agent",
            "git_utils",
        ],
        "api_endpoints": [
            "/api/agent/chat",
            "/api/code/analyze",
        ],
    }
