from typing import Dict, Any
import os
import tempfile
from pathlib import Path

from jarvis.jarvis_utils.output import OutputType, PrettyOutput


class ScriptTool:
    """Combined script execution tool
    
    Executes scripts with any interpreter with a unified interface.
    """
    name = "execute_script"
    description = "执行脚本并返回结果，支持任意解释器。注意：由于模型上下文长度限制，请避免在脚本中输出大量信息，应该使用rg过滤输出"
    labels = ['system', 'shell', 'python', 'execution', 'script']
    parameters = {
        "type": "object",
        "properties": {
            "interpreter": {
                "type": "string",
                "description": "脚本解释器: 如bash, python3, expect, perl, ruby等任意解释器。如需直接执行shell命令, 可使用bash作为解释器"
            },
            "script_type": {
                "type": "string",
                "enum": ["shell_command", "shell_script", "python_script"],
                "description": "已废弃，请使用interpreter参数。脚本类型: shell_command (Shell命令), shell_script (Shell脚本), python_script (Python脚本)"
            },
            "script_content": {
                "type": "string",
                "description": "要执行的脚本内容"
            }
        },
        "required": ["script_content"]
    }

    # Map of common file extensions for interpreters (can be extended as needed)
    INTERPRETER_EXTENSIONS = {
        "bash": "sh",
        "sh": "sh",
        "python": "py",
        "python2": "py",
        "python3": "py",
        "perl": "pl",
        "ruby": "rb",
        "node": "js",
        "nodejs": "js",
        "php": "php",
        "powershell": "ps1",
        "pwsh": "ps1",
        "R": "r",
        "Rscript": "r",
        "julia": "jl",
        "lua": "lua",
        "go": "go",
        "awk": "awk",
        "kotlin": "kt",
        "java": "java",
        "javac": "java",
        "scala": "scala",
        "swift": "swift",
        "gcc": "c",
        "g++": "cpp",
    }

    def _execute_script_with_interpreter(self, interpreter: str, script_content: str) -> Dict[str, Any]:
        """Execute a script with the specified interpreter
        
        Args:
            interpreter: The interpreter to use (any valid interpreter command)
            script_content: Content of the script
            
        Returns:
            Dictionary with execution results
        """
        try:
            # Get file extension for the interpreter
            extension = self.INTERPRETER_EXTENSIONS.get(interpreter, "script")
            
            # Create temporary script file
            script_path = os.path.join(tempfile.gettempdir(), f"jarvis_{interpreter.replace('/', '_')}_{os.getpid()}.{extension}")
            output_file = os.path.join(tempfile.gettempdir(), f"jarvis_output_{os.getpid()}.log")
            try:
                with open(script_path, 'w', encoding='utf-8', errors="ignore") as f:
                    f.write(script_content)
                
                # Use script command to capture both stdout and stderr
                tee_command = f"script -q -c '{interpreter} {script_path}' {output_file}"
                
                # Execute command and capture return code
                os.system(tee_command)
                
                # Read and process output file
                try:
                    with open(output_file, 'r', encoding='utf-8', errors='ignore') as f:
                        output = f.read()
                        # Remove header and footer added by script command (if any)
                        if output:
                            lines = output.splitlines()
                            if len(lines) > 2:
                                output = "\n".join(lines[1:-1])
                except Exception as e:
                    output = f"读取输出文件失败: {str(e)}"
                    
                # Return successful result
                return {
                    "success": True,
                    "stdout": output,
                    "stderr": "",
                }
                
            finally:
                # Clean up temporary files
                Path(script_path).unlink(missing_ok=True)
                Path(output_file).unlink(missing_ok=True)

        except Exception as e:
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e)
            }

    def execute(self, args: Dict) -> Dict[str, Any]:
        """Execute script based on interpreter and content
        
        Args:
            args: Dictionary containing interpreter (or script_type) and script_content
            
        Returns:
            Dictionary with execution results
        """
        try:
            script_content = args.get("script_content", "").strip()
            if not script_content:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "Missing or empty script_content parameter"
                }
            
            # Get interpreter, with fallback to script_type for backward compatibility
            interpreter = args.get("interpreter")
            script_type = args.get("script_type")
            
            # Handle backward compatibility
            if interpreter is None and script_type is not None:
                if script_type == "shell_command":
                    # For direct shell commands, use bash -c
                    return self._execute_script_with_interpreter("bash -c", script_content)
                elif script_type == "shell_script":
                    interpreter = "bash"
                elif script_type == "python_script":
                    interpreter = "python"
            
            # Default to bash if nothing specified
            if interpreter is None:
                interpreter = "bash"
                
            # Execute the script with the specified interpreter
            return self._execute_script_with_interpreter(interpreter, script_content)
                
        except Exception as e:
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e)
            } 