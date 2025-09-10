# -*- coding: utf-8 -*-
import os
import sys
import time
from typing import Any, Dict, TYPE_CHECKING
from jarvis.jarvis_utils.output import OutputType, PrettyOutput

# 为了类型检查，总是导入这些模块
if TYPE_CHECKING:
    pass

# 平台相关的导入
if sys.platform != "win32":
    pass
else:
    # Windows平台的导入
    pass


class VirtualTTYTool:
    name = "virtual_tty"
    description = (
        "控制虚拟终端执行各种操作，如启动终端、输入命令、获取输出等。"
        + "与execute_script不同，此工具会创建一个持久的虚拟终端会话，可以连续执行多个命令，并保持终端状态。"
        + "适用于需要交互式操作的场景，如运行需要用户输入的交互式程序（如：ssh连接、sftp传输、gdb/dlv调试等）。"
        + "注意：Windows平台功能有限，某些Unix特有功能可能不可用。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "要执行的终端操作类型",
                "enum": [
                    "launch",
                    "send_keys",
                    "output",
                    "close",
                    "get_screen",
                    "list",
                ],
            },
            "keys": {
                "type": "string",
                "description": "要发送的按键序列（仅支持单行输入，当action为send_keys时有效）",
            },
            "add_enter": {
                "type": "boolean",
                "description": "是否在单行命令末尾自动添加回车符（仅当action为send_keys时有效，默认为true）",
            },
            "timeout": {
                "type": "number",
                "description": "等待输出的超时时间（秒，仅当action为send_keys或output时有效，默认为5.0）",
            },
            "tty_id": {
                "type": "string",
                "description": "虚拟终端的唯一标识符（默认为'default'）",
            },
        },
        "required": ["action"],
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行终端操作

        参数:
            args: 包含操作参数的字典，包括agent属性

        返回:
            字典，包含以下内容：
                - success: 布尔值，表示操作状态
                - stdout: 成功消息或操作结果
                - stderr: 错误消息或空字符串
        """
        # 获取agent对象
        agent = args.get("agent")
        if agent is None:
            return {"success": False, "stdout": "", "stderr": "未提供agent对象"}

        # 获取TTY ID，默认为"default"
        tty_id = args.get("tty_id", "default")

        # 确保agent有tty_sessions字典
        if not hasattr(agent, "tty_sessions"):
            agent.tty_sessions = {}

        # 如果指定的tty_id不存在，为其创建一个新的tty_data
        if tty_id not in agent.tty_sessions:
            if sys.platform == "win32":
                import queue as _queue  # pylint: disable=import-outside-toplevel

                agent.tty_sessions[tty_id] = {
                    "process": None,
                    "output_queue": _queue.Queue(),
                    "output_thread": None,
                    "shell": "cmd.exe",
                }
            else:
                agent.tty_sessions[tty_id] = {
                    "master_fd": None,
                    "pid": None,
                    "shell": "/bin/bash",
                }

        action = args.get("action", "").strip().lower()

        # 验证操作类型
        valid_actions = ["launch", "send_keys", "output", "close", "get_screen", "list"]
        if action not in valid_actions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"不支持的操作: {action}。有效操作: {', '.join(valid_actions)}",
            }

        try:
            if action == "launch":
                if args.get("keys", "") != "":
                    PrettyOutput.print(
                        "启动虚拟终端时，不能同时指定 keys 参数", OutputType.ERROR
                    )
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "启动虚拟终端时，不能同时指定keys参数",
                    }

                result = self._launch_tty(agent, tty_id)
                if not result["success"]:
                    PrettyOutput.print(
                        f"启动虚拟终端 [{tty_id}] 失败", OutputType.ERROR
                    )
                return result
            elif action == "send_keys":
                keys = args.get("keys", "").strip()
                add_enter = args.get("add_enter", True)
                timeout = args.get("timeout", 5.0)  # 默认5秒超时

                result = self._input_command(agent, tty_id, keys, timeout, add_enter)
                if not result["success"]:
                    PrettyOutput.print(
                        f"发送按键序列到终端 [{tty_id}] 失败", OutputType.ERROR
                    )
                return result
            elif action == "output":
                timeout = args.get("timeout", 5.0)  # 默认5秒超时

                result = self._get_output(agent, tty_id, timeout)
                if not result["success"]:
                    PrettyOutput.print(
                        f"获取终端 [{tty_id}] 输出失败", OutputType.ERROR
                    )
                return result
            elif action == "close":

                result = self._close_tty(agent, tty_id)
                if not result["success"]:
                    PrettyOutput.print(
                        f"关闭虚拟终端 [{tty_id}] 失败", OutputType.ERROR
                    )
                return result
            elif action == "get_screen":

                result = self._get_screen(agent, tty_id)
                if not result["success"]:
                    PrettyOutput.print(
                        f"获取终端 [{tty_id}] 屏幕内容失败", OutputType.ERROR
                    )
                return result
            elif action == "list":

                result = self._list_ttys(agent)
                if not result["success"]:
                    PrettyOutput.print("获取虚拟终端列表失败", OutputType.ERROR)
                return result
            return {"success": False, "stdout": "", "stderr": "不支持的操作"}

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"执行终端操作出错: {str(e)}",
            }

    def _launch_tty(self, agent: Any, tty_id: str) -> Dict[str, Any]:
        """启动虚拟终端"""
        if sys.platform == "win32":
            return self._launch_tty_windows(agent, tty_id)
        else:
            return self._launch_tty_unix(agent, tty_id)

    def _launch_tty_unix(self, agent: Any, tty_id: str) -> Dict[str, Any]:
        """Unix/Linux平台启动虚拟终端"""
        try:
            # 如果该ID的终端已经启动，先关闭它
            if agent.tty_sessions[tty_id]["master_fd"] is not None:
                self._close_tty(agent, tty_id)

            # 在Unix平台上导入需要的模块
            import pty as _pty  # pylint: disable=import-outside-toplevel
            import fcntl as _fcntl  # pylint: disable=import-outside-toplevel
            import select as _select  # pylint: disable=import-outside-toplevel

            # 创建伪终端
            pid, master_fd = _pty.fork()

            if pid == 0:  # 子进程
                # 执行shell
                os.execvp(
                    agent.tty_sessions[tty_id]["shell"],
                    [agent.tty_sessions[tty_id]["shell"]],
                )
            else:  # 父进程
                # 设置非阻塞模式
                _fcntl.fcntl(master_fd, _fcntl.F_SETFL, os.O_NONBLOCK)

                # 保存终端状态
                agent.tty_sessions[tty_id]["master_fd"] = master_fd
                agent.tty_sessions[tty_id]["pid"] = pid

                # 读取初始输出
                output = ""
                start_time = time.time()
                while time.time() - start_time < 2.0:  # 最多等待2秒
                    try:
                        r, _, _ = _select.select([master_fd], [], [], 0.1)
                        if r:
                            data = os.read(master_fd, 1024)
                            if data:
                                output += data.decode()
                    except BlockingIOError:
                        continue

                return {"success": True, "stdout": output, "stderr": ""}

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"启动虚拟终端 [{tty_id}] 失败: {str(e)}",
            }

    def _launch_tty_windows(self, agent: Any, tty_id: str) -> Dict[str, Any]:
        """Windows平台启动虚拟终端"""
        try:
            # 如果该ID的终端已经启动，先关闭它
            if agent.tty_sessions[tty_id]["process"] is not None:
                self._close_tty(agent, tty_id)

            # 在Windows平台上导入需要的模块
            import subprocess as _subprocess  # pylint: disable=import-outside-toplevel
            import threading as _threading  # pylint: disable=import-outside-toplevel
            import queue as _queue  # pylint: disable=import-outside-toplevel

            # 创建子进程
            process = _subprocess.Popen(
                agent.tty_sessions[tty_id]["shell"],
                stdin=_subprocess.PIPE,
                stdout=_subprocess.PIPE,
                stderr=_subprocess.STDOUT,
                shell=True,
                text=True,
                bufsize=0,
                encoding="utf-8",
                errors="replace",
            )

            # 保存进程对象
            agent.tty_sessions[tty_id]["process"] = process

            # 创建输出读取线程
            def read_output():
                while True:
                    if process is None or process.poll() is not None:
                        break
                    try:
                        if process.stdout is None:
                            break
                        line = process.stdout.readline()
                        if line:
                            agent.tty_sessions[tty_id]["output_queue"].put(line)
                    except:
                        break

            output_thread = _threading.Thread(target=read_output, daemon=True)
            output_thread.start()
            agent.tty_sessions[tty_id]["output_thread"] = output_thread

            # 读取初始输出
            output = ""
            start_time = time.time()
            while time.time() - start_time < 2.0:  # 最多等待2秒
                try:
                    line = agent.tty_sessions[tty_id]["output_queue"].get(timeout=0.1)
                    output += line
                except _queue.Empty:
                    continue

            return {"success": True, "stdout": output, "stderr": ""}

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"启动虚拟终端 [{tty_id}] 失败: {str(e)}",
            }

    def _input_command(
        self,
        agent: Any,
        tty_id: str,
        command: str,
        timeout: float,
        add_enter: bool = True,
    ) -> Dict[str, Any]:
        """输入单行命令并等待输出

        参数:
            command: 要输入的单行命令
            add_enter: 是否在命令末尾添加回车符
        """
        if sys.platform == "win32":
            return self._input_command_windows(
                agent, tty_id, command, timeout, add_enter
            )
        else:
            return self._input_command_unix(agent, tty_id, command, timeout, add_enter)

    def _input_command_unix(
        self,
        agent: Any,
        tty_id: str,
        command: str,
        timeout: float,
        add_enter: bool = True,
    ) -> Dict[str, Any]:
        """Unix/Linux平台输入命令"""
        if agent.tty_sessions[tty_id]["master_fd"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"虚拟终端 [{tty_id}] 未启动",
            }

        # 严格检查并拒绝多行输入
        if "\n" in command:
            return {"success": False, "stdout": "", "stderr": "错误：禁止多行输入"}

        try:
            # 根据add_enter参数决定是否添加回车符
            if add_enter:
                command = command + "\n"

            # 发送按键序列
            os.write(agent.tty_sessions[tty_id]["master_fd"], command.encode())

            # 等待输出
            output = ""
            start_time = time.time()

            while time.time() - start_time < timeout:
                try:
                    # 使用select等待数据可读
                    import select as _select  # pylint: disable=import-outside-toplevel

                    r, _, _ = _select.select(
                        [agent.tty_sessions[tty_id]["master_fd"]], [], [], 0.1
                    )
                    if r:
                        data = os.read(agent.tty_sessions[tty_id]["master_fd"], 1024)
                        if data:
                            output += data.decode()
                except BlockingIOError:
                    continue
            return {"success": True, "stdout": output, "stderr": ""}

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"在终端 [{tty_id}] 执行命令失败: {str(e)}",
            }

    def _input_command_windows(
        self,
        agent: Any,
        tty_id: str,
        command: str,
        timeout: float,
        add_enter: bool = True,
    ) -> Dict[str, Any]:
        """Windows平台输入命令"""
        if agent.tty_sessions[tty_id]["process"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"虚拟终端 [{tty_id}] 未启动",
            }

        # 严格检查并拒绝多行输入
        if "\n" in command:
            return {"success": False, "stdout": "", "stderr": "错误：禁止多行输入"}

        try:
            # 根据add_enter参数决定是否添加回车符
            if add_enter:
                command = command + "\n"

            # 发送命令
            agent.tty_sessions[tty_id]["process"].stdin.write(command)
            agent.tty_sessions[tty_id]["process"].stdin.flush()

            # 等待输出
            output = ""
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    line = agent.tty_sessions[tty_id]["output_queue"].get(timeout=0.1)
                    output += line
                except Exception:  # queue.Empty
                    continue

            return {"success": True, "stdout": output, "stderr": ""}

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"在终端 [{tty_id}] 执行命令失败: {str(e)}",
            }

    def _get_output(
        self, agent: Any, tty_id: str, timeout: float = 5.0
    ) -> Dict[str, Any]:
        """获取终端输出"""
        if sys.platform == "win32":
            return self._get_output_windows(agent, tty_id, timeout)
        else:
            return self._get_output_unix(agent, tty_id, timeout)

    def _get_output_unix(
        self, agent: Any, tty_id: str, timeout: float = 5.0
    ) -> Dict[str, Any]:
        """Unix/Linux平台获取输出"""
        if agent.tty_sessions[tty_id]["master_fd"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"虚拟终端 [{tty_id}] 未启动",
            }

        try:
            output = ""
            start_time = time.time()

            while time.time() - start_time < timeout:
                # 使用select等待数据可读
                import select as _select  # pylint: disable=import-outside-toplevel

                r, _, _ = _select.select(
                    [agent.tty_sessions[tty_id]["master_fd"]], [], [], 0.1
                )
                if r:
                    while True:
                        try:
                            data = os.read(
                                agent.tty_sessions[tty_id]["master_fd"], 1024
                            )
                            if data:
                                output += data.decode()
                            else:
                                break
                        except BlockingIOError:
                            break
            return {"success": True, "stdout": output, "stderr": ""}

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"获取终端 [{tty_id}] 输出失败: {str(e)}",
            }

    def _get_output_windows(
        self, agent: Any, tty_id: str, timeout: float = 5.0
    ) -> Dict[str, Any]:
        """Windows平台获取输出"""
        if agent.tty_sessions[tty_id]["process"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"虚拟终端 [{tty_id}] 未启动",
            }

        try:
            output = ""
            start_time = time.time()

            while time.time() - start_time < timeout:
                try:
                    line = agent.tty_sessions[tty_id]["output_queue"].get(timeout=0.1)
                    output += line
                except Exception:  # queue.Empty
                    continue

            return {"success": True, "stdout": output, "stderr": ""}

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"获取终端 [{tty_id}] 输出失败: {str(e)}",
            }

    def _close_tty(self, agent: Any, tty_id: str) -> Dict[str, Any]:
        """关闭虚拟终端"""
        if sys.platform == "win32":
            return self._close_tty_windows(agent, tty_id)
        else:
            return self._close_tty_unix(agent, tty_id)

    def _close_tty_unix(self, agent: Any, tty_id: str) -> Dict[str, Any]:
        """Unix/Linux平台关闭终端"""
        if agent.tty_sessions[tty_id]["master_fd"] is None:
            return {
                "success": True,
                "stdout": f"没有正在运行的虚拟终端 [{tty_id}]",
                "stderr": "",
            }

        try:
            # 关闭主文件描述符
            os.close(agent.tty_sessions[tty_id]["master_fd"])

            # 终止子进程
            if agent.tty_sessions[tty_id]["pid"]:
                import signal as _signal  # pylint: disable=import-outside-toplevel

                os.kill(agent.tty_sessions[tty_id]["pid"], _signal.SIGTERM)

            # 重置终端数据
            agent.tty_sessions[tty_id] = {
                "master_fd": None,
                "pid": None,
                "shell": "/bin/bash",
            }

            return {
                "success": True,
                "stdout": f"虚拟终端 [{tty_id}] 已关闭",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"关闭虚拟终端 [{tty_id}] 失败: {str(e)}",
            }

    def _close_tty_windows(self, agent: Any, tty_id: str) -> Dict[str, Any]:
        """Windows平台关闭终端"""
        if agent.tty_sessions[tty_id]["process"] is None:
            return {
                "success": True,
                "stdout": f"没有正在运行的虚拟终端 [{tty_id}]",
                "stderr": "",
            }

        try:
            # 终止进程
            agent.tty_sessions[tty_id]["process"].terminate()
            agent.tty_sessions[tty_id]["process"].wait()

            # 重置终端数据
            import queue as _queue  # pylint: disable=import-outside-toplevel

            agent.tty_sessions[tty_id] = {
                "process": None,
                "output_queue": _queue.Queue(),
                "output_thread": None,
                "shell": "cmd.exe",
            }

            return {
                "success": True,
                "stdout": f"虚拟终端 [{tty_id}] 已关闭",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"关闭虚拟终端 [{tty_id}] 失败: {str(e)}",
            }

    def _get_screen(self, agent: Any, tty_id: str) -> Dict[str, Any]:
        """获取当前终端屏幕内容"""
        if sys.platform == "win32":
            # Windows平台暂不支持获取屏幕内容
            return {
                "success": False,
                "stdout": "",
                "stderr": "Windows平台暂不支持获取屏幕内容功能",
            }

        if agent.tty_sessions[tty_id]["master_fd"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"虚拟终端 [{tty_id}] 未启动",
            }

        try:
            # 发送控制序列获取屏幕内容
            os.write(
                agent.tty_sessions[tty_id]["master_fd"],
                b"\x1b[2J\x1b[H\x1b[999;999H\x1b[6n",
            )

            # 读取响应
            output = ""
            start_time = time.time()
            while time.time() - start_time < 2.0:  # 最多等待2秒
                try:
                    import select as _select  # pylint: disable=import-outside-toplevel

                    r, _, _ = _select.select(
                        [agent.tty_sessions[tty_id]["master_fd"]], [], [], 0.1
                    )
                    if r:
                        data = os.read(agent.tty_sessions[tty_id]["master_fd"], 1024)
                        if data:
                            output += data.decode()
                except BlockingIOError:
                    continue

            # 清理控制字符
            output = (
                output.replace("\x1b[2J", "")
                .replace("\x1b[H", "")
                .replace("\x1b[999;999H", "")
                .replace("\x1b[6n", "")
            )

            return {"success": True, "stdout": output.strip(), "stderr": ""}

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"获取终端 [{tty_id}] 屏幕内容失败: {str(e)}",
            }

    def _list_ttys(self, agent: Any) -> Dict[str, Any]:
        """列出所有虚拟终端"""
        try:
            active_ttys = []

            for tty_id, tty_data in agent.tty_sessions.items():
                if sys.platform == "win32":
                    status = "活动" if tty_data["process"] is not None else "关闭"
                    active_ttys.append(
                        {
                            "id": tty_id,
                            "status": status,
                            "pid": (
                                tty_data["process"].pid if tty_data["process"] else None
                            ),
                            "shell": tty_data["shell"],
                        }
                    )
                else:
                    status = "活动" if tty_data["master_fd"] is not None else "关闭"
                    active_ttys.append(
                        {
                            "id": tty_id,
                            "status": status,
                            "pid": tty_data["pid"] if tty_data["pid"] else None,
                            "shell": tty_data["shell"],
                        }
                    )

            # 格式化输出
            output = "虚拟终端列表:\n"
            for tty in active_ttys:
                output += f"ID: {tty['id']}, 状态: {tty['status']}, PID: {tty['pid']}, Shell: {tty['shell']}\n"

            return {
                "success": True,
                "stdout": output,
                "stderr": "",
                "tty_list": active_ttys,  # 返回原始数据，方便程序处理
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"获取虚拟终端列表失败: {str(e)}",
            }
