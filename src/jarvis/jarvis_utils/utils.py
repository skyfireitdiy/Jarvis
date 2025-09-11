# -*- coding: utf-8 -*-
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime, date

import yaml  # type: ignore
from rich.align import Align
from rich.console import RenderableType

from jarvis import __version__
from jarvis.jarvis_utils.config import (
    get_data_dir,
    get_max_big_content_size,
    set_global_env_data,
)
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.globals import get_in_chat, get_interrupt, set_interrupt
from jarvis.jarvis_utils.input import user_confirm
from jarvis.jarvis_utils.output import OutputType, PrettyOutput

# 向后兼容：导出 get_yes_no 供外部模块引用
get_yes_no = user_confirm

g_config_file = None

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


def _setup_signal_handler() -> None:
    """设置SIGINT信号处理函数"""
    original_sigint = signal.getsignal(signal.SIGINT)

    def sigint_handler(signum, frame):
        if get_in_chat():
            set_interrupt(True)
            if get_interrupt() > 5 and original_sigint and callable(original_sigint):
                original_sigint(signum, frame)
        else:
            if original_sigint and callable(original_sigint):
                original_sigint(signum, frame)

    signal.signal(signal.SIGINT, sigint_handler)


def _check_pip_updates() -> bool:
    """检查pip安装的Jarvis是否有更新

    返回:
        bool: 是否执行了更新（成功更新返回True以触发重启）
    """
    import urllib.request
    import urllib.error
    from packaging import version

    # 检查上次检查日期
    last_check_file = Path(get_data_dir()) / "last_pip_check"
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
        except (urllib.error.URLError, KeyError, json.JSONDecodeError):
            return False

        # 比较版本
        current_ver = version.parse(__version__)
        latest_ver = version.parse(latest_version)

        if latest_ver > current_ver:
            PrettyOutput.print(
                f"检测到新版本 v{latest_version} (当前版本: v{__version__})",
                OutputType.INFO,
            )

            # 检测是否在虚拟环境中
            in_venv = hasattr(sys, "real_prefix") or (
                hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
            )

            # 检测是否使用uv
            is_uv_env = False
            uv_executable: Optional[str] = None
            if in_venv:
                if sys.platform == "win32":
                    uv_path = Path(sys.prefix) / "Scripts" / "uv.exe"
                else:
                    uv_path = Path(sys.prefix) / "bin" / "uv"
                if uv_path.exists():
                    is_uv_env = True
                    uv_executable = str(uv_path)

            # 检测是否安装了 RAG 特性（更精确）
            from jarvis.jarvis_utils.utils import (
                is_rag_installed as _is_rag_installed,
            )  # 延迟导入避免潜在循环依赖
            rag_installed = _is_rag_installed()

            # 更新命令
            package_spec = (
                "jarvis-ai-assistant[rag]" if rag_installed else "jarvis-ai-assistant"
            )
            if is_uv_env and uv_executable:
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
                PrettyOutput.print("正在自动更新 Jarvis，请稍候...", OutputType.INFO)
                result = subprocess.run(
                    cmd_list,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=600,
                )
                if result.returncode == 0:
                    PrettyOutput.print("更新成功，正在重启以应用新版本...", OutputType.SUCCESS)
                    # 更新检查日期，避免重复触发
                    last_check_file.write_text(today_str)
                    return True
                else:
                    err = (result.stderr or result.stdout or "").strip()
                    if err:
                        PrettyOutput.print(
                            f"自动更新失败，错误信息（已截断）: {err[:500]}",
                            OutputType.WARNING,
                        )
                    PrettyOutput.print(
                        f"请手动执行以下命令更新: {update_cmd}", OutputType.INFO
                    )
            except Exception:
                PrettyOutput.print("自动更新出现异常，已切换为手动更新方式。", OutputType.WARNING)
                PrettyOutput.print(
                    f"请手动执行以下命令更新: {update_cmd}", OutputType.INFO
                )

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
    script_dir = Path(os.path.dirname(os.path.dirname(__file__)))

    # 先检查是否是git源码安装
    git_dir = script_dir / ".git"
    if git_dir.exists():
        from jarvis.jarvis_utils.git_utils import check_and_update_git_repo

        return check_and_update_git_repo(str(script_dir))

    # 检查是否是pip/uv pip安装的版本
    return _check_pip_updates()


