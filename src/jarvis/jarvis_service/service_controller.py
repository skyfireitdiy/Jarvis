# -*- coding: utf-8 -*-
"""服务主循环控制器：负责启动/停止网关与前端子进程，并在子进程异常退出时自动拉起。"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import typer

from jarvis.jarvis_service.service_types import (
    LoopAction,
    ServiceConfig,
    ServiceProcesses,
)
from jarvis.jarvis_utils.output import PrettyOutput

GATEWAY_READY_WAIT_SECONDS = 5
PROCESS_TERMINATE_TIMEOUT_SECONDS = 10

# 子进程连续启动失败达到该次数后，放弃自动拉起并退出服务，交给 systemd 兜底
MAX_CONSECUTIVE_START_FAILURES = 10
# 退避序列上限（秒）
MAX_RESTART_BACKOFF_SECONDS = 60
# 子进程启动后存活超过该时长，视为启动成功并重置失败计数
STARTUP_STABLE_SECONDS = 5


def compute_restart_backoff(failure_count: int) -> int:
    """计算第 N 次连续失败后的重启退避秒数。

    Args:
        failure_count: 连续失败次数（从 1 开始）

    Returns:
        退避秒数：1, 2, 4, 8, 16, 32, 60, 60, ...
    """
    if failure_count <= 0:
        return 0
    exponent = min(failure_count - 1, 16)
    return min(2**exponent, MAX_RESTART_BACKOFF_SECONDS)


class ServiceController:
    """管理服务启动、停止与信号驱动的循环控制。"""

    def __init__(self, config: ServiceConfig) -> None:
        self._config = config
        self._requested_action = LoopAction.EXIT
        self._signal_received = False
        # 网关/前端各自的连续启动失败计数
        self._gateway_failures = 0
        self._frontend_failures = 0

    def request_exit(self, _signum: int, _frame: object) -> None:
        """接收到终止信号时退出循环。"""
        self._requested_action = LoopAction.EXIT
        self._signal_received = True

    def request_restart(self, _signum: int, _frame: object) -> None:
        """接收到重启信号时重新启动服务。"""
        self._requested_action = LoopAction.RESTART
        self._signal_received = True

    def request_restart_gateway_only(self, _signum: int, _frame: object) -> None:
        """接收到信号时只重启网关服务，保持前端运行。"""
        self._requested_action = LoopAction.RESTART_GATEWAY_ONLY
        self._signal_received = True

    def request_restart_frontend_only(self, _signum: int, _frame: object) -> None:
        """接收到信号时只重启前端服务，保持网关运行。"""
        self._requested_action = LoopAction.RESTART_FRONTEND_ONLY
        self._signal_received = True

    def run_forever(self) -> None:
        """无限循环运行服务，直到收到退出信号或子进程反复启动失败。"""
        gateway_process: Optional[subprocess.Popen[bytes]] = None
        frontend_process: Optional[subprocess.Popen[bytes]] = None
        while True:
            self._signal_received = False
            self._requested_action = LoopAction.EXIT

            # 启动前按需等待退避，避免服务启动即崩导致的重启风暴
            if not self._wait_backoff_before_start(gateway_process, frontend_process):
                return

            processes = self._start_services(gateway_process, frontend_process)
            if processes is None:
                return

            gateway_process = processes.gateway_process
            frontend_process = processes.frontend_process
            started_at = time.monotonic()

            next_action = self._wait_for_signal_or_process_exit(processes, started_at)

            if next_action == LoopAction.RESTART_GATEWAY_ONLY:
                # 只重启网关，保持前端运行
                PrettyOutput.auto_print("🔄 只重启网关服务，保持前端运行")
                self._stop_gateway_only(processes)
                gateway_process = None
                frontend_process = processes.frontend_process
                continue

            if next_action == LoopAction.RESTART_FRONTEND_ONLY:
                # 只重启前端，保持网关运行
                PrettyOutput.auto_print("🔄 只重启前端服务，保持网关运行")
                self._stop_frontend_only(processes)
                gateway_process = processes.gateway_process
                frontend_process = None
                continue

            # 完全停止所有服务
            gateway_process = None
            frontend_process = None
            self._stop_services(processes)
            if next_action == LoopAction.EXIT:
                PrettyOutput.auto_print("🛑 服务已停止")
                return
            PrettyOutput.auto_print("🔄 接收到重启信号，正在重新启动服务")

    def _wait_backoff_before_start(
        self,
        gateway_process: Optional[subprocess.Popen[bytes]],
        frontend_process: Optional[subprocess.Popen[bytes]],
    ) -> bool:
        """在启动子进程前按连续失败次数等待退避。

        Args:
            gateway_process: 需要重启的网关进程（None 表示无需重启网关）
            frontend_process: 需要重启的前端进程（None 表示无需重启前端）

        Returns:
            True 表示可以继续启动；False 表示失败次数超限，应退出服务
        """
        backoff = 0
        if gateway_process is None:
            backoff = max(backoff, compute_restart_backoff(self._gateway_failures))
        if frontend_process is None and self._config.node_mode == "master":
            backoff = max(backoff, compute_restart_backoff(self._frontend_failures))

        if backoff > 0:
            PrettyOutput.auto_print(f"⏳ 等待 {backoff} 秒后重试启动服务")
            if self._interruptible_sleep(backoff):
                # 等待期间收到信号，交由主循环处理
                return True

        return not self._failure_limit_reached()

    def _failure_limit_reached(self) -> bool:
        """判断是否有服务连续失败次数超限。"""
        if self._gateway_failures >= MAX_CONSECUTIVE_START_FAILURES:
            PrettyOutput.auto_print(
                f"❌ 网关服务连续启动失败 {self._gateway_failures} 次，放弃自动拉起，退出服务"
            )
            return True
        if self._frontend_failures >= MAX_CONSECUTIVE_START_FAILURES:
            PrettyOutput.auto_print(
                f"❌ 前端服务连续启动失败 {self._frontend_failures} 次，放弃自动拉起，退出服务"
            )
            return True
        return False

    def _interruptible_sleep(self, seconds: float) -> bool:
        """可被信号打断的等待。

        Returns:
            True 表示等待期间收到了信号
        """
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self._signal_received:
                return True
            time.sleep(min(0.2, max(0.0, deadline - time.monotonic())))
        return False

    def _start_services(
        self,
        existing_gateway: Optional[subprocess.Popen[bytes]] = None,
        existing_frontend: Optional[subprocess.Popen[bytes]] = None,
    ) -> Optional[ServiceProcesses]:
        """按节点模式启动服务进程。

        Args:
            existing_gateway: 已存在的网关进程（只重启前端时使用）
            existing_frontend: 已存在的前端进程（只重启网关时使用）

        Returns:
            启动后的进程集合；若启动失败次数超限则返回 None
        """
        self._validate_runtime_dependencies()

        if existing_gateway is not None and existing_frontend is not None:
            PrettyOutput.auto_print("🚀 启动 Jarvis 服务")
        elif existing_gateway is not None:
            PrettyOutput.auto_print("🚀 重新启动前端服务（保持网关运行）")
        elif existing_frontend is not None:
            PrettyOutput.auto_print("🚀 重新启动网关服务（保持前端运行）")
        else:
            PrettyOutput.auto_print("🚀 启动 Jarvis 服务")
        PrettyOutput.auto_print(f"📁 项目根目录: {self._config.project_root}")

        gateway_process = existing_gateway
        if gateway_process is None:
            try:
                gateway_process = self._start_gateway_process()
            except typer.Exit:
                self._gateway_failures += 1
                if self._failure_limit_reached():
                    return None
                # 网关启动失败但仍可重试：返回空进程集合交给下一轮
                return ServiceProcesses(
                    gateway_process=_DeadProcess(),
                    frontend_process=existing_frontend,
                )
            self._wait_for_gateway_ready()

        frontend_process = existing_frontend
        if frontend_process is None and self._config.node_mode == "master":
            try:
                self._prepare_frontend_assets()
                frontend_process = self._start_frontend_process()
            except typer.Exit:
                self._frontend_failures += 1
                if self._failure_limit_reached():
                    return None
                return ServiceProcesses(
                    gateway_process=gateway_process,
                    frontend_process=_DeadProcess(),
                )

        self._print_service_summary(
            gateway_pid=gateway_process.pid,
            frontend_pid=frontend_process.pid if frontend_process else None,
        )
        return ServiceProcesses(
            gateway_process=gateway_process,
            frontend_process=frontend_process,
        )

    def _wait_for_signal_or_process_exit(
        self, processes: ServiceProcesses, started_at: Optional[float] = None
    ) -> LoopAction:
        """等待信号或子进程退出，并返回后续动作。

        子进程意外退出时不再退出整个服务，而是返回只重启该子进程的动作。

        Args:
            processes: 当前运行的进程集合
            started_at: 本轮启动的 monotonic 时间戳，用于判定启动是否稳定

        Returns:
            后续应执行的动作
        """
        stable_deadline = (
            started_at + STARTUP_STABLE_SECONDS if started_at is not None else None
        )
        while True:
            if self._signal_received:
                return self._requested_action
            if processes.gateway_process.poll() is not None:
                return_code = processes.gateway_process.returncode
                PrettyOutput.auto_print(
                    f"⚠️ 网关服务已退出（退出码: {return_code}），将自动重新拉起网关"
                )
                self._record_exit_result(True, stable_deadline)
                return LoopAction.RESTART_GATEWAY_ONLY
            if (
                processes.frontend_process is not None
                and processes.frontend_process.poll() is not None
            ):
                return_code = processes.frontend_process.returncode
                PrettyOutput.auto_print(
                    f"⚠️ 前端服务已退出（退出码: {return_code}），将自动重新拉起前端"
                )
                self._record_exit_result(False, stable_deadline)
                return LoopAction.RESTART_FRONTEND_ONLY
            time.sleep(1)

    def _record_exit_result(
        self, is_gateway: bool, stable_deadline: Optional[float]
    ) -> None:
        """根据子进程是否稳定运行过一段时间，更新连续失败计数。

        Args:
            is_gateway: True 表示网关，False 表示前端
            stable_deadline: 启动后达到“稳定”的时间点
        """
        is_stable = stable_deadline is not None and time.monotonic() >= stable_deadline
        if is_gateway:
            self._gateway_failures = 0 if is_stable else self._gateway_failures + 1
        else:
            self._frontend_failures = 0 if is_stable else self._frontend_failures + 1

    def _validate_runtime_dependencies(self) -> None:
        """校验运行时依赖命令。"""
        self._require_command("python", "未找到 Python 环境")
        self._require_command("jwg", "未找到 jwg 命令，请确保 Jarvis 已正确安装")
        if self._config.node_mode == "master":
            self._require_command("npm", "未找到 npm 环境")

    def _require_command(self, command_name: str, error_message: str) -> None:
        """确保命令存在。"""
        if self._find_command(command_name) is None:
            PrettyOutput.auto_print(f"❌ {error_message}")
            raise typer.Exit(code=1)

    def _find_command(self, command_name: str) -> Optional[str]:
        """查找命令完整路径，优先 PATH，其次常见用户目录。"""
        found = shutil.which(command_name)
        if found:
            return found
        # 用 bash 加载用户环境查找（覆盖用户 shell PATH）
        try:
            result = subprocess.run(
                ["bash", "-lc", f"which {command_name}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        # 额外检查常见用户 bin 目录
        candidates = [
            Path.home() / ".local" / "bin" / command_name,
            Path(sys.executable).parent / command_name,
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return None

    def _start_gateway_process(self) -> subprocess.Popen[bytes]:
        """启动 Web Gateway 进程。"""
        PrettyOutput.auto_print("⏳ 启动网关服务")
        jwg_path = self._find_command("jwg")
        if jwg_path is None:
            PrettyOutput.auto_print("❌ 未找到 jwg 命令，请确保 Jarvis 已正确安装")
            raise typer.Exit(code=1)
        command = [
            jwg_path,
            "--host",
            self._config.gateway_host,
            "--port",
            str(self._config.gateway_port),
        ]
        if self._config.node_mode:
            command.extend(["--node-mode", self._config.node_mode])
        if self._config.node_id:
            command.extend(["--node-id", self._config.node_id])
        if self._config.master_url:
            command.extend(["--master-url", self._config.master_url])
        if self._config.node_secret:
            command.extend(["--node-secret", self._config.node_secret])
        process = subprocess.Popen(command, cwd=self._config.project_root)
        PrettyOutput.auto_print(f"✅ 网关已启动 (PID: {process.pid})")
        return process

    def _wait_for_gateway_ready(self) -> None:
        """等待网关服务完成启动。"""
        PrettyOutput.auto_print("⏳ 等待网关服务就绪")
        time.sleep(GATEWAY_READY_WAIT_SECONDS)

    def _prepare_frontend_assets(self) -> None:
        """按需安装依赖并构建前端产物。

        通过 package-lock.json 的 hash 判断是否需要 npm install，通过源码 mtime
        判断是否需要 npm run build，避免每次重启都重复构建。
        """
        if self._should_install_dependencies():
            PrettyOutput.auto_print("⏳ 安装前端依赖")
            self._run_command(["npm", "install"], self._config.frontend_root)
            PrettyOutput.auto_print("✅ 前端依赖安装完成")
            self._save_build_state(lock_hash=self._compute_lock_hash())
        else:
            PrettyOutput.auto_print("⏩ 前端依赖未变化，跳过安装")

        if self._config.dev_mode:
            PrettyOutput.auto_print("⏩ 开发模式跳过构建步骤")
            return

        if self._should_build():
            PrettyOutput.auto_print("⏳ 构建前端发布产物")
            self._run_command(["npm", "run", "build"], self._config.frontend_root)
            PrettyOutput.auto_print("✅ 前端发布版本构建完成")
            self._save_build_state(built_at=self._compute_source_mtime())
        else:
            PrettyOutput.auto_print("⏩ 前端源码未变化，跳过构建")

    def _get_build_state_path(self) -> Path:
        """返回前端构建状态记录文件路径。"""
        return self._config.frontend_root / ".jarvis-frontend-build.json"

    def _load_build_state(self) -> dict:
        """读取前端构建状态记录。"""
        path = self._get_build_state_path()
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_build_state(self, **updates: object) -> None:
        """更新并持久化前端构建状态记录。"""
        state = self._load_build_state()
        state.update(updates)
        try:
            self._get_build_state_path().write_text(
                json.dumps(state, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as error:
            PrettyOutput.auto_print(f"⚠️ 无法写入前端构建状态: {error}")

    def _compute_lock_hash(self) -> str:
        """计算依赖锁文件的内容 hash。"""
        lock_path = self._config.frontend_root / "package-lock.json"
        if not lock_path.exists():
            return ""
        try:
            return hashlib.sha256(lock_path.read_bytes()).hexdigest()
        except OSError:
            return ""

    def _compute_source_mtime(self) -> float:
        """计算前端源码目录的最新修改时间。"""
        newest = 0.0
        candidates = [
            self._config.frontend_root / "src",
            self._config.frontend_root / "public",
        ]
        for directory in candidates:
            if not directory.exists():
                continue
            for path in directory.rglob("*"):
                if path.is_file():
                    try:
                        newest = max(newest, path.stat().st_mtime)
                    except OSError:
                        continue
        for filename in ("index.html", "vite.config.js", "package.json"):
            path = self._config.frontend_root / filename
            if path.exists():
                try:
                    newest = max(newest, path.stat().st_mtime)
                except OSError:
                    continue
        return newest

    def _compute_dist_mtime(self) -> float:
        """计算前端构建产物目录的最新修改时间。"""
        dist_dir = self._config.frontend_root / "dist"
        if not dist_dir.exists():
            return 0.0
        newest = 0.0
        for path in dist_dir.rglob("*"):
            if path.is_file():
                try:
                    newest = max(newest, path.stat().st_mtime)
                except OSError:
                    continue
        return newest

    def _should_install_dependencies(self) -> bool:
        """判断是否需要执行 npm install。"""
        if os.getenv("JARVIS_FORCE_FRONTEND_REBUILD", "").lower() in (
            "1",
            "true",
            "yes",
        ):
            return True
        if not (self._config.frontend_root / "node_modules").exists():
            return True
        current_hash = self._compute_lock_hash()
        if not current_hash:
            return True
        return self._load_build_state().get("lock_hash") != current_hash

    def _should_build(self) -> bool:
        """判断是否需要执行 npm run build。"""
        if os.getenv("JARVIS_FORCE_FRONTEND_REBUILD", "").lower() in (
            "1",
            "true",
            "yes",
        ):
            return True
        dist_mtime = self._compute_dist_mtime()
        if dist_mtime <= 0:
            return True
        return self._compute_source_mtime() > dist_mtime

    def _start_frontend_process(self) -> subprocess.Popen[bytes]:
        """启动前端服务。"""
        if self._config.dev_mode:
            PrettyOutput.auto_print("⏳ 启动前端开发服务（热加载模式）")
            command = [
                "npm",
                "run",
                "dev",
                "--",
                "--host",
                self._config.frontend_host,
                "--port",
                str(self._config.frontend_port),
            ]
        else:
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
        mode_name = "开发" if self._config.dev_mode else "发布"
        PrettyOutput.auto_print(f"✅ 前端{mode_name}服务已启动 (PID: {process.pid})")
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
        if processes.frontend_process is not None:
            self._terminate_process(processes.frontend_process, "前端服务")
        self._terminate_process(processes.gateway_process, "网关服务")

    def _stop_gateway_only(self, processes: ServiceProcesses) -> None:
        """只停止网关服务，保持前端运行。"""
        PrettyOutput.auto_print("🛑 正在停止网关服务")
        self._terminate_process(processes.gateway_process, "网关服务")

    def _stop_frontend_only(self, processes: ServiceProcesses) -> None:
        """只停止前端服务，保持网关运行。"""
        PrettyOutput.auto_print("🛑 正在停止前端服务")
        if processes.frontend_process is not None:
            self._terminate_process(processes.frontend_process, "前端服务")

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
        self, gateway_pid: int, frontend_pid: Optional[int]
    ) -> None:
        """打印启动结果摘要。"""
        PrettyOutput.auto_print(
            f"ℹ️ Gateway: http://{self._config.gateway_host}:{self._config.gateway_port} (PID: {gateway_pid})"
        )
        if frontend_pid is not None:
            PrettyOutput.auto_print(
                f"ℹ️ Frontend: http://{self._config.frontend_host}:{self._config.frontend_port} (PID: {frontend_pid})"
            )
        else:
            PrettyOutput.auto_print("ℹ️ Frontend: child 模式下未启动")
        PrettyOutput.auto_print(f"ℹ️ Node mode: {self._config.node_mode}")
        PrettyOutput.auto_print("ℹ️ 按 Ctrl+C 停止服务")


class _DeadProcess:
    """表示启动失败、已退出的占位进程，使主循环能立即感知并重试。"""

    pid = -1
    returncode = 1

    def poll(self) -> int:
        """始终返回已退出状态。"""
        return 1

    def terminate(self) -> None:
        """占位进程无需终止。"""

    def kill(self) -> None:
        """占位进程无需强杀。"""

    def wait(self, timeout: Optional[float] = None) -> int:
        """占位进程已退出，直接返回退出码。"""
        return 1
