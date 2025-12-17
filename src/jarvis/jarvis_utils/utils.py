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
from rich.align import Align
from rich.console import RenderableType

from jarvis import __version__
from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.config import get_max_big_content_size
from jarvis.jarvis_utils.config import set_global_env_data
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.globals import get_in_chat
from jarvis.jarvis_utils.globals import get_interrupt
from jarvis.jarvis_utils.globals import set_interrupt
from jarvis.jarvis_utils.input import user_confirm
from jarvis.jarvis_utils.output import PrettyOutput

# 向后兼容：导出 get_yes_no 供外部模块引用
get_yes_no = user_confirm

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
    # RAG
    "jrg": "jarvis-rag",
    # 统计
    "jst": "jarvis-stats",
    # 记忆整理
    "jmo": "jarvis-memory-organizer",
    # 安全分析
    "jsec": "jarvis-sec",
    # C2Rust迁移
    "jc2r": "jarvis-c2rust",
}

# RAG 依赖检测工具函数（更精确）
_RAG_REQUIRED_MODULES = [
    "langchain",
    "langchain_community",
    "chromadb",
    "sentence_transformers",
    "rank_bm25",
    "unstructured",
]
_RAG_OPTIONAL_MODULES = [
    "langchain_huggingface",
]


def get_missing_rag_modules() -> List[str]:
    """
    返回缺失的 RAG 关键依赖模块列表。
    仅检查必要模块，不导入模块，避免副作用。
    """
    try:
        from importlib.util import find_spec

        missing = [m for m in _RAG_REQUIRED_MODULES if find_spec(m) is None]
        return missing
    except Exception:
        # 任何异常都视为无法确认，保持保守策略
        return _RAG_REQUIRED_MODULES[:]  # 视为全部缺失


