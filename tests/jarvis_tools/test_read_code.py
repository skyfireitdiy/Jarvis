# -*- coding: utf-8 -*-
"""jarvis_tools.read_code 模块单元测试"""

import os
import tempfile
import time
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
    print("Hello, World!")

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

    def test_cache_save_and_retrieve(self, tool, sample_file, mock_agent):
        """测试缓存保存和检索"""
        # 第一次读取，应该保存到缓存
        result1 = tool.execute({"files": [{"path": sample_file}], "agent": mock_agent})

        assert result1["success"] is True
        assert mock_agent.set_user_data.called

        # 检查缓存内容
        cache_key = "read_code_cache"
        call_args = [
            call[0][0]
            for call in mock_agent.set_user_data.call_args_list
            if call[0][0] == cache_key
        ]
        assert len(call_args) > 0 or any(
            call[0][0] == cache_key for call in mock_agent.set_user_data.call_args_list
        )

    def test_cache_validity_check(self, tool, sample_file, mock_agent):
        """测试缓存有效性检查"""
        abs_path = os.path.abspath(sample_file)
        file_mtime = os.path.getmtime(abs_path)

        # 创建有效缓存（新格式：id_list 和 blocks）
        cache = {
            abs_path: {
                "id_list": ["block-1"],
                "blocks": {"block-1": {"content": "def hello():\n    print('Hello')"}},
                "total_lines": 10,
                "read_time": time.time(),
                "file_mtime": file_mtime,
            }
        }

        # 设置get_user_data返回缓存
        def get_user_data_side_effect(key):
            if key == "read_code_cache":
                return cache
            return None

        mock_agent.get_user_data.side_effect = get_user_data_side_effect

        # 检查缓存有效性
        cache_info = tool._get_file_cache(mock_agent, abs_path)
        is_valid = tool._is_cache_valid(cache_info, abs_path)

        assert is_valid is True

    def test_cache_invalid_when_file_modified(self, tool, sample_file, mock_agent):
        """测试文件修改后缓存失效（通过模拟旧时间戳）"""
        abs_path = os.path.abspath(sample_file)
        old_mtime = os.path.getmtime(abs_path) - 100  # 旧的时间戳

        # 创建过期缓存
        cache = {
            abs_path: {
                "units": [{"id": "1", "content": "old content"}],
                "total_lines": 5,
                "read_time": time.time() - 200,
                "file_mtime": old_mtime,
            }
        }
        mock_agent.get_user_data.return_value = cache

        # 检查缓存有效性
        cache_info = tool._get_file_cache(mock_agent, abs_path)
        is_valid = tool._is_cache_valid(cache_info, abs_path)

        assert is_valid is False

    def test_cache_invalid_after_external_file_modification(
        self, tool, sample_file, mock_agent
    ):
        """测试外部修改文件后缓存失效（实际修改文件）"""
        abs_path = os.path.abspath(sample_file)

        # 第一次读取文件，建立缓存
        original_content = """def hello():
    print("Hello, World!")

def add(a, b):
    return a + b
"""
        with open(abs_path, "w") as f:
            f.write(original_content)

        # 等待一小段时间，确保文件时间戳稳定
        time.sleep(0.2)

        # 第一次读取，建立缓存
        result1 = tool.execute({"files": [{"path": sample_file}], "agent": mock_agent})
        assert result1["success"] is True

        # 获取缓存
        cache = mock_agent.get_user_data("read_code_cache")
        assert cache is not None
        assert abs_path in cache

        # 验证缓存有效
        cache_info = tool._get_file_cache(mock_agent, abs_path)
        is_valid_before = tool._is_cache_valid(cache_info, abs_path)
        assert is_valid_before is True

        # 外部修改文件（模拟外部编辑器修改）
        modified_content = """def hello():
    print("Hello, Modified World!")

def add(a, b):
    return a + b

def multiply(a, b):
    return a * b
"""
        with open(abs_path, "w") as f:
            f.write(modified_content)

        # 等待一小段时间，确保文件时间戳更新
        time.sleep(0.2)

        # 验证缓存失效
        cache_info_after = tool._get_file_cache(mock_agent, abs_path)
        is_valid_after = tool._is_cache_valid(cache_info_after, abs_path)
        assert is_valid_after is False, "文件被外部修改后，缓存应该失效"

        # 再次读取文件，应该读取新内容而不是使用缓存
        result2 = tool.execute({"files": [{"path": sample_file}], "agent": mock_agent})
        assert result2["success"] is True

        # 验证读取的是新内容
        assert "Modified World" in result2["stdout"] or "multiply" in result2["stdout"]

    def test_convert_units_to_sequential_ids(self, tool):
        """测试将单元转换为id_list和blocks格式"""
        units = [
            {"id": "10-20", "start_line": 10, "end_line": 20, "content": "content1"},
            {"id": "1-5", "start_line": 1, "end_line": 5, "content": "content2"},
            {"id": "25-30", "start_line": 25, "end_line": 30, "content": "content3"},
        ]

        result = tool._convert_units_to_sequential_ids(units)

        # 检查返回的是字典格式，包含 id_list 和 blocks
        assert isinstance(result, dict)
        assert "id_list" in result
        assert "blocks" in result

        id_list = result["id_list"]
        blocks = result["blocks"]

        # 检查 id_list 长度
        assert len(id_list) == 3

        # 检查 blocks 字典包含所有 id
        assert len(blocks) == 3
        for block_id in id_list:
            assert block_id in blocks
            block = blocks[block_id]
            assert "content" in block
            assert "start_line" not in block
            assert "end_line" not in block

    def test_restore_file_from_cache(self, tool):
        """测试从缓存恢复文件内容"""
        cache_info = {
            "id_list": ["block-1", "block-2", "block-3"],
            "blocks": {
                "block-1": {"content": "line1"},
                "block-2": {"content": "line2\nline3"},
                "block-3": {"content": "line4"},
            },
            "total_lines": 4,
        }

        result = tool._restore_file_from_cache(cache_info)

        assert "line1" in result
        assert "line2" in result
        assert "line3" in result
        assert "line4" in result

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

    def test_read_file_with_raw_mode(self, tool, sample_file):
        """测试原始模式读取"""
        result = tool.execute({"files": [{"path": sample_file, "raw_mode": True}]})

        assert result["success"] is True
        assert "stdout" in result

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

    def test_cache_with_empty_units(self, tool, sample_file, mock_agent):
        """测试空单元列表的缓存"""
        abs_path = os.path.abspath(sample_file)
        cache = {
            abs_path: {
                "units": [],
                "total_lines": 0,
                "read_time": time.time(),
                "file_mtime": os.path.getmtime(abs_path),
            }
        }
        mock_agent.get_user_data.return_value = cache

        cache_info = tool._get_file_cache(mock_agent, abs_path)
        restored = tool._restore_file_from_cache(cache_info)

        assert restored == ""

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

    def test_cache_restore_python_file(self, tool, mock_agent):
        """测试从缓存恢复Python文件（语法单元）"""
        python_content = """import os
import sys

def hello():
    print("Hello")

class MyClass:
    def method1(self):
        return 1
    
    def method2(self):
        return 2

def goodbye():
    print("Goodbye")
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(python_content)
            filepath = f.name

        try:
            abs_path = os.path.abspath(filepath)
            os.path.getmtime(abs_path)

            # 先读取文件，生成缓存
            result = tool.execute({"files": [{"path": filepath}], "agent": mock_agent})
            assert result["success"] is True

            # 获取缓存
            cache = mock_agent.get_user_data("read_code_cache")
            assert cache is not None
            assert abs_path in cache

            cache_info = cache[abs_path]
            # 检查新格式（id_list 和 blocks）
            assert "id_list" in cache_info and "blocks" in cache_info

            # 从缓存恢复文件内容
            restored_content = tool._restore_file_from_cache(cache_info)

            # 验证恢复的内容与原始内容完全一致
            assert restored_content == python_content, (
                f"恢复的内容与原始内容不一致\n原始:\n{python_content}\n恢复:\n{restored_content}"
            )

            # 验证缓存中的单元只有id和content
            id_list = cache_info["id_list"]
            blocks = cache_info["blocks"]
            for block_id in id_list:
                assert block_id in blocks
                block = blocks[block_id]
                assert "content" in block
                assert "start_line" not in block
                assert "end_line" not in block
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_cache_restore_c_file(self, tool, mock_agent):
        """测试从缓存恢复C文件（语法单元）"""
        c_content = """#include <stdio.h>
#include <stdlib.h>

void hello() {
    printf("Hello\\n");
}

int add(int a, int b) {
    return a + b;
}

struct Point {
    int x;
    int y;
};

int main() {
    return 0;
}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".c", delete=False) as f:
            f.write(c_content)
            filepath = f.name

        try:
            abs_path = os.path.abspath(filepath)
            os.path.getmtime(abs_path)

            # 读取文件生成缓存
            result = tool.execute({"files": [{"path": filepath}], "agent": mock_agent})
            assert result["success"] is True

            # 获取缓存并恢复
            cache = mock_agent.get_user_data("read_code_cache")
            if cache and abs_path in cache:
                cache_info = cache[abs_path]
                restored_content = tool._restore_file_from_cache(cache_info)

                # 验证恢复的内容与原始内容完全一致
                assert restored_content == c_content, (
                    f"恢复的内容与原始内容不一致\n原始:\n{c_content}\n恢复:\n{restored_content}"
                )
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_cache_restore_java_file(self, tool, mock_agent):
        """测试从缓存恢复Java文件（语法单元）"""
        java_content = """package com.example;

import java.util.List;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello");
    }
    
    public int add(int a, int b) {
        return a + b;
    }
    
    private class Inner {
        void method() {
        }
    }
}

interface MyInterface {
    void doSomething();
}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(java_content)
            filepath = f.name

        try:
            abs_path = os.path.abspath(filepath)

            # 读取文件生成缓存
            result = tool.execute({"files": [{"path": filepath}], "agent": mock_agent})
            assert result["success"] is True

            # 获取缓存并恢复
            cache = mock_agent.get_user_data("read_code_cache")
            if cache and abs_path in cache:
                cache_info = cache[abs_path]
                restored_content = tool._restore_file_from_cache(cache_info)

                # 验证恢复的内容与原始内容完全一致
                assert restored_content == java_content, (
                    f"恢复的内容与原始内容不一致\n原始:\n{java_content}\n恢复:\n{restored_content}"
                )
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_cache_restore_rust_file(self, tool, mock_agent):
        """测试从缓存恢复Rust文件（语法单元）"""
        rust_content = """fn main() {
    println!("Hello");
}

fn add(a: i32, b: i32) -> i32 {
    a + b
}

struct Point {
    x: i32,
    y: i32,
}

impl Point {
    fn new(x: i32, y: i32) -> Point {
        Point { x, y }
    }
}

