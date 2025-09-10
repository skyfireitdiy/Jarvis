# -*- coding: utf-8 -*-
"""
输出格式化模块
该模块为Jarvis系统提供了丰富的文本格式化和显示工具。
包含：
- 用于分类不同输出类型的OutputType枚举
- 用于格式化和显示样式化输出的PrettyOutput类
- 多种编程语言的语法高亮支持
- 结构化输出的面板显示
"""
from datetime import datetime
from enum import Enum
from typing import Dict, Optional, Tuple, Any, List

from pygments.lexers import guess_lexer
from pygments.util import ClassNotFound
from rich.box import SIMPLE
from rich.panel import Panel
from rich.style import Style as RichStyle
from rich.syntax import Syntax
from rich.text import Text

from jarvis.jarvis_utils.config import get_pretty_output, is_print_error_traceback
from jarvis.jarvis_utils.globals import console, get_agent_list
from dataclasses import dataclass
from abc import ABC, abstractmethod


class OutputType(Enum):
    """
    输出类型枚举，用于分类和样式化不同类型的消息。

    属性：
        SYSTEM: AI助手消息
        CODE: 代码相关输出
        RESULT: 工具执行结果
        ERROR: 错误信息
        INFO: 系统提示
        PLANNING: 任务规划
        PROGRESS: 执行进度
        SUCCESS: 成功信息
        WARNING: 警告信息
        DEBUG: 调试信息
        USER: 用户输入
        TOOL: 工具调用
    """

    SYSTEM = "SYSTEM"
    CODE = "CODE"
    RESULT = "RESULT"
    ERROR = "ERROR"
    INFO = "INFO"
    PLANNING = "PLANNING"
    PROGRESS = "PROGRESS"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    DEBUG = "DEBUG"
    USER = "USER"
    TOOL = "TOOL"


@dataclass
class OutputEvent:
    """
    输出事件的通用结构，供不同输出后端（Sink）消费。
    - text: 文本内容
    - output_type: 输出类型
    - timestamp: 是否显示时间戳
    - lang: 语法高亮语言（可选，不提供则自动检测）
    - traceback: 是否显示异常堆栈
    - section: 若为章节标题输出，填入标题文本；否则为None
    - context: 额外上下文（预留给TUI/日志等）
    """

    text: str
    output_type: OutputType
    timestamp: bool = True
    lang: Optional[str] = None
    traceback: bool = False
    section: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class OutputSink(ABC):
    """输出后端抽象接口，不同前端（控制台/TUI/SSE/日志）实现该接口以消费输出事件。"""

    @abstractmethod
    def emit(self, event: OutputEvent) -> None:  # pragma: no cover - 抽象方法
        raise NotImplementedError


