# -*- coding: utf-8 -*-
"""jarvis_tools.registry 模块单元测试"""

import pytest
from unittest.mock import MagicMock

from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_tools.base import Tool


class TestToolRegistry:
    """测试 ToolRegistry 类"""

    @pytest.fixture
    def registry(self):
        """创建测试用的 ToolRegistry 实例"""
        reg = ToolRegistry()
        # 清空自动加载的工具，只测试我们注册的工具
        reg.tools.clear()
        return reg

    @pytest.fixture
    def sample_tool(self):
        """创建示例工具"""

        def tool_func(args):
            return {"success": True, "stdout": "test output", "stderr": ""}

        return Tool(
            name="test_tool",
            description="Test tool",
            parameters={"type": "object"},
            func=tool_func,
        )

    def test_init(self, registry):
        """测试初始化"""
        assert registry is not None
        assert hasattr(registry, "tools")
        assert isinstance(registry.tools, dict)

    def test_register_tool(self, registry, sample_tool):
        """测试注册工具"""
        registry.register_tool(
            sample_tool.name,
            sample_tool.description,
            sample_tool.parameters,
            sample_tool.func,
        )
        assert "test_tool" in registry.tools
        assert registry.tools["test_tool"].name == "test_tool"

    def test_get_tool_existing(self, registry, sample_tool):
        """测试获取已存在的工具"""
        registry.register_tool(
            sample_tool.name,
            sample_tool.description,
            sample_tool.parameters,
            sample_tool.func,
        )
        tool = registry.get_tool("test_tool")
        assert tool is not None
        assert tool.name == "test_tool"

    def test_get_tool_nonexistent(self, registry):
        """测试获取不存在的工具"""
        tool = registry.get_tool("nonexistent_tool")
        assert tool is None

    def test_get_all_tools(self, registry, sample_tool):
        """测试获取所有工具"""
        registry.register_tool(
            sample_tool.name,
            sample_tool.description,
            sample_tool.parameters,
            sample_tool.func,
        )
        tools = registry.get_all_tools()
        assert isinstance(tools, list)
        assert len(tools) > 0
        # 检查工具字典格式
        tool_dict = next((t for t in tools if t["name"] == "test_tool"), None)
        assert tool_dict is not None
        assert tool_dict["name"] == "test_tool"
        assert tool_dict["description"] == "Test tool"

    def test_execute_tool_success(self, registry, sample_tool):
        """测试成功执行工具"""
        registry.register_tool(
            sample_tool.name,
            sample_tool.description,
            sample_tool.parameters,
            sample_tool.func,
        )
        result = registry.execute_tool("test_tool", {"arg1": "value1"})
        assert result["success"] is True
        assert "stdout" in result

    def test_execute_tool_nonexistent(self, registry):
        """测试执行不存在的工具"""
        result = registry.execute_tool("nonexistent_tool", {})
        assert result["success"] is False
        assert "stderr" in result
        assert "不存在" in result["stderr"]

    def test_execute_tool_with_agent_v1(self, registry, sample_tool):
        """测试使用 v1.0 协议执行工具（带 agent）"""
        registry.register_tool(
            sample_tool.name,
            sample_tool.description,
            sample_tool.parameters,
            sample_tool.func,
        )
        mock_agent = MagicMock()
        result = registry.execute_tool(
            "test_tool", {"arg1": "value1"}, agent=mock_agent
        )
        assert result["success"] is True

    def test_execute_tool_with_agent_v2(self, registry):
        """测试使用 v2.0 协议执行工具"""

        def v2_tool_func(args, agent):
            return {"success": True, "stdout": "v2 output", "stderr": ""}

        registry.register_tool(
            "v2_tool",
            "V2 tool",
            {"type": "object"},
            v2_tool_func,
            protocol_version="2.0",
        )

        mock_agent = MagicMock()
        result = registry.execute_tool("v2_tool", {"arg1": "value1"}, agent=mock_agent)
        assert result["success"] is True
        assert result["stdout"] == "v2 output"

    def test_execute_tool_exception(self, registry):
        """测试工具执行异常"""

        def failing_tool(args):
            raise ValueError("Tool error")

        registry.register_tool(
            "failing_tool", "Failing tool", {"type": "object"}, failing_tool
        )

        result = registry.execute_tool("failing_tool", {})
        assert result["success"] is False
        assert "stderr" in result

    def test_parse_special_marker_format_with_end_marker(self):
        """测试解析特殊标记格式（带结束标记）"""
        content = """<|tool_calls_section_begin|>
<|tool_call_begin|>functions.read_code:0<|tool_call_argument_begin|>
{"files": [{"path": "test.py"}]}
<|tool_call_end|>
"""
        result = ToolRegistry._parse_special_marker_format(content)
        assert len(result) == 1
        assert result[0]["name"] == "read_code"
        assert result[0]["arguments"] == {"files": [{"path": "test.py"}]}

    def test_parse_special_marker_format_without_end_marker(self):
        """测试解析特殊标记格式（无结束标记）"""
        content = '<|tool_call_begin|>functions.execute_script:1<|tool_call_argument_begin|>{"script_content": "echo hello"}'
        result = ToolRegistry._parse_special_marker_format(content)
        assert len(result) == 1
        assert result[0]["name"] == "execute_script"
        assert result[0]["arguments"] == {"script_content": "echo hello"}

    def test_parse_special_marker_format_multiple_calls(self):
        """测试解析多个工具调用"""
        content = """<|tool_call_begin|>functions.read_code:0<|tool_call_argument_begin|>
{"files": [{"path": "a.py"}]}
<|tool_call_end|>
<|tool_call_begin|>functions.edit_file:1<|tool_call_argument_begin|>
{"files": [{"file_path": "b.py"}]}
<|tool_call_end|>
"""
        result = ToolRegistry._parse_special_marker_format(content)
        assert len(result) == 2
        assert result[0]["name"] == "read_code"
        assert result[1]["name"] == "edit_file"

    def test_parse_special_marker_format_invalid_json(self):
        """测试解析无效JSON的情况"""
        content = """<|tool_call_begin|>functions.test_tool:0<|tool_call_argument_begin|>
{invalid json}
<|tool_call_end|>
"""
        result = ToolRegistry._parse_special_marker_format(content)
        # 无效JSON应该被跳过，返回空列表
        assert len(result) == 0

    def test_extract_tool_calls_with_special_marker(self):
        """测试_extract_tool_calls能正确解析特殊标记格式"""
        content = '<|tool_call_begin|>functions.read_code:0<|tool_call_argument_begin|>{"files": [{"path": "test.py"}]}<|tool_call_end|>'
        result, error, auto_completed = ToolRegistry._extract_tool_calls(content)
        assert error == ""
        # _extract_tool_calls 始终返回列表
        assert len(result) == 1
        assert result[0]["name"] == "read_code"
        assert result[0]["arguments"] == {"files": [{"path": "test.py"}]}

    def test_parse_tool_name_json_format_basic(self):
        """测试解析工具名+JSON格式: 工具名\n{JSON参数}"""
        content = 'read_code\n{"files": [{"path": "test.py"}]}'
        result = ToolRegistry._parse_tool_name_json_format(content)
        assert len(result) == 1
        assert result[0]["name"] == "read_code"
        assert result[0]["arguments"] == {"files": [{"path": "test.py"}]}

    def test_parse_tool_name_json_format_with_nested_json(self):
        """测试解析工具名+嵌套JSON格式（两层嵌套）"""
        content = (
            'execute_script\n{"interpreter": "bash", "script_content": "echo hello"}'
        )
        result = ToolRegistry._parse_tool_name_json_format(content)
        assert len(result) == 1
        assert result[0]["name"] == "execute_script"
        assert result[0]["arguments"] == {
            "interpreter": "bash",
            "script_content": "echo hello",
        }

    def test_parse_xml_parameter_format_basic(self):
        """测试解析XML参数标签格式: <tool_name><parameter name="key">value</parameter></tool_name>"""
        content = '<read_code>\n<parameter name="files">[{"path": "test.py"}]</parameter>\n</read_code>'
        result = ToolRegistry._parse_xml_parameter_format(content, [])
        assert len(result) == 1
        assert result[0]["name"] == "read_code"
        assert result[0]["arguments"] == {"files": [{"path": "test.py"}]}

    def test_parse_xml_parameter_format_multiple_params(self):
        """测试解析XML参数标签格式: 多个parameter子标签"""
        content = '<execute_script>\n<parameter name="interpreter">bash</parameter>\n<parameter name="script_content">echo hello</parameter>\n</execute_script>'
        result = ToolRegistry._parse_xml_parameter_format(content, [])
        assert len(result) == 1
        assert result[0]["name"] == "execute_script"
        assert result[0]["arguments"]["interpreter"] == "bash"
        assert result[0]["arguments"]["script_content"] == "echo hello"

    def test_extract_tool_calls_with_tool_name_json_format(self):
        """测试_extract_tool_calls能正确解析工具名+JSON格式"""
        content = 'read_code\n{"files": [{"path": "test.py"}]}'
        result, error, _ = ToolRegistry._extract_tool_calls(content)
        assert error == ""
        assert len(result) == 1
        assert result[0]["name"] == "read_code"
        assert result[0]["arguments"] == {"files": [{"path": "test.py"}]}

    def test_extract_tool_calls_with_xml_parameter_format(self):
        """测试_extract_tool_calls能正确解析XML参数标签格式"""
        content = '<execute_script>\n<parameter name="interpreter">bash</parameter>\n<parameter name="script_content">grep -n pattern file</parameter>\n</execute_script>'
        result, error, _ = ToolRegistry._extract_tool_calls(content)
        assert error == ""
        assert len(result) == 1
        assert result[0]["name"] == "execute_script"
        assert result[0]["arguments"]["interpreter"] == "bash"
        assert result[0]["arguments"]["interpreter"] == "bash"
        assert result[0]["arguments"]["script_content"] == "grep -n pattern file"

    # ────────────── _compress_output 测试 ──────────────

    def test_compress_output_empty(self, registry):
        """测试空字符串和特殊标记直接返回"""
        assert registry._compress_output("") == ""
        assert registry._compress_output("<无输出和错误>") == "<无输出和错误>"

    def test_compress_output_blank_lines_collapse(self, registry):
        """第1层：连续空行>=3折叠为2个"""
        text = "line1\n\n\n\n\nline2"
        result = registry._compress_output(text)
        # 5个空行折叠为2个
        assert result == "line1\n\n\nline2"

    def test_compress_output_blank_lines_keep(self, registry):
        """第1层：连续空行<3保持不变"""
        text = "line1\n\n\nline2"
        result = registry._compress_output(text)
        # 2个空行不折叠
        assert result == "line1\n\n\nline2"

    def test_compress_output_json_compress(self, registry):
        """第2层：JSON压缩生效（压缩比<70%）"""
        text = '<stdout>\n{\n  "key": "value",\n  "nested": {\n    "a": 1\n  }\n}\n</stdout>'
        result = registry._compress_output(text)
        # 压缩后应变为一行JSON
        assert "<stdout>" in result
        assert "</stdout>" in result
        assert '{"key":"value","nested":{"a":1}}' in result
        assert '\n  "key"' not in result

    def test_compress_output_json_no_compress(self, registry):
        """第2层：已紧凑JSON/非JSON/无效JSON不压缩"""
        # 已紧凑的JSON（压缩比>=70%）
        compact_text = '<stdout>\n{"a":"b"}\n</stdout>'
        result = registry._compress_output(compact_text)
        assert result == compact_text  # 不变
        # 非JSON文本
        plain_text = "<stdout>\njust a normal text\n</stdout>"
        result = registry._compress_output(plain_text)
        assert result == plain_text  # 不变

    def test_compress_output_repeated_lines(self, registry):
        """第3层：连续重复行>=4合并"""
        text = "header\ndata_line\ndata_line\ndata_line\ndata_line\ndata_line\nfooter"
        result = registry._compress_output(text)
        lines = result.split("\n")
        assert lines[0] == "header"
        assert lines[1] == "data_line"
        assert "...（以上内容重复 4 次）" in lines[2]
        assert lines[3] == "footer"

    def test_compress_output_repeated_lines_few(self, registry):
        """第3层：连续重复行<4不压缩"""
        text = "a\nb\nb\nb\nc"
        result = registry._compress_output(text)
        assert result == text  # 3次重复不压缩

    def test_compress_output_safety_boundary(self, registry):
        """第4层：超过200行时保留首尾各100行"""
        lines = [f"line_{i}" for i in range(250)]
        text = "\n".join(lines)
        result = registry._compress_output(text)
        result_lines = result.split("\n")
        # 检查是否包含折叠标记
        assert "行已折叠" in result
        assert "总行数 250" in result
        # 检查首尾保留
        assert "line_0" in result_lines[0]
        assert "line_99" in result_lines[99]
        # 检查尾部保留
        assert "line_249" in result_lines[-1]
        assert "line_150" in result  # 尾部起始行出现在结果中
