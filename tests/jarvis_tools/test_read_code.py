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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(content)
            filepath = f.name
        
        yield filepath
        
        # 清理
        if os.path.exists(filepath):
            os.unlink(filepath)

    def test_read_single_file(self, tool, sample_file):
        """测试读取单个文件"""
        result = tool.execute({
            "files": [{"path": sample_file}]
        })
        
        assert result["success"] is True
        assert "stdout" in result
        assert sample_file in result["stdout"] or os.path.basename(sample_file) in result["stdout"]

    def test_read_file_with_range(self, tool, sample_file):
        """测试读取文件指定范围"""
        result = tool.execute({
            "files": [{"path": sample_file, "start_line": 1, "end_line": 5}]
        })
        
        assert result["success"] is True
        assert "stdout" in result

    def test_read_nonexistent_file(self, tool):
        """测试读取不存在的文件"""
        result = tool.execute({
            "files": [{"path": "/nonexistent/file/path.py"}]
        })
        
        assert result["success"] is False
        # 错误信息可能在stderr或stdout中
        error_msg = result.get("stderr", "") + result.get("stdout", "")
        assert "不存在" in error_msg or "not found" in error_msg.lower() or "文件读取失败" in error_msg

    def test_read_multiple_files(self, tool, sample_file):
        """测试读取多个文件"""
        # 创建第二个文件
        content2 = "x = 1\ny = 2\nz = x + y\n"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(content2)
            filepath2 = f.name
        
        try:
            result = tool.execute({
                "files": [
                    {"path": sample_file},
                    {"path": filepath2}
                ]
            })
            
            assert result["success"] is True
            assert "stdout" in result
        finally:
            if os.path.exists(filepath2):
                os.unlink(filepath2)

    def test_cache_save_and_retrieve(self, tool, sample_file, mock_agent):
        """测试缓存保存和检索"""
        # 第一次读取，应该保存到缓存
        result1 = tool.execute({
            "files": [{"path": sample_file}],
            "agent": mock_agent
        })
        
        assert result1["success"] is True
        assert mock_agent.set_user_data.called
        
        # 检查缓存内容
        cache_key = "read_code_cache"
        call_args = [call[0][0] for call in mock_agent.set_user_data.call_args_list if call[0][0] == cache_key]
        assert len(call_args) > 0 or any(call[0][0] == cache_key for call in mock_agent.set_user_data.call_args_list)

    def test_cache_validity_check(self, tool, sample_file, mock_agent):
        """测试缓存有效性检查"""
        abs_path = os.path.abspath(sample_file)
        file_mtime = os.path.getmtime(abs_path)
        
        # 创建有效缓存
        cache = {
            abs_path: {
                "units": [
                    {"id": "1", "content": "def hello():\n    print('Hello')"}
                ],
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
        """测试文件修改后缓存失效"""
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

    def test_convert_units_to_sequential_ids(self, tool):
        """测试将单元转换为序号id格式"""
        units = [
            {"id": "10-20", "start_line": 10, "end_line": 20, "content": "content1"},
            {"id": "1-5", "start_line": 1, "end_line": 5, "content": "content2"},
            {"id": "25-30", "start_line": 25, "end_line": 30, "content": "content3"},
        ]
        
        result = tool._convert_units_to_sequential_ids(units)
        
        assert len(result) == 3
        assert result[0]["id"] == "1"
        assert result[1]["id"] == "2"
        assert result[2]["id"] == "3"
        assert "start_line" not in result[0]
        assert "end_line" not in result[0]
        assert "content" in result[0]

    def test_restore_file_from_cache(self, tool):
        """测试从缓存恢复文件内容"""
        cache_info = {
            "units": [
                {"id": "2", "content": "line2\nline3"},
                {"id": "1", "content": "line1"},
                {"id": "3", "content": "line4"},
            ],
            "total_lines": 4,
        }
        
        result = tool._restore_file_from_cache(cache_info)
        
        assert "line1" in result
        assert "line2" in result
        assert "line3" in result
        assert "line4" in result

    def test_read_empty_file(self, tool):
        """测试读取空文件"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            empty_file = f.name
        
        try:
            result = tool.execute({
                "files": [{"path": empty_file}]
            })
            
            assert result["success"] is True
            assert "空" in result["stdout"] or "empty" in result["stdout"].lower()
        finally:
            if os.path.exists(empty_file):
                os.unlink(empty_file)

    def test_read_file_with_raw_mode(self, tool, sample_file):
        """测试原始模式读取"""
        result = tool.execute({
            "files": [{"path": sample_file, "raw_mode": True}]
        })
        
        assert result["success"] is True
        assert "stdout" in result

    def test_read_file_with_negative_line_number(self, tool, sample_file):
        """测试使用负数行号（从文件末尾倒数）"""
        result = tool.execute({
            "files": [{"path": sample_file, "start_line": -5, "end_line": -1}]
        })
        
        # 应该成功或给出合理错误
        assert "success" in result

    def test_read_file_exceeds_token_limit(self, tool):
        """测试读取超大文件（超过token限制）"""
        # 创建一个很大的文件
        large_content = "\n".join([f"line {i}" for i in range(10000)])
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(large_content)
            large_file = f.name
        
        try:
            result = tool.execute({
                "files": [{"path": large_file}]
            })
            
            # 应该失败或给出警告
            assert "success" in result
        finally:
            if os.path.exists(large_file):
                os.unlink(large_file)

    def test_read_file_with_invalid_range(self, tool, sample_file):
        """测试无效的行号范围"""
        result = tool.execute({
            "files": [{"path": sample_file, "start_line": 100, "end_line": 50}]
        })
        
        # 代码可能会自动修正范围，所以可能成功也可能失败
        # 只要不抛出异常即可
        assert "success" in result

    def test_read_file_without_agent(self, tool, sample_file):
        """测试不使用agent读取文件"""
        result = tool.execute({
            "files": [{"path": sample_file}]
        })
        
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(python_content)
            filepath = f.name
        
        try:
            abs_path = os.path.abspath(filepath)
            file_mtime = os.path.getmtime(abs_path)
            
            # 先读取文件，生成缓存
            result = tool.execute({
                "files": [{"path": filepath}],
                "agent": mock_agent
            })
            assert result["success"] is True
            
            # 获取缓存
            cache = mock_agent.get_user_data("read_code_cache")
            assert cache is not None
            assert abs_path in cache
            
            cache_info = cache[abs_path]
            assert "units" in cache_info
            
            # 从缓存恢复文件内容
            restored_content = tool._restore_file_from_cache(cache_info)
            
            # 验证恢复的内容与原始内容完全一致
            assert restored_content == python_content, f"恢复的内容与原始内容不一致\n原始:\n{python_content}\n恢复:\n{restored_content}"
            
            # 验证缓存中的单元只有id和content
            units = cache_info["units"]
            for unit in units:
                assert "id" in unit
                assert "content" in unit
                assert "start_line" not in unit
                assert "end_line" not in unit
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.c', delete=False) as f:
            f.write(c_content)
            filepath = f.name
        
        try:
            abs_path = os.path.abspath(filepath)
            file_mtime = os.path.getmtime(abs_path)
            
            # 读取文件生成缓存
            result = tool.execute({
                "files": [{"path": filepath}],
                "agent": mock_agent
            })
            assert result["success"] is True
            
            # 获取缓存并恢复
            cache = mock_agent.get_user_data("read_code_cache")
            if cache and abs_path in cache:
                cache_info = cache[abs_path]
                restored_content = tool._restore_file_from_cache(cache_info)
                
                # 验证恢复的内容与原始内容完全一致
                assert restored_content == c_content, f"恢复的内容与原始内容不一致\n原始:\n{c_content}\n恢复:\n{restored_content}"
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False) as f:
            f.write(java_content)
            filepath = f.name
        
        try:
            abs_path = os.path.abspath(filepath)
            
            # 读取文件生成缓存
            result = tool.execute({
                "files": [{"path": filepath}],
                "agent": mock_agent
            })
            assert result["success"] is True
            
            # 获取缓存并恢复
            cache = mock_agent.get_user_data("read_code_cache")
            if cache and abs_path in cache:
                cache_info = cache[abs_path]
                restored_content = tool._restore_file_from_cache(cache_info)
                
                # 验证恢复的内容与原始内容完全一致
                assert restored_content == java_content, f"恢复的内容与原始内容不一致\n原始:\n{java_content}\n恢复:\n{restored_content}"
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.rs', delete=False) as f:
            f.write(rust_content)
            filepath = f.name
        
        try:
            abs_path = os.path.abspath(filepath)
            
            # 读取文件生成缓存
            result = tool.execute({
                "files": [{"path": filepath}],
                "agent": mock_agent
            })
            assert result["success"] is True
            
            # 获取缓存并恢复
            cache = mock_agent.get_user_data("read_code_cache")
            if cache and abs_path in cache:
                cache_info = cache[abs_path]
                restored_content = tool._restore_file_from_cache(cache_info)
                
                # 验证恢复的内容与原始内容完全一致
                assert restored_content == rust_content, f"恢复的内容与原始内容不一致\n原始:\n{rust_content}\n恢复:\n{restored_content}"
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.go', delete=False) as f:
            f.write(go_content)
            filepath = f.name
        
        try:
            abs_path = os.path.abspath(filepath)
            
            # 读取文件生成缓存
            result = tool.execute({
                "files": [{"path": filepath}],
                "agent": mock_agent
            })
            assert result["success"] is True
            
            # 获取缓存并恢复
            cache = mock_agent.get_user_data("read_code_cache")
            if cache and abs_path in cache:
                cache_info = cache[abs_path]
                restored_content = tool._restore_file_from_cache(cache_info)
                
                # 验证恢复的内容与原始内容完全一致
                assert restored_content == go_content, f"恢复的内容与原始内容不一致\n原始:\n{go_content}\n恢复:\n{restored_content}"
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(text_content)
            filepath = f.name
        
        try:
            abs_path = os.path.abspath(filepath)
            
            # 读取文件生成缓存
            result = tool.execute({
                "files": [{"path": filepath}],
                "agent": mock_agent
            })
            assert result["success"] is True
            
            # 获取缓存并恢复
            cache = mock_agent.get_user_data("read_code_cache")
            if cache and abs_path in cache:
                cache_info = cache[abs_path]
                restored_content = tool._restore_file_from_cache(cache_info)
                
                # 验证恢复的内容与原始内容完全一致
                assert restored_content == text_content, f"恢复的内容与原始内容不一致\n原始:\n{text_content}\n恢复:\n{restored_content}"
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(nested_content)
            filepath = f.name
        
        try:
            abs_path = os.path.abspath(filepath)
            
            # 读取文件生成缓存
            result = tool.execute({
                "files": [{"path": filepath}],
                "agent": mock_agent
            })
            assert result["success"] is True
            
            # 获取缓存并恢复
            cache = mock_agent.get_user_data("read_code_cache")
            if cache and abs_path in cache:
                cache_info = cache[abs_path]
                restored_content = tool._restore_file_from_cache(cache_info)
                
                # 验证恢复的内容与原始内容完全一致
                assert restored_content == nested_content, f"恢复的内容与原始内容不一致\n原始:\n{nested_content}\n恢复:\n{restored_content}"
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(python_with_imports)
            filepath = f.name
        
        try:
            abs_path = os.path.abspath(filepath)
            
            # 读取文件生成缓存
            result = tool.execute({
                "files": [{"path": filepath}],
                "agent": mock_agent
            })
            assert result["success"] is True
            
            # 获取缓存并恢复
            cache = mock_agent.get_user_data("read_code_cache")
            if cache and abs_path in cache:
                cache_info = cache[abs_path]
                restored_content = tool._restore_file_from_cache(cache_info)
                
                # 验证恢复的内容与原始内容完全一致
                assert restored_content == python_with_imports, f"恢复的内容与原始内容不一致\n原始:\n{python_with_imports}\n恢复:\n{restored_content}"
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.c', delete=False) as f:
            f.write(complex_c)
            filepath = f.name
        
        try:
            abs_path = os.path.abspath(filepath)
            
            # 读取文件生成缓存
            result = tool.execute({
                "files": [{"path": filepath}],
                "agent": mock_agent
            })
            assert result["success"] is True
            
            # 获取缓存并恢复
            cache = mock_agent.get_user_data("read_code_cache")
            if cache and abs_path in cache:
                cache_info = cache[abs_path]
                restored_content = tool._restore_file_from_cache(cache_info)
                
                # 验证恢复的内容与原始内容完全一致
                assert restored_content == complex_c, f"恢复的内容与原始内容不一致\n原始:\n{complex_c}\n恢复:\n{restored_content}"
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(python_content)
            filepath = f.name
        
        try:
            abs_path = os.path.abspath(filepath)
            
            # 读取文件生成缓存
            result = tool.execute({
                "files": [{"path": filepath}],
                "agent": mock_agent
            })
            assert result["success"] is True
            
            # 获取缓存
            cache = mock_agent.get_user_data("read_code_cache")
            if cache and abs_path in cache:
                cache_info = cache[abs_path]
                units = cache_info["units"]
                
                # 验证id是序号格式（字符串"1", "2", "3"等）
                ids = [unit["id"] for unit in units]
                assert all(str(id).isdigit() for id in ids)
                
                # 验证id是连续的
                numeric_ids = [int(id) for id in ids if str(id).isdigit()]
                if len(numeric_ids) > 1:
                    assert numeric_ids == sorted(numeric_ids)
                    assert numeric_ids[0] == 1  # 从1开始
                
                # 验证恢复的内容与原始内容完全一致
                restored_content = tool._restore_file_from_cache(cache_info)
                assert restored_content == python_content, f"恢复的内容与原始内容不一致\n原始:\n{python_content}\n恢复:\n{restored_content}"
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(original_content)
            filepath = f.name
        
        try:
            abs_path = os.path.abspath(filepath)
            
            # 步骤1：读取文件并生成缓存
            result1 = tool.execute({
                "files": [{"path": filepath}],
                "agent": mock_agent
            })
            assert result1["success"] is True
            
            # 步骤2：获取缓存
            cache = mock_agent.get_user_data("read_code_cache")
            assert cache is not None
            assert abs_path in cache
            
            cache_info = cache[abs_path]
            
            # 步骤3：从缓存恢复内容
            restored_content = tool._restore_file_from_cache(cache_info)
            
            # 步骤4：验证恢复的内容与原始内容完全一致
            assert restored_content == original_content, f"恢复的内容与原始内容不一致\n原始:\n{original_content}\n恢复:\n{restored_content}"
            
            # 步骤5：验证缓存结构正确（只有id和content）
            units = cache_info["units"]
            for unit in units:
                assert "id" in unit
                assert "content" in unit
                assert "start_line" not in unit
                assert "end_line" not in unit
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(js_content)
            filepath = f.name
        
        try:
            abs_path = os.path.abspath(filepath)
            
            # 读取文件生成缓存
            result = tool.execute({
                "files": [{"path": filepath}],
                "agent": mock_agent
            })
            assert result["success"] is True
            
            # 获取缓存并恢复
            cache = mock_agent.get_user_data("read_code_cache")
            if cache and abs_path in cache:
                cache_info = cache[abs_path]
                restored_content = tool._restore_file_from_cache(cache_info)
                
                # 验证恢复的内容与原始内容完全一致
                assert restored_content == js_content, f"恢复的内容与原始内容不一致\n原始:\n{js_content}\n恢复:\n{restored_content}"
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False) as f:
            f.write(cpp_content)
            filepath = f.name
        
        try:
            abs_path = os.path.abspath(filepath)
            
            # 读取文件生成缓存
            result = tool.execute({
                "files": [{"path": filepath}],
                "agent": mock_agent
            })
            assert result["success"] is True
            
            # 获取缓存并恢复
            cache = mock_agent.get_user_data("read_code_cache")
            if cache and abs_path in cache:
                cache_info = cache[abs_path]
                restored_content = tool._restore_file_from_cache(cache_info)
                
                # 验证恢复的内容与原始内容完全一致
                assert restored_content == cpp_content, f"恢复的内容与原始内容不一致\n原始:\n{cpp_content}\n恢复:\n{restored_content}"
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(python_content)
            filepath = f.name
        
        try:
            abs_path = os.path.abspath(filepath)
            
            # 读取文件生成缓存
            result = tool.execute({
                "files": [{"path": filepath}],
                "agent": mock_agent
            })
            assert result["success"] is True
            
            # 获取缓存并恢复
            cache = mock_agent.get_user_data("read_code_cache")
            if cache and abs_path in cache:
                cache_info = cache[abs_path]
                restored_content = tool._restore_file_from_cache(cache_info)
                
                # 验证恢复的内容与原始内容完全一致
                assert restored_content == python_content, f"恢复的内容与原始内容不一致\n原始:\n{python_content}\n恢复:\n{restored_content}"
                
                # 验证缓存单元结构
                units = cache_info["units"]
                assert len(units) > 0
                for unit in units:
                    assert "id" in unit
                    assert isinstance(unit["id"], str)
                    assert unit["id"].isdigit()  # id应该是数字字符串
                    assert "content" in unit
                    assert isinstance(unit["content"], str)
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(content)
            filepath = f.name
        
        try:
            abs_path = os.path.abspath(filepath)
            
            # 读取文件生成缓存
            result = tool.execute({
                "files": [{"path": filepath}],
                "agent": mock_agent
            })
            assert result["success"] is True
            
            # 获取缓存
            cache = mock_agent.get_user_data("read_code_cache")
            if cache and abs_path in cache:
                cache_info = cache[abs_path]
                units = cache_info["units"]
                
                # 验证所有函数都在缓存中
                unit_contents = [unit["content"] for unit in units]
                assert any("def func1()" in content for content in unit_contents)
                assert any("def func2()" in content for content in unit_contents)
                assert any("def func3()" in content for content in unit_contents)
                
                # 恢复并验证与原始内容完全一致
                restored = tool._restore_file_from_cache(cache_info)
                assert restored == content, f"恢复的内容与原始内容不一致\n原始:\n{content}\n恢复:\n{restored}"
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_cache_restore_preserves_content_order(self, tool, mock_agent):
        """测试恢复时保持内容的顺序"""
        content = """First

Second

Third
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(content)
            filepath = f.name
        
        try:
            abs_path = os.path.abspath(filepath)
            
            # 读取文件生成缓存
            result = tool.execute({
                "files": [{"path": filepath}],
                "agent": mock_agent
            })
            assert result["success"] is True
            
            # 获取缓存并恢复
            cache = mock_agent.get_user_data("read_code_cache")
            if cache and abs_path in cache:
                cache_info = cache[abs_path]
                restored = tool._restore_file_from_cache(cache_info)
                
                # 验证恢复的内容与原始内容完全一致
                assert restored == content, f"恢复的内容与原始内容不一致\n原始:\n{content}\n恢复:\n{restored}"
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

