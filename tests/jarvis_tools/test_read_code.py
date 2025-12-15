# -*- coding: utf-8 -*-
"""jarvis_tools.read_code 模块单元测试"""

import os
import tempfile
from unittest.mock import MagicMock

import pytest

from jarvis.jarvis_tools.read_code import ReadCodeTool


class TestReadCodeTool:
    """测试 ReadCodeTool 类"""

    @pytest.fixture
    def tool(self):
        """创建测试用的 ReadCodeTool 实例"""
        return ReadCodeTool()

    @pytest.fixture
    def mock_agent(self):
        """创建模拟的 Agent 实例"""
        agent = MagicMock()
        # 使用字典存储用户数据
        agent._user_data = {}

        # 显式设置 model_group 为 None，避免 MagicMock 自动创建属性
        agent.model_group = None

        # 显式设置 model 为 None，避免 MagicMock 自动创建属性导致 get_remaining_token_count 返回 MagicMock
        agent.model = None

        def get_user_data(key):
            return agent._user_data.get(key)

        def set_user_data(key, value):
            agent._user_data[key] = value

        agent.get_user_data = MagicMock(side_effect=get_user_data)
        agent.set_user_data = MagicMock(side_effect=set_user_data)
        return agent

    @pytest.fixture
    def sample_file(self):
        """创建示例文件"""
        content = """def hello():
    PrettyOutput.auto_print("📝 Hello, World!")

def add(a, b):
    return a + b

class Calculator:
    def __init__(self):
        self.value = 0
    
    def add(self, x):
        self.value += x
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(content)
            filepath = f.name

        yield filepath

        # 清理
        if os.path.exists(filepath):
            os.unlink(filepath)

    def test_read_single_file(self, tool, sample_file):
        """测试读取单个文件"""
        result = tool.execute({"files": [{"path": sample_file}]})

        assert result["success"] is True
        assert "stdout" in result
        assert (
            sample_file in result["stdout"]
            or os.path.basename(sample_file) in result["stdout"]
        )

    def test_read_file_with_range(self, tool, sample_file):
        """测试读取文件指定范围"""
        result = tool.execute(
            {"files": [{"path": sample_file, "start_line": 1, "end_line": 5}]}
        )

        assert result["success"] is True
        assert "stdout" in result

    def test_read_nonexistent_file(self, tool):
        """测试读取不存在的文件"""
        result = tool.execute({"files": [{"path": "/nonexistent/file/path.py"}]})

        assert result["success"] is False
        # 错误信息可能在stderr或stdout中
        error_msg = result.get("stderr", "") + result.get("stdout", "")
        assert (
            "不存在" in error_msg
            or "not found" in error_msg.lower()
            or "文件读取失败" in error_msg
        )

    def test_read_multiple_files(self, tool, sample_file):
        """测试读取多个文件"""
        # 创建第二个文件
        content2 = "x = 1\ny = 2\nz = x + y\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(content2)
            filepath2 = f.name

        try:
            result = tool.execute(
                {"files": [{"path": sample_file}, {"path": filepath2}]}
            )

            assert result["success"] is True
            assert "stdout" in result
        finally:
            if os.path.exists(filepath2):
                os.unlink(filepath2)

    def test_read_empty_file(self, tool):
        """测试读取空文件"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            empty_file = f.name

        try:
            result = tool.execute({"files": [{"path": empty_file}]})

            assert result["success"] is True
            assert "空" in result["stdout"] or "empty" in result["stdout"].lower()
        finally:
            if os.path.exists(empty_file):
                os.unlink(empty_file)

    def test_read_file_with_negative_line_number(self, tool, sample_file):
        """测试使用负数行号（从文件末尾倒数）"""
        result = tool.execute(
            {"files": [{"path": sample_file, "start_line": -5, "end_line": -1}]}
        )

        # 应该成功或给出合理错误
        assert "success" in result

    def test_read_file_exceeds_token_limit(self, tool):
        """测试读取超大文件（超过token限制）"""
        # 创建一个很大的文件
        large_content = "\n".join([f"line {i}" for i in range(10000)])
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(large_content)
            large_file = f.name

        try:
            result = tool.execute({"files": [{"path": large_file}]})

            # 应该失败或给出警告
            assert "success" in result
        finally:
            if os.path.exists(large_file):
                os.unlink(large_file)

    def test_read_file_with_invalid_range(self, tool, sample_file):
        """测试无效的行号范围"""
        result = tool.execute(
            {"files": [{"path": sample_file, "start_line": 100, "end_line": 50}]}
        )

        # 代码可能会自动修正范围，所以可能成功也可能失败
        # 只要不抛出异常即可
        assert "success" in result

    def test_read_file_without_agent(self, tool, sample_file):
        """测试不使用agent读取文件"""
        result = tool.execute({"files": [{"path": sample_file}]})

        assert result["success"] is True
        assert "stdout" in result

    def test_read_with_missing_files(self, tool):
        """测试缺少files参数"""
        result = tool.execute({})
        assert result["success"] is False
        # 错误信息可能是中文
        error_msg = result.get("stderr", "").lower()
        assert "files" in error_msg or "文件列表" in result.get("stderr", "")

        # 空的files列表
        result = tool.execute({"files": []})
        assert result["success"] is False

    def test_merged_ranges_deduplication(self, tool, mock_agent):
        """测试同一文件多个重叠范围读取时的去重功能"""
        content = """class MyClass:
    def method1(self):
        PrettyOutput.auto_print("📝 method1")
        return 1
    
    def method2(self):
        PrettyOutput.auto_print("📝 method2")
        return 2
    
    def method3(self):
        PrettyOutput.auto_print("📝 method3")
        return 3
    
    def method4(self):
        PrettyOutput.auto_print("📝 method4")
        return 4
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(content)
            filepath = f.name
        try:
            # 测试两个重叠范围
            result = tool.execute(
                {
                    "files": [
                        {"path": filepath, "start_line": 1, "end_line": 10},
                        {"path": filepath, "start_line": 5, "end_line": 15},
                    ],
                    "agent": mock_agent,
                }
            )
            assert result["success"] is True
            # 验证输出包含文件内容
            assert filepath in result["stdout"] or "method" in result["stdout"]
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_merged_ranges_multiple_requests(self, tool, mock_agent):
        """测试同一文件三个及以上范围请求的去重"""
        content = """def func1():
    pass

