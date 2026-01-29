import atexit
import errno

# -*- coding: utf-8 -*-
import hashlib
import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import date
from datetime import datetime
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union

import yaml


from jarvis import __version__
from jarvis.jarvis_utils.config import (
    get_data_dir,
    get_max_input_token_count,
    set_llm_group,
)
from jarvis.jarvis_utils.config import set_global_config_data
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.globals import get_in_chat
from jarvis.jarvis_utils.globals import get_interrupt
from jarvis.jarvis_utils.globals import set_interrupt
from jarvis.jarvis_utils.output import PrettyOutput


# 向后兼容：导出 get_yes_no 供外部模块引用（延迟导入以避免循环依赖）
def get_yes_no(*args, **kwargs):
    from jarvis.jarvis_utils.input import user_confirm

    return user_confirm(*args, **kwargs)


def decode_output(data: bytes) -> str:
    """解码命令输出，自动尝试 UTF-8 和 GBK 编码

    Args:
        data: 字节类型的输出数据

    Returns:
        解码后的字符串
    """
    # 优先尝试 UTF-8（严格模式，失败时回退到其他编码）
    try:
        return data.decode("utf-8")
    except (UnicodeDecodeError, AttributeError):
        pass

    # 回退到 GBK（Windows 常用编码）
    try:
        return data.decode("gbk")
    except (UnicodeDecodeError, AttributeError):
        pass

    # 最后尝试 latin-1（不会失败，但可能有乱码）
    try:
        return data.decode("latin-1")
    except AttributeError:
        # 如果不是字节类型，转换为字符串
        return str(data)


g_config_file: Optional[str] = None

COMMAND_MAPPING = {
    # jarvis主命令
    "jvs": "jarvis",
    # 代码代理
    "jca": "jarvis-code-agent",
    # 智能shell
    "jss": "jarvis-smart-shell",
    # 平台管理
    "jpm": "jarvis-platform-manager",
    # Git提交
    "jgc": "jarvis-git-commit",
    # 代码审查
    "jcr": "jarvis-code-review",
    # Git压缩
    "jgs": "jarvis-git-squash",
    # 多代理
    "jma": "jarvis-multi-agent",
    # 代理
    "ja": "jarvis-agent",
    # 工具
    "jt": "jarvis-tool",
    # 方法论
    "jm": "jarvis-methodology",
    # 记忆整理
    "jmo": "jarvis-memory-organizer",
    # 安全分析
    "jsec": "jarvis-sec",
    # C2Rust迁移
    "jc2r": "jarvis-c2rust",
}


def is_editable_install() -> bool:
    """
    检测当前 Jarvis 是否以可编辑模式安装（pip/uv install -e .）。

    判断顺序（多策略并行，任意命中即认为是可编辑安装）：
    1. 读取 PEP 610 的 direct_url.json（dir_info.editable）
    2. 兼容旧式 .egg-link / .pth 可编辑安装
    3. 启发式回退：源码路径上游存在 .git 且不在 site-packages/dist-packages
    """
    # 优先使用 importlib.metadata 读取 distribution 的 direct_url.json
    try:
        import importlib.metadata as metadata  # Python 3.8+
    except Exception:
        # 如果importlib.metadata不可用，直接返回None，表示无法检查
        return False

    def _check_direct_url() -> Optional[bool]:
        candidates = ["jarvis-ai-assistant", "jarvis_ai_assistant"]
        for name in candidates:
            try:
                dist = metadata.distribution(name)
            except Exception:
                continue
            try:
                files = dist.files or []
                for f in files:
                    try:
                        if f.name == "direct_url.json":
                            p = Path(str(dist.locate_file(f)))
                            if p.exists():
                                with open(
                                    p, "r", encoding="utf-8", errors="ignore"
                                ) as fp:
                                    info = json.load(fp)
                                dir_info = info.get("dir_info") or {}
                                if isinstance(dir_info, dict) and bool(
                                    dir_info.get("editable")
                                ):
                                    return True
                                # 兼容部分工具可能写入顶层 editable 字段
                                if bool(info.get("editable")):
                                    return True
                                return False  # 找到了 direct_url.json 但未标记 editable
                    except Exception:
                        continue
            except Exception:
                continue
        return None

    res = _check_direct_url()
    if res is True:
        # 明确标记为 editable，直接返回 True
        return True
    # 对于 res 为 False/None 的情况，不直接下结论，继续使用后续多种兼容策略进行判断

    # 兼容旧式 .egg-link / .pth 可编辑安装
    try:
        module_path = Path(__file__).resolve()
        pkg_root = module_path.parent.parent  # jarvis 包根目录

        # 1) 基于 sys.path 的 .egg-link / .pth 检测（更贴近测试场景，依赖 os.path.exists）
        import os as _os

        for entry in sys.path:
            try:
                egg_link = Path(entry) / f"{pkg_root.name}.egg-link"
                pth_file = Path(entry) / f"{pkg_root.name}.pth"
                if _os.path.exists(str(egg_link)) or _os.path.exists(str(pth_file)):
                    return True
            except Exception:
                continue

        # 2) 兼容更通用的 .egg-link 形式（读取指向源码路径）
        for entry in sys.path:
            try:
                p = Path(entry)
                if not p.exists() or not p.is_dir():
                    continue
                for egg in p.glob("*.egg-link"):
                    try:
                        text = egg.read_text(encoding="utf-8", errors="ignore")
                        first_line = (text.strip().splitlines() or [""])[0]
                        if not first_line:
                            continue
                        src_path = Path(first_line).resolve()
                        # 当前包根目录在 egg-link 指向的源码路径下，视为可编辑安装
                        if str(pkg_root).startswith(str(src_path)):
                            return True
                    except Exception:
                        continue
            except Exception:
                continue
    except Exception:
        pass

    # 启发式回退：源码仓库路径
    try:
        parents = list(Path(__file__).resolve().parents)
        has_git = any((d / ".git").exists() for d in parents)
        in_site = any(
            ("site-packages" in str(d)) or ("dist-packages" in str(d)) for d in parents
        )
        if has_git and not in_site:
            return True
    except Exception:
        pass

    return False


