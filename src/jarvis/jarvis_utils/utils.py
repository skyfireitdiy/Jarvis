# -*- coding: utf-8 -*-
import hashlib
import json
import os
import platform
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime

import yaml  # type: ignore
from rich.align import Align
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from jarvis import __version__
from jarvis.jarvis_utils.config import (
    get_data_dir,
    get_max_big_content_size,
    set_global_env_data,
)
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.globals import get_in_chat, get_interrupt, set_interrupt
from jarvis.jarvis_utils.output import OutputType, PrettyOutput

g_config_file = None


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


def _show_welcome_message(welcome_str: str) -> None:
    """显示欢迎信息

    参数:
        welcome_str: 欢迎信息字符串
    """
    if not welcome_str:
        return

    jarvis_ascii_art = f"""
   ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
   ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
   ██║███████║██████╔╝██║   ██║██║███████╗
██╗██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚████║██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚═══╝╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
 {welcome_str}

 https://github.com/skyfireitdiy/Jarvis
 v{__version__}
"""
    PrettyOutput.print_gradient_text(jarvis_ascii_art, (0, 120, 255), (0, 255, 200))


def _check_git_updates() -> bool:
    """检查并更新git仓库

    返回:
        bool: 是否需要重启进程
    """
    script_dir = Path(os.path.dirname(os.path.dirname(__file__)))
    from jarvis.jarvis_utils.git_utils import check_and_update_git_repo

    return check_and_update_git_repo(str(script_dir))