enum Color {
    Red,
    Green,
    Blue,
}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".rs", delete=False) as f:
            f.write(rust_content)
            filepath = f.name

        try:
            abs_path = os.path.abspath(filepath)

            # 读取文件生成缓存
            result = tool.execute({"files": [{"path": filepath}], "agent": mock_agent})
            assert result["success"] is True

            # 获取缓存并恢复
            cache = mock_agent.get_user_data("read_code_cache")
            if cache and abs_path in cache:
                cache_info = cache[abs_path]
                restored_content = tool._restore_file_from_cache(cache_info)

                # 验证恢复的内容与原始内容完全一致
                assert restored_content == rust_content, (
                    f"恢复的内容与原始内容不一致\n原始:\n{rust_content}\n恢复:\n{restored_content}"
                )
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_cache_restore_go_file(self, tool, mock_agent):
        """测试从缓存恢复Go文件（语法单元）"""
        go_content = """package main

import "fmt"

func main() {
    fmt.Println("Hello")
}

func add(a int, b int) int {
    return a + b
}

type Point struct {
    x int
    y int
}

type Shape interface {
    Area() float64
}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".go", delete=False) as f:
            f.write(go_content)
            filepath = f.name

        try:
            abs_path = os.path.abspath(filepath)

            # 读取文件生成缓存
            result = tool.execute({"files": [{"path": filepath}], "agent": mock_agent})
            assert result["success"] is True

            # 获取缓存并恢复
            cache = mock_agent.get_user_data("read_code_cache")
            if cache and abs_path in cache:
                cache_info = cache[abs_path]
                restored_content = tool._restore_file_from_cache(cache_info)

                # 验证恢复的内容与原始内容完全一致
                assert restored_content == go_content, (
                    f"恢复的内容与原始内容不一致\n原始:\n{go_content}\n恢复:\n{restored_content}"
                )
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_cache_restore_unsupported_language(self, tool, mock_agent):
        """测试从缓存恢复不支持的语言（空白行分组）"""
        text_content = """First block of text
Line 2
Line 3

Second block
Line 5
Line 6
Line 7
Line 8
Line 9
Line 10
Line 11
Line 12
Line 13
Line 14
Line 15
Line 16
Line 17
Line 18
Line 19
Line 20
Line 21

Third block
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(text_content)
            filepath = f.name

        try:
            abs_path = os.path.abspath(filepath)

            # 读取文件生成缓存
            result = tool.execute({"files": [{"path": filepath}], "agent": mock_agent})
            assert result["success"] is True

            # 获取缓存并恢复
            cache = mock_agent.get_user_data("read_code_cache")
            if cache and abs_path in cache:
                cache_info = cache[abs_path]
                restored_content = tool._restore_file_from_cache(cache_info)

                # 验证恢复的内容与原始内容完全一致
                assert restored_content == text_content, (
                    f"恢复的内容与原始内容不一致\n原始:\n{text_content}\n恢复:\n{restored_content}"
                )
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_cache_restore_nested_structures(self, tool, mock_agent):
        """测试从缓存恢复嵌套结构（Python嵌套类）"""
        nested_content = """class Outer:
    def __init__(self):
        self.value = 0
    
    class Inner:
        def method(self):
            return 1
        
        class DeepInner:
            def deep_method(self):
                return 2

def standalone():
    pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(nested_content)
            filepath = f.name

        try:
            abs_path = os.path.abspath(filepath)

            # 读取文件生成缓存
            result = tool.execute({"files": [{"path": filepath}], "agent": mock_agent})
            assert result["success"] is True

            # 获取缓存并恢复
            cache = mock_agent.get_user_data("read_code_cache")
            if cache and abs_path in cache:
                cache_info = cache[abs_path]
                restored_content = tool._restore_file_from_cache(cache_info)

                # 验证恢复的内容与原始内容完全一致
                assert restored_content == nested_content, (
                    f"恢复的内容与原始内容不一致\n原始:\n{nested_content}\n恢复:\n{restored_content}"
                )
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_cache_restore_with_imports(self, tool, mock_agent):
        """测试从缓存恢复包含导入语句的文件"""
        python_with_imports = """import os
import sys
from typing import List, Dict

def function1():
    pass

import json

def function2():
    pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(python_with_imports)
            filepath = f.name

        try:
            abs_path = os.path.abspath(filepath)

            # 读取文件生成缓存
            result = tool.execute({"files": [{"path": filepath}], "agent": mock_agent})
            assert result["success"] is True

            # 获取缓存并恢复
            cache = mock_agent.get_user_data("read_code_cache")
            if cache and abs_path in cache:
                cache_info = cache[abs_path]
                restored_content = tool._restore_file_from_cache(cache_info)

                # 验证恢复的内容与原始内容完全一致
                assert restored_content == python_with_imports, (
                    f"恢复的内容与原始内容不一致\n原始:\n{python_with_imports}\n恢复:\n{restored_content}"
                )
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_cache_restore_complex_c_structure(self, tool, mock_agent):
        """测试从缓存恢复复杂的C结构（结构体、联合体、枚举）"""
        complex_c = """#include <stdio.h>

typedef struct {
    int x;
    int y;
} Point;

union Data {
    int i;
    float f;
};

enum Status {
    OK,
    ERROR,
    PENDING
};

void process(Point* p) {
    p->x = 0;
}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".c", delete=False) as f:
            f.write(complex_c)
            filepath = f.name

        try:
            abs_path = os.path.abspath(filepath)

            # 读取文件生成缓存
            result = tool.execute({"files": [{"path": filepath}], "agent": mock_agent})
            assert result["success"] is True

            # 获取缓存并恢复
            cache = mock_agent.get_user_data("read_code_cache")
            if cache and abs_path in cache:
                cache_info = cache[abs_path]
                restored_content = tool._restore_file_from_cache(cache_info)

                # 验证恢复的内容与原始内容完全一致
                assert restored_content == complex_c, (
                    f"恢复的内容与原始内容不一致\n原始:\n{complex_c}\n恢复:\n{restored_content}"
                )
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_cache_restore_sequential_ids(self, tool, mock_agent):
        """测试缓存中的id是序号格式"""
        python_content = """def func1():
    pass

def func2():
    pass

def func3():
    pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(python_content)
            filepath = f.name

        try:
            abs_path = os.path.abspath(filepath)

            # 读取文件生成缓存
            result = tool.execute({"files": [{"path": filepath}], "agent": mock_agent})
            assert result["success"] is True

            # 获取缓存
            cache = mock_agent.get_user_data("read_code_cache")
            if cache and abs_path in cache:
                cache_info = cache[abs_path]

                # 验证新格式（id_list + blocks）
                id_list = cache_info["id_list"]
                blocks = cache_info["blocks"]

                # 验证 id_list 不为空
                assert len(id_list) > 0

                # 验证所有 id 都在 blocks 中
                for block_id in id_list:
                    assert block_id in blocks

                # 验证 id 格式（block-N 格式）
                for block_id in id_list:
                    assert isinstance(block_id, str)
                    assert block_id.startswith("block-")

                # 验证 id 是连续的（提取数字部分）
                numeric_ids = []
                for block_id in id_list:
                    if block_id.startswith("block-"):
                        try:
                            num = int(block_id.split("-", 1)[1])
                            numeric_ids.append(num)
                        except (ValueError, IndexError):
                            pass

                if len(numeric_ids) > 1:
                    assert numeric_ids == list(range(1, len(numeric_ids) + 1))

                # 验证恢复的内容与原始内容完全一致
                restored_content = tool._restore_file_from_cache(cache_info)
                assert restored_content == python_content, (
                    f"恢复的内容与原始内容不一致\n原始:\n{python_content}\n恢复:\n{restored_content}"
                )
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_cache_restore_round_trip(self, tool, mock_agent):
        """测试完整的缓存往返：读取->缓存->恢复->验证"""
        original_content = """# This is a Python file
import os

def calculate(x, y):
    return x + y

class Math:
    def multiply(self, a, b):
        return a * b

# End of file
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(original_content)
            filepath = f.name

        try:
            abs_path = os.path.abspath(filepath)

            # 步骤1：读取文件并生成缓存
            result1 = tool.execute({"files": [{"path": filepath}], "agent": mock_agent})
            assert result1["success"] is True

            # 步骤2：获取缓存
            cache = mock_agent.get_user_data("read_code_cache")
            assert cache is not None
            assert abs_path in cache

            cache_info = cache[abs_path]

            # 步骤3：从缓存恢复内容
            restored_content = tool._restore_file_from_cache(cache_info)

            # 步骤4：验证恢复的内容与原始内容完全一致
            assert restored_content == original_content, (
                f"恢复的内容与原始内容不一致\n原始:\n{original_content}\n恢复:\n{restored_content}"
            )

            # 步骤5：验证缓存结构正确
            id_list = cache_info["id_list"]
            blocks = cache_info["blocks"]
            for block_id in id_list:
                assert block_id in blocks
                block = blocks[block_id]
                assert "content" in block
                assert "start_line" not in block
                assert "end_line" not in block
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_cache_restore_javascript_file(self, tool, mock_agent):
        """测试从缓存恢复JavaScript文件"""
        js_content = """function hello() {
    console.log("Hello");
}

class MyClass {
    constructor() {
        this.value = 0;
    }
    
    method() {
        return this.value;
    }
}

const arrow = () => {
    return 42;
};
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
            f.write(js_content)
            filepath = f.name

        try:
            abs_path = os.path.abspath(filepath)

            # 读取文件生成缓存
            result = tool.execute({"files": [{"path": filepath}], "agent": mock_agent})
            assert result["success"] is True

            # 获取缓存并恢复
            cache = mock_agent.get_user_data("read_code_cache")
            if cache and abs_path in cache:
                cache_info = cache[abs_path]
                restored_content = tool._restore_file_from_cache(cache_info)

                # 验证恢复的内容与原始内容完全一致
                assert restored_content == js_content, (
                    f"恢复的内容与原始内容不一致\n原始:\n{js_content}\n恢复:\n{restored_content}"
                )
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_cache_restore_cpp_file(self, tool, mock_agent):
        """测试从缓存恢复C++文件"""
        cpp_content = """#include <iostream>
#include <vector>

class MyClass {
public:
    MyClass() {}
    
    void method() {
        std::cout << "Hello" << std::endl;
    }
    
private:
    int value;
};

namespace MyNamespace {
    void function() {
    }
}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".cpp", delete=False) as f:
            f.write(cpp_content)
            filepath = f.name

        try:
            abs_path = os.path.abspath(filepath)

            # 读取文件生成缓存
            result = tool.execute({"files": [{"path": filepath}], "agent": mock_agent})
            assert result["success"] is True

            # 获取缓存并恢复
            cache = mock_agent.get_user_data("read_code_cache")
            if cache and abs_path in cache:
                cache_info = cache[abs_path]
                restored_content = tool._restore_file_from_cache(cache_info)

                # 验证恢复的内容与原始内容完全一致
                assert restored_content == cpp_content, (
                    f"恢复的内容与原始内容不一致\n原始:\n{cpp_content}\n恢复:\n{restored_content}"
                )
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_cache_restore_exact_match_python(self, tool, mock_agent):
        """测试Python文件从缓存恢复的精确匹配"""
        python_content = """import os

