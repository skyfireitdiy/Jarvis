# -*- coding: utf-8 -*-
"""Jarvis service CLI。"""

import os
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

import typer

from jarvis.jarvis_utils.output import PrettyOutput

DEFAULT_GATEWAY_HOST = "127.0.0.1"
DEFAULT_GATEWAY_PORT = 8000
DEFAULT_FRONTEND_HOST = "127.0.0.1"
DEFAULT_FRONTEND_PORT = 5173
GATEWAY_READY_WAIT_SECONDS = 5
PROCESS_TERMINATE_TIMEOUT_SECONDS = 10
ROOT_MARKER_FILES = ("pyproject.toml",)
ROOT_MARKER_DIRECTORIES = ("frontend", "src/jarvis")

app = typer.Typer(help="Jarvis Service 服务")


class LoopAction(Enum):
    """服务循环的控制动作。"""

    EXIT = "exit"
    RESTART = "restart"


@dataclass
class ServiceConfig:
    """服务启动配置。"""

    project_root: Path
    frontend_root: Path
    gateway_host: str
    gateway_port: int
    frontend_host: str
    frontend_port: int
    gateway_password: Optional[str]


@dataclass
class ServiceProcesses:
    """运行中的服务进程。"""

    gateway_process: subprocess.Popen[bytes]
    frontend_process: subprocess.Popen[bytes]


class ServiceController:
    """管理服务启动、停止与信号驱动的循环控制。"""

    def __init__(self, config: ServiceConfig) -> None:
        self._config = config
        self._requested_action = LoopAction.EXIT
        self._signal_received = False

    def request_exit(self, _signum: int, _frame: object) -> None:
        """接收到终止信号时退出循环。"""
        self._requested_action = LoopAction.EXIT
        self._signal_received = True

    def request_restart(self, _signum: int, _frame: object) -> None:
        """接收到重启信号时重新启动服务。"""
        self._requested_action = LoopAction.RESTART
        self._signal_received = True

    def run_forever(self) -> None:
        """无限循环运行服务，直到收到退出信号。"""
        while True:
            self._signal_received = False
            self._requested_action = LoopAction.EXIT
            processes = self._start_services()
            next_action = self._wait_for_signal_or_process_exit(processes)
            self._stop_services(processes)
            if next_action == LoopAction.EXIT:
                PrettyOutput.auto_print("🛑 服务已停止")
                return
            PrettyOutput.auto_print("🔄 接收到重启信号，正在重新启动服务")

    def _start_services(self) -> ServiceProcesses:
        """启动 gateway 与 frontend 服务。"""
        self._validate_runtime_dependencies()
        PrettyOutput.auto_print("🚀 启动 Jarvis 服务")
        PrettyOutput.auto_print(f"📁 项目根目录: {self._config.project_root}")

        gateway_process = self._start_gateway_process()
        self._wait_for_gateway_ready()
        self._prepare_frontend_assets()
        frontend_process = self._start_frontend_process()
        self._print_service_summary(gateway_process.pid, frontend_process.pid)
        return ServiceProcesses(
            gateway_process=gateway_process,
            frontend_process=frontend_process,
        )

    def _wait_for_signal_or_process_exit(
        self, processes: ServiceProcesses
    ) -> LoopAction:
        """等待信号或子进程退出，并返回后续动作。"""
        while True:
            if self._signal_received:
                return self._requested_action
            if processes.gateway_process.poll() is not None:
                PrettyOutput.auto_print("⚠️ 网关服务已退出，服务循环将结束")
                return LoopAction.EXIT
            if processes.frontend_process.poll() is not None:
                PrettyOutput.auto_print("⚠️ 前端服务已退出，服务循环将结束")
                return LoopAction.EXIT
            time.sleep(1)

    def _validate_runtime_dependencies(self) -> None:
        """校验运行时依赖命令。"""
        self._require_command("python", "未找到 Python 环境")
        self._require_command("npm", "未找到 npm 环境")
        self._require_command("jwg", "未找到 jwg 命令，请确保 Jarvis 已正确安装")

    def _require_command(self, command_name: str, error_message: str) -> None:
        """确保命令存在。"""
        if not shutil.which(command_name):
            PrettyOutput.auto_print(f"❌ {error_message}")
            raise typer.Exit(code=1)

    def _start_gateway_process(self) -> subprocess.Popen[bytes]:
        """启动 Web Gateway 进程。"""
        PrettyOutput.auto_print("⏳ 启动网关服务")
        command = [
            "jwg",
            "--host",
            self._config.gateway_host,
            "--port",
            str(self._config.gateway_port),
        ]
        if self._config.gateway_password:
            command.extend(["--gateway-password", self._config.gateway_password])
        process = subprocess.Popen(command, cwd=self._config.project_root)
        PrettyOutput.auto_print(f"✅ 网关已启动 (PID: {process.pid})")
        return process

    def _wait_for_gateway_ready(self) -> None:
        """等待网关服务完成启动。"""
        PrettyOutput.auto_print("⏳ 等待网关服务就绪")
        time.sleep(GATEWAY_READY_WAIT_SECONDS)

    def _prepare_frontend_assets(self) -> None:
        """安装依赖并构建前端产物。"""
        PrettyOutput.auto_print("⏳ 安装前端依赖")
        self._run_command(["npm", "install"], self._config.frontend_root)
        PrettyOutput.auto_print("✅ 前端依赖安装完成")
        PrettyOutput.auto_print("⏳ 构建前端发布产物")
        self._run_command(["npm", "run", "build"], self._config.frontend_root)
        PrettyOutput.auto_print("✅ 前端发布版本构建完成")

    def _start_frontend_process(self) -> subprocess.Popen[bytes]:
        """启动前端预览服务。"""
        PrettyOutput.auto_print("⏳ 启动前端发布服务")
        command = [
            "npm",
            "run",
            "preview",
            "--",
            "--host",
            self._config.frontend_host,
            "--port",
            str(self._config.frontend_port),
        ]
        process = subprocess.Popen(command, cwd=self._config.frontend_root)
        PrettyOutput.auto_print(f"✅ 前端发布服务已启动 (PID: {process.pid})")
        return process

    def _run_command(self, command: list[str], cwd: Path) -> None:
        """执行前台命令并在失败时退出。"""
        try:
            subprocess.run(command, cwd=cwd, check=True)
        except subprocess.CalledProcessError as error:
            PrettyOutput.auto_print(
                f"❌ 命令执行失败: {' '.join(command)} (退出码: {error.returncode})"
            )
            raise typer.Exit(code=error.returncode) from error

    def _stop_services(self, processes: ServiceProcesses) -> None:
        """停止所有服务进程。"""
        PrettyOutput.auto_print("🛑 正在停止服务")
        self._terminate_process(processes.frontend_process, "前端服务")
        self._terminate_process(processes.gateway_process, "网关服务")

    def _terminate_process(
        self, process: subprocess.Popen[bytes], process_name: str
    ) -> None:
        """终止单个子进程。"""
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=PROCESS_TERMINATE_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            PrettyOutput.auto_print(f"⚠️ 强制结束{process_name}")
            process.kill()
            process.wait()

    def _print_service_summary(
        self, gateway_pid: int, frontend_pid: int
    ) -> None:
        """打印启动结果摘要。"""
        PrettyOutput.auto_print(
            f"ℹ️ 网关地址: http://{self._config.gateway_host}:{self._config.gateway_port}"
        )
        PrettyOutput.auto_print(
            f"ℹ️ 前端地址: http://{self._config.frontend_host}:{self._config.frontend_port}"
        )
        PrettyOutput.auto_print(
            f"ℹ️ 运行中的 PID: gateway={gateway_pid}, frontend={frontend_pid}"
        )
        PrettyOutput.auto_print("ℹ️ 提示: Ctrl+C 停止全部服务，发送 SIGUSR1 触发重启")


