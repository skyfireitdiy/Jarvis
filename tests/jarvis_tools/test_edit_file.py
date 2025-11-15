# -*- coding: utf-8 -*-
"""jarvis_tools.edit_file 模块单元测试"""

import os
import tempfile
import time
from unittest.mock import MagicMock

import pytest

from jarvis.jarvis_tools.edit_file import EditFileTool


class TestEditFileTool:
    """测试 EditFileTool 类"""

    @pytest.fixture
    def tool(self):
        """创建测试用的 EditFileTool 实例"""
        return EditFileTool()

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
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(content)
            filepath = f.name
        
        yield filepath
        
        # 清理
        if os.path.exists(filepath):
            os.unlink(filepath)
        if os.path.exists(filepath + ".bak"):
            os.unlink(filepath + ".bak")

    @pytest.fixture
    def sample_file_with_cache(self, sample_file, mock_agent):
        """创建带缓存的示例文件"""
        abs_path = os.path.abspath(sample_file)
        file_mtime = os.path.getmtime(abs_path)
        
        # 创建有效缓存（新格式：id_list 和 blocks）
        cache = {
            abs_path: {
                "id_list": ["block-1", "block-2", "block-3"],
                "blocks": {
                    "block-1": {"content": "def hello():\n    print(\"Hello, World!\")\n"},
                    "block-2": {"content": "\ndef add(a, b):\n    return a + b\n"},
                    "block-3": {"content": "\nclass Calculator:\n    def __init__(self):\n        self.value = 0\n"},
                },
                "total_lines": 10,
                "read_time": time.time(),
                "file_mtime": file_mtime,
            }
        }
        
        # 设置 get_user_data 的返回值
        def get_user_data_side_effect(key):
            if key == "read_code_cache":
                return cache
            return None
        
        mock_agent.get_user_data.side_effect = get_user_data_side_effect
        
        return sample_file, mock_agent

    def test_replace_block(self, tool, sample_file_with_cache):
        """测试替换块"""
        sample_file, mock_agent = sample_file_with_cache
        
        result = tool.execute({
            "file_path": sample_file,
            "diffs": [{
                "type": "structured",
                "block_id": "block-1",
                "action": "replace",
                "content": "def hello():\n    print('Hi!')\n"
            }],
            "agent": mock_agent
        })
        
        assert result["success"] is True
        
        # 验证文件内容已更新
        with open(sample_file, 'r') as f:
            content = f.read()
            assert "Hi!" in content

    def test_delete_block(self, tool, sample_file_with_cache):
        """测试删除块（清空内容）"""
        sample_file, mock_agent = sample_file_with_cache
        
        result = tool.execute({
            "file_path": sample_file,
            "diffs": [{
                "type": "structured",
                "block_id": "block-1",
                "action": "delete"
            }],
            "agent": mock_agent
        })
        
        assert result["success"] is True
        
        # 验证缓存中的块内容已清空
        cache = mock_agent.get_user_data("read_code_cache")
        if cache:
            abs_path = os.path.abspath(sample_file)
            if abs_path in cache:
                blocks = cache[abs_path]["blocks"]
                block = blocks.get("block-1")
                if block:
                    assert block["content"] == ""

    def test_insert_before(self, tool, sample_file_with_cache):
        """测试在块前插入"""
        sample_file, mock_agent = sample_file_with_cache
        
        result = tool.execute({
            "file_path": sample_file,
            "diffs": [{
                "type": "structured",
                "block_id": "block-2",
                "action": "insert_before",
                "content": "# New comment\n"
            }],
            "agent": mock_agent
        })
        
        assert result["success"] is True
        
        # 验证文件内容已更新
        with open(sample_file, 'r') as f:
            content = f.read()
            assert "# New comment" in content

    def test_insert_after(self, tool, sample_file_with_cache):
        """测试在块后插入"""
        sample_file, mock_agent = sample_file_with_cache
        
        result = tool.execute({
            "file_path": sample_file,
            "diffs": [{
                "type": "structured",
                "block_id": "block-2",
                "action": "insert_after",
                "content": "# After comment\n"
            }],
            "agent": mock_agent
        })
        
        assert result["success"] is True
        
        # 验证文件内容已更新
        with open(sample_file, 'r') as f:
            content = f.read()
            assert "# After comment" in content

    def test_edit_without_cache(self, tool, sample_file, mock_agent):
        """测试在没有缓存的情况下编辑"""
        result = tool.execute({
            "file_path": sample_file,
            "diffs": [{
                "type": "structured",
                "block_id": "block-1",
                "action": "replace",
                "content": "new content"
            }],
            "agent": mock_agent
        })
        
        # 应该失败，提示需要先读取文件
        assert result["success"] is False
        assert "缓存" in result["stderr"] or "read_code" in result["stderr"].lower()

    def test_edit_with_invalid_block_id(self, tool, sample_file_with_cache):
        """测试使用无效的块id"""
        sample_file, mock_agent = sample_file_with_cache
        
        result = tool.execute({
            "file_path": sample_file,
            "diffs": [{
                "type": "structured",
                "block_id": "block-999",
                "action": "replace",
                "content": "new content"
            }],
            "agent": mock_agent
        })
        
        assert result["success"] is False
        assert "未找到" in result["stderr"] or "not found" in result["stderr"].lower()

    def test_edit_multiple_operations(self, tool, sample_file_with_cache):
        """测试多个编辑操作"""
        sample_file, mock_agent = sample_file_with_cache
        
        result = tool.execute({
            "file_path": sample_file,
            "diffs": [
                {
                    "type": "structured",
                    "block_id": "block-1",
                    "action": "replace",
                    "content": "def hello():\n    print('Modified')\n"
                },
                {
                    "type": "structured",
                    "block_id": "block-2",
                    "action": "insert_before",
                    "content": "# Before add\n"
                }
            ],
            "agent": mock_agent
        })
        
        assert result["success"] is True
        
        # 验证两个操作都生效
        with open(sample_file, 'r') as f:
            content = f.read()
            assert "Modified" in content
            assert "# Before add" in content

    def test_edit_with_missing_content(self, tool, sample_file_with_cache):
        """测试缺少content参数"""
        sample_file, mock_agent = sample_file_with_cache
        
        result = tool.execute({
            "file_path": sample_file,
            "diffs": [{
                "type": "structured",
                "block_id": "block-1",
                "action": "replace"
            }],
            "agent": mock_agent
        })
        
        assert result["success"] is False
        assert "content" in result["stderr"].lower()

    def test_edit_with_invalid_action(self, tool, sample_file_with_cache):
        """测试无效的操作类型"""
        sample_file, mock_agent = sample_file_with_cache
        
        result = tool.execute({
            "file_path": sample_file,
            "diffs": [{
                "type": "structured",
                "block_id": "block-1",
                "action": "invalid_action",
                "content": "content"
            }],
            "agent": mock_agent
        })
        
        assert result["success"] is False
        assert "action" in result["stderr"].lower()

    def test_edit_nonexistent_file(self, tool, mock_agent):
        """测试编辑不存在的文件"""
        # 创建无效缓存（新格式）
        cache = {
            "/nonexistent/file.py": {
                "id_list": ["block-1"],
                "blocks": {"block-1": {"content": "content"}},
                "total_lines": 1,
                "read_time": time.time(),
                "file_mtime": time.time(),
            }
        }
        mock_agent.get_user_data.return_value = cache
        
        result = tool.execute({
            "file_path": "/nonexistent/file.py",
            "diffs": [{
                "type": "structured",
                "block_id": "block-1",
                "action": "replace",
                "content": "new content"
            }],
            "agent": mock_agent
        })
        
        # 应该失败，因为缓存无效
        assert result["success"] is False

    def test_cache_update_after_edit(self, tool, sample_file, mock_agent):
        """测试编辑后缓存更新"""
        abs_path = os.path.abspath(sample_file)
        
        # 设置缓存，使其可以被修改（新格式）
        cache = {
            abs_path: {
                "id_list": ["block-1", "block-2"],
                "blocks": {
                    "block-1": {"content": "original content"},
                    "block-2": {"content": "other content"},
                },
                "total_lines": 2,
                "read_time": time.time(),
                "file_mtime": os.path.getmtime(abs_path),
            }
        }
        
        # 设置 get_user_data 的返回值
        def get_user_data_side_effect(key):
            if key == "read_code_cache":
                return cache
            return None
        
        mock_agent.get_user_data.side_effect = get_user_data_side_effect
        
        result = tool.execute({
            "file_path": sample_file,
            "diffs": [{
                "type": "structured",
                "block_id": "block-1",
                "action": "replace",
                "content": "new content\n"
            }],
            "agent": mock_agent
        })
        
        assert result["success"] is True
        
        # 验证缓存已更新
        assert mock_agent.set_user_data.called
        # 检查缓存中的内容是否已更新
        final_cache = cache[abs_path]
        blocks = final_cache["blocks"]
        block = blocks.get("block-1")
        assert block is not None
        assert "new content" in block["content"]

    def test_apply_structured_edit_to_cache(self, tool):
        """测试直接在缓存中应用编辑"""
        cache_info = {
            "id_list": ["block-1", "block-2"],
            "blocks": {
                "block-1": {"content": "original content"},
                "block-2": {"content": "other content"},
            },
            "total_lines": 2,
        }
        
        # 测试替换
        success, error = EditFileTool._apply_structured_edit_to_cache(
            cache_info, "block-1", "replace", "new content"
        )
        assert success is True
        assert cache_info["blocks"]["block-1"]["content"] == "new content"
        
        # 测试删除（清空）
        success, error = EditFileTool._apply_structured_edit_to_cache(
            cache_info, "block-2", "delete", None
        )
        assert success is True
        assert cache_info["blocks"]["block-2"]["content"] == ""
        
        # 测试插入前
        success, error = EditFileTool._apply_structured_edit_to_cache(
            cache_info, "block-1", "insert_before", "prefix "
        )
        assert success is True
        assert cache_info["blocks"]["block-1"]["content"].startswith("prefix ")
        
        # 测试插入后
        success, error = EditFileTool._apply_structured_edit_to_cache(
            cache_info, "block-1", "insert_after", " suffix"
        )
        assert success is True
        assert cache_info["blocks"]["block-1"]["content"].endswith(" suffix")

    def test_restore_file_from_cache(self, tool):
        """测试从缓存恢复文件"""
        cache_info = {
            "id_list": ["block-1", "block-2", "block-3"],
            "blocks": {
                "block-1": {"content": "first"},
                "block-2": {"content": "second"},
                "block-3": {"content": "third"},
            },
        }
        
        result = EditFileTool._restore_file_from_cache(cache_info)
        
        # 应该按id_list顺序拼接
        assert "first" in result
        assert "second" in result
        assert "third" in result
        # 验证顺序
        assert result.index("first") < result.index("second")
        assert result.index("second") < result.index("third")

    def test_validate_structured_diff(self, tool):
        """测试验证结构化diff"""
        # 有效的diff
        error, patch = EditFileTool._validate_structured({
            "block_id": "block-1",
            "action": "replace",
            "content": "new content"
        }, 0)
        
        assert error is None
        assert patch is not None
        assert patch["STRUCTURED_BLOCK_ID"] == "block-1"
        assert patch["STRUCTURED_ACTION"] == "replace"
        
        # 缺少block_id
        error, patch = EditFileTool._validate_structured({
            "action": "replace",
            "content": "content"
        }, 0)
        
        assert error is not None
        assert "block_id" in error["stderr"]
        
        # 无效的action
        error, patch = EditFileTool._validate_structured({
            "block_id": "block-1",
            "action": "invalid",
            "content": "content"
        }, 0)
        
        assert error is not None
        assert "action" in error["stderr"]

    def test_edit_with_empty_diffs(self, tool, sample_file_with_cache):
        """测试空的diffs列表"""
        sample_file, mock_agent = sample_file_with_cache
        
        result = tool.execute({
            "file_path": sample_file,
            "diffs": [],
            "agent": mock_agent
        })
        
        assert result["success"] is False
        assert "diffs" in result["stderr"].lower()

    def test_edit_file_validation(self, tool):
        """测试文件编辑参数验证"""
        # 缺少 file_path
        result = tool.execute({
            "diffs": [{
                "type": "structured",
                "block_id": "block-1",
                "action": "replace",
                "content": "content"
            }]
        })
        assert result["success"] is False
        assert "file_path" in result["stderr"].lower()

    def test_restore_empty_cache(self, tool):
        """测试恢复空缓存"""
        cache_info = {"id_list": [], "blocks": {}}
        result = EditFileTool._restore_file_from_cache(cache_info)
        assert result == ""
        
        # 测试 None 缓存
        result = EditFileTool._restore_file_from_cache(None)
        assert result == ""
        
        # 测试缺少 id_list 和 blocks 的缓存
        result = EditFileTool._restore_file_from_cache({})
        assert result == ""

    def test_edit_python_file_with_cache(self, tool, mock_agent):
        """测试编辑Python文件（带缓存）"""
        python_content = """def func1():
    return 1

def func2():
    return 2
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(python_content)
            filepath = f.name
        
        try:
            abs_path = os.path.abspath(filepath)
            file_mtime = os.path.getmtime(abs_path)
            
            # 创建缓存（新格式）
            cache = {
                abs_path: {
                    "id_list": ["block-1", "block-2"],
                    "blocks": {
                        "block-1": {"content": "def func1():\n    return 1\n"},
                        "block-2": {"content": "\ndef func2():\n    return 2\n"},
                    },
                    "total_lines": 6,
                    "read_time": time.time(),
                    "file_mtime": file_mtime,
                }
            }
            def get_user_data_side_effect(key):
                if key == "read_code_cache":
                    return cache
                return None
            
            mock_agent.get_user_data.side_effect = get_user_data_side_effect
            
            # 编辑文件
            result = tool.execute({
                "file_path": filepath,
                "diffs": [{
                    "type": "structured",
                    "block_id": "block-1",
                    "action": "replace",
                    "content": "def func1():\n    return 100\n"
                }],
                "agent": mock_agent
            })
            
            assert result["success"] is True
            
            # 验证文件已更新
            with open(filepath, 'r') as f:
                content = f.read()
                assert "return 100" in content
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)
            if os.path.exists(filepath + ".bak"):
                os.unlink(filepath + ".bak")

    def test_edit_c_file_with_cache(self, tool, mock_agent):
        """测试编辑C文件（带缓存）"""
        c_content = """#include <stdio.h>

