# -*- coding: utf-8 -*-
"""Jarvis service CLI。"""

import atexit
import os
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Optional

import typer

from jarvis.jarvis_service.service_backends import (  # noqa: F401
    ServiceBackend,
    WindowsTaskBackend,
    _detect_platform,
    create_backend,
)
from jarvis.jarvis_service.service_controller import (  # noqa: F401
    ServiceController,
)
from jarvis.jarvis_service.service_types import (  # noqa: F401
    LoopAction,
    ServiceConfig,
    ServiceProcesses,
    ServiceStatus,
)
from jarvis.jarvis_service.systemd_backend import SystemdBackend  # noqa: F401
from jarvis.jarvis_service.systemd_helpers import (  # noqa: F401
    _get_service_name,
    _run_systemctl_action,
    _run_systemctl_enable_disable,
)
from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_utils.utils import init_env


def validate_node_id(node_id: str) -> None:
    """验证 node_id 是否只包含 URL 安全字符（白名单方式）。

    使用白名单验证：只允许字母、数字、下划线、连字符和点号。
    空字符串视为无效输入。

    Args:
        node_id: 要验证的节点 ID

    Raises:
        ValueError: 当 node_id 为空或包含非法字符时
    """
    if not node_id:
        raise ValueError("node-id 不能为空")

    # 白名单：只允许字母、数字、下划线、连字符和点号
    import re

    if not re.match(r"^[a-zA-Z0-9_.\-]+$", node_id):
        raise ValueError(
            "node-id 包含非法字符。只允许字母、数字、下划线、连字符和点号。示例：node-001、worker.node_1"
        )


DEFAULT_GATEWAY_HOST = "127.0.0.1"
DEFAULT_GATEWAY_PORT = 8000
DEFAULT_FRONTEND_HOST = "127.0.0.1"
DEFAULT_FRONTEND_PORT = 5173
ROOT_MARKER_FILES = ("pyproject.toml",)
ROOT_MARKER_DIRECTORIES = ("src/jarvis",)
FRONTEND_RELATIVE_PATH = Path("src/jarvis/jarvis_service/frontend")
MASTER_NODE_SECRET_RELATIVE_PATH = Path("node_mode/master_node_secret")
AUTO_GENERATED_SECRET_NBYTES = 24

app = typer.Typer(help="Jarvis Service 服务")
SINGLE_INSTANCE_LOCK_HANDLE = None  # type: Optional[TextIO]

init_env("")


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


GATEWAY_TOKEN_RELATIVE_PATH = Path("gateway_token")
JWT_SECRET_RELATIVE_PATH = Path("jwt_secret")


