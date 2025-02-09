
import os
import re
from typing import Dict, List
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter, Completer, Completion
from jarvis.utils import OutputType, PrettyOutput


def _parse_file_selection(input_str: str, max_index: int) -> List[int]:
    """Parse file selection expression
    
    Supported formats:
    - Single number: "1"
    - Comma-separated: "1,3,5"
    - Range: "1-5"
    - Combination: "1,3-5,7"
    
    Args:
        input_str: User input selection expression
        max_index: Maximum selectable index
        
    Returns:
        List[int]: Selected index list (starting from 0)
    """
    selected = set()
    
    # Remove all whitespace characters
    input_str = "".join(input_str.split())
    
    # Process comma-separated parts
    for part in input_str.split(","):
        if not part:
            continue
        
        # Process range (e.g.: 3-6)
        if "-" in part:
            try:
                start, end = map(int, part.split("-"))
                # Convert to index starting from 0
                start = max(0, start - 1)
                end = min(max_index, end - 1)
                if start <= end:
                    selected.update(range(start, end + 1))
            except ValueError:
                PrettyOutput.print(f"Ignore invalid range expression: {part}", OutputType.WARNING)
        # Process single number
        else:
            try:
                index = int(part) - 1  # Convert to index starting from 0
                if 0 <= index < max_index:
                    selected.add(index)
                else:
                    PrettyOutput.print(f"Ignore index out of range: {part}", OutputType.WARNING)
            except ValueError:
                PrettyOutput.print(f"Ignore invalid number: {part}", OutputType.WARNING)
    
    return sorted(list(selected))

def _get_file_completer(root_dir: str) -> Completer:
    """Create file path completer"""
    class FileCompleter(Completer):
        def __init__(self, root_dir: str):
            self.root_dir = root_dir
            
        def get_completions(self, document, complete_event):
            # Get the text of the current input
            text = document.text_before_cursor
            
            # If the input is empty, return all files in the root directory
            if not text:
                for path in self._list_files(""):
                    yield Completion(path, start_position=0)
                return
                
            # Get the current directory and partial file name
            current_dir = os.path.dirname(text)
            file_prefix = os.path.basename(text)
            
            # List matching files
            search_dir = os.path.join(self.root_dir, current_dir) if current_dir else self.root_dir
            if os.path.isdir(search_dir):
                for path in self._list_files(current_dir):
                    if path.startswith(text):
                        yield Completion(path, start_position=-len(text))
        
        def _list_files(self, current_dir: str) -> List[str]:
            """List all files in the specified directory (recursively)"""
            files = []
            search_dir = os.path.join(self.root_dir, current_dir)
            
            for root, _, filenames in os.walk(search_dir):
                for filename in filenames:
                    full_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(full_path, self.root_dir)
                    # Ignore .git directory and other hidden files
                    if not any(part.startswith('.') for part in rel_path.split(os.sep)):
                        files.append(rel_path)
            
            return sorted(files)

    return FileCompleter(root_dir)

def _fuzzy_match_files(root_dir: str, pattern: str) -> List[str]:
    """Fuzzy match file path
    
    Args:
        pattern: Matching pattern
        
    Returns:
        List[str]: List of matching file paths
    """
    matches = []
    
    # 将模式转换为正则表达式
    pattern = pattern.replace('.', r'\.').replace('*', '.*').replace('?', '.')
    pattern = f".*{pattern}.*"  # 允许部分匹配
    regex = re.compile(pattern, re.IGNORECASE)
    
    # 遍历所有文件
    for root, _, files in os.walk(root_dir):
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, root_dir)
            # 忽略 .git 目录和其他隐藏文件
            if not any(part.startswith('.') for part in rel_path.split(os.sep)):
                if regex.match(rel_path):
                    matches.append(rel_path)
    
    return sorted(matches)

def select_files(related_files: List[str], root_dir: str) -> List[str]:
    """Let the user select and supplement related files"""
    PrettyOutput.section("Related files", OutputType.INFO)
    
    # Display found files
    selected_files = list(related_files)  # Default select all
    for i, file in enumerate(related_files, 1):
        PrettyOutput.print(f"[{i}] {file}", OutputType.INFO)
    
    # Ask the user if they need to adjust the file list
    user_input = input("\nDo you need to adjust the file list? (y/n) [n]: ").strip().lower() or 'n'
    if user_input == 'y':
        # Let the user select files
        PrettyOutput.print("\nPlease enter the file numbers to include (support: 1,3-6 format, press Enter to keep the current selection):", OutputType.INFO)
        numbers = input(">>> ").strip()
        if numbers:
            selected_indices = _parse_file_selection(numbers, len(related_files))
            if selected_indices:
                selected_files = [related_files[i] for i in selected_indices]
            else:
                PrettyOutput.print("No valid files selected, keep the current selection", OutputType.WARNING)
    
    # Ask if they need to supplement files
    user_input = input("\nDo you need to supplement other files? (y/n) [n]: ").strip().lower() or 'n'
    if user_input == 'y':
        # Create file completion session
        session = PromptSession(
            completer=_get_file_completer(root_dir),
            complete_while_typing=True
        )
        
        while True:
            PrettyOutput.print("\nPlease enter the file path to supplement (support Tab completion and *? wildcard, input empty line to end):", OutputType.INFO)
            try:
                file_path = session.prompt(">>> ").strip()
            except KeyboardInterrupt:
                break
                
            if not file_path:
                break
                
            # Process wildcard matching
            if '*' in file_path or '?' in file_path:
                matches = _fuzzy_match_files(root_dir, file_path)
                if not matches:
                    PrettyOutput.print("No matching files found", OutputType.WARNING)
                    continue
                    
                # Display matching files
                PrettyOutput.print("\nFound the following matching files:", OutputType.INFO)
                for i, path in enumerate(matches, 1):
                    PrettyOutput.print(f"[{i}] {path}", OutputType.INFO)
                    
                # Let the user select
                numbers = input("\nPlease select the file numbers to add (support: 1,3-6 format, press Enter to select all): ").strip()
                if numbers:
                    indices = _parse_file_selection(numbers, len(matches))
                    if not indices:
                        continue
                    paths_to_add = [matches[i] for i in indices]
                else:
                    paths_to_add = matches
            else:
                paths_to_add = [file_path]
            
            # Add selected files
            for path in paths_to_add:
                full_path = os.path.join(root_dir, path)
                if not os.path.isfile(full_path):
                    PrettyOutput.print(f"File does not exist: {path}", OutputType.ERROR)
                    continue
                
                try:
                    selected_files.append(path)
                    PrettyOutput.print(f"File added: {path}", OutputType.SUCCESS)
                except Exception as e:
                    PrettyOutput.print(f"Failed to read file: {str(e)}", OutputType.ERROR)
    
    return selected_files