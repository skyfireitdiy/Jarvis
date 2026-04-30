# -*- coding: utf-8 -*-
"""Jarvis service CLI。"""

import atexit
import os
import secrets
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, TextIO

import typer

from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_utils.utils import init_env

DEFAULT_GATEWAY_HOST = "127.0.0.1"
DEFAULT_GATEWAY_PORT = 8000
DEFAULT_FRONTEND_HOST = "127.0.0.1"
DEFAULT_FRONTEND_PORT = 5173
GATEWAY_READY_WAIT_SECONDS = 5
PROCESS_TERMINATE_TIMEOUT_SECONDS = 10
ROOT_MARKER_FILES = ("pyproject.toml",)
ROOT_MARKER_DIRECTORIES = ("src/jarvis",)
FRONTEND_RELATIVE_PATH = Path("src/jarvis/jarvis_service/frontend")
MASTER_NODE_SECRET_RELATIVE_PATH = Path("node_mode/master_node_secret")
AUTO_GENERATED_SECRET_NBYTES = 24

app = typer.Typer(help="Jarvis Service 服务")
SINGLE_INSTANCE_LOCK_HANDLE = None  # type: Optional[TextIO]

init_env("")


class LoopAction(Enum):
    """服务循环的控制动作。"""

    EXIT = "exit"
    RESTART = "restart"
    RESTART_GATEWAY_ONLY = "restart_gateway_only"


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
    node_mode: str
    node_id: Optional[str]
    master_url: Optional[str]
    node_secret: Optional[str]
    dev_mode: bool = False


@dataclass
class ServiceProcesses:
    """运行中的服务进程。"""

    gateway_process: subprocess.Popen[bytes]
    frontend_process: Optional[subprocess.Popen[bytes]]


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

    def request_restart_gateway_only(self, _signum: int, _frame: object) -> None:
        """接收到信号时只重启网关服务，保持前端运行。"""
        self._requested_action = LoopAction.RESTART_GATEWAY_ONLY
        self._signal_received = True

    def run_forever(self) -> None:
        """无限循环运行服务，直到收到退出信号。"""
        frontend_process: Optional[subprocess.Popen[bytes]] = None
        while True:
            self._signal_received = False
            self._requested_action = LoopAction.EXIT
            processes = self._start_services(frontend_process)
            next_action = self._wait_for_signal_or_process_exit(processes)

            if next_action == LoopAction.RESTART_GATEWAY_ONLY:
                # 只重启网关，保持前端运行
                PrettyOutput.auto_print("🔄 只重启网关服务，保持前端运行")
                frontend_process = processes.frontend_process
                self._stop_gateway_only(processes)
                continue

            # 完全停止所有服务
            frontend_process = None
            self._stop_services(processes)
            if next_action == LoopAction.EXIT:
                PrettyOutput.auto_print("🛑 服务已停止")
                return
            PrettyOutput.auto_print("🔄 接收到重启信号，正在重新启动服务")

    def _start_services(
        self, existing_frontend: Optional[subprocess.Popen[bytes]] = None
    ) -> ServiceProcesses:
        """按节点模式启动服务进程。

        Args:
            existing_frontend: 已存在的前端进程（只重启网关时使用）
        """
        self._validate_runtime_dependencies()

        if existing_frontend is not None:
            PrettyOutput.auto_print("🚀 重新启动网关服务（保持前端运行）")
        else:
            PrettyOutput.auto_print("🚀 启动 Jarvis 服务")
        PrettyOutput.auto_print(f"📁 项目根目录: {self._config.project_root}")

        gateway_process = self._start_gateway_process()
        self._wait_for_gateway_ready()

        frontend_process = existing_frontend
        if frontend_process is None and self._config.node_mode == "master":
            self._prepare_frontend_assets()
            frontend_process = self._start_frontend_process()

        self._print_service_summary(
            gateway_pid=gateway_process.pid,
            frontend_pid=frontend_process.pid if frontend_process else None,
        )
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
                PrettyOutput.auto_print("⚠️ 网关服务已退出，Jarvis Service 即将停止")
                return LoopAction.EXIT
            if (
                processes.frontend_process is not None
                and processes.frontend_process.poll() is not None
            ):
                PrettyOutput.auto_print("⚠️ 前端服务已退出，Jarvis Service 即将停止")
                return LoopAction.EXIT
            time.sleep(1)

    def _validate_runtime_dependencies(self) -> None:
        """校验运行时依赖命令。"""
        self._require_command("python", "未找到 Python 环境")
        self._require_command("jwg", "未找到 jwg 命令，请确保 Jarvis 已正确安装")
        if self._config.node_mode == "master":
            self._require_command("npm", "未找到 npm 环境")

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
        """安装依赖并构建前端产物。"""
        PrettyOutput.auto_print("⏳ 安装前端依赖")
        self._run_command(["npm", "install"], self._config.frontend_root)
        PrettyOutput.auto_print("✅ 前端依赖安装完成")
        if not self._config.dev_mode:
            PrettyOutput.auto_print("⏳ 构建前端发布产物")
            self._run_command(["npm", "run", "build"], self._config.frontend_root)
            PrettyOutput.auto_print("✅ 前端发布版本构建完成")
        else:
            PrettyOutput.auto_print("⏩ 开发模式跳过构建步骤")

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
    has_marker_files = all(
        (candidate_root / marker).exists() for marker in ROOT_MARKER_FILES
    )
    has_marker_directories = all(
        (candidate_root / marker).exists() for marker in ROOT_MARKER_DIRECTORIES
    )
    return has_marker_files and has_marker_directories


