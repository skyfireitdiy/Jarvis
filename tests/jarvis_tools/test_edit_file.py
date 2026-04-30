# -*- coding: utf-8 -*-
"""jarvis_tools.edit_file 模块单元测试"""

import os
import tempfile

import pytest

from jarvis.jarvis_tools.edit_file import EditFileNormalTool


class TestEditFileNormalTool:
    """测试 EditFileNormalTool 类"""

    @pytest.fixture
    def tool(self):
        """创建测试用的 EditFileNormalTool 实例"""
        return EditFileNormalTool()

    @pytest.fixture
    def temp_file(self):
        """创建临时文件"""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("""def hello():
    print("Hello, World!")

def add(a, b):
    return a + b

def multiply(x, y):
    return x * y
""")
            temp_path = f.name

        yield temp_path

        # 清理
        if os.path.exists(temp_path):
            os.remove(temp_path)
        if os.path.exists(temp_path + ".bak"):
            os.remove(temp_path + ".bak")

    @pytest.fixture
    def temp_file2(self):
        """创建第二个临时文件"""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("""class Test:
    def method1(self):
        pass
    
    def method2(self):
        pass
""")
            temp_path = f.name

        yield temp_path

        # 清理
        if os.path.exists(temp_path):
            os.remove(temp_path)
        if os.path.exists(temp_path + ".bak"):
            os.remove(temp_path + ".bak")

    def test_single_edit_success(self, tool, temp_file):
        """测试单处编辑成功"""
        args = {
            "files": [
                {
                    "file_path": temp_file,
                    "diffs": [
                        {
                            "search": 'def hello():\n    print("Hello, World!")',
                            "replace": 'def hello():\n    print("Hello, Jarvis!")',
                        }
                    ],
                }
            ]
        }

        result = tool.execute(args)

        assert result["success"] is True
        assert "修改成功" in result["stdout"]

        # 验证文件内容已更新
        with open(temp_file, "r", encoding="utf-8") as f:
            content = f.read()
            assert 'print("Hello, Jarvis!")' in content
            assert 'print("Hello, World!")' not in content

    def test_multiple_edits_success(self, tool, temp_file):
        """测试多处编辑成功"""
        args = {
            "files": [
                {
                    "file_path": temp_file,
                    "diffs": [
                        {
                            "search": 'def hello():\n    print("Hello, World!")',
                            "replace": 'def hello():\n    print("Hello, Jarvis!")',
                        },
                        {
                            "search": "def add(a, b):\n    return a + b",
                            "replace": "def add(a, b):\n    return a + b + 1",
                        },
                    ],
                }
            ]
        }

        result = tool.execute(args)

        assert result["success"] is True
        assert "修改成功" in result["stdout"]

        # 验证文件内容已更新
        with open(temp_file, "r", encoding="utf-8") as f:
            content = f.read()
            assert 'print("Hello, Jarvis!")' in content
            assert "return a + b + 1" in content

    def test_single_edit_failure_with_error_message(self, tool, temp_file):
        """测试单处编辑失败时，错误信息正确传递到 stderr"""
        args = {
            "files": [
                {
                    "file_path": temp_file,
                    "diffs": [
                        {
                            "search": "不存在的文本",
                            "replace": "新文本",
                        }
                    ],
                }
            ]
        }

        result = tool.execute(args)

        assert result["success"] is False
        # 验证 stderr 包含详细的错误信息
        assert "stderr" in result
        assert result["stderr"] != ""
        assert (
            "未找到精确匹配的文本" in result["stderr"]
            or "未找到可匹配的文本" in result["stderr"]
        )
        assert (
            temp_file in result["stderr"]
            or os.path.basename(temp_file) in result["stderr"]
        )

    def test_multiple_edits_failure_with_error_message(self, tool, temp_file):
        """测试多处编辑失败时，错误信息正确传递到 stderr（关键测试）"""
        args = {
            "files": [
                {
                    "file_path": temp_file,
                    "diffs": [
                        {
                            "search": 'def hello():\n    print("Hello, World!")',
                            "replace": 'def hello():\n    print("Hello, Jarvis!")',
                        },
                        {
                            "search": "不存在的第二个文本",
                            "replace": "新文本",
                        },
                    ],
                }
            ]
        }

        result = tool.execute(args)

        assert result["success"] is False
        # 关键验证：stderr 应该包含详细的错误信息，而不仅仅是文件列表
        assert "stderr" in result
        assert result["stderr"] != ""
        # 验证包含详细的错误信息
        assert (
            "第 2 个diff失败" in result["stderr"]
            or "未找到精确匹配" in result["stderr"]
            or "未找到可匹配的文本" in result["stderr"]
        )
        # 验证不是只有文件列表
        assert (
            "失败 1 个文件" not in result["stderr"]
            or "未找到精确匹配" in result["stderr"]
        )
        # 验证包含文件路径或文件名
        assert (
            temp_file in result["stderr"]
            or os.path.basename(temp_file) in result["stderr"]
        )

    def test_multiple_files_partial_failure(self, tool, temp_file, temp_file2):
        """测试多个文件编辑，部分成功部分失败"""
        args = {
            "files": [
                {
                    "file_path": temp_file,
                    "diffs": [
                        {
                            "search": 'def hello():\n    print("Hello, World!")',
                            "replace": 'def hello():\n    print("Hello, Jarvis!")',
                        }
                    ],
                },
                {
                    "file_path": temp_file2,
                    "diffs": [
                        {
                            "search": "不存在的文本",
                            "replace": "新文本",
                        }
                    ],
                },
            ]
        }

        result = tool.execute(args)

        assert result["success"] is False
        # 验证 stderr 包含失败文件的详细错误信息
        assert "stderr" in result
        assert result["stderr"] != ""
        # 应该包含失败文件的错误信息
        assert (
            "未找到精确匹配" in result["stderr"]
            or "未找到可匹配的文本" in result["stderr"]
            or "失败" in result["stderr"]
        )
        # 验证成功文件的信息在 stdout 中
        assert "成功" in result["stdout"] or "修改成功" in result["stdout"]

    def test_multiple_matches_fail_without_replace_all(self, tool):
        """测试多匹配时默认失败，要求显式 replace_all。"""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write('print("hello")\nprint("hello")\n')
            temp_path = f.name

        try:
            result = tool.execute(
                {
                    "files": [
                        {
                            "file_path": temp_path,
                            "diffs": [
                                {
                                    "search": 'print("hello")',
                                    "replace": 'print("world")',
                                }
                            ],
                        }
                    ]
                }
            )

            assert result["success"] is False
            assert "replace_all=false" in result["stderr"]
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            if os.path.exists(temp_path + ".bak"):
                os.remove(temp_path + ".bak")

    def test_multiple_matches_success_with_replace_all(self, tool):
        """测试多匹配时 replace_all=true 可全部替换。"""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write('print("hello")\nprint("hello")\n')
            temp_path = f.name

        try:
            result = tool.execute(
                {
                    "files": [
                        {
                            "file_path": temp_path,
                            "diffs": [
                                {
                                    "search": 'print("hello")',
                                    "replace": 'print("world")',
                                    "replace_all": True,
                                }
                            ],
                        }
                    ]
                }
            )

            assert result["success"] is True
            with open(temp_path, "r", encoding="utf-8") as f:
                content = f.read()
            assert content.count('print("world")') == 2
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            if os.path.exists(temp_path + ".bak"):
                os.remove(temp_path + ".bak")

    def test_quote_normalization_finds_actual_search_text(self, tool):
        """测试直引号 search 可匹配文件中的弯引号实际文本。"""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("message = “Hello”\n")
            temp_path = f.name

        try:
            result = tool.execute(
                {
                    "files": [
                        {
                            "file_path": temp_path,
                            "diffs": [
                                {
                                    "search": 'message = "Hello"',
                                    "replace": 'message = "World"',
                                }
                            ],
                        }
                    ]
                }
            )

            assert result["success"] is True
            with open(temp_path, "r", encoding="utf-8") as f:
                content = f.read()
            assert "message = “World”" in content
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            if os.path.exists(temp_path + ".bak"):
                os.remove(temp_path + ".bak")

    def test_preserve_curly_single_quote_style(self, tool):
        """测试匹配到弯单引号时，replace 结果保持弯单引号风格。"""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("status = ‘done’\n")
            temp_path = f.name

        try:
            result = tool.execute(
                {
                    "files": [
                        {
                            "file_path": temp_path,
                            "diffs": [
                                {
                                    "search": "status = 'done'",
                                    "replace": "status = 'ready'",
                                }
                            ],
                        }
                    ]
                }
            )

            assert result["success"] is True
            with open(temp_path, "r", encoding="utf-8") as f:
                content = f.read()
            assert "status = ‘ready’" in content
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            if os.path.exists(temp_path + ".bak"):
                os.remove(temp_path + ".bak")

    def test_multiple_edits_first_success_second_failure(self, tool, temp_file):
        """测试多处编辑，第一个成功，第二个失败"""
        args = {
            "files": [
                {
                    "file_path": temp_file,
                    "diffs": [
                        {
                            "search": "def add(a, b):",
                            "replace": "def add(a, b, c=0):",
                        },
                        {
                            "search": "完全不存在的文本12345",
                            "replace": "新文本",
                        },
                    ],
                }
            ]
        }

        result = tool.execute(args)

        assert result["success"] is False
        # 验证 stderr 包含第二个 diff 的详细错误信息
        assert "stderr" in result
        assert result["stderr"] != ""
        assert (
            "第 2 个diff失败" in result["stderr"]
            or "未找到精确匹配" in result["stderr"]
            or "未找到可匹配的文本" in result["stderr"]
        )
        # 当前实现下，当同一文件的后续 diff 失败时，不会写入前面成功的内存修改
        with open(temp_file, "r", encoding="utf-8") as f:
            content = f.read()
            assert "def add(a, b, c=0):" not in content
            assert "def add(a, b):" in content

    def test_invalid_args_missing_files(self, tool):
        """测试缺少 files 参数"""
        args = {}

        result = tool.execute(args)

        assert result["success"] is False
        assert "缺少必需参数" in result["stderr"] or "files" in result["stderr"]

    def test_invalid_args_empty_files(self, tool):
        """测试空的 files 数组"""
        args = {"files": []}

        result = tool.execute(args)

        assert result["success"] is False
        # 空列表会被 if not files 捕获，返回"缺少必需参数：files"
        assert "files" in result["stderr"]

    def test_invalid_args_missing_file_path(self, tool):
        """测试缺少 file_path"""
        args = {
            "files": [
                {
                    "diffs": [{"search": "test", "replace": "new"}],
                }
            ]
        }

        result = tool.execute(args)

        assert result["success"] is False
        assert "file_path" in result["stderr"] or "缺少必需参数" in result["stderr"]

    def test_invalid_args_missing_diffs(self, tool, temp_file):
        """测试缺少 diffs"""
        args = {
            "files": [
                {
                    "file_path": temp_file,
                }
            ]
        }

        result = tool.execute(args)

        assert result["success"] is False
        assert "diffs" in result["stderr"] or "缺少必需参数" in result["stderr"]

    def test_error_message_contains_search_text_preview(self, tool, temp_file):
        """测试错误信息包含搜索文本预览"""
        search_text = "这是一个很长的搜索文本" * 10
        args = {
            "files": [
                {
                    "file_path": temp_file,
                    "diffs": [
                        {
                            "search": search_text,
                            "replace": "新文本",
                        }
                    ],
                }
            ]
        }

        result = tool.execute(args)

        assert result["success"] is False
        # 验证错误信息包含搜索文本的前200个字符
        assert "stderr" in result
        assert result["stderr"] != ""
        # 应该包含搜索文本的预览
        assert "搜索文本" in result["stderr"] or "未找到精确匹配" in result["stderr"]

    def test_stderr_contains_detailed_error_not_just_file_list(self, tool, temp_file):
        """测试 stderr 包含详细错误信息，而不仅仅是文件列表（验证修复）"""
        args = {
            "files": [
                {
                    "file_path": temp_file,
                    "diffs": [
                        {
                            "search": "完全不存在的文本用于测试",
                            "replace": "新文本",
                        }
                    ],
                }
            ]
        }

        result = tool.execute(args)

        assert result["success"] is False
        stderr = result["stderr"]

        # 验证 stderr 不为空
        assert stderr != ""

        # 关键验证：stderr 应该包含详细的错误信息，而不仅仅是 "失败 X 个文件: - file"
        # 应该包含具体的错误描述
        has_detailed_error = (
            "未找到精确匹配" in stderr
            or "第" in stderr
            and "个diff失败" in stderr
            or "搜索文本" in stderr
        )
        assert has_detailed_error, (
            f"stderr 应该包含详细错误信息，但实际内容为: {stderr[:200]}"
        )

        # 验证包含文件路径或文件名
        assert temp_file in stderr or os.path.basename(temp_file) in stderr

    def test_multiple_edits_with_deletion_causing_line_changes(self, tool):
        """测试多处修改，其中包含删除操作导致行号变化"""
        # 创建初始文件
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("""import os
import sys

def helper1():
    pass

def helper2():
    pass

def main():
    print("main function")

def helper3():
    pass
""")
            temp_path = f.name

        try:
            # 执行多处修改
            args = {
                "files": [
                    {
                        "file_path": temp_path,
                        "diffs": [
                            # 第一个修改：删除 import 语句（减少行数）
                            {
                                "search": "import os\nimport sys\n\n",
                                "replace": "",
                            },
                            # 第二个修改：删除 helper1（减少行数）
                            {
                                "search": "def helper1():\n    pass\n\n",
                                "replace": "",
                            },
                            # 第三个修改：修改 main 函数（行号已经变化）
                            {
                                "search": 'def main():\n    print("main function")',
                                "replace": 'def main():\n    print("main function modified")',
                            },
                            # 第四个修改：删除 helper2（减少行数）
                            {
                                "search": "def helper2():\n    pass\n\n",
                                "replace": "",
                            },
                            # 第五个修改：修改 helper3（行号已经变化）
                            {
                                "search": "def helper3():\n    pass",
                                "replace": "def helper3():\n    return True",
                            },
                        ],
                    }
                ]
            }

            result = tool.execute(args)

            # 验证所有修改都成功
            assert result["success"] is True, f"编辑失败: {result.get('stderr', '')}"
            assert "修改成功" in result["stdout"]

            # 验证文件内容
            with open(temp_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 验证删除操作
            assert "import os" not in content
            assert "import sys" not in content
            assert "def helper1():" not in content
            assert "def helper2():" not in content

            # 验证修改操作
            assert 'print("main function modified")' in content
            assert 'print("main function")' not in content
            assert "return True" in content
            assert "def helper3():" in content

            # 验证文件行数确实减少了
            lines = content.splitlines()
            assert len(lines) < 15, f"文件应该少于15行，实际有{len(lines)}行"

        finally:
            # 清理
            if os.path.exists(temp_path):
                os.remove(temp_path)
            if os.path.exists(temp_path + ".bak"):
                os.remove(temp_path + ".bak")

    def test_multiple_edits_with_long_to_short_replacement(self, tool):
        """测试多处修改，其中包含将长内容替换为短内容导致行号减少"""
        # 创建初始文件，包含大量内容
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("""def process_data():
    # 这是一个很长的函数，包含大量注释和代码
    # 第1行注释：用于说明函数的功能
    # 第2行注释：用于说明参数的含义
    # 第3行注释：用于说明返回值的类型
    # 第4行注释：用于说明异常处理
    # 第5行注释：用于说明使用示例
    # 第6行注释：用于说明注意事项
    # 第7行注释：用于说明性能考虑
    # 第8行注释：用于说明兼容性
    # 第9行注释：用于说明版本历史
    # 第10行注释：用于说明相关函数
    # 第11行注释：用于说明实现细节
    # 第12行注释：用于说明测试用例
    # 第13行注释：用于说明已知问题
    # 第14行注释：用于说明未来计划
    # 第15行注释：用于说明参考资料
    # 第16行注释：用于说明代码风格
    # 第17行注释：用于说明错误处理
    # 第18行注释：用于说明日志记录
    # 第19行注释：用于说明配置选项
    # 第20行注释：用于说明依赖关系
    data = []
    for i in range(100):
        data.append(i * 2)
    return data

def calculate_sum(a, b):
    return a + b

def format_output(text):
    return text.upper()
""")
            temp_path = f.name

        try:
            # 记录初始文件行数
            with open(temp_path, "r", encoding="utf-8") as f:
                initial_lines = len(f.read().splitlines())

            # 执行多处修改
            args = {
                "files": [
                    {
                        "file_path": temp_path,
                        "diffs": [
                            # 第一个修改：将长函数替换为短函数（大幅减少行数）
                            {
                                "search": """def process_data():
    # 这是一个很长的函数，包含大量注释和代码
    # 第1行注释：用于说明函数的功能
    # 第2行注释：用于说明参数的含义
    # 第3行注释：用于说明返回值的类型
    # 第4行注释：用于说明异常处理
    # 第5行注释：用于说明使用示例
    # 第6行注释：用于说明注意事项
    # 第7行注释：用于说明性能考虑
    # 第8行注释：用于说明兼容性
    # 第9行注释：用于说明版本历史
    # 第10行注释：用于说明相关函数
    # 第11行注释：用于说明实现细节
    # 第12行注释：用于说明测试用例
    # 第13行注释：用于说明已知问题
    # 第14行注释：用于说明未来计划
    # 第15行注释：用于说明参考资料
    # 第16行注释：用于说明代码风格
    # 第17行注释：用于说明错误处理
    # 第18行注释：用于说明日志记录
    # 第19行注释：用于说明配置选项
    # 第20行注释：用于说明依赖关系
    data = []
    for i in range(100):
        data.append(i * 2)
    return data""",
                                "replace": "def process_data():\n    return [i * 2 for i in range(100)]",
                            },
                            # 第二个修改：修改 calculate_sum 函数（行号已经大幅减少）
                            {
                                "search": "def calculate_sum(a, b):\n    return a + b",
                                "replace": "def calculate_sum(a, b):\n    return a + b + 1",
                            },
                            # 第三个修改：修改 format_output 函数（行号已经大幅减少）
                            {
                                "search": "def format_output(text):\n    return text.upper()",
                                "replace": "def format_output(text):\n    return text.upper() + '!'",
                            },
                        ],
                    }
                ]
            }

            result = tool.execute(args)

            # 验证所有修改都成功
            assert result["success"] is True, f"编辑失败: {result.get('stderr', '')}"
            assert "修改成功" in result["stdout"]

            # 验证文件内容
            with open(temp_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 验证第一个修改：长函数被替换为短函数
            assert "def process_data():" in content
            assert "return [i * 2 for i in range(100)]" in content
            # 验证长注释都被删除
            assert "第1行注释" not in content
            assert "第20行注释" not in content
            assert "data = []" not in content
            assert "for i in range(100):" not in content

            # 验证第二个修改：calculate_sum 被修改
            # 检查函数定义中包含新的返回值
            import re

            calculate_sum_match = re.search(
                r"def calculate_sum\([^)]+\):.*?return\s+(.+?)(?=\n\ndef|\Z)",
                content,
                re.DOTALL,
            )
            assert calculate_sum_match, "找不到 calculate_sum 函数"
            assert "a + b + 1" in calculate_sum_match.group(1), (
                f"calculate_sum 应该返回 a + b + 1，实际: {calculate_sum_match.group(1)}"
            )

            # 验证第三个修改：format_output 被修改
            format_output_match = re.search(
                r"def format_output\([^)]+\):.*?return\s+(.+?)(?=\n\ndef|\Z)",
                content,
                re.DOTALL,
            )
            assert format_output_match, "找不到 format_output 函数"
            assert "text.upper() + '!'" in format_output_match.group(1), (
                f"format_output 应该返回 text.upper() + '!'，实际: {format_output_match.group(1)}"
            )

            # 验证文件行数确实大幅减少了
            final_lines = len(content.splitlines())
            assert final_lines < initial_lines - 15, (
                f"文件应该减少至少15行，初始{initial_lines}行，最终{final_lines}行"
            )
            assert final_lines < 10, f"文件应该少于10行，实际有{final_lines}行"

        finally:
            # 清理
            if os.path.exists(temp_path):
                os.remove(temp_path)
            if os.path.exists(temp_path + ".bak"):
                os.remove(temp_path + ".bak")

    def test_multiple_edits_with_mixed_long_short_changes(self, tool):
        """测试多处修改，包含从短变长和从长变短的混合场景"""
        # 创建初始文件
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("""def func1():
    pass

def func2():
    # 这是一个很长的注释块
    # 包含很多行注释
    # 用于测试从长变短的场景
    # 第4行注释
    # 第5行注释
    # 第6行注释
    # 第7行注释
    # 第8行注释
    # 第9行注释
    # 第10行注释
    return "result"

def func3():
    pass
""")
            temp_path = f.name

        try:
            # 执行多处修改
            args = {
                "files": [
                    {
                        "file_path": temp_path,
                        "diffs": [
                            # 第一个修改：将短函数变长（插入大量内容）
                            {
                                "search": "def func1():\n    pass",
                                "replace": """def func1():
    # 添加大量注释
    # 注释行1
    # 注释行2
    # 注释行3
    # 注释行4
    # 注释行5
    # 注释行6
    # 注释行7
    # 注释行8
    # 注释行9
    # 注释行10
    return "func1_result"
""",
                            },
                            # 第二个修改：将长函数变短（删除大量内容）
                            {
                                "search": """def func2():
    # 这是一个很长的注释块
    # 包含很多行注释
    # 用于测试从长变短的场景
    # 第4行注释
    # 第5行注释
    # 第6行注释
    # 第7行注释
    # 第8行注释
    # 第9行注释
    # 第10行注释
    return "result"
""",
                                "replace": 'def func2():\n    return "result"',
                            },
                            # 第三个修改：修改 func3（行号已经变化）
                            {
                                "search": "def func3():\n    pass",
                                "replace": "def func3():\n    return True",
                            },
                        ],
                    }
                ]
            }

            result = tool.execute(args)

            # 验证所有修改都成功
            assert result["success"] is True, f"编辑失败: {result.get('stderr', '')}"
            assert "修改成功" in result["stdout"]

            # 验证文件内容
            with open(temp_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 验证第一个修改：func1 变长了
            assert "def func1():" in content
            assert "注释行1" in content
            assert "注释行10" in content
            assert 'return "func1_result"' in content
            assert "pass" not in content or content.count("pass") == 0

            # 验证第二个修改：func2 变短了
            assert "def func2():" in content
            assert 'return "result"' in content
            # 验证长注释都被删除
            assert "这是一个很长的注释块" not in content
            assert "第10行注释" not in content

            # 验证第三个修改：func3 被修改
            assert "def func3():" in content
            assert "return True" in content

        finally:
            # 清理
            if os.path.exists(temp_path):
                os.remove(temp_path)
            if os.path.exists(temp_path + ".bak"):
                os.remove(temp_path + ".bak")


class TestEditFileEncoding:
    """测试文件编码检测和一致性"""

    @pytest.fixture
    def tool(self):
        """创建测试用的 EditFileNormalTool 实例"""
        return EditFileNormalTool()

    def test_utf8_encoding_preserved(self, tool):
        """测试 UTF-8 编码文件编辑后编码保持一致"""
        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".txt") as f:
            content = "你好世界\nHello World\n"
            f.write(content.encode("utf-8"))
            temp_path = f.name

        try:
            args = {
                "files": [
                    {
                        "file_path": temp_path,
                        "diffs": [
                            {
                                "search": "你好世界",
                                "replace": "你好 Jarvis",
                            }
                        ],
                    }
                ]
            }

            result = tool.execute(args)
            assert result["success"] is True

            with open(temp_path, "rb") as f:
                raw_content = f.read()
            decoded = raw_content.decode("utf-8")
            assert "你好 Jarvis" in decoded
            assert "你好世界" not in decoded

        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            if os.path.exists(temp_path + ".bak"):
                os.remove(temp_path + ".bak")



    def test_encoding_detection_with_bom(self, tool):
        """测试带 BOM 的 UTF-8 文件处理"""
        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".txt") as f:
            content = "BOM测试\nTest with BOM\n"
            f.write(b"\xef\xbb\xbf")
            f.write(content.encode("utf-8"))
            temp_path = f.name

        try:
            args = {
                "files": [
                    {
                        "file_path": temp_path,
                        "diffs": [
                            {
                                "search": "BOM测试",
                                "replace": "BOM修改",
                            }
                        ],
                    }
                ]
            }

            result = tool.execute(args)
            assert result["success"] is True

            with open(temp_path, "rb") as f:
                raw_content = f.read()
            decoded = raw_content.decode("utf-8-sig")
            assert "BOM修改" in decoded

        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            if os.path.exists(temp_path + ".bak"):
                os.remove(temp_path + ".bak")

    def test_empty_file_encoding(self, tool):
        """测试空文件的编码处理"""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            temp_path = f.name

        try:
            args = {
                "files": [
                    {
                        "file_path": temp_path,
                        "diffs": [
                            {
                                "search": "",
                                "replace": "新内容\n",
                            }
                        ],
                    }
                ]
            }

            result = tool.execute(args)
            assert result["success"] is True

            with open(temp_path, "r", encoding="utf-8") as f:
                content = f.read()
            assert "新内容" in content

        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            if os.path.exists(temp_path + ".bak"):
                os.remove(temp_path + ".bak")
