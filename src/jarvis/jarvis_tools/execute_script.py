# -*- coding: utf-8 -*-
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List

from jarvis.jarvis_utils.output import PrettyOutput

# 匹配 ANSI/终端转义序列，如 ^[[?61;4;6;7;14;21;22;23;24;28;32;42;52c（终端能力查询应答）
_ANSI_ESCAPE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


class ScriptTool:
    """Combined script execution tool

    Executes scripts with any interpreter with a unified interface.
    """

    name = "execute_script"
    description = "执行脚本并返回结果，支持任意解释器。Windows 默认使用 powershell，Unix 默认使用 bash。为了避免输出过多内容，建议使用 rg、grep、Select-String 等命令过滤和限制输出长度。\n\n示例用法（Unix/Linux）：\n• 查找日志中的错误：interpreter='bash', script_content='grep -i \"error\" /var/log/app.log'\n• 查看文件开头20行：interpreter='bash', script_content='head -n 20 large_file.txt'\n• 搜索代码中的函数定义：interpreter='bash', script_content=\"rg '^def ' src/\"\n\n示例用法（Windows）：\n• 查找文件中的错误：interpreter='powershell', script_content='Select-String -Pattern \"error\" -Path .\\app.log'\n• 查看目录列表：interpreter='powershell', script_content='Get-ChildItem | Select-Object -First 20'\n• 执行 Python 脚本：interpreter='python', script_content='print(\"hello\")'"
    parameters = {
        "type": "object",
        "properties": {
            "interpreter": {
                "type": "string",
                "description": "脚本解释器。Windows 推荐 powershell 或 python；Unix 推荐 bash 或 python3。",
            },
            "script_content": {
                "type": "string",
                "description": "要执行的脚本内容。为了避免输出过多，建议使用过滤命令：\n例如：\n• grep -i 'error' filename  # 查找包含'error'的行\n• rg 'pattern' filename     # 使用ripgrep查找模式\n• tail -n 50 filename       # 显示文件最后50行\n• head -n 20 filename       # 显示文件前20行\n• command | head -n 100     # 限制命令输出前100行",
            },
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
        "cmd": "bat",
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

    @staticmethod
    def _is_windows() -> bool:
        """检测是否为 Windows 系统（Windows 没有 script 命令）"""
        return sys.platform == "win32"

    def _get_windows_command(
        self, interpreter: str, script_path: str, extension: str
    ) -> List[str]:
        """构建 Windows 下的执行命令，PowerShell 需要 -ExecutionPolicy Bypass"""
        if interpreter in ("powershell", "pwsh"):
            return [
                interpreter,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                script_path,
            ]
        if interpreter == "cmd" and extension == "bat":
            return ["cmd", "/c", script_path]
        if interpreter in ("python", "python2", "python3"):
            return [interpreter, "-u", script_path]  # -u: 无缓冲输出
        return [interpreter, script_path]

    @staticmethod
    def _decode_windows_output(data: bytes) -> str:
        """Windows 下解码子进程输出，优先 UTF-8，回退到 cp936（中文 Windows）"""
        if not data:
            return ""
        for enc in ("utf-8", "cp936", "gbk", "latin-1"):
            try:
                return data.decode(enc, errors="replace")
            except (LookupError, ValueError):
                continue
        return data.decode("latin-1", errors="replace")

    @staticmethod
    def _strip_ansi(text: str) -> str:
        """移除 ANSI/终端转义序列（如能力查询 ^[[?61;4;6;7;...c），避免混入可读输出"""
        return _ANSI_ESCAPE.sub("", text)

    def _execute_on_windows_interactive_pty(
        self, argv: List[str], env: Dict[str, str], get_timeout: Any
    ) -> Dict[str, Any]:
        """使用 pywinpty (ConPTY) 实现：用户可交互 + 可捕获输出，类似 Unix script 命令"""
        from winpty import PtyProcess

        import threading

        captured: List[str] = []
        capture_lock = threading.Lock()
        read_done = threading.Event()
        exc_holder: List[BaseException] = []

        def reader(pty_proc: Any) -> None:
            try:
                while pty_proc.isalive():
                    try:
                        data = pty_proc.read(4096)
                        if data:
                            text = self._strip_ansi(
                                self._decode_windows_output(
                                    data if isinstance(data, bytes) else data.encode()
                                )
                            )
                            with capture_lock:
                                captured.append(text)
                            sys.stdout.write(text)
                            sys.stdout.flush()
                    except (EOFError, OSError):
                        break
            except Exception as e:
                exc_holder.append(e)
            finally:
                read_done.set()

        try:
            proc = PtyProcess.spawn(argv, cwd=os.getcwd(), env=env)
        except Exception as e:
            PrettyOutput.auto_print(f"❌ PTY 启动失败: {str(e)}")
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
            }

        reader_t = threading.Thread(target=reader, args=(proc,), daemon=True)
        reader_t.start()

        def stdin_forward() -> None:
            """使用 msvcrt.kbhit 轮询而非 readline 阻塞，确保脚本结束后能及时退出，不抢占后续 stdin"""
            try:
                import msvcrt

                while proc.isalive():
                    if msvcrt.kbhit():
                        try:
                            ch = msvcrt.getwch()
                            proc.write(ch.encode("utf-8"))
                        except (EOFError, OSError, UnicodeEncodeError):
                            break
                    else:
                        time.sleep(0.05)
            except (EOFError, OSError, ImportError):
                pass

        stdin_t = threading.Thread(target=stdin_forward, daemon=True)
        stdin_t.start()

        try:
            timeout = get_timeout()
            reader_t.join(timeout=timeout)
            if reader_t.is_alive():
                for m in ("terminate", "kill"):
                    fn = getattr(proc, m, None)
                    if callable(fn):
                        try:
                            fn()
                            break
                        except Exception:
                            pass
                try:
                    getattr(proc, "wait", lambda: None)()
                except Exception:
                    pass
                read_done.wait(timeout=2)
                return {
                    "success": False,
                    "stdout": "".join(captured),
                    "stderr": f"执行超时（超过{timeout}秒），进程已被终止。",
                }
        except Exception as e:
            for m in ("terminate", "kill"):
                fn = getattr(proc, m, None)
                if callable(fn):
                    try:
                        fn()
                        break
                    except Exception:
                        pass
            return {
                "success": False,
                "stdout": "".join(captured),
                "stderr": str(e),
            }

        exit_code = (
            getattr(proc, "exitstatus", None)
            or getattr(proc, "returncode", None)
            or 0
        )
        read_done.wait(timeout=2)
        output = "".join(captured).strip()
        if exc_holder:
            return {
                "success": False,
                "stdout": output,
                "stderr": str(exc_holder[0]),
            }
        return {
            "success": exit_code == 0,
            "stdout": output,
            "stderr": "" if exit_code == 0 else f"退出码: {exit_code}",
        }

    def _execute_on_windows(
        self,
        interpreter: str,
        script_path: str,
        extension: str,
        is_non_interactive: bool,
        get_timeout: Any,
    ) -> Dict[str, Any]:
        """Windows 平台执行脚本（使用 subprocess，无 script 命令）

        非交互模式：接管 stdin/stdout/stderr，捕获输出返回（用户无法交互）
        交互模式：继承父进程 stdio，用户可与程序交互（如 input/Read-Host），但不捕获输出
        """
        import subprocess

        cmd = self._get_windows_command(interpreter, script_path, extension)
        env = os.environ.copy()
        if interpreter in ("python", "python2", "python3"):
            env["PYTHONIOENCODING"] = "utf-8"
        try:
            if is_non_interactive:
                # Agent/自动化模式：接管 I/O，捕获输出，用户无法交互
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    stdin=subprocess.DEVNULL,
                    cwd=os.getcwd(),
                    env=env,
                )
                try:
                    stdout_bytes, stderr_bytes = proc.communicate(
                        timeout=get_timeout()
                    )
                except subprocess.TimeoutExpired:
                    try:
                        proc.terminate()
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        try:
                            proc.kill()
                            proc.wait()
                        except Exception:
                            pass
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": f"执行超时（超过{get_timeout()}秒），进程已被终止（非交互模式）。",
                    }
                stdout_str = self._strip_ansi(
                    self._decode_windows_output(stdout_bytes or b"")
                )
                stderr_str = self._strip_ansi(
                    self._decode_windows_output(stderr_bytes or b"")
                )
                output = (
                    stdout_str
                    + ("\n" + stderr_str if stderr_str else "")
                ).strip()
                return {
                    "success": proc.returncode == 0,
                    "stdout": output,
                    "stderr": stderr_str if proc.returncode != 0 else "",
                }
            else:
                # 交互模式：尝试使用 pywinpty (ConPTY)，既可用户交互又可捕获输出（类似 script）
                return self._execute_on_windows_interactive_pty(
                    argv=cmd,
                    env=env,
                    get_timeout=get_timeout,
                )
        except FileNotFoundError as e:
            PrettyOutput.auto_print(f"❌ {str(e)}")
            return {
                "success": False,
                "stdout": "",
                "stderr": f"未找到解释器 '{interpreter}'，请确保已安装并加入 PATH。",
            }
        except Exception as e:
            PrettyOutput.auto_print(f"❌ {str(e)}")
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
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

                # Display script content using rich panel before execution
                from rich.console import Console
                from rich.panel import Panel
                from rich.syntax import Syntax

                console = Console()
                syntax = Syntax(
                    script_content,
                    interpreter,
                    theme="monokai",
                    line_numbers=True,
                    word_wrap=True,
                )
                panel = Panel(
                    syntax,
                    title=f"📜 执行脚本 ({interpreter})",
                    border_style="cyan",
                )
                console.print(panel)

                import subprocess

                from jarvis.jarvis_utils.config import get_script_execution_timeout
                from jarvis.jarvis_utils.config import is_non_interactive

                if self._is_windows():
                    # Windows 没有 script 命令，使用 subprocess 直接捕获输出
                    return self._execute_on_windows(
                        interpreter=interpreter,
                        script_path=script_path,
                        extension=extension,
                        is_non_interactive=is_non_interactive(),
                        get_timeout=get_script_execution_timeout,
                    )
                else:
                    # Unix/Linux: 使用 script 命令捕获 stdout 和 stderr
                    tee_command = (
                        f"script -q -c '{interpreter} {script_path}' "
                        f"{output_file}"
                    )
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
                            PrettyOutput.auto_print(f"❌ {str(e)}")
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
                        os.system(tee_command)

                    try:
                        output = self.get_display_output(output_file)
                    except Exception as e:
                        output = f"读取输出文件失败: {str(e)}"

                    if is_non_interactive() and timed_out:
                        return {
                            "success": False,
                            "stdout": output,
                            "stderr": f"执行超时（超过{get_script_execution_timeout()}秒），进程已被终止（非交互模式）。",
                        }
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
            PrettyOutput.auto_print(f"❌ {str(e)}")
            return {"success": False, "stdout": "", "stderr": str(e)}

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
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

            # Get interpreter: Windows 默认 powershell，Unix 默认 bash
            interpreter = args.get(
                "interpreter", "powershell" if self._is_windows() else "bash"
            )

            # Execute the script with the specified interpreter
            return self._execute_script_with_interpreter(interpreter, script_content)

        except Exception as e:
            PrettyOutput.auto_print(f"❌ {str(e)}")
            return {"success": False, "stdout": "", "stderr": str(e)}