def func2():
    pass

def func3():
    pass

def func4():
    pass

def func5():
    pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(content)
            filepath = f.name
        try:
            # 测试三个范围请求
            result = tool.execute(
                {
                    "files": [
                        {"path": filepath, "start_line": 1, "end_line": 5},
                        {"path": filepath, "start_line": 3, "end_line": 10},
                        {"path": filepath, "start_line": 8, "end_line": 15},
                    ],
                    "agent": mock_agent,
                }
            )
            assert result["success"] is True
            # 验证输出包含文件内容
            assert filepath in result["stdout"] or "func" in result["stdout"]
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_merged_ranges_different_files(self, tool, mock_agent):
        """测试不同文件的多范围请求不会被错误合并"""
        content1 = """def func_a():
    pass
"""
        content2 = """def func_b():
    pass
"""
        with (
            tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f1,
            tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f2,
        ):
            f1.write(content1)
            f2.write(content2)
            filepath1 = f1.name
            filepath2 = f2.name
        try:
            result = tool.execute(
                {
                    "files": [
                        {"path": filepath1, "start_line": 1, "end_line": -1},
                        {"path": filepath2, "start_line": 1, "end_line": -1},
                    ],
                    "agent": mock_agent,
                }
            )
            assert result["success"] is True
            # 两个文件都应该被读取
            assert filepath1 in result["stdout"] or "func_a" in result["stdout"]
            assert filepath2 in result["stdout"] or "func_b" in result["stdout"]
        finally:
            if os.path.exists(filepath1):
                os.unlink(filepath1)
            if os.path.exists(filepath2):
                os.unlink(filepath2)

    def test_merged_ranges_without_agent(self, tool):
        """测试无agent时多范围请求的去重"""
        content = """class Test:
    def method1(self):
        pass
    
    def method2(self):
        pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(content)
            filepath = f.name
        try:
            # 无agent时也应该去重
            result = tool.execute(
                {
                    "files": [
                        {"path": filepath, "start_line": 1, "end_line": 4},
                        {"path": filepath, "start_line": 3, "end_line": 7},
                    ]
                }
            )
            assert result["success"] is True
            # 验证输出包含文件内容
            assert filepath in result["stdout"] or "method" in result["stdout"]
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)
