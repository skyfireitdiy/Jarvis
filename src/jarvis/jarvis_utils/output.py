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

from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
from enum import Enum
import re
from typing import Any
from typing import Callable
from typing import Dict
from typing import Generator
from typing import List
from typing import Optional
from typing import Tuple
from datetime import datetime
import threading

from pygments.lexers import guess_lexer
from pygments.util import ClassNotFound
from rich.style import Style as RichStyle
from rich.syntax import Syntax
from rich.text import Text

from jarvis.jarvis_utils.config import get_pretty_output
from jarvis.jarvis_utils.config import is_print_error_traceback
from jarvis.jarvis_utils.globals import console
from jarvis.jarvis_utils.globals import get_agent_list
from jarvis.jarvis_utils.globals import get_agent


# Rich支持的标准颜色列表
RICH_STANDARD_COLORS = {
    "black",
    "red",
    "green",
    "yellow",
    "blue",
    "magenta",
    "cyan",
    "white",
    "bright_black",
    "bright_red",
    "bright_green",
    "bright_yellow",
    "bright_blue",
    "bright_magenta",
    "bright_cyan",
    "bright_white",
    "dark_red",
    "dark_green",
    "dark_yellow",
    "dark_blue",
    "dark_magenta",
    "dark_cyan",
    "grey0",
    "grey100",
    "grey50",
    "grey70",
    "grey30",
}


def _safe_color_get(color_name: str, fallback: str = "white") -> str:
    """
    安全的颜色获取函数，提供颜色验证和回退机制。

    参数：
        color_name: 期望的颜色名称
        fallback: 回退颜色名称（默认为白色）

    返回：
        有效的颜色名称，如果原颜色无效则返回回退颜色
    """
    if color_name in RICH_STANDARD_COLORS:
        return color_name

    # 尝试一些常见的颜色别名映射
    color_alias_map = {
        "dark_olive_green": "green",
        "orange3": "bright_yellow",
        "sea_green3": "green",
        "dark_sea_green": "green",
        "grey58": "grey50",
    }

    return color_alias_map.get(color_name, fallback)


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
        START: 任务开始
        TARGET: 目标任务
        STOP: 任务停止
        RETRY: 重试操作
        ROLLBACK: 回滚操作
        DIRECTORY: 目录相关
        STATISTICS: 统计信息
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
    START = "START"
    TARGET = "TARGET"
    STOP = "STOP"
    RETRY = "RETRY"
    ROLLBACK = "ROLLBACK"
    DIRECTORY = "DIRECTORY"
    STATISTICS = "STATISTICS"
    CHEAP_MODEL = "CHEAP_MODEL"
    NORMAL_MODEL = "NORMAL_MODEL"
    SMART_MODEL = "SMART_MODEL"
    # 流式输出类型
    STREAM_START = "STREAM_START"
    STREAM_CHUNK = "STREAM_CHUNK"
    STREAM_END = "STREAM_END"
    # Diff 可视化类型
    DIFF = "DIFF"


# 输出类型图标映射（统一的图标定义）
OUTPUT_ICONS = {
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
    OutputType.START: "🚀",
    OutputType.TARGET: "🎯",
    OutputType.STOP: "🛑",
    OutputType.RETRY: "🔄",
    OutputType.ROLLBACK: "🔙",
    OutputType.DIRECTORY: "📁",
    OutputType.STATISTICS: "📊",
    OutputType.CHEAP_MODEL: "💰",
    OutputType.NORMAL_MODEL: "⭐",
    OutputType.SMART_MODEL: "🧠",
    OutputType.STREAM_START: "⏳",
    OutputType.STREAM_CHUNK: "▶️",
    OutputType.STREAM_END: "✅",
    OutputType.DIFF: "🔄",
}


