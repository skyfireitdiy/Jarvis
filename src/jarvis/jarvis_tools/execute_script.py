# -*- coding: utf-8 -*-
import os
import re
import sys
import tempfile
import time
from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

from jarvis.jarvis_utils.output import PrettyOutput

# 匹配 ANSI/终端转义序列
# CSI: ^[[?61;4;6;7;...c（终端能力查询应答）
# OSC: ^[]0;253971765/49760;C:\...\powershell.EXE（窗口标题/进程信息等，会混入输出）
_ANSI_ESCAPE = re.compile(
    r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)?)"
)
# Windows ConPTY 有时只输出 OSC payload 而 ESC 被吞掉，导致混入：
# 格式1: 0;pid/pid;C:\path\exe.EXE
# 格式2: 0;C:\path\exe.EXE (pid/pid 部分缺失)
# 格式3: 0;pid/pid (只有进程信息，无路径)
_OSC_PAYLOAD_ORPHAN = re.compile(
    r"^\s*0;(?:\d+/\d+;?)?(?:[^\n\r]*\.(?:EXE|exe|ps1|bat|cmd|py)\s*)?\s*"
)


class ExecutionStreamPublisher(ABC):
    """脚本执行流式消息发布器抽象。"""

    @abstractmethod
    def publish(self, message: Dict[str, Any], session_id: Optional[str] = None) -> None:
        raise NotImplementedError


class NullExecutionStreamPublisher(ExecutionStreamPublisher):
    """默认空发布器，保持原有行为。"""

    def publish(self, message: Dict[str, Any], session_id: Optional[str] = None) -> None:
        del message, session_id


@dataclass(frozen=True)
class ExecutionRequest:
    interpreter: str
    script_content: str
    execution_mode: str
    session_id: Optional[str] = None
    stream_publisher: Optional[ExecutionStreamPublisher] = None


class ExecutionBackend(ABC):
    """脚本执行后端抽象。"""

    @abstractmethod
    def execute(self, tool: Any, request: ExecutionRequest) -> Dict[str, Any]:
        raise NotImplementedError


class CapturedExecutionBackend(ExecutionBackend):
    """标准结果模式后端，保持现有 stdout/stderr 返回结构。"""

    def execute(self, tool: Any, request: ExecutionRequest) -> Dict[str, Any]:
        return tool._execute_script_captured(request)


