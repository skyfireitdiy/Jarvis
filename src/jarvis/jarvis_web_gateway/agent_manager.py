# -*- coding: utf-8 -*-
"""Agent Manager：管理 Agent 生命周期。

负责创建、停止、监控 Agent 子进程，分配和管理端口。
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import uuid
from datetime import datetime
from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional


class AgentInfo:
    """Agent 信息。"""

    def __init__(
        self,
        agent_id: str,
        agent_type: str,
        pid: int,
        port: int,
        working_dir: str,
        process: subprocess.Popen,
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

    def __init__(self, on_status_change: Optional[Callable[[str, str, Any], None]] = None) -> None:
        """初始化 AgentManager。

        Args:
            on_status_change: 状态变更回调函数
        """
        self._agents: Dict[str, AgentInfo] = {}
        self._on_status_change = on_status_change

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

        # 启动监控任务
        agent_info._monitor_task = asyncio.create_task(
            self._monitor_agent(agent_id)
        )

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

        # 从内存中移除
        del self._agents[agent_id]

        # 通知状态变更
        if self._on_status_change:
            self._on_status_change(agent_id, "stopped", agent_info.to_dict())

        return {"agent_id": agent_id, "status": "stopped"}

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
            port = int(min_port + (max_port - min_port) * (hash(uuid.uuid4()) % 10000) / 10000)

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

        try:
            # 等待进程退出
            return_code = await asyncio.get_event_loop().run_in_executor(
                None, agent_info.process.wait
            )

            # 检查是否异常退出
            if return_code != 0:
                agent_info.status = "error"
                print(f"[AGENT MANAGER] Agent {agent_id} exited with code {return_code}")
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
                print(f"[AGENT MANAGER] Agent {agent_id} exited normally")
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