def is_rag_installed() -> bool:
    """
    更准确的 RAG 安装检测：确认关键依赖模块均可用。
    """
    return len(get_missing_rag_modules()) == 0


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

            # 检测是否安装了 RAG 特性（更精确）
            from jarvis.jarvis_utils.utils import (
                is_rag_installed as _is_rag_installed,
            )  # 延迟导入避免潜在循环依赖

            rag_installed = _is_rag_installed()

            # 更新命令
            package_spec = (
                "jarvis-ai-assistant[rag]" if rag_installed else "jarvis-ai-assistant"
            )
            if uv_executable:
                cmd_list = [uv_executable, "pip", "install", "--upgrade", package_spec]
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
                update_cmd = f"{sys.executable} -m pip install --upgrade {package_spec}"

            # 自动尝试升级（失败时提供手动命令）
            try:
                PrettyOutput.auto_print("ℹ️ 正在自动更新 Jarvis，请稍候...")
                result = subprocess.run(
                    cmd_list,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=600,
                )
                if result.returncode == 0:
                    PrettyOutput.auto_print("✅ 更新成功，正在重启以应用新版本...")
                    # 更新检查日期，避免重复触发
                    last_check_file.write_text(today_str)
                    return True
                else:
                    err = (result.stderr or result.stdout or "").strip()
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
    """显示Jarvis使用统计信息"""
    try:
        from rich.console import Console
        from rich.console import Group
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text

        console = Console()

        from jarvis.jarvis_stats.stats import StatsManager
        from jarvis.jarvis_stats.storage import StatsStorage

        # 获取所有可用的指标
        all_metrics = StatsManager.list_metrics()

        # 根据指标名称和标签自动分类
        categorized_stats: Dict[str, Dict[str, Any]] = {
            "tool": {"title": "🔧 工具调用", "metrics": {}, "suffix": "次"},
            "code": {"title": "📝 代码修改", "metrics": {}, "suffix": "次"},
            "lines": {"title": "📊 代码行数", "metrics": {}, "suffix": "行"},
            "commit": {"title": "💾 提交统计", "metrics": {}, "suffix": "个"},
            "command": {"title": "📱 命令使用", "metrics": {}, "suffix": "次"},
            "adoption": {"title": "🎯 采纳情况", "metrics": {}, "suffix": ""},
            "other": {"title": "📦 其他指标", "metrics": {}, "suffix": ""},
        }

        # 复用存储实例，避免重复创建
        storage = StatsStorage()

        # 一次性读取元数据，避免重复读取
        try:
            meta = storage._load_json(storage.meta_file)
            metrics_info = meta.get("metrics", {})
        except Exception:
            metrics_info = {}

        # 批量读取所有总量文件，避免逐个文件操作
        metric_totals: Dict[str, float] = {}
        totals_dir = storage.totals_dir
        if totals_dir.exists():
            try:
                for total_file in totals_dir.glob("*"):
                    if total_file.is_file():
                        try:
                            with open(total_file, "r", encoding="utf-8") as f:
                                total = float((f.read() or "0").strip() or "0")
                                if total > 0:
                                    metric_totals[total_file.name] = total
                        except Exception:
                            pass
            except Exception:
                pass

        # 遍历所有指标，使用批量读取的数据
        for metric in all_metrics:
            # 从批量读取的数据中获取总量
            total = metric_totals.get(metric, 0.0)

            if not total or total <= 0:
                continue

            # 从已加载的元数据中获取分组信息，避免重复读取
            try:
                info = metrics_info.get(metric, {})
                group = info.get("group", "other")
            except Exception:
                group = "other"

            if group == "tool":
                categorized_stats["tool"]["metrics"][metric] = int(total)
            elif group == "code_agent":
                # 根据指标名称细分
                if metric.startswith("code_lines_"):
                    categorized_stats["lines"]["metrics"][metric] = int(total)
                elif "commit" in metric:
                    categorized_stats["commit"]["metrics"][metric] = int(total)
                else:
                    categorized_stats["code"]["metrics"][metric] = int(total)
            elif group == "command":
                categorized_stats["command"]["metrics"][metric] = int(total)
            else:
                categorized_stats["other"]["metrics"][metric] = int(total)

        # 合并长短命令的历史统计数据
        command_stats = categorized_stats["command"]["metrics"]
        if command_stats:
            merged_stats: Dict[str, int] = {}
            for metric, count in command_stats.items():
                long_command = COMMAND_MAPPING.get(metric, metric)
                merged_stats[long_command] = merged_stats.get(long_command, 0) + count
            categorized_stats["command"]["metrics"] = merged_stats

        # 计算采纳率并添加到统计中
        commit_stats = categorized_stats["commit"]["metrics"]
        # 使用精确的指标名称
        generated_commits = commit_stats.get("commits_generated", 0)
        accepted_commits = commit_stats.get("commits_accepted", 0)

        # 如果有 generated，则计算采纳率
        if generated_commits > 0:
            adoption_rate = (accepted_commits / generated_commits) * 100
            categorized_stats["adoption"]["metrics"]["adoption_rate"] = (
                f"{adoption_rate:.1f}%"
            )
            categorized_stats["adoption"]["metrics"]["commits_status"] = (
                f"{accepted_commits}/{generated_commits}"
            )

        # 右侧内容：总体表现 + 使命与愿景
        right_column_items = []
        summary_content: list[str] = []
        from rich import box

        # 计算总体表现的摘要数据
        # 总结统计
        total_tools = sum(
            count
            for _, stats in categorized_stats["tool"]["metrics"].items()
            for metric, count in {
                k: v
                for k, v in categorized_stats["tool"]["metrics"].items()
                if isinstance(v, (int, float))
            }.items()
        )
        total_tools = sum(
            count
            for metric, count in categorized_stats["tool"]["metrics"].items()
            if isinstance(count, (int, float))
        )

        total_changes = sum(
            count
            for metric, count in categorized_stats["code"]["metrics"].items()
            if isinstance(count, (int, float))
        )

        # 统计代码行数
        lines_stats = categorized_stats["lines"]["metrics"]
        total_lines_added = lines_stats.get(
            "code_lines_inserted", lines_stats.get("code_lines_added", 0)
        )
        total_lines_deleted = lines_stats.get("code_lines_deleted", 0)
        total_lines_modified = total_lines_added + total_lines_deleted

        # 构建总体表现内容
        if total_tools > 0 or total_changes > 0 or total_lines_modified > 0:
            parts = []
            if total_tools > 0:
                parts.append(f"工具调用 {total_tools:,} 次")
            if total_changes > 0:
                parts.append(f"代码修改 {total_changes:,} 次")
            if total_lines_modified > 0:
                parts.append(f"修改代码行数 {total_lines_modified:,} 行")

            if parts:
                summary_content.append(f"📈 总计: {', '.join(parts)}")

            # 添加代码采纳率显示
            adoption_metrics = categorized_stats["adoption"]["metrics"]
            if "adoption_rate" in adoption_metrics:
                summary_content.append(
                    f"✅ 代码采纳率: {adoption_metrics['adoption_rate']}"
                )

            # 计算节省的时间
            time_saved_seconds: float = 0.0
            tool_stats = categorized_stats["tool"]["metrics"]
            code_agent_changes = categorized_stats["code"]["metrics"]
            lines_stats = categorized_stats["lines"]["metrics"]
            commit_stats = categorized_stats["commit"]["metrics"]
            command_stats = categorized_stats["command"]["metrics"]

            # 统一的工具使用时间估算（每次调用节省2分钟）
            DEFAULT_TOOL_TIME_SAVINGS = 2 * 60  # 秒

            # 计算所有工具的时间节省
            for tool_name, count in tool_stats.items():
                if isinstance(count, (int, float)):
                    time_saved_seconds += count * DEFAULT_TOOL_TIME_SAVINGS

            # 其他类型的时间计算
            total_code_agent_calls: float = float(
                sum(
                    v
                    for v in code_agent_changes.values()
                    if isinstance(v, (int, float))
                )
            )
            time_saved_seconds += total_code_agent_calls * 10 * 60
            time_saved_seconds += lines_stats.get("code_lines_added", 0) * 0.8 * 60
            time_saved_seconds += lines_stats.get("code_lines_deleted", 0) * 0.2 * 60
            time_saved_seconds += (
                sum(v for v in commit_stats.values() if isinstance(v, (int, float)))
                * 10
                * 60
            )
            time_saved_seconds += (
                sum(v for v in command_stats.values() if isinstance(v, (int, float)))
                * 1
                * 60
            )

            if time_saved_seconds > 0:
                total_minutes = int(time_saved_seconds / 60)
                seconds = int(time_saved_seconds % 60)
                hours = total_minutes // 60
                minutes = total_minutes % 60

                # 只显示小时和分钟
                if hours > 0:
                    time_str = f"{hours} 小时 {minutes} 分钟"
                elif total_minutes > 0:
                    time_str = f"{minutes} 分钟 {seconds} 秒"
                else:
                    time_str = f"{seconds} 秒"

                summary_content.append(f"⏱️  节省时间: 约 {time_str}")

                # 计算时间节省的鼓励信息
                total_work_days = hours // 8
                work_years = total_work_days // 240
                remaining_days_after_years = total_work_days % 240
                work_months = remaining_days_after_years // 20
                remaining_days_after_months = remaining_days_after_years % 20
                work_days = remaining_days_after_months
                remaining_hours = int(hours % 8)

                time_parts = []
                if work_years > 0:
                    time_parts.append(f"{work_years} 年")
                if work_months > 0:
                    time_parts.append(f"{work_months} 个月")
                if work_days > 0:
                    time_parts.append(f"{work_days} 个工作日")
                if remaining_hours > 0:
                    time_parts.append(f"{remaining_hours} 小时")

                if time_parts:
                    time_description = "、".join(time_parts)
                    if work_years >= 1:
                        encouragement = (
                            f"🎉 相当于节省了 {time_description} 的工作时间！"
                        )
                    elif work_months >= 1:
                        encouragement = (
                            f"🚀 相当于节省了 {time_description} 的工作时间！"
                        )
                    elif work_days >= 1:
                        encouragement = (
                            f"💪 相当于节省了 {time_description} 的工作时间！"
                        )
                    else:
                        encouragement = (
                            f"✨ 相当于节省了 {time_description} 的工作时间！"
                        )
                elif hours >= 1:
                    encouragement = f"⭐ 相当于节省了 {int(hours)} 小时的工作时间，积少成多，继续保持！"

                if encouragement:
                    summary_content.append(encouragement)

        # 欢迎信息 Panel
        if welcome_str:
            jarvis_ascii_art_str = """
   ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
   ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
   ██║███████║██████╔╝██║   ██║██║███████╗
██╗██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚████║██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚═══╝╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝"""

            welcome_panel_content = Group(
                Align.center(Text(jarvis_ascii_art_str, style="bold blue")),
                Align.center(Text(welcome_str, style="bold")),
                "",  # for a blank line
                Align.center(Text(f"v{__version__}")),
                Align.center(Text("https://github.com/skyfireitdiy/Jarvis")),
            )

            welcome_panel = Panel(
                welcome_panel_content, border_style="yellow", expand=True
            )
            right_column_items.append(welcome_panel)

        # 总体表现 Panel
        summary_panel = Panel(
            Text(
                "\n".join(summary_content) if summary_content else "暂无数据",
                justify="left",
            ),
            title="✨ 总体表现 ✨",
            title_align="center",
            border_style="green",
            expand=True,
        )
        right_column_items.append(summary_panel)

        # 愿景 Panel
        vision_text = Text(
            "让开发者与AI成为共生伙伴",
            justify="center",
            style="italic",
        )
        vision_panel = Panel(
            vision_text,
            title="🔭 愿景 (Vision) 🔭",
            title_align="center",
            border_style="cyan",
            expand=True,
        )
        right_column_items.append(vision_panel)

        # 使命 Panel
        mission_text = Text(
            "让灵感高效落地为代码与行动",
            justify="center",
            style="italic",
        )
        mission_panel = Panel(
            mission_text,
            title="🎯 使命 (Mission) 🎯",
            title_align="center",
            border_style="magenta",
            expand=True,
        )
        right_column_items.append(mission_panel)

        # 创建左右两列的内容组
        left_column_items = []
        right_column_items = []

        # 左侧：欢迎Logo和基本信息
        if welcome_str:
            jarvis_ascii_art_str = """
   ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
   ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
   ██║███████║██████╔╝██║   ██║██║███████╗
██╗██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚████║██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚═══╝╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝"""

            welcome_content = Group(
                Align.center(Text(jarvis_ascii_art_str, style="bold blue")),
                Align.center(Text(welcome_str, style="bold")),
                "",  # for a blank line
                Align.center(Text(f"v{__version__}")),
                Align.center(Text("https://github.com/skyfireitdiy/Jarvis")),
            )

            welcome_panel = Panel(
                welcome_content,
                title="🤖 Jarvis AI Assistant",
                border_style="yellow",
                expand=True,
            )
            left_column_items.append(welcome_panel)

        # 右侧：总体表现、愿景和使命
        # 总体表现 Panel
        summary_panel = Panel(
            Text(
                "\n".join(summary_content) if summary_content else "暂无数据",
                justify="left",
            ),
            title="✨ 总体表现 ✨",
            title_align="center",
            border_style="green",
            expand=True,
        )
        right_column_items.append(summary_panel)

        # 愿景 Panel
        vision_text = Text(
            "让开发者与AI成为共生伙伴",
            justify="center",
            style="italic",
        )
        vision_panel = Panel(
            vision_text,
            title="🔭 愿景 (Vision) 🔭",
            title_align="center",
            border_style="cyan",
            expand=True,
        )
        right_column_items.append(vision_panel)

        # 使命 Panel
        mission_text = Text(
            "让灵感高效落地为代码与行动",
            justify="center",
            style="italic",
        )
        mission_panel = Panel(
            mission_text,
            title="🎯 使命 (Mission) 🎯",
            title_align="center",
            border_style="magenta",
            expand=True,
        )
        right_column_items.append(mission_panel)

        left_column_group = Group(*left_column_items) if left_column_items else None
        right_column_group = Group(*right_column_items)

        layout_renderable: RenderableType

        if console.width < 200:
            # 上下布局（窄屏）
            layout_items: List[RenderableType] = []
            if left_column_group:
                layout_items.append(left_column_group)
            layout_items.append(right_column_group)
            layout_renderable = Group(*layout_items)
        else:
            # 左右布局（宽屏）
            layout_table = Table(
                show_header=False,
                box=None,
                padding=(0, 2),  # 上下0，左右2字符的内边距
                expand=True,
                pad_edge=False,
            )
            # 左右布局，优化比例：左侧更紧凑，右侧更宽敞
            if left_column_group:
                layout_table.add_column(
                    ratio=35, min_width=40
                )  # 左侧欢迎信息，最小宽度40
                layout_table.add_column(
                    ratio=65, min_width=80
                )  # 右侧统计信息，最小宽度80
                layout_table.add_row(left_column_group, right_column_group)
            else:
                # 如果没有欢迎信息，右侧占满
                layout_table.add_column(ratio=100)
                layout_table.add_row(right_column_group)
            layout_renderable = layout_table

        # 打印最终的布局
        # 将整体布局封装在一个最终的Panel中，以提供整体边框
        final_panel = Panel(
            layout_renderable,
            title="Jarvis AI Assistant",
            title_align="center",
            border_style="blue",
            box=box.HEAVY,
            padding=(0, 1),
        )
        console.print(final_panel)
    except Exception as e:
        # 输出错误信息以便调试
        import traceback

        PrettyOutput.auto_print(f"❌ 统计显示出错: {str(e)}")
        PrettyOutput.auto_print(f"❌ {traceback.format_exc()}")


