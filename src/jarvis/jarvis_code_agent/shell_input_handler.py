

from typing import Any, Tuple

from jarvis.jarvis_tools.execute_shell_script import ShellScriptTool
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
            ShellScriptTool().execute({"script_content": script})
            return "", True
        return user_input, False
    