def get_master_node_secret_path() -> Path:
    """返回 master 节点密钥持久化文件路径。"""
    return Path(get_data_dir()) / MASTER_NODE_SECRET_RELATIVE_PATH


def load_or_create_master_node_secret() -> tuple[str, bool]:
    """读取或创建 master 节点密钥。"""
    secret_path = get_master_node_secret_path()
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    if secret_path.exists():
        existing_secret = secret_path.read_text(encoding="utf-8").strip()
        if existing_secret:
            return existing_secret, False
    generated_secret = secrets.token_urlsafe(AUTO_GENERATED_SECRET_NBYTES)
    secret_path.write_text(f"{generated_secret}\n", encoding="utf-8")
    try:
        os.chmod(secret_path, 0o600)
    except OSError:
        pass
    return generated_secret, True


def build_service_config(
    gateway_host: Optional[str] = None,
    gateway_port: Optional[int] = None,
    frontend_host: Optional[str] = None,
    frontend_port: Optional[int] = None,
    gateway_password: Optional[str] = None,
    node_mode: Optional[str] = None,
    node_id: Optional[str] = None,
    master_url: Optional[str] = None,
    node_secret: Optional[str] = None,
    dev_mode: bool = False,
) -> ServiceConfig:
    """根据命令行参数与环境变量构建服务配置。"""
    project_root = resolve_project_root()
    frontend_root = project_root / FRONTEND_RELATIVE_PATH
    resolved_gateway_host = gateway_host or os.getenv(
        "JARVIS_GATEWAY_HOST", DEFAULT_GATEWAY_HOST
    )
    resolved_gateway_port = gateway_port or int(
        os.getenv("JARVIS_GATEWAY_PORT", str(DEFAULT_GATEWAY_PORT))
    )
    resolved_frontend_host = frontend_host or os.getenv(
        "JARVIS_FRONTEND_HOST", DEFAULT_FRONTEND_HOST
    )
    resolved_frontend_port = frontend_port or int(
        os.getenv("JARVIS_FRONTEND_PORT", str(DEFAULT_FRONTEND_PORT))
    )
    resolved_gateway_password = (
        gateway_password or os.getenv("JARVIS_GATEWAY_PASSWORD") or None
    )
    resolved_node_mode = node_mode or os.getenv("JARVIS_NODE_MODE", "master")
    resolved_node_id = node_id or os.getenv("JARVIS_NODE_ID") or None
    resolved_master_url = master_url or os.getenv("JARVIS_MASTER_URL") or None
    resolved_node_secret = node_secret or os.getenv("JARVIS_NODE_SECRET") or None
    resolved_dev_mode = dev_mode or os.getenv("JARVIS_DEV_MODE", "false").lower() in (
        "true",
        "1",
        "yes",
    )

    if resolved_gateway_host is None:
        resolved_gateway_host = DEFAULT_GATEWAY_HOST
    if resolved_frontend_host is None:
        resolved_frontend_host = DEFAULT_FRONTEND_HOST
    if resolved_node_mode is None:
        resolved_node_mode = "master"
    if resolved_node_mode == "master" and not resolved_node_secret:
        resolved_node_secret, secret_created = load_or_create_master_node_secret()
        secret_path = get_master_node_secret_path()
        if secret_created:
            PrettyOutput.auto_print(
                "🔐 master 模式未传入 node-secret，已自动生成并保存"
            )
        else:
            PrettyOutput.auto_print(
                "🔐 master 模式未传入 node-secret，已加载已保存的密钥"
            )
        PrettyOutput.auto_print(f"🔑 node-secret: {resolved_node_secret}")
        PrettyOutput.auto_print(f"📄 密钥文件: {secret_path}")
    return ServiceConfig(
        project_root=project_root,
        frontend_root=frontend_root,
        gateway_host=resolved_gateway_host,
        gateway_port=resolved_gateway_port,
        frontend_host=resolved_frontend_host,
        frontend_port=resolved_frontend_port,
        gateway_password=resolved_gateway_password,
        node_mode=resolved_node_mode,
        node_id=resolved_node_id,
        master_url=resolved_master_url,
        node_secret=resolved_node_secret,
        dev_mode=resolved_dev_mode,
    )


