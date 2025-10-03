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
    file_paths = re.findall(r"'([^']+)'", user_input)

    if not file_paths:
        return user_input, False

    added_context = ""
    read_code_tool = ReadCodeTool()

    for path in file_paths:
        if os.path.isfile(path) and is_text_file(path):
            line_count = count_lines(path)
            if line_count > 0:
                # Use ReadCodeTool to get formatted content
                result = read_code_tool._handle_single_file(path)
                if result["success"]:
                    # Remove the file path from the original input to avoid redundancy
                    user_input = user_input.replace(f"'{path}'", "")
                    # Append the full, formatted output from the tool, which includes headers and line numbers
                    added_context += "\n" + result["stdout"]

    if added_context:
        user_input = user_input.strip() + added_context

    return user_input, False
