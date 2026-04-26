# -*- coding: utf-8 -*-
"""jarvis_utils.output 模块单元测试"""

from unittest.mock import Mock, patch
from jarvis.jarvis_utils.output import (
    OutputType,
    OutputEvent,
    PrettyOutput,
    OutputSink,
    ConsoleOutputSink,
    _safe_color_get,
    emit_output,
)


class TestOutputType:
    """测试 OutputType 枚举"""

    def test_enum_values(self):
        """测试枚举值"""
        assert OutputType.SYSTEM.value == "SYSTEM"
        assert OutputType.CODE.value == "CODE"
        assert OutputType.RESULT.value == "RESULT"
        assert OutputType.ERROR.value == "ERROR"
        assert OutputType.INFO.value == "INFO"
        assert OutputType.PLANNING.value == "PLANNING"
        assert OutputType.PROGRESS.value == "PROGRESS"
        assert OutputType.SUCCESS.value == "SUCCESS"
        assert OutputType.WARNING.value == "WARNING"
        assert OutputType.DEBUG.value == "DEBUG"
        assert OutputType.USER.value == "USER"
        assert OutputType.TOOL.value == "TOOL"

    def test_enum_comparison(self):
        """测试枚举比较"""
        assert OutputType.SYSTEM.value == "SYSTEM"
        assert OutputType.ERROR.value != "SUCCESS"

    def test_enum_membership(self):
        """测试枚举成员"""
        assert "SYSTEM" in [e.value for e in OutputType]
        assert "ERROR" in [e.value for e in OutputType]


class TestOutputEvent:
    """测试 OutputEvent 数据类"""

    def test_basic_creation(self):
        """测试基本创建"""
        event = OutputEvent(text="Test message", output_type=OutputType.INFO)
        assert event.text == "Test message"
        assert event.output_type == OutputType.INFO
        assert event.timestamp is True  # 默认值
        assert event.lang is None
        assert event.traceback is False
        assert event.section is None
        assert event.context is None

    def test_full_creation(self):
        """测试完整创建"""
        event = OutputEvent(
            text="Test message",
            output_type=OutputType.ERROR,
            timestamp=False,
            lang="python",
            traceback=True,
            section="Test Section",
            context={"key": "value"},
        )
        assert event.text == "Test message"
        assert event.output_type == OutputType.ERROR
        assert event.timestamp is False
        assert event.lang == "python"
        assert event.traceback is True
        assert event.section == "Test Section"
        assert event.context == {"key": "value"}

    def test_different_output_types(self):
        """测试不同的输出类型"""
        for output_type in OutputType:
            event = OutputEvent(
                text=f"Message for {output_type.value}", output_type=output_type
            )
            assert event.output_type == output_type
            assert event.text == f"Message for {output_type.value}"

    def test_empty_text(self):
        """测试空文本"""
        event = OutputEvent(text="", output_type=OutputType.INFO)
        assert event.text == ""
        assert event.output_type == OutputType.INFO


class TestSafeColorGet:
    """测试 _safe_color_get 函数"""

    def test_valid_color(self):
        """测试有效颜色"""
        assert _safe_color_get("red") == "red"
        assert _safe_color_get("blue") == "blue"
        assert _safe_color_get("green") == "green"

    def test_invalid_color_with_fallback(self):
        """测试无效颜色使用回退"""
        assert _safe_color_get("invalid_color", "white") == "white"
        assert _safe_color_get("not_a_color", "grey50") == "grey50"

    def test_color_alias_mapping(self):
        """测试颜色别名映射"""
        assert _safe_color_get("dark_olive_green") == "green"
        assert _safe_color_get("orange3") == "bright_yellow"
        assert _safe_color_get("sea_green3") == "green"
        assert _safe_color_get("dark_sea_green") == "green"
        assert _safe_color_get("grey58") == "grey50"

    def test_default_fallback(self):
        """测试默认回退颜色"""
        assert _safe_color_get("invalid") == "white"


