# -*- coding: utf-8 -*-
import os
from typing import Any
from typing import Tuple

from jarvis.jarvis_agent.utils import join_prompts
from jarvis.jarvis_utils.input import user_confirm
from jarvis.jarvis_utils.output import PrettyOutput


def _detect_interpreter(script: str) -> str:
    """根据脚本内容自动检测合适的解释器。

    Args:
        script: 要执行的脚本内容

    Returns:
        解释器名称：'bash'、'powershell'、'cmd'、'pwsh' 等

    检测规则:
        1. Windows 上优先检测 powershell/pwsh/cmd 命令
        2. Unix/Linux 上使用 bash 作为默认
        3. 如果无法识别，默认使用 bash
    """
    # 获取脚本的第一行（去除空白字符）
    lines = script.strip().splitlines()
    if not lines:
        return "bash"

    first_line = lines[0].strip()

    # Windows 检测：powershell/pwsh/cmd
    if os.name == "nt":
        # 检测 PowerShell 命令
        if first_line.startswith("powershell ") or first_line.startswith("pwsh "):
            return "powershell"
        # 检测 cmd 命令
        if first_line.startswith("cmd "):
            return "cmd"
    else:
        # Unix/Linux 检测
        # 处理 env terminal=1 bash 这样的命令
        if first_line.startswith("env "):
            # 提取实际的 shell 名称
            parts = first_line.split()
            for part in parts:
                if part in ("bash", "zsh", "fish", "sh"):
                    return "bash"

    # 默认使用 bash
    return "bash"


def shell_input_handler(user_input: str, agent: Any) -> Tuple[str, bool]:
    lines = user_input.splitlines()
    cmdline = [line for line in lines if line.startswith("!")]
    if len(cmdline) == 0:
        return user_input, False
    else:
        marker = "# JARVIS-NOCONFIRM"

        def _clean(line: str) -> str:
            s = line[1:]  # remove leading '!'
            # strip no-confirm marker if present
            idx = s.find(marker)
            if idx != -1:
                s = s[:idx]
            return s.rstrip()

        # Build script while stripping the no-confirm marker from each line
        script = "\n".join([_clean(c) for c in cmdline])
        PrettyOutput.auto_print(script)

        # If any line contains the no-confirm marker, skip the pre-execution confirmation
        no_confirm = any(marker in c for c in cmdline)

        if no_confirm or user_confirm("是否要执行以上shell脚本？", default=True):
            from jarvis.jarvis_tools.registry import ToolRegistry

            # 根据脚本内容自动检测合适的解释器
            interpreter = _detect_interpreter(script)

            output = ToolRegistry().handle_tool_calls(
                {
                    "name": "execute_script",
                    "want": "提取命令执行结果关键信息",
                    "arguments": {"interpreter": interpreter, "script_content": script},
                },
                agent,
            )
            if user_confirm("是否将执行结果反馈给Agent？", default=True):
                # 只过滤掉带有 JARVIS-NOCONFIRM 标记的命令（Ctrl+T 自动生成的）
                # 保留用户手动输入的普通 shell 命令，让 Agent 能了解完整上下文
                marker = "# JARVIS-NOCONFIRM"
                filtered_input = "\n".join(
                    [
                        line
                        for line in user_input.splitlines()
                        if not (line.startswith("!") and marker in line)
                    ]
                )
                return (
                    join_prompts(
                        [
                            filtered_input,
                            f"用户执行以下脚本：\n{script}",
                            f"执行结果：\n{output}",
                        ]
                    ),
                    False,
                )
            return "", True
        return user_input, False