def get_single_instance_lock_path() -> Path:
    """返回当前用户的服务实例锁文件路径。"""
    return Path(get_data_dir()) / f"jarvis-service-{os.getuid()}.lock"


def release_single_instance_lock() -> None:
    """释放当前用户的服务实例锁。"""
    global SINGLE_INSTANCE_LOCK_HANDLE
    if SINGLE_INSTANCE_LOCK_HANDLE is None:
        return
    SINGLE_INSTANCE_LOCK_HANDLE.close()
    SINGLE_INSTANCE_LOCK_HANDLE = None


def acquire_single_instance_lock() -> None:
    """获取当前用户的服务实例锁，若失败则退出。"""
    global SINGLE_INSTANCE_LOCK_HANDLE
    lock_file_path = get_single_instance_lock_path()
    lock_file_path.parent.mkdir(parents=True, exist_ok=True)
    lock_handle = open(lock_file_path, "w", encoding="utf-8")
    try:
        import fcntl

        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_handle.close()
        PrettyOutput.auto_print("❌ 当前用户已有 jarvis-service 实例正在运行")
        raise typer.Exit(code=1)
    service_pid = os.getpid()
    lock_handle.write(f"{service_pid}\n")
    lock_handle.flush()
    SINGLE_INSTANCE_LOCK_HANDLE = lock_handle
    atexit.register(release_single_instance_lock)


def run_service(config: ServiceConfig) -> None:
    """启动 Jarvis 服务循环。"""
    acquire_single_instance_lock()
    controller = ServiceController(config)
    signal.signal(signal.SIGINT, controller.request_exit)
    signal.signal(signal.SIGTERM, controller.request_exit)
    signal.signal(signal.SIGUSR1, controller.request_restart)
    signal.signal(signal.SIGUSR2, controller.request_restart_gateway_only)
    controller.run_forever()