def init_env(welcome_str: str = "", config_file: Optional[str] = None) -> None:
    """初始化Jarvis环境

    参数:
        welcome_str: 欢迎信息字符串
        config_file: 配置文件路径，默认为None(使用~/.jarvis/config.yaml)
    """
    # 0. 检查是否处于Jarvis打开的终端环境，避免嵌套
    try:
        if os.environ.get("terminal") == "1":
            PrettyOutput.auto_print(
                "⚠️ 检测到当前终端由 Jarvis 打开。再次启动可能导致嵌套。"
            )
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
    except Exception:
        # 静默失败，不影响正常使用
        pass

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
    try:
        if _check_jarvis_updates():
            os.execv(sys.executable, [sys.executable] + sys.argv)
            sys.exit(0)
    except Exception:
        # 静默失败，不影响正常使用
        pass


def _interactive_config_setup(config_file_path: Path) -> None:
    """交互式配置引导"""
    from jarvis.jarvis_platform.registry import PlatformRegistry
    from jarvis.jarvis_utils.input import get_choice
    from jarvis.jarvis_utils.input import get_single_line_input as get_input
    from jarvis.jarvis_utils.input import user_confirm as get_yes_no

    PrettyOutput.auto_print("ℹ️ 欢迎使用 Jarvis！未找到配置文件，现在开始引导配置。")

    # 1. 选择平台
    registry = PlatformRegistry.get_global_platform_registry()
    platforms = registry.get_available_platforms()
    platform_name = get_choice("请选择您要使用的AI平台", platforms)

    # 2. 配置 API 密钥等信息（用于 llm_config）
    platform_class = registry.platforms.get(platform_name)
    if not platform_class:
        PrettyOutput.auto_print(f"❌ 平台 '{platform_name}' 加载失败。")
        sys.exit(1)

    env_vars = {}
    llm_config = {}
    required_keys = platform_class.get_required_env_keys()
    defaults = platform_class.get_env_defaults()
    config_guide = platform_class.get_env_config_guide()

    # 环境变量到 llm_config 键名的映射
    env_to_llm_config_map = {
        "OPENAI_API_KEY": "openai_api_key",
        "OPENAI_API_BASE": "openai_api_base",
        "OPENAI_EXTRA_HEADERS": "openai_extra_headers",
        "KIMI_API_KEY": "kimi_api_key",
        "TONGYI_COOKIES": "tongyi_cookies",
        "YUANBAO_COOKIES": "yuanbao_cookies",
    }

    if required_keys:
        PrettyOutput.auto_print(f"ℹ️ 请输入 {platform_name} 平台所需的配置信息:")

        # 如果有配置指导，先显示总体说明
        if config_guide:
            # 为避免 PrettyOutput 在循环中为每行加框，先拼接后统一打印
            guide_lines = ["", "配置获取方法:"]
            for key in required_keys:
                if key in config_guide and config_guide[key]:
                    guide_lines.append("")
                    guide_lines.append(f"{key} 获取方法:")
                    guide_lines.append(str(config_guide[key]))
            PrettyOutput.auto_print("ℹ️ " + "\n".join(guide_lines))
        else:
            # 若无指导，仍需遍历以保持后续逻辑一致
            pass

        for key in required_keys:
            # 显示该环境变量的配置指导（上文已统一打印，此处不再逐条打印）

            default_value = defaults.get(key, "")
            prompt_text = f"  - {key}"
            if default_value:
                prompt_text += f" (默认: {default_value})"
            prompt_text += ": "

            value = get_input(prompt_text, default=default_value)
            env_vars[key] = value
            os.environ[key] = value  # 立即设置环境变量以便后续测试

            # 同时添加到 llm_config（如果存在映射）
            llm_config_key = env_to_llm_config_map.get(key)
            if llm_config_key:
                llm_config[llm_config_key] = value

    # 3. 选择模型
    try:
        # 创建平台实例时传递 llm_config（如果已收集）
        platform_instance = registry.create_platform(
            platform_name, llm_config=llm_config if llm_config else None
        )
        if not platform_instance:
            PrettyOutput.auto_print(f"❌ 无法创建平台 '{platform_name}'。")
            sys.exit(1)

        model_list_tuples = platform_instance.get_model_list()
        model_choices = [f"{name} ({desc})" for name, desc in model_list_tuples]
        model_display_name = get_choice("请选择要使用的模型", model_choices)

        # 从显示名称反向查找模型ID
        selected_index = model_choices.index(model_display_name)
        model_name, _ = model_list_tuples[selected_index]

    except Exception:
        PrettyOutput.auto_print("❌ 获取模型列表失败")
        if not get_yes_no("无法获取模型列表，是否继续配置？"):
            sys.exit(1)
        model_name = get_input("请输入模型名称:")

    # 4. 测试配置
    PrettyOutput.auto_print("ℹ️ 正在测试配置...")
    test_passed = False
    try:
        # 创建平台实例时传递 llm_config（如果已收集）
        platform_instance = registry.create_platform(
            platform_name, llm_config=llm_config if llm_config else None
        )
        if platform_instance:
            platform_instance.set_model_name(model_name)
            response_generator = platform_instance.chat("hello")
            response = "".join(response_generator)
            if response:
                PrettyOutput.auto_print(f"✅ 测试成功，模型响应: {response}")
                test_passed = True
            else:
                PrettyOutput.auto_print("❌ 测试失败，模型没有响应。")
        else:
            PrettyOutput.auto_print("❌ 测试失败，无法创建平台实例。")
    except Exception:
        PrettyOutput.auto_print("❌ 测试失败")

    # 5. 询问最大输入 token 数量
    max_input_token_count = 32000
    try:
        max_input_token_str = get_input(
            "请输入最大输入 token 数量（留空使用默认: 32000）:",
            default="32000",
        )
        if max_input_token_str and max_input_token_str.strip():
            max_input_token_count = int(max_input_token_str.strip())
    except Exception:
        pass

    # 6. 生成 LLM 配置名称
    llm_name = f"{platform_name}-{model_name}".replace(" ", "-").lower()
    # 清理名称，只保留字母、数字和连字符
    import re

    llm_name = re.sub(r"[^a-z0-9-]", "", llm_name)
    if not llm_name:
        llm_name = "default-llm"

    # 7. 交互式确认并应用配置（使用新的引用方式）
    config_data = {
        "ENV": env_vars,
        "llms": {
            llm_name: {
                "platform": platform_name,
                "model": model_name,
                "max_input_token_count": max_input_token_count,
                "llm_config": llm_config if llm_config else {},
            }
        },
        "llm_groups": {
            "default": {
                "normal_llm": llm_name,
            }
        },
        "llm_group": "default",
    }

    if not test_passed:
        if not get_yes_no("配置测试失败，是否仍要应用该配置并继续？", default=False):
            PrettyOutput.auto_print("ℹ️ 已取消配置。")
            sys.exit(0)

    # 8. 选择其他功能开关与可选项（复用统一逻辑）
    _collect_optional_config_interactively(config_data)

    # 7. 应用到当前会话并写入配置文件（基于交互结果，不从默认值生成）
    set_global_env_data(config_data)
    _process_env_variables(config_data)
    try:
        schema_path = (
            Path(__file__).parent.parent / "jarvis_data" / "config_schema.json"
        )
        config_file_path.parent.mkdir(parents=True, exist_ok=True)
        header = ""
        if schema_path.exists():
            header = f"# yaml-language-server: $schema={str(schema_path.absolute())}\n"
        _prune_defaults_with_schema(config_data)
        yaml_str = yaml.dump(config_data, allow_unicode=True, sort_keys=False)
        with open(config_file_path, "w", encoding="utf-8") as f:
            if header:
                f.write(header)
            f.write(yaml_str)
        PrettyOutput.auto_print(f"✅ 配置文件已生成: {config_file_path}")
        PrettyOutput.auto_print("ℹ️ 配置完成，请重新启动Jarvis。")
        sys.exit(0)
    except Exception:
        PrettyOutput.auto_print("❌ 写入配置文件失败")
        sys.exit(1)