def _show_usage_stats(welcome_str: str) -> None:
    """显示Jarvis使用统计信息"""
    from jarvis.jarvis_utils.output import OutputType, PrettyOutput

    try:

        from rich.console import Console, Group
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text

        console = Console()

        from jarvis.jarvis_stats.stats import StatsManager

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

        # 遍历所有指标，使用快速总量读取以避免全量扫描
        for metric in all_metrics:
            try:
                total = StatsManager.get_metric_total(metric)
            except Exception:
                total = 0.0

            if not total or total <= 0:
                continue

            # 优先使用元信息中的分组（在写入指标时已记录）
            info = StatsManager.get_metric_info(metric) or {}
            group = info.get("group", "other")

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
            categorized_stats["adoption"]["metrics"][
                "adoption_rate"
            ] = f"{adoption_rate:.1f}%"
            categorized_stats["adoption"]["metrics"][
                "commits_status"
            ] = f"{accepted_commits}/{generated_commits}"

        # 构建输出
        has_data = False
        stats_output = []

        for category, data in categorized_stats.items():
            if data["metrics"]:
                has_data = True
                stats_output.append((data["title"], data["metrics"], data["suffix"]))

        # 显示统计信息
        if has_data:
            # 1. 创建统计表格
            from rich import box

            table = Table(
                show_header=True,
                header_style="bold magenta",
                title_justify="center",
                box=box.ROUNDED,
                padding=(0, 1),
            )
            table.add_column("分类", style="cyan", no_wrap=True, width=12)
            table.add_column("指标", style="white", width=20)
            table.add_column("数量", style="green", justify="right", width=10)
            table.add_column("分类", style="cyan", no_wrap=True, width=12)
            table.add_column("指标", style="white", width=20)
            table.add_column("数量", style="green", justify="right", width=10)

            # 收集所有要显示的数据
            all_rows = []
            for title, stats, suffix in stats_output:
                if stats:
                    sorted_stats = sorted(
                        stats.items(), key=lambda item: item[1], reverse=True
                    )
                    for i, (metric, count) in enumerate(sorted_stats):
                        display_name = metric.replace("_", " ").title()
                        category_title = title if i == 0 else ""
                        # 处理不同类型的count值
                        if isinstance(count, (int, float)):
                            count_str = f"{count:,} {suffix}"
                        else:
                            # 对于字符串类型的count（如百分比或比率），直接使用
                            count_str = str(count)
                        all_rows.append((category_title, display_name, count_str))

            # 以3行2列的方式添加数据
            has_content = len(all_rows) > 0
            # 计算需要多少行来显示所有数据
            total_rows = len(all_rows)
            rows_needed = (total_rows + 1) // 2  # 向上取整，因为是2列布局

            for i in range(rows_needed):
                left_idx = i
                right_idx = i + rows_needed

                if left_idx < len(all_rows):
                    left_row = all_rows[left_idx]
                else:
                    left_row = ("", "", "")

                if right_idx < len(all_rows):
                    right_row = all_rows[right_idx]
                else:
                    right_row = ("", "", "")

                table.add_row(
                    left_row[0],
                    left_row[1],
                    left_row[2],
                    right_row[0],
                    right_row[1],
                    right_row[2],
                )

            # 2. 创建总结面板
            summary_content = []

            # 总结统计
            total_tools = sum(
                count
                for title, stats, _ in stats_output
                if "工具" in title
                for metric, count in stats.items()
            )
            total_changes = sum(
                count
                for title, stats, _ in stats_output
                if "代码修改" in title
                for metric, count in stats.items()
            )

            # 统计代码行数
            lines_stats = categorized_stats["lines"]["metrics"]
            total_lines_added = lines_stats.get(
                "code_lines_inserted", lines_stats.get("code_lines_added", 0)
            )
            total_lines_deleted = lines_stats.get("code_lines_deleted", 0)
            total_lines_modified = total_lines_added + total_lines_deleted

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
            time_saved_seconds = 0
            tool_stats = categorized_stats["tool"]["metrics"]
            code_agent_changes = categorized_stats["code"]["metrics"]
            lines_stats = categorized_stats["lines"]["metrics"]
            # commit_stats is already defined above
            command_stats = categorized_stats["command"]["metrics"]

            # 统一的工具使用时间估算（每次调用节省2分钟）
            DEFAULT_TOOL_TIME_SAVINGS = 2 * 60  # 秒

            # 计算所有工具的时间节省
            for tool_name, count in tool_stats.items():
                time_saved_seconds += count * DEFAULT_TOOL_TIME_SAVINGS

            # 其他类型的时间计算
            total_code_agent_calls = sum(code_agent_changes.values())
            time_saved_seconds += total_code_agent_calls * 10 * 60
            time_saved_seconds += lines_stats.get("code_lines_added", 0) * 0.8 * 60
            time_saved_seconds += lines_stats.get("code_lines_deleted", 0) * 0.2 * 60
            time_saved_seconds += sum(commit_stats.values()) * 10 * 60
            time_saved_seconds += sum(command_stats.values()) * 1 * 60

            time_str = ""
            hours = 0
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

                if summary_content:
                    summary_content.append("")  # Add a separator line
                summary_content.append(f"⏱️  节省时间: 约 {time_str}")

                encouragement = ""
                # 计算各级时间单位
                total_work_days = hours // 8  # 总工作日数
                work_years = total_work_days // 240  # 每年约240个工作日
                remaining_days_after_years = total_work_days % 240
                work_months = remaining_days_after_years // 20  # 每月约20个工作日
                remaining_days_after_months = remaining_days_after_years % 20
                work_days = remaining_days_after_months
                remaining_hours = int(hours % 8)  # 剩余不足一个工作日的小时数

                # 构建时间描述
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

            # 3. 组合并打印
            from rich import box

            # 右侧内容：总体表现 + 使命与愿景
            right_column_items = []

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
            if summary_content:
                summary_panel = Panel(
                    Text("\n".join(summary_content), justify="left"),
                    title="✨ 总体表现 ✨",
                    title_align="center",
                    border_style="green",
                    expand=True,
                )
                right_column_items.append(summary_panel)

            # 愿景 Panel
            vision_text = Text(
                "重新定义开发者体验，打破人与工具的界限，构建开发者与AI之间真正的共生伙伴关系。",
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
                "通过深度人机协作，将开发者的灵感（Vibe）高效落地为代码与行动，释放创造之力。",
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

            right_column_group = Group(*right_column_items)

            layout_renderable: RenderableType

            if console.width < 200:
                # 上下布局
                layout_items: List[RenderableType] = []
                layout_items.append(right_column_group)
                if has_content:
                    layout_items.append(Align.center(table))
                layout_renderable = Group(*layout_items)
            else:
                # 左右布局（当前）
                layout_table = Table(
                    show_header=False,
                    box=None,
                    padding=0,
                    expand=True,
                    pad_edge=False,
                )
                # 左右布局，左侧为总结信息，右侧为统计表格
                layout_table.add_column(ratio=5)  # 左侧
                layout_table.add_column(ratio=5)  # 右侧

                if has_content:
                    # 将总结信息放在左侧，统计表格放在右侧（表格居中显示）
                    layout_table.add_row(right_column_group, Align.center(table))
                else:
                    # 如果没有统计数据，则总结信息占满
                    layout_table.add_row(right_column_group)
                layout_renderable = layout_table

            # 打印最终的布局
            if has_content or summary_content:
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

        PrettyOutput.print(f"统计显示出错: {str(e)}", OutputType.ERROR)
        PrettyOutput.print(traceback.format_exc(), OutputType.ERROR)


def init_env(welcome_str: str, config_file: Optional[str] = None) -> None:
    """初始化Jarvis环境

    参数:
        welcome_str: 欢迎信息字符串
        config_file: 配置文件路径，默认为None(使用~/.jarvis/config.yaml)
    """
    # 0. 检查是否处于Jarvis打开的终端环境，避免嵌套
    try:
        if os.environ.get("JARVIS_TERMINAL") == "1":
            PrettyOutput.print(
                "检测到当前终端由 Jarvis 打开。再次启动可能导致嵌套。",
                OutputType.WARNING,
            )
            if not user_confirm("是否仍要继续启动 Jarvis？", default=False):
                PrettyOutput.print("已取消启动以避免终端嵌套。", OutputType.INFO)
                sys.exit(0)
    except Exception:
        pass

    # 1. 设置信号处理
    _setup_signal_handler()

    # 2. 统计命令使用
    count_cmd_usage()

    # 3. 设置配置文件
    global g_config_file
    g_config_file = config_file
    load_config()

    # 4. 显示历史统计数据（仅在显示欢迎信息时显示）
    if welcome_str:
        _show_usage_stats(welcome_str)

    # 5. 检查Jarvis更新
    if _check_jarvis_updates():
        os.execv(sys.executable, [sys.executable] + sys.argv)
        sys.exit(0)


def _interactive_config_setup(config_file_path: Path):
    """交互式配置引导"""
    from jarvis.jarvis_platform.registry import PlatformRegistry
    from jarvis.jarvis_utils.input import (
        get_choice,
        get_single_line_input as get_input,
        user_confirm as get_yes_no,
    )

    PrettyOutput.print(
        "欢迎使用 Jarvis！未找到配置文件，现在开始引导配置。", OutputType.INFO
    )

    # 1. 选择平台
    registry = PlatformRegistry.get_global_platform_registry()
    platforms = registry.get_available_platforms()
    platform_name = get_choice("请选择您要使用的AI平台", platforms)

    # 2. 配置环境变量
    platform_class = registry.platforms.get(platform_name)
    if not platform_class:
        PrettyOutput.print(f"平台 '{platform_name}' 加载失败。", OutputType.ERROR)
        sys.exit(1)

    env_vars = {}
    required_keys = platform_class.get_required_env_keys()
    defaults = platform_class.get_env_defaults()
    config_guide = platform_class.get_env_config_guide()
    if required_keys:
        PrettyOutput.print(
            f"请输入 {platform_name} 平台所需的配置信息:", OutputType.INFO
        )

        # 如果有配置指导，先显示总体说明
        if config_guide:
            # 为避免 PrettyOutput 在循环中为每行加框，先拼接后统一打印
            guide_lines = ["", "配置获取方法:"]
            for key in required_keys:
                if key in config_guide and config_guide[key]:
                    guide_lines.append("")
                    guide_lines.append(f"{key} 获取方法:")
                    guide_lines.append(str(config_guide[key]))
            PrettyOutput.print("\n".join(guide_lines), OutputType.INFO)
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

    # 3. 选择模型
    try:
        platform_instance = registry.create_platform(platform_name)
        if not platform_instance:
            PrettyOutput.print(f"无法创建平台 '{platform_name}'。", OutputType.ERROR)
            sys.exit(1)

        model_list_tuples = platform_instance.get_model_list()
        model_choices = [f"{name} ({desc})" for name, desc in model_list_tuples]
        model_display_name = get_choice("请选择要使用的模型", model_choices)

        # 从显示名称反向查找模型ID
        selected_index = model_choices.index(model_display_name)
        model_name, _ = model_list_tuples[selected_index]

    except Exception:
        PrettyOutput.print("获取模型列表失败", OutputType.ERROR)
        if not get_yes_no("无法获取模型列表，是否继续配置？"):
            sys.exit(1)
        model_name = get_input("请输入模型名称:")

    # 4. 测试配置
    PrettyOutput.print("正在测试配置...", OutputType.INFO)
    test_passed = False
    try:
        platform_instance = registry.create_platform(platform_name)
        if platform_instance:
            platform_instance.set_model_name(model_name)
            response_generator = platform_instance.chat("hello")
            response = "".join(response_generator)
            if response:
                PrettyOutput.print(
                    f"测试成功，模型响应: {response}", OutputType.SUCCESS
                )
                test_passed = True
            else:
                PrettyOutput.print("测试失败，模型没有响应。", OutputType.ERROR)
        else:
            PrettyOutput.print("测试失败，无法创建平台实例。", OutputType.ERROR)
    except Exception:
        PrettyOutput.print("测试失败", OutputType.ERROR)

    # 5. 交互式确认并应用配置（不直接生成配置文件）
    config_data = {
        "ENV": env_vars,
        "JARVIS_PLATFORM": platform_name,
        "JARVIS_MODEL": model_name,
    }

    if not test_passed:
        if not get_yes_no("配置测试失败，是否仍要应用该配置并继续？", default=False):
            PrettyOutput.print("已取消配置。", OutputType.INFO)
            sys.exit(0)

    # 6. 选择其他功能开关与可选项（复用统一逻辑）
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
        PrettyOutput.print(f"配置文件已生成: {config_file_path}", OutputType.SUCCESS)
        PrettyOutput.print("配置完成，请重新启动Jarvis。", OutputType.INFO)
        sys.exit(0)
    except Exception:
        PrettyOutput.print("写入配置文件失败", OutputType.ERROR)
        sys.exit(1)


def load_config():
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


from typing import Tuple


def _load_config_file(config_file: str) -> Tuple[str, dict]:
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
    jarvis_dir: str, config_file: str, content: str, config_data: dict
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


def _process_env_variables(config_data: dict) -> None:
    """处理配置中的环境变量

    参数:
        config_data: 解析后的配置字典
    """
    if "ENV" in config_data and isinstance(config_data["ENV"], dict):
        os.environ.update(
            {str(k): str(v) for k, v in config_data["ENV"].items() if v is not None}
        )


def _collect_optional_config_interactively(
    config_data: dict, ask_all: bool = False
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
    from jarvis.jarvis_utils.input import user_confirm as get_yes_no
    from jarvis.jarvis_utils.input import get_single_line_input

    def _ask_and_set(_key, _tip, _default, _type="bool"):
        try:
            if not ask_all and _key in config_data:
                return False
            if _type == "bool":
                cur = bool(config_data.get(_key, _default))
                val = get_yes_no(_tip, default=cur)
                # 与当前值相同则不写入，避免冗余
                if bool(val) == cur:
                    return False
                config_data[_key] = bool(val)
            else:
                cur = str(config_data.get(_key, _default or ""))
                val = get_single_line_input(f"{_tip}", default=cur)
                v = ("" if val is None else str(val)).strip()
                # 输入与当前值相同则不写入
                if v == cur:
                    return False
                config_data[_key] = v
            return True
        except Exception:
            # 异常时不写入，保持精简
            return False

    def _ask_and_set_optional_str(_key, _tip, _default: str = "") -> bool:
        try:
            if not ask_all and _key in config_data:
                return False
            cur = str(config_data.get(_key, _default or ""))
            val = get_single_line_input(f"{_tip}", default=cur)
            if val is None:
                return False
            s = str(val).strip()
            # 空输入表示不改变
            if s == "":
                return False
            if s == cur:
                return False
            config_data[_key] = s
            return True
        except Exception:
            return False

    def _ask_and_set_int(_key, _tip, _default: int) -> bool:
        try:
            if not ask_all and _key in config_data:
                return False
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

    def _ask_and_set_list(_key, _tip) -> bool:
        try:
            if not ask_all and _key in config_data:
                return False
            cur_val = config_data.get(_key, [])
            if isinstance(cur_val, list):
                cur_display = ", ".join([str(x) for x in cur_val])
            else:
                cur_display = str(cur_val or "")
            val = get_single_line_input(f"{_tip}", default=cur_display)
            if val is None:
                return False
            s = str(val).strip()
            if s == cur_display.strip():
                return False
            if not s:
                # 输入为空表示不改变
                return False
            items = [x.strip() for x in s.split(",") if x.strip()]
            if isinstance(cur_val, list) and items == cur_val:
                return False
            config_data[_key] = items
            return True
        except Exception:
            return False

    changed = False
    # 现有两个开关
    changed = (
        _ask_and_set(
            "JARVIS_ENABLE_GIT_JCA_SWITCH",
            "是否在检测到Git仓库时，提示并可自动切换到代码开发模式（jca）？",
            False,
            "bool",
        )
        or changed
    )
    changed = (
        _ask_and_set(
            "JARVIS_ENABLE_STARTUP_CONFIG_SELECTOR",
            "在进入默认通用代理前，是否先列出可用配置（agent/multi_agent/roles）供选择？",
            False,
            "bool",
        )
        or changed
    )

    # 新增的配置项交互（通用体验相关）
    changed = (
        _ask_and_set(
            "JARVIS_PRETTY_OUTPUT",
            "是否启用更美观的终端输出（Pretty Output）？",
            False,
            "bool",
        )
        or changed
    )
    changed = (
        _ask_and_set(
            "JARVIS_PRINT_PROMPT",
            "是否打印发送给模型的提示词（Prompt）？",
            False,
            "bool",
        )
        or changed
    )
    changed = (
        _ask_and_set(
            "JARVIS_IMMEDIATE_ABORT",
            "是否启用立即中断？\n- 选择 是/true：在对话输出流的每次迭代中检测到用户中断（例如 Ctrl+C）时，立即返回当前已生成的内容并停止继续输出。\n- 选择 否/false：不会在输出过程中立刻返回，而是按既有流程处理（不中途打断输出）。",
            False,
            "bool",
        )
        or changed
    )
    changed = (
        _ask_and_set(
            "JARVIS_ENABLE_STATIC_ANALYSIS",
            "是否启用静态代码分析（Static Analysis）？",
            True,
            "bool",
        )
        or changed
    )
    changed = (
        _ask_and_set(
            "JARVIS_USE_METHODOLOGY",
            "是否启用方法论系统（Methodology）？",
            True,
            "bool",
        )
        or changed
    )
    changed = (
        _ask_and_set(
            "JARVIS_USE_ANALYSIS",
            "是否启用分析流程（Analysis）？",
            True,
            "bool",
        )
        or changed
    )
    changed = (
        _ask_and_set(
            "JARVIS_FORCE_SAVE_MEMORY",
            "是否强制保存会话记忆？",
            True,
            "bool",
        )
        or changed
    )

    # 代码与工具操作安全提示
    changed = (
        _ask_and_set(
            "JARVIS_EXECUTE_TOOL_CONFIRM",
            "执行工具前是否需要确认？",
            False,
            "bool",
        )
        or changed
    )
    changed = (
        _ask_and_set(
            "JARVIS_CONFIRM_BEFORE_APPLY_PATCH",
            "应用补丁前是否需要确认？",
            False,
            "bool",
        )
        or changed
    )

    # 数据目录与最大输入Token
    from jarvis.jarvis_utils.config import get_data_dir as _get_data_dir  # lazy import

    changed = (
        _ask_and_set_optional_str(
            "JARVIS_DATA_PATH",
            f"是否自定义数据目录路径(JARVIS_DATA_PATH)？留空使用默认: {_get_data_dir()}",
        )
        or changed
    )
    changed = (
        _ask_and_set_int(
            "JARVIS_MAX_INPUT_TOKEN_COUNT",
            "自定义最大输入Token数量（留空使用默认: 32000）",
            32000,
        )
        or changed
    )
    changed = (
        _ask_and_set_int(
            "JARVIS_TOOL_FILTER_THRESHOLD",
            "设置AI工具筛选阈值 (当可用工具数超过此值时触发AI筛选, 默认30)",
            30,
        )
        or changed
    )

    # 目录类配置（逗号分隔）
    changed = (
        _ask_and_set_list(
            "JARVIS_TOOL_LOAD_DIRS",
            "指定工具加载目录（逗号分隔，留空跳过）：",
        )
        or changed
    )
    changed = (
        _ask_and_set_list(
            "JARVIS_METHODOLOGY_DIRS",
            "指定方法论加载目录（逗号分隔，留空跳过）：",
        )
        or changed
    )
    changed = (
        _ask_and_set_list(
            "JARVIS_AGENT_DEFINITION_DIRS",
            "指定 agent 定义加载目录（逗号分隔，留空跳过）：",
        )
        or changed
    )
    changed = (
        _ask_and_set_list(
            "JARVIS_MULTI_AGENT_DIRS",
            "指定 multi_agent 加载目录（逗号分隔，留空跳过）：",
        )
        or changed
    )
    changed = (
        _ask_and_set_list(
            "JARVIS_ROLES_DIRS",
            "指定 roles 加载目录（逗号分隔，留空跳过）：",
        )
        or changed
    )

    # Web 搜索配置（可选）
    changed = (
        _ask_and_set_optional_str(
            "JARVIS_WEB_SEARCH_PLATFORM",
            "配置 Web 搜索平台名称（留空跳过）：",
        )
        or changed
    )
    changed = (
        _ask_and_set_optional_str(
            "JARVIS_WEB_SEARCH_MODEL",
            "配置 Web 搜索模型名称（留空跳过）：",
        )
        or changed
    )

    # Git 校验模式
    def _ask_git_check_mode() -> bool:
        try:
            _key = "JARVIS_GIT_CHECK_MODE"
            if not ask_all and _key in config_data:
                return False

            from jarvis.jarvis_utils.input import get_choice
            from jarvis.jarvis_utils.config import get_git_check_mode

            current_mode = config_data.get(_key, get_git_check_mode())
            choices = ["strict", "warn"]
            tip = (
                "请选择 Git 仓库检查模式 (JARVIS_GIT_CHECK_MODE):\n"
                "此设置决定了当在 Git 仓库中检测到未提交的更改时，Jarvis应如何处理。\n"
                "这对于确保代码修改和提交操作在干净的工作区上进行至关重要。\n"
                "  - strict: (推荐) 如果存在未提交的更改，则中断相关操作（如代码修改、自动提交）。\n"
                "            这可以防止意外覆盖或丢失本地工作。\n"
                "  - warn:   如果存在未提交的更改，仅显示警告信息，然后继续执行操作。\n"
                "            适用于您希望绕过检查并自行管理仓库状态的场景。"
            )

            try:
                # 查找当前模式在选项中的索引
                default_index = choices.index(current_mode)
            except ValueError:
                default_index = 0  # 默认为第一个选项

            new_mode = get_choice(
                tip,
                choices,
            )

            if new_mode == current_mode:
                return False

            config_data[_key] = new_mode
            return True
        except Exception:
            return False

    changed = _ask_git_check_mode() or changed

    # Git 提交提示词（可选）
    changed = (
        _ask_and_set_optional_str(
            "JARVIS_GIT_COMMIT_PROMPT",
            "自定义 Git 提交提示模板（留空跳过）：",
        )
        or changed
    )

    # RAG 配置（可选）
    try:
        from jarvis.jarvis_utils.config import (
            get_rag_embedding_model as _get_rag_embedding_model,
            get_rag_rerank_model as _get_rag_rerank_model,
        )

        rag_default_embed = _get_rag_embedding_model()
        rag_default_rerank = _get_rag_rerank_model()
    except Exception:
        rag_default_embed = "BAAI/bge-m3"
        rag_default_rerank = "BAAI/bge-reranker-v2-m3"

    try:
        if "JARVIS_RAG" not in config_data:
            if get_yes_no("是否配置 RAG 检索增强参数？", default=False):
                rag_conf: Dict[str, Any] = {}
                emb = get_single_line_input(
                    f"RAG 嵌入模型（留空使用默认: {rag_default_embed}）：",
                    default="",
                ).strip()
                rerank = get_single_line_input(
                    f"RAG rerank 模型（留空使用默认: {rag_default_rerank}）：",
                    default="",
                ).strip()
                use_bm25 = get_yes_no("RAG 是否使用 BM25？", default=True)
                use_rerank = get_yes_no("RAG 是否使用 rerank？", default=True)
                if emb:
                    rag_conf["embedding_model"] = emb
                else:
                    rag_conf["embedding_model"] = rag_default_embed
                if rerank:
                    rag_conf["rerank_model"] = rerank
                else:
                    rag_conf["rerank_model"] = rag_default_rerank
                rag_conf["use_bm25"] = bool(use_bm25)
                rag_conf["use_rerank"] = bool(use_rerank)
                config_data["JARVIS_RAG"] = rag_conf
                changed = True
    except Exception:
        pass

    # 中心仓库配置
    changed = (
        _ask_and_set(
            "JARVIS_CENTRAL_METHODOLOGY_REPO",
            "请输入中心方法论仓库地址（可留空跳过）：",
            "",
            "str",
        )
        or changed
    )
    changed = (
        _ask_and_set(
            "JARVIS_CENTRAL_TOOL_REPO",
            "请输入中心工具仓库地址（可留空跳过）：",
            "",
            "str",
        )
        or changed
    )

    # 已移除 LLM 组配置交互

    # 已移除 RAG 组配置交互

    # 已移除 工具组配置交互

    # 已移除：替换映射（JARVIS_REPLACE_MAP）的交互式配置，保持最简交互
    # SHELL 覆盖（可选）
    try:
        default_shell = os.getenv("SHELL", "/bin/bash")
        changed = (
            _ask_and_set_optional_str(
                "SHELL",
                f"覆盖 SHELL 路径（留空使用系统默认: {default_shell}）：",
                default_shell,
            )
            or changed
        )
    except Exception:
        pass

    # 已移除：MCP（JARVIS_MCP）的交互式配置，保持最简交互
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
        PrettyOutput.print("加载配置文件失败", OutputType.ERROR)
        if get_yes_no("配置文件格式错误，是否删除并重新配置？"):
            try:
                os.remove(config_file)
                PrettyOutput.print(
                    "已删除损坏的配置文件，请重启Jarvis以重新配置。", OutputType.SUCCESS
                )
            except Exception:
                PrettyOutput.print("删除配置文件失败", OutputType.ERROR)
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


def _load_default_config_from_schema() -> dict:
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


def _prune_defaults_with_schema(config_data: dict) -> bool:
    """
    删除与 schema 默认值一致的配置项，返回是否发生了变更
    仅处理 schema 中定义的键，未在 schema 中的键不会被修改
    """
    defaults = _load_default_config_from_schema()
    if not defaults or not isinstance(config_data, dict):
        return False

    changed = False

    def _prune_node(node: dict, default_node: dict):
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


def _read_old_config_file(config_file):
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
                    value = "\n".join(current_value).strip().strip("'").strip('"')
                    # 将字符串"true"/"false"转换为bool类型
                    if value.lower() == "true":
                        value = True
                    elif value.lower() == "false":
                        value = False
                    config_data[current_key] = value
                    current_value = []
                    # 解析新的键值对
                key, value = line.split("=", 1)
                current_key = key.strip()
                current_value.append(value.strip())
            elif current_key is not None:
                # 多行值的后续行
                current_value.append(line.strip())
                # 处理最后一个键值对
        if current_key is not None:
            value = "\n".join(current_value).strip().strip("'").strip('"')
            # 将字符串"true"/"false"转换为bool类型
            if value.lower() == "true":
                value = True
            elif value.lower() == "false":
                value = False
            config_data[current_key] = value
        os.environ.update(
            {str(k): str(v) for k, v in config_data.items() if v is not None}
        )
        set_global_env_data(config_data)
    PrettyOutput.print(
        "检测到旧格式配置文件，旧格式以后将不再支持，请尽快迁移到新格式",
        OutputType.WARNING,
    )


def while_success(func: Callable[[], Any], sleep_time: float = 0.1, max_retries: int = 5) -> Any:
    """循环执行函数直到成功（累计日志后统一打印，避免逐次加框）

    参数：
    func -- 要执行的函数
    sleep_time -- 每次失败后的等待时间（秒）
    max_retries -- 最大重试次数，默认5次

    返回：
    函数执行结果
    """
    result: Any = None
    retry_count = 0
    while retry_count < max_retries:
        try:
            result = func()
            break
        except Exception:
            retry_count += 1
            if retry_count < max_retries:
                PrettyOutput.print(
                    f"发生异常，重试中 ({retry_count}/{max_retries})，等待 {sleep_time}s...",
                    OutputType.WARNING,
                )
                time.sleep(sleep_time)
            continue
    return result


def while_true(func: Callable[[], bool], sleep_time: float = 0.1, max_retries: int = 5) -> Any:
    """循环执行函数直到返回True（累计日志后统一打印，避免逐次加框）

    参数:
        func: 要执行的函数，必须返回布尔值
        sleep_time: 每次失败后的等待时间(秒)
        max_retries: 最大重试次数，默认5次

    返回:
        函数最终返回的True值

    注意:
        与while_success不同，此函数只检查返回是否为True，
        不捕获异常，异常会直接抛出
    """
    ret: bool = False
    retry_count = 0
    while retry_count < max_retries:
        ret = func()
        if ret:
            break
        retry_count += 1
        if retry_count < max_retries:
            PrettyOutput.print(
                f"返回空值，重试中 ({retry_count}/{max_retries})，等待 {sleep_time}s...",
                OutputType.WARNING,
            )
            time.sleep(sleep_time)
    return ret


def get_file_md5(filepath: str) -> str:
    """计算文件内容的MD5哈希值

    参数:
        filepath: 要计算哈希的文件路径

    返回:
        str: 文件内容的MD5哈希值
    """
    return hashlib.md5(open(filepath, "rb").read(100 * 1024 * 1024)).hexdigest()


def get_file_line_count(filename: str) -> int:
    """计算文件中的行数

    参数:
        filename: 要计算行数的文件路径

    返回:
        int: 文件中的行数，如果文件无法读取则返回0
    """
    try:
        return len(open(filename, "r", encoding="utf-8", errors="ignore").readlines())
    except Exception:
        return 0


def count_cmd_usage() -> None:
    """统计当前命令的使用次数"""
    import sys
    import os
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
    content: str, model_group_override: Optional[str] = None
) -> bool:
    """判断文件内容是否超出上下文限制"""
    return get_context_token_count(content) > get_max_big_content_size(
        model_group_override
    )


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


def _pull_git_repo(repo_path: Path, repo_type: str):
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
                    PrettyOutput.print(
                        f"放弃 '{repo_path.name}' 的更改失败: {str(e)}",
                        OutputType.ERROR,
                    )
                    return
            else:
                PrettyOutput.print(
                    f"跳过更新 '{repo_path.name}' 以保留未提交的更改。",
                    OutputType.INFO,
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
            PrettyOutput.print(
                f"{repo_type}库 '{repo_path.name}' 已更新。", OutputType.SUCCESS
            )

    except FileNotFoundError:
        PrettyOutput.print(
            f"git 命令未找到，跳过更新 '{repo_path.name}'。", OutputType.WARNING
        )
    except subprocess.TimeoutExpired:
        PrettyOutput.print(f"更新 '{repo_path.name}' 超时。", OutputType.ERROR)
    except subprocess.CalledProcessError as e:
        error_message = e.stderr.strip() if e.stderr else str(e)
        PrettyOutput.print(
            f"更新 '{repo_path.name}' 失败: {error_message}", OutputType.ERROR
        )
    except Exception as e:
        PrettyOutput.print(
            f"更新 '{repo_path.name}' 时发生未知错误: {str(e)}", OutputType.ERROR
        )


def daily_check_git_updates(repo_dirs: List[str], repo_type: str):
    """
    对指定的目录列表执行每日一次的git更新检查。

    Args:
        repo_dirs (List[str]): 需要检查的git仓库目录列表。
        repo_type (str): 仓库的类型名称，例如 "工具" 或 "方法论"，用于日志输出。
    """
    data_dir = Path(get_data_dir())
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
            PrettyOutput.print(f"无法写入git更新检查时间戳: {e}", OutputType.WARNING)
