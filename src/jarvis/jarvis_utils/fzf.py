# -*- coding: utf-8 -*-
"""FZF selector utility."""
import shutil
import subprocess
from typing import List, Optional, Union

def fzf_select(
    options: Union[List[str], List[dict]],
    prompt: str = "SELECT> ",
    key: Optional[str] = None,
) -> Optional[str]:
    """
    Uses fzf to select an item from a list.

    Args:
        options: A list of strings or dicts to choose from.
        prompt: The prompt to display in fzf.
        key: If options is a list of dicts, this is the key to display.

    Returns:
        The selected item, or None if fzf is not available or the selection is cancelled.
    """
    if shutil.which("fzf") is None:
        return None

    if not options:
        return None

    if isinstance(options[0], dict):
        if key is None:
            raise ValueError("A key must be provided for a list of dicts.")
        input_lines = [str(item.get(key, "")) for item in options]
    else:
        input_lines = [str(item) for item in options]

    try:
        process = subprocess.run(
            [
                "fzf",
                "--prompt",
                prompt,
                "--height",
                "40%",
                "--border",
                "--layout=reverse",
            ],
            input="\n".join(input_lines),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        selected = process.stdout.strip()
        return selected if selected else None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
