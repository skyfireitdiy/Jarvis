from typing import Dict, Any
import os
import time
import pty
import fcntl
import signal
import select

class VirtualTTYTool:
    name = "virtual_tty"
    description = "控制虚拟终端执行各种操作，如启动终端、输入命令、获取输出等。与execute_script不同，此工具会创建一个持久的虚拟终端会话，可以连续执行多个命令，并保持终端状态。适用于需要交互式操作的场景，如运行需要用户输入的交互式程序。"
    labels = ['terminal', 'system', 'interactive']
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "要执行的终端操作，可选值: 'launch', 'send_keys', 'output', 'close', 'get_screen'"
            },
            "keys": {
                "type": "string",
                "description": "要发送的按键序列（用于send_keys操作）。"
            },
            "add_enter": {
                "type": "boolean",
                "description": "是否在按键序列末尾添加回车符（\\n），默认为false"
            },
            "timeout": {
                "type": "number",
                "description": "等待输出的超时时间（秒），用于send_keys和output操作"
            },
            "tty_id": {
                "type": "string",
                "description": "虚拟终端的唯一标识符，用于区分多个TTY会话。如果未提供，默认为'default'"
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
            
        # 获取TTY ID，默认为"default"
        tty_id = args.get("tty_id", "default")
            
        # 确保agent有tty_sessions字典
        if not hasattr(agent, "tty_sessions"):
            agent.tty_sessions = {}
            
        # 如果指定的tty_id不存在，为其创建一个新的tty_data
        if tty_id not in agent.tty_sessions:
            agent.tty_sessions[tty_id] = {
                "master_fd": None,
                "pid": None,
                "shell": "/bin/bash"
            }
            
        action = args.get("action", "").strip().lower()
        
        # 验证操作类型
        valid_actions = ['launch', 'send_keys', 'output', 'close', 'get_screen', 'list']
        if action not in valid_actions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"不支持的操作: {action}。有效操作: {', '.join(valid_actions)}"
            }
            
        try:
            if action == "launch":
                print(f"🚀 正在启动虚拟终端 [{tty_id}]...")
                result = self._launch_tty(agent, tty_id)
                if result["success"]:
                    print(f"✅ 启动虚拟终端 [{tty_id}] 成功")
                else:
                    print(f"❌ 启动虚拟终端 [{tty_id}] 失败")
                return result
            elif action == "send_keys":
                keys = args.get("keys", "").strip()
                add_enter = args.get("add_enter", False)
                timeout = args.get("timeout", 5.0)  # 默认5秒超时
                print(f"⌨️ 正在向终端 [{tty_id}] 发送按键序列: {keys}...")
                result = self._input_command(agent, tty_id, keys, timeout, add_enter)
                if result["success"]:
                    print(f"✅ 发送按键序列到终端 [{tty_id}] 成功")
                else:
                    print(f"❌ 发送按键序列到终端 [{tty_id}] 失败")
                return result
            elif action == "output":
                timeout = args.get("timeout", 5.0)  # 默认5秒超时
                print(f"📥 正在获取终端 [{tty_id}] 输出...")
                result = self._get_output(agent, tty_id, timeout)
                if result["success"]:
                    print(f"✅ 获取终端 [{tty_id}] 输出成功")
                else:
                    print(f"❌ 获取终端 [{tty_id}] 输出失败")
                return result
            elif action == "close":
                print(f"🔒 正在关闭虚拟终端 [{tty_id}]...")
                result = self._close_tty(agent, tty_id)
                if result["success"]:
                    print(f"✅ 关闭虚拟终端 [{tty_id}] 成功")
                else:
                    print(f"❌ 关闭虚拟终端 [{tty_id}] 失败")
                return result
            elif action == "get_screen":
                print(f"🖥️ 正在获取终端 [{tty_id}] 屏幕内容...")
                result = self._get_screen(agent, tty_id)
                if result["success"]:
                    print(f"✅ 获取终端 [{tty_id}] 屏幕内容成功")
                else:
                    print(f"❌ 获取终端 [{tty_id}] 屏幕内容失败")
                return result
            elif action == "list":
                print("📋 正在获取所有虚拟终端列表...")
                result = self._list_ttys(agent)
                if result["success"]:
                    print("✅ 获取虚拟终端列表成功")
                else:
                    print("❌ 获取虚拟终端列表失败")
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
    
    def _launch_tty(self, agent: Any, tty_id: str) -> Dict[str, Any]:
        """启动虚拟终端"""
        try:
            # 如果该ID的终端已经启动，先关闭它
            if agent.tty_sessions[tty_id]["master_fd"] is not None:
                self._close_tty(agent, tty_id)
                
            # 创建伪终端
            pid, master_fd = pty.fork()
            
            if pid == 0:  # 子进程
                # 执行shell
                os.execvp(agent.tty_sessions[tty_id]["shell"], [agent.tty_sessions[tty_id]["shell"]])
            else:  # 父进程
                # 设置非阻塞模式
                fcntl.fcntl(master_fd, fcntl.F_SETFL, os.O_NONBLOCK)
                
                # 保存终端状态
                agent.tty_sessions[tty_id]["master_fd"] = master_fd
                agent.tty_sessions[tty_id]["pid"] = pid
                
                # 读取初始输出
                output = ""
                start_time = time.time()
                while time.time() - start_time < 2.0:  # 最多等待2秒
                    try:
                        r, _, _ = select.select([master_fd], [], [], 0.1)
                        if r:
                            data = os.read(master_fd, 1024)
                            if data:
                                output += data.decode()
                    except BlockingIOError:
                        continue
                
                if output:
                    print(f"📤 终端 [{tty_id}]: {output}")
                
                return {
                    "success": True,
                    "stdout": output,
                    "stderr": ""
                }
                
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"启动虚拟终端 [{tty_id}] 失败: {str(e)}"
            }
    
    def _input_command(self, agent: Any, tty_id: str, command: str, timeout: float, add_enter: bool = False) -> Dict[str, Any]:
        """输入命令并等待输出"""
        if agent.tty_sessions[tty_id]["master_fd"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"虚拟终端 [{tty_id}] 未启动"
            }
            
        try:
            # 根据add_enter参数决定是否添加换行符
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
                    r, _, _ = select.select([agent.tty_sessions[tty_id]["master_fd"]], [], [], 0.1)
                    if r:
                        data = os.read(agent.tty_sessions[tty_id]["master_fd"], 1024)
                        if data:
                            output += data.decode()
                except BlockingIOError:
                    continue
            print(f"📤 终端 [{tty_id}]: {output}")
            return {
                "success": True,
                "stdout": output,
                "stderr": ""
            }
            
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"在终端 [{tty_id}] 执行命令失败: {str(e)}"
            }
    
    def _get_output(self, agent: Any, tty_id: str, timeout: float = 5.0) -> Dict[str, Any]:
        """获取终端输出"""
        if agent.tty_sessions[tty_id]["master_fd"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"虚拟终端 [{tty_id}] 未启动"
            }
            
        try:
            output = ""
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                # 使用select等待数据可读
                r, _, _ = select.select([agent.tty_sessions[tty_id]["master_fd"]], [], [], 0.1)
                if r:
                    while True:
                        try:
                            data = os.read(agent.tty_sessions[tty_id]["master_fd"], 1024)
                            if data:
                                output += data.decode()
                            else:
                                break
                        except BlockingIOError:
                            break
            print(f"📤 终端 [{tty_id}]: {output}")
                        
            return {
                "success": True,
                "stdout": output,
                "stderr": ""
            }
            
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"获取终端 [{tty_id}] 输出失败: {str(e)}"
            }
    
    def _close_tty(self, agent: Any, tty_id: str) -> Dict[str, Any]:
        """关闭虚拟终端"""
        if agent.tty_sessions[tty_id]["master_fd"] is None:
            return {
                "success": True,
                "stdout": f"没有正在运行的虚拟终端 [{tty_id}]",
                "stderr": ""
            }
            
        try:
            # 关闭主文件描述符
            os.close(agent.tty_sessions[tty_id]["master_fd"])
            
            # 终止子进程
            if agent.tty_sessions[tty_id]["pid"]:
                os.kill(agent.tty_sessions[tty_id]["pid"], signal.SIGTERM)
                
            # 重置终端数据
            agent.tty_sessions[tty_id] = {
                "master_fd": None,
                "pid": None,
                "shell": "/bin/bash"
            }
            
            return {
                "success": True,
                "stdout": f"虚拟终端 [{tty_id}] 已关闭",
                "stderr": ""
            }
            
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"关闭虚拟终端 [{tty_id}] 失败: {str(e)}"
            }

    def _get_screen(self, agent: Any, tty_id: str) -> Dict[str, Any]:
        """获取当前终端屏幕内容"""
        if agent.tty_sessions[tty_id]["master_fd"] is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"虚拟终端 [{tty_id}] 未启动"
            }
            
        try:
            # 发送控制序列获取屏幕内容
            os.write(agent.tty_sessions[tty_id]["master_fd"], b"\x1b[2J\x1b[H\x1b[999;999H\x1b[6n")
            
            # 读取响应
            output = ""
            start_time = time.time()
            while time.time() - start_time < 2.0:  # 最多等待2秒
                try:
                    r, _, _ = select.select([agent.tty_sessions[tty_id]["master_fd"]], [], [], 0.1)
                    if r:
                        data = os.read(agent.tty_sessions[tty_id]["master_fd"], 1024)
                        if data:
                            output += data.decode()
                except BlockingIOError:
                    continue
            
            # 清理控制字符
            output = output.replace("\x1b[2J", "").replace("\x1b[H", "").replace("\x1b[999;999H", "").replace("\x1b[6n", "")
            
            return {
                "success": True,
                "stdout": output.strip(),
                "stderr": ""
            }
            
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"获取终端 [{tty_id}] 屏幕内容失败: {str(e)}"
            }
            
    def _list_ttys(self, agent: Any) -> Dict[str, Any]:
        """列出所有虚拟终端"""
        try:
            active_ttys = []
            
            for tty_id, tty_data in agent.tty_sessions.items():
                status = "活动" if tty_data["master_fd"] is not None else "关闭"
                active_ttys.append({
                    "id": tty_id,
                    "status": status,
                    "pid": tty_data["pid"] if tty_data["pid"] else None,
                    "shell": tty_data["shell"]
                })
                
            # 格式化输出
            output = "虚拟终端列表:\n"
            for tty in active_ttys:
                output += f"ID: {tty['id']}, 状态: {tty['status']}, PID: {tty['pid']}, Shell: {tty['shell']}\n"
                
            return {
                "success": True,
                "stdout": output,
                "stderr": "",
                "tty_list": active_ttys  # 返回原始数据，方便程序处理
            }
            
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"获取虚拟终端列表失败: {str(e)}"
            }
