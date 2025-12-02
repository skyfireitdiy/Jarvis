# -*- coding: utf-8 -*-
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List


class ScriptTool:
    """Combined script execution tool

    Executes scripts with any interpreter with a unified interface.
    """

    name = "execute_script"
    description = "执行脚本并返回结果，支持任意解释器。建议使用rg过滤大量输出。"
    parameters = {
        "type": "object",
        "properties": {
            "interpreter": {
                "type": "string",
                "description": "脚本解释器（如bash、python3、perl等）。执行shell命令可使用bash。",
            },
            "script_content": {"type": "string", "description": "要执行的脚本内容"},
        },
        "required": ["script_content"],
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

    def get_display_output(self, file_path: str) -> str:
        """消除控制字符，得到用户实际看到的文本，去除script命令首尾行"""
        # 读取文件内容并尝试多种编码
        with open(file_path, "rb") as f:
            data = f.read()

        import pyte

        screen = pyte.Screen(300, 100000)
        stream = pyte.ByteStream(screen)
        stream.feed(data)

        # 清理每行右侧空格，并过滤空行
        cleaned: List[str] = []
        for y in range(screen.lines):
            line = screen.buffer[y]
            stripped = "".join(char.data for char in line.values()).rstrip()
            if stripped:
                cleaned.append(stripped)
        return "\n".join(cleaned[1:-1])

    def _execute_script_with_interpreter(
        self, interpreter: str, script_content: str
    ) -> Dict[str, Any]:
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
            script_path = os.path.join(
                tempfile.gettempdir(),
                f"jarvis_{interpreter.replace('/', '_')}_{os.getpid()}.{extension}",
            )
            output_file = os.path.join(
                tempfile.gettempdir(), f"jarvis_output_{os.getpid()}.log"
            )
            try:
                with open(script_path, "w", encoding="utf-8", errors="ignore") as f:
                    f.write(script_content)

                # Use script command to capture both stdout and stderr
                tee_command = (
                    f"script -q -c '{interpreter} {script_path}' {output_file}"
                )

                # Execute command with optional timeout in non-interactive mode
                from jarvis.jarvis_utils.config import (
                    get_script_execution_timeout,
                    is_non_interactive,
                )
                import subprocess

                timed_out = False
                if is_non_interactive():
                    proc = None
                    try:
                        proc = subprocess.Popen(tee_command, shell=True)
                        try:
                            proc.wait(timeout=get_script_execution_timeout())
                        except subprocess.TimeoutExpired:
                            timed_out = True
                            try:
                                proc.terminate()
                                proc.wait(timeout=2)
                            except subprocess.TimeoutExpired:
                                try:
                                    proc.kill()
                                    proc.wait()
                                except Exception:
                                    pass
                            except Exception:
                                try:
                                    proc.kill()
                                    proc.wait()
                                except Exception:
                                    pass
                    except Exception as e:
                        # 确保进程被关闭
                        if proc is not None:
                            try:
                                proc.terminate()
                                proc.wait(timeout=1)
                            except Exception:
                                try:
                                    proc.kill()
                                    proc.wait()
                                except Exception:
                                    pass
                        print(f"❌ {str(e)}")
                        # Attempt to read any partial output if available
                        try:
                            output = self.get_display_output(output_file)
                        except Exception as ee:
                            output = f"读取输出文件失败: {str(ee)}"
                        return {
                            "success": False,
                            "stdout": output,
                            "stderr": f"执行脚本失败: {str(e)}",
                        }
                    finally:
                        # 确保进程和文件描述符被关闭
                        if proc is not None:
                            try:
                                if proc.stdin:
                                    proc.stdin.close()
                                if proc.stdout:
                                    proc.stdout.close()
                                if proc.stderr:
                                    proc.stderr.close()
                            except Exception:
                                pass
                else:
                    # Execute command and capture return code
                    os.system(tee_command)

                # Read and process output file
                try:
                    # 消除控制字符，得到用户实际看到的文本
                    output = self.get_display_output(output_file)
                except Exception as e:
                    output = f"读取输出文件失败: {str(e)}"

                # Return result (handle timeout in non-interactive mode)
                if is_non_interactive() and timed_out:
                    return {
                        "success": False,
                        "stdout": output,
                        "stderr": f"执行超时（超过{get_script_execution_timeout()}秒），进程已被终止（非交互模式）。",
                    }
                else:
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
            print(f"❌ {str(e)}")
            return {"success": False, "stdout": "", "stderr": str(e)}

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
                    "stderr": "Missing or empty script_content parameter",
                }

            # Get interpreter, default to bash if not specified
            interpreter = args.get("interpreter", "bash")

            # Execute the script with the specified interpreter
            return self._execute_script_with_interpreter(interpreter, script_content)

        except Exception as e:
            print(f"❌ {str(e)}")
            return {"success": False, "stdout": "", "stderr": str(e)}