def _show_usage_stats() -> None:
    """显示Jarvis使用统计信息"""
    from jarvis.jarvis_utils.output import OutputType, PrettyOutput

    try:
        from datetime import datetime

        from rich.console import Console, Group
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text

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
        }

        # 遍历所有指标，获取统计数据
        for metric in all_metrics:
            # 获取该指标的所有数据
            stats_data = StatsManager.get_stats(
                metric_name=metric,
                start_time=datetime(2000, 1, 1),
                end_time=datetime.now(),
            )

            if stats_data and isinstance(stats_data, dict) and "records" in stats_data:
                # 按照标签分组统计
                tag_totals: Dict[str, float] = {}
                for record in stats_data["records"]:
                    tags = record.get("tags", {})
                    group = tags.get("group", "other")
                    tag_totals[group] = tag_totals.get(group, 0) + record["value"]

                # 根据标签将指标分配到相应类别
                for group, total in tag_totals.items():
                    if total > 0:
                        if group == "tool":
                            categorized_stats["tool"]["metrics"][metric] = int(total)
                        elif group == "code_agent":
                            # 根据指标名称细分
                            if metric.startswith("code_lines_"):
                                categorized_stats["lines"]["metrics"][metric] = int(
                                    total
                                )
                            elif "commit" in metric:
                                categorized_stats["commit"]["metrics"][metric] = int(
                                    total
                                )
                            else:
                                categorized_stats["code"]["metrics"][metric] = int(
                                    total
                                )
                        elif group == "command":
                            categorized_stats["command"]["metrics"][metric] = int(total)

        # 计算采纳率并添加到统计中
        commit_stats = categorized_stats["commit"]["metrics"]
        # 尝试多种可能的指标名称
        generated_commits = commit_stats.get(
            "commits_generated", commit_stats.get("commit_generated", 0)
        )
        accepted_commits = commit_stats.get(
            "commits_accepted",
            commit_stats.get("commit_accepted", commit_stats.get("commit_adopted", 0)),
        )
        rejected_commits = commit_stats.get(
            "commits_rejected", commit_stats.get("commit_rejected", 0)
        )

        # 如果有 generated 和 accepted，则使用这两个计算采纳率
        if generated_commits > 0 and accepted_commits > 0:
            adoption_rate = (accepted_commits / generated_commits) * 100
            categorized_stats["adoption"]["metrics"][
                "adoption_rate"
            ] = f"{adoption_rate:.1f}%"
            categorized_stats["adoption"]["metrics"][
                "commits_status"
            ] = f"{accepted_commits}/{generated_commits}"
        elif accepted_commits > 0 or rejected_commits > 0:
            # 否则使用 accepted 和 rejected 计算
            total_commits = accepted_commits + rejected_commits
            if total_commits > 0:
                adoption_rate = (accepted_commits / total_commits) * 100
                categorized_stats["adoption"]["metrics"][
                    "adoption_rate"
                ] = f"{adoption_rate:.1f}%"
                categorized_stats["adoption"]["metrics"][
                    "commits_status"
                ] = f"{accepted_commits}/{total_commits}"

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
                title="📊 Jarvis 使用统计",
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
                    parts.append(f"代码行数 {total_lines_modified:,} 行")

                if parts:
                    summary_content.append(f"📈 总计: {', '.join(parts)}")

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
                        encouragement = f"🎉 相当于节省了 {time_description} 的工作时间！"
                    elif work_months >= 1:
                        encouragement = f"🚀 相当于节省了 {time_description} 的工作时间！"
                    elif work_days >= 1:
                        encouragement = f"💪 相当于节省了 {time_description} 的工作时间！"
                    else:
                        encouragement = f"✨ 相当于节省了 {time_description} 的工作时间！"
                elif hours >= 1:
                    encouragement = f"⭐ 相当于节省了 {int(hours)} 小时的工作时间，积少成多，继续保持！"
                if encouragement:
                    summary_content.append(encouragement)

            # 3. 组合并打印
            render_items: List[RenderableType] = []
            if has_content:
                # 居中显示表格
                centered_table = Align.center(table)
                render_items.append(centered_table)

            if summary_content:
                summary_panel = Panel(
                    Text("\n".join(summary_content), justify="left"),
                    title="✨ 总体表现 ✨",
                    title_align="center",
                    border_style="green",
                    expand=False,
                )
                # 居中显示面板
                centered_panel = Align.center(summary_panel)
                render_items.append(centered_panel)

            if render_items:
                console = Console()
                render_group = Group(*render_items)
                console.print(render_group)
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
    # 1. 设置信号处理
    _setup_signal_handler()

    # 2. 统计命令使用
    count_cmd_usage()

    # 3. 显示欢迎信息
    if welcome_str:
        _show_welcome_message(welcome_str)

    # 4. 设置配置文件
    global g_config_file
    g_config_file = config_file
    load_config()

    # 5. 显示历史统计数据（仅在显示欢迎信息时显示）
    if welcome_str:
        _show_usage_stats()

    # 6. 检查git更新
    if _check_git_updates():
        os.execv(sys.executable, [sys.executable] + sys.argv)
        sys.exit(0)


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
            # 生成默认配置文件
            schema_path = (
                Path(__file__).parent.parent / "jarvis_data" / "config_schema.json"
            )
            if schema_path.exists():
                try:
                    config_file_path.parent.mkdir(parents=True, exist_ok=True)
                    generate_default_config(str(schema_path), str(config_file_path))
                    PrettyOutput.print(
                        f"已生成默认配置文件: {config_file_path}", OutputType.INFO
                    )
                    sys.exit(0)
                except Exception as e:
                    PrettyOutput.print(f"生成默认配置文件失败: {e}", OutputType.ERROR)
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
    content, config_data = _load_config_file(config_file)
    _ensure_schema_declaration(jarvis_dir, config_file, content, config_data)
    set_global_env_data(config_data)
    _process_env_variables(config_data)


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

    content = f"# yaml-language-server: $schema={schema}\n"
    content += yaml.dump(default_config, allow_unicode=True, sort_keys=False)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)


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
        f"检测到旧格式配置文件，旧格式以后将不再支持，请尽快迁移到新格式",
        OutputType.WARNING,
    )


def while_success(func: Callable[[], Any], sleep_time: float = 0.1) -> Any:
    """循环执行函数直到成功

    参数：
    func -- 要执行的函数
    sleep_time -- 每次失败后的等待时间（秒）

    返回：
    函数执行结果
    """
    while True:
        try:
            return func()
        except Exception as e:
            PrettyOutput.print(
                f"执行失败: {str(e)}, 等待 {sleep_time}s...", OutputType.WARNING
            )
            time.sleep(sleep_time)
            continue


def while_true(func: Callable[[], bool], sleep_time: float = 0.1) -> Any:
    """循环执行函数直到返回True

    参数:
        func: 要执行的函数，必须返回布尔值
        sleep_time: 每次失败后的等待时间(秒)

    返回:
        函数最终返回的True值

    注意:
        与while_success不同，此函数只检查返回是否为True，
        不捕获异常，异常会直接抛出
    """
    while True:
        ret = func()
        if ret:
            break
        PrettyOutput.print(f"执行失败, 等待 {sleep_time}s...", OutputType.WARNING)
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
    except Exception as e:
        return 0