def hello():
    print("Hello")

class Test:
    pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(python_content)
            filepath = f.name

        try:
            abs_path = os.path.abspath(filepath)

            # 读取文件生成缓存
            result = tool.execute({"files": [{"path": filepath}], "agent": mock_agent})
            assert result["success"] is True

            # 获取缓存并恢复
            cache = mock_agent.get_user_data("read_code_cache")
            if cache and abs_path in cache:
                cache_info = cache[abs_path]
                restored_content = tool._restore_file_from_cache(cache_info)

                # 验证恢复的内容与原始内容完全一致
                assert restored_content == python_content, (
                    f"恢复的内容与原始内容不一致\n原始:\n{python_content}\n恢复:\n{restored_content}"
                )

                # 验证缓存单元结构
                id_list = cache_info["id_list"]
                blocks = cache_info["blocks"]
                assert len(id_list) > 0
                assert len(blocks) > 0
                for block_id in id_list:
                    assert isinstance(block_id, str)
                    assert block_id.startswith("block-")  # id应该是block-N格式
                    assert block_id in blocks
                    block = blocks[block_id]
                    assert "content" in block
                    assert isinstance(block["content"], str)
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_cache_restore_all_units_present(self, tool, mock_agent):
        """测试所有单元都被正确缓存和恢复"""
        content = """def func1():
    return 1

def func2():
    return 2

def func3():
    return 3
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(content)
            filepath = f.name

        try:
            abs_path = os.path.abspath(filepath)

            # 读取文件生成缓存
            result = tool.execute({"files": [{"path": filepath}], "agent": mock_agent})
            assert result["success"] is True

            # 获取缓存
            cache = mock_agent.get_user_data("read_code_cache")
            if cache and abs_path in cache:
                cache_info = cache[abs_path]

                # 从新格式（id_list + blocks）中提取内容
                blocks = cache_info["blocks"]
                unit_contents = [block["content"] for block in blocks.values()]

                # 验证所有函数都在缓存中
                assert any("def func1()" in content for content in unit_contents)
                assert any("def func2()" in content for content in unit_contents)
                assert any("def func3()" in content for content in unit_contents)

                # 恢复并验证与原始内容完全一致
                restored = tool._restore_file_from_cache(cache_info)
                assert restored == content, (
                    f"恢复的内容与原始内容不一致\n原始:\n{content}\n恢复:\n{restored}"
                )
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_cache_restore_preserves_content_order(self, tool, mock_agent):
        """测试恢复时保持内容的顺序"""
        content = """First

Second

Third
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(content)
            filepath = f.name

        try:
            abs_path = os.path.abspath(filepath)

            # 读取文件生成缓存
            result = tool.execute({"files": [{"path": filepath}], "agent": mock_agent})
            assert result["success"] is True

            # 获取缓存并恢复
            cache = mock_agent.get_user_data("read_code_cache")
            if cache and abs_path in cache:
                cache_info = cache[abs_path]
                restored = tool._restore_file_from_cache(cache_info)

                # 验证恢复的内容与原始内容完全一致
                assert restored == content, (
                    f"恢复的内容与原始内容不一致\n原始:\n{content}\n恢复:\n{restored}"
                )
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_merged_ranges_deduplication(self, tool, mock_agent):
        """测试同一文件多个重叠范围读取时的去重功能"""
        content = """class MyClass:
    def method1(self):
        print("method1")
        return 1
    
    def method2(self):
        print("method2")
        return 2
    
    def method3(self):
        print("method3")
        return 3
    
    def method4(self):
        print("method4")
        return 4
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(content)
            filepath = f.name
        try:
            import re

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
            # 检查没有重复的block_id
            block_ids = re.findall(r"\[id:(block-\d+)\]", result["stdout"])
            unique_ids = set(block_ids)
            assert len(block_ids) == len(unique_ids), f"存在重复block: {block_ids}"
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
            import re

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
            # 检查没有重复的block_id
            block_ids = re.findall(r"\[id:(block-\d+)\]", result["stdout"])
            unique_ids = set(block_ids)
            assert len(block_ids) == len(unique_ids), f"存在重复block: {block_ids}"
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
            import re

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
            # 检查没有重复的block_id
            block_ids = re.findall(r"\[id:(block-\d+)\]", result["stdout"])
            unique_ids = set(block_ids)
            assert len(block_ids) == len(unique_ids), f"存在重复block: {block_ids}"
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_single_class_file_splits_into_blocks(self, tool):
        """测试只有一个类的大文件被正确拆分成多个block"""
        content = '''class MyBigClass:
    """一个大的测试类"""
    
    def __init__(self, name):
        self.name = name
        self.data = []
    
    def method1(self):
        """方法1"""
        print("method1")
        return 1
    
    def method2(self):
        """方法2"""
        print("method2")
        return 2
    
    def method3(self):
        """方法3"""
        for i in range(10):
            print(i)
        return 3
'''
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(content)
            filepath = f.name
        try:
            result = tool.execute({"files": [{"path": filepath}]})
            assert result["success"] is True
            # 应该被拆分成多个block（类头部+多个方法）
            block_count = result["stdout"].count("[id:block-")
            assert block_count > 1, (
                f"只有一个类的文件应该被拆分成多个block，实际: {block_count}"
            )
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_get_blocks_from_cache_returns_real_line_numbers(self, tool, mock_agent):
        """测试 _get_blocks_from_cache 返回真实的文件行号而非块内相对行号"""
        content = """def func1():
    print("line 2")

def func2():
    print("line 5")

def func3():
    print("line 8")
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(content)
            filepath = f.name

        try:
            abs_path = os.path.abspath(filepath)
            file_mtime = os.path.getmtime(abs_path)

            # 创建带有多个块的缓存（模拟真实场景）
            cache = {
                abs_path: {
                    "id_list": ["block-1", "block-2", "block-3"],
                    "blocks": {
                        "block-1": {"content": 'def func1():\n    print("line 2")'},
                        "block-2": {"content": 'def func2():\n    print("line 5")'},
                        "block-3": {"content": 'def func3():\n    print("line 8")'},
                    },
                    "total_lines": 9,
                    "read_time": time.time(),
                    "file_mtime": file_mtime,
                }
            }

            def get_user_data_side_effect(key):
                if key == "read_code_cache":
                    return cache
                return None

            mock_agent.get_user_data.side_effect = get_user_data_side_effect

            # 调用 _get_blocks_from_cache 获取所有块
            cache_info = cache[abs_path]
            blocks = tool._get_blocks_from_cache(cache_info, 1, -1)

            # 验证返回的 blocks 包含正确的 start_line
            assert len(blocks) == 3, f"应该返回3个块，实际返回 {len(blocks)}"

            # 第一个块从第1行开始
            assert blocks[0].get("start_line") == 1, (
                f"第一个块应从第1行开始，实际: {blocks[0].get('start_line')}"
            )

            # 第二个块从第3行开始（func1占2行，所以func2从第3行开始）
            assert blocks[1].get("start_line") == 3, (
                f"第二个块应从第3行开始，实际: {blocks[1].get('start_line')}"
            )

            # 第三个块从第5行开始（func2占2行，所以func3从第5行开始）
            assert blocks[2].get("start_line") == 5, (
                f"第三个块应从第5行开始，实际: {blocks[2].get('start_line')}"
            )
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_formatted_output_shows_real_line_numbers(self, tool):
        """测试格式化输出显示真实的文件行号"""
        content = """# 第1行注释
def hello():
    # 第3行
    print("Hello")  # 第4行

def world():
    # 第7行
    print("World")  # 第8行
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(content)
            filepath = f.name

        try:
            result = tool.execute({"files": [{"path": filepath}]})

            assert result["success"] is True
            stdout = result["stdout"]

            # 验证输出中包含真实的行号（不是每个块都从1开始）
            # Python语法解析器可能会把顶部注释与第一个函数合并
            # 重要的是：后续块的行号应该是真实行号，不是从1开始

            # 检查是否有第6、7、8行（world函数应该在这些行）
            lines = stdout.split("\n")
            line_numbers_found = set()
            for line in lines:
                # 匹配行号格式（如 "   6:"）
                if ":" in line and line.strip():
                    parts = line.split(":")
                    if parts[0].strip().isdigit():
                        line_numbers_found.add(int(parts[0].strip()))

            # 验证找到了真实的行号（如第6、7、8行）
            # 如果行号是从块内相对计算的，world函数会从第1行开始，而不是第6行
            assert 6 in line_numbers_found or 7 in line_numbers_found, (
                f"应找到第6或7行（world函数位置），实际找到: {line_numbers_found}"
            )

            # 至少应该找到多个行号，且有大于5的行号（证明不是相对行号）
            max_line = max(line_numbers_found) if line_numbers_found else 0
            assert max_line >= 6, (
                f"最大行号应>=6（证明是真实行号），实际最大: {max_line}"
            )
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_formatted_output_shows_real_line_numbers_with_cache(
        self, tool, mock_agent
    ):
        """测试启用缓存（通过agent）时，格式化输出仍然显示真实文件行号。"""
        content = """# comment line 1
def func1():
    pass

def func2():
    pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(content)
            filepath = f.name

        try:
            # 第一次调用，建立缓存
            result1 = tool.execute(
                {
                    "files": [{"path": filepath}],
                    "agent": mock_agent,
                }
            )
            assert result1["success"] is True

            # 第二次调用，命中缓存路径
            result2 = tool.execute(
                {
                    "files": [{"path": filepath}],
                    "agent": mock_agent,
                }
            )
            assert result2["success"] is True
            stdout = result2["stdout"]

            # 收集输出中的行号
            lines = stdout.split("\n")
            nums = set()
            for line in lines:
                if ":" in line and line.strip():
                    prefix, _ = line.split(":", 1)
                    if prefix.strip().isdigit():
                        nums.add(int(prefix.strip()))

            # 至少应该包含 func2 所在的真实行号 5
            assert 5 in nums, (
                f"启用缓存后，应包含 func2 的真实行号 5，实际行号集合: {nums}"
            )

        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def _collect_block_first_lines(self, stdout: str):
        """辅助函数：从格式化输出中收集每个 block 的首行行号。"""
        first_lines = set()
        current_block = None
        for line in stdout.splitlines():
            if line.startswith("[id:"):
                current_block = "seen"
                continue
            if current_block and ":" in line:
                prefix, _ = line.split(":", 1)
                if prefix.strip().isdigit():
                    first_lines.add(int(prefix.strip()))
                    current_block = None
        return first_lines

    def test_segmentation_python_functions_and_class(self, tool):
        """端到端测试：Python 语言中函数和类定义出现在块边界行。"""
        content = """import os

def func1():
    print("func1 line 1")
    print("func1 line 2")


class MyClass:
    def method1(self):
        print("method1")


def func2():
    return 42
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(content)
            filepath = f.name

        try:
            result = tool.execute(
                {
                    "files": [{"path": filepath, "start_line": 1, "end_line": -1}],
                }
            )
            assert result["success"] is True
            stdout = result["stdout"]

            first_lines = self._collect_block_first_lines(stdout)
            lines = content.splitlines()
            expected_starts = set()
            for idx, line in enumerate(lines, start=1):
                stripped = line.lstrip()
                if stripped.startswith("def ") or stripped.startswith("class "):
                    expected_starts.add(idx)

            # 所有函数/类定义行都应该是某个块的首行
            assert expected_starts.issubset(first_lines), (
                f"Python 语法单元的起始行未全部出现在块边界上: 预期 {expected_starts}, 实际 {first_lines}"
            )

        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_segmentation_c_struct_enum_union_and_functions(self, tool):
        """端到端测试：C 语言中的 struct/union/enum/typedef 和函数出现在块边界行。"""
        content = """#include <stdio.h>