void func1() {
    printf("1");
}

void func2() {
    printf("2");
}
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.c', delete=False) as f:
            f.write(c_content)
            filepath = f.name
        
        try:
            abs_path = os.path.abspath(filepath)
            file_mtime = os.path.getmtime(abs_path)
            
            # 创建缓存（新格式）
            cache = {
                abs_path: {
                    "id_list": ["block-1", "block-2", "block-3"],
                    "blocks": {
                        "block-1": {"content": "#include <stdio.h>\n\n"},
                        "block-2": {"content": "void func1() {\n    printf(\"1\");\n}\n\n"},
                        "block-3": {"content": "void func2() {\n    printf(\"2\");\n}\n"},
                    },
                    "total_lines": 10,
                    "read_time": time.time(),
                    "file_mtime": file_mtime,
                }
            }
            def get_user_data_side_effect(key):
                if key == "read_code_cache":
                    return cache
                return None
            
            mock_agent.get_user_data.side_effect = get_user_data_side_effect
            
            # 编辑文件
            result = tool.execute({
                "file_path": filepath,
                "diffs": [{
                    "type": "structured",
                    "block_id": "block-2",
                    "action": "replace",
                    "content": "void func1() {\n    printf(\"modified\");\n}\n\n"
                }],
                "agent": mock_agent
            })
            
            assert result["success"] is True
            
            # 验证文件已更新
            with open(filepath, 'r') as f:
                content = f.read()
                assert "modified" in content
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)
            if os.path.exists(filepath + ".bak"):
                os.unlink(filepath + ".bak")

    def test_edit_java_file_with_cache(self, tool, mock_agent):
        """测试编辑Java文件（带缓存）"""
        java_content = """public class Main {
    public void method1() {
    }
    
    public void method2() {
    }
}
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False) as f:
            f.write(java_content)
            filepath = f.name
        
        try:
            abs_path = os.path.abspath(filepath)
            file_mtime = os.path.getmtime(abs_path)
            
            # 创建缓存（新格式）
            cache = {
                abs_path: {
                    "id_list": ["block-1", "block-2", "block-3", "block-4"],
                    "blocks": {
                        "block-1": {"content": "public class Main {\n"},
                        "block-2": {"content": "    public void method1() {\n    }\n"},
                        "block-3": {"content": "    \n    public void method2() {\n    }\n"},
                        "block-4": {"content": "}\n"},
                    },
                    "total_lines": 7,
                    "read_time": time.time(),
                    "file_mtime": file_mtime,
                }
            }
            def get_user_data_side_effect(key):
                if key == "read_code_cache":
                    return cache
                return None
            
            mock_agent.get_user_data.side_effect = get_user_data_side_effect
            
            # 编辑文件
            result = tool.execute({
                "file_path": filepath,
                "diffs": [{
                    "type": "structured",
                    "block_id": "block-2",
                    "action": "insert_before",
                    "content": "    // New comment\n"
                }],
                "agent": mock_agent
            })
            
            assert result["success"] is True
            
            # 验证文件已更新
            with open(filepath, 'r') as f:
                content = f.read()
                assert "// New comment" in content
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)
            if os.path.exists(filepath + ".bak"):
                os.unlink(filepath + ".bak")

    def test_edit_rust_file_with_cache(self, tool, mock_agent):
        """测试编辑Rust文件（带缓存）"""
        rust_content = """fn main() {
    println!("Hello");
}

