"""
输出格式化模块
该模块为Jarvis系统提供了丰富的文本格式化和显示工具。
包含：
- 用于分类不同输出类型的OutputType枚举
- 用于格式化和显示样式化输出的PrettyOutput类
- 多种编程语言的语法高亮支持
- 结构化输出的面板显示
"""
from enum import Enum
from datetime import datetime
from typing import Optional
from rich.panel import Panel
from rich.text import Text
from rich.syntax import Syntax
from rich.style import Style as RichStyle
from pygments.lexers import guess_lexer
from pygments.util import ClassNotFound
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
        'Python': 'python',
        'JavaScript': 'javascript',
        'TypeScript': 'typescript',
        'Java': 'java',
        'C++': 'cpp',
        'C#': 'csharp',
        'Ruby': 'ruby',
        'PHP': 'php',
        'Go': 'go',
        'Rust': 'rust',
        'Bash': 'bash',
        'HTML': 'html',
        'CSS': 'css',
        'SQL': 'sql',
        'R': 'r',
        'Kotlin': 'kotlin',
        'Swift': 'swift',
        'Scala': 'scala',
        'Perl': 'perl',
        'Lua': 'lua',
        'YAML': 'yaml',
        'JSON': 'json',
        'XML': 'xml',
        'Markdown': 'markdown',
        'Text': 'text',
        'Shell': 'bash',
        'Dockerfile': 'dockerfile',
        'Makefile': 'makefile',
        'INI': 'ini',
        'TOML': 'toml',
    }
    @staticmethod
    def _detect_language(text: str, default_lang: str = 'markdown') -> str:
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
    def _format(output_type: OutputType, timestamp: bool = True) -> Text:
        """
        使用时间戳和图标格式化输出头。

        参数：
            output_type: 输出类型
            timestamp: 是否包含时间戳

        返回：
            Text: 格式化后的rich Text对象
        """
        formatted = Text()
        if timestamp:
            formatted.append(f"[{datetime.now().strftime('%H:%M:%S')}][{output_type.value}]", style=output_type.value)
        agent_info = get_agent_list()
        if agent_info:
            formatted.append(f"[{agent_info}]", style="blue")
        icon = PrettyOutput._ICONS.get(output_type, "")
        formatted.append(f" {icon} ", style=output_type.value)
        return formatted
    @staticmethod
    def print(text: str, output_type: OutputType, timestamp: bool = True, lang: Optional[str] = None, traceback: bool = False):
        """
        使用样式和语法高亮打印格式化输出。

        参数：
            text: 要打印的文本内容
            output_type: 输出类型（影响样式）
            timestamp: 是否显示时间戳
            lang: 语法高亮的语言
            traceback: 是否显示错误的回溯信息
        """
        styles = {
            OutputType.SYSTEM: RichStyle(color="bright_cyan", bgcolor="#1a1a1a", frame=True, meta={"icon": "🤖"}),
            OutputType.CODE: RichStyle(color="green", bgcolor="#1a1a1a", frame=True, meta={"icon": "📝"}),
            OutputType.RESULT: RichStyle(color="bright_blue", bgcolor="#1a1a1a", frame=True, meta={"icon": "✨"}),
            OutputType.ERROR: RichStyle(color="red", frame=True, bgcolor="dark_red", meta={"icon": "❌"}),
            OutputType.INFO: RichStyle(color="gold1", frame=True, bgcolor="grey11", meta={"icon": "ℹ️"}),
            OutputType.PLANNING: RichStyle(color="purple", bold=True, frame=True, meta={"icon": "📋"}),
            OutputType.PROGRESS: RichStyle(color="white", encircle=True, frame=True, meta={"icon": "⏳"}),
            OutputType.SUCCESS: RichStyle(color="bright_green", bold=True, strike=False, meta={"icon": "✅"}),
            OutputType.WARNING: RichStyle(color="yellow", bold=True, blink2=True, bgcolor="dark_orange", meta={"icon": "⚠️"}),
            OutputType.DEBUG: RichStyle(color="grey58", dim=True, conceal=True, meta={"icon": "🔍"}),
            OutputType.USER: RichStyle(color="spring_green2", frame=True, meta={"icon": "👤"}),
            OutputType.TOOL: RichStyle(color="dark_sea_green4", bgcolor="grey19", frame=True, meta={"icon": "🔧"}),
        }
        lang = lang if lang is not None else PrettyOutput._detect_language(text, default_lang='markdown')
        header = PrettyOutput._format(output_type, timestamp)
        content = Syntax(text, lang, theme="monokai", word_wrap=True)
        panel = Panel(
            content,
            style=styles[output_type],
            border_style=styles[output_type],
            title=header,
            title_align="left",
            padding=(0, 0),
            highlight=True,
            # box=HEAVY,
        )
        console.print()
        console.print(panel)
        if traceback or output_type == OutputType.ERROR:
            console.print_exception()
    @staticmethod
    def section(title: str, output_type: OutputType = OutputType.INFO):
        """
        在样式化面板中打印章节标题。

        参数：
            title: 章节标题文本
            output_type: 输出类型（影响样式）
        """
        panel = Panel(
            Text(title, style=output_type.value, justify="center"),
            border_style=output_type.value
        )
        console.print()
        console.print(panel)
        console.print()
    @staticmethod
    def print_stream(text: str, is_thinking: bool = False):
        """
        打印流式输出，不带换行符。

        参数：
            text: 要打印的文本
        """
        style = RichStyle(color="bright_cyan", bold=True, frame=True, meta={"icon": "🤖"})
        if is_thinking:
            style = RichStyle(color="grey58", italic=True, frame=True, meta={"icon": "🤖"})
        console.print(text, style=style, end="")
    @staticmethod
    def print_stream_end():
        """
        结束流式输出，带换行符。
        """
        end_style = PrettyOutput._get_style(OutputType.SUCCESS)
        console.print("\n", style=end_style)
        console.file.flush()
    @staticmethod
    def _get_style(output_type: OutputType) -> RichStyle:
        """
        获取预定义的RichStyle用于输出类型。

        参数：
            output_type: 要获取样式的输出类型

        返回：
            RichStyle: 对应的样式
        """
        return console.get_style(output_type.value)
