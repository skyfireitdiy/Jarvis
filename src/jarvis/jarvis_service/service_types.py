# -*- coding: utf-8 -*-
"""Jarvis service 的基础数据类型与枚举。"""

from dataclasses import dataclass
from enum import Enum
import subprocess
from pathlib import Path
from typing import Optional


class LoopAction(Enum):
    """服务循环的控制动作。"""

    EXIT = "exit"
    RESTART = "restart"
    RESTART_GATEWAY_ONLY = "restart_gateway_only"
    RESTART_FRONTEND_ONLY = "restart_frontend_only"


@dataclass
class ServiceConfig:
    """服务启动配置。"""

    project_root: Path
    frontend_root: Path
    gateway_host: str
    gateway_port: int
    frontend_host: str
    frontend_port: int
    node_mode: str
    node_id: Optional[str]
    master_url: Optional[str]
    node_secret: Optional[str]
    dev_mode: bool = False


@dataclass
class ServiceStatus:
    """服务状态信息（跨平台统一格式）。"""

    is_running: bool
    is_enabled: bool  # 是否启用自启动
    pid: Optional[int] = None
    mode: Optional[str] = None  # "master"或"child"
    error_message: Optional[str] = None


@dataclass
class ServiceProcesses:
    """运行中的服务进程。"""

    gateway_process: subprocess.Popen[bytes]
    frontend_process: Optional[subprocess.Popen[bytes]]
