from typing import Dict, Any
import os
import time
import pty
import fcntl
import signal
import select
from yaspin import yaspin
from yaspin.spinners import Spinners

class VirtualTTYTool:
    name = "virtual_tty"
    description = "控制虚拟终端执行各种操作，如启动终端、输入命令、获取输出等。与execute_shell不同，此工具会创建一个持久的虚拟终端会话，可以连续执行多个命令，并保持终端状态。适用于需要交互式操作的场景，如运行需要用户输入的交互式程序。"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "要执行的终端操作，可选值: 'launch', 'send_keys', 'output', 'close'"
            },
            "keys": {
                "type": "string",
                "description": "要发送的按键序列（用于send_keys操作），例如：'ls\\n'表示输入ls后按回车"
            },
            "timeout": {
                "type": "number",
                "description": "等待输出的超时时间（秒），用于send_keys和output操作"
            }
        },
        "required": ["action"]
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
            return {
                "success": False,
                "stdout": "",
                "stderr": "未提供agent对象"
            }
            
        # 确保agent有tty属性字典
        if not hasattr(agent, "tty_data"):
            agent.tty_data = {
                "master_fd": None,
                "pid": None,
                "shell": os.environ.get("SHELL", "/bin/bash")
            }
            
        action = args.get("action", "").strip().lower()
        
        # 验证操作类型
        valid_actions = ['launch', 'send_keys', 'output', 'close']
        if action not in valid_actions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"不支持的操作: {action}。有效操作: {', '.join(valid_actions)}"
            }
            
        try:
            if action == "launch":
                with yaspin(Spinners.dots, text="正在启动虚拟终端...") as spinner:
                    result = self._launch_tty(agent)
                    if result["success"]:
                        spinner.text = "启动虚拟终端成功"
                        spinner.ok("✅")
                    else:
                        spinner.text = "启动虚拟终端失败"
                        spinner.fail("❌")
                    return result
            elif action == "send_keys":
                keys = args.get("keys", "").strip()
                timeout = args.get("timeout", 5.0)  # 默认5秒超时
                with yaspin(Spinners.dots, text=f"正在发送按键序列: {keys}...") as spinner:
                    result = self._input_command(agent, keys, timeout)
                    if result["success"]:
                        spinner.text = f"发送按键序列 {keys} 成功"
                        spinner.ok("✅")
                    else:
                        spinner.text = f"发送按键序列 {keys} 失败"
                        spinner.fail("❌")
                    return result
            elif action == "output":
                timeout = args.get("timeout", 5.0)  # 默认5秒超时
                with yaspin(Spinners.dots, text="正在获取终端输出...") as spinner:
                    result = self._get_output(agent, timeout)
                    if result["success"]:
                        spinner.text = "获取终端输出成功"
                        spinner.ok("✅")
                    else:
                        spinner.text = "获取终端输出失败"
                        spinner.fail("❌")
                    return result
            elif action == "close":
                with yaspin(Spinners.dots, text="正在关闭虚拟终端...") as spinner:
                    result = self._close_tty(agent)
                    if result["success"]:
                        spinner.text = "关闭虚拟终端成功"
                        spinner.ok("✅")
                    else:
                        spinner.text = "关闭虚拟终端失败"
                        spinner.fail("❌")
                    return result
            return {
                "success": False,
                "stdout": "",
                "stderr": "不支持的操作"
            }
            
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"执行终端操作出错: {str(e)}"
            }
    
    def _launch_tty(self, agent: Any) -> Dict[str, Any]:
        """启动虚拟终端"""
        try:
            # 创建伪终端
            pid, master_fd = pty.fork()
            
            if pid == 0:  # 子进程
                # 执行shell
                os.execvp(agent.tty_data["shell"], [agent.tty_data["shell"]])
            else:  # 父进程
                # 设置非阻塞模式
                fcntl.fcntl(master_fd, fcntl.F_SETFL, os.O_NONBLOCK)
                
                # 保存终端状态
                agent.tty_data["master_fd"] = master_fd
                agent.tty_data["pid"] = pid
                
                return {
                    "success": True,
                    "stdout": "虚拟终端已启动",
                    "stderr": ""
                }
                
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"启动虚拟终端失败: {str(e)}"
            }
    
    def _input_command(self, agent: Any, command: str, timeout: float) -> Dict[str, Any]:
        """输入命令并等待输出"""
        if agent.tty_data["master_fd"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": "虚拟终端未启动"
            }
            
        try:
            # 直接发送按键序列，不添加换行符
            os.write(agent.tty_data["master_fd"], command.encode())
            
            # 等待输出
            output = ""
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                try:
                    # 使用select等待数据可读
                    r, _, _ = select.select([agent.tty_data["master_fd"]], [], [], 0.1)
                    if r:
                        data = os.read(agent.tty_data["master_fd"], 1024)
                        if data:
                            output += data.decode()
                except BlockingIOError:
                    continue
                    
            return {
                "success": True,
                "stdout": output,
                "stderr": ""
            }
            
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"执行命令失败: {str(e)}"
            }
    
    def _get_output(self, agent: Any, timeout: float = 5.0) -> Dict[str, Any]:
        """获取终端输出"""
        if agent.tty_data["master_fd"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": "虚拟终端未启动"
            }
            
        try:
            output = ""
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                # 使用select等待数据可读
                r, _, _ = select.select([agent.tty_data["master_fd"]], [], [], 0.1)
                if r:
                    while True:
                        try:
                            data = os.read(agent.tty_data["master_fd"], 1024)
                            if data:
                                output += data.decode()
                            else:
                                break
                        except BlockingIOError:
                            break
                        
            return {
                "success": True,
                "stdout": output,
                "stderr": ""
            }
            
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"获取输出失败: {str(e)}"
            }
    
    def _close_tty(self, agent: Any) -> Dict[str, Any]:
        """关闭虚拟终端"""
        if agent.tty_data["master_fd"] is None:
            return {
                "success": True,
                "stdout": "没有正在运行的虚拟终端",
                "stderr": ""
            }
            
        try:
            # 关闭主文件描述符
            os.close(agent.tty_data["master_fd"])
            
            # 终止子进程
            if agent.tty_data["pid"]:
                os.kill(agent.tty_data["pid"], signal.SIGTERM)
                
            # 清除终端数据
            agent.tty_data = {
                "master_fd": None,
                "pid": None,
                "shell": os.environ.get("SHELL", "/bin/bash")
            }
            
            return {
                "success": True,
                "stdout": "虚拟终端已关闭",
                "stderr": ""
            }
            
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"关闭虚拟终端失败: {str(e)}"
            }
