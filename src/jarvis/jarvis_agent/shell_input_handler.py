# -*- coding: utf-8 -*-
from typing import Any
from typing import Tuple

from jarvis.jarvis_agent.utils import join_prompts
from jarvis.jarvis_utils.input import user_confirm
from jarvis.jarvis_utils.output import PrettyOutput


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

            output = ToolRegistry().handle_tool_calls(
                {
                    "name": "execute_script",
                    "want": "提取命令执行结果关键信息",
                    "arguments": {"interpreter": "bash", "script_content": script},
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