def load_config() -> None:
    config_file = g_config_file
    config_file_path = (
        Path(config_file)
        if config_file is not None
        else Path(os.path.expanduser("~/.jarvis/config.yaml"))
    )

    # 加载配置文件
    if not config_file_path.exists():
        old_config_file = config_file_path.parent / "env"
        if old_config_file.exists():  # 旧的配置文件存在
            _read_old_config_file(old_config_file)
        else:
            _interactive_config_setup(config_file_path)
    else:
        _load_and_process_config(str(config_file_path.parent), str(config_file_path))


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


def _ask_config_bool(
    config_data: Dict[str, Any], ask_all: bool, _key: str, _tip: str, _default: bool
) -> bool:
    """询问并设置布尔类型配置项"""
    try:
        if not ask_all and _key in config_data:
            return False
        from jarvis.jarvis_utils.input import user_confirm as get_yes_no

        cur = bool(config_data.get(_key, _default))
        val = get_yes_no(_tip, default=cur)
        if bool(val) == cur:
            return False
        config_data[_key] = bool(val)
        return True
    except Exception:
        return False


def _ask_config_str(
    config_data: Dict[str, Any], ask_all: bool, _key: str, _tip: str, _default: str = ""
) -> bool:
    """询问并设置字符串类型配置项"""
    try:
        if not ask_all and _key in config_data:
            return False
        from jarvis.jarvis_utils.input import get_single_line_input

        cur = str(config_data.get(_key, _default or ""))
        val = get_single_line_input(f"{_tip}", default=cur)
        v = ("" if val is None else str(val)).strip()
        if v == cur:
            return False
        config_data[_key] = v
        return True
    except Exception:
        return False