def count_cmd_usage() -> None:
    """统计当前命令的使用次数"""
    import sys
    import os
    from jarvis.jarvis_stats.stats import StatsManager

    # 命令映射关系：将短命令映射到长命令
    command_mapping = {
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
    }

    # 从完整路径中提取命令名称
    cmd_path = sys.argv[0]
    cmd_name = os.path.basename(cmd_path)
    
    # 如果是短命令，映射到长命令
    if cmd_name in command_mapping:
        metric_name = command_mapping[cmd_name]
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


def copy_to_clipboard(text: str) -> None:
    """将文本复制到剪贴板，支持Windows、macOS和Linux

    参数:
        text: 要复制的文本
    """
    print("--- 剪贴板内容开始 ---")
    print(text)
    print("--- 剪贴板内容结束 ---")

    system = platform.system()

    # Windows系统
    if system == "Windows":
        try:
            # 使用Windows的clip命令
            process = subprocess.Popen(
                ["clip"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=True,
            )
            if process.stdin:
                process.stdin.write(text.encode("utf-8"))
                process.stdin.close()
            return
        except Exception as e:
            PrettyOutput.print(f"使用Windows clip命令时出错: {e}", OutputType.WARNING)

    # macOS系统
    elif system == "Darwin":
        try:
            process = subprocess.Popen(
                ["pbcopy"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if process.stdin:
                process.stdin.write(text.encode("utf-8"))
                process.stdin.close()
            return
        except Exception as e:
            PrettyOutput.print(f"使用macOS pbcopy命令时出错: {e}", OutputType.WARNING)

    # Linux系统
    else:
        # 尝试使用 xsel
        try:
            process = subprocess.Popen(
                ["xsel", "-b", "-i"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if process.stdin:
                process.stdin.write(text.encode("utf-8"))
                process.stdin.close()
            return
        except FileNotFoundError:
            pass  # xsel 未安装，继续尝试下一个
        except Exception as e:
            PrettyOutput.print(f"使用xsel时出错: {e}", OutputType.WARNING)

        # 尝试使用 xclip
        try:
            process = subprocess.Popen(
                ["xclip", "-selection", "clipboard"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if process.stdin:
                process.stdin.write(text.encode("utf-8"))
                process.stdin.close()
            return
        except FileNotFoundError:
            PrettyOutput.print(
                "xsel 和 xclip 均未安装, 无法复制到剪贴板", OutputType.WARNING
            )
        except Exception as e:
            PrettyOutput.print(f"使用xclip时出错: {e}", OutputType.WARNING)


def _pull_git_repo(repo_path: Path, repo_type: str):
    """对指定的git仓库执行git pull操作，并根据commit hash判断是否有更新。"""
    git_dir = repo_path / ".git"
    if not git_dir.is_dir():
        return

    PrettyOutput.print(f"正在更新{repo_type}库 '{repo_path.name}'...", OutputType.INFO)
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
            PrettyOutput.print(
                f"'{repo_path.name}' 未配置远程仓库，跳过更新。",
                OutputType.INFO,
            )
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
            PrettyOutput.print(
                f"检测到 '{repo_path.name}' 存在未提交的更改，跳过自动更新。",
                OutputType.WARNING,
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

        # 执行 git pull
        pull_result = subprocess.run(
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
            if pull_result.stdout.strip():
                PrettyOutput.print(pull_result.stdout.strip(), OutputType.INFO)
        else:
            PrettyOutput.print(
                f"{repo_type}库 '{repo_path.name}' 已是最新版本。", OutputType.INFO
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
        PrettyOutput.print(f"执行每日{repo_type}库更新检查...", OutputType.INFO)
        for repo_dir in repo_dirs:
            p_repo_dir = Path(repo_dir)
            if p_repo_dir.exists() and p_repo_dir.is_dir():
                _pull_git_repo(p_repo_dir, repo_type)
        try:
            last_check_file.write_text(str(time.time()))
        except IOError as e:
            PrettyOutput.print(f"无法写入git更新检查时间戳: {e}", OutputType.WARNING)
