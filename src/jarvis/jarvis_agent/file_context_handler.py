# -*- coding: utf-8 -*-
import re
import os
from typing import Any, Tuple

from jarvis.jarvis_tools.read_code import ReadCodeTool


def is_text_file(filepath: str) -> bool:
    """
    Check if a file is a text file.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            f.read(1024)  # Try to read a small chunk
        return True
    except (UnicodeDecodeError, IOError):
        return False


def count_lines(filepath: str) -> int:
    """
    Count the number of lines in a file.
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except IOError:
        return 0


def file_context_handler(user_input: str, agent_: Any) -> Tuple[str, bool]:
    """
    Extracts file paths from the input, reads their content if they are valid text files
    and appends the content to the input.

    Args:
        user_input: The user's input string.
        agent_: The agent instance.

    Returns:
        A tuple containing the modified user input and a boolean indicating if
        further processing should be skipped.
    """
    # Regex to find paths in single quotes
    raw_paths = re.findall(r"'([^']+)'", user_input)
    # Convert to absolute paths and de-duplicate by absolute path while preserving order
    abs_to_raws: dict[str, list[str]] = {}
    file_paths = []
    for _raw in raw_paths:
        abs_path = os.path.abspath(_raw)
        if abs_path not in abs_to_raws:
            abs_to_raws[abs_path] = []
            file_paths.append(abs_path)
        abs_to_raws[abs_path].append(_raw)

    if not file_paths:
        return user_input, False

    added_context = ""
    read_code_tool = ReadCodeTool()

    for abs_path in file_paths:
        if os.path.isfile(abs_path) and is_text_file(abs_path):
            line_count = count_lines(abs_path)
            if line_count > 0:
                # Use ReadCodeTool to get formatted content
                result = read_code_tool._handle_single_file(abs_path)
                if result["success"]:
                    # Remove all original path tokens that map to this absolute path to avoid redundancy
                    for _raw in abs_to_raws.get(abs_path, []):
                        user_input = user_input.replace(f"'{_raw}'", "")
                    # Append the full, formatted output from the tool, which includes headers and line numbers
                    added_context += "\n" + result["stdout"]

    if added_context:
        user_input = user_input.strip() + added_context

    return user_input, False
