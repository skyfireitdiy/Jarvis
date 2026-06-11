"""测试工具解析器对不同格式的识别能力"""

from jarvis.jarvis_tools.registry import ToolRegistry


class TestToolParsing:
    """测试工具调用解析的各种场景"""

    def test_parse_tool_with_name_prefix(self):
        """测试：工具名 + 代码块格式（应该被识别）"""
        content = """
        read_code
        ```json
        {
            "files": [{"path": "test.py"}]
        }
        ```
        """

        result, _, _ = ToolRegistry._extract_tool_calls(content)
        assert len(result) == 1
        assert result[0]["name"] == "read_code"
        assert result[0]["arguments"]["files"][0]["path"] == "test.py"

    def test_parse_bare_json_tool_call(self):
        """测试：裸露的 JSON 工具调用（应该被识别）"""
        content = """
        这是一些文本
        {"name": "read_code", "arguments": {"files": [{"path": "test.py"}]}}
        更多文本
        """

        result, _, _ = ToolRegistry._extract_tool_calls(content)
        assert len(result) == 1
        assert result[0]["name"] == "read_code"

    def test_ignore_json_code_block_without_tool_name(self):
        """测试：单独的 JSON 代码块（不应该被识别）"""
        content = """
        这是示例代码：
        ```json
        {
            "name": "some_tool",
            "arguments": {"key": "value"}
        }
        ```
        """

        result, _, _ = ToolRegistry._extract_tool_calls(content)
        # 不应该识别为工具调用
        assert len(result) == 0

    def test_ignore_example_in_documentation(self):
        """测试：文档中的示例（不应该被识别）"""
        content = """
        ## 工具使用示例
        
        ```json
        {
            "name": "edit_file",
            "arguments": {
                "files": [{"file_path": "example.py"}]
            }
        }
        ```
        
        以上是工具调用的示例格式。
        """

        result, _, _ = ToolRegistry._extract_tool_calls(content)
        assert len(result) == 0

    def test_parse_multiple_tools_mixed_format(self):
        """测试：混合格式的多个工具调用"""
        content = """
        首先读取文件：
        read_code
        ```json
        {"files": [{"path": "file1.py"}]}
        ```
        
        然后执行脚本：
        {"name": "execute_script", "arguments": {"script_content": "echo test"}}
        """

        result, _, _ = ToolRegistry._extract_tool_calls(content)
        assert len(result) == 2
        tool_names = [r["name"] for r in result]
        assert "read_code" in tool_names
        assert "execute_script" in tool_names

    def test_parse_nested_json_in_code_block(self):
        """测试：代码块中的嵌套 JSON（带工具名应被识别）"""
        content = """
        edit_file
        ```json
        {
            "files": [{
                "file_path": "test.py",
                "diffs": [{
                    "search": "old",
                    "replace": "new"
                }]
            }]
        }
        ```
        """

        result, _, _ = ToolRegistry._extract_tool_calls(content)
        assert len(result) == 1
        assert result[0]["name"] == "edit_file"
        assert result[0]["arguments"]["files"][0]["file_path"] == "test.py"

    def test_ignore_incomplete_json_in_code_block(self):
        """测试：代码块中不完整的 JSON（不应该被识别）"""
        content = """
        这是示例：
        ```json
        {
            "name": "xxx",
            ....
        }
        ```
        """

        result, _, _ = ToolRegistry._extract_tool_calls(content)
        assert len(result) == 0

    def test_parse_tool_with_language_hint(self):
        """测试：带语言提示的代码块 + 工具名"""
        content = """
        read_code
        ```python
        {"files": [{"path": "test.py"}]}
        ```
        """

        result, _, _ = ToolRegistry._extract_tool_calls(content)
        assert len(result) == 1
        assert result[0]["name"] == "read_code"

    def test_ignore_code_block_with_non_json_content(self):
        """测试：非 JSON 内容的代码块（不应该被识别）"""
        content = """
        代码示例：
        ```python
        def hello():
            print("hello")
        ```
        """

        result, _, _ = ToolRegistry._extract_tool_calls(content)
        assert len(result) == 0

    def test_real_world_scenario_with_explanation(self):
        """测试：真实场景 - 回复中包含说明和工具调用"""
        content = """
        好的，我来读取这个文件。
        
        read_code
        ```json
        {
            "files": [{
                "path": "src/main.py",
                "start_line": 1,
                "end_line": 50
            }]
        }
        ```
        
        这个工具会读取文件的前50行。
        """

        result, _, _ = ToolRegistry._extract_tool_calls(content)
        assert len(result) == 1
        assert result[0]["name"] == "read_code"
        assert result[0]["arguments"]["files"][0]["path"] == "src/main.py"