# Emoji 到输出类型的反向映射（包含别名）
EMOJI_TO_OUTPUT_TYPE = {
    "🤖": OutputType.SYSTEM,
    "📝": OutputType.CODE,
    "✨": OutputType.RESULT,
    "❌": OutputType.ERROR,
    "ℹ️": OutputType.INFO,
    "📋": OutputType.PLANNING,
    "⏳": OutputType.PROGRESS,
    "✅": OutputType.SUCCESS,
    "⚠️": OutputType.WARNING,
    "🔍": OutputType.DEBUG,
    "👤": OutputType.USER,
    "🔧": OutputType.TOOL,
    "🚀": OutputType.START,
    "🎯": OutputType.TARGET,
    "🛑": OutputType.STOP,
    "🔄": OutputType.RETRY,
    "🔙": OutputType.ROLLBACK,
    "📁": OutputType.DIRECTORY,
    "📂": OutputType.DIRECTORY,  # 别名
    "📊": OutputType.STATISTICS,
    "💰": OutputType.CHEAP_MODEL,
    "⭐": OutputType.NORMAL_MODEL,
    "🧠": OutputType.SMART_MODEL,
    "🎬": OutputType.STREAM_START,
    "▶️": OutputType.STREAM_CHUNK,
    "🏁": OutputType.STREAM_END,
    "🔄": OutputType.DIFF,
}


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

    # 章节样式配置（使用统一的图标）
    _SECTION_STYLES = {
        OutputType.SYSTEM: RichStyle(
            color="cyan", frame=True, meta={"icon": OUTPUT_ICONS[OutputType.SYSTEM]}
        ),
        OutputType.CODE: RichStyle(
            color="green", frame=True, meta={"icon": OUTPUT_ICONS[OutputType.CODE]}
        ),
        OutputType.RESULT: RichStyle(
            color="blue", frame=True, meta={"icon": OUTPUT_ICONS[OutputType.RESULT]}
        ),
        OutputType.ERROR: RichStyle(
            color="bright_red",
            frame=True,
            meta={"icon": OUTPUT_ICONS[OutputType.ERROR]},
            blink=True,
            bold=True,
        ),
        OutputType.INFO: RichStyle(
            color="grey70", frame=True, meta={"icon": OUTPUT_ICONS[OutputType.INFO]}
        ),
        OutputType.PLANNING: RichStyle(
            color="magenta",
            bold=True,
            frame=True,
            meta={"icon": OUTPUT_ICONS[OutputType.PLANNING]},
        ),
        OutputType.PROGRESS: RichStyle(
            color="grey50",
            encircle=True,
            frame=True,
            meta={"icon": OUTPUT_ICONS[OutputType.PROGRESS]},
        ),
        OutputType.SUCCESS: RichStyle(
            color="bright_green",
            bold=True,
            strike=False,
            meta={"icon": OUTPUT_ICONS[OutputType.SUCCESS]},
        ),
        OutputType.WARNING: RichStyle(
            color="bright_yellow",
            bold=True,
            blink=True,
            meta={"icon": OUTPUT_ICONS[OutputType.WARNING]},
        ),
        OutputType.DEBUG: RichStyle(
            color="grey50",
            dim=True,
            conceal=True,
            meta={"icon": OUTPUT_ICONS[OutputType.DEBUG]},
        ),
        OutputType.USER: RichStyle(
            color="bright_green",
            frame=True,
            meta={"icon": OUTPUT_ICONS[OutputType.USER]},
        ),
        OutputType.TOOL: RichStyle(
            color="green", frame=True, meta={"icon": OUTPUT_ICONS[OutputType.TOOL]}
        ),
        OutputType.START: RichStyle(
            color="bright_cyan",
            bold=True,
            frame=True,
            meta={"icon": OUTPUT_ICONS[OutputType.START]},
        ),
        OutputType.TARGET: RichStyle(
            color="bright_magenta",
            bold=True,
            frame=True,
            meta={"icon": OUTPUT_ICONS[OutputType.TARGET]},
        ),
        OutputType.STOP: RichStyle(
            color="bright_red",
            bold=True,
            frame=True,
            meta={"icon": OUTPUT_ICONS[OutputType.STOP]},
        ),
        OutputType.RETRY: RichStyle(
            color="grey70",
            bold=True,
            frame=True,
            meta={"icon": OUTPUT_ICONS[OutputType.RETRY]},
        ),
        OutputType.ROLLBACK: RichStyle(
            color="grey70",
            bold=True,
            frame=True,
            meta={"icon": OUTPUT_ICONS[OutputType.ROLLBACK]},
        ),
        OutputType.DIRECTORY: RichStyle(
            color="cyan", frame=True, meta={"icon": OUTPUT_ICONS[OutputType.DIRECTORY]}
        ),
        OutputType.STATISTICS: RichStyle(
            color="grey58",
            frame=True,
            meta={"icon": OUTPUT_ICONS[OutputType.STATISTICS]},
        ),
        OutputType.CHEAP_MODEL: RichStyle(
            color="grey58",
            frame=True,
            meta={"icon": OUTPUT_ICONS[OutputType.CHEAP_MODEL]},
        ),
        OutputType.NORMAL_MODEL: RichStyle(
            color="bright_blue",
            frame=True,
            meta={"icon": OUTPUT_ICONS[OutputType.NORMAL_MODEL]},
        ),
        OutputType.SMART_MODEL: RichStyle(
            color="bright_magenta",
            bold=True,
            frame=True,
            meta={"icon": OUTPUT_ICONS[OutputType.SMART_MODEL]},
        ),
        OutputType.DIFF: RichStyle(
            color="cyan",
            frame=True,
            meta={"icon": OUTPUT_ICONS[OutputType.DIFF]},
        ),
    }

    # 文字颜色映射
    _TEXT_COLORS = {
        OutputType.SYSTEM: "cyan",
        OutputType.CODE: "green",
        OutputType.RESULT: "blue",
        OutputType.ERROR: "bright_red",
        OutputType.INFO: "grey70",
        OutputType.PLANNING: "magenta",
        OutputType.PROGRESS: "grey50",
        OutputType.SUCCESS: "bright_green",
        OutputType.WARNING: "bright_yellow",
        OutputType.DEBUG: "grey30",
        OutputType.USER: "bright_green",
        OutputType.TOOL: "green",
        OutputType.START: "bright_cyan",
        OutputType.TARGET: "bright_magenta",
        OutputType.STOP: "bright_red",
        OutputType.RETRY: "grey70",
        OutputType.ROLLBACK: "grey70",
        OutputType.DIRECTORY: "cyan",
        OutputType.STATISTICS: "grey58",
        OutputType.CHEAP_MODEL: "grey58",
        OutputType.NORMAL_MODEL: "bright_blue",
        OutputType.SMART_MODEL: "bright_magenta",
        OutputType.DIFF: "cyan",
    }

    @staticmethod
    def _highlight_progress_text(
        text: str, output_type: OutputType, text_colors: Dict[OutputType, str]
    ) -> Text:
        """
        检测并高亮文本中的进度信息（如"第 X 轮"或"第 X/Y 轮"）。

        参数：
            text: 要处理的文本
            output_type: 输出类型
            text_colors: 颜色映射字典

        返回：
            Text: 格式化后的文本对象
        """
        progress_pattern = r"第\s*(\d+)(?:/(\d+))?\s*轮"
        if re.search(progress_pattern, text):
            # 包含进度信息，高亮数字
            parts = re.split(progress_pattern, text)
            colored_text = Text()
            for i, part in enumerate(parts):
                if i % 3 == 0:  # 普通文本
                    colored_text.append(
                        part,
                        style=RichStyle(
                            color=_safe_color_get(text_colors[output_type], "white")
                        ),
                    )
                elif i % 3 == 1:  # 第一个数字（当前轮次）
                    colored_text.append(
                        part,
                        style=RichStyle(
                            color=_safe_color_get(text_colors[output_type], "white"),
                            bold=True,
                        ),
                    )
                elif i % 3 == 2 and part:  # 第二个数字（总轮次，如果有）
                    colored_text.append(
                        f"/{part}",
                        style=RichStyle(
                            color=_safe_color_get(text_colors[output_type], "white")
                        ),
                    )
            return colored_text
        else:
            # 普通文本
            return Text(
                text,
                style=RichStyle(
                    color=_safe_color_get(text_colors[output_type], "white")
                ),
            )

    def emit(self, event: OutputEvent) -> None:
        # 流式输出类型由 Gateway 处理，CLI 模式忽略
        if event.output_type in (
            OutputType.STREAM_START,
            OutputType.STREAM_CHUNK,
            OutputType.STREAM_END,
        ):
            return

        # 章节输出
        if event.section is not None:
            # 使用带背景色和样式的Text替代Panel
            style_obj = self._SECTION_STYLES.get(
                event.output_type, RichStyle(color="white")
            )
            text = Text(f"\n{event.section}\n", style=style_obj, justify="center")
            if get_pretty_output():
                console.print(text)
            else:
                console.print(Text(event.section, style=event.output_type.value))
            return

        # 普通内容输出
        lang = (
            event.lang
            if event.lang is not None
            else PrettyOutput._detect_language(event.text, default_lang="markdown")
        )

        content = Syntax(
            event.text,
            lang,
            theme="monokai",
            word_wrap=True,
            # 使用终端默认背景色
        )
        # 直接输出带背景色的内容，不再使用Panel包装
        agent_name = PrettyOutput._format(event.output_type, event.timestamp)
        header_text = Text(
            agent_name,
            style=RichStyle(color="grey58", dim=True),
        )
        if get_pretty_output():
            # 检测是否为多行文本，如果是则使用更好的格式化
            lines = event.text.split("\n")
            is_multiline = len(lines) > 1

            # 检测是否包含列表项（以数字、-、* 开头）
            is_list = any(
                line.strip().startswith(("- ", "* ", "• "))
                or (
                    line.strip()
                    and line.strip()[0].isdigit()
                    and ". " in line.strip()[:5]
                )
                for line in lines
            )

            # 检测是否包含缩进内容（可能是子项或代码块）
            has_indent = any(line.startswith(("   ", "  ", "\t")) for line in lines)

            if is_multiline and (is_list or has_indent):
                # 多行列表或缩进内容：第一行显示header，后续行使用缩进
                combined_text = Text()
                combined_text.append(header_text)
                combined_text.append(" ")

                # 第一行：检测并高亮进度信息
                first_line = lines[0]
                colored_first_line = self._highlight_progress_text(
                    first_line, event.output_type, self._TEXT_COLORS
                )

                combined_text.append(colored_first_line)
                console.print(combined_text)

                # 后续行使用缩进，保持视觉层次
                for line in lines[1:]:
                    if line.strip():  # 非空行
                        # 检测列表项标记并适当格式化
                        line_stripped = line.strip()
                        is_list_item = line_stripped.startswith(("- ", "* ", "• ")) or (
                            line_stripped
                            and line_stripped[0].isdigit()
                            and ". " in line_stripped[:5]
                        )

                        # 如果已经是缩进的，保持原样；否则添加缩进
                        if line.startswith(("   ", "  ", "\t")):
                            display_line = line
                        else:
                            display_line = f"   {line}"

                        indented_line = Text(
                            display_line,
                            style=RichStyle(
                                color=_safe_color_get(
                                    self._TEXT_COLORS[event.output_type], "white"
                                ),
                                dim=not is_list_item
                                and line.startswith(
                                    ("   ", "  ", "\t")
                                ),  # 已缩进的非列表项稍微变暗
                            ),
                        )
                        console.print(indented_line)
                    else:
                        console.print()  # 空行保持原样
            else:
                # 单行或简单多行：合并header和content在同一行显示
                combined_text = Text()
                combined_text.append(header_text)
                combined_text.append(" ")

                # 检测并高亮进度信息（单行情况）
                colored_content = self._highlight_progress_text(
                    event.text, event.output_type, self._TEXT_COLORS
                )
                combined_text.append(colored_content)

                console.print(combined_text)
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