def _ask_config_optional_str(
    config_data: Dict[str, Any], ask_all: bool, _key: str, _tip: str, _default: str = ""
) -> bool:
    """询问并设置可选字符串类型配置项（空输入表示不改变）"""
    try:
        if not ask_all and _key in config_data:
            return False
        from jarvis.jarvis_utils.input import get_single_line_input

        cur = str(config_data.get(_key, _default or ""))
        val = get_single_line_input(f"{_tip}", default=cur)
        if not val:
            return False
        s = str(val).strip()
        if s == "" or s == cur:
            return False
        config_data[_key] = s
        return True
    except Exception:
        return False


def _ask_config_int(
    config_data: Dict[str, Any], ask_all: bool, _key: str, _tip: str, _default: int
) -> bool:
    """询问并设置整数类型配置项"""
    try:
        if not ask_all and _key in config_data:
            return False
        from jarvis.jarvis_utils.input import get_single_line_input

        cur = str(config_data.get(_key, _default))
        val_str = get_single_line_input(f"{_tip}", default=cur)
        s = "" if val_str is None else str(val_str).strip()
        if s == "" or s == cur:
            return False
        try:
            v = int(s)
        except Exception:
            return False
        if str(v) == cur:
            return False
        config_data[_key] = v
        return True
    except Exception:
        return False


def _ask_config_list(
    config_data: Dict[str, Any], ask_all: bool, _key: str, _tip: str
) -> bool:
    """询问并设置列表类型配置项（逗号分隔）"""
    try:
        if not ask_all and _key in config_data:
            return False
        from jarvis.jarvis_utils.input import get_single_line_input

        cur_val = config_data.get(_key, [])
        if isinstance(cur_val, list):
            cur_display = ", ".join([str(x) for x in cur_val])
        else:
            cur_display = str(cur_val or "")
        val = get_single_line_input(f"{_tip}", default=cur_display)
        if not val:
            return False
        s = str(val).strip()
        if s == cur_display.strip():
            return False
        if not s:
            return False
        items = [x.strip() for x in s.split(",") if x.strip()]
        if isinstance(cur_val, list) and items == cur_val:
            return False
        config_data[_key] = items
        return True
    except Exception:
        return False


def _collect_basic_switches(config_data: Dict[str, Any], ask_all: bool) -> bool:
    """收集基础开关配置"""
    changed = False
    changed = (
        _ask_config_bool(
            config_data,
            ask_all,
            "enable_git_jca_switch",
            "是否在检测到Git仓库时，提示并可自动切换到代码开发模式（jca）？",
            True,
        )
        or changed
    )
    changed = (
        _ask_config_bool(
            config_data,
            ask_all,
            "enable_startup_config_selector",
            "在进入默认通用代理前，是否先列出可用配置（agent/multi_agent/roles）供选择？",
            True,
        )
        or changed
    )
    return changed


def _collect_ui_experience_config(config_data: Dict[str, Any], ask_all: bool) -> bool:
    """收集UI体验相关配置"""
    changed = False
    try:
        import platform as _platform_mod

        _default_pretty = False if _platform_mod.system() == "Windows" else True
    except Exception:
        _default_pretty = True

    changed = (
        _ask_config_bool(
            config_data,
            ask_all,
            "pretty_output",
            "是否启用更美观的终端输出（Pretty Output）？",
            _default_pretty,
        )
        or changed
    )
    changed = (
        _ask_config_bool(
            config_data,
            ask_all,
            "print_prompt",
            "是否打印发送给模型的提示词（Prompt）？",
            False,
        )
        or changed
    )
    changed = (
        _ask_config_bool(
            config_data,
            ask_all,
            "immediate_abort",
            "是否启用立即中断？\n- 选择 是/true：在对话输出流的每次迭代中检测到用户中断（例如 Ctrl+C）时，立即返回当前已生成的内容并停止继续输出。\n- 选择 否/false：不会在输出过程中立刻返回，而是按既有流程处理（不中途打断输出）。",
            False,
        )
        or changed
    )

    # Diff 可视化模式配置
    if ask_all or "diff_visualization_mode" not in config_data:
        from jarvis.jarvis_utils.input import get_choice

        current_mode = config_data.get("diff_visualization_mode", "side_by_side")
        diff_mode_choices = [
            f"side_by_side - 左右分栏对比显示{'（当前）' if current_mode == 'side_by_side' else ''}",
            f"unified - 统一diff格式{'（当前）' if current_mode == 'unified' else ''}",
            f"syntax - 语法高亮模式{'（当前）' if current_mode == 'syntax' else ''}",
            f"compact - 紧凑模式{'（当前）' if current_mode == 'compact' else ''}",
        ]
        selected_display = get_choice("选择 Diff 可视化模式", diff_mode_choices)
        selected_mode = selected_display.split(" - ")[0]
        if selected_mode != current_mode:
            config_data["diff_visualization_mode"] = selected_mode
            changed = True

    return changed