class ConsoleOutputSink(OutputSink):
    """
    默认控制台输出实现，保持与原 PrettyOutput 行为一致。
    """

    def emit(self, event: OutputEvent) -> None:
        # 章节输出
        if event.section is not None:
            text = Text(event.section, style=event.output_type.value, justify="center")
            panel = Panel(text, border_style=event.output_type.value)
            if get_pretty_output():
                console.print(panel)
            else:
                console.print(text)
            return

        # 普通内容输出
        lang = (
            event.lang
            if event.lang is not None
            else PrettyOutput._detect_language(event.text, default_lang="markdown")
        )

        # 与原实现保持一致的样式定义
        styles: Dict[OutputType, Dict[str, Any]] = {
            OutputType.SYSTEM: dict(bgcolor="#1e2b3c"),
            OutputType.CODE: dict(bgcolor="#1c2b1c"),
            OutputType.RESULT: dict(bgcolor="#1c1c2b"),
            OutputType.ERROR: dict(bgcolor="#2b1c1c"),
            OutputType.INFO: dict(bgcolor="#2b2b1c", meta={"icon": "ℹ️"}),
            OutputType.PLANNING: dict(bgcolor="#2b1c2b"),
            OutputType.PROGRESS: dict(bgcolor="#1c1c1c"),
            OutputType.SUCCESS: dict(bgcolor="#1c2b1c"),
            OutputType.WARNING: dict(bgcolor="#2b2b1c"),
            OutputType.DEBUG: dict(bgcolor="#1c1c1c"),
            OutputType.USER: dict(bgcolor="#1c2b2b"),
            OutputType.TOOL: dict(bgcolor="#1c2b2b"),
        }

        header_styles = {
            OutputType.SYSTEM: RichStyle(
                color="bright_cyan", bgcolor="#1e2b3c", frame=True, meta={"icon": "🤖"}
            ),
            OutputType.CODE: RichStyle(
                color="green", bgcolor="#1c2b1c", frame=True, meta={"icon": "📝"}
            ),
            OutputType.RESULT: RichStyle(
                color="bright_blue", bgcolor="#1c1c2b", frame=True, meta={"icon": "✨"}
            ),
            OutputType.ERROR: RichStyle(
                color="red", frame=True, bgcolor="#2b1c1c", meta={"icon": "❌"}
            ),
            OutputType.INFO: RichStyle(
                color="bright_cyan", frame=True, bgcolor="#2b2b1c", meta={"icon": "ℹ️"}
            ),
            OutputType.PLANNING: RichStyle(
                color="purple",
                bold=True,
                frame=True,
                bgcolor="#2b1c2b",
                meta={"icon": "📋"},
            ),
            OutputType.PROGRESS: RichStyle(
                color="white",
                encircle=True,
                frame=True,
                bgcolor="#1c1c1c",
                meta={"icon": "⏳"},
            ),
            OutputType.SUCCESS: RichStyle(
                color="bright_green",
                bold=True,
                strike=False,
                bgcolor="#1c2b1c",
                meta={"icon": "✅"},
            ),
            OutputType.WARNING: RichStyle(
                color="yellow",
                bold=True,
                blink2=True,
                bgcolor="#2b2b1c",
                meta={"icon": "⚠️"},
            ),
            OutputType.DEBUG: RichStyle(
                color="grey58",
                dim=True,
                conceal=True,
                bgcolor="#1c1c1c",
                meta={"icon": "🔍"},
            ),
            OutputType.USER: RichStyle(
                color="spring_green2",
                frame=True,
                bgcolor="#1c2b2b",
                meta={"icon": "👤"},
            ),
            OutputType.TOOL: RichStyle(
                color="dark_sea_green4",
                bgcolor="#1c2b2b",
                frame=True,
                meta={"icon": "🔧"},
            ),
        }

        Text(
            PrettyOutput._format(event.output_type, event.timestamp),
            style=header_styles[event.output_type],
        )
        content = Syntax(
            event.text,
            lang,
            theme="monokai",
            word_wrap=True,
            background_color=styles[event.output_type]["bgcolor"],
        )
        panel = Panel(
            content,
            border_style=header_styles[event.output_type],
            padding=(0, 0),
            highlight=True,
        )
        if get_pretty_output():
            console.print(panel)
        else:
            console.print(content)
        if event.traceback or (
            event.output_type == OutputType.ERROR and is_print_error_traceback()
        ):
            try:
                console.print_exception()
            except Exception as e:
                console.print(f"Error: {e}")


# 模块级输出分发器（默认注册控制台后端）
_output_sinks: List[OutputSink] = [ConsoleOutputSink()]


def emit_output(event: OutputEvent) -> None:
    """向所有已注册的输出后端广播事件。"""
    for sink in list(_output_sinks):
        try:
            sink.emit(event)
        except Exception as e:
            # 后端故障不影响其他后端
            console.print(f"[输出后端错误] {sink.__class__.__name__}: {e}")


