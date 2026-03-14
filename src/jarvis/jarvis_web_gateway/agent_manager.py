# -*- coding: utf-8 -*-
"""Agent Manager：管理 Agent 生命周期。

负责创建、停止、监控 Agent 子进程，分配和管理端口。
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional

from jarvis.jarvis_utils.config import get_data_dir


class AgentInfo:
    """Agent 信息。"""

    def __init__(
        self,
        agent_id: str,
        agent_type: str,
        pid: int,
        port: int,
        working_dir: str,
        process: Optional[subprocess.Popen],
        name: Optional[str] = None,
    ) -> None:
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.name = name
        self.pid = pid
        self.port = port
        self.working_dir = working_dir
        self.process = process
        self.status = "running"
        self.created_at = datetime.now().isoformat()
        self._monitor_task: Optional[asyncio.Task] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "name": self.name,
            "pid": self.pid,
            "port": self.port,
            "status": self.status,
            "working_dir": self.working_dir,
            "created_at": self.created_at,
        }


class AgentManager:
    """Agent 管理器：管理 Agent 子进程和端口。"""

    # Agent 入口文件路径
    AGENT_ENTRY_POINTS = {
        "agent": "python -m jarvis.jarvis_agent.jarvis",
        "codeagent": "python -m jarvis.jarvis_code_agent.code_agent",
    }

    # 随机端口范围
    PORT_RANGE = (10000, 65535)

    # Agent 列表持久化文件路径
    PERSISTENCE_FILE = Path(get_data_dir()) / "gateway" / ".jarvis_agents.json"

    def __init__(
        self, on_status_change: Optional[Callable[[str, str, Any], None]] = None
    ) -> None:
        """初始化 AgentManager。

        Args:
            on_status_change: 状态变更回调函数
        """
        self._agents: Dict[str, AgentInfo] = {}
        self._on_status_change = on_status_change

        # 加载已保存的 Agent 列表
        self._load_agents()

    def create_agent(
        self,
        agent_type: str,
        working_dir: str,
        name: Optional[str] = None,
        llm_group: str = "default",
        tool_group: str = "default",
        config_file: Optional[str] = None,
        task: Optional[str] = None,
        additional_args: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """创建 Agent。

        Args:
            agent_type: Agent 类型 ("agent" 或 "codeagent")
            working_dir: 工作目录
            name: Agent 名称（可选，用于标识）
            llm_group: LLM 模型组
            tool_group: 工具组
            config_file: 配置文件路径
            task: 任务描述（仅对 codeagent 有效）
            additional_args: 额外参数

        Returns:
            Agent 信息字典

        Raises:
            ValueError: 参数无效
            RuntimeError: 启动失败
        """
        # 验证 agent_type
        if agent_type not in self.AGENT_ENTRY_POINTS:
            raise ValueError(
                f"Invalid agent_type: {agent_type}, "
                f"must be one of {list(self.AGENT_ENTRY_POINTS.keys())}"
            )

        # 展开工作目录中的 ~ 符号
        working_dir = os.path.expanduser(working_dir)

        # 验证工作目录
        if not os.path.isdir(working_dir):
            raise ValueError(f"Working directory not found: {working_dir}")

        # 生成唯一 ID
        agent_id = str(uuid.uuid4())

        # 分配端口
        port = self._allocate_port()
        if port is None:
            raise RuntimeError("No available port")

        # 构建命令行参数
        cmd = self._build_command(
            agent_type=agent_type,
            port=port,
            llm_group=llm_group,
            tool_group=tool_group,
            config_file=config_file,
            task=task,
            additional_args=additional_args,
        )

        # 打印启动信息
        print("[AGENT MANAGER] Creating agent:")
        print(f"  Agent ID: {agent_id}")
        print(f"  Type: {agent_type}")
        print(f"  Working Dir: {working_dir}")
        print(f"  Port: {port}")
        print(f"  Command: {' '.join(cmd)}")

        # 启动子进程（不重定向 stdin/stdout/stderr，允许 TTY 环境）
        try:
            print("[AGENT MANAGER] Starting subprocess...")
            process = subprocess.Popen(
                cmd,
                cwd=working_dir,
            )
            print(f"[AGENT MANAGER] Process started with PID: {process.pid}")
        except Exception as e:
            print(f"[AGENT MANAGER] Failed to start agent: {e}")
            raise RuntimeError(f"Failed to start agent: {e}")

        # 创建 AgentInfo
        agent_info = AgentInfo(
            agent_id=agent_id,
            agent_type=agent_type,
            pid=process.pid,
            port=port,
            working_dir=working_dir,
            process=process,
            name=name,
        )

        # 保存到内存
        self._agents[agent_id] = agent_info
        print(f"[AGENT MANAGER] Agent created successfully: {agent_id}")

        # 保存到持久化文件
        self._save_agents()

        # 启动监控任务
        agent_info._monitor_task = asyncio.create_task(self._monitor_agent(agent_id))

        # 返回信息
        return agent_info.to_dict()

    def stop_agent(self, agent_id: str) -> Dict[str, Any]:
        """停止 Agent。

        Args:
            agent_id: Agent ID

        Returns:
            停止结果

        Raises:
            KeyError: Agent 不存在
        """
        if agent_id not in self._agents:
            raise KeyError(f"Agent not found: {agent_id}")

        agent_info = self._agents[agent_id]

        # 发送 SIGTERM
        if agent_info.process is not None:
            agent_info.process.terminate()

            # 等待进程退出（最多 10 秒）
            try:
                agent_info.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                # 强制杀死进程
                agent_info.process.kill()
                agent_info.process.wait()

        # 取消监控任务
        if agent_info._monitor_task:
            agent_info._monitor_task.cancel()

        # 更新状态
        agent_info.status = "stopped"

        # 保留在内存中（不删除），以便重启后恢复历史记录
        # del self._agents[agent_id]

        # 更新持久化文件
        self._save_agents()

        # 通知状态变更
        if self._on_status_change:
            self._on_status_change(agent_id, "stopped", agent_info.to_dict())

        return {"agent_id": agent_id, "status": "stopped"}

    def delete_agent(self, agent_id: str) -> Dict[str, Any]:
        """删除 Agent。

        Args:
            agent_id: Agent ID

        Returns:
            删除结果

        Raises:
            KeyError: Agent 不存在
        """
        if agent_id not in self._agents:
            raise KeyError(f"Agent not found: {agent_id}")

        agent_info = self._agents[agent_id]

        # 如果正在运行，先停止
        if agent_info.status == "running" and agent_info.process is not None:
            agent_info.process.terminate()

            # 等待进程退出（最多 10 秒）
            try:
                agent_info.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                # 强制杀死进程
                agent_info.process.kill()
                agent_info.process.wait()

        # 取消监控任务
        if agent_info._monitor_task:
            agent_info._monitor_task.cancel()

        # 从内存中删除
        del self._agents[agent_id]

        # 更新持久化文件
        self._save_agents()

        # 通知状态变更
        if self._on_status_change:
            self._on_status_change(agent_id, "deleted", None)

        return {"agent_id": agent_id, "status": "deleted"}

    def get_agent_list(self) -> List[Dict[str, Any]]:
        """获取 Agent 列表。

        Returns:
            Agent 信息列表
        """
        return [agent.to_dict() for agent in self._agents.values()]

    def get_agent(self, agent_id: str) -> Optional[AgentInfo]:
        """获取 Agent 信息。

        Args:
            agent_id: Agent ID

        Returns:
            Agent 信息，不存在返回 None
        """
        return self._agents.get(agent_id)

    def _allocate_port(self) -> Optional[int]:
        """分配随机端口。

        Returns:
            可用端口，无可用端口返回 None
        """
        min_port, max_port = self.PORT_RANGE

        # 尝试 10 次随机分配
        for _ in range(10):
            port = int(
                min_port + (max_port - min_port) * (hash(uuid.uuid4()) % 10000) / 10000
            )

            # 检查端口是否被占用
            if self._is_port_available(port):
                return port

        return None

    def _is_port_available(self, port: int) -> bool:
        """检查端口是否可用。

        Args:
            port: 端口号

        Returns:
            True 可用，False 被占用
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return True
        except OSError:
            return False

    def _build_command(
        self,
        agent_type: str,
        port: int,
        llm_group: str,
        tool_group: str,
        config_file: Optional[str],
        task: Optional[str],
        additional_args: Optional[Dict[str, Any]],
    ) -> List[str]:
        """构建 Agent 启动命令。

        Args:
            agent_type: Agent 类型
            port: 端口
            llm_group: LLM 模型组
            tool_group: 工具组
            config_file: 配置文件路径
            task: 任务描述
            additional_args: 额外参数

        Returns:
            命令列表
        """
        # 基础命令
        base_cmd = self.AGENT_ENTRY_POINTS[agent_type].split()

        # 添加参数
        cmd = base_cmd.copy()
        cmd.extend(["--web-gateway-host", "0.0.0.0"])  # 允许来自任何 IP 的连接
        cmd.extend(["--web-gateway-port", str(port)])
        cmd.append("--web-gateway")  # 启动为 WebSocket Gateway 模式

        if config_file:
            cmd.extend(["--config-file", config_file])

        if task:
            cmd.extend(["--task", task])

        # 添加额外参数
        if additional_args:
            for key, value in additional_args.items():
                cmd.extend([f"--{key}", str(value)])

        return cmd

    async def _monitor_agent(self, agent_id: str) -> None:
        """监控 Agent 进程。

        Args:
            agent_id: Agent ID
        """
        agent_info = self._agents.get(agent_id)
        if not agent_info:
            return

        # 如果进程对象为 None（恢复的情况），直接返回
        if agent_info.process is None:
            print(
                f"[AGENT MANAGER] Agent {agent_id} has no process object, skipping monitor"
            )
            return

        try:
            # 等待进程退出
            return_code = await asyncio.get_event_loop().run_in_executor(
                None, agent_info.process.wait
            )

            # 检查是否异常退出
            if return_code != 0:
                agent_info.status = "error"
                print(
                    f"[AGENT MANAGER] Agent {agent_id} exited with code {return_code}"
                )
                if self._on_status_change:
                    self._on_status_change(
                        agent_id,
                        "error",
                        {
                            "agent_id": agent_id,
                            "status": "error",
                            "return_code": return_code,
                            "message": f"Agent exited with code {return_code}",
                        },
                    )
            else:
                # 正常退出，更新状态为 stopped
                agent_info.status = "stopped"
                print(
                    f"[AGENT MANAGER] Agent {agent_id} exited normally, status updated to stopped"
                )
                # 保存到持久化文件
                self._save_agents()
                # 通知状态变更
                if self._on_status_change:
                    self._on_status_change(
                        agent_id,
                        "stopped",
                        {
                            "agent_id": agent_id,
                            "status": "stopped",
                            "return_code": return_code,
                            "message": "Agent exited normally",
                        },
                    )
        except asyncio.CancelledError:
            # 任务被取消，正常情况
            print(f"[AGENT MANAGER] Monitor task cancelled for agent {agent_id}")
            pass
        except Exception as e:
            # 监控出错
            print(f"[AGENT MANAGER] Monitor error for agent {agent_id}: {e}")
            agent_info.status = "error"
            if self._on_status_change:
                self._on_status_change(
                    agent_id,
                    "error",
                    {
                        "agent_id": agent_id,
                        "status": "error",
                        "message": f"Monitor error: {e}",
                    },
                )

    async def cleanup(self) -> None:
        """清理所有 Agent。"""
        agent_ids = list(self._agents.keys())
        for agent_id in agent_ids:
            try:
                self.stop_agent(agent_id)
            except Exception:
                pass

    async def start_monitoring_for_running_agents(self) -> None:
        """为所有运行中的 Agent 启动监控任务。

        这个方法需要在异步上下文中调用（在应用启动后）。
        """
        for agent_id, agent_info in list(self._agents.items()):
            if agent_info.status == "running" and agent_info._monitor_task is None:
                print(f"[AGENT MANAGER] Starting monitor task for agent {agent_id}")
                agent_info._monitor_task = asyncio.create_task(
                    self._monitor_agent(agent_id)
                )

    def _load_agents(self) -> None:
        """从文件加载已保存的 Agent 列表。"""
        if not self.PERSISTENCE_FILE.exists():
            print("[AGENT MANAGER] No persistence file found, starting fresh")
            return

        try:
            with open(self.PERSISTENCE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, list):
                print("[AGENT MANAGER] Invalid persistence file format")
                return

            print(
                f"[AGENT MANAGER] Loading {len(data)} saved agents from {self.PERSISTENCE_FILE}"
            )

            for agent_data in data:
                try:
                    # 恢复 AgentInfo
                    agent_info = AgentInfo(
                        agent_id=agent_data["agent_id"],
                        agent_type=agent_data["agent_type"],
                        pid=agent_data.get("pid", 0),
                        port=agent_data["port"],
                        working_dir=agent_data["working_dir"],
                        process=None,  # 进程对象无法恢复，设为 None
                        name=agent_data.get("name"),
                    )

                    # 检查进程是否还在运行
                    pid = agent_data.get("pid")
                    if pid and self._is_process_running(pid):
                        # 进程还在运行，恢复为 running 状态
                        agent_info.status = agent_data.get("status", "running")
                        print(
                            f"[AGENT MANAGER] Restored running agent {agent_info.agent_id} (PID: {pid})"
                        )

                        # 重新启动监控任务（需要异步上下文）
                        # 注意：这里不能直接创建异步任务，需要在异步上下文中调用
                        agent_info._monitor_task = None  # 稍后在异步上下文中创建
                    else:
                        # 进程已停止，恢复为 stopped 状态
                        agent_info.status = "stopped"
                        print(
                            f"[AGENT MANAGER] Restored stopped agent {agent_info.agent_id}"
                        )

                    # 恢复创建时间
                    agent_info.created_at = agent_data.get(
                        "created_at", datetime.now().isoformat()
                    )

                    # 保存到内存
                    self._agents[agent_info.agent_id] = agent_info
                except Exception as e:
                    print(
                        f"[AGENT MANAGER] Failed to restore agent {agent_data.get('agent_id')}: {e}"
                    )

            print(f"[AGENT MANAGER] Loaded {len(self._agents)} agents successfully")

        except Exception as e:
            print(f"[AGENT MANAGER] Failed to load agents: {e}")

    def _save_agents(self) -> None:
        """保存 Agent 列表到文件。"""
        try:
            # 确保目录存在
            self.PERSISTENCE_FILE.parent.mkdir(parents=True, exist_ok=True)

            data = [agent.to_dict() for agent in self._agents.values()]
            with open(self.PERSISTENCE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(
                f"[AGENT MANAGER] Saved {len(data)} agents to {self.PERSISTENCE_FILE}"
            )
        except Exception as e:
            print(f"[AGENT MANAGER] Failed to save agents: {e}")

    def _is_process_running(self, pid: int) -> bool:
        """检查进程是否在运行。

        Args:
            pid: 进程 ID

        Returns:
            True 运行中，False 已停止
        """
        try:
            # 发送信号 0 检查进程是否存在
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, OSError):
            return False
