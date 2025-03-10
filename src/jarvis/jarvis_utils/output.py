"""
Output Formatting Module
This module provides rich text formatting and display utilities for the Jarvis system.
It includes:
- OutputType enum for categorizing different types of output
- PrettyOutput class for formatting and displaying styled output
- Syntax highlighting support for various programming languages
- Panel-based display for structured output
"""
from enum import Enum
from datetime import datetime
from typing import Optional
from rich.panel import Panel
from rich.box import HEAVY
from rich.text import Text
from rich.syntax import Syntax
from rich.style import Style as RichStyle
from pygments.lexers import guess_lexer
from pygments.util import ClassNotFound
from .globals import console, get_agent_list
class OutputType(Enum):
    """
    Enumeration of output types for categorizing and styling different types of messages.
    
    Attributes:
        SYSTEM: AI assistant message
        CODE: Code related output
        RESULT: Tool execution result
        ERROR: Error information
        INFO: System prompt
        PLANNING: Task planning
        PROGRESS: Execution progress
        SUCCESS: Success information
        WARNING: Warning information
        DEBUG: Debug information
        USER: User input
        TOOL: Tool call
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
    Class for formatting and displaying rich text output using the rich library.
    
    Provides methods for:
    - Formatting different types of output with appropriate styling
    - Syntax highlighting for code blocks
    - Panel-based display for structured content
    - Stream output for progressive display
    """
    # Icons for different output types
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
    # Language mapping for syntax highlighting
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
        Detect the programming language of the given text.
        
        Args:
            text: The text to analyze
            default_lang: Default language if detection fails
            
        Returns:
            str: Detected language name
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
        Format the output header with timestamp and icon.
        
        Args:
            output_type: Type of output
            timestamp: Whether to include timestamp
            
        Returns:
            Text: Formatted rich Text object
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
        Print formatted output with styling and syntax highlighting.
        
        Args:
            text: The text content to print
            output_type: The type of output (affects styling)
            timestamp: Whether to show timestamp
            lang: Language for syntax highlighting
            traceback: Whether to show traceback for errors
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
            box=HEAVY,
        )
        console.print(panel)
        if traceback or output_type == OutputType.ERROR:
            console.print_exception()
    @staticmethod
    def section(title: str, output_type: OutputType = OutputType.INFO):
        """
        Print a section title in a styled panel.
        
        Args:
            title: The section title text
            output_type: The type of output (affects styling)
        """
        panel = Panel(
            Text(title, style=output_type.value, justify="center"),
            border_style=output_type.value
        )
        console.print()
        console.print(panel)
        console.print()
    @staticmethod
    def print_stream(text: str):
        """
        Print stream output without line break.
        
        Args:
            text: The text to print
        """
        style = PrettyOutput._get_style(OutputType.SYSTEM)
        console.print(text, style=style, end="")
    @staticmethod
    def print_stream_end():
        """
        End stream output with line break.
        """
        end_style = PrettyOutput._get_style(OutputType.SUCCESS)
        console.print("\n", style=end_style)
        console.file.flush()
    @staticmethod
    def _get_style(output_type: OutputType) -> RichStyle:
        """
        Get pre-defined RichStyle for output type.
        
        Args:
            output_type: The output type to get style for
            
        Returns:
            RichStyle: The corresponding style
        """
        return console.get_style(output_type.value)