class PrettyOutput:
    """
    使用rich库格式化和显示富文本输出的类。

    提供以下方法：
    - 使用适当的样式格式化不同类型的输出
    - 代码块的语法高亮
    - 结构化内容的面板显示
    - 渐进显示的流式输出
    """

    # 不同输出类型的图标
    _ICONS = {
        OutputType.SYSTEM: "🤖",
        OutputType.CODE: "📝",
        OutputType.RESULT: "✨",
        OutputType.ERROR: "❌",
        OutputType.INFO: "ℹ️",
        OutputType.PLANNING: "📋",
        OutputType.PROGRESS: "⏳",
        OutputType.SUCCESS: "✅",
        OutputType.WARNING: "⚠️",
        OutputType.DEBUG: "🔍",
        OutputType.USER: "👤",
        OutputType.TOOL: "🔧",
    }
    # 语法高亮的语言映射
    _lang_map = {
        "Python": "python",
        "JavaScript": "javascript",
        "TypeScript": "typescript",
        "Java": "java",
        "C++": "cpp",
        "C#": "csharp",
        "Ruby": "ruby",
        "PHP": "php",
        "Go": "go",
        "Rust": "rust",
        "Bash": "bash",
        "HTML": "html",
        "CSS": "css",
        "SQL": "sql",
        "R": "r",
        "Kotlin": "kotlin",
        "Swift": "swift",
        "Scala": "scala",
        "Perl": "perl",
        "Lua": "lua",
        "YAML": "yaml",
        "JSON": "json",
        "XML": "xml",
        "Markdown": "markdown",
        "Text": "text",
        "Shell": "bash",
        "Dockerfile": "dockerfile",
        "Makefile": "makefile",
        "INI": "ini",
        "TOML": "toml",
    }

    @staticmethod
    def _detect_language(text: str, default_lang: str = "markdown") -> str:
        """
        检测给定文本的编程语言。

        参数：
            text: 要分析的文本
            default_lang: 如果检测失败，默认返回的语言

        返回：
            str: 检测到的语言名称
        """
        try:
            lexer = guess_lexer(text)
            detected_lang = lexer.name  # type: ignore[attr-defined]
            return PrettyOutput._lang_map.get(detected_lang, default_lang)
        except (ClassNotFound, Exception):
            return default_lang

    @staticmethod
    def _format(output_type: OutputType, timestamp: bool = True) -> str:
        """
        使用时间戳和图标格式化输出头。

        参数：
            output_type: 输出类型
            timestamp: 是否包含时间戳

        返回：
            Text: 格式化后的rich Text对象
        """
        icon = PrettyOutput._ICONS.get(output_type, "")
        formatted = f"{icon}  "
        if timestamp:
            formatted += f"[{datetime.now().strftime('%H:%M:%S')}][{output_type.value}]"
        agent_info = get_agent_list()
        if agent_info:
            formatted += f"[{agent_info}]"
        return formatted

    @staticmethod
    def print(
        text: str,
        output_type: OutputType,
        timestamp: bool = True,
        lang: Optional[str] = None,
        traceback: bool = False,
    ):
        """
        使用样式和语法高亮打印格式化输出（已抽象为事件 + Sink 机制）。
        保持对现有调用方的向后兼容，同时为TUI/日志等前端预留扩展点。
        """
        event = OutputEvent(
            text=text,
            output_type=output_type,
            timestamp=timestamp,
            lang=lang,
            traceback=traceback,
        )
        emit_output(event)

    @staticmethod
    def section(title: str, output_type: OutputType = OutputType.INFO):
        """
        在样式化面板中打印章节标题（通过事件 + Sink 机制分发）。
        """
        event = OutputEvent(
            text="",
            output_type=output_type,
            section=title,
        )
        emit_output(event)

    @staticmethod
    # Sink管理（为外部注册自定义后端预留）
    @staticmethod
    def add_sink(sink: OutputSink) -> None:
        """注册一个新的输出后端。"""
        _output_sinks.append(sink)

    @staticmethod
    def clear_sinks(keep_default: bool = True) -> None:
        """清空已注册的输出后端；可选择保留默认控制台后端。"""
        if keep_default:
            globals()["_output_sinks"] = [
                s for s in _output_sinks if isinstance(s, ConsoleOutputSink)
            ]
        else:
            _output_sinks.clear()

    @staticmethod
    def get_sinks() -> List[OutputSink]:
        """获取当前已注册的输出后端列表（副本）。"""
        return list(_output_sinks)

    @staticmethod
    def print_gradient_text(
        text: str, start_color: Tuple[int, int, int], end_color: Tuple[int, int, int]
    ) -> None:
        """打印带有渐变色彩的文本。

        Args:
            text: 要打印的文本
            start_color: 起始RGB颜色元组 (r, g, b)
            end_color: 结束RGB颜色元组 (r, g, b)
        """
        lines = text.strip("\n").split("\n")
        total_lines = len(lines)
        colored_lines = []
        for i, line in enumerate(lines):
            # 计算当前行的渐变颜色
            r = int(
                start_color[0] + (end_color[0] - start_color[0]) * i / (total_lines - 1)
            )
            g = int(
                start_color[1] + (end_color[1] - start_color[1]) * i / (total_lines - 1)
            )
            b = int(
                start_color[2] + (end_color[2] - start_color[2]) * i / (total_lines - 1)
            )

            # 使用ANSI转义序列设置颜色
            colored_lines.append(f"\033[38;2;{r};{g};{b}m{line}\033[0m")
        colored_text = Text(
            "\n".join(colored_lines), style=OutputType.TOOL.value, justify="center"
        )
        panel = Panel(colored_text, box=SIMPLE)
        console.print(panel)