# 输出锁，确保多线程输出不会混乱
_output_lock = threading.Lock()


def emit_output(event: OutputEvent) -> None:
    """向所有已注册的输出后端广播事件。"""
    # 先检查是否需要跳过控制台输出（避免向终端打印 Gateway 专用数据）
    context = event.context or {}
    skip_console = context.get("_gateway_skip", False)

    # 如果没有设置跳过标记，向所有输出后端广播事件
    if not skip_console:
        with _output_lock:
            for sink in list(_output_sinks):
                try:
                    sink.emit(event)
                except Exception as e:
                    # 后端故障不影响其他后端
                    console.print(f"[输出后端错误] {sink.__class__.__name__}: {e}")

    try:
        from jarvis.jarvis_gateway.events import GatewayOutputEvent
        from jarvis.jarvis_gateway.manager import get_current_gateway
    except Exception:
        return

    gateway = get_current_gateway()
    if gateway is None:
        return

    gateway_context = dict(context) if context else None
    if gateway_context:
        gateway_context.pop("_gateway_skip", None)

    try:
        gateway.emit_output(
            GatewayOutputEvent(
                text=event.text,
                output_type=event.output_type.value,
                timestamp=event.timestamp,
                lang=event.lang,
                traceback=event.traceback,
                section=event.section,
                context=gateway_context,
            )
        )
    except Exception as e:
        console.print(f"[网关输出错误] {gateway.__class__.__name__}: {e}")