def _collect_analysis_config(config_data: Dict[str, Any], ask_all: bool) -> bool:
    """收集代码分析相关配置"""
    changed = False
    changed = (
        _ask_config_bool(
            config_data,
            ask_all,
            "enable_static_analysis",
            "是否启用静态代码分析（Static Analysis）？",
            True,
        )
        or changed
    )
    changed = (
        _ask_config_bool(
            config_data,
            ask_all,
            "enable_build_validation",
            "是否启用构建验证（Build Validation）？在代码编辑后自动验证代码能否成功编译/构建。",
            True,
        )
        or changed
    )
    changed = (
        _ask_config_int(
            config_data,
            ask_all,
            "build_validation_timeout",
            "构建验证的超时时间（秒，默认30秒）",
            30,
        )
        or changed
    )
    changed = (
        _ask_config_bool(
            config_data,
            ask_all,
            "enable_impact_analysis",
            "是否启用编辑影响范围分析（Impact Analysis）？分析代码编辑的影响范围，识别可能受影响的文件、函数、测试等。",
            True,
        )
        or changed
    )
    return changed


def _collect_agent_features_config(config_data: Dict[str, Any], ask_all: bool) -> bool:
    """收集Agent功能相关配置"""
    changed = False
    changed = (
        _ask_config_bool(
            config_data,
            ask_all,
            "use_methodology",
            "是否启用方法论系统（Methodology）？",
            True,
        )
        or changed
    )
    changed = (
        _ask_config_bool(
            config_data,
            ask_all,
            "use_analysis",
            "是否启用分析流程（Analysis）？",
            True,
        )
        or changed
    )
    changed = (
        _ask_config_bool(
            config_data,
            ask_all,
            "force_save_memory",
            "是否强制保存会话记忆？",
            False,
        )
        or changed
    )
    return changed


def _collect_session_config(config_data: Dict[str, Any], ask_all: bool) -> bool:
    """收集会话与调试相关配置"""
    changed = False
    changed = (
        _ask_config_bool(
            config_data,
            ask_all,
            "save_session_history",
            "是否保存会话记录？",
            False,
        )
        or changed
    )
    changed = (
        _ask_config_bool(
            config_data,
            ask_all,
            "print_error_traceback",
            "是否在错误输出时打印回溯调用链？",
            False,
        )
        or changed
    )
    changed = (
        _ask_config_bool(
            config_data,
            ask_all,
            "skip_predefined_tasks",
            "是否跳过预定义任务加载（不读取 pre-command 列表）？",
            False,
        )
        or changed
    )
    changed = (
        _ask_config_int(
            config_data,
            ask_all,
            "conversation_turn_threshold",
            "对话轮次阈值（达到此轮次时触发总结，建议50-100）：",
            50,
        )
        or changed
    )
    return changed


def _collect_safety_config(config_data: Dict[str, Any], ask_all: bool) -> bool:
    """收集代码与工具操作安全提示配置"""
    changed = False
    changed = (
        _ask_config_bool(
            config_data,
            ask_all,
            "execute_tool_confirm",
            "执行工具前是否需要确认？",
            False,
        )
        or changed
    )
    changed = (
        _ask_config_bool(
            config_data,
            ask_all,
            "confirm_before_apply_patch",
            "应用补丁前是否需要确认？",
            False,
        )
        or changed
    )
    return changed


def _collect_data_and_token_config(config_data: Dict[str, Any], ask_all: bool) -> bool:
    """收集数据目录与最大输入Token配置"""
    changed = False
    from jarvis.jarvis_utils.config import get_data_dir as _get_data_dir

    changed = (
        _ask_config_optional_str(
            config_data,
            ask_all,
            "data_path",
            f"是否自定义数据目录路径(data_path)？留空使用默认: {_get_data_dir()}",
        )
        or changed
    )
    changed = (
        _ask_config_int(
            config_data,
            ask_all,
            "max_input_token_count",
            "自定义最大输入Token数量（留空使用默认: 128000）",
            128000,
        )
        or changed
    )
    changed = (
        _ask_config_int(
            config_data,
            ask_all,
            "cheap_max_input_token_count",
            "廉价模型的最大输入Token数量（留空或0表示使用max_input_token_count）",
            0,
        )
        or changed
    )
    changed = (
        _ask_config_int(
            config_data,
            ask_all,
            "smart_max_input_token_count",
            "智能模型的最大输入Token数量（留空或0表示使用max_input_token_count）",
            0,
        )
        or changed
    )
    changed = (
        _ask_config_int(
            config_data,
            ask_all,
            "tool_filter_threshold",
            "设置AI工具筛选阈值 (当可用工具数超过此值时触发AI筛选, 默认30)",
            30,
        )
        or changed
    )
    return changed


def _collect_advanced_config(config_data: Dict[str, Any], ask_all: bool) -> bool:
    """收集高级配置（自动总结、脚本超时等）"""
    changed = False
    changed = (
        _ask_config_int(
            config_data,
            ask_all,
            "script_execution_timeout",
            "脚本执行超时时间（秒，默认300，仅非交互模式生效）",
            300,
        )
        or changed
    )
    changed = (
        _ask_config_int(
            config_data,
            ask_all,
            "addon_prompt_threshold",
            "附加提示的触发阈值（字符数，默认1024）。当消息长度超过此值时，会自动添加默认的附加提示",
            1024,
        )
        or changed
    )
    changed = (
        _ask_config_bool(
            config_data,
            ask_all,
            "enable_intent_recognition",
            "是否启用意图识别功能？用于智能上下文推荐中的LLM意图提取和语义分析",
            True,
        )
        or changed
    )
    return changed


def _collect_directory_config(config_data: Dict[str, Any], ask_all: bool) -> bool:
    """收集目录类配置（逗号分隔）"""
    changed = False
    changed = (
        _ask_config_list(
            config_data,
            ask_all,
            "tool_load_dirs",
            "指定工具加载目录（逗号分隔，留空跳过）：",
        )
        or changed
    )
    changed = (
        _ask_config_list(
            config_data,
            ask_all,
            "methodology_dirs",
            "指定方法论加载目录（逗号分隔，留空跳过）：",
        )
        or changed
    )
    changed = (
        _ask_config_list(
            config_data,
            ask_all,
            "agent_definition_dirs",
            "指定 agent 定义加载目录（逗号分隔，留空跳过）：",
        )
        or changed
    )
    changed = (
        _ask_config_list(
            config_data,
            ask_all,
            "multi_agent_dirs",
            "指定 multi_agent 加载目录（逗号分隔，留空跳过）：",
        )
        or changed
    )
    changed = (
        _ask_config_list(
            config_data,
            ask_all,
            "roles_dirs",
            "指定 roles 加载目录（逗号分隔，留空跳过）：",
        )
        or changed
    )
    changed = (
        _ask_config_list(
            config_data,
            ask_all,
            "after_tool_call_cb_dirs",
            "指定工具调用后回调实现目录（逗号分隔，留空跳过）：",
        )
        or changed
    )
    return changed


