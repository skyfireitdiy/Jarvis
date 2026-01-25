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
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
from datetime import datetime

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
    def print(
        text: str,
        output_type: OutputType,
        timestamp: bool = True,
        lang: Optional[str] = None,
        traceback: bool = False,
    ) -> None:
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
        # 直接输出渐变文本，不再使用Panel包装
        console.print(colored_text)

    @staticmethod
    def auto_print(text: str, timestamp: bool = True) -> None:
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
        PrettyOutput.print(text=text, output_type=output_type, timestamp=timestamp)

    @staticmethod
    def print_markdown(
        content: str,
        title: Optional[str] = None,
        border_style: str = "bright_blue",
        theme: str = "monokai",
    ) -> None:
        """
        使用Panel显示带markdown语法高亮的内容。

        参数：
            content: 要显示的markdown格式内容
            title: Panel标题（可选）
            border_style: 边框样式（默认"bright_blue"）
            theme: markdown高亮主题（默认"monokai"）
        """
        from rich.panel import Panel

        # 创建markdown语法高亮对象
        syntax = Syntax(content, "markdown", theme=theme, word_wrap=True)

        # 创建Panel包装Syntax对象
        panel = Panel(syntax, title=title, border_style=border_style, expand=True)

        # 打印Panel
        console.print(panel)
