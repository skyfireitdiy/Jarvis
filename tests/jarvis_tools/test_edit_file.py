# -*- coding: utf-8 -*-
"""jarvis_tools.edit_file_free 模块单元测试"""

import os
import tempfile

import pytest

from jarvis.jarvis_tools.edit_file_free import EditFileFreeTool


# TestEditFileTool class removed - edit_file_structed has been deleted


class TestEditFileFreeTool:
    """测试 EditFileFreeTool 类"""

    @pytest.fixture
    def tool(self):
        """创建测试用的 EditFileFreeTool 实例"""
        return EditFileFreeTool()

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
    
    def multiply(self, a, b):
        return a * b
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(content)
            filepath = f.name

        yield filepath

        # 清理
        if os.path.exists(filepath):
            os.unlink(filepath)
        if os.path.exists(filepath + ".bak"):
            os.unlink(filepath + ".bak")

    def test_replace_function_by_name(self, tool, sample_file):
        """测试：通过函数名替换函数"""
        new_code = """def add(a, b):
    return a + b + 1
"""
        args = {
            "files": [
                {
                    "file_path": sample_file,
                    "diffs": [{"content": new_code}],
                }
            ]
        }

        result = tool.execute(args)
        assert result["success"] is True

        # 验证完整文件内容
        expected_content = """def hello():
    print("Hello, World!")

def add(a, b):
    return a + b + 1

class Calculator:
    def __init__(self):
        self.value = 0
    
    def multiply(self, a, b):
        return a * b
"""
        with open(sample_file, "r", encoding="utf-8") as f:
            actual_content = f.read()
        assert actual_content == expected_content

    def test_replace_class_by_name(self, tool, sample_file):
        """测试：通过类名替换类"""
        new_code = """class Calculator:
    def __init__(self):
        self.value = 0
        self.history = []
    
    def multiply(self, a, b):
        return a * b
"""
        args = {
            "files": [
                {
                    "file_path": sample_file,
                    "diffs": [{"content": new_code}],
                }
            ]
        }

        result = tool.execute(args)
        assert result["success"] is True

        # 验证完整文件内容
        expected_content = """def hello():
    print("Hello, World!")

def add(a, b):
    return a + b

class Calculator:
    def __init__(self):
        self.value = 0
        self.history = []
    
    def multiply(self, a, b):
        return a * b
"""
        with open(sample_file, "r", encoding="utf-8") as f:
            actual_content = f.read()
        assert actual_content == expected_content

    def test_append_when_no_match(self, tool, sample_file):
        """测试：找不到匹配时追加到文件末尾"""
        new_code = """def new_function():
    print("New function")
"""
        args = {
            "files": [
                {
                    "file_path": sample_file,
                    "diffs": [{"content": new_code}],
                }
            ]
        }

        result = tool.execute(args)
        assert result["success"] is True

        # 验证完整文件内容（新代码应该追加到末尾）
        expected_content = """def hello():
    print("Hello, World!")

def add(a, b):
    return a + b

class Calculator:
    def __init__(self):
        self.value = 0
    
    def multiply(self, a, b):
        return a * b
def new_function():
    print("New function")
"""
        with open(sample_file, "r", encoding="utf-8") as f:
            actual_content = f.read()
        assert actual_content == expected_content

    def test_fuzzy_match_replace(self, tool, sample_file):
        """测试：模糊匹配替换"""
        # 提供略有差异的代码
        new_code = """def hello():
    print("Hello, World!")
    print("Updated")
"""
        args = {
            "files": [
                {
                    "file_path": sample_file,
                    "diffs": [{"content": new_code}],
                }
            ]
        }

        result = tool.execute(args)
        assert result["success"] is True

        # 验证完整文件内容
        expected_content = """def hello():
    print("Hello, World!")
    print("Updated")
def add(a, b):
    return a + b

class Calculator:
    def __init__(self):
        self.value = 0
    
    def multiply(self, a, b):
        return a * b
"""
        with open(sample_file, "r", encoding="utf-8") as f:
            actual_content = f.read()
        assert actual_content == expected_content

    def test_replace_when_match_found(self, tool, sample_file):
        """测试：找到匹配时进行替换"""
        new_code = """def add(a, b):
    return a + b + 10
"""
        args = {
            "files": [
                {
                    "file_path": sample_file,
                    "diffs": [{"content": new_code}],
                }
            ]
        }

        result = tool.execute(args)
        assert result["success"] is True

        # 验证完整文件内容
        expected_content = """def hello():
    print("Hello, World!")

def add(a, b):
    return a + b + 10

class Calculator:
    def __init__(self):
        self.value = 0
    
    def multiply(self, a, b):
        return a * b
"""
        with open(sample_file, "r", encoding="utf-8") as f:
            actual_content = f.read()
        assert actual_content == expected_content

    def test_multiple_diffs(self, tool, sample_file):
        """测试：多个编辑操作"""
        args = {
            "files": [
                {
                    "file_path": sample_file,
                    "diffs": [
                        {"content": 'def hello():\n    print("Updated Hello")\n'},
                        {"content": "def new_func():\n    pass\n"},
                    ],
                }
            ]
        }

        result = tool.execute(args)
        assert result["success"] is True

        # 验证完整文件内容
        expected_content = """def hello():
    print("Updated Hello")

def add(a, b):
    return a + b

class Calculator:
    def __init__(self):
        self.value = 0
    
    def multiply(self, a, b):
        return a * b
def new_func():
    pass
"""
        with open(sample_file, "r", encoding="utf-8") as f:
            actual_content = f.read()
        assert actual_content == expected_content

    def test_multiple_files(self, tool):
        """测试：同时编辑多个文件"""
        # 创建两个文件
        file1_content = "def func1():\n    pass\n"
        file2_content = "def func2():\n    pass\n"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f1:
            f1.write(file1_content)
            filepath1 = f1.name

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f2:
            f2.write(file2_content)
            filepath2 = f2.name

        try:
            args = {
                "files": [
                    {
                        "file_path": filepath1,
                        "diffs": [{"content": "def func1():\n    return 1\n"}],
                    },
                    {
                        "file_path": filepath2,
                        "diffs": [{"content": "def func2():\n    return 2\n"}],
                    },
                ]
            }

            result = tool.execute(args)
            assert result["success"] is True

            # 验证两个文件的完整内容
            expected_content1 = "def func1():\n    return 1\n"
            with open(filepath1, "r", encoding="utf-8") as f:
                actual_content1 = f.read()
            assert actual_content1 == expected_content1

            expected_content2 = "def func2():\n    return 2\n"
            with open(filepath2, "r", encoding="utf-8") as f:
                actual_content2 = f.read()
            assert actual_content2 == expected_content2

        finally:
            for filepath in [filepath1, filepath2]:
                if os.path.exists(filepath):
                    os.unlink(filepath)
                if os.path.exists(filepath + ".bak"):
                    os.unlink(filepath + ".bak")

    def test_validate_new_code_required(self, tool, sample_file):
        """测试：验证 new_code 参数必需"""
        args = {
            "files": [
                {
                    "file_path": sample_file,
                    "diffs": [{}],  # 缺少 new_code
                }
            ]
        }

        result = tool.execute(args)
        assert result["success"] is False
        # 错误信息可能在 stdout 或 stderr 中
        error_msg = (result.get("stderr", "") + " " + result.get("stdout", "")).lower()
        assert "content" in error_msg

    def test_validate_new_code_not_empty(self, tool, sample_file):
        """测试：验证 new_code 不能为空"""
        args = {
            "files": [
                {
                    "file_path": sample_file,
                    "diffs": [{"content": ""}],
                }
            ]
        }

        result = tool.execute(args)
        assert result["success"] is False
        # 错误信息可能在 stdout 或 stderr 中
        error_msg = result.get("stderr", "") + " " + result.get("stdout", "")
        assert "不能为空" in error_msg or "empty" in error_msg.lower()

    def test_extract_code_features(self, tool):
        """测试：提取代码特征"""
        code = """def my_function(x, y):
    class MyClass:
        pass
    import os
    return x + y
"""
        features = EditFileFreeTool._extract_code_features(code)

        assert "my_function" in features["function_names"]
        assert "MyClass" in features["class_names"]
        assert len(features["keywords"]) > 0

    def test_find_best_match_position(self, tool):
        """测试：查找最佳匹配位置"""
        content = """def hello():
    print("Hello")

def add(a, b):
    return a + b
"""
        new_code = """def add(a, b):
    return a + b + 1
"""
        match_result, error_msg = EditFileFreeTool._find_best_match_position(
            content, new_code
        )

        assert match_result is not None
        start_pos, end_pos, similarity = match_result
        assert similarity >= 0.6  # 默认阈值
        assert start_pos < end_pos

    def test_find_best_match_position_no_match(self, tool):
        """测试：找不到匹配位置"""
        content = """def hello():
    print("Hello")
"""
        old_code = """def completely_different():
    return None
"""
        match_result, error_msg = EditFileFreeTool._find_best_match_position(
            content, old_code
        )

        assert match_result is None

    def test_apply_free_edit_replace(self, tool):
        """测试：应用替换编辑"""
        content = """def hello():
    print("Hello")
"""
        diff = {
            "content": """def hello():
    print("Updated")
""",
            "is_diff": False,
            "old_code": """def hello():
    print("Updated")
""",
            "new_code": """def hello():
    print("Updated")
""",
        }

        success, result, warning = EditFileFreeTool._apply_free_edit_to_content(
            content, diff
        )
        assert success is True
        expected_content = """def hello():
    print("Updated")
"""
        assert result == expected_content

    def test_apply_free_edit_append(self, tool):
        """测试：应用追加编辑"""
        content = """def hello():
    print("Hello")
"""
        diff = {
            "content": """def new_func():
    pass
""",
            "is_diff": False,
            "old_code": """def new_func():
    pass
""",
            "new_code": """def new_func():
    pass
""",
        }

        success, result, warning = EditFileFreeTool._apply_free_edit_to_content(
            content, diff
        )
        assert success is True
        expected_content = """def hello():
    print("Hello")
def new_func():
    pass
"""
        assert result == expected_content
        assert warning is not None
        assert "追加" in warning or "append" in warning.lower()

    def test_file_with_special_characters(self, tool):
        """测试：包含特殊字符的代码"""
        content = """def test():
    s = "Hello 'World'"
    s2 = 'Hello "World"'
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(content)
            filepath = f.name

        try:
            new_code = """def test():
    s = "Hello 'Universe'"
    s2 = 'Hello "Universe"'
