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
from typing import Dict, Optional, Tuple, Any

from pygments.lexers import guess_lexer
from pygments.util import ClassNotFound
from rich.box import SIMPLE
from rich.panel import Panel
from rich.style import Style as RichStyle
from rich.syntax import Syntax
from rich.text import Text

from jarvis.jarvis_utils.config import get_pretty_output
from jarvis.jarvis_utils.globals import console, get_agent_list


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
        使用样式和语法高亮打印格式化输出。

        参数：
            text: 要打印的文本内容
            output_type: 输出类型（影响样式）
            timestamp: 是否显示时间戳
            lang: 语法高亮的语言
            traceback: 是否显示错误的回溯信息
        """
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
                color="gold1", frame=True, bgcolor="#2b2b1c", meta={"icon": "ℹ️"}
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

        lang = (
            lang
            if lang is not None
            else PrettyOutput._detect_language(text, default_lang="markdown")
        )
        header = Text(
            PrettyOutput._format(output_type, timestamp),
            style=header_styles[output_type],
        )
        content = Syntax(
            text,
            lang,
            theme="monokai",
            word_wrap=True,
            background_color=styles[output_type]["bgcolor"],
        )
        panel = Panel(
            content,
            border_style=header_styles[output_type],
            title=header,
            title_align="left",
            padding=(0, 0),
            highlight=True,
        )
        if get_pretty_output():
            console.print(panel)
        else:
            if len(text.strip().splitlines()) > 1:
                console.print(header)
                console.print(content)
            else:
                console.print(header, content)
        if traceback or output_type == OutputType.ERROR:
            try:
                console.print_exception()
            except Exception as e:
                console.print(f"Error: {e}")

    @staticmethod
    def section(title: str, output_type: OutputType = OutputType.INFO):
        """
        在样式化面板中打印章节标题。

        参数：
            title: 章节标题文本
            output_type: 输出类型（影响样式）
        """
        text = Text(title, style=output_type.value, justify="center")
        panel = Panel(text, border_style=output_type.value)
        if get_pretty_output():
            console.print(panel)
        else:
            console.print(text)

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