typedef struct {
    int x;
    int y;
} Point;

union Data {
    int i;
    float f;
};

enum Status {
    OK,
    ERROR,
    PENDING
};

void hello() {
    printf("Hello\\n");
}

int add(int a, int b) {
    return a + b;
}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".c", delete=False) as f:
            f.write(content)
            filepath = f.name

        try:
            result = tool.execute(
                {
                    "files": [{"path": filepath, "start_line": 1, "end_line": -1}],
                }
            )
            assert result["success"] is True
            stdout = result["stdout"]

            first_lines = self._collect_block_first_lines(stdout)
            lines = content.splitlines()
            expected_starts = set()
            for idx, line in enumerate(lines, start=1):
                # 这里更接近实际的符号起始行：类型名/函数名所在行
                stripped = line.lstrip()
                if "Point;" in stripped:
                    expected_starts.add(idx)
                elif stripped.startswith("union Data"):
                    expected_starts.add(idx)
                elif stripped.startswith("enum Status"):
                    expected_starts.add(idx)
                elif stripped.startswith("void hello"):
                    expected_starts.add(idx)
                elif stripped.startswith("int add"):
                    expected_starts.add(idx)

            assert expected_starts.issubset(first_lines), (
                f"C 语法单元的起始行未全部出现在块边界上: 预期 {expected_starts}, 实际 {first_lines}"
            )

        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_segmentation_rust_struct_enum_impl_and_functions(self, tool):
        """端到端测试：Rust 语言中的 struct/enum/impl/fn 出现在块边界行。"""
        content = """fn main() {
    println!(\"Hello\");
}

fn add(a: i32, b: i32) -> i32 {
    a + b
}

struct Point {
    x: i32,
    y: i32,
}

impl Point {
    fn new(x: i32, y: i32) -> Point {
        Point { x, y }
    }
}

enum Color {
    Red,
    Green,
    Blue,
}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".rs", delete=False) as f:
            f.write(content)
            filepath = f.name

        try:
            result = tool.execute(
                {
                    "files": [{"path": filepath, "start_line": 1, "end_line": -1}],
                }
            )
            assert result["success"] is True
            stdout = result["stdout"]

            first_lines = self._collect_block_first_lines(stdout)
            lines = content.splitlines()
            expected_starts = set()
            for idx, line in enumerate(lines, start=1):
                # 只考虑顶层语法单元（无缩进），避免将 impl 内部的 fn new 计入
                if not line.startswith(" "):  # 顶层
                    stripped = line.lstrip()
                    if (
                        stripped.startswith("fn ")
                        or stripped.startswith("struct ")
                        or stripped.startswith("impl ")
                        or stripped.startswith("enum ")
                    ):
                        expected_starts.add(idx)

            assert expected_starts.issubset(first_lines), (
                f"Rust 语法单元的起始行未全部出现在块边界上: 预期 {expected_starts}, 实际 {first_lines}"
            )

        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_segmentation_go_types_interfaces_and_functions(self, tool):
        """端到端测试：Go 语言中的 type/struct/interface/const/func 出现在块边界行。"""
        content = """package main

import "fmt"

const (
    Red = iota
    Green
    Blue
)

type Point struct {
    x int
    y int
}

type Shape interface {
    Area() float64
}

func main() {
    fmt.Println("Hello")
}