"""
            args = {
                "files": [
                    {
                        "file_path": filepath,
                        "diffs": [{"content": new_code}],
                    }
                ]
            }

            result = tool.execute(args)
            assert result["success"] is True

            # 验证完整文件内容
            expected_content = """def test():
    s = "Hello 'Universe'"
    s2 = 'Hello "Universe"'
"""
            with open(filepath, "r", encoding="utf-8") as f:
                actual_content = f.read()
            assert actual_content == expected_content

        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)
            if os.path.exists(filepath + ".bak"):
                os.unlink(filepath + ".bak")

    def test_diff_format_add_line(self, tool, sample_file):
        """测试：diff 格式 - 添加一行"""
        diff_content = """ def add(a, b):
-    return a + b
+    result = a + b
+    return result
"""
        args = {
            "files": [
                {
                    "file_path": sample_file,
                    "diffs": [{"content": diff_content}],
                }
            ]
        }

        result = tool.execute(args)
        assert result["success"] is True

        # 验证完整文件内容
        expected_content = """def hello():
    print("Hello, World!")
def add(a, b):
    result = a + b
    return result

class Calculator:
    def __init__(self):
        self.value = 0
    
    def multiply(self, a, b):
        return a * b
"""
        with open(sample_file, "r", encoding="utf-8") as f:
            actual_content = f.read()
        assert actual_content == expected_content

    def test_diff_format_delete_line(self, tool, sample_file):
        """测试：diff 格式 - 删除一行"""
        diff_content = """ def hello():