def _setup_signal_handler() -> None:
    """设置SIGINT信号处理函数"""
    original_sigint = signal.getsignal(signal.SIGINT)

    def sigint_handler(signum: int, frame: Any) -> None:
        if get_in_chat():
            set_interrupt(True)
            if get_interrupt() > 5 and original_sigint and callable(original_sigint):
                original_sigint(signum, frame)
        else:
            if original_sigint and callable(original_sigint):
                original_sigint(signum, frame)

    signal.signal(signal.SIGINT, sigint_handler)


# ----------------------------
# 单实例文件锁（放置于初始化早期使用）
# ----------------------------
_INSTANCE_LOCK_PATH: Optional[Path] = None


def _get_instance_lock_path(lock_name: str = "instance.lock") -> Path:
    try:
        data_dir = Path(str(get_data_dir()))
    except Exception:
        data_dir = Path(os.path.expanduser("~/.jarvis"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / lock_name


def _read_lock_owner_pid(lock_path: Path) -> Optional[int]:
    try:
        txt = lock_path.read_text(encoding="utf-8", errors="ignore").strip()
        if not txt:
            return None
        try:
            info = json.loads(txt)
            pid = info.get("pid")
            return int(pid) if pid is not None else None
        except Exception:
            # 兼容纯数字PID
            return int(txt)
    except Exception:
        return None


def _is_process_alive(pid: int) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # 无权限但进程存在
        return True
    except OSError as e:
        # 某些平台上，EPERM 表示进程存在但无权限
        if getattr(e, "errno", None) == errno.EPERM:
            return True
        return False
    else:
        return True


def _release_instance_lock() -> None:
    global _INSTANCE_LOCK_PATH
    try:
        if _INSTANCE_LOCK_PATH and _INSTANCE_LOCK_PATH.exists():
            _INSTANCE_LOCK_PATH.unlink()
    except Exception:
        # 清理失败不影响退出
        pass
    _INSTANCE_LOCK_PATH = None


def _acquire_single_instance_lock(lock_name: str = "instance.lock") -> None:
    """
    在数据目录(~/.jarvis 或配置的数据目录)下创建实例锁，防止重复启动。
    如果检测到已有存活实例，提示后退出。
    """
    global _INSTANCE_LOCK_PATH
    lock_path = _get_instance_lock_path(lock_name)

    # 已存在锁：检查是否为有效存活实例
    if lock_path.exists():
        pid = _read_lock_owner_pid(lock_path)
        if pid and _is_process_alive(pid):
            PrettyOutput.auto_print(
                f"⚠️ 检测到已有一个 Jarvis 实例正在运行 (PID: {pid})。\n如果确认不存在正在运行的实例，请删除锁文件后重试：{lock_path}"
            )
            sys.exit(0)
        # 尝试移除陈旧锁
        try:
            lock_path.unlink()
        except Exception:
            PrettyOutput.auto_print(
                f"❌ 无法删除旧锁文件：{lock_path}，请手动清理后重试。"
            )
            sys.exit(1)

    # 原子创建锁文件，避免并发竞争
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(str(lock_path), flags)
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            payload = {
                "pid": os.getpid(),
                "time": int(time.time()),
                "argv": sys.argv[:10],
            }
            try:
                fp.write(json.dumps(payload, ensure_ascii=False))
            except Exception:
                fp.write(str(os.getpid()))
        _INSTANCE_LOCK_PATH = lock_path
        atexit.register(_release_instance_lock)
    except FileExistsError:
        # 极端并发下再次校验
        pid = _read_lock_owner_pid(lock_path)
        if pid and _is_process_alive(pid):
            PrettyOutput.auto_print(
                f"⚠️ 检测到已有一个 Jarvis 实例正在运行 (PID: {pid})。"
            )
            sys.exit(0)
        PrettyOutput.auto_print(
            f"❌ 锁文件已存在但可能为陈旧状态：{lock_path}，请手动删除后重试。"
        )
        sys.exit(1)
    except Exception as e:
        PrettyOutput.auto_print(f"❌ 创建实例锁失败: {e}")
        sys.exit(1)


def _is_installed_via_uv_tool() -> bool:
    """检测当前jarvis是否通过uv tool安装

    返回:
        bool: 如果是通过uv tool安装返回True
    """
    try:
        # 检查sys.argv[0]是否在典型的uv tool安装目录
        argv0_path = Path(sys.argv[0]).resolve()

        # uv tool安装的典型路径
        if sys.platform == "win32":
            uv_tool_dirs = [
                Path(os.environ.get("LOCALAPPDATA", "")) / "uv" / "bin",
                Path(os.environ.get("APPDATA", "")) / "uv" / "bin",
            ]
        else:
            uv_tool_dirs = [
                Path.home() / ".local" / "bin",
                Path.home() / ".local" / "share" / "uv" / "bin",
            ]

        # 检查是否在uv tool目录中
        for uv_dir in uv_tool_dirs:
            try:
                if uv_dir.exists() and argv0_path.is_relative_to(uv_dir):
                    # 进一步验证是否真的通过uv tool安装
                    from shutil import which as _which

                    uv_exe = _which("uv")
                    if uv_exe:
                        try:
                            # 执行uv tool list验证
                            result = subprocess.run(
                                [uv_exe, "tool", "list"],
                                capture_output=True,
                                timeout=10,
                                text=True,
                            )
                            if result.returncode == 0:
                                if "jarvis-ai-assistant" in result.stdout.lower():
                                    return True
                        except Exception:
                            pass
            except Exception:
                pass
    except Exception:
        pass
    return False


def _check_pip_updates() -> bool:
    """检查pip安装的Jarvis是否有更新

    返回:
        bool: 是否执行了更新（成功更新返回True以触发重启）
    """
    import urllib.error
    import urllib.request

    from packaging import version

    # 检查上次检查日期
    last_check_file = Path(str(get_data_dir())) / "last_pip_check"
    today_str = date.today().strftime("%Y-%m-%d")

    if last_check_file.exists():
        try:
            last_check_date = last_check_file.read_text().strip()
            if last_check_date == today_str:
                return False
        except Exception:
            pass

    try:
        # 获取PyPI上的最新版本
        url = "https://pypi.org/pypi/jarvis-ai-assistant/json"
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                data = json.loads(response.read().decode())
                latest_version = data["info"]["version"]
        except (urllib.error.URLError, KeyError, ValueError):
            return False

        # 比较版本
        current_ver = version.parse(__version__)
        latest_ver = version.parse(latest_version)

        if latest_ver > current_ver:
            PrettyOutput.auto_print(
                f"ℹ️ 检测到新版本 v{latest_version} (当前版本: v{__version__})"
            )

            # 检查是否为主版本升级(主版本号不同)
            is_major_upgrade = latest_ver.major != current_ver.major
            if is_major_upgrade:
                # 主版本升级可能包含不兼容变更,询问用户确认
                from jarvis.jarvis_utils.input import user_confirm

                PrettyOutput.auto_print(
                    f"⚠️ 主版本升级警告: v{current_ver} -> v{latest_ver}"
                )
                PrettyOutput.auto_print(
                    "主版本升级可能包含不兼容的API变更,建议查看发布说明。"
                )
                if not user_confirm("是否继续升级? (默认为升级)", default=True):
                    PrettyOutput.auto_print("ℹ️ 已取消升级,将在下次启动时再次检查更新。")
                    # 更新检查日期,避免重复提示
                    last_check_file.write_text(today_str)
                    return False

            # 检测是否通过uv tool安装
            is_uv_tool_install = _is_installed_via_uv_tool()

            if is_uv_tool_install:
                # 使用 uv tool upgrade 更新
                from shutil import which as _which

                uv_exe = _which("uv")
                if uv_exe:
                    # 注意：uv tool upgrade 不支持额外参数，只升级基础包
                    cmd_list = [uv_exe, "tool", "upgrade", "jarvis-ai-assistant"]
                    update_cmd = "uv tool upgrade jarvis-ai-assistant"
                else:
                    # 如果找不到uv，回退到pip方式
                    is_uv_tool_install = False

            if not is_uv_tool_install:
                # 检测是否在虚拟环境中
                hasattr(sys, "real_prefix") or (
                    hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
                )

                # 检测是否可用 uv（优先使用虚拟环境内的uv，其次PATH中的uv）
                from shutil import which as _which

                uv_executable: Optional[str] = None
                if sys.platform == "win32":
                    venv_uv = Path(sys.prefix) / "Scripts" / "uv.exe"
                else:
                    venv_uv = Path(sys.prefix) / "bin" / "uv"
                if venv_uv.exists():
                    uv_executable = str(venv_uv)
                else:
                    path_uv = _which("uv")
                    if path_uv:
                        uv_executable = path_uv

                # 更新命令
                package_spec = "jarvis-ai-assistant"
                if uv_executable:
                    cmd_list = [
                        uv_executable,
                        "pip",
                        "install",
                        "--upgrade",
                        package_spec,
                    ]
                    update_cmd = f"uv pip install --upgrade {package_spec}"
                else:
                    cmd_list = [
                        sys.executable,
                        "-m",
                        "pip",
                        "install",
                        "--upgrade",
                        package_spec,
                    ]
                    update_cmd = (
                        f"{sys.executable} -m pip install --upgrade {package_spec}"
                    )

            # 自动尝试升级（失败时提供手动命令）
            try:
                PrettyOutput.auto_print("ℹ️ 正在自动更新 Jarvis，请稍候...")
                result = subprocess.run(
                    cmd_list,
                    capture_output=True,
                    timeout=600,
                )
                if result.returncode == 0:
                    PrettyOutput.auto_print("✅ 更新成功，正在重启以应用新版本...")
                    # 更新检查日期，避免重复触发
                    last_check_file.write_text(today_str)
                    return True
                else:
                    err = (
                        decode_output(result.stderr)
                        or decode_output(result.stdout)
                        or ""
                    ).strip()
                    if err:
                        PrettyOutput.auto_print(
                            f"⚠️ 自动更新失败，错误信息（已截断）: {err[:500]}"
                        )
                    PrettyOutput.auto_print(f"ℹ️ 请手动执行以下命令更新: {update_cmd}")
            except Exception:
                PrettyOutput.auto_print("⚠️ 自动更新出现异常，已切换为手动更新方式。")
                PrettyOutput.auto_print(f"ℹ️ 请手动执行以下命令更新: {update_cmd}")

        # 更新检查日期
        last_check_file.write_text(today_str)

    except Exception:
        # 静默处理错误，不影响正常使用
        pass

    return False


def _check_jarvis_updates() -> bool:
    """检查并更新Jarvis本身（git仓库或pip包）

    返回:
        bool: 是否需要重启进程
    """
    # 从当前文件目录向上查找包含 .git 的仓库根目录，修复原先只检查 src/jarvis 的问题
    try:
        script_path = Path(__file__).resolve()
        repo_root: Optional[Path] = None
        for d in [script_path.parent] + list(script_path.parents):
            if (d / ".git").exists():
                repo_root = d
                break
    except Exception:
        repo_root = None

    # 先检查是否是git源码安装（找到仓库根目录即认为是源码安装）
    if repo_root and (repo_root / ".git").exists():
        from jarvis.jarvis_utils.git_utils import check_and_update_git_repo

        return check_and_update_git_repo(str(repo_root))

    # 检查是否是pip/uv pip安装的版本
    return _check_pip_updates()


def _show_usage_stats(welcome_str: str) -> None:
    """显示Jarvis欢迎信息

    参数:
        welcome_str: 欢迎信息字符串
    """
    try:
        from rich.console import Console
        from rich.console import Group
        from rich.panel import Panel
        from rich.text import Text
        from rich.align import Align

        console = Console()

        from jarvis.jarvis_utils.config import (
            get_cheap_model_name,
            get_cheap_platform_name,
            get_normal_model_name,
            get_normal_platform_name,
            get_smart_model_name,
            get_smart_platform_name,
            get_jarvis_github_url,
            get_jarvis_gitee_url,
        )
        import os

        # 欢迎信息 Panel
        if welcome_str:
            jarvis_ascii_art_str = """
   ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
   ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
   ██║███████║██████╔╝██║   ██║██║███████╗
██╗██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚████║██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚═══╝╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝"""

            # 获取模型信息和工作目录
            try:
                cheap_model = get_cheap_model_name()
                cheap_platform = get_cheap_platform_name()
                normal_model = get_normal_model_name()
                normal_platform = get_normal_platform_name()
                smart_model = get_smart_model_name()
                smart_platform = get_smart_platform_name()
                model_info = f"💰 {cheap_model}({cheap_platform})  ⭐ {normal_model}({normal_platform})  🧠 {smart_model}({smart_platform})"
            except Exception:
                model_info = "💰  未知  ⭐  未知  🧠  未知"

            work_dir = os.getcwd()
            work_dir_info = f"📁 工作目录: {work_dir}"

            # 获取仓库链接
            github_url = get_jarvis_github_url()
            gitee_url = get_jarvis_gitee_url()

            welcome_panel_content = Group(
                Align.center(Text(jarvis_ascii_art_str, style="bold blue")),
                Align.center(Text(welcome_str, style="bold")),
                "",  # for a blank line
                Align.center(Text(model_info, style="cyan")),
                Align.center(Text(work_dir_info, style="dim")),
                "",  # for a blank line
                Align.center(Text(f"🎯 v{__version__}", style="bold green")),
                "",  # for a blank line
                Align.center(
                    Text("🐙 GitHub: ", style="bold cyan")
                    + Text.from_markup(
                        f"[link={github_url}]{github_url}[/link]", style="cyan"
                    )
                ),
                Align.center(
                    Text("🎋 Gitee: ", style="bold cyan")
                    + Text.from_markup(
                        f"[link={gitee_url}]{gitee_url}[/link]", style="cyan"
                    )
                ),
            )

            # 计算panel宽度：max(2/3终端宽度，文字最大宽度)
            terminal_width = console.width
            # 渲染内容获取实际宽度（考虑多行情况）
            content_width = max(
                len(str(line)) for line in str(welcome_panel_content).split("\\n")
            )
            panel_width = max(terminal_width * 2 // 3, content_width)

            welcome_panel = Panel(
                welcome_panel_content,
                border_style="cyan",
                expand=False,
                width=panel_width,
            )
            console.print(Align.center(welcome_panel))
    except Exception:
        # 静默失败，不影响正常使用
        pass


def init_env(
    welcome_str: str = "",
    config_file: Optional[str] = None,
    llm_group: Optional[str] = None,
    auto_upgrade: bool = True,
) -> None:
    """初始化Jarvis环境

    参数:
        welcome_str: 欢迎信息字符串
        config_file: 配置文件路径，默认为None(使用~/.jarvis/config.yaml)
        llm_group: 模型组覆盖参数，用于显示用户指定的模型组
        auto_upgrade: 是否自动检查并升级Jarvis，默认为True
    """
    # 0. 检查是否处于Jarvis打开的终端环境，避免嵌套
    try:
        if os.environ.get("terminal") == "1":
            PrettyOutput.auto_print(
                "⚠️ 检测到当前终端由 Jarvis 打开。再次启动可能导致嵌套。"
            )
            from jarvis.jarvis_utils.input import user_confirm

            if not user_confirm("是否仍要继续启动 Jarvis？", default=False):
                PrettyOutput.auto_print("ℹ️ 已取消启动以避免终端嵌套。")
                sys.exit(0)
    except Exception:
        pass

    # 1. 设置信号处理
    try:
        _setup_signal_handler()
    except Exception:
        pass

    # 2. 统计命令使用（异步执行，避免阻塞初始化）
    try:
        count_cmd_usage()
    except Exception:
        # 静默失败，不影响正常使用
        pass

    # 3. 设置配置文件
    global g_config_file
    g_config_file = config_file
    try:
        load_config()
        # 设置默认的GitHub和Gitee链接配置，让所有工具都能访问
        from jarvis.jarvis_utils.config import (
            GLOBAL_CONFIG_DATA,
            set_config,
        )

        if not GLOBAL_CONFIG_DATA.get("jarvis_github_url"):
            set_config(
                "jarvis_github_url", "https://github.com/skyfireitdiy/Jarvis.git"
            )
        if not GLOBAL_CONFIG_DATA.get("jarvis_gitee_url"):
            set_config("jarvis_gitee_url", "https://gitee.com/skyfireitdiy/Jarvis.git")
    except Exception:
        # 静默失败，不影响正常使用
        pass

    set_llm_group(llm_group)

    # 4. 显示历史统计数据（仅在显示欢迎信息时显示）
    # 使用延迟加载，避免阻塞初始化
    if welcome_str:
        try:
            # 在后台线程中显示统计，避免阻塞主流程
            import threading

            def show_stats_async() -> None:
                try:
                    _show_usage_stats(welcome_str)
                except Exception:
                    pass

            stats_thread = threading.Thread(target=show_stats_async, daemon=True)
            stats_thread.start()
        except Exception:
            # 静默失败，不影响正常使用
            pass

    # 5. 检查Jarvis更新（异步执行，避免阻塞）
    if auto_upgrade:
        try:
            if _check_jarvis_updates():
                os.execv(sys.executable, [sys.executable] + sys.argv)
                sys.exit(0)
        except Exception:
            # 静默失败，不影响正常使用
            pass

    # 6. 设置tmux窗口平铺布局（统一管理）
    try:
        if "TMUX" in os.environ:
            # 在tmux环境中，设置当前窗口为平铺布局
            subprocess.run(
                ["tmux", "select-layout", "tiled"],
                check=True,
                timeout=5,
            )
    except Exception:
        # 静默失败，不影响正常使用
        pass

    # 7. 确保规则说明文件存在
    try:
        from jarvis.jarvis_utils.config import get_data_dir
        from pathlib import Path

        jarvis_data_dir = Path(get_data_dir())
        rule_file = jarvis_data_dir / "rule"

        if not rule_file.exists():
            # 从源码目录拷贝规则说明文件
            src_rule_file = Path(__file__).parent.parent / "jarvis_data" / "rule"
            if src_rule_file.exists():
                import shutil

                jarvis_data_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_rule_file, rule_file)
    except Exception:
        # 静默失败，不影响正常使用
        pass


def _interactive_config_setup(config_file_path: Path) -> None:
    """交互式配置引导

    直接调用 jqc 命令进行快速配置。
    """
    PrettyOutput.auto_print("ℹ️ 欢迎使用 Jarvis！正在启动快速配置程序...")

    try:
        # 构建 jqc 命令
        cmd = ["jqc", "--output", str(config_file_path)]

        # 直接调用 jqc 命令
        subprocess.run(cmd)
        sys.exit(0)
    except Exception as e:
        PrettyOutput.auto_print(f"❌ 启动配置程序失败: {e}")
        sys.exit(1)


def load_config() -> None:
    config_file = g_config_file

    # 如果用户显式指定了配置文件，仍然只加载该文件（向后兼容）
    if config_file is not None:
        config_file_path = Path(config_file)
        if not config_file_path.exists():
            old_config_file = config_file_path.parent / "env"
            if old_config_file.exists():  # 旧的配置文件存在
                _read_old_config_file(old_config_file)
            else:
                _interactive_config_setup(config_file_path)
        else:
            _load_and_process_config(
                str(config_file_path.parent), str(config_file_path)
            )
    else:
        # 从当前目录开始逐层向上查找所有 .jarvis/config.yaml 文件
        config_files = _find_all_config_files(os.getcwd())

        if not config_files:
            # 如果没有找到任何配置文件，使用默认路径
            config_file_path = Path(os.path.expanduser("~/.jarvis/config.yaml"))
            if not config_file_path.exists():
                old_config_file = config_file_path.parent / "env"
                if old_config_file.exists():  # 旧的配置文件存在
                    _read_old_config_file(old_config_file)
                else:
                    _interactive_config_setup(config_file_path)
            else:
                _load_and_process_config(
                    str(config_file_path.parent), str(config_file_path)
                )
        elif len(config_files) == 1:
            # 只找到一个配置文件，直接加载
            config_file_path = Path(config_files[0])
            _load_and_process_config(
                str(config_file_path.parent), str(config_file_path)
            )
        else:
            # 找到多个配置文件，合并配置（底层覆盖上层）
            content, merged_config = _merge_configs(config_files)
            # 使用最底层的配置文件（最后一个）作为主配置文件
            main_config_file = config_files[-1]
            main_config_dir = str(Path(main_config_file).parent)

            try:
                _ensure_schema_declaration(
                    main_config_dir, main_config_file, content, merged_config
                )
                set_global_config_data(merged_config)
                _process_env_variables(merged_config)
            except Exception:
                from jarvis.jarvis_utils.input import user_confirm as get_yes_no

                PrettyOutput.auto_print("❌ 加载配置文件失败")
                if get_yes_no("配置文件格式错误，是否删除并重新配置？"):
                    try:
                        os.remove(main_config_file)
                        PrettyOutput.auto_print(
                            "✅ 已删除损坏的配置文件，请重启Jarvis以重新配置。"
                        )
                    except Exception:
                        PrettyOutput.auto_print("❌ 删除配置文件失败")
                sys.exit(1)


def _find_all_config_files(start_dir: str) -> List[str]:
    """从指定目录开始逐层向上查找所有 .jarvis/config.yaml 文件

    参数:
        start_dir: 起始目录路径

    返回:
        List[str]: 按从上层到下层顺序排列的配置文件路径列表
    """
    config_files = []
    current_dir = Path(start_dir).resolve()
    root_dir = Path("/").resolve()
    max_levels = 20  # 最多向上查找20层，防止无限循环
    level = 0

    while current_dir != root_dir and level < max_levels:
        config_path = current_dir / ".jarvis" / "config.yaml"
        if config_path.exists():
            config_files.append(str(config_path))
        current_dir = current_dir.parent
        level += 1

    # 检查根目录
    config_path = root_dir / ".jarvis" / "config.yaml"
    if config_path.exists():
        config_files.append(str(config_path))

    # 反转列表，使得上层配置在前，下层配置在后
    config_files.reverse()
    return config_files


def _merge_configs(config_files: List[str]) -> Tuple[str, Dict[str, Any]]:
    """按顺序加载多个配置文件并合并（底层覆盖上层）

    参数:
        config_files: 配置文件路径列表（从上层到下层）

    返回:
        Tuple[str, dict]: (最后一个配置文件的原始内容, 合并后的配置字典)
    """
    merged_config = {}
    last_content = ""

    for config_file in config_files:
        content, config_data = _load_config_file(config_file)
        if isinstance(config_data, dict):
            merged_config.update(config_data)
        last_content = content  # 保存最后一个配置文件的内容

    return last_content, merged_config


def _load_config_file(config_file: str) -> Tuple[str, Dict[str, Any]]:
    """读取并解析YAML格式的配置文件

    参数:
        config_file: 配置文件路径

    返回:
        Tuple[str, dict]: (文件原始内容, 解析后的配置字典)
    """
    with open(config_file, "r", encoding="utf-8") as f:
        content = f.read()
        config_data = yaml.safe_load(content) or {}
        return content, config_data


def _ensure_schema_declaration(
    jarvis_dir: str, config_file: str, content: str, config_data: Dict[str, Any]
) -> None:
    """确保配置文件包含schema声明

    参数:
        jarvis_dir: Jarvis数据目录路径
        config_file: 配置文件路径
        content: 配置文件原始内容
        config_data: 解析后的配置字典
    """
    if (
        isinstance(config_data, dict)
        and "# yaml-language-server: $schema=" not in content
    ):
        schema_path = Path(
            os.path.relpath(
                Path(__file__).parent.parent / "jarvis_data" / "config_schema.json",
                start=jarvis_dir,
            )
        )
        with open(config_file, "w", encoding="utf-8") as f:
            f.write(f"# yaml-language-server: $schema={schema_path}\n")
            f.write(content)


def _process_env_variables(config_data: Dict[str, Any]) -> None:
    """处理配置中的环境变量

    参数:
        config_data: 解析后的配置字典
    """
    if "ENV" in config_data and isinstance(config_data["ENV"], dict):
        os.environ.update(
            {str(k): str(v) for k, v in config_data["ENV"].items() if v is not None}
        )


def _load_and_process_config(jarvis_dir: str, config_file: str) -> None:
    """加载并处理配置文件

    功能：
    1. 读取配置文件
    2. 确保schema声明存在
    3. 保存配置到全局变量
    4. 处理环境变量

    参数:
        jarvis_dir: Jarvis数据目录路径
        config_file: 配置文件路径
    """
    from jarvis.jarvis_utils.input import user_confirm as get_yes_no

    try:
        content, config_data = _load_config_file(config_file)
        _ensure_schema_declaration(jarvis_dir, config_file, content, config_data)
        set_global_config_data(config_data)
        _process_env_variables(config_data)
    except Exception:
        PrettyOutput.auto_print("❌ 加载配置文件失败")
        if get_yes_no("配置文件格式错误，是否删除并重新配置？"):
            try:
                os.remove(config_file)
                PrettyOutput.auto_print(
                    "✅ 已删除损坏的配置文件，请重启Jarvis以重新配置。"
                )
            except Exception:
                PrettyOutput.auto_print("❌ 删除配置文件失败")
        sys.exit(1)


def generate_default_config(schema_path: str, output_path: str) -> None:
    """从schema文件生成默认的YAML格式配置文件

    功能：
    1. 从schema文件读取配置结构
    2. 根据schema中的default值生成默认配置
    3. 自动添加schema声明
    4. 处理嵌套的schema结构
    5. 保留注释和格式

    参数:
        schema_path: schema文件路径
        output_path: 生成的配置文件路径
    """
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    def _generate_from_schema(schema_dict: Dict[str, Any]) -> Dict[str, Any]:
        config = {}
        if "properties" in schema_dict:
            for key, value in schema_dict["properties"].items():
                if "default" in value:
                    config[key] = value["default"]
                elif "properties" in value:  # 处理嵌套对象
                    config[key] = _generate_from_schema(value)
                elif value.get("type") == "array":  # 处理列表类型
                    config[key] = []
        return config

    default_config = _generate_from_schema(schema)

    content = f"# yaml-language-server: $schema={schema_path}\n"
    content += yaml.dump(default_config, allow_unicode=True, sort_keys=False)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)


def _load_default_config_from_schema() -> Dict[str, Any]:
    """从 schema 生成默认配置字典，用于对比并剔除等于默认值的键"""
    try:
        schema_path = (
            Path(__file__).parent.parent / "jarvis_data" / "config_schema.json"
        )
        if not schema_path.exists():
            return {}
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)

        def _generate_from_schema(schema_dict: Dict[str, Any]) -> Dict[str, Any]:
            cfg: Dict[str, Any] = {}
            if isinstance(schema_dict, dict) and "properties" in schema_dict:
                for key, value in schema_dict["properties"].items():
                    if "default" in value:
                        cfg[key] = value["default"]
                    elif value.get("type") == "array":
                        cfg[key] = []
                    elif "properties" in value:
                        cfg[key] = _generate_from_schema(value)
            return cfg

        return _generate_from_schema(schema)
    except Exception:
        return {}