@app.command(name="install")
def install_command(
    gateway_host: Optional[str] = typer.Option(
        None,
        "--gateway-host",
        help="Gateway 监听地址（默认可被 JARVIS_GATEWAY_HOST 覆盖）",
    ),
    gateway_port: Optional[int] = typer.Option(
        None,
        "--gateway-port",
        help="Gateway 监听端口（默认可被 JARVIS_GATEWAY_PORT 覆盖）",
    ),
    frontend_host: Optional[str] = typer.Option(
        None,
        "--frontend-host",
        help="前端预览服务监听地址（默认可被 JARVIS_FRONTEND_HOST 覆盖）",
    ),
    frontend_port: Optional[int] = typer.Option(
        None,
        "--frontend-port",
        help="前端预览服务监听端口（默认可被 JARVIS_FRONTEND_PORT 覆盖）",
    ),
    gateway_password: Optional[str] = typer.Option(
        None,
        "--gateway-password",
        help="Gateway 密码（默认可被 JARVIS_GATEWAY_PASSWORD 覆盖）",
    ),
    node_mode: Optional[str] = typer.Option(
        None,
        "--node-mode",
        help="节点模式：master 或 child（默认可被 JARVIS_NODE_MODE 覆盖）",
    ),
    node_id: Optional[str] = typer.Option(
        None,
        "--node-id",
        help="当前节点 ID（默认可被 JARVIS_NODE_ID 覆盖）",
    ),
    master_url: Optional[str] = typer.Option(
        None,
        "--master-url",
        help="主节点地址（child 模式使用，默认可被 JARVIS_MASTER_URL 覆盖）",
    ),
    node_secret: Optional[str] = typer.Option(
        None,
        "--node-secret",
        help="主子节点共享密钥（默认可被 JARVIS_NODE_SECRET 覆盖）",
    ),
) -> None:
    """安装 Jarvis Service 为 systemd 用户服务。"""
    config = build_service_config(
        gateway_host=gateway_host,
        gateway_port=gateway_port,
        frontend_host=frontend_host,
        frontend_port=frontend_port,
        gateway_password=gateway_password,
        node_mode=node_mode,
        node_id=node_id,
        master_url=master_url,
        node_secret=node_secret,
    )
    _install_systemd_service(config)


@app.command(name="start")
def start_command(
    gateway_host: Optional[str] = typer.Option(
        None,
        "--gateway-host",
        help="Gateway 监听地址（默认可被 JARVIS_GATEWAY_HOST 覆盖）",
    ),
    gateway_port: Optional[int] = typer.Option(
        None,
        "--gateway-port",
        help="Gateway 监听端口（默认可被 JARVIS_GATEWAY_PORT 覆盖）",
    ),
    frontend_host: Optional[str] = typer.Option(
        None,
        "--frontend-host",
        help="前端预览服务监听地址（默认可被 JARVIS_FRONTEND_HOST 覆盖）",
    ),
    frontend_port: Optional[int] = typer.Option(
        None,
        "--frontend-port",
        help="前端预览服务监听端口（默认可被 JARVIS_FRONTEND_PORT 覆盖）",
    ),
    gateway_password: Optional[str] = typer.Option(
        None,
        "--gateway-password",
        help="Gateway 密码（默认可被 JARVIS_GATEWAY_PASSWORD 覆盖）",
    ),
    node_mode: Optional[str] = typer.Option(
        None,
        "--node-mode",
        help="节点模式：master 或 child（默认可被 JARVIS_NODE_MODE 覆盖）",
    ),
    node_id: Optional[str] = typer.Option(
        None,
        "--node-id",
        help="当前节点 ID（默认可被 JARVIS_NODE_ID 覆盖）",
    ),
    master_url: Optional[str] = typer.Option(
        None,
        "--master-url",
        help="主节点地址（child 模式使用，默认可被 JARVIS_MASTER_URL 覆盖）",
    ),
    node_secret: Optional[str] = typer.Option(
        None,
        "--node-secret",
        help="主子节点共享密钥（默认可被 JARVIS_NODE_SECRET 覆盖）",
    ),
    dev_mode: bool = typer.Option(
        False,
        "--dev",
        help="开发模式：前端以 dev 模式启动（热加载）",
    ),
) -> None:
    """启动 Jarvis Service。"""
    config = build_service_config(
        gateway_host=gateway_host,
        gateway_port=gateway_port,
        frontend_host=frontend_host,
        frontend_port=frontend_port,
        gateway_password=gateway_password,
        node_mode=node_mode,
        node_id=node_id,
        master_url=master_url,
        node_secret=node_secret,
        dev_mode=dev_mode,
    )
    run_service(config)