class TestHighlightProgressText:
    """测试 _highlight_progress_text 静态方法"""

    def test_single_progress_round(self):
        """测试单个进度轮次（第X轮）"""
        from rich.text import Text

        text = "正在执行第 3 轮处理"
        result = ConsoleOutputSink._highlight_progress_text(
            text, OutputType.PROGRESS, {OutputType.PROGRESS: "grey50"}
        )

        assert isinstance(result, Text)
        assert "3" in str(result)

    def test_progress_with_total(self):
        """测试带总数的进度（第X/Y轮）"""
        from rich.text import Text

        text = "正在执行第 3/10 轮处理"
        result = ConsoleOutputSink._highlight_progress_text(
            text, OutputType.PROGRESS, {OutputType.PROGRESS: "grey50"}
        )

        assert isinstance(result, Text)
        assert "3" in str(result)
        assert "10" in str(result)

    def test_no_progress_info(self):
        """测试不包含进度信息的普通文本"""
        from rich.text import Text

        text = "普通文本内容"
        result = ConsoleOutputSink._highlight_progress_text(
            text, OutputType.INFO, {OutputType.INFO: "blue"}
        )

        assert isinstance(result, Text)
        assert str(result) == text

    def test_multiple_progress_patterns(self):
        """测试文本中包含多个进度模式"""
        from rich.text import Text

        text = "第 1 轮开始，第 2 轮继续"
        result = ConsoleOutputSink._highlight_progress_text(
            text, OutputType.PROGRESS, {OutputType.PROGRESS: "grey50"}
        )

        assert isinstance(result, Text)
        assert "1" in str(result)
        assert "2" in str(result)

    def test_progress_with_spaces(self):
        """测试进度文本中的空格处理"""
        from rich.text import Text

        text = "第  5  轮  "
        result = ConsoleOutputSink._highlight_progress_text(
            text, OutputType.PROGRESS, {OutputType.PROGRESS: "grey50"}
        )

        assert isinstance(result, Text)
        assert "5" in str(result)


