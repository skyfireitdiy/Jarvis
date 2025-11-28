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
        
        # 创建有效缓存（新格式：id_list 和 blocks）
        cache = {
            abs_path: {
                "id_list": ["block-1"],
                "blocks": {
                    "block-1": {"content": "def hello():\n    print('Hello')"}
                },
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

    def test_cache_invalid_after_external_file_modification(self, tool, sample_file, mock_agent):
        """测试外部修改文件后缓存失效（实际修改文件）"""
        abs_path = os.path.abspath(sample_file)
        
        # 第一次读取文件，建立缓存
        original_content = """def hello():
    print("Hello, World!")

def add(a, b):
    return a + b
"""
        with open(abs_path, 'w') as f:
            f.write(original_content)
        
        # 等待一小段时间，确保文件时间戳稳定
        time.sleep(0.2)
        
        # 第一次读取，建立缓存
        result1 = tool.execute({
            "files": [{"path": sample_file}],
            "agent": mock_agent
        })
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
        with open(abs_path, 'w') as f:
            f.write(modified_content)
        
        # 等待一小段时间，确保文件时间戳更新
        time.sleep(0.2)
        
        # 验证缓存失效
        cache_info_after = tool._get_file_cache(mock_agent, abs_path)
        is_valid_after = tool._is_cache_valid(cache_info_after, abs_path)
        assert is_valid_after is False, "文件被外部修改后，缓存应该失效"
        
        # 再次读取文件，应该读取新内容而不是使用缓存
        result2 = tool.execute({
            "files": [{"path": sample_file}],
            "agent": mock_agent
        })
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
            os.path.getmtime(abs_path)
            
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
            # 检查新格式（id_list 和 blocks）
            assert "id_list" in cache_info and "blocks" in cache_info
            
            # 从缓存恢复文件内容
            restored_content = tool._restore_file_from_cache(cache_info)
            
            # 验证恢复的内容与原始内容完全一致
            assert restored_content == python_content, f"恢复的内容与原始内容不一致\n原始:\n{python_content}\n恢复:\n{restored_content}"
            
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.c', delete=False) as f:
            f.write(c_content)
            filepath = f.name
        
        try:
            abs_path = os.path.abspath(filepath)
            os.path.getmtime(abs_path)
            
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
                
                # 从新格式（id_list + blocks）中提取内容
                blocks = cache_info["blocks"]
                unit_contents = [block["content"] for block in blocks.values()]
                
                # 验证所有函数都在缓存中
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


    def test_merged_ranges_deduplication(self, tool, mock_agent):
        """测试同一文件多个重叠范围读取时的去重功能"""
        content = '''class MyClass:
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
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(content)
            filepath = f.name
        try:
            import re
            # 测试两个重叠范围
            result = tool.execute({
                "files": [
                    {"path": filepath, "start_line": 1, "end_line": 10},
                    {"path": filepath, "start_line": 5, "end_line": 15}
                ],
                "agent": mock_agent
            })
            assert result["success"] is True
            # 检查没有重复的block_id
            block_ids = re.findall(r'\[id:(block-\d+)\]', result['stdout'])
            unique_ids = set(block_ids)
            assert len(block_ids) == len(unique_ids), f"存在重复block: {block_ids}"
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_merged_ranges_multiple_requests(self, tool, mock_agent):
        """测试同一文件三个及以上范围请求的去重"""
        content = '''def func1():
    pass

def func2():
    pass

def func3():
    pass

def func4():
    pass

def func5():
    pass
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(content)
            filepath = f.name
        try:
            import re
            # 测试三个范围请求
            result = tool.execute({
                "files": [
                    {"path": filepath, "start_line": 1, "end_line": 5},
                    {"path": filepath, "start_line": 3, "end_line": 10},
                    {"path": filepath, "start_line": 8, "end_line": 15}
                ],
                "agent": mock_agent
            })
            assert result["success"] is True
            # 检查没有重复的block_id
            block_ids = re.findall(r'\[id:(block-\d+)\]', result['stdout'])
            unique_ids = set(block_ids)
            assert len(block_ids) == len(unique_ids), f"存在重复block: {block_ids}"
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_merged_ranges_different_files(self, tool, mock_agent):
        """测试不同文件的多范围请求不会被错误合并"""
        content1 = '''def func_a():
    pass
'''
        content2 = '''def func_b():
    pass
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f1, \
             tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f2:
            f1.write(content1)
            f2.write(content2)
            filepath1 = f1.name
            filepath2 = f2.name
        try:
            result = tool.execute({
                "files": [
                    {"path": filepath1, "start_line": 1, "end_line": -1},
                    {"path": filepath2, "start_line": 1, "end_line": -1}
                ],
                "agent": mock_agent
            })
            assert result["success"] is True
            # 两个文件都应该被读取
            assert filepath1 in result['stdout'] or "func_a" in result['stdout']
            assert filepath2 in result['stdout'] or "func_b" in result['stdout']
        finally:
            if os.path.exists(filepath1):
                os.unlink(filepath1)
            if os.path.exists(filepath2):
                os.unlink(filepath2)

    def test_merged_ranges_without_agent(self, tool):
        """测试无agent时多范围请求的去重"""
        content = '''class Test:
    def method1(self):
        pass
    
    def method2(self):
        pass
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(content)
            filepath = f.name
        try:
            import re
            # 无agent时也应该去重
            result = tool.execute({
                "files": [
                    {"path": filepath, "start_line": 1, "end_line": 4},
                    {"path": filepath, "start_line": 3, "end_line": 7}
                ]
            })
            assert result["success"] is True
            # 检查没有重复的block_id
            block_ids = re.findall(r'\[id:(block-\d+)\]', result['stdout'])
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(content)
            filepath = f.name
        try:
            result = tool.execute({
                "files": [{"path": filepath}]
            })
            assert result["success"] is True
            # 应该被拆分成多个block（类头部+多个方法）
            block_count = result['stdout'].count('[id:block-')
            assert block_count > 1, f"只有一个类的文件应该被拆分成多个block，实际: {block_count}"
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)
    def test_get_blocks_from_cache_returns_real_line_numbers(self, tool, mock_agent):
        """测试 _get_blocks_from_cache 返回真实的文件行号而非块内相对行号"""
        content = '''def func1():
    print("line 2")

def func2():
    print("line 5")

def func3():
    print("line 8")
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
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
                        "block-1": {"content": "def func1():\n    print(\"line 2\")"},
                        "block-2": {"content": "def func2():\n    print(\"line 5\")"},
                        "block-3": {"content": "def func3():\n    print(\"line 8\")"}
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
            assert blocks[0].get("start_line") == 1, \
                f"第一个块应从第1行开始，实际: {blocks[0].get('start_line')}"
           
            # 第二个块从第3行开始（func1占2行，所以func2从第3行开始）
            assert blocks[1].get("start_line") == 3, \
                f"第二个块应从第3行开始，实际: {blocks[1].get('start_line')}"
           
            # 第三个块从第5行开始（func2占2行，所以func3从第5行开始）
            assert blocks[2].get("start_line") == 5, \
                f"第三个块应从第5行开始，实际: {blocks[2].get('start_line')}"
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_formatted_output_shows_real_line_numbers(self, tool):
        """测试格式化输出显示真实的文件行号"""
        content = '''# 第1行注释
def hello():
    # 第3行
    print("Hello")  # 第4行

def world():
    # 第7行
    print("World")  # 第8行
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(content)
            filepath = f.name
       
        try:
            result = tool.execute({
                "files": [{"path": filepath}]
            })
           
            assert result["success"] is True
            stdout = result["stdout"]
           
            # 验证输出中包含真实的行号（不是每个块都从1开始）
            # Python语法解析器可能会把顶部注释与第一个函数合并
            # 重要的是：后续块的行号应该是真实行号，不是从1开始
           
            # 检查是否有第6、7、8行（world函数应该在这些行）
            lines = stdout.split('\n')
            line_numbers_found = set()
            for line in lines:
                # 匹配行号格式（如 "   6:"）
                if ':' in line and line.strip():
                    parts = line.split(':')
                    if parts[0].strip().isdigit():
                        line_numbers_found.add(int(parts[0].strip()))
           
            # 验证找到了真实的行号（如第6、7、8行）
            # 如果行号是从块内相对计算的，world函数会从第1行开始，而不是第6行
            assert 6 in line_numbers_found or 7 in line_numbers_found, \
                f"应找到第6或7行（world函数位置），实际找到: {line_numbers_found}"

            # 至少应该找到多个行号，且有大于5的行号（证明不是相对行号）
            max_line = max(line_numbers_found) if line_numbers_found else 0
            assert max_line >= 6, \
                f"最大行号应>=6（证明是真实行号），实际最大: {max_line}"
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