struct Point {
    x: i32,
    y: i32,
}
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.rs', delete=False) as f:
            f.write(rust_content)
            filepath = f.name
        
        try:
            abs_path = os.path.abspath(filepath)
            file_mtime = os.path.getmtime(abs_path)
            
            # 创建缓存（新格式）
            cache = {
                abs_path: {
                    "id_list": ["block-1", "block-2"],
                    "blocks": {
                        "block-1": {"content": "fn main() {\n    println!(\"Hello\");\n}\n\n"},
                        "block-2": {"content": "struct Point {\n    x: i32,\n    y: i32,\n}\n"},
                    },
                    "total_lines": 8,
                    "read_time": time.time(),
                    "file_mtime": file_mtime,
                }
            }
            def get_user_data_side_effect(key):
                if key == "read_code_cache":
                    return cache
                return None
            
            mock_agent.get_user_data.side_effect = get_user_data_side_effect
            
            # 编辑文件
            result = tool.execute({
                "file_path": filepath,
                "diffs": [{
                    "type": "structured",
                    "block_id": "block-1",
                    "action": "delete"
                }],
                "agent": mock_agent
            })
            
            assert result["success"] is True
            
            # 验证缓存中的块内容已清空
            final_cache = cache[abs_path]
            blocks = final_cache["blocks"]
            block = blocks.get("block-1")
            assert block is not None
            assert block["content"] == ""
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)
            if os.path.exists(filepath + ".bak"):
                os.unlink(filepath + ".bak")

    def test_edit_go_file_with_cache(self, tool, mock_agent):
        """测试编辑Go文件（带缓存）"""
        go_content = """package main

func main() {
    fmt.Println("Hello")
}

type Point struct {
    x int
    y int
}
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.go', delete=False) as f:
            f.write(go_content)
            filepath = f.name
        
        try:
            abs_path = os.path.abspath(filepath)
            file_mtime = os.path.getmtime(abs_path)
            
            # 创建缓存（新格式）
            cache = {
                abs_path: {
                    "id_list": ["block-1", "block-2", "block-3"],
                    "blocks": {
                        "block-1": {"content": "package main\n\n"},
                        "block-2": {"content": "func main() {\n    fmt.Println(\"Hello\")\n}\n\n"},
                        "block-3": {"content": "type Point struct {\n    x int\n    y int\n}\n"},
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
            
            # 编辑文件
            result = tool.execute({
                "file_path": filepath,
                "diffs": [{
                    "type": "structured",
                    "block_id": "block-2",
                    "action": "insert_after",
                    "content": "    fmt.Println(\"World\")\n"
                }],
                "agent": mock_agent
            })
            
            assert result["success"] is True
            
            # 验证文件已更新
            with open(filepath, 'r') as f:
                content = f.read()
                assert "World" in content
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)
            if os.path.exists(filepath + ".bak"):
                os.unlink(filepath + ".bak")

    def test_edit_restore_from_cache_after_edit(self, tool, mock_agent):
        """测试编辑后从缓存恢复文件"""
        original_content = """def test():
    return 1
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(original_content)
            filepath = f.name
        
        try:
            abs_path = os.path.abspath(filepath)
            file_mtime = os.path.getmtime(abs_path)
            
            # 创建初始缓存（新格式）
            cache = {
                abs_path: {
                    "id_list": ["block-1"],
                    "blocks": {
                        "block-1": {"content": "def test():\n    return 1\n"},
                    },
                    "total_lines": 2,
                    "read_time": time.time(),
                    "file_mtime": file_mtime,
                }
            }
            def get_user_data_side_effect(key):
                if key == "read_code_cache":
                    return cache
                return None
            
            mock_agent.get_user_data.side_effect = get_user_data_side_effect
            
            # 编辑文件
            result = tool.execute({
                "file_path": filepath,
                "diffs": [{
                    "type": "structured",
                    "block_id": "block-1",
                    "action": "replace",
                    "content": "def test():\n    return 999\n"
                }],
                "agent": mock_agent
            })
            
            assert result["success"] is True
            
            # 从更新后的缓存恢复（缓存会被修改）
            final_cache = cache  # 直接使用被修改的cache字典
            if final_cache and abs_path in final_cache:
                cache_info = final_cache[abs_path]
                restored = EditFileTool._restore_file_from_cache(cache_info)
                
                # 验证恢复的内容包含修改后的内容
                assert "return 999" in restored
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)
            if os.path.exists(filepath + ".bak"):
                os.unlink(filepath + ".bak")

    def test_edit_multiple_languages_round_trip(self, tool, mock_agent):
        """测试多种语言的完整编辑往返"""
        languages = [
            (".py", """def func():
    pass
"""),
            (".c", """void func() {
}
"""),
            (".java", """public void func() {
}
"""),
            (".rs", """fn func() {
}
"""),
            (".go", """func func() {
}
"""),
        ]
        
        for suffix, content in languages:
            with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False) as f:
                f.write(content)
                filepath = f.name
            
            try:
                abs_path = os.path.abspath(filepath)
                file_mtime = os.path.getmtime(abs_path)
                
                # 创建缓存（新格式）
                cache = {
                    abs_path: {
                        "id_list": ["block-1"],
                        "blocks": {
                            "block-1": {"content": content},
                        },
                        "total_lines": len(content.split('\n')),
                        "read_time": time.time(),
                        "file_mtime": file_mtime,
                    }
                }
                def get_user_data_side_effect(key):
                    if key == "read_code_cache":
                        return cache
                    return None
                
                mock_agent.get_user_data.side_effect = get_user_data_side_effect
                
                # 编辑文件
                result = tool.execute({
                    "file_path": filepath,
                    "diffs": [{
                        "type": "structured",
                        "block_id": "block-1",
                        "action": "replace",
                        "content": content.replace("func", "modified_func")
                    }],
                    "agent": mock_agent
                })
                
                assert result["success"] is True
                
                # 验证文件已更新
                with open(filepath, 'r') as f:
                    file_content = f.read()
                    assert "modified_func" in file_content
            finally:
                if os.path.exists(filepath):
                    os.unlink(filepath)
                if os.path.exists(filepath + ".bak"):
                    os.unlink(filepath + ".bak")