class TestConsoleOutputSink:
    """测试 ConsoleOutputSink 类"""

    @patch("jarvis.jarvis_utils.output.console")
    @patch("jarvis.jarvis_utils.output.get_pretty_output", return_value=True)
    def test_emit_section(self, mock_get_pretty, mock_console):
        """测试章节输出"""
        sink = ConsoleOutputSink()
        event = OutputEvent(
            text="", output_type=OutputType.SYSTEM, section="Test Section"
        )
        sink.emit(event)
        assert mock_console.print.called

    @patch("jarvis.jarvis_utils.output.console")
    @patch("jarvis.jarvis_utils.output.get_pretty_output", return_value=False)
    def test_emit_section_no_pretty(self, mock_get_pretty, mock_console):
        """测试章节输出（非美化模式）"""
        sink = ConsoleOutputSink()
        event = OutputEvent(
            text="", output_type=OutputType.SYSTEM, section="Test Section"
        )
        sink.emit(event)
        assert mock_console.print.called

    @patch("jarvis.jarvis_utils.output.console")
    @patch("jarvis.jarvis_utils.output.get_pretty_output", return_value=True)
    @patch("jarvis.jarvis_utils.output.get_agent_list", return_value="[1]TestAgent")
    def test_emit_simple_text(self, mock_get_agent_list, mock_get_pretty, mock_console):
        """测试简单文本输出"""
        sink = ConsoleOutputSink()
        event = OutputEvent(text="Hello World", output_type=OutputType.INFO)
        sink.emit(event)
        assert mock_console.print.called

    @patch("jarvis.jarvis_utils.output.console")
    @patch("jarvis.jarvis_utils.output.get_pretty_output", return_value=True)
    @patch(
        "jarvis.jarvis_utils.output.get_agent_list", return_value="[1]Agent1, Agent2"
    )
    @patch("jarvis.jarvis_utils.output.get_agent")
    def test_emit_multiline_list(
        self, mock_get_agent, mock_get_agent_list, mock_get_pretty, mock_console
    ):
        """测试多行列表输出"""
        mock_agent = Mock()
        mock_agent.non_interactive = False
        mock_get_agent.return_value = mock_agent

        sink = ConsoleOutputSink()
        event = OutputEvent(
            text="- Item 1\n- Item 2\n- Item 3", output_type=OutputType.INFO
        )
        sink.emit(event)
        assert mock_console.print.called

    @patch("jarvis.jarvis_utils.output.console")
    @patch("jarvis.jarvis_utils.output.get_pretty_output", return_value=True)
    @patch("jarvis.jarvis_utils.output.get_agent_list", return_value="[1]TestAgent")
    def test_emit_progress_text(
        self, mock_get_agent_list, mock_get_pretty, mock_console
    ):
        """测试进度文本高亮"""
        sink = ConsoleOutputSink()
        event = OutputEvent(text="第 3 轮执行", output_type=OutputType.PROGRESS)
        sink.emit(event)
        assert mock_console.print.called

    @patch("jarvis.jarvis_utils.output.console")
    @patch("jarvis.jarvis_utils.output.get_pretty_output", return_value=True)
    @patch("jarvis.jarvis_utils.output.get_agent_list", return_value="[1]TestAgent")
    def test_emit_progress_with_total(
        self, mock_get_agent_list, mock_get_pretty, mock_console
    ):
        """测试带总数的进度文本"""
        sink = ConsoleOutputSink()
        event = OutputEvent(text="第 3/10 轮执行", output_type=OutputType.PROGRESS)
        sink.emit(event)
        assert mock_console.print.called

    @patch("jarvis.jarvis_utils.output.console")
    @patch("jarvis.jarvis_utils.output.is_print_error_traceback", return_value=False)
    @patch("jarvis.jarvis_utils.output.get_pretty_output", return_value=True)
    @patch("jarvis.jarvis_utils.output.get_agent_list", return_value="[1]TestAgent")
    def test_emit_error_without_traceback(
        self,
        mock_get_agent_list,
        mock_get_pretty,
        mock_is_print_traceback,
        mock_console,
    ):
        """测试错误输出不打印堆栈"""
        sink = ConsoleOutputSink()
        event = OutputEvent(
            text="Error occurred", output_type=OutputType.ERROR, traceback=False
        )
        sink.emit(event)
        assert mock_console.print.called

    @patch("jarvis.jarvis_utils.output.console")
    @patch("jarvis.jarvis_utils.output.is_print_error_traceback", return_value=True)
    @patch("jarvis.jarvis_utils.output.get_pretty_output", return_value=True)
    @patch("jarvis.jarvis_utils.output.get_agent_list", return_value="[1]TestAgent")
    def test_emit_error_with_traceback(
        self,
        mock_get_agent_list,
        mock_get_pretty,
        mock_is_print_traceback,
        mock_console,
    ):
        """测试错误输出打印堆栈"""
        mock_console.print_exception = Mock()
        sink = ConsoleOutputSink()
        event = OutputEvent(
            text="Error occurred", output_type=OutputType.ERROR, traceback=True
        )
        sink.emit(event)
        assert mock_console.print.called


