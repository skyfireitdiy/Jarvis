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
    SYSTEM = "SYSTEM"      # AI assistant message
    CODE = "CODE"         # Code related
    RESULT = "RESULT"     # Tool execution result
    ERROR = "ERROR"       # Error information
    INFO = "INFO"         # System prompt
    PLANNING = "PLANNING" # Task planning
    PROGRESS = "PROGRESS" # Execution progress
    SUCCESS = "SUCCESS"   # Success information
    WARNING = "WARNING"   # Warning information
    DEBUG = "DEBUG"       # Debug information
    USER = "USER"         # User input
    TOOL = "TOOL"         # Tool call
class PrettyOutput:
    """Pretty output using rich"""
    
    # Icons for different output types
    _ICONS = {
        OutputType.SYSTEM: "🤖",    # Robot - AI assistant
        OutputType.CODE: "📝",      # Notebook - Code
        OutputType.RESULT: "✨",    # Flash - Result
        OutputType.ERROR: "❌",     # Error - Error
        OutputType.INFO: "ℹ️",      # Info - Prompt
        OutputType.PLANNING: "📋",  # Clipboard - Planning
        OutputType.PROGRESS: "⏳",  # Hourglass - Progress
        OutputType.SUCCESS: "✅",   # Checkmark - Success
        OutputType.WARNING: "⚠️",   # Warning - Warning
        OutputType.DEBUG: "🔍",     # Magnifying glass - Debug
        OutputType.USER: "👤",      # User - User
        OutputType.TOOL: "🔧",      # Wrench - Tool
    }
    # Common language mapping dictionary
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
        """Helper method to detect language and map it to syntax highlighting name"""
        try:
            lexer = guess_lexer(text)
            detected_lang = lexer.name
            return PrettyOutput._lang_map.get(detected_lang, default_lang)
        except ClassNotFound:
            return default_lang
        except Exception:
            return default_lang
    @staticmethod
    def _format(output_type: OutputType, timestamp: bool = True) -> Text:
        """Format output text using rich Text"""
        # Create rich Text object
        formatted = Text()
        
        # Add timestamp and agent info
        if timestamp:
            formatted.append(f"[{datetime.now().strftime('%H:%M:%S')}][{output_type.value}]", style=output_type.value)
        agent_info = get_agent_list()
        if agent_info:  # Only add brackets if there's agent info
            formatted.append(f"[{agent_info}]", style="blue")
        # Add icon
        icon = PrettyOutput._ICONS.get(output_type, "")
        formatted.append(f" {icon} ", style=output_type.value)
        
        return formatted
    @staticmethod
    def print(text: str, output_type: OutputType, timestamp: bool = True, lang: Optional[str] = None, traceback: bool = False):
        """Print formatted output using rich console with styling
        
        Args:
            text: The text content to print
            output_type: The type of output (affects styling)
            timestamp: Whether to show timestamp
            lang: Language for syntax highlighting
            traceback: Whether to show traceback for errors
        """
        
        # Define styles for different output types
        styles = {
            OutputType.SYSTEM: RichStyle(
                color="bright_cyan", 
                bgcolor="#1a1a1a",
                frame=True,
                meta={"icon": "🤖"}
            ),
            OutputType.CODE: RichStyle(
                color="green", 
                bgcolor="#1a1a1a",
                frame=True,
                meta={"icon": "📝"}
            ),
            OutputType.RESULT: RichStyle(
                color="bright_blue",
                bgcolor="#1a1a1a",
                frame=True,
                meta={"icon": "✨"}
            ),
            OutputType.ERROR: RichStyle(
                color="red", 
                frame=True,
                bgcolor="dark_red",
                meta={"icon": "❌"}
            ),
            OutputType.INFO: RichStyle(
                color="gold1",
                frame=True,
                bgcolor="grey11",
                meta={"icon": "ℹ️"}
            ),
            OutputType.PLANNING: RichStyle(
                color="purple", 
                bold=True,
                frame=True,
                meta={"icon": "📋"}
            ),
            OutputType.PROGRESS: RichStyle(
                color="white", 
                encircle=True,
                frame=True,
                meta={"icon": "⏳"}
            ),
            OutputType.SUCCESS: RichStyle(
                color="bright_green", 
                bold=True,
                strike=False,
                meta={"icon": "✅"},
            ),
            OutputType.WARNING: RichStyle(
                color="yellow", 
                bold=True,
                blink2=True,
                bgcolor="dark_orange",
                meta={"icon": "⚠️"}
            ),
            OutputType.DEBUG: RichStyle(
                color="grey58",
                dim=True,
                conceal=True,
                meta={"icon": "🔍"}
            ),
            OutputType.USER: RichStyle(
                color="spring_green2",
                frame=True,
                meta={"icon": "👤"}
            ),
            OutputType.TOOL: RichStyle(
                color="dark_sea_green4",
                bgcolor="grey19",
                frame=True,
                meta={"icon": "🔧"}
            )
        }
        
        # Get formatted header
        lang = lang if lang is not None else PrettyOutput._detect_language(text, default_lang='markdown')
        header = PrettyOutput._format(output_type, timestamp)
        
        # Create syntax highlighted content
        content = Syntax(
            text,
            lang,
            theme="monokai",
            word_wrap=True,
        )
        
        # Create panel with styling
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
        
        # Print panel
        console.print(panel)
        
        # Print stack trace for errors if requested
        if traceback or output_type == OutputType.ERROR:
            console.print_exception()
    @staticmethod
    def section(title: str, output_type: OutputType = OutputType.INFO):
        """Print section title in a panel"""
        panel = Panel(
            Text(title, style=output_type.value, justify="center"),
            border_style=output_type.value
        )
        console.print()
        console.print(panel)
        console.print()
    @staticmethod
    def print_stream(text: str):
        """Print stream output without line break"""
        # 使用进度类型样式
        style = PrettyOutput._get_style(OutputType.SYSTEM)
        console.print(text, style=style, end="")
    @staticmethod
    def print_stream_end():
        """End stream output with line break"""
        # 结束符样式
        end_style = PrettyOutput._get_style(OutputType.SUCCESS)
        console.print("\n", style=end_style)
        console.file.flush()
    @staticmethod
    def _get_style(output_type: OutputType) -> RichStyle:
        """Get pre-defined RichStyle for output type"""
        return console.get_style(output_type.value)