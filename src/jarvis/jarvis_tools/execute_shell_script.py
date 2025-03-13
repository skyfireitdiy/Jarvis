from typing import Dict, Any
import os
import tempfile
from pathlib import Path

from jarvis.jarvis_utils.output import OutputType, PrettyOutput


class ShellScriptTool:
    name = "execute_shell_script"
    description = "执行Shell脚本文件并返回结果"
    parameters = {
        "type": "object",
        "properties": {
            "script_content": {
                "type": "string",
                "description": "要执行的Shell脚本内容"
            }
        },
        "required": ["script_content"]
    }
    def execute(self, args: Dict) -> Dict[str, Any]:
        """Execute shell script content"""
        try:
            script_content = args.get("script_content", "").strip()
            if not script_content:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "Missing or empty script_content parameter"
                }
            
            # Create temporary script file
            script_path = os.path.join(tempfile.gettempdir(), f"jarvis_script_{os.getpid()}.sh")
            try:
                with open(script_path, 'w', encoding='utf-8') as f:
                    f.write(script_content)
                # Use execute_shell to run the script
                from jarvis.jarvis_tools.execute_shell import ShellTool
                shell_tool = ShellTool()
                result = shell_tool.execute({"command": f"bash {script_path}"})
                
                return {
                    "success": result["success"],
                    "stdout": result["stdout"],
                    "stderr": result["stderr"]
                }
            finally:
                # Clean up temporary script file
                Path(script_path).unlink(missing_ok=True)
                
        except Exception as e:
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e)
            }