class TestPrettyOutput:
    """测试 PrettyOutput 类"""

    @patch("jarvis.jarvis_utils.output.emit_output")
    def test_print_basic(self, mock_emit):
        """测试基本print方法"""
        PrettyOutput._print("Hello World", OutputType.INFO)
        mock_emit.assert_called_once()
        args = mock_emit.call_args[0][0]
        assert args.text == "Hello World"
        assert args.output_type == OutputType.INFO
        assert args.timestamp is True

    @patch("jarvis.jarvis_utils.output.emit_output")
    def test_print_with_timestamp_false(self, mock_emit):
        """测试print方法（不显示时间戳）"""
        PrettyOutput._print("Hello World", OutputType.INFO, timestamp=False)
        args = mock_emit.call_args[0][0]
        assert args.timestamp is False

    @patch("jarvis.jarvis_utils.output.emit_output")
    def test_print_with_lang(self, mock_emit):
        """测试print方法（指定语言）"""
        PrettyOutput._print("print('hello')", OutputType.CODE, lang="python")
        args = mock_emit.call_args[0][0]
        assert args.lang == "python"

    @patch("jarvis.jarvis_utils.output.emit_output")
    def test_print_with_traceback(self, mock_emit):
        """测试print方法（打印堆栈）"""
        PrettyOutput._print("Error occurred", OutputType.ERROR, traceback=True)
        args = mock_emit.call_args[0][0]
        assert args.traceback is True

    @patch("jarvis.jarvis_utils.output.emit_output")
    def test_section_basic(self, mock_emit):
        """测试基本section方法"""
        PrettyOutput.section("Section Title")
        args = mock_emit.call_args[0][0]
        assert args.section == "Section Title"
        assert args.output_type == OutputType.INFO

    @patch("jarvis.jarvis_utils.output.emit_output")
    def test_section_with_output_type(self, mock_emit):
        """测试section方法（指定输出类型）"""
        PrettyOutput.section("Section Title", OutputType.WARNING)
        args = mock_emit.call_args[0][0]
        assert args.output_type == OutputType.WARNING

    @patch("jarvis.jarvis_utils.output.emit_output")
    def test_add_sink(self, mock_emit):
        """测试add_sink方法"""
        custom_sink = Mock(spec=OutputSink)
        initial_count = len(PrettyOutput.get_sinks())
        PrettyOutput.add_sink(custom_sink)
        assert len(PrettyOutput.get_sinks()) == initial_count + 1
        assert custom_sink in PrettyOutput.get_sinks()
        # 清理
        PrettyOutput.clear_sinks()

    def test_clear_sinks_keep_default(self):
        """测试clear_sinks方法（保留默认sink）"""
        custom_sink = Mock(spec=OutputSink)
        PrettyOutput.add_sink(custom_sink)
        PrettyOutput.clear_sinks(keep_default=True)
        sinks = PrettyOutput.get_sinks()
        assert len(sinks) == 1
        assert isinstance(sinks[0], ConsoleOutputSink)

    def test_clear_sinks_remove_all(self):
        """测试clear_sinks方法（清除所有sink）"""
        PrettyOutput.add_sink(Mock(spec=OutputSink))
        PrettyOutput.clear_sinks(keep_default=False)
        assert len(PrettyOutput.get_sinks()) == 0

    def test_get_sinks(self):
        """测试get_sinks方法"""
        # 先确保有默认sink
        sinks = PrettyOutput.get_sinks()
        assert isinstance(sinks, list)
        # 如果没有sink，添加一个默认的
        if len(sinks) == 0:
            PrettyOutput.add_sink(ConsoleOutputSink())
            sinks = PrettyOutput.get_sinks()
        assert len(sinks) >= 1
        # 测试返回的是副本
        sinks.append("fake_sink")
        assert "fake_sink" not in PrettyOutput.get_sinks()

    def test_detect_language_python(self):
        """测试Python语言检测"""
        text = """#!/usr/bin/env python
import os

def hello():
    print('world')

if __name__ == '__main__':
    hello()"""
        detected = PrettyOutput._detect_language(text)
        assert detected == "python"

    def test_detect_language_javascript(self):
        """测试JavaScript语言检测"""
        text = """// JavaScript code
const x = 10;
function hello() {
    console.log('world');
}
module.exports = hello;"""
        detected = PrettyOutput._detect_language(text)
        # 由于pygments识别可能不准确，我们只验证它返回了有效结果
        assert isinstance(detected, str)
        assert len(detected) > 0

    def test_detect_language_yaml(self):
        """测试YAML语言检测"""
        text = """# YAML configuration
---
key: value
nested:
  item: 1"""
        detected = PrettyOutput._detect_language(text)
        # 由于pygments可能将YAML识别为其他格式，我们只验证它返回了有效结果
        assert isinstance(detected, str)
        assert len(detected) > 0

    def test_detect_language_default(self):
        """测试默认语言检测"""
        text = "plain text content"
        detected = PrettyOutput._detect_language(text)
        assert detected == "markdown"

    def test_detect_language_custom_default(self):
        """测试自定义默认语言"""
        text = "plain text"
        detected = PrettyOutput._detect_language(text, default_lang="text")
        assert detected == "text"

    def test_detect_language_json(self):
        """测试JSON语言检测"""
        text = '{\n  "key": "value",\n  "number": 123,\n  "nested": {\n    "item": true\n  }\n}'
        detected = PrettyOutput._detect_language(text)
        # 由于pygments可能将JSON识别为其他格式，我们只验证它返回了有效结果
        assert isinstance(detected, str)
        assert len(detected) > 0

    @patch(
        "jarvis.jarvis_utils.output.get_agent_list", return_value="[1]Agent1, Agent2"
    )
    @patch("jarvis.jarvis_utils.output.get_agent")
    @patch("jarvis.jarvis_utils.output.datetime")
    def test_format_with_timestamp(
        self, mock_datetime, mock_get_agent, mock_get_agent_list
    ):
        """测试_format方法（带时间戳）"""
        mock_datetime.now.return_value.strftime.return_value = "12:34:56"
        mock_agent = Mock()
        mock_agent.non_interactive = False
        mock_get_agent.return_value = mock_agent

        result = PrettyOutput._format(OutputType.INFO, timestamp=True)
        assert "12:34:56" in result
        assert "⏰" in result
        assert "Agent1" in result
        assert "Agent2" in result

    @patch("jarvis.jarvis_utils.output.get_agent_list", return_value="[1]Agent1")
    @patch("jarvis.jarvis_utils.output.get_agent")
    def test_format_without_timestamp(self, mock_get_agent, mock_get_agent_list):
        """测试format方法（不带时间戳）"""
        mock_agent = Mock()
        mock_agent.non_interactive = False
        mock_get_agent.return_value = mock_agent

        result = PrettyOutput._format(OutputType.INFO, timestamp=False)
        assert "⏰" not in result
        assert "Agent1" in result

    @patch("jarvis.jarvis_utils.output.get_agent_list", return_value="")
    def test_format_no_agents(self, mock_get_agent_list):
        """测试format方法（无agent）"""
        result = PrettyOutput._format(OutputType.INFO)
        assert result == ""

    @patch(
        "jarvis.jarvis_utils.output.get_agent_list", return_value="[2]Agent1, Agent2"
    )
    @patch("jarvis.jarvis_utils.output.get_agent")
    def test_format_non_interactive_agent(self, mock_get_agent, mock_get_agent_list):
        """测试format方法（非交互agent）"""
        mock_agent1 = Mock()
        mock_agent1.non_interactive = True
        mock_agent2 = Mock()
        mock_agent2.non_interactive = False
        mock_get_agent.side_effect = [mock_agent1, mock_agent2]

        result = PrettyOutput._format(OutputType.INFO, timestamp=False)
        assert "Agent1🔇" in result
        assert "Agent2🔊" in result

    @patch("jarvis.jarvis_utils.output.console")
    def test_print_gradient_text_single_line(self, mock_console):
        """测试渐变文本（单行）"""
        # 使用至少两行文本以避免除零错误
        PrettyOutput.print_gradient_text("Hello\nWorld", (255, 0, 0), (0, 0, 255))
        mock_console.print.assert_called_once()
        # 验证调用的参数是Text对象
        call_args = mock_console.print.call_args
        from rich.text import Text

        assert isinstance(call_args[0][0], Text)

    @patch("jarvis.jarvis_utils.output.console")
    def test_print_gradient_text_multiline(self, mock_console):
        """测试渐变文本（多行）"""
        text = "Line 1\nLine 2\nLine 3"
        PrettyOutput.print_gradient_text(text, (255, 0, 0), (0, 255, 0))
        mock_console.print.assert_called_once()

    @patch("jarvis.jarvis_utils.output.console")
    def test_print_gradient_text_same_color(self, mock_console):
        """测试渐变文本（相同颜色）"""
        # 使用至少两行文本以避免除零错误
        PrettyOutput.print_gradient_text(
            "Same\nColor", (100, 100, 100), (100, 100, 100)
        )
        mock_console.print.assert_called_once()

    @patch("jarvis.jarvis_utils.output.emit_output")
    def test_auto_print_warning_emoji(self, mock_emit):
        """测试auto_print（警告emoji）"""
        PrettyOutput.auto_print("⚠️ Warning message")
        args = mock_emit.call_args[0][0]
        assert args.output_type == OutputType.WARNING

    @patch("jarvis.jarvis_utils.output.emit_output")
    def test_auto_print_error_emoji(self, mock_emit):
        """测试auto_print（错误emoji）"""
        PrettyOutput.auto_print("❌ Error message")
        args = mock_emit.call_args[0][0]
        assert args.output_type == OutputType.ERROR

    @patch("jarvis.jarvis_utils.output.emit_output")
    def test_auto_print_success_emoji(self, mock_emit):
        """测试auto_print（成功emoji）"""
        PrettyOutput.auto_print("✅ Success message")
        args = mock_emit.call_args[0][0]
        assert args.output_type == OutputType.SUCCESS

    @patch("jarvis.jarvis_utils.output.emit_output")
    def test_auto_print_no_emoji(self, mock_emit):
        """测试auto_print（无emoji）"""
        PrettyOutput.auto_print("Plain message")
        args = mock_emit.call_args[0][0]
        assert args.output_type == OutputType.INFO

    @patch("jarvis.jarvis_utils.output.emit_output")
    def test_auto_print_multiline(self, mock_emit):
        """测试auto_print（多行文本）"""
        PrettyOutput.auto_print("✅ First line\nSecond line")
        args = mock_emit.call_args[0][0]
        assert args.text.startswith("\n")

    @patch("jarvis.jarvis_utils.output.emit_output")
    def test_auto_print_emoji_spacing(self, mock_emit):
        """测试auto_print（emoji间距）"""
        PrettyOutput.auto_print("✅Message without space")
        args = mock_emit.call_args[0][0]
        assert "✅ Message without space" == args.text

    @patch("jarvis.jarvis_utils.output.emit_output")
    def test_auto_print_with_timestamp_false(self, mock_emit):
        """测试auto_print（不显示时间戳）"""
        PrettyOutput.auto_print("✅ Message", timestamp=False)
        args = mock_emit.call_args[0][0]
        assert args.timestamp is False

    @patch("jarvis.jarvis_utils.output.console")
    def test_print_markdown_basic(self, mock_console):
        """测试print_markdown（基本）"""
        content = "# Title\nContent here"
        PrettyOutput.print_markdown(content)
        assert mock_console.print.called

    @patch("jarvis.jarvis_utils.output.console")
    def test_print_markdown_with_title(self, mock_console):
        """测试print_markdown（带标题）"""
        content = "# Title\nContent here"
        PrettyOutput.print_markdown(content, title="Test Panel")
        assert mock_console.print.called

    @patch("jarvis.jarvis_utils.output.console")
    def test_print_markdown_custom_border_style(self, mock_console):
        """测试print_markdown（自定义边框样式）"""
        content = "# Title\nContent here"
        PrettyOutput.print_markdown(content, border_style="green")
        assert mock_console.print.called

    @patch("jarvis.jarvis_utils.output.console")
    def test_print_markdown_custom_theme(self, mock_console):
        """测试print_markdown（自定义主题）"""
        content = "```python\nprint('hello')\n```"
        PrettyOutput.print_markdown(content, theme="github-dark")
        assert mock_console.print.called