-    print("Hello, World!")
+    print("Updated Hello")
"""
        args = {
            "files": [
                {
                    "file_path": sample_file,
                    "diffs": [{"content": diff_content}],
                }
            ]
        }

        result = tool.execute(args)
        assert result["success"] is True

        # 验证完整文件内容
        expected_content = """def hello():
    print("Updated Hello")

def add(a, b):
    return a + b

class Calculator:
    def __init__(self):
        self.value = 0
    
    def multiply(self, a, b):
        return a * b
"""
        with open(sample_file, "r", encoding="utf-8") as f:
            actual_content = f.read()
        assert actual_content == expected_content

    def test_diff_format_replace_function(self, tool, sample_file):
        """测试：diff 格式 - 替换整个函数"""
        diff_content = """ def add(a, b):
-    return a + b
+    return a + b + 1
"""
        args = {
            "files": [
                {
                    "file_path": sample_file,
                    "diffs": [{"content": diff_content}],
                }
            ]
        }

        result = tool.execute(args)
        assert result["success"] is True

        # 验证完整文件内容
        expected_content = """def hello():
    print("Hello, World!")
def add(a, b):
    return a + b + 1

class Calculator:
    def __init__(self):
        self.value = 0
    
    def multiply(self, a, b):
        return a * b
"""
        with open(sample_file, "r", encoding="utf-8") as f:
            actual_content = f.read()
        assert actual_content == expected_content

    def test_diff_format_add_only(self, tool, sample_file):
        """测试：diff 格式 - 只有新增（没有旧代码）"""
        diff_content = """+def new_function():