def _collect_web_search_config(config_data: Dict[str, Any], ask_all: bool) -> bool:
    """收集Web搜索配置"""
    changed = False
    changed = (
        _ask_config_optional_str(
            config_data,
            ask_all,
            "web_search_platform",
            "配置 Web 搜索平台名称（留空跳过）：",
        )
        or changed
    )
    changed = (
        _ask_config_optional_str(
            config_data,
            ask_all,
            "web_search_model",
            "配置 Web 搜索模型名称（留空跳过）：",
        )
        or changed
    )
    return changed


def _collect_git_config(config_data: Dict[str, Any], ask_all: bool) -> bool:
    """收集Git相关配置"""
    changed = False
    changed = (
        _ask_config_optional_str(
            config_data,
            ask_all,
            "git_commit_prompt",
            "自定义 Git 提交提示模板（留空跳过）：",
        )
        or changed
    )
    return changed


def _collect_rag_config(config_data: Dict[str, Any], ask_all: bool) -> bool:
    """收集RAG配置（使用新的引用方式）"""
    changed = False
    try:
        from jarvis.jarvis_utils.config import (
            get_rag_embedding_model as _get_rag_embedding_model,
        )
        from jarvis.jarvis_utils.config import (
            get_rag_rerank_model as _get_rag_rerank_model,
        )
        from jarvis.jarvis_utils.input import (
            get_single_line_input as get_single_line_input_func,
        )
        from jarvis.jarvis_utils.input import user_confirm as get_yes_no_func

        rag_default_embed = _get_rag_embedding_model()
        rag_default_rerank = _get_rag_rerank_model()
        get_yes_no_var: Optional[Any] = get_yes_no_func
        get_single_line_input_var: Optional[Any] = get_single_line_input_func
    except Exception:
        rag_default_embed = "BAAI/bge-m3"
        rag_default_rerank = "BAAI/bge-reranker-v2-m3"
        get_yes_no_var = None
        get_single_line_input_var = None

    try:
        if (
            "rag_groups" not in config_data
            and get_yes_no_var is not None
            and get_single_line_input_var is not None
        ):
            if get_yes_no_var("是否配置 RAG 检索增强参数？", default=False):
                # 初始化 embeddings 和 rerankers（如果不存在）
                if "embeddings" not in config_data:
                    config_data["embeddings"] = {}
                if "rerankers" not in config_data:
                    config_data["rerankers"] = {}
                if "rag_groups" not in config_data:
                    config_data["rag_groups"] = {}

                # 收集嵌入模型配置
                emb = get_single_line_input_var(
                    f"RAG 嵌入模型（留空使用默认: {rag_default_embed}）：",
                    default="",
                ).strip()
                if not emb:
                    emb = rag_default_embed

                # 创建嵌入模型配置
                embedding_name = "default-rag-embedding"
                config_data["embeddings"][embedding_name] = {
                    "embedding_model": emb,
                    "embedding_type": "LocalEmbeddingModel",
                    "embedding_max_length": 512,
                }

                # 收集重排模型配置
                rerank = get_single_line_input_var(
                    f"RAG rerank 模型（留空使用默认: {rag_default_rerank}）：",
                    default="",
                ).strip()
                if get_yes_no_var is not None:
                    use_bm25 = get_yes_no_var("RAG 是否使用 BM25？", default=True)
                    use_rerank = get_yes_no_var("RAG 是否使用 rerank？", default=True)
                else:
                    use_bm25 = True
                    use_rerank = True

                # 创建重排模型配置（如果使用 rerank）
                rag_group_config = {
                    "embedding": embedding_name,
                    "use_bm25": bool(use_bm25),
                    "use_rerank": bool(use_rerank),
                }

                if use_rerank:
                    if not rerank:
                        rerank = rag_default_rerank
                    reranker_name = "default-rag-reranker"
                    config_data["rerankers"][reranker_name] = {
                        "rerank_model": rerank,
                        "reranker_type": "LocalReranker",
                        "reranker_max_length": 512,
                    }
                    rag_group_config["reranker"] = reranker_name

                # 创建 rag_groups 配置（对象格式）
                config_data["rag_groups"]["default"] = rag_group_config
                config_data["rag_group"] = "default"
                changed = True
    except Exception:
        pass
    return changed


def _collect_central_repo_config(config_data: Dict[str, Any], ask_all: bool) -> bool:
    """收集中心仓库配置"""
    changed = False
    changed = (
        _ask_config_str(
            config_data,
            ask_all,
            "central_methodology_repo",
            "请输入中心方法论仓库路径或Git地址（可留空跳过）：",
            "",
        )
        or changed
    )
    changed = (
        _ask_config_str(
            config_data,
            ask_all,
            "central_tool_repo",
            "请输入中心工具仓库路径或Git地址（可留空跳过）：",
            "",
        )
        or changed
    )
    return changed


def _collect_shell_config(config_data: Dict[str, Any], ask_all: bool) -> bool:
    """收集SHELL覆盖配置"""
    changed = False
    try:
        import os

        default_shell = os.getenv("SHELL", "/bin/bash")
        changed = (
            _ask_config_optional_str(
                config_data,
                ask_all,
                "SHELL",
                f"覆盖 SHELL 路径（留空使用系统默认: {default_shell}）：",
                default_shell,
            )
            or changed
        )
    except Exception:
        pass
    return changed


