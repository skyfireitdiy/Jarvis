# -*- coding: utf-8 -*-
"""FZF选择器工具。"""

import shutil
import subprocess
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Union
from typing import cast


def fzf_select(
    options: Union[List[str], List[Dict[str, Any]]],
    prompt: str = "SELECT> ",
    key: Optional[str] = None,
) -> Optional[str]:
    """
    使用fzf从列表中选择一个项目。

    参数:
        options: 可供选择的字符串或字典列表。
        prompt: 在fzf中显示的提示信息。
        key: 如果options是字典列表，则此参数指定要显示的键名。

    返回:
        选中的项目，如果fzf不可用或选择被取消则返回None。
    """
    if shutil.which("fzf") is None:
        return None

    if not options:
        return None

    if isinstance(options[0], dict):
        if key is None:
            raise ValueError("A key must be provided for a list of dicts.")
        input_lines = [str(cast(Dict[str, Any], item).get(key, "")) for item in options]
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