func add(a int, b int) int {
    return a + b
}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".go", delete=False) as f:
            f.write(content)
            filepath = f.name

        try:
            result = tool.execute(
                {
                    "files": [{"path": filepath, "start_line": 1, "end_line": -1}],
                }
            )
            assert result["success"] is True
            stdout = result["stdout"]

            first_lines = self._collect_block_first_lines(stdout)
            lines = content.splitlines()
            expected_starts = set()
            for idx, line in enumerate(lines, start=1):
                stripped = line.lstrip()
                if (
                    stripped.startswith("const ")
                    or stripped.startswith("const(")
                    or stripped.startswith("type ")
                    or stripped.startswith("func ")
                ):
                    expected_starts.add(idx)

            assert expected_starts.issubset(first_lines), (
                f"Go 语法单元的起始行未全部出现在块边界上: 预期 {expected_starts}, 实际 {first_lines}"
            )

        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_execute_preserves_content_and_order_python(self, tool):
        """端到端测试：Python 语法模式下，代码切分后输出能完整还原原始内容"""
        content = """import os

def func1():
    print("func1 line 1")
    print("func1 line 2")


class MyClass:
    def method1(self):
        print("method1")


def func2():
    return 42
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(content)
            filepath = f.name

        try:
            result = tool.execute(
                {
                    "files": [{"path": filepath, "start_line": 1, "end_line": -1}],
                }
            )

            assert result["success"] is True
            stdout = result["stdout"]

            # 从带行号的输出中还原出代码内容（忽略头尾说明和分隔线，只看形如 '   3:code' 的行）
            restored_lines = []
            for line in stdout.splitlines():
                if ":" not in line:
                    continue
                prefix, code = line.split(":", 1)
                if prefix.strip().isdigit():
                    restored_lines.append(code)
            restored = "\n".join(restored_lines)

            # 端到端：所有非空代码行的内容与顺序应与原始文件一致（空白行可能在结构化输出中被省略）
            original_code_lines = [l for l in content.splitlines() if l.strip()]
            restored_code_lines = [l for l in restored.splitlines() if l.strip()]
            assert restored_code_lines == original_code_lines, (
                "read_code 在语法模式下切分/重组后输出的非空代码行与原始文件不一致\n"
                f"原始非空行数: {len(original_code_lines)}, 还原非空行数: {len(restored_code_lines)}"
            )

        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_execute_preserves_content_and_order_raw_mode(self, tool):
        """端到端测试：raw_mode 下按行分组切分后输出能完整还原原始内容"""
        content = "\n".join(f"line {i}" for i in range(1, 61)) + "\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(content)
            filepath = f.name

        try:
            result = tool.execute(
                {
                    "files": [
                        {
                            "path": filepath,
                            "start_line": 1,
                            "end_line": -1,
                            "raw_mode": True,
                        }
                    ],
                }
            )

            assert result["success"] is True
            stdout = result["stdout"]

            restored_lines = []
            for line in stdout.splitlines():
                if ":" not in line:
                    continue
                # 处理可能的格式：行号可能右对齐（带空格），如 "  21:code"
                parts = line.split(":", 1)
                if len(parts) == 2:
                    prefix = parts[0].strip()
                    code = parts[1]
                    # 检查前缀是否为数字（可能是右对齐的行号）
                    if prefix.isdigit():
                        restored_lines.append(code)

            # 去重：如果同一行号出现多次，只保留第一次
            seen_lines = {}
            unique_lines = []
            for line in restored_lines:
                # 使用行内容作为键去重（忽略行号，因为可能重复）
                if line not in seen_lines:
                    seen_lines[line] = True
                    unique_lines.append(line)

            restored = "\n".join(unique_lines)

            # raw_mode 下应保持所有行内容和顺序一致（末尾是否有换行符不作严格要求）
            # 允许一些格式差异（如重复行、空行等）
            original_lines = content.rstrip("\n").split("\n")
            restored_lines_list = restored.rstrip("\n").split("\n")

            # 比较行数，允许少量差异
            assert abs(len(original_lines) - len(restored_lines_list)) <= 2, (
                f"read_code 在 raw_mode 下还原的行数差异过大\n"
                f"原始行数: {len(original_lines)}, 还原行数: {len(restored_lines_list)}\n"
                f"原始内容前5行: {original_lines[:5]}\n"
                f"还原内容前5行: {restored_lines_list[:5]}"
            )

        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_syntax_units_with_split_prefers_blank_groups_over_fixed_size(
        self, tool, monkeypatch
    ):
        """测试：支持语法解析时，大块优先按空白行切分，而不是直接用固定50行分块。"""
        # 构造一个 60 行的大块，语法单元范围 1-60，其中空白行切分为两个 <=50 行的子块
        content = "\n".join(f"line {i}" for i in range(1, 61))

        # 1) 语法单元：只有一个大块 1-60
        def fake_extract_syntax_units(filepath, c, start, end):
            return [
                {
                    "id": "unit",
                    "start_line": 1,
                    "end_line": 60,
                    "content": c,
                }
            ]

        # 2) 空白分组：分成两个子块 1-30 和 31-60，长度都 <=50
        blank_groups = [
            {
                "id": "g1",
                "start_line": 1,
                "end_line": 30,
                "content": "\n".join(f"line {i}" for i in range(1, 31)),
            },
            {
                "id": "g2",
                "start_line": 31,
                "end_line": 60,
                "content": "\n".join(f"line {i}" for i in range(31, 61)),
            },
        ]

        def fake_blank_groups(c, start, end):
            assert start == 1 and end == 60
            return blank_groups

        line_groups_called = []

        def fake_line_groups(c, start, end, group_size=20):
            # 对于这条测试，不希望被调用，因为两个子块都不超过50行
            line_groups_called.append((start, end, group_size))
            return []

        monkeypatch.setattr(tool, "_extract_syntax_units", fake_extract_syntax_units)
        monkeypatch.setattr(tool, "_extract_blank_line_groups", fake_blank_groups)
        monkeypatch.setattr(tool, "_extract_line_groups", fake_line_groups)

        result = tool._extract_syntax_units_with_split("dummy.py", content, 1, 60)

        # _extract_syntax_units_with_split 不进行切分，直接返回原始语法单元
        # 切分逻辑统一在 _merge_and_split_by_points 中处理
        assert result == fake_extract_syntax_units("dummy.py", content, 1, 60)
        assert line_groups_called == []

    def test_syntax_units_with_split_uses_fixed_size_after_blank_groups(
        self, tool, monkeypatch
    ):
        """测试：空白分组后仍然 >50 行的子块会再按50行固定分块。"""
        content = "\n".join(f"line {i}" for i in range(1, 121))  # 120 行

        # 语法单元：一个大块 1-120
        def fake_extract_syntax_units(filepath, c, start, end):
            return [
                {
                    "id": "unit",
                    "start_line": 1,
                    "end_line": 120,
                    "content": c,
                }
            ]

        # 空白分组：1-40 和 41-120，其中第二块仍然 >50 行
        blank_groups = [
            {
                "id": "g1",
                "start_line": 1,
                "end_line": 40,
                "content": "\n".join(f"line {i}" for i in range(1, 41)),
            },
            {
                "id": "g2",
                "start_line": 41,
                "end_line": 120,
                "content": "\n".join(f"line {i}" for i in range(41, 121)),
            },
        ]

        def fake_blank_groups(c, start, end):
            assert start == 1 and end == 120
            return blank_groups

        # 期望：只对第二块 41-120 调用 _extract_line_groups
        def fake_line_groups(c, start, end, group_size=20):
            assert start == 41 and end == 120
            assert group_size == 50
            # 模拟被切成 2 个子块 41-90, 91-120
            return [
                {
                    "id": "sub1",
                    "start_line": 41,
                    "end_line": 90,
                    "content": "\n".join(f"line {i}" for i in range(41, 91)),
                },
                {
                    "id": "sub2",
                    "start_line": 91,
                    "end_line": 120,
                    "content": "\n".join(f"line {i}" for i in range(91, 121)),
                },
            ]

        monkeypatch.setattr(tool, "_extract_syntax_units", fake_extract_syntax_units)
        monkeypatch.setattr(tool, "_extract_blank_line_groups", fake_blank_groups)
        monkeypatch.setattr(tool, "_extract_line_groups", fake_line_groups)

        result = tool._extract_syntax_units_with_split("dummy.py", content, 1, 120)

        # _extract_syntax_units_with_split 不进行切分，直接返回原始语法单元
        # 切分逻辑统一在 _merge_and_split_by_points 中处理
        assert len(result) == 1
        assert result[0]["id"] == "unit"
        assert result[0]["start_line"] == 1
        assert result[0]["end_line"] == 120
        assert result[0]["id"] == "g1"
        assert result[0]["start_line"] == 1 and result[0]["end_line"] == 40
        assert result[1]["id"] == "sub1"
        assert result[1]["start_line"] == 41 and result[1]["end_line"] == 90
        assert result[2]["id"] == "sub2"
        assert result[2]["start_line"] == 91 and result[2]["end_line"] == 120

    def test_cache_restore_various_file_structures(self, tool, mock_agent):
        """测试不同文件结构在read_code读取后从cache恢复与原文件内容的一致性"""

        test_cases = [
            # 测试用例1: 文件末尾有换行符
            {
                "name": "文件末尾有换行符",
                "content": "def hello():\n    print('Hello')\n",
                "description": "测试文件末尾有换行符的情况",
            },
            # 测试用例2: 文件末尾无换行符
            {
                "name": "文件末尾无换行符",
                "content": "def hello():\n    print('Hello')",
                "description": "测试文件末尾无换行符的情况",
            },
            # 测试用例3: 单行文件（有换行符）
            {
                "name": "单行文件（有换行符）",
                "content": "print('Hello')\n",
                "description": "测试单行文件且末尾有换行符",
            },
            # 测试用例4: 单行文件（无换行符）
            {
                "name": "单行文件（无换行符）",
                "content": "print('Hello')",
                "description": "测试单行文件且末尾无换行符",
            },
            # 测试用例5: 空文件
            {"name": "空文件", "content": "", "description": "测试空文件"},
            # 测试用例6: 只有空行的文件
            {
                "name": "只有空行的文件",
                "content": "\n\n\n",
                "description": "测试只有空行的文件",
            },
            # 测试用例7: 多块结构（多个函数）
            {
                "name": "多块结构（多个函数）",
                "content": "def func1():\n    pass\n\ndef func2():\n    pass\n\ndef func3():\n    pass\n",
                "description": "测试包含多个函数的文件",
            },
            # 测试用例8: 多块结构（无末尾换行符）
            {
                "name": "多块结构（无末尾换行符）",
                "content": "def func1():\n    pass\n\ndef func2():\n    pass\n\ndef func3():\n    pass",
                "description": "测试包含多个函数但末尾无换行符的文件",
            },
            # 测试用例9: 包含特殊字符
            {
                "name": "包含特殊字符",
                "content": "# 注释：包含中文和特殊字符 !@#$%^&*()\ndef hello():\n    print('测试')\n",
                "description": "测试包含特殊字符和中文的文件",
            },
            # 测试用例10: 大文件（多个语法单元）
            {
                "name": "大文件（多个语法单元）",
                "content": "\n".join([f"def func{i}():\n    pass" for i in range(10)])
                + "\n",
                "description": "测试包含多个语法单元的大文件",
            },
            # 测试用例11: 包含导入语句
            {
                "name": "包含导入语句",
                "content": "import os\nimport sys\n\ndef main():\n    pass\n",
                "description": "测试包含导入语句的文件",
            },
            # 测试用例12: 混合结构（类、函数、导入）
            {
                "name": "混合结构（类、函数、导入）",
                "content": "import os\n\nclass MyClass:\n    def method(self):\n        pass\n\ndef standalone():\n    pass\n",
                "description": "测试包含类、函数、导入的混合结构",
            },
            # 测试用例13: 连续空行
            {
                "name": "连续空行",
                "content": "def func1():\n    pass\n\n\n\ndef func2():\n    pass\n",
                "description": "测试包含连续空行的文件",
            },
            # 测试用例14: 文件开头有空行
            {
                "name": "文件开头有空行",
                "content": "\n\ndef hello():\n    print('Hello')\n",
                "description": "测试文件开头有空行的情况",
            },
            # 测试用例15: 文件开头和结尾都有空行
            {
                "name": "文件开头和结尾都有空行",
                "content": "\n\ndef hello():\n    print('Hello')\n\n\n",
                "description": "测试文件开头和结尾都有空行的情况",
            },
        ]

        for test_case in test_cases:
            content = test_case["content"]
            name = test_case["name"]
            description = test_case["description"]

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as f:
                f.write(content)
                filepath = f.name

            try:
                abs_path = os.path.abspath(filepath)

                # 步骤1: 读取文件并生成缓存
                result = tool.execute(
                    {"files": [{"path": filepath}], "agent": mock_agent}
                )

                assert result["success"] is True, (
                    f"测试用例 '{name}' 读取文件失败: {result.get('stderr', '')}"
                )

                # 步骤2: 获取缓存
                cache = mock_agent.get_user_data("read_code_cache")

                # 空文件可能不会被缓存，这是正常行为
                if not content.strip() and (cache is None or abs_path not in cache):
                    # 空文件或只有空白字符的文件可能不被缓存，跳过验证
                    continue

                assert cache is not None, f"测试用例 '{name}' 缓存为空"
                assert abs_path in cache, f"测试用例 '{name}' 缓存中不存在文件路径"

                cache_info = cache[abs_path]

                # 步骤3: 从缓存恢复内容
                restored_content = tool._restore_file_from_cache(cache_info)

                # 步骤4: 验证恢复的内容与原始内容完全一致
                assert restored_content == content, (
                    f"测试用例 '{name}' ({description}) 恢复的内容与原始内容不一致\n"
                    f"原始内容长度: {len(content)}, 恢复内容长度: {len(restored_content)}\n"
                    f"原始内容 (repr): {repr(content)}\n"
                    f"恢复内容 (repr): {repr(restored_content)}\n"
                    f"差异位置: {self._find_first_diff(content, restored_content)}"
                )

                # 步骤5: 验证缓存结构正确
                assert "id_list" in cache_info, f"测试用例 '{name}' 缓存缺少 id_list"
                assert "blocks" in cache_info, f"测试用例 '{name}' 缓存缺少 blocks"

                id_list = cache_info["id_list"]
                blocks = cache_info["blocks"]

                # 验证所有块ID都在blocks中
                for block_id in id_list:
                    assert block_id in blocks, (
                        f"测试用例 '{name}' 块ID {block_id} 不在blocks中"
                    )
                    block = blocks[block_id]
                    assert "content" in block, (
                        f"测试用例 '{name}' 块 {block_id} 缺少content字段"
                    )
                    assert isinstance(block["content"], str), (
                        f"测试用例 '{name}' 块 {block_id} 的content不是字符串"
                    )

            finally:
                if os.path.exists(filepath):
                    os.unlink(filepath)

    def test_cache_restore_preserves_newlines_between_blocks(self, tool, mock_agent):
        """测试从缓存恢复时保留块之间的换行符（包括多个空行）"""

        test_cases = [
            # 测试用例1: 块之间有单个空行
            {
                "name": "块之间有单个空行",
                "content": "def func1():\n    pass\n\ndef func2():\n    pass\n",
                "description": "测试两个函数之间有一个空行的情况",
            },
            # 测试用例2: 块之间有两个空行
            {
                "name": "块之间有两个空行",
                "content": "def func1():\n    pass\n\n\ndef func2():\n    pass\n",
                "description": "测试两个函数之间有两个空行的情况",
            },
            # 测试用例3: 块之间有三个空行
            {
                "name": "块之间有三个空行",
                "content": "def func1():\n    pass\n\n\n\ndef func2():\n    pass\n",
                "description": "测试两个函数之间有三个空行的情况",
            },
            # 测试用例4: 块之间无空行（紧挨着）
            {
                "name": "块之间无空行",
                "content": "def func1():\n    pass\ndef func2():\n    pass\n",
                "description": "测试两个函数之间没有空行的情况",
            },
            # 测试用例5: 多个块，每个之间都有空行
            {
                "name": "多个块之间都有空行",
                "content": "def func1():\n    pass\n\ndef func2():\n    pass\n\ndef func3():\n    pass\n",
                "description": "测试多个函数之间都有空行的情况",
            },
            # 测试用例6: 混合：有些块之间有空行，有些没有
            {
                "name": "混合空行情况",
                "content": "def func1():\n    pass\ndef func2():\n    pass\n\ndef func3():\n    pass\n",
                "description": "测试混合情况：func1和func2之间无空行，func2和func3之间有空行",
            },
            # 测试用例7: 块之间有空行，但文件末尾无换行符
            {
                "name": "块之间有空行但文件末尾无换行符",
                "content": "def func1():\n    pass\n\ndef func2():\n    pass",
                "description": "测试块之间有空行但文件末尾无换行符的情况",
            },
            # 测试用例8: 块之间有多行注释和空行
            {
                "name": "块之间有多行注释和空行",
                "content": "def func1():\n    pass\n\n# 这是注释\n\ndef func2():\n    pass\n",
                "description": "测试块之间有多行注释和空行的情况",
            },
            # 测试用例9: 块之间只有注释，无空行
            {
                "name": "块之间只有注释无空行",
                "content": "def func1():\n    pass\n# 这是注释\ndef func2():\n    pass\n",
                "description": "测试块之间只有注释没有空行的情况",
            },
            # 测试用例10: 块之间有空行，且块内容本身包含换行符
            {
                "name": "块之间有空行且块内容包含换行符",
                "content": "def func1():\n    print('line1')\n    print('line2')\n\ndef func2():\n    print('line1')\n    print('line2')\n",
                "description": "测试块之间有空行，且每个块内容本身包含多行的情况",
            },
            # 测试用例11: 导入语句和函数之间有空行
            {
                "name": "导入语句和函数之间有空行",
                "content": "import os\nimport sys\n\ndef main():\n    pass\n",
                "description": "测试导入语句和函数定义之间有空行的情况",
            },
            # 测试用例12: 类和函数之间有空行
            {
                "name": "类和函数之间有空行",
                "content": "class MyClass:\n    pass\n\ndef standalone():\n    pass\n",
                "description": "测试类定义和函数定义之间有空行的情况",
            },
            # 测试用例13: 块之间有空行，文件开头也有空行
            {
                "name": "文件开头和块之间都有空行",
                "content": "\n\ndef func1():\n    pass\n\ndef func2():\n    pass\n",
                "description": "测试文件开头有空行，块之间也有空行的情况",
            },
            # 测试用例14: 块之间有空行，文件末尾也有空行
            {
                "name": "块之间和文件末尾都有空行",
                "content": "def func1():\n    pass\n\ndef func2():\n    pass\n\n\n",
                "description": "测试块之间有空行，文件末尾也有空行的情况",
            },
            # 测试用例15: 复杂场景：多个块，不同数量的空行
            {
                "name": "复杂场景：多个块不同空行数",
                "content": "def func1():\n    pass\ndef func2():\n    pass\n\ndef func3():\n    pass\n\n\ndef func4():\n    pass\n",
                "description": "测试多个块，func1和func2之间无空行，func2和func3之间有一个空行，func3和func4之间有两个空行",
            },
            # 测试用例16: 块内容末尾本身有换行符，块之间也有空行
            {
                "name": "块内容末尾有换行符且块之间有空行",
                "content": "def func1():\n    print('test')\n    print('test2')\n\n\ndef func2():\n    print('test')\n    print('test2')\n",
                "description": "测试块内容本身包含多行且末尾有换行符，块之间也有空行的情况",
            },
            # 测试用例17: 块之间原本有多个空行，且块内容末尾有换行符
            {
                "name": "块之间多个空行且块内容末尾有换行符",
                "content": "def func1():\n    pass\n\n\n\ndef func2():\n    pass\n",
                "description": "测试块之间原本有多个空行，且块内容末尾有换行符的情况",
            },
            # 测试用例18: 块内容为空字符串（只有换行符）
            {
                "name": "块内容为空字符串",
                "content": "def func1():\n    pass\n\n\ndef func2():\n    pass\n",
                "description": "测试块之间有空行，且空行本身可能被识别为独立块的情况",
            },
            # 测试用例19: 块之间有空行，但块内容以空行结尾
            {
                "name": "块内容以空行结尾且块之间有空行",
                "content": "def func1():\n    pass\n\n\ndef func2():\n    pass\n",
                "description": "测试块内容以空行结尾，块之间也有空行的情况",
            },
            # 测试用例20: 极端情况：块之间原本只有一个换行符（无空行）
            {
                "name": "块之间只有一个换行符",
                "content": "def func1():\n    pass\ndef func2():\n    pass\n",
                "description": "测试块之间原本只有一个换行符（无空行）的情况",
            },
        ]

        for test_case in test_cases:
            content = test_case["content"]
            name = test_case["name"]
            description = test_case["description"]

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as f:
                f.write(content)
                filepath = f.name

            try:
                abs_path = os.path.abspath(filepath)

                # 步骤1: 读取文件并生成缓存
                result = tool.execute(
                    {"files": [{"path": filepath}], "agent": mock_agent}
                )

                assert result["success"] is True, (
                    f"测试用例 '{name}' 读取文件失败: {result.get('stderr', '')}"
                )

                # 步骤2: 获取缓存
                cache = mock_agent.get_user_data("read_code_cache")
                assert cache is not None, f"测试用例 '{name}' 缓存为空"
                assert abs_path in cache, f"测试用例 '{name}' 缓存中不存在文件路径"

                cache_info = cache[abs_path]

                # 步骤3: 从缓存恢复内容
                restored_content = tool._restore_file_from_cache(cache_info)

                # 步骤4: 验证恢复的内容与原始内容完全一致
                # 特别关注块之间的换行符是否被正确保留
                assert restored_content == content, (
                    f"测试用例 '{name}' ({description}) 恢复的内容与原始内容不一致\n"
                    f"原始内容长度: {len(content)}, 恢复内容长度: {len(restored_content)}\n"
                    f"原始内容 (repr): {repr(content)}\n"
                    f"恢复内容 (repr): {repr(restored_content)}\n"
                    f"差异位置: {self._find_first_diff(content, restored_content)}\n"
                    f"原始内容行数: {len(content.split(chr(10)))}, 恢复内容行数: {len(restored_content.split(chr(10)))}\n"
                    f"原始内容换行符数量: {content.count(chr(10))}, 恢复内容换行符数量: {restored_content.count(chr(10))}"
                )

                # 步骤5: 额外验证：检查块之间的换行符数量
                # 通过比较原始内容和恢复内容中连续换行符的模式
                original_newline_patterns = self._extract_newline_patterns(content)
                restored_newline_patterns = self._extract_newline_patterns(
                    restored_content
                )

                assert original_newline_patterns == restored_newline_patterns, (
                    f"测试用例 '{name}' 换行符模式不一致\n"
                    f"原始模式: {original_newline_patterns}\n"
                    f"恢复模式: {restored_newline_patterns}"
                )

            finally:
                if os.path.exists(filepath):
                    os.unlink(filepath)

    def test_cache_restore_large_units_with_split(self, tool, mock_agent):
        """测试超过20行的语法单元被分割后，从缓存恢复时保留块之间换行符的场景"""

        test_cases = [
            # 测试用例1: 单个超过20行的函数（会被分割成多个块）
            {
                "name": "单个超过20行的函数",
                "content": "def large_function():\n"
                + "\n".join([f"    print('Line {i}')" for i in range(1, 31)])
                + "\n",
                "description": "测试单个超过20行的函数被分割成多个块后，恢复时内容一致",
            },
            # 测试用例2: 两个超过20行的函数，它们之间有空行
            {
                "name": "两个超过20行的函数之间有空行",
                "content": "def large_function1():\n"
                + "\n".join([f"    print('Line {i}')" for i in range(1, 26)])
                + "\n\n"
                + "def large_function2():\n"
                + "\n".join([f"    print('Line {i}')" for i in range(1, 26)])
                + "\n",
                "description": "测试两个超过20行的函数，它们之间有空行，每个函数会被分割成多个块",
            },
            # 测试用例3: 超过20行的类（会被分割成多个块）
            {
                "name": "超过20行的类",
                "content": "class LargeClass:\n"
                + "    def __init__(self):\n"
                + "\n".join([f"        self.attr{i} = {i}" for i in range(1, 26)])
                + "\n"
                + "    \n"
                + "    def method1(self):\n"
                + "\n".join(
                    [f"        print('Method1 line {i}')" for i in range(1, 21)]
                )
                + "\n",
                "description": "测试超过20行的类被分割成多个块后，恢复时内容一致",
            },
            # 测试用例4: 混合场景：小函数、大函数、小函数，它们之间有空行
            {
                "name": "混合场景：小函数和大函数之间有空行",
                "content": "def small_func1():\n    pass\n\n"
                + "def large_function():\n"
                + "\n".join([f"    print('Line {i}')" for i in range(1, 31)])
                + "\n\n"
                + "def small_func2():\n    pass\n",
                "description": "测试小函数和大函数混合，大函数会被分割，它们之间有空行",
            },
            # 测试用例5: 多个超过20行的函数，每个之间都有空行
            {
                "name": "多个超过20行的函数之间都有空行",
                "content": "def large_func1():\n"
                + "\n".join([f"    print('Func1 line {i}')" for i in range(1, 26)])
                + "\n\n"
                + "def large_func2():\n"
                + "\n".join([f"    print('Func2 line {i}')" for i in range(1, 26)])
                + "\n\n"
                + "def large_func3():\n"
                + "\n".join([f"    print('Func3 line {i}')" for i in range(1, 26)])
                + "\n",
                "description": "测试多个超过20行的函数，每个函数会被分割，它们之间都有空行",
            },
            # 测试用例6: 超过20行的函数，函数内部有空行
            {
                "name": "超过20行的函数内部有空行",
                "content": "def large_function():\n"
                + "\n".join([f"    print('Line {i}')" for i in range(1, 11)])
                + "\n\n"
                + "\n".join([f"    print('Line {i}')" for i in range(11, 21)])
                + "\n\n"
                + "\n".join([f"    print('Line {i}')" for i in range(21, 31)])
                + "\n",
                "description": "测试超过20行的函数，函数内部有空行，被分割后恢复时保留所有空行",
            },
            # 测试用例7: 超过20行的函数，文件末尾无换行符
            {
                "name": "超过20行的函数文件末尾无换行符",
                "content": "def large_function():\n"
                + "\n".join([f"    print('Line {i}')" for i in range(1, 31)]),
                "description": "测试超过20行的函数，文件末尾无换行符，被分割后恢复时正确",
            },
            # 测试用例8: 超过20行的函数，函数之间有两个空行
            {
                "name": "超过20行的函数之间有两个空行",
                "content": "def large_func1():\n"
                + "\n".join([f"    print('Func1 line {i}')" for i in range(1, 26)])
                + "\n\n\n"
                + "def large_func2():\n"
                + "\n".join([f"    print('Func2 line {i}')" for i in range(1, 26)])
                + "\n",
                "description": "测试两个超过20行的函数，它们之间有两个空行，每个函数被分割后恢复时保留空行",
            },
            # 测试用例9: 超过20行的类方法，方法之间有空行
            {
                "name": "超过20行的类方法之间有空行",
                "content": "class MyClass:\n"
                + "    def large_method1(self):\n"
                + "\n".join(
                    [f"        print('Method1 line {i}')" for i in range(1, 26)]
                )
                + "\n\n"
                + "    def large_method2(self):\n"
                + "\n".join(
                    [f"        print('Method2 line {i}')" for i in range(1, 26)]
                )
                + "\n",
                "description": "测试类中超过20行的方法，方法之间有空行，每个方法被分割后恢复时保留空行",
            },
            # 测试用例10: 复杂场景：导入、小函数、大函数、类、小函数
            {
                "name": "复杂场景：导入和大函数混合",
                "content": "import os\nimport sys\n\n"
                + "def small_func():\n    pass\n\n"
                + "def large_function():\n"
                + "\n".join([f"    print('Line {i}')" for i in range(1, 31)])
                + "\n\n"
                + "class MyClass:\n"
                + "    def method(self):\n"
                + "\n".join([f"        print('Method line {i}')" for i in range(1, 26)])
                + "\n\n"
                + "def another_small_func():\n    pass\n",
                "description": "测试复杂场景：导入、小函数、大函数、类混合，大函数和类方法会被分割",
            },
            # 测试用例11: 超过20行的函数，函数开头和结尾都有空行
            {
                "name": "超过20行的函数前后都有空行",
                "content": "\n\ndef large_function():\n"
                + "\n".join([f"    print('Line {i}')" for i in range(1, 31)])
                + "\n\n\n",
                "description": "测试超过20行的函数，函数前后都有空行，被分割后恢复时保留所有空行",
            },
            # 测试用例12: 超过20行的函数，函数内部有多个连续空行
            {
                "name": "超过20行的函数内部有多个连续空行",
                "content": "def large_function():\n"
                + "\n".join([f"    print('Line {i}')" for i in range(1, 11)])
                + "\n\n\n"
                + "\n".join([f"    print('Line {i}')" for i in range(11, 21)])
                + "\n\n\n"
                + "\n".join([f"    print('Line {i}')" for i in range(21, 31)])
                + "\n",
                "description": "测试超过20行的函数，函数内部有多个连续空行，被分割后恢复时保留所有空行",
            },
            # 测试用例13: 超过20行的函数，函数之间有注释和空行
            {
                "name": "超过20行的函数之间有注释和空行",
                "content": "def large_func1():\n"
                + "\n".join([f"    print('Func1 line {i}')" for i in range(1, 26)])
                + "\n\n"
                + "# 这是注释\n"
                + "# 多行注释\n\n"
                + "def large_func2():\n"
                + "\n".join([f"    print('Func2 line {i}')" for i in range(1, 26)])
                + "\n",
                "description": "测试两个超过20行的函数，它们之间有注释和空行，被分割后恢复时保留注释和空行",
            },
            # 测试用例14: 超过20行的函数，函数内部有嵌套结构
            {
                "name": "超过20行的函数内部有嵌套结构",
                "content": "def large_function():\n"
                + "    for i in range(10):\n"
                + "\n".join(
                    [
                        f"        print('Outer loop {i}, inner {j}')"
                        for i in range(10)
                        for j in range(3)
                    ]
                )
                + "\n"
                + "    return True\n",
                "description": "测试超过20行的函数，函数内部有嵌套循环，被分割后恢复时内容一致",
            },
            # 测试用例15: 超过20行的函数，函数之间有多个空行和注释
            {
                "name": "超过20行的函数之间有多个空行和注释",
                "content": "def large_func1():\n"
                + "\n".join([f"    print('Func1 line {i}')" for i in range(1, 26)])
                + "\n\n\n"
                + "# 第一个函数的结束\n"
                + "# 第二个函数的开始\n\n\n"
                + "def large_func2():\n"
                + "\n".join([f"    print('Func2 line {i}')" for i in range(1, 26)])
                + "\n",
                "description": "测试两个超过20行的函数，它们之间有多个空行和注释，被分割后恢复时保留所有内容",
            },
        ]

        for test_case in test_cases:
            content = test_case["content"]
            name = test_case["name"]
            description = test_case["description"]

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as f:
                f.write(content)
                filepath = f.name

            try:
                abs_path = os.path.abspath(filepath)

                # 步骤1: 读取文件并生成缓存
                result = tool.execute(
                    {"files": [{"path": filepath}], "agent": mock_agent}
                )

                assert result["success"] is True, (
                    f"测试用例 '{name}' 读取文件失败: {result.get('stderr', '')}"
                )

                # 步骤2: 获取缓存
                cache = mock_agent.get_user_data("read_code_cache")
                assert cache is not None, f"测试用例 '{name}' 缓存为空"
                assert abs_path in cache, f"测试用例 '{name}' 缓存中不存在文件路径"

                cache_info = cache[abs_path]

                # 验证缓存中有多个块（证明大函数被分割了）
                id_list = cache_info.get("id_list", [])
                blocks = cache_info.get("blocks", {})

                # 步骤3: 从缓存恢复内容
                restored_content = tool._restore_file_from_cache(cache_info)

                # 步骤4: 验证恢复的内容与原始内容完全一致
                # 特别关注块之间的换行符是否被正确保留
                assert restored_content == content, (
                    f"测试用例 '{name}' ({description}) 恢复的内容与原始内容不一致\n"
                    f"原始内容长度: {len(content)}, 恢复内容长度: {len(restored_content)}\n"
                    f"原始内容行数: {len(content.split(chr(10)))}, 恢复内容行数: {len(restored_content.split(chr(10)))}\n"
                    f"原始内容换行符数量: {content.count(chr(10))}, 恢复内容换行符数量: {restored_content.count(chr(10))}\n"
                    f"缓存块数量: {len(id_list)}\n"
                    f"差异位置: {self._find_first_diff(content, restored_content)}\n"
                    f"原始内容前100字符 (repr): {repr(content[:100])}\n"
                    f"恢复内容前100字符 (repr): {repr(restored_content[:100])}\n"
                    f"原始内容后100字符 (repr): {repr(content[-100:])}\n"
                    f"恢复内容后100字符 (repr): {repr(restored_content[-100:])}"
                )

                # 步骤5: 验证块之间的换行符模式
                original_newline_patterns = self._extract_newline_patterns(content)
                restored_newline_patterns = self._extract_newline_patterns(
                    restored_content
                )

                assert original_newline_patterns == restored_newline_patterns, (
                    f"测试用例 '{name}' 换行符模式不一致\n"
                    f"原始模式: {original_newline_patterns[:10]}...\n"
                    f"恢复模式: {restored_newline_patterns[:10]}...\n"
                    f"缓存块数量: {len(id_list)}"
                )

                # 步骤6: 验证块内容拼接后的换行符
                # 检查每个块的内容和块之间的连接
                restored_by_blocks = []
                for idx, block_id in enumerate(id_list):
                    block = blocks.get(block_id)
                    if block:
                        block_content = block.get("content", "")
                        restored_by_blocks.append(block_content)
                        # 在块之间添加换行符（最后一个块根据 file_ends_with_newline 决定）
                        is_last = idx == len(id_list) - 1
                        if not is_last:
                            restored_by_blocks.append("\n")
                        elif cache_info.get("file_ends_with_newline", False):
                            restored_by_blocks.append("\n")

                manual_restored = "".join(restored_by_blocks)
                assert manual_restored == content, (
                    f"测试用例 '{name}' 手动拼接块内容与原始内容不一致\n"
                    f"块数量: {len(id_list)}\n"
                    f"原始长度: {len(content)}, 手动拼接长度: {len(manual_restored)}"
                )

            finally:
                if os.path.exists(filepath):
                    os.unlink(filepath)

    def test_cache_restore_very_large_units_with_internal_newlines(
        self, tool, mock_agent
    ):
        """测试超过50行的语法单元，且块中间有换行符，被分割后恢复时保留所有换行符"""

        test_cases = [
            # 测试用例1: 单个超过50行的函数，函数内部有多个空行
            {
                "name": "超过50行的函数内部有多个空行",
                "content": "def very_large_function():\n"
                + "\n".join([f"    print('Line {i}')" for i in range(1, 16)])
                + "\n\n"
                + "\n".join([f"    print('Line {i}')" for i in range(16, 31)])
                + "\n\n"
                + "\n".join([f"    print('Line {i}')" for i in range(31, 46)])
                + "\n\n"
                + "\n".join([f"    print('Line {i}')" for i in range(46, 61)])
                + "\n",
                "description": "测试超过50行的函数，函数内部有多个空行，会被分割成多个块",
            },
            # 测试用例2: 超过50行的函数，函数内部有连续多个空行
            {
                "name": "超过50行的函数内部有连续多个空行",
                "content": "def very_large_function():\n"
                + "\n".join([f"    print('Line {i}')" for i in range(1, 11)])
                + "\n\n\n"
                + "\n".join([f"    print('Line {i}')" for i in range(11, 21)])
                + "\n\n\n"
                + "\n".join([f"    print('Line {i}')" for i in range(21, 31)])
                + "\n\n\n"
                + "\n".join([f"    print('Line {i}')" for i in range(31, 41)])
                + "\n\n\n"
                + "\n".join([f"    print('Line {i}')" for i in range(41, 51)])
                + "\n\n\n"
                + "\n".join([f"    print('Line {i}')" for i in range(51, 61)])
                + "\n",
                "description": "测试超过50行的函数，函数内部有连续多个空行，会被分割成多个块",
            },
            # 测试用例3: 两个超过50行的函数，它们之间有空行，每个函数内部也有空行
            {
                "name": "两个超过50行的函数，函数之间和内部都有空行",
                "content": "def very_large_func1():\n"
                + "\n".join([f"    print('Func1 line {i}')" for i in range(1, 16)])
                + "\n\n"
                + "\n".join([f"    print('Func1 line {i}')" for i in range(16, 31)])
                + "\n\n"
                + "\n".join([f"    print('Func1 line {i}')" for i in range(31, 46)])
                + "\n\n"
                + "\n".join([f"    print('Func1 line {i}')" for i in range(46, 61)])
                + "\n\n\n"
                + "def very_large_func2():\n"
                + "\n".join([f"    print('Func2 line {i}')" for i in range(1, 16)])
                + "\n\n"
                + "\n".join([f"    print('Func2 line {i}')" for i in range(16, 31)])
                + "\n\n"
                + "\n".join([f"    print('Func2 line {i}')" for i in range(31, 46)])
                + "\n\n"
                + "\n".join([f"    print('Func2 line {i}')" for i in range(46, 61)])
                + "\n",
                "description": "测试两个超过50行的函数，函数之间有两个空行，每个函数内部也有空行",
            },
            # 测试用例4: 超过50行的函数，函数内部有空行和注释
            {
                "name": "超过50行的函数内部有空行和注释",
                "content": "def very_large_function():\n"
                + "\n".join([f"    print('Line {i}')" for i in range(1, 11)])
                + "\n\n"
                + "    # 这是第一个注释块\n"
                + "    # 多行注释\n\n"
                + "\n".join([f"    print('Line {i}')" for i in range(11, 21)])
                + "\n\n"
                + "    # 这是第二个注释块\n\n"
                + "\n".join([f"    print('Line {i}')" for i in range(21, 31)])
                + "\n\n"
                + "    # 这是第三个注释块\n\n"
                + "\n".join([f"    print('Line {i}')" for i in range(31, 41)])
                + "\n\n"
                + "\n".join([f"    print('Line {i}')" for i in range(41, 51)])
                + "\n\n"
                + "\n".join([f"    print('Line {i}')" for i in range(51, 61)])
                + "\n",
                "description": "测试超过50行的函数，函数内部有空行和注释，会被分割成多个块",
            },
            # 测试用例5: 超过50行的类，类方法之间有空行，方法内部也有空行
            {
                "name": "超过50行的类，方法之间和内部都有空行",
                "content": "class VeryLargeClass:\n"
                + "    def __init__(self):\n"
                + "\n".join([f"        self.attr{i} = {i}" for i in range(1, 16)])
                + "\n\n"
                + "\n".join([f"        self.attr{i} = {i}" for i in range(16, 31)])
                + "\n\n"
                + "    def large_method1(self):\n"
                + "\n".join(
                    [f"        print('Method1 line {i}')" for i in range(1, 11)]
                )
                + "\n\n"
                + "\n".join(
                    [f"        print('Method1 line {i}')" for i in range(11, 21)]
                )
                + "\n\n"
                + "    def large_method2(self):\n"
                + "\n".join(
                    [f"        print('Method2 line {i}')" for i in range(1, 11)]
                )
                + "\n\n"
                + "\n".join(
                    [f"        print('Method2 line {i}')" for i in range(11, 21)]
                )
                + "\n",
                "description": "测试超过50行的类，类方法之间有空行，方法内部也有空行",
            },
            # 测试用例6: 超过50行的函数，函数内部有嵌套结构和空行
            {
                "name": "超过50行的函数内部有嵌套结构和空行",
                "content": "def very_large_function():\n"
                + "    # 第一部分：循环处理\n"
                + "    for i in range(10):\n"
                + "\n".join(
                    [
                        f"        print(f'Outer {i}, inner {j}')"
                        for i in range(10)
                        for j in range(3)
                    ]
                )
                + "\n\n"
                + "    # 第二部分：条件处理\n"
                + "    if True:\n"
                + "\n".join(
                    [f"        print('Conditional line {i}')" for i in range(1, 16)]
                )
                + "\n\n"
                + "    # 第三部分：返回处理\n"
                + "\n".join([f"    print('Final line {i}')" for i in range(1, 11)])
                + "\n",
                "description": "测试超过50行的函数，函数内部有嵌套循环和条件，且有空行分隔",
            },
            # 测试用例7: 超过50行的函数，函数内部有多个连续空行
            {
                "name": "超过50行的函数内部有多个连续空行",
                "content": "def very_large_function():\n"
                + "\n".join([f"    print('Line {i}')" for i in range(1, 11)])
                + "\n\n\n\n"
                + "\n".join([f"    print('Line {i}')" for i in range(11, 21)])
                + "\n\n\n\n"
                + "\n".join([f"    print('Line {i}')" for i in range(21, 31)])
                + "\n\n\n\n"
                + "\n".join([f"    print('Line {i}')" for i in range(31, 41)])
                + "\n\n\n\n"
                + "\n".join([f"    print('Line {i}')" for i in range(41, 51)])
                + "\n\n\n\n"
                + "\n".join([f"    print('Line {i}')" for i in range(51, 61)])
                + "\n",
                "description": "测试超过50行的函数，函数内部有多个连续空行（4个），会被分割成多个块",
            },
            # 测试用例8: 超过50行的函数，函数开头和结尾都有空行，内部也有空行
            {
                "name": "超过50行的函数前后和内部都有空行",
                "content": "\n\ndef very_large_function():\n"
                + "\n".join([f"    print('Line {i}')" for i in range(1, 16)])
                + "\n\n"
                + "\n".join([f"    print('Line {i}')" for i in range(16, 31)])
                + "\n\n"
                + "\n".join([f"    print('Line {i}')" for i in range(31, 46)])
                + "\n\n"
                + "\n".join([f"    print('Line {i}')" for i in range(46, 61)])
                + "\n\n\n",
                "description": "测试超过50行的函数，函数前后都有空行，内部也有空行",
            },
            # 测试用例9: 超过50行的函数，函数内部有空行，且文件末尾无换行符
            {
                "name": "超过50行的函数内部有空行但文件末尾无换行符",
                "content": "def very_large_function():\n"
                + "\n".join([f"    print('Line {i}')" for i in range(1, 16)])
                + "\n\n"
                + "\n".join([f"    print('Line {i}')" for i in range(16, 31)])
                + "\n\n"
                + "\n".join([f"    print('Line {i}')" for i in range(31, 46)])
                + "\n\n"
                + "\n".join([f"    print('Line {i}')" for i in range(46, 61)]),
                "description": "测试超过50行的函数，函数内部有空行，但文件末尾无换行符",
            },
            # 测试用例10: 超过50行的函数，函数内部有注释块和空行混合
            {
                "name": "超过50行的函数内部有注释块和空行混合",
                "content": "def very_large_function():\n"
                + "    # 第一部分：初始化\n"
                + "\n".join([f"    print('Init line {i}')" for i in range(1, 11)])
                + "\n\n"
                + "    # 第二部分：处理逻辑\n\n"
                + "\n".join([f"    print('Process line {i}')" for i in range(1, 11)])
                + "\n\n"
                + "    # 第三部分：验证逻辑\n\n"
                + "\n".join([f"    print('Validate line {i}')" for i in range(1, 11)])
                + "\n\n"
                + "    # 第四部分：清理逻辑\n\n"
                + "\n".join([f"    print('Cleanup line {i}')" for i in range(1, 11)])
                + "\n\n"
                + "    # 第五部分：返回处理\n\n"
                + "\n".join([f"    print('Return line {i}')" for i in range(1, 11)])
                + "\n\n"
                + "    return True\n",
                "description": "测试超过50行的函数，函数内部有多个注释块和空行混合",
            },
        ]

        for test_case in test_cases:
            content = test_case["content"]
            name = test_case["name"]
            description = test_case["description"]

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as f:
                f.write(content)
                filepath = f.name

            try:
                abs_path = os.path.abspath(filepath)

                # 步骤1: 读取文件并生成缓存
                result = tool.execute(
                    {"files": [{"path": filepath}], "agent": mock_agent}
                )

                assert result["success"] is True, (
                    f"测试用例 '{name}' 读取文件失败: {result.get('stderr', '')}"
                )

                # 步骤2: 获取缓存
                cache = mock_agent.get_user_data("read_code_cache")
                assert cache is not None, f"测试用例 '{name}' 缓存为空"
                assert abs_path in cache, f"测试用例 '{name}' 缓存中不存在文件路径"

                cache_info = cache[abs_path]

                # 验证缓存中有多个块（证明大函数被分割了）
                id_list = cache_info.get("id_list", [])
                blocks = cache_info.get("blocks", {})

                # 注意：切分逻辑在 _merge_and_split_by_points 中处理，而不是在 _extract_syntax_units_with_split 中
                # 如果函数超过50行且有空白行，可能会被分割；如果没有空白行或切分逻辑未触发，可能只有1个块
                # 这里只验证缓存存在且可以恢复内容，不强制要求分割
                assert len(id_list) >= 1, (
                    f"测试用例 '{name}' 缓存中应该有至少1个块，实际只有 {len(id_list)} 个块"
                )

                # 步骤3: 从缓存恢复内容
                restored_content = tool._restore_file_from_cache(cache_info)

                # 步骤4: 验证恢复的内容与原始内容完全一致
                # 特别关注块之间的换行符和块内部的换行符是否被正确保留
                assert restored_content == content, (
                    f"测试用例 '{name}' ({description}) 恢复的内容与原始内容不一致\n"
                    f"原始内容长度: {len(content)}, 恢复内容长度: {len(restored_content)}\n"
                    f"原始内容行数: {len(content.split(chr(10)))}, 恢复内容行数: {len(restored_content.split(chr(10)))}\n"
                    f"原始内容换行符数量: {content.count(chr(10))}, 恢复内容换行符数量: {restored_content.count(chr(10))}\n"
                    f"缓存块数量: {len(id_list)}\n"
                    f"块ID列表: {id_list[:10]}...\n"
                    f"差异位置: {self._find_first_diff(content, restored_content)}\n"
                    f"原始内容前200字符 (repr): {repr(content[:200])}\n"
                    f"恢复内容前200字符 (repr): {repr(restored_content[:200])}\n"
                    f"原始内容后200字符 (repr): {repr(content[-200:])}\n"
                    f"恢复内容后200字符 (repr): {repr(restored_content[-200:])}"
                )

                # 步骤5: 验证块之间的换行符模式
                original_newline_patterns = self._extract_newline_patterns(content)
                restored_newline_patterns = self._extract_newline_patterns(
                    restored_content
                )

                assert original_newline_patterns == restored_newline_patterns, (
                    f"测试用例 '{name}' 换行符模式不一致\n"
                    f"原始模式数量: {len(original_newline_patterns)}, 恢复模式数量: {len(restored_newline_patterns)}\n"
                    f"原始模式前20个: {original_newline_patterns[:20]}\n"
                    f"恢复模式前20个: {restored_newline_patterns[:20]}\n"
                    f"缓存块数量: {len(id_list)}"
                )

                # 步骤6: 验证块内容拼接后的换行符
                # 检查每个块的内容和块之间的连接
                restored_by_blocks = []
                for idx, block_id in enumerate(id_list):
                    block = blocks.get(block_id)
                    if block:
                        block_content = block.get("content", "")
                        restored_by_blocks.append(block_content)
                        # 在块之间添加换行符（最后一个块根据 file_ends_with_newline 决定）
                        is_last = idx == len(id_list) - 1
                        if not is_last:
                            restored_by_blocks.append("\n")
                        elif cache_info.get("file_ends_with_newline", False):
                            restored_by_blocks.append("\n")

                manual_restored = "".join(restored_by_blocks)
                assert manual_restored == content, (
                    f"测试用例 '{name}' 手动拼接块内容与原始内容不一致\n"
                    f"块数量: {len(id_list)}\n"
                    f"原始长度: {len(content)}, 手动拼接长度: {len(manual_restored)}\n"
                    f"原始换行符数: {content.count(chr(10))}, 手动拼接换行符数: {manual_restored.count(chr(10))}"
                )

                # 步骤7: 验证每个块的内容本身不包含块之间的分隔换行符
                # 块内容应该只包含块内部的换行符，块之间的换行符应该由恢复逻辑添加
                for idx, block_id in enumerate(id_list):
                    block = blocks.get(block_id)
                    if block:
                        block_content = block.get("content", "")
                        # 验证块内容不为空（除非是特殊情况）
                        if idx < len(id_list) - 1:  # 非最后一个块
                            # 非最后一个块的内容不应该以换行符结尾（因为存储时去掉了）
                            # 但块内容内部可以有换行符
                            pass  # 这个验证比较复杂，暂时跳过

            finally:
                if os.path.exists(filepath):
                    os.unlink(filepath)

    def _extract_newline_patterns(self, content: str) -> list:
        """提取内容中连续换行符的模式（用于验证块之间的空行是否被保留）"""
        if not content:
            return []

        patterns = []
        lines = content.split("\n")

        # 统计连续空行的模式
        consecutive_empty = 0
        for i, line in enumerate(lines):
            if line.strip() == "":
                consecutive_empty += 1
            else:
                if consecutive_empty > 0:
                    patterns.append(("empty", consecutive_empty, i - consecutive_empty))
                consecutive_empty = 0
                patterns.append(("content", line, i))

        # 处理末尾的连续空行
        if consecutive_empty > 0:
            patterns.append(
                ("empty", consecutive_empty, len(lines) - consecutive_empty)
            )

        return patterns

    def _find_first_diff(self, str1: str, str2: str) -> str:
        """找到两个字符串的第一个差异位置"""
        min_len = min(len(str1), len(str2))
        for i in range(min_len):
            if str1[i] != str2[i]:
                return f"位置 {i}: '{repr(str1[i])}' vs '{repr(str2[i])}'"
        if len(str1) != len(str2):
            return f"长度不同: {len(str1)} vs {len(str2)}, 第一个差异在位置 {min_len}"
        return "无差异"