def resolve_project_root() -> Path:
    """根据可编辑安装路径自动定位 Jarvis 源码根目录。"""
    current_path = Path(__file__).resolve()
    for candidate_root in (current_path.parent, *current_path.parents):
        if is_project_root(candidate_root):
            return candidate_root
    PrettyOutput.auto_print(
        "❌ 未找到 Jarvis 源码根目录，请确认使用 'uv tool install -e .' 进行安装"
    )
    raise typer.Exit(code=1)


def is_project_root(candidate_root: Path) -> bool:
    """判断目录是否为 Jarvis 项目根目录。"""
    has_marker_files = all((candidate_root / marker).exists() for marker in ROOT_MARKER_FILES)
    has_marker_directories = all(
        (candidate_root / marker).exists() for marker in ROOT_MARKER_DIRECTORIES
    )
    return has_marker_files and has_marker_directories


def build_service_config() -> ServiceConfig:
    """根据环境变量构建服务配置。"""
    project_root = resolve_project_root()
    frontend_root = project_root / "frontend"
    return ServiceConfig(
        project_root=project_root,
        frontend_root=frontend_root,
        gateway_host=os.getenv("JARVIS_GATEWAY_HOST", DEFAULT_GATEWAY_HOST),
        gateway_port=int(os.getenv("JARVIS_GATEWAY_PORT", str(DEFAULT_GATEWAY_PORT))),
        frontend_host=os.getenv("JARVIS_FRONTEND_HOST", DEFAULT_FRONTEND_HOST),
        frontend_port=int(os.getenv("JARVIS_FRONTEND_PORT", str(DEFAULT_FRONTEND_PORT))),
        gateway_password=os.getenv("JARVIS_GATEWAY_PASSWORD") or None,
    )


def run_service() -> None:
    """启动 Jarvis 服务循环。"""
    config = build_service_config()
    controller = ServiceController(config)
    signal.signal(signal.SIGINT, controller.request_exit)
    signal.signal(signal.SIGTERM, controller.request_exit)
    signal.signal(signal.SIGUSR1, controller.request_restart)
    controller.run_forever()


def main() -> None:
    """应用入口。"""
    run_service()


if __name__ == "__main__":
    main()