def _prune_defaults_with_schema(config_data: Dict[str, Any]) -> bool:
    """
    删除与 schema 默认值一致的配置项，返回是否发生了变更
    仅处理 schema 中定义的键，未在 schema 中的键不会被修改
    """
    defaults = _load_default_config_from_schema()
    if not defaults or not isinstance(config_data, dict):
        return False

    changed = False

    def _prune_node(node: Dict[str, Any], default_node: Dict[str, Any]) -> None:
        nonlocal changed
        for key in list(node.keys()):
            if key in default_node:
                dv = default_node[key]
                v = node[key]
                if isinstance(dv, dict) and isinstance(v, dict):
                    _prune_node(v, dv)
                    if not v:
                        del node[key]
                        changed = True
                elif isinstance(dv, list) and isinstance(v, list):
                    if v == dv:
                        del node[key]
                        changed = True
                else:
                    if v == dv:
                        del node[key]
                        changed = True

    _prune_node(config_data, defaults)
    return changed


def _read_old_config_file(config_file: Union[str, Path]) -> None:
    """读取并解析旧格式的env配置文件

    功能：
    1. 解析键值对格式的旧配置文件
    2. 支持多行值的处理
    3. 自动去除值的引号和空格
    4. 将配置数据保存到全局变量
    5. 设置环境变量并显示迁移警告

    参数:
        config_file: 旧格式配置文件路径
    """
    config_data = {}
    current_key = None
    current_value = []
    with open(config_file, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.rstrip()
            if not line or line.startswith(("#", ";")):
                continue
            if "=" in line and not line.startswith((" ", "\t")):
                # 处理之前收集的多行值
                if current_key is not None:
                    processed_value = (
                        "\n".join(current_value).strip().strip("'").strip('"')
                    )
                    # 将字符串"true"/"false"转换为bool类型
                    if processed_value.lower() == "true":
                        final_value = True
                    elif processed_value.lower() == "false":
                        final_value = False
                    else:
                        final_value = processed_value  # type: ignore[assignment]
                    config_data[current_key] = final_value
                    current_value = []
                    # 解析新的键值对
                key_part, value_part = line.split("=", 1)
                current_key = key_part.strip()
                current_value.append(value_part.strip())
            elif current_key is not None:
                # 多行值的后续行
                current_value.append(line.strip())
                # 处理最后一个键值对
        if current_key is not None:
            processed_value = "\n".join(current_value).strip().strip("'").strip('"')
            # 将字符串"true"/"false"转换为bool类型
            if processed_value.lower() == "true":
                final_value = True
            elif processed_value.lower() == "false":
                final_value = False
            else:
                final_value = processed_value  # type: ignore[assignment]
            config_data[current_key] = final_value
        os.environ.update(
            {str(k): str(v) for k, v in config_data.items() if v is not None}
        )
        set_global_config_data(config_data)
    PrettyOutput.auto_print(
        "⚠️ 检测到旧格式配置文件，旧格式以后将不再支持，请尽快迁移到新格式"
    )


# 线程本地存储，用于共享重试计数器
_retry_context = threading.local()

# 独立的线程本地存储，用于 while_success 的重试计数器
_retry_context_success = threading.local()

# 独立的线程本地存储，用于 while_true 的重试计数器
_retry_context_true = threading.local()


def _get_retry_count() -> int:
    """获取当前线程的重试计数（已废弃，保留向后兼容）"""
    if not hasattr(_retry_context, "count"):
        _retry_context.count = 0
    return int(_retry_context.count)


def _increment_retry_count() -> int:
    """增加重试计数并返回新的计数值（已废弃，保留向后兼容）"""
    if not hasattr(_retry_context, "count"):
        _retry_context.count = 0
    _retry_context.count += 1
    return int(_retry_context.count)


def _reset_retry_count() -> None:
    """重置重试计数（已废弃，保留向后兼容）"""
    _retry_context.count = 0


# while_success 专用的计数器函数
def _get_retry_count_success() -> int:
    """获取当前线程的 while_success 重试计数"""
    if not hasattr(_retry_context_success, "count"):
        _retry_context_success.count = 0
    return int(_retry_context_success.count)


def _increment_retry_count_success() -> int:
    """增加 while_success 重试计数并返回新的计数值"""
    if not hasattr(_retry_context_success, "count"):
        _retry_context_success.count = 0
    _retry_context_success.count += 1
    return int(_retry_context_success.count)


def _reset_retry_count_success() -> None:
    """重置 while_success 重试计数"""
    _retry_context_success.count = 0


# while_true 专用的计数器函数
def _get_retry_count_true() -> int:
    """获取当前线程的 while_true 重试计数"""
    if not hasattr(_retry_context_true, "count"):
        _retry_context_true.count = 0
    return int(_retry_context_true.count)


def _increment_retry_count_true() -> int:
    """增加 while_true 重试计数并返回新的计数值"""
    if not hasattr(_retry_context_true, "count"):
        _retry_context_true.count = 0
    _retry_context_true.count += 1
    return int(_retry_context_true.count)


def _reset_retry_count_true() -> None:
    """重置 while_true 重试计数"""
    _retry_context_true.count = 0


def while_success(func: Callable[[], Any]) -> Any:
    """循环执行函数直到成功（累计日志后统一打印，避免逐次加框）

    参数：
    func -- 要执行的函数

    返回：
    函数执行结果

    注意：
    使用独立的重试计数器，累计重试6次，使用指数退避（第一次等待1s）
    """
    MAX_RETRIES = 6
    result: Any = None

    while True:
        # 检测中断信号，如果中断则直接返回（不清除中断标志）
        if get_interrupt() > 0:
            return None
        try:
            result = func()
            _reset_retry_count_success()  # 成功后重置计数器
            break
        except Exception as e:
            retry_count = _increment_retry_count_success()
            if retry_count <= MAX_RETRIES:
                # 指数退避：第1次等待1s (2^0)，第2次等待2s (2^1)，第3次等待4s (2^2)，第4次等待8s (2^3)，第6次等待32s (2^5)
                sleep_time = 2 ** (retry_count - 1)
                if retry_count < MAX_RETRIES:
                    PrettyOutput.auto_print(
                        f"⚠️ 发生异常:\n{e}\n重试中 ({retry_count}/{MAX_RETRIES})，等待 {sleep_time}s..."
                    )
                    time.sleep(sleep_time)
                else:
                    PrettyOutput.auto_print(
                        f"⚠️ 发生异常:\n{e}\n已达到最大重试次数 ({retry_count}/{MAX_RETRIES})"
                    )
                    _reset_retry_count_success()
                    raise
            else:
                _reset_retry_count_success()
                raise
    return result


def while_true(func: Callable[[], bool]) -> Any:
    """循环执行函数直到返回True（累计日志后统一打印，避免逐次加框）

    参数:
        func: 要执行的函数，必须返回布尔值

    返回:
        函数最终返回的True值

    注意:
        与while_success不同，此函数只检查返回是否为True，
        不捕获异常，异常会直接抛出。
        使用独立的重试计数器，累计重试6次，使用指数退避（第一次等待1s）
    """
    MAX_RETRIES = 6
    ret: bool = False

    while True:
        # 检测中断信号，如果中断则直接返回（不清除中断标志）
        if get_interrupt() > 0:
            return False
        try:
            ret = func()
            if ret:
                _reset_retry_count_true()  # 成功后重置计数器
                break
        except Exception:
            # 异常直接抛出，不捕获
            _reset_retry_count_true()
            raise

        retry_count = _increment_retry_count_true()
        if retry_count <= MAX_RETRIES:
            # 指数退避：第1次等待1s (2^0)，第2次等待2s (2^1)，第3次等待4s (2^2)，第4次等待8s (2^3)，第6次等待32s (2^5)
            sleep_time = 2 ** (retry_count - 1)
            if retry_count < MAX_RETRIES:
                PrettyOutput.auto_print(
                    f"⚠️ 返回空值，重试中 ({retry_count}/{MAX_RETRIES})，等待 {sleep_time}s..."
                )
                time.sleep(sleep_time)
            else:
                PrettyOutput.auto_print(
                    f"⚠️ 返回空值，已达到最大重试次数 ({retry_count}/{MAX_RETRIES})"
                )
                _reset_retry_count_true()
                break
        else:
            _reset_retry_count_true()
            break
    return ret


def get_file_md5(filepath: str) -> str:
    """计算文件内容的MD5哈希值

    参数:
        filepath: 要计算哈希的文件路径

    返回:
        str: 文件内容的MD5哈希值（为降低内存占用，仅读取前100MB进行计算）
    """
    # 采用流式读取，避免一次性加载100MB到内存
    h = hashlib.md5()
    max_bytes = 100 * 1024 * 1024  # 与原实现保持一致：仅读取前100MB
    buf_size = 8 * 1024 * 1024  # 8MB缓冲
    read_bytes = 0
    with open(filepath, "rb") as f:
        while read_bytes < max_bytes:
            to_read = min(buf_size, max_bytes - read_bytes)
            chunk = f.read(to_read)
            if not chunk:
                break
            h.update(chunk)
            read_bytes += len(chunk)
    return h.hexdigest()


def get_file_line_count(filename: str) -> int:
    """计算文件中的行数

    参数:
        filename: 要计算行数的文件路径

    返回:
        int: 文件中的行数，如果文件无法读取则返回0
    """
    try:
        # 使用流式逐行计数，避免将整个文件读入内存
        with open(filename, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def count_cmd_usage() -> None:
    """统计当前命令的使用次数（已废弃，保留函数以兼容旧代码）"""
    # jarvis-stats 功能已移除，此函数不再执行任何操作
    pass


def is_context_overflow(
    content: str,
    platform: Optional[Any] = None,
) -> bool:
    """判断文件内容是否超出上下文限制

    参数:
        content: 要检查的内容
        platform: 平台实例（可选），如果提供则使用剩余token数量判断

    返回:
        bool: 如果内容超出上下文限制返回True
    """
    # 快速长度预估：如果内容长度明显超过限制，直接返回True，无需精确计算token
    if content:
        # 粗略估算：假设平均每个token约4个字符，保守估计使用3.5个字符/token
        estimated_tokens = len(content) // 3.5

        # 获取最大token限制
        max_tokens = get_max_input_token_count()

        # 如果预估token数超过限制的150%，直接认为超出（避免精确计算）
        if estimated_tokens > max_tokens * 1.5:
            return True

        # 如果预估token数小于限制的50%，直接认为安全
        if estimated_tokens < max_tokens * 0.5:
            return False

    # 只有在预估结果不明确时，才进行精确的token计算
    content_tokens = get_context_token_count(content)

    # 优先使用剩余token数量
    if platform is not None:
        try:
            remaining_tokens = platform.get_remaining_token_count()
            # 如果内容token数超过剩余token的80%，认为超出限制
            threshold = int(remaining_tokens * 0.8)
            if threshold > 0:
                return content_tokens > threshold
        except Exception:
            pass

    # 回退方案：使用输入窗口限制
    return content_tokens > get_max_input_token_count()


def get_loc_stats() -> str:
    """使用loc命令获取当前目录的代码统计信息

    返回:
        str: loc命令输出的原始字符串，失败时返回空字符串
    """
    try:
        result = subprocess.run(["loc"], capture_output=True)
        return decode_output(result.stdout) if result.returncode == 0 else ""
    except FileNotFoundError:
        return ""


def _pull_git_repo(repo_path: Path, repo_type: str) -> None:
    """对指定的git仓库执行git pull操作，并根据commit hash判断是否有更新。"""
    git_dir = repo_path / ".git"
    if not git_dir.is_dir():
        return

    try:
        # 检查是否有远程仓库
        remote_result = subprocess.run(
            ["git", "remote"],
            cwd=repo_path,
            capture_output=True,
            check=True,
            timeout=10,
        )
        if not decode_output(remote_result.stdout).strip():
            return

        # 检查git仓库状态
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_path,
            capture_output=True,
            check=True,
            timeout=10,
        )
        if decode_output(status_result.stdout):
            from jarvis.jarvis_utils.input import user_confirm

            if user_confirm(
                f"检测到 '{repo_path.name}' 存在未提交的更改，是否放弃这些更改并更新？"
            ):
                try:
                    subprocess.run(
                        ["git", "checkout", "."],
                        cwd=repo_path,
                        capture_output=True,
                        check=True,
                        timeout=10,
                    )
                except (
                    subprocess.CalledProcessError,
                    subprocess.TimeoutExpired,
                    FileNotFoundError,
                ) as e:
                    PrettyOutput.auto_print(
                        f"❌ 放弃 '{repo_path.name}' 的更改失败: {str(e)}"
                    )
                    return
            else:
                PrettyOutput.auto_print(
                    f"ℹ️ 跳过更新 '{repo_path.name}' 以保留未提交的更改。"
                )
                return

        # 获取更新前的commit hash
        before_hash_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            check=True,
            timeout=10,
        )
        before_hash = decode_output(before_hash_result.stdout).strip()

        # 检查是否是空仓库
        ls_remote_result = subprocess.run(
            ["git", "ls-remote", "--heads", "origin"],
            cwd=repo_path,
            capture_output=True,
            check=True,
            timeout=10,
        )

        if not decode_output(ls_remote_result.stdout).strip():
            return

        # 执行 git pull
        subprocess.run(
            ["git", "pull"],
            cwd=repo_path,
            capture_output=True,
            check=True,
            timeout=60,
        )

        # 获取更新后的commit hash
        after_hash_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            check=True,
            timeout=10,
        )
        after_hash = decode_output(after_hash_result.stdout).strip()

        if before_hash != after_hash:
            PrettyOutput.auto_print(f"✅ {repo_type}库 '{repo_path.name}' 已更新。")

    except FileNotFoundError:
        PrettyOutput.auto_print(f"⚠️ git 命令未找到，跳过更新 '{repo_path.name}'。")
    except subprocess.TimeoutExpired:
        PrettyOutput.auto_print(f"❌ 更新 '{repo_path.name}' 超时。")
    except subprocess.CalledProcessError as e:
        error_message = decode_output(e.stderr).strip() if e.stderr else str(e)
        PrettyOutput.auto_print(f"❌ 更新 '{repo_path.name}' 失败: {error_message}")
    except Exception as e:
        PrettyOutput.auto_print(f"❌ 更新 '{repo_path.name}' 时发生未知错误: {str(e)}")


def daily_check_git_updates(repo_dirs: List[str], repo_type: str) -> None:
    """
    对指定的目录列表执行每日一次的git更新检查。

    Args:
        repo_dirs (List[str]): 需要检查的git仓库目录列表。
        repo_type (str): 仓库的类型名称，例如 "工具" 或 "方法论"，用于日志输出。
    """
    data_dir = Path(str(get_data_dir()))
    last_check_file = data_dir / f"{repo_type}_updates_last_check.txt"
    should_check_for_updates = True

    if last_check_file.exists():
        try:
            last_check_timestamp = float(last_check_file.read_text())
            last_check_date = datetime.fromtimestamp(last_check_timestamp).date()
            if last_check_date == datetime.now().date():
                should_check_for_updates = False
        except (ValueError, IOError):
            pass

    if should_check_for_updates:
        for repo_dir in repo_dirs:
            p_repo_dir = Path(repo_dir)
            if p_repo_dir.exists() and p_repo_dir.is_dir():
                _pull_git_repo(p_repo_dir, repo_type)
        try:
            last_check_file.write_text(str(time.time()))
        except IOError as e:
            PrettyOutput.auto_print(f"⚠️ 无法写入git更新检查时间戳: {e}")
