"""
Input Handling Module
This module provides utilities for handling user input in the Jarvis system.
It includes:
- Single line input with history support
- Multi-line input with enhanced completion
- File path completion with fuzzy matching
- Custom key bindings for input control
"""
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style as PromptStyle
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.completion import Completer, Completion, PathCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.key_binding import KeyBindings
from fuzzywuzzy import process
from colorama import Fore, Style as ColoramaStyle
from ..jarvis_utils.output import PrettyOutput, OutputType
def get_single_line_input(tip: str) -> str:
    """
    Get single line input with history support.
    
    Args:
        tip: The prompt message to display
        
    Returns:
        str: The user's input
    """
    session = PromptSession(history=None)
    style = PromptStyle.from_dict({
        'prompt': 'ansicyan',
    })
    return session.prompt(f"{tip}", style=style)
class FileCompleter(Completer):
    """
    Custom completer for file paths with fuzzy matching.
    
    Attributes:
        path_completer: Base path completer
        max_suggestions: Maximum number of suggestions to show
        min_score: Minimum matching score for suggestions
    """
    def __init__(self):
        """Initialize the file completer with default settings."""
        self.path_completer = PathCompleter()
        self.max_suggestions = 10
        self.min_score = 10
    def get_completions(self, document: Document, complete_event) -> Completion: # type: ignore
        """
        Generate completions for file paths with fuzzy matching.
        
        Args:
            document: The current document being edited
            complete_event: The completion event
            
        Yields:
            Completion: Suggested completions
        """
        text = document.text_before_cursor
        cursor_pos = document.cursor_position
        # Find all @ positions in text
        at_positions = [i for i, char in enumerate(text) if char == '@']
        if not at_positions:
            return
        # Get the last @ position
        current_at_pos = at_positions[-1]
        # If cursor is not after the last @, don't complete
        if cursor_pos <= current_at_pos:
            return
        # Check if there's a space after @
        text_after_at = text[current_at_pos + 1:cursor_pos]
        if ' ' in text_after_at:
            return
        # Get the text after the current @
        file_path = text_after_at.strip()
        # Calculate replacement length
        replace_length = len(text_after_at) + 1
        # Get all possible files using git ls-files
        all_files = []
        try:
            import subprocess
            result = subprocess.run(['git', 'ls-files'], 
                                 stdout=subprocess.PIPE, 
                                 stderr=subprocess.PIPE,
                                 text=True)
            if result.returncode == 0:
                all_files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        except Exception:
            pass
        # Generate completions
        if not file_path:
            scored_files = [(path, 100) for path in all_files[:self.max_suggestions]]
        else:
            scored_files_data = process.extract(file_path, all_files, limit=self.max_suggestions)
            scored_files = [(m[0], m[1]) for m in scored_files_data]
            scored_files.sort(key=lambda x: x[1], reverse=True)
            scored_files = scored_files[:self.max_suggestions]
        # Yield completions
        for path, score in scored_files:
            if not file_path or score > self.min_score:
                display_text = path
                if file_path and score < 100:
                    display_text = f"{path} ({score}%)"
                yield Completion(
                    text=f"'{path}'",
                    start_position=-replace_length,
                    display=display_text,
                    display_meta="File"
                ) # type: ignore
def get_multiline_input(tip: str) -> str:
    """
    Get multi-line input with enhanced completion and confirmation.
    
    Args:
        tip: The prompt message to display
        
    Returns:
        str: The user's input, or empty string if canceled
    """
    # Display input instructions
    PrettyOutput.section("用户输入 - 使用 @ 触发文件补全，Tab 选择补全项，Ctrl+J 提交，按 Ctrl+C 取消输入", OutputType.USER)
    print(f"{Fore.GREEN}{tip}{ColoramaStyle.RESET_ALL}")
    # Configure key bindings
    bindings = KeyBindings()
    @bindings.add('enter')
    def _(event):
        """Handle enter key for completion or new line."""
        if event.current_buffer.complete_state:
            event.current_buffer.apply_completion(event.current_buffer.complete_state.current_completion)
        else:
            event.current_buffer.insert_text('\n')
    @bindings.add('c-j')
    def _(event):
        """Handle Ctrl+J for submission."""
        event.current_buffer.validate_and_handle()
    # Configure prompt session
    style = PromptStyle.from_dict({
        'prompt': 'ansicyan',
    })
    try:
        session = PromptSession(
            history=None,
            completer=FileCompleter(),
            key_bindings=bindings,
            complete_while_typing=True,
            multiline=True,
            vi_mode=False,
            mouse_support=False
        )
        prompt = FormattedText([
            ('class:prompt', '>>> ')
        ])
        # Get input
        text = session.prompt(
            prompt,
            style=style,
        ).strip()
        return text
    except KeyboardInterrupt:
        PrettyOutput.print("输入已取消", OutputType.INFO)
        return ""