def _install_systemd_service(config: ServiceConfig) -> None:
    """安装 Jarvis Service 为 systemd 用户服务。"""

    service_executable = shutil.which("jarvis-service")
    if service_executable is None:
        PrettyOutput.auto_print(
            "❌ 未找到 jarvis-service 可执行文件，请确保 Jarvis 已正确安装"
        )
        raise typer.Exit(code=1)

    # 构建服务文件内容
    current_path = os.environ.get("PATH", "")
    service_content = """[Unit]
Description=Jarvis Service
After=network.target

[Service]
Type=simple
Environment=PATH={path}
WorkingDirectory={project_root}
ExecStart={service_executable} start --gateway-host {gateway_host} --gateway-port {gateway_port} --frontend-host {frontend_host} --frontend-port {frontend_port}""".format(
        path=current_path,
        project_root=config.project_root,
        service_executable=service_executable,
        gateway_host=config.gateway_host,
        gateway_port=config.gateway_port,
        frontend_host=config.frontend_host,
        frontend_port=config.frontend_port,
    )

    # 添加可选参数
    if config.gateway_password:
        service_content += " --gateway-password {}".format(config.gateway_password)
    if config.node_mode:
        service_content += " --node-mode {}".format(config.node_mode)
    if config.node_id:
        service_content += " --node-id {}".format(config.node_id)
    if config.master_url:
        service_content += " --master-url {}".format(config.master_url)
    if config.node_secret:
        service_content += " --node-secret {}".format(config.node_secret)

    service_content += """
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
"""

    # 确定 systemd 用户目录
    systemd_user_dir = Path.home() / ".config" / "systemd" / "user"
    systemd_user_dir.mkdir(parents=True, exist_ok=True)

    # 写入服务文件
    service_file_path = systemd_user_dir / "jarvis-service.service"
    service_file_path.write_text(service_content, encoding="utf-8")

    PrettyOutput.auto_print(f"✅ systemd 服务文件已创建: {service_file_path}")

    # 启用 linger 模式，使服务在用户注销后继续运行
    try:
        import getpass

        username = getpass.getuser()

        # 检查是否已启用 linger
        result = subprocess.run(
            ["loginctl", "show-user", username, "--property=Linger"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        linger_enabled = False
        if result.returncode == 0:
            linger_enabled = "Linger=yes" in result.stdout

        if not linger_enabled:
            PrettyOutput.auto_print(
                "\n🔧 正在启用 linger 模式（使服务在用户注销后继续运行）..."
            )
            enable_result = subprocess.run(
                ["loginctl", "enable-linger", username],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if enable_result.returncode == 0:
                PrettyOutput.auto_print(
                    "✅ Linger 模式已启用，服务将在用户注销后继续运行"
                )
            else:
                PrettyOutput.auto_print(
                    f"⚠️  自动启用 linger 失败: {enable_result.stderr}"
                )
                PrettyOutput.auto_print(
                    f"💡 请手动执行: sudo loginctl enable-linger {username}"
                )
        else:
            PrettyOutput.auto_print("✅ Linger 模式已启用，服务将在用户注销后继续运行")
    except Exception as e:
        PrettyOutput.auto_print(f"⚠️  检查/启用 linger 时出错: {e}")
        PrettyOutput.auto_print("💡 服务可能需要在用户登录时运行，或手动启用 linger")

    PrettyOutput.auto_print("\n📋 服务管理命令:")
    PrettyOutput.auto_print("  systemctl --user daemon-reload")
    PrettyOutput.auto_print("  systemctl --user enable jarvis-service.service")
    PrettyOutput.auto_print("  systemctl --user start jarvis-service.service")
    PrettyOutput.auto_print("  systemctl --user status jarvis-service.service")


def main() -> None:
    """Compatible with old script entry, delegate to Typer app."""
    app()


if __name__ == "__main__":
    main()