def load_or_create_gateway_token() -> str:
    """读取或创建 Gateway Token（JARVIS_AUTH_TOKEN），持久化到 data 目录。

    供 jwg 子进程继承使用，保证网关重启后客户端 Token 仍有效。
    """
    path = Path(get_data_dir()) / GATEWAY_TOKEN_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    token = str(uuid.uuid4())
    path.write_text(f"{token}\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return token


def load_or_create_jwt_secret() -> str:
    """读取或创建 JWT 签名密钥（JARVIS_JWT_SECRET），持久化到 data 目录。

    供 jwg 子进程继承使用，保证网关重启后客户端 JWT Token 仍可验签。
    """
    path = Path(get_data_dir()) / JWT_SECRET_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    secret = secrets.token_urlsafe(AUTO_GENERATED_SECRET_NBYTES)
    path.write_text(f"{secret}\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return secret


def ensure_service_tokens() -> None:
    """在 service 进程内生成/加载并持久化 Token，写入环境变量供 jwg 子进程继承。

    若环境变量已显式设置（如用户手动配置），则优先尊重用户配置，不覆盖。
    """
    if not os.environ.get("JARVIS_AUTH_TOKEN"):
        os.environ["JARVIS_AUTH_TOKEN"] = load_or_create_gateway_token()
    if not os.environ.get("JARVIS_JWT_SECRET"):
        os.environ["JARVIS_JWT_SECRET"] = load_or_create_jwt_secret()


def build_service_config(
    gateway_host: Optional[str] = None,
    gateway_port: Optional[int] = None,
    frontend_host: Optional[str] = None,
    frontend_port: Optional[int] = None,
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
    resolved_node_mode = node_mode or os.getenv("JARVIS_NODE_MODE", "master")
    resolved_node_id = node_id or os.getenv("JARVIS_NODE_ID") or None
    # 验证 node_id 是否包含 URL 不安全字符
    if resolved_node_id:
        validate_node_id(resolved_node_id)
    resolved_master_url = master_url or os.getenv("JARVIS_MASTER_URL") or None
    resolved_node_secret = node_secret or os.getenv("JARVIS_NODE_SECRET") or None
    resolved_dev_mode = dev_mode or os.getenv("JARVIS_DEV_MODE", "false").lower() in (
        "true",
        "1",
        "yes",
    )

    if resolved_gateway_host is None:
        resolved_gateway_host = DEFAULT_GATEWAY_HOST
    # 子节点网关只允许监听回环地址：子节点本地无 auth 数据、不独立做权限判定，
    # 若绑定到非回环地址会把节点暴露为无认证入口。
    if resolved_node_mode == "child" and resolved_gateway_host not in (
        "127.0.0.1",
        "localhost",
        "::1",
    ):
        PrettyOutput.auto_print(
            f"⚠️ 子节点网关仅允许监听回环地址，已忽略 gateway-host={resolved_gateway_host}，"
            f"强制使用 {DEFAULT_GATEWAY_HOST}"
        )
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
        node_mode=resolved_node_mode,
        node_id=resolved_node_id,
        master_url=resolved_master_url,
        node_secret=resolved_node_secret,
        dev_mode=resolved_dev_mode,
    )


def get_single_instance_lock_path() -> Path:
    """返回当前用户的服务实例锁文件路径。"""
    if os.name == "nt":
        # Windows: use username instead of uid
        import getpass

        user_id = getpass.getuser()
    else:
        user_id = str(os.getuid())
    return Path(get_data_dir()) / f"jarvis-service-{user_id}.lock"


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
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(lock_handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError):
        lock_handle.close()
        PrettyOutput.auto_print("❌ 当前用户已有 jarvis-service 实例正在运行")
        raise typer.Exit(code=1)
    service_pid = os.getpid()
    lock_handle.write(f"{service_pid}\n")
    lock_handle.flush()
    SINGLE_INSTANCE_LOCK_HANDLE = lock_handle
    atexit.register(release_single_instance_lock)


# Windows 重启命令 TCP 端口（与 app.py / node_manager.py 中保持一致）
_RESTART_COMMAND_TCP_PORT = 18766


def _start_restart_command_server(controller: ServiceController) -> None:
    """Windows: 启动 TCP 命令服务器，接收重启命令。

    在守护线程中运行，监听 127.0.0.1:18766，接收以下命令：
    - RESTART_ALL: 触发完整重启（等价于 SIGUSR1）
    - RESTART_GATEWAY_ONLY: 仅重启网关（等价于 SIGUSR2）
    """
    import socket as _socket

    _stop_event = threading.Event()

    def _serve() -> None:
        server = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        server.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", _RESTART_COMMAND_TCP_PORT))
        server.listen(1)
        server.settimeout(1.0)  # 允许优雅退出
        try:
            while not _stop_event.is_set():
                try:
                    conn, _ = server.accept()
                    try:
                        data = conn.recv(1024).decode("utf-8").strip()
                        if data == "RESTART_ALL":
                            controller.request_restart(0, None)
                        elif data == "RESTART_GATEWAY_ONLY":
                            controller.request_restart_gateway_only(0, None)
                    finally:
                        conn.close()
                except _socket.timeout:
                    continue
                except OSError:
                    break
        finally:
            server.close()

    t = threading.Thread(target=_serve, daemon=True, name="restart-cmd-server")
    t.start()


def run_service(config: ServiceConfig) -> None:
    """启动 Jarvis 服务循环。"""
    acquire_single_instance_lock()
    # 在 service 进程内生成/加载并持久化 Token，写入环境变量供 jwg 子进程继承，
    # 保证网关重启后客户端 Token 仍有效。
    ensure_service_tokens()
    controller = ServiceController(config)
    signal.signal(signal.SIGINT, controller.request_exit)
    signal.signal(signal.SIGTERM, controller.request_exit)
    if sys.platform != "win32":
        signal.signal(signal.SIGUSR1, controller.request_restart)
        signal.signal(signal.SIGUSR2, controller.request_restart_gateway_only)
    else:
        # Windows: SIGUSR1/SIGUSR2 不可用，通过 TCP 命令通道触发重启
        _start_restart_command_server(controller)
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
        node_mode=node_mode,
        node_id=node_id,
        master_url=master_url,
        node_secret=node_secret,
    )
    _install_systemd_service(config)


@app.command(name="run")
def run_command(
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
    """直接运行 Jarvis Service（非systemd管理）。"""
    config = build_service_config(
        gateway_host=gateway_host,
        gateway_port=gateway_port,
        frontend_host=frontend_host,
        frontend_port=frontend_port,
        node_mode=node_mode,
        node_id=node_id,
        master_url=master_url,
        node_secret=node_secret,
        dev_mode=dev_mode,
    )
    run_service(config)


@app.command(name="start")
def start_service_command(
    mode: str = typer.Argument(
        ...,
        help="要启动的服务模式：master或child",
    ),
) -> None:
    """启动systemd管理的Jarvis服务。

    根据指定的模式启动对应的systemd服务（jarvis-master.service或jarvis-child.service），
    并自动启用（enable）该服务，同时禁用（disable）另一个模式的服务。
    """
    mode_lower = mode.lower()
    if mode_lower not in ["master", "child"]:
        PrettyOutput.auto_print(f"❌ 无效的模式: {mode}。请使用 'master' 或 'child'")
        raise typer.Exit(code=1)

    service_name = _get_service_name(mode_lower)
    PrettyOutput.auto_print(f"🚀 正在启动 {mode_lower} 服务: {service_name}")

    # 先执行daemon-reload确保systemd识别新创建或修改的服务文件
    try:
        subprocess.run(
            ["systemctl", "--user", "daemon-reload"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as e:
        PrettyOutput.auto_print(f"⚠ daemon-reload失败: {e}")

    # 启动服务
    if not _run_systemctl_action("start", mode_lower):
        PrettyOutput.auto_print(f"💡 请手动执行: systemctl --user start {service_name}")
        raise typer.Exit(code=1)

    PrettyOutput.auto_print(f"✅ {mode_lower} 服务已启动")

    # 启用当前服务
    PrettyOutput.auto_print(f"🔧 正在启用 {mode_lower} 服务...")
    if _run_systemctl_enable_disable("enable", mode_lower):
        PrettyOutput.auto_print(f"✅ {mode_lower} 服务已启用（开机自启）")
    else:
        PrettyOutput.auto_print(f"⚠ 启用{mode_lower}服务失败，但服务仍在运行")

    # 先停止另一个模式的服务（避免端口冲突或单实例锁）
    other_mode = "child" if mode_lower == "master" else "master"
    if _run_systemctl_action("is-active", other_mode):
        PrettyOutput.auto_print(f"🛑 正在停止 {other_mode} 服务...")
        if _run_systemctl_action("stop", other_mode):
            PrettyOutput.auto_print(f"✅ {other_mode} 服务已停止")
        else:
            PrettyOutput.auto_print(f"⚠ 停止{other_mode}服务失败")

    # 禁用另一个模式的服务
    PrettyOutput.auto_print(f"🔧 正在禁用 {other_mode} 服务...")
    if _run_systemctl_enable_disable("disable", other_mode):
        PrettyOutput.auto_print(f"✅ {other_mode} 服务已禁用")
    else:
        PrettyOutput.auto_print(f"⚠ 禁用{other_mode}服务失败")


@app.command(name="stop")
def stop_service_command(
    mode: str = typer.Argument(
        ...,
        help="要停止的服务模式：master或child",
    ),
) -> None:
    """停止systemd管理的Jarvis服务。

    根据指定的模式停止对应的systemd服务（jarvis-master.service或jarvis-child.service），
    并自动禁用（disable）该服务。
    """
    mode_lower = mode.lower()
    if mode_lower not in ["master", "child"]:
        PrettyOutput.auto_print(f"❌ 无效的模式: {mode}。请使用 'master' 或 'child'")
        raise typer.Exit(code=1)

    service_name = _get_service_name(mode_lower)
    PrettyOutput.auto_print(f"🛑 正在停止 {mode_lower} 服务: {service_name}")

    # 停止服务
    if not _run_systemctl_action("stop", mode_lower):
        PrettyOutput.auto_print(f"💡 请手动执行: systemctl --user stop {service_name}")
        raise typer.Exit(code=1)

    PrettyOutput.auto_print(f"✅ {mode_lower} 服务已停止")

    # 禁用服务
    PrettyOutput.auto_print(f"🔧 正在禁用 {mode_lower} 服务...")
    if _run_systemctl_enable_disable("disable", mode_lower):
        PrettyOutput.auto_print(f"✅ {mode_lower} 服务已禁用")
    else:
        PrettyOutput.auto_print(f"⚠ 禁用{mode_lower}服务失败，但服务已停止")


@app.command(name="switch")
def switch_service_command(
    target_mode: str = typer.Argument(
        ...,
        help="要切换到的目标模式：master或child",
    ),
) -> None:
    """切换Jarvis服务的运行模式。

    先停止当前运行的服务，然后启动目标模式的服务。确保不会同时运行master和child。
    切换时会自动启用（enable）目标服务并禁用（disable）另一个服务。
    """
    target_mode_lower = target_mode.lower()
    if target_mode_lower not in ["master", "child"]:
        PrettyOutput.auto_print(
            f"❌ 无效的目标模式: {target_mode}。请使用 'master' 或 'child'"
        )
        raise typer.Exit(code=1)

    # 检测当前运行的服务
    master_running = _run_systemctl_action("is-active", "master")
    child_running = _run_systemctl_action("is-active", "child")

    # 检查是否已经是目标模式
    if (target_mode_lower == "master" and master_running) or (
        target_mode_lower == "child" and child_running
    ):
        PrettyOutput.auto_print(f"ℹ️ 当前已经是 {target_mode_lower} 模式")
        return

    # 停止当前运行的服务
    stop_success = True
    if master_running and target_mode_lower == "child":
        PrettyOutput.auto_print("🛑 正在停止 master 服务...")
        if not _run_systemctl_action("stop", "master"):
            PrettyOutput.auto_print("❌ 停止 master 服务失败，无法继续切换")
            stop_success = False
    elif child_running and target_mode_lower == "master":
        PrettyOutput.auto_print("🛑 正在停止 child 服务...")
        if not _run_systemctl_action("stop", "child"):
            PrettyOutput.auto_print("❌ 停止 child 服务失败，无法继续切换")
            stop_success = False

    if not stop_success:
        raise typer.Exit(code=1)

    # 启动目标服务
    target_service_name = _get_service_name(target_mode_lower)
    PrettyOutput.auto_print(
        f"🚀 正在启动 {target_mode_lower} 服务: {target_service_name}"
    )

    if not _run_systemctl_action("start", target_mode_lower):
        PrettyOutput.auto_print(
            f"⚠ 启动失败，请手动执行: systemctl --user start {target_service_name}"
        )
        raise typer.Exit(code=1)

    PrettyOutput.auto_print(f"✅ 已切换到 {target_mode_lower} 模式")

    # 启用目标服务并禁用另一个服务
    PrettyOutput.auto_print(f"🔧 正在启用 {target_mode_lower} 服务...")
    if _run_systemctl_enable_disable("enable", target_mode_lower):
        PrettyOutput.auto_print(f"✅ {target_mode_lower} 服务已启用")
    else:
        PrettyOutput.auto_print(f"⚠ 启用{target_mode_lower}服务失败")

    # 禁用另一个模式的服务
    other_mode = "child" if target_mode_lower == "master" else "master"
    PrettyOutput.auto_print(f"🔧 正在禁用 {other_mode} 服务...")
    if _run_systemctl_enable_disable("disable", other_mode):
        PrettyOutput.auto_print(f"✅ {other_mode} 服务已禁用")
    else:
        PrettyOutput.auto_print(f"⚠ 禁用{other_mode}服务失败")


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

    # 收集代理相关的环境变量
    proxy_env_vars = []
    for var_name in [
        "http_proxy",
        "HTTP_PROXY",
        "https_proxy",
        "HTTPS_PROXY",
        "no_proxy",
        "NO_PROXY",
        "ftp_proxy",
        "FTP_PROXY",
        "socks_proxy",
        "SOCKS_PROXY",
    ]:
        value = os.environ.get(var_name)
        if value:
            proxy_env_vars.append(f"Environment={var_name}={value}")

    proxy_env_section = "\n".join(proxy_env_vars) if proxy_env_vars else ""

    # 根据node_mode确定服务文件名和描述
    service_name = _get_service_name(config.node_mode)
    mode_display = config.node_mode or "master"
    PrettyOutput.auto_print(f"📦 正在安装 {mode_display} 模式服务: {service_name}")

    service_content = """[Unit]
Description=Jarvis Service ({mode})
After=network.target

[Service]
Type=simple
Environment=PATH={path}
{proxy_env}
WorkingDirectory={project_root}
ExecStart={service_executable} run --gateway-host {gateway_host} --gateway-port {gateway_port} --frontend-host {frontend_host} --frontend-port {frontend_port}""".format(
        mode=mode_display,
        path=current_path,
        project_root=config.project_root,
        service_executable=service_executable,
        gateway_host=config.gateway_host,
        gateway_port=config.gateway_port,
        frontend_host=config.frontend_host,
        frontend_port=config.frontend_port,
        proxy_env=proxy_env_section,
    )

    # 添加可选参数
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
    service_file_path = systemd_user_dir / service_name
    service_file_path.write_text(service_content, encoding="utf-8")

    PrettyOutput.auto_print(f"✅ systemd 服务文件已创建: {service_file_path}")
    PrettyOutput.auto_print(f"💡 请使用 'jarvis-service start {mode_display}' 启动服务")

    # 仅在非 Windows 系统上显示 systemctl 命令提示
    if sys.platform != "win32":
        PrettyOutput.auto_print("📋 服务管理命令:")
        PrettyOutput.auto_print("  systemctl --user daemon-reload")
        PrettyOutput.auto_print(f"  systemctl --user enable {service_name}")
        PrettyOutput.auto_print(f"  systemctl --user start {service_name}")
        PrettyOutput.auto_print(f"  systemctl --user status {service_name}")

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
                "🔧 正在启用 linger 模式（使服务在用户注销后继续运行）..."
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

    PrettyOutput.auto_print("📋 jservice 管理命令:")
    PrettyOutput.auto_print("  jservice start")
    PrettyOutput.auto_print("  jservice stop")
    PrettyOutput.auto_print("  jservice status")
    PrettyOutput.auto_print("  jservice restart")


def main() -> None:
    """Compatible with old script entry, delegate to Typer app."""
    app()


if __name__ == "__main__":
    main()