class PrettyOutput:
    """
    使用rich库格式化和显示富文本输出的类。

    提供以下方法：
    - 使用适当的样式格式化不同类型的输出
    - 代码块的语法高亮
    - 结构化内容的面板显示
    - 渐进显示的流式输出
    """

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
            detected_lang = lexer.name
            return PrettyOutput._lang_map.get(detected_lang, default_lang)
        except (ClassNotFound, Exception):
            return default_lang

    @staticmethod
    def _format(output_type: OutputType, timestamp: bool = True) -> str:
        """
        返回带时间戳前缀的Agent名字格式。

        参数：
            output_type: 输出类型（不再使用）
            timestamp: 是否包含时间戳

        返回：
            str: 包含时间戳和Agent名字的字符串
        """
        agent_info = get_agent_list()
        if not agent_info:
            return ""

        # 提取agent名字列表（去掉前面的数量标识）
        match = re.match(r"^\[(\d+)\](.+)$", agent_info)
        if match:
            count = match.group(1)
            agent_names = match.group(2).strip()
            # 为每个agent名字添加对应的emoji（根据其non_interactive状态）
            agent_names_with_emoji = []
            for name in agent_names.split(", "):
                name = name.strip()
                agent = get_agent(name)
                if agent and getattr(agent, "non_interactive", False):
                    emoji = "🔇"  # 非交互模式
                else:
                    emoji = "🔊"  # 交互模式
                agent_names_with_emoji.append(f"{name}{emoji}")
            agent_info = f"[{count}]{', '.join(agent_names_with_emoji)}"

        if timestamp:
            current_time = datetime.now().strftime("%H:%M:%S")
            # 使用更美观的时间戳格式，添加分隔符
            return f"⏰ {current_time} │ {agent_info}"
        else:
            return agent_info

    @staticmethod
    def _print(
        text: str,
        output_type: OutputType,
        timestamp: bool = True,
        lang: Optional[str] = None,
        traceback: bool = False,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        使用样式和语法高亮打印格式化输出（已抽象为事件 + Sink 机制）。
        内部接口，不建议直接使用，请使用 auto_print 代替。
        保持对现有调用方的向后兼容，同时为TUI/日志等前端预留扩展点。
        """
        # 自动获取上下文信息
        if context is None:
            context = {}

        # 获取当前 agent 名称
        try:
            from jarvis.jarvis_utils.globals import get_current_agent_name

            agent_name = get_current_agent_name()
            if agent_name and "agent_name" not in context:
                context["agent_name"] = agent_name
        except Exception:
            pass

        # 获取是否无交互模式
        try:
            from jarvis.jarvis_utils.config import is_non_interactive

            non_interactive = is_non_interactive()
            if "non_interactive" not in context:
                context["non_interactive"] = non_interactive
        except Exception:
            pass

        event = OutputEvent(
            text=text,
            output_type=output_type,
            timestamp=timestamp,
            lang=lang,
            traceback=traceback,
            context=context if context else None,
        )
        emit_output(event)

    @staticmethod
    def section(title: str, output_type: OutputType = OutputType.INFO) -> None:
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
        with _output_lock:
            _output_sinks.append(sink)

    @staticmethod
    def remove_sink(sink: OutputSink) -> None:
        """移除指定输出后端；若不存在则忽略。"""
        with _output_lock:
            try:
                _output_sinks.remove(sink)
            except ValueError:
                pass

    @staticmethod
    def clear_sinks(keep_default: bool = True) -> None:
        """清空已注册的输出后端；可选择保留默认控制台后端。"""
        with _output_lock:
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
        # 直接输出渐变文本，不再使用Panel包装
        console.print(colored_text)

    @staticmethod
    def auto_print(
        text: str,
        timestamp: bool = True,
        lang: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        自动根据打印信息的前缀emoji判断类型并着色输出。

        支持的emoji前缀映射：
        - ⚠️ -> WARNING (黄色警告)
        - ❌ -> ERROR (红色错误)
        - ✅ -> SUCCESS (绿色成功)
        - ℹ️ -> INFO (青色信息)
        - 📋 -> PLANNING (紫色规划)
        - ⏳ -> PROGRESS (白色进度)
        - 🔍 -> DEBUG (灰色调试)
        - 🤖 -> SYSTEM (青色系统)
        - 📝 -> CODE (绿色代码)
        - ✨ -> RESULT (蓝色结果)
        - 👤 -> USER (绿色用户)
        - 🔧 -> TOOL (绿色工具)

        参数：
            text: 要打印的文本
            timestamp: 是否显示时间戳
            lang: 语言类型（用于语法高亮）
            context: 额外上下文信息（用于前端显示 agent_name 等）
        """
        # 检测emoji前缀（使用统一的emoji映射）
        output_type = OutputType.INFO  # 默认类型
        detected_emoji = None
        for emoji, type_enum in EMOJI_TO_OUTPUT_TYPE.items():
            if text.startswith(emoji):
                output_type = type_enum
                detected_emoji = emoji
                break

        # 优化文本格式：确保emoji和文本之间有适当的间距
        if detected_emoji:
            # 如果emoji后没有空格，添加一个空格
            if len(text) > len(detected_emoji) and text[len(detected_emoji)] != " ":
                text = f"{detected_emoji} {text[len(detected_emoji) :].lstrip()}"

        # 如果打印的内容中有换行，就在要打印的内容开头添加一个换行
        if "\n" in text:
            text = f"\n{text}"

        # 使用现有的print方法进行着色输出
        PrettyOutput._print(
            text=text,
            output_type=output_type,
            timestamp=timestamp,
            lang=lang,
            context=context,
        )

    @staticmethod
    def print_markdown(
        content: str,
        title: Optional[str] = None,
        border_style: str = "bright_blue",
        theme: str = "monokai",
    ) -> None:
        """
        使用Panel显示带Markdown渲染的内容（标题左对齐）。

        参数：
            content: 要显示的markdown格式内容
            title: Panel标题（可选）
            border_style: 边框样式（默认"bright_blue"）
            theme: markdown高亮主题（默认"monokai"）
        """
        from rich import box
        from rich.markdown import Markdown, Heading
        from rich.panel import Panel
        from rich.text import Text

        # 保存原始方法
        _original_rich_console = Heading.__rich_console__

        def _left_aligned_heading_rich_console(self, console, options):
            """自定义Heading渲染，让标题左对齐"""
            text = self.text
            text.justify = "left"  # 改为左对齐
            if self.tag == "h1":
                yield Panel(
                    text,
                    box=box.HEAVY,
                    style="markdown.h1.border",
                )
            else:
                if self.tag == "h2":
                    yield Text("")
                yield text

        # 临时应用patch
        Heading.__rich_console__ = _left_aligned_heading_rich_console

        try:
            # 创建Markdown渲染对象
            markdown = Markdown(content, code_theme=theme)

            # 创建Panel包装Markdown对象
            panel = Panel(markdown, title=title, border_style=border_style, expand=True)

            # 打印Panel到终端
            console.print(panel)
        finally:
            # 恢复原始方法
            Heading.__rich_console__ = _original_rich_console

        # 通过事件系统输出到Gateway（用于Web界面）
        # 注意：只在 Gateway 模式下发送事件，避免 CLI 模式下重复打印
        try:
            from jarvis.jarvis_gateway.manager import get_current_gateway
        except Exception:
            return

        if get_current_gateway() is not None:
            event = OutputEvent(
                text=content,
                output_type=OutputType.RESULT,
                lang="markdown",
                section=title,
            )
            emit_output(event)

    @staticmethod
    def print_centered_panel(
        renderable: Any,
        title: Optional[str] = None,
        title_align: str = "center",
        border_style: str = "blue",
        **kwargs: Any,
    ) -> None:
        """
        使用居中的Panel显示内容。

        参数：
            renderable: 要显示的内容（Text、Group等Rich可渲染对象）
            title: Panel标题（可选）
            title_align: 标题对齐方式（默认"center"）
            border_style: 边框样式（默认"blue"）
            **kwargs: 传递给Panel的其他参数
        """
        from rich.align import Align
        from rich.panel import Panel

        panel = Panel(
            renderable,
            title=title,
            title_align=title_align,
            border_style=border_style,
            **kwargs,
        )
        console.print(Align.center(panel))

    @staticmethod
    def print_script_panel(
        content: str,
        title: str,
        lang: str = "python",
        theme: str = "monokai",
    ) -> None:
        """
        使用Panel显示带语法高亮的脚本内容。

        参数：
            content: 脚本内容
            title: Panel标题
            lang: 语法高亮语言（默认"python"）
            theme: 高亮主题（默认"monokai"）
        """
        from rich.panel import Panel

        syntax = Syntax(
            content,
            lang,
            theme=theme,
            line_numbers=True,
            word_wrap=True,
        )
        panel = Panel(syntax, title=title, border_style="cyan")
        console.print(panel)

        # 通过事件系统输出到Gateway（用于Web界面）
        # 注意：只在 Gateway 模式下发送事件，避免 CLI 模式下重复打印
        try:
            from jarvis.jarvis_gateway.manager import get_current_gateway
        except Exception:
            return

        if get_current_gateway() is not None:
            event = OutputEvent(
                text=content,
                output_type=OutputType.CODE,
                lang=lang,
                section=None,
            )
            emit_output(event)

    @staticmethod
    def print_resource_overview_panel(
        welcome_message: str,
        current_dir: str,
        stats_parts: List[str],
    ) -> None:
        """
        显示Jarvis资源概览面板（居中）。

        参数：
            welcome_message: 欢迎信息
            current_dir: 当前工作目录
            stats_parts: 统计信息列表（每项为带markup的字符串）
        """
        stats_text = Text.from_markup(" | ".join(stats_parts), justify="center")
        panel_content = Text()
        panel_content.append(welcome_message, style="bold white")
        panel_content.append("\n")
        panel_content.append(f"📁  工作目录: {current_dir}", style="dim white")
        panel_content.append("\n\n")
        panel_content.append(stats_text)
        panel_content.justify = "center"
        PrettyOutput.print_centered_panel(
            panel_content,
            title="✨ Jarvis 资源概览 ✨",
            title_align="center",
            border_style="blue",
            expand=False,
        )

    @staticmethod
    def print_welcome_panel(content: Any) -> None:
        """
        显示欢迎信息面板（居中）。

        参数：
            content: 欢迎内容（Group、Text等Rich可渲染对象）
        """
        from rich.align import Align
        from rich.panel import Panel

        terminal_width = console.width
        content_width = max(len(str(line)) for line in str(content).split("\n"))
        panel_width = max(terminal_width * 2 // 3, content_width)
        welcome_panel = Panel(
            content,
            border_style="cyan",
            expand=False,
            width=panel_width,
        )
        console.print(Align.center(welcome_panel))

    @staticmethod
    def stream_chat_with_panel(
        chat_iterator: Generator[Tuple[str, str], None, None],
        title: str,
        status_message: str,
        get_used_token_count: Callable[[], int],
        get_conversation_turn: Callable[[], int],
        get_platform_max_input_token_count: Callable[[], int],
        get_context_token_count: Callable[[str], int],
        append_session_history: Callable[[str, str], None],
        start_time: float,
        message: str = "",
        max_output: int = 0,
        check_interrupt: Callable[[], bool] = lambda: False,
        panel_lock: Optional[threading.RLock] = None,
    ) -> Tuple[str, float]:
        """
        使用Live+Panel进行流式聊天输出（pretty output模式）。

        参数：
            chat_iterator: 聊天响应迭代器
            title: 面板标题（模型名称）
            status_message: 等待首token时显示的Status消息
            get_used_token_count: 获取已用token数的回调
            get_conversation_turn: 获取对话轮次的回调
            get_platform_max_input_token_count: 获取平台最大token数的回调
            get_context_token_count: 计算文本token数的回调
            append_session_history: 追加会话历史的回调
            start_time: 开始时间戳
            message: 用户消息（用于中断时保存历史）
            max_output: 最大输出长度，0表示无限制
            check_interrupt: 检查是否请求中断的回调
            panel_lock: 用于保护panel更新的线程锁（可选）

        返回：
            Tuple[str, float]: (模型响应, 首token时间)
        """
        import time

        from rich import box
        from rich.live import Live
        from rich.panel import Panel
        from rich.status import Status
        from rich.text import Text

        from jarvis.jarvis_utils.config import get_conversation_turn_threshold
        from jarvis.jarvis_utils.config import is_immediate_abort

        first_chunk = None
        first_token_time = 0.0

        with Status(
            status_message,
            spinner="dots",
            console=console,
        ):
            try:
                while True:
                    if is_immediate_abort() and check_interrupt():
                        append_session_history(message, "")
                        return "", 0.0
                    first_chunk = next(chat_iterator)
                    if first_chunk and first_chunk[1]:  # 检查内容非空
                        first_token_time = time.time() - start_time
                        break
            except StopIteration:
                append_session_history(message, "")
                return "", 0.0

        _lock = panel_lock if panel_lock is not None else threading.RLock()

        def _format_progress_bar(percent: float, width: int = 15) -> str:
            percent = max(0, min(100, percent))
            filled = int(width * percent / 100)
            empty = width - filled
            return "█" * filled + "░" * empty

        def _get_token_usage_info(current_response: str) -> Tuple[float, str, str]:
            try:
                history_tokens = get_used_token_count()
                current_response_tokens = get_context_token_count(current_response)
                total_tokens = history_tokens + current_response_tokens
                max_tokens = get_platform_max_input_token_count()
                if max_tokens > 0:
                    usage_percent = (total_tokens / max_tokens) * 100
                    percent_color = (
                        "red"
                        if usage_percent >= 90
                        else "yellow"
                        if usage_percent >= 80
                        else "green"
                    )
                    progress_bar = _format_progress_bar(usage_percent, width=15)
                    return usage_percent, percent_color, progress_bar
                return 0.0, "green", ""
            except Exception:
                return 0.0, "green", ""

        def _update_panel_subtitle(
            pnl: Panel,
            response: str,
            is_completed: bool = False,
            duration: float = 0.0,
            first_tok_time: float = 0.0,
        ) -> None:
            current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            threshold = get_conversation_turn_threshold()
            try:
                usage_percent, percent_color, progress_bar = _get_token_usage_info(
                    response
                )
                max_tokens = get_platform_max_input_token_count()
                total_tokens = get_used_token_count() + get_context_token_count(
                    response
                )
                if is_completed:
                    response_tokens = get_context_token_count(response)
                    generation_time = (
                        duration - first_tok_time
                        if duration > first_tok_time
                        else duration
                    )
                    tokens_per_second = (
                        response_tokens / generation_time if generation_time > 0 else 0
                    )
                    if max_tokens > 0 and progress_bar:
                        pnl.subtitle = (
                            f"[bold green]✓ {current_time_str} | ({get_conversation_turn()}/{threshold}) | 对话完成耗时: {duration:.2f}秒 | "
                            f"首token: {first_tok_time:.2f}秒 | 速度: {tokens_per_second:.1f} tokens/s | "
                            f"Token: [{percent_color}]{progress_bar} {usage_percent:.1f}% ({total_tokens}/{max_tokens})[/{percent_color}][/bold green]"
                        )
                    else:
                        pnl.subtitle = f"[bold green]✓ {current_time_str} | ({get_conversation_turn()}/{threshold}) | 对话完成耗时: {duration:.2f}秒 | 首token: {first_tok_time:.2f}秒 | 速度: {tokens_per_second:.1f} tokens/s[/bold green]"
                else:
                    if max_tokens > 0 and progress_bar:
                        pnl.subtitle = (
                            f"[yellow]{current_time_str} | ({get_conversation_turn()}/{threshold}) | 正在回答... (按 Ctrl+C 中断) | "
                            f"Token: [{percent_color}]{progress_bar} {usage_percent:.1f}% ({total_tokens}/{max_tokens})[/{percent_color}][/yellow]"
                        )
                    else:
                        pnl.subtitle = f"[yellow]{current_time_str} | ({get_conversation_turn()}/{threshold}) | 正在回答... (按 Ctrl+C 中断)[/yellow]"
            except Exception:
                if is_completed:
                    pnl.subtitle = f"[bold green]✓ {current_time_str} | ({get_conversation_turn()}/{threshold}) | 对话完成耗时: {duration:.2f}秒[/bold green]"
                else:
                    pnl.subtitle = f"[yellow]{current_time_str} | ({get_conversation_turn()}/{threshold}) | 正在回答... (按 Ctrl+C 中断)[/yellow]"

        text_content = Text(overflow="fold")
        panel = Panel(
            text_content,
            title=f"[bold cyan]{title}[/bold cyan]",
            subtitle="[yellow]正在回答... (按 Ctrl+C 中断)[/yellow]",
            border_style="cyan",
            box=box.ROUNDED,
            expand=True,
        )

        response = ""
        last_subtitle_update_time = time.time()
        subtitle_update_interval = 1
        update_count = 0

        with Live(panel, refresh_per_second=6, transient=True) as live:

            def _update_panel_content(
                content: str,
                style: str = "bright_white",
                update_subtitle: bool = False,
                show_cursor: bool = True,
            ):
                nonlocal \
                    response, \
                    last_subtitle_update_time, \
                    update_count, \
                    text_content, \
                    panel

                # 使用 Text.append 支持不同样式
                new_text_obj = Text(overflow="fold")
                # 只在 text_content 不为空时才追加旧内容
                if text_content.plain:
                    plain_text = text_content.plain
                    # 每次更新时移除末尾旧光标（避免光标累积）
                    if plain_text.endswith("▌"):
                        plain_text = plain_text[:-1]
                    new_text_obj.append(plain_text, style=text_content.style)
                new_text_obj.append(content, style=style)
                # 添加动态光标效果
                if show_cursor and content:
                    new_text_obj.append("▌", style="bold cyan")
                update_count += 1

                max_text_height = console.height - 5
                if max_text_height <= 0:
                    max_text_height = 1

                lines = new_text_obj.wrap(
                    console,
                    console.width - 4 if console.width > 4 else 1,
                )

                final_text = new_text_obj
                if len(lines) > max_text_height:
                    final_text = Text(
                        "\n".join([line.plain for line in lines[-max_text_height:]]),
                        overflow="fold",
                    )

                with _lock:
                    text_content = final_text
                    # 直接更新panel的内部内容，避免重建整个Panel
                    panel.renderable = text_content

                    current_time = time.time()
                    should_update_subtitle = (
                        update_subtitle
                        or update_count % 10 == 0
                        or (current_time - last_subtitle_update_time)
                        >= subtitle_update_interval
                    )

                    if should_update_subtitle:
                        _update_panel_subtitle(panel, response, is_completed=False)
                        last_subtitle_update_time = current_time

                    try:
                        live.update(panel)
                    except (IndexError, RuntimeError):
                        pass

            # 解包元组 (chunk_type, chunk_content)
            first_chunk_type, first_chunk_content = first_chunk
            # 只有 content 类型才拼接到 response
            if first_chunk_type == "content":
                response += first_chunk_content
            if first_chunk_content:
                # 根据类型设置样式
                first_style = "dim" if first_chunk_type == "reason" else "bright_white"
                _update_panel_content(
                    first_chunk_content, style=first_style, update_subtitle=True
                )
                # 解析 title 获取 agent_name 和 model_name
                agent_name = ""
                model_name = ""
                if "·" in title:
                    parts = title.split("·")
                    if len(parts) > 1:
                        agent_name = parts[0].strip()
                        if "(" in parts[1]:
                            model_name = parts[1].split("(")[1].rstrip(")").strip()
                # 发送流式开始事件
                emit_output(
                    OutputEvent(
                        text="",
                        output_type=OutputType.STREAM_START,
                        timestamp=False,
                        context={
                            "agent_name": agent_name,
                            "model_name": model_name,
                            "start_time": start_time,
                        },
                    )
                )

                # 发送第一个chunk（避免第一个chunk丢失）
                if first_chunk_content:
                    emit_output(
                        OutputEvent(
                            text=first_chunk_content,
                            output_type=OutputType.STREAM_CHUNK,
                            timestamp=False,
                        )
                    )

            buffer: List[Tuple[str, str]] = []
            last_update_time = time.time()
            update_interval = 0.2
            min_buffer_size = 5

            def _flush_buffer():
                nonlocal buffer, last_update_time
                if buffer:
                    for content, style in buffer:
                        _update_panel_content(content, style=style)
                    buffer = []
                    last_update_time = time.time()

            for chunk_type, chunk_content in chat_iterator:
                if not chunk_content:
                    continue
                # 所有内容都显示，reason用灰色样式
                style = "dim" if chunk_type == "reason" else "bright_white"
                buffer.append((chunk_content, style))
                # 只有 content 类型才拼接到 response
                if chunk_type == "content":
                    response += chunk_content
                # 发送流式 chunk 事件（reason 和 content 都发送）
                if chunk_content:
                    emit_output(
                        OutputEvent(
                            text=chunk_content,
                            output_type=OutputType.STREAM_CHUNK,
                            timestamp=False,
                        )
                    )

                if max_output > 0 and len(response) >= max_output:
                    _flush_buffer()
                    append_session_history(message, response)
                    break

                current_time = time.time()
                should_update = (
                    len(buffer) >= min_buffer_size
                    or (current_time - last_update_time) >= update_interval
                )

                if should_update:
                    _flush_buffer()

                if is_immediate_abort() and check_interrupt():
                    _flush_buffer()
                    append_session_history(message, response)
                    break

            _flush_buffer()
            end_time = time.time()
            duration = end_time - start_time
            _update_panel_content("", update_subtitle=True, show_cursor=False)
            with _lock:
                _update_panel_subtitle(
                    panel,
                    response,
                    is_completed=True,
                    duration=duration,
                    first_tok_time=first_token_time,
                )
                live.update(panel)

        # 发送流式结束事件
        response_tokens = (
            get_context_token_count(response) if get_context_token_count else 0
        )
        generation_time = (
            duration - first_token_time if duration > first_token_time else duration
        )
        tokens_per_second = (
            response_tokens / generation_time if generation_time > 0 else 0
        )
        emit_output(
            OutputEvent(
                text="",
                output_type=OutputType.STREAM_END,
                timestamp=False,
                context={
                    "duration": duration,
                    "first_token_time": first_token_time,
                    "tokens": response_tokens,
                    "tokens_per_second": tokens_per_second,
                },
            )
        )

        return response, first_token_time

    @staticmethod
    def stream_chat_simple(
        chat_iterator: Generator[Tuple[str, str], None, None],
        prefix: str,
        start_time: float,
        message: str = "",
        max_output: int = 0,
        check_interrupt: Callable[[], bool] = lambda: False,
        append_session_history: Callable[[str, str], None] = lambda a, b: None,
        get_context_token_count: Optional[Callable[[str], int]] = None,
    ) -> Tuple[str, float]:
        """
        使用简单模式进行流式聊天输出（逐字符打印）。

        参数：
            chat_iterator: 聊天响应迭代器
            prefix: 输出前缀（如"🤖 模型输出 - xxx"）
            start_time: 开始时间戳
            message: 用户消息（用于中断时保存历史）
            max_output: 最大输出长度，0表示无限制
            check_interrupt: 检查是否请求中断的回调
            append_session_history: 追加会话历史的回调
            get_context_token_count: 计算文本token数的回调（用于显示速度，可选）
            output_sink: 输出后端（可选），用于 Gateway 模式流式发送

        返回：
            Tuple[str, float]: (模型响应, 首token时间)
        """
        import time

        # 解析 prefix 获取 agent_name 和 model_name
        agent_name = ""
        model_name = ""
        if "·" in prefix:
            parts = prefix.split("·")
            if len(parts) > 1:
                agent_name = parts[0].replace("🤖 模型输出 - ", "").strip()
                if "(" in parts[1]:
                    model_name = parts[1].split("(")[1].rstrip(")").strip()

        console.print(prefix, soft_wrap=False)
        response = ""
        first_token_time = 0.0

        # 发送流式开始事件
        emit_output(
            OutputEvent(
                text="",
                output_type=OutputType.STREAM_START,
                timestamp=False,
                context={
                    "agent_name": agent_name,
                    "model_name": model_name,
                    "start_time": start_time,
                },
            )
        )

        for chunk_type, chunk_content in chat_iterator:
            if chunk_content and first_token_time == 0.0:
                first_token_time = time.time() - start_time
            # 打印时 reason 和 content 都显示，reason用灰色样式
            style = "dim" if chunk_type == "reason" else "bright_white"
            console.print(chunk_content, end="", style=style)
            # 返回时只拼接 content 类型
            if chunk_type == "content":
                response += chunk_content
            # 发送流式 chunk 事件
            if chunk_content:
                emit_output(
                    OutputEvent(
                        text=chunk_content,
                        output_type=OutputType.STREAM_CHUNK,
                        timestamp=False,
                    )
                )
            if max_output > 0 and len(response) >= max_output:
                append_session_history(message, response)
                return response, first_token_time
            if check_interrupt():
                append_session_history(message, response)
                return response, first_token_time
        console.print()
        end_time = time.time()
        duration = end_time - start_time
        response_tokens = (
            get_context_token_count(response) if get_context_token_count else 0
        )
        generation_time = (
            duration - first_token_time if duration > first_token_time else duration
        )
        tokens_per_second = (
            response_tokens / generation_time if generation_time > 0 else 0
        )
        console.print(
            f"✓ 对话完成耗时: {duration:.2f}秒 | 首token: {first_token_time:.2f}秒 | 速度: {tokens_per_second:.1f} tokens/s"
        )

        # 发送流式结束事件
        emit_output(
            OutputEvent(
                text="",
                output_type=OutputType.STREAM_END,
                timestamp=False,
                context={
                    "duration": duration,
                    "first_token_time": first_token_time,
                    "tokens": response_tokens,
                    "tokens_per_second": tokens_per_second,
                },
            )
        )

        return response, first_token_time
