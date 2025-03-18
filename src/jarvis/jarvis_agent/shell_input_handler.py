

from typing import Any, Tuple

from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import user_confirm


def shell_input_handler(user_input: str, agent: Any) -> Tuple[str, bool]:
    lines = user_input.splitlines()
    cmdline = [line for line in lines if line.startswith("!")]
    if len(cmdline) == 0:
        return user_input, False
    else:
        script = '\n'.join([c[1:] for c in cmdline])
        PrettyOutput.print(script, OutputType.CODE, lang="bash")
        if user_confirm(f"是否要执行以上shell脚本？", default=True):
            output = ToolRegistry().handle_tool_calls({
                "name": "execute_shell_script",
                "arguments": {
                    "script_content": script
                }
            })
            return f"{user_input}\n\n用户执行以下脚本：\n{script}\n\n执行结果：\n{output}", False
        return user_input, False
    