+    print("New function")
"""
        args = {
            "files": [
                {
                    "file_path": sample_file,
                    "diffs": [{"content": diff_content}],
                }
            ]
        }

        result = tool.execute(args)
        assert result["success"] is True

        # 验证完整文件内容（应该追加到末尾）
        with open(sample_file, "r", encoding="utf-8") as f:
            actual_content = f.read()
        assert "def new_function():" in actual_content
        assert 'print("New function")' in actual_content

    def test_is_diff_format(self, tool):
        """测试：判断是否为 diff 格式"""
        # diff 格式
        assert EditFileFreeTool._is_diff_format("+new line\n")
        assert EditFileFreeTool._is_diff_format("-old line\n")
        assert EditFileFreeTool._is_diff_format(" unchanged\n+new\n")
        assert EditFileFreeTool._is_diff_format(" unchanged\n-old\n")

        # 不是 diff 格式
        assert not EditFileFreeTool._is_diff_format("normal code\n")
        assert not EditFileFreeTool._is_diff_format("")
        assert not EditFileFreeTool._is_diff_format("+++file header\n")
        assert not EditFileFreeTool._is_diff_format("---file header\n")

    def test_parse_diff_content(self, tool):
        """测试：解析 diff 格式内容"""
        diff_content = """ def hello():
-    print("Old")
+    print("New")
     return True
"""
        old_code, new_code = EditFileFreeTool._parse_diff_content(diff_content)

        assert 'print("Old")' in old_code
        assert 'print("Old")' not in new_code
        assert 'print("New")' in new_code
        assert 'print("New")' not in old_code
        assert "def hello():" in old_code
        assert "def hello():" in new_code
        assert "return True" in old_code
        assert "return True" in new_code