def _collect_optional_config_interactively(
    config_data: Dict[str, Any], ask_all: bool = False
) -> bool:
    """
    复用的交互式配置收集逻辑：
    - ask_all=False（默认）：仅对缺省的新功能开关/可选项逐项询问，已存在项跳过
    - ask_all=True：对所有项进行询问，默认值取自当前配置文件，可覆盖现有设置
    - 修改传入的 config_data
    - 包含更多来自 config.py 的可选项
    返回:
        bool: 是否有变更
    """
    changed = False

    # 收集各类配置
    changed = _collect_basic_switches(config_data, ask_all) or changed
    changed = _collect_ui_experience_config(config_data, ask_all) or changed
    changed = _collect_analysis_config(config_data, ask_all) or changed
    changed = _collect_agent_features_config(config_data, ask_all) or changed
    changed = _collect_session_config(config_data, ask_all) or changed
    changed = _collect_safety_config(config_data, ask_all) or changed
    changed = _collect_data_and_token_config(config_data, ask_all) or changed
    changed = _collect_advanced_config(config_data, ask_all) or changed
    changed = _collect_directory_config(config_data, ask_all) or changed
    changed = _collect_web_search_config(config_data, ask_all) or changed
    changed = _collect_git_config(config_data, ask_all) or changed
    changed = _collect_rag_config(config_data, ask_all) or changed
    changed = _collect_central_repo_config(config_data, ask_all) or changed
    changed = _collect_shell_config(config_data, ask_all) or changed

    return changed


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
        set_global_env_data(config_data)
        _process_env_variables(config_data)

        # 加载 schema 默认并剔除等于默认值的项
        pruned = _prune_defaults_with_schema(config_data)

        if pruned:
            # 保留schema声明，如无则自动补充
            header = ""
            try:
                with open(config_file, "r", encoding="utf-8") as rf:
                    first_line = rf.readline()
                    if first_line.startswith("# yaml-language-server: $schema="):
                        header = first_line
            except Exception:
                header = ""
            yaml_str = yaml.dump(config_data, allow_unicode=True, sort_keys=False)
            if not header:
                schema_path = Path(
                    os.path.relpath(
                        Path(__file__).parent.parent
                        / "jarvis_data"
                        / "config_schema.json",
                        start=jarvis_dir,
                    )
                )
                header = f"# yaml-language-server: $schema={schema_path}\n"
            with open(config_file, "w", encoding="utf-8") as wf:
                wf.write(header)
                wf.write(yaml_str)
            # 更新全局配置
            set_global_env_data(config_data)
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
        set_global_env_data(config_data)
    PrettyOutput.auto_print(
        "⚠️ 检测到旧格式配置文件，旧格式以后将不再支持，请尽快迁移到新格式"
    )


# 线程本地存储，用于共享重试计数器
_retry_context = threading.local()


def _get_retry_count() -> int:
    """获取当前线程的重试计数"""
    if not hasattr(_retry_context, "count"):
        _retry_context.count = 0
    return int(_retry_context.count)


def _increment_retry_count() -> int:
    """增加重试计数并返回新的计数值"""
    if not hasattr(_retry_context, "count"):
        _retry_context.count = 0
    _retry_context.count += 1
    return int(_retry_context.count)


def _reset_retry_count() -> None:
    """重置重试计数"""
    _retry_context.count = 0


def while_success(func: Callable[[], Any]) -> Any:
    """循环执行函数直到成功（累计日志后统一打印，避免逐次加框）

    参数：
    func -- 要执行的函数

    返回：
    函数执行结果

    注意：
    与while_true共享重试计数器，累计重试6次，使用指数退避（第一次等待1s）
    """
    MAX_RETRIES = 6
    result: Any = None

    while True:
        try:
            result = func()
            _reset_retry_count()  # 成功后重置计数器
            break
        except Exception as e:
            retry_count = _increment_retry_count()
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
                    _reset_retry_count()
                    raise
            else:
                _reset_retry_count()
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
        与while_success共享重试计数器，累计重试6次，使用指数退避（第一次等待1s）
    """
    MAX_RETRIES = 6
    ret: bool = False

    while True:
        try:
            ret = func()
            if ret:
                _reset_retry_count()  # 成功后重置计数器
                break
        except Exception:
            # 异常直接抛出，不捕获
            _reset_retry_count()
            raise

        retry_count = _increment_retry_count()
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
                _reset_retry_count()
                break
        else:
            _reset_retry_count()
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
    """统计当前命令的使用次数"""
    import os
    import sys

    from jarvis.jarvis_stats.stats import StatsManager

    # 从完整路径中提取命令名称
    cmd_path = sys.argv[0]
    cmd_name = os.path.basename(cmd_path)

    # 如果是短命令，映射到长命令
    if cmd_name in COMMAND_MAPPING:
        metric_name = COMMAND_MAPPING[cmd_name]
    else:
        metric_name = cmd_name

    # 使用 StatsManager 记录命令使用统计
    StatsManager.increment(metric_name, group="command")


def is_context_overflow(
    content: str,
    model_group_override: Optional[str] = None,
    platform: Optional[Any] = None,
) -> bool:
    """判断文件内容是否超出上下文限制

    参数:
        content: 要检查的内容
        model_group_override: 模型组覆盖（可选）
        platform: 平台实例（可选），如果提供则使用剩余token数量判断

    返回:
        bool: 如果内容超出上下文限制返回True
    """
    # 快速长度预估：如果内容长度明显超过限制，直接返回True，无需精确计算token
    if content:
        # 粗略估算：假设平均每个token约4个字符，保守估计使用3.5个字符/token
        estimated_tokens = len(content) // 3.5

        # 获取最大token限制
        max_tokens = get_max_big_content_size(model_group_override)

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
    return content_tokens > get_max_big_content_size(model_group_override)


def get_loc_stats() -> str:
    """使用loc命令获取当前目录的代码统计信息

    返回:
        str: loc命令输出的原始字符串，失败时返回空字符串
    """
    try:
        result = subprocess.run(
            ["loc"], capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        return result.stdout if result.returncode == 0 else ""
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
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=10,
        )
        if not remote_result.stdout.strip():
            return

        # 检查git仓库状态
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=10,
        )
        if status_result.stdout:
            if user_confirm(
                f"检测到 '{repo_path.name}' 存在未提交的更改，是否放弃这些更改并更新？"
            ):
                try:
                    subprocess.run(
                        ["git", "checkout", "."],
                        cwd=repo_path,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
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
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=10,
        )
        before_hash = before_hash_result.stdout.strip()

        # 检查是否是空仓库
        ls_remote_result = subprocess.run(
            ["git", "ls-remote", "--heads", "origin"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=10,
        )

        if not ls_remote_result.stdout.strip():
            return

        # 执行 git pull
        subprocess.run(
            ["git", "pull"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )

        # 获取更新后的commit hash
        after_hash_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        after_hash = after_hash_result.stdout.strip()

        if before_hash != after_hash:
            PrettyOutput.auto_print(f"✅ {repo_type}库 '{repo_path.name}' 已更新。")

    except FileNotFoundError:
        PrettyOutput.auto_print(f"⚠️ git 命令未找到，跳过更新 '{repo_path.name}'。")
    except subprocess.TimeoutExpired:
        PrettyOutput.auto_print(f"❌ 更新 '{repo_path.name}' 超时。")
    except subprocess.CalledProcessError as e:
        error_message = e.stderr.strip() if e.stderr else str(e)
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