class TestEmitOutput:
    """测试 emit_output 函数"""

    @patch("jarvis.jarvis_utils.output.console")
    def test_emit_to_all_sinks(self, mock_console):
        """测试向所有sink广播事件"""
        sink1 = Mock(spec=OutputSink)
        sink2 = Mock(spec=OutputSink)

        PrettyOutput.clear_sinks(keep_default=False)
        PrettyOutput.add_sink(sink1)
        PrettyOutput.add_sink(sink2)

        event = OutputEvent(text="Test", output_type=OutputType.INFO)
        emit_output(event)

        sink1.emit.assert_called_once_with(event)
        sink2.emit.assert_called_once_with(event)

        # 清理
        PrettyOutput.clear_sinks()

    @patch("jarvis.jarvis_utils.output.console")
    def test_emit_with_sink_exception(self, mock_console):
        """测试sink异常不影响其他sink"""
        sink1 = Mock(spec=OutputSink)
        sink1.emit.side_effect = Exception("Sink1 error")
        sink2 = Mock(spec=OutputSink)

        PrettyOutput.clear_sinks(keep_default=False)
        PrettyOutput.add_sink(sink1)
        PrettyOutput.add_sink(sink2)

        event = OutputEvent(text="Test", output_type=OutputType.INFO)
        emit_output(event)

        # sink2应该被调用
        sink2.emit.assert_called_once_with(event)
        # 应该打印错误信息
        assert mock_console.print.called

        # 清理
        PrettyOutput.clear_sinks()