class VirtualTTYExecutionBackend(ExecutionBackend):
    """交互流/TTY 模式后端。"""

    def execute(self, tool: Any, request: ExecutionRequest) -> Dict[str, Any]:
        return tool._execute_script_interactive(request)


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

    @staticmethod
    def _is_macos() -> bool:
        """检测是否为 macOS 系统（macOS 的 script 命令语法与 Linux 不同）"""
        return sys.platform == "darwin"

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
        """Windows 下解码子进程输出。Python 脚本用 PYTHONIOENCODING=utf-8 输出 UTF-8，
        其他（如 PowerShell）可能用控制台编码（GBK）。优先尝试 UTF-8 以正确显示中文。"""
        if not data:
            return ""
        from jarvis.jarvis_utils.config import get_default_encoding

        # 优先 UTF-8：Python 脚本 stdout 在此模式下为 UTF-8
        for enc in ("utf-8", get_default_encoding(), "cp936"):
            try:
                return data.decode(enc)
            except (UnicodeDecodeError, LookupError, ValueError):
                continue
        return data.decode("latin-1", errors="replace")

    @staticmethod
    def _strip_ansi(text: str) -> str:
        """移除 ANSI/终端转义序列及 Windows ConPTY 的 OSC 残留（如 0;pid/pid;C:\\path\\exe.EXE）"""
        s = _ANSI_ESCAPE.sub("", text)
        s = _OSC_PAYLOAD_ORPHAN.sub("", s)
        return s

    def _publish_stream_message(
        self,
        publisher: Optional[ExecutionStreamPublisher],
        chunk: str,
        *,
        stream: str,
        session_id: Optional[str],
    ) -> None:
        if not publisher or not chunk:
            return
        publisher.publish(
            {
                "type": "tool_stream",
                "tool": self.name,
                "stream": stream,
                "chunk": chunk,
            },
            session_id=session_id,
        )

    def _execute_on_windows_interactive_pty(
        self,
        argv: List[str],
        env: Dict[str, str],
        get_timeout: Any,
        stream_publisher: Optional[ExecutionStreamPublisher] = None,
        session_id: Optional[str] = None,
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
                            self._publish_stream_message(
                                stream_publisher,
                                text,
                                stream="stdout",
                                session_id=session_id,
                            )
                            sys.stdout.write(text)
                            sys.stdout.flush()
                    except (EOFError, OSError):
                        break
                # 进程结束后，再尝试多次读取剩余数据（包括 OSC 残留）
                # ConPTY 可能在进程退出后仍输出 OSC 序列
                for _ in range(3):
                    try:
                        remaining_data = pty_proc.read(4096)
                        if remaining_data:
                            text = self._strip_ansi(
                                self._decode_windows_output(
                                    remaining_data
                                    if isinstance(remaining_data, bytes)
                                    else remaining_data.encode()
                                )
                            )
                            # 只输出非空内容，避免输出清理后的空行
                            if text.strip():
                                with capture_lock:
                                    captured.append(text)
                                self._publish_stream_message(
                                    stream_publisher,
                                    text,
                                    stream="stdout",
                                    session_id=session_id,
                                )
                                sys.stdout.write(text)
                                sys.stdout.flush()
                        else:
                            break
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
                    if msvcrt.kbhit():  # type: ignore[attr-defined]
                        try:
                            ch = msvcrt.getwch()  # type: ignore[attr-defined]
                            proc.write(ch)
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
            getattr(proc, "exitstatus", None) or getattr(proc, "returncode", None) or 0
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
        stream_publisher: Optional[ExecutionStreamPublisher] = None,
        session_id: Optional[str] = None,
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
                    stdout_bytes, stderr_bytes = proc.communicate(timeout=get_timeout())
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
                    stdout_str + ("\n" + stderr_str if stderr_str else "")
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
                    stream_publisher=stream_publisher,
                    session_id=session_id,
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

    def _select_backend(self, execution_mode: str) -> ExecutionBackend:
        normalized_mode = (execution_mode or "auto").strip().lower()
        if normalized_mode == "interactive":
            return VirtualTTYExecutionBackend()
        if normalized_mode == "captured":
            return CapturedExecutionBackend()

        from jarvis.jarvis_utils.config import is_non_interactive

        return CapturedExecutionBackend() if is_non_interactive() else VirtualTTYExecutionBackend()

    def _execute_script_captured(self, request: ExecutionRequest) -> Dict[str, Any]:
        return self._execute_script_with_interpreter_internal(request, force_non_interactive=True)

    def _execute_script_interactive(self, request: ExecutionRequest) -> Dict[str, Any]:
        return self._execute_script_with_interpreter_internal(request, force_non_interactive=False)

    def _execute_script_with_interpreter_internal(
        self, request: ExecutionRequest, force_non_interactive: bool
    ) -> Dict[str, Any]:
        interpreter = request.interpreter
        script_content = request.script_content
        try:
            extension = self.INTERPRETER_EXTENSIONS.get(interpreter, "script")
            script_path = os.path.join(
                tempfile.gettempdir(),
                f"jarvis_{interpreter.replace('/', '_')}_{os.getpid()}.{extension}",
            )
            output_file = os.path.join(
                tempfile.gettempdir(), f"jarvis_output_{os.getpid()}.log"
            )
            try:
                enc = "utf-8-sig" if interpreter in ("powershell", "pwsh") else "utf-8"
                with open(script_path, "w", encoding=enc, errors="ignore") as f:
                    f.write(script_content)

                from jarvis.jarvis_utils.output import PrettyOutput
                PrettyOutput.print_script_panel(
                    content=script_content,
                    title=f"📜 执行脚本 ({interpreter})",
                    lang=interpreter,
                )

                import subprocess
                from jarvis.jarvis_utils.config import get_script_execution_timeout

                if self._is_windows():
                    return self._execute_on_windows(
                        interpreter=interpreter,
                        script_path=script_path,
                        extension=extension,
                        is_non_interactive=force_non_interactive,
                        get_timeout=get_script_execution_timeout,
                        stream_publisher=request.stream_publisher,
                        session_id=request.session_id,
                    )

                if self._is_macos():
                    tee_command = f"script -q {output_file} {interpreter} {script_path}"
                else:
                    tee_command = f"script -q -c '{interpreter} {script_path}' {output_file}"

                timed_out = False
                if force_non_interactive:
                    proc = None
                    try:
                        proc = subprocess.Popen(tee_command, shell=True)  # nosec B602
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
                    if request.stream_publisher is not None:
                        self._publish_stream_message(
                            request.stream_publisher,
                            "interactive stream bridge is not yet available on Unix; falling back to legacy terminal execution\n",
                            stream="stderr",
                            session_id=request.session_id,
                        )
                    os.system(tee_command)  # nosec B605

                try:
                    output = self.get_display_output(output_file)
                except Exception as e:
                    output = f"读取输出文件失败: {str(e)}"

                if force_non_interactive and timed_out:
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
                Path(script_path).unlink(missing_ok=True)
                Path(output_file).unlink(missing_ok=True)
        except Exception as e:
            PrettyOutput.auto_print(f"❌ {str(e)}")
            return {"success": False, "stdout": "", "stderr": str(e)}

    def _execute_script_with_interpreter(
        self,
        interpreter: str,
        script_content: str,
        execution_mode: str = "auto",
        session_id: Optional[str] = None,
        stream_publisher: Optional[ExecutionStreamPublisher] = None,
    ) -> Dict[str, Any]:
        request = ExecutionRequest(
            interpreter=interpreter,
            script_content=script_content,
            execution_mode=execution_mode,
            session_id=session_id,
            stream_publisher=stream_publisher,
        )
        backend = self._select_backend(execution_mode)
        return backend.execute(self, request)

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
            execution_mode = str(args.get("execution_mode", "auto"))
            session_id = args.get("session_id")
            stream_publisher = args.get("stream_publisher")
            if stream_publisher is not None and not isinstance(
                stream_publisher, ExecutionStreamPublisher
            ):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "stream_publisher must implement ExecutionStreamPublisher",
                }

            # Execute the script with the specified interpreter
            return self._execute_script_with_interpreter(
                interpreter,
                script_content,
                execution_mode=execution_mode,
                session_id=session_id if isinstance(session_id, str) else None,
                stream_publisher=stream_publisher,
            )

        except Exception as e:
            PrettyOutput.auto_print(f"❌ {str(e)}")
            return {"success": False, "stdout": "", "stderr": str(e)}
