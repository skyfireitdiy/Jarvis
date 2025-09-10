# -*- coding: utf-8 -*-
"""Jarvis AI 助手主入口模块"""
from typing import Optional

import typer

from jarvis.jarvis_agent import OutputType, PrettyOutput
from jarvis.jarvis_agent.agent_manager import AgentManager
from jarvis.jarvis_agent.config_editor import ConfigEditor
from jarvis.jarvis_agent.methodology_share_manager import MethodologyShareManager
from jarvis.jarvis_agent.tool_share_manager import ToolShareManager
from jarvis.jarvis_utils.utils import init_env
from jarvis.jarvis_utils.config import (
    is_enable_git_repo_jca_switch,
    is_enable_builtin_config_selector,
    get_agent_definition_dirs,
    get_multi_agent_dirs,
    get_roles_dirs,
)
import jarvis.jarvis_utils.utils as jutils
from jarvis.jarvis_utils.input import user_confirm, get_single_line_input
from jarvis.jarvis_utils.fzf import fzf_select
import os
import subprocess
from pathlib import Path
import yaml  # type: ignore
from rich.table import Table
from rich.console import Console

app = typer.Typer(help="Jarvis AI 助手")


def print_commands_overview() -> None:
    """打印命令与快捷方式总览表。"""
    try:
        cmd_table = Table(show_header=True, header_style="bold magenta")
        cmd_table.add_column("命令", style="bold")
        cmd_table.add_column("快捷方式", style="cyan")
        cmd_table.add_column("功能描述", style="white")

        cmd_table.add_row("jarvis", "jvs", "通用AI代理，适用于多种任务")
        cmd_table.add_row("jarvis-agent", "ja", "AI代理基础功能，处理会话和任务")
        cmd_table.add_row(
            "jarvis-code-agent",
            "jca",
            "专注于代码分析、修改和生成的代码代理",
        )
        cmd_table.add_row("jarvis-code-review", "jcr", "智能代码审查工具")
        cmd_table.add_row(
            "jarvis-git-commit",
            "jgc",
            "自动化分析代码变更并生成规范的Git提交信息",
        )
        cmd_table.add_row("jarvis-git-squash", "jgs", "Git提交历史整理工具")
        cmd_table.add_row(
            "jarvis-platform-manager",
            "jpm",
            "管理和测试不同的大语言模型平台",
        )
        cmd_table.add_row("jarvis-multi-agent", "jma", "多智能体协作系统")
        cmd_table.add_row("jarvis-tool", "jt", "工具管理与调用系统")
        cmd_table.add_row("jarvis-methodology", "jm", "方法论知识库管理")
        cmd_table.add_row(
            "jarvis-rag",
            "jrg",
            "构建和查询本地化的RAG知识库",
        )
        cmd_table.add_row("jarvis-smart-shell", "jss", "实验性的智能Shell功能")
        cmd_table.add_row(
            "jarvis-stats",
            "jst",
            "通用统计模块，支持记录和可视化任意指标数据",
        )
        cmd_table.add_row(
            "jarvis-memory-organizer",
            "jmo",
            "记忆管理工具，支持整理、合并、导入导出记忆",
        )

        Console().print(cmd_table)
    except Exception:
        # 静默忽略渲染异常，避免影响主流程
        pass


def handle_edit_option(edit: bool, config_file: Optional[str]) -> bool:
    """处理配置文件编辑选项，返回是否已处理并需提前结束。"""
    if edit:
        ConfigEditor.edit_config(config_file)
        return True
    return False


def handle_share_methodology_option(
    share_methodology: bool, config_file: Optional[str]
) -> bool:
    """处理方法论分享选项，返回是否已处理并需提前结束。"""
    if share_methodology:
        init_env("", config_file=config_file)  # 初始化配置但不显示欢迎信息
        methodology_manager = MethodologyShareManager()
        methodology_manager.run()
        return True
    return False


def handle_share_tool_option(share_tool: bool, config_file: Optional[str]) -> bool:
    """处理工具分享选项，返回是否已处理并需提前结束。"""
    if share_tool:
        init_env("", config_file=config_file)  # 初始化配置但不显示欢迎信息
        tool_manager = ToolShareManager()
        tool_manager.run()
        return True
    return False


def handle_interactive_config_option(
    interactive_config: bool, config_file: Optional[str]
) -> bool:
    """处理交互式配置选项，返回是否已处理并需提前结束。"""
    if not interactive_config:
        return False
    try:
        config_path = (
            Path(config_file)
            if config_file is not None
            else Path(os.path.expanduser("~/.jarvis/config.yaml"))
        )
        if not config_path.exists():
            # 无现有配置时，进入完整引导流程（该流程内会写入并退出）
            jutils._interactive_config_setup(config_path)
            return True

        # 读取现有配置
        _, config_data = jutils._load_config_file(str(config_path))

        # 复用 utils 中的交互式配置逻辑，对所有项进行询问，默认值来自现有配置
        changed = jutils._collect_optional_config_interactively(
            config_data, ask_all=True
        )
        if not changed:
            PrettyOutput.print("没有需要更新的配置项，保持现有配置。", OutputType.INFO)
            return True

        # 剔除与 schema 默认值一致的键，保持配置精简
        try:
            jutils._prune_defaults_with_schema(config_data)
        except Exception:
            pass

        # 生成/保留 schema 头
        header = ""
        try:
            with open(config_path, "r", encoding="utf-8") as rf:
                first_line = rf.readline()
                if first_line.startswith("# yaml-language-server: $schema="):
                    header = first_line
        except Exception:
            header = ""

        yaml_str = yaml.dump(config_data, allow_unicode=True, sort_keys=False)
        if not header:
            try:
                schema_path = Path(
                    os.path.relpath(
                        Path(__file__).resolve().parents[1]
                        / "jarvis_data"
                        / "config_schema.json",
                        start=str(config_path.parent),
                    )
                )
                header = f"# yaml-language-server: $schema={schema_path}\n"
            except Exception:
                header = ""

        with open(config_path, "w", encoding="utf-8") as wf:
            if header:
                wf.write(header)
            wf.write(yaml_str)

        PrettyOutput.print(f"配置已更新: {config_path}", OutputType.SUCCESS)
        return True
    except Exception as e:
        PrettyOutput.print(f"交互式配置失败: {e}", OutputType.ERROR)
        return True


def preload_config_for_flags(config_file: Optional[str]) -> None:
    """预加载配置（仅用于读取功能开关），不会显示欢迎信息或影响后续 init_env。"""
    try:
        jutils.g_config_file = config_file
        jutils.load_config()
    except Exception:
        # 静默忽略配置加载异常
        pass


def try_switch_to_jca_if_git_repo(
    model_group: Optional[str],
    tool_group: Optional[str],
    config_file: Optional[str],
    restore_session: bool,
    task: Optional[str],
) -> None:
    """在初始化环境前检测Git仓库，并可选择自动切换到代码开发模式（jca）。"""
    if is_enable_git_repo_jca_switch():
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
            )
            if res.returncode == 0:
                git_root = res.stdout.strip()
                if git_root and os.path.isdir(git_root):
                    PrettyOutput.print(
                        f"检测到当前位于 Git 仓库: {git_root}", OutputType.INFO
                    )
                    if user_confirm(
                        "检测到Git仓库，是否切换到代码开发模式（jca）？", default=False
                    ):
                        # 构建并切换到 jarvis-code-agent 命令，传递兼容参数
                        args = ["jarvis-code-agent"]
                        if model_group:
                            args += ["-g", model_group]
                        if tool_group:
                            args += ["-G", tool_group]
                        if config_file:
                            args += ["-f", config_file]
                        if restore_session:
                            args += ["--restore-session"]
                        if task:
                            args += ["-r", task]
                        PrettyOutput.print(
                            "正在切换到 'jca'（jarvis-code-agent）以进入代码开发模式...",
                            OutputType.INFO,
                        )
                        os.execvp(args[0], args)
        except Exception:
            # 静默忽略检测异常，不影响主流程
            pass


def handle_builtin_config_selector(
    model_group: Optional[str],
    tool_group: Optional[str],
    config_file: Optional[str],
    task: Optional[str],
) -> None:
    """在进入默认通用代理前，列出内置配置供选择（agent/multi_agent/roles）。"""
    if is_enable_builtin_config_selector():
        try:
            # 优先使用项目内置目录，若不存在则回退到指定的绝对路径
            builtin_root = Path(__file__).resolve().parents[3] / "builtin"
            if not builtin_root.exists():
                builtin_root = Path("/home/skyfire/code/Jarvis/builtin")

            categories = [
                ("agent", "jarvis-agent", "*.yaml"),
                ("multi_agent", "jarvis-multi-agent", "*.yaml"),
                ("roles", "jarvis-platform-manager", "*.yaml"),
            ]

            options = []
            for cat, cmd, pattern in categories:
                # 构建待扫描目录列表：优先使用配置中的目录，其次回退到内置目录
                search_dirs = []
                try:
                    if cat == "agent":
                        search_dirs.extend(
                            [
                                Path(os.path.expanduser(os.path.expandvars(str(p))))
                                for p in get_agent_definition_dirs()
                                if p
                            ]
                        )
                    elif cat == "multi_agent":
                        search_dirs.extend(
                            [
                                Path(os.path.expanduser(os.path.expandvars(str(p))))
                                for p in get_multi_agent_dirs()
                                if p
                            ]
                        )
                    elif cat == "roles":
                        search_dirs.extend(
                            [
                                Path(os.path.expanduser(os.path.expandvars(str(p))))
                                for p in get_roles_dirs()
                                if p
                            ]
                        )
                except Exception:
                    # 忽略配置读取异常
                    pass

                # 追加内置目录
                search_dirs.append(builtin_root / cat)

                # 去重并保留顺序
                unique_dirs = []
                seen = set()
                for d in search_dirs:
                    try:
                        key = str(Path(d).resolve())
                    except Exception:
                        key = str(d)
                    if key not in seen:
                        seen.add(key)
                        unique_dirs.append(Path(d))

                # 每日自动更新配置目录（如目录为Git仓库则执行git pull，每日仅一次）
                try:
                    jutils.daily_check_git_updates([str(p) for p in unique_dirs], cat)
                except Exception:
                    # 忽略更新过程中的所有异常，避免影响主流程
                    pass

                for dir_path in unique_dirs:
                    if not dir_path.exists():
                        continue
                    for fpath in sorted(dir_path.glob(pattern)):
                        # 解析YAML以获取可读名称/描述（失败时静默降级为文件名）
                        name = fpath.stem
                        desc = ""
                        roles_count = 0
                        try:
                            with open(
                                fpath, "r", encoding="utf-8", errors="ignore"
                            ) as fh:
                                data = yaml.safe_load(fh) or {}
                            if isinstance(data, dict):
                                name = data.get("name") or data.get("title") or name
                                desc = data.get("description") or data.get("desc") or ""
                                if cat == "roles" and isinstance(
                                    data.get("roles"), list
                                ):
                                    roles_count = len(data["roles"])
                                    if not desc:
                                        desc = f"{roles_count} 个角色"
                        except Exception:
                            # 忽略解析错误，使用默认显示
                            pass

                        # 为 roles 构建详细信息（每个角色的名称与描述）
                        details = ""
                        if cat == "roles":
                            roles = (data or {}).get("roles", [])
                            if isinstance(roles, list):
                                lines = []
                                for role in roles:
                                    if isinstance(role, dict):
                                        rname = str(role.get("name", "") or "")
                                        rdesc = str(role.get("description", "") or "")
                                        lines.append(
                                            f"{rname} - {rdesc}" if rdesc else rname
                                        )
                                details = "\n".join([ln for ln in lines if ln])
                            # 如果没有角色详情，退回到统计信息
                            if not details and isinstance(
                                (data or {}).get("roles"), list
                            ):
                                details = f"{len(data['roles'])} 个角色"

                        options.append(
                            {
                                "category": cat,
                                "cmd": cmd,
                                "file": str(fpath),
                                "name": str(name),
                                "desc": str(desc),
                                "details": str(details),
                                "roles_count": int(roles_count),
                            }
                        )

            if options:
                PrettyOutput.section("可用的内置配置", OutputType.SUCCESS)
                # 使用 rich Table 呈现
                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("No.", style="cyan", no_wrap=True)
                table.add_column("类型", style="green", no_wrap=True)
                table.add_column("名称", style="bold")
                table.add_column("文件", style="dim")
                table.add_column("描述", style="white")

                for idx, opt in enumerate(options, 1):
                    category = str(opt.get("category", ""))
                    name = str(opt.get("name", ""))
                    file_path = str(opt.get("file", ""))
                    # 描述列显示配置描述；若为 roles 同时显示角色数量与列表
                    if category == "roles":
                        count = opt.get("roles_count")
                        details_val = opt.get("details", "")
                        parts: list[str] = []
                        if isinstance(count, int) and count > 0:
                            parts.append(f"{count} 个角色")
                        if isinstance(details_val, str) and details_val:
                            parts.append(details_val)
                        desc_display = "\n".join(parts) if parts else ""
                    else:
                        desc_display = str(opt.get("desc", ""))
                    table.add_row(str(idx), category, name, file_path, desc_display)

                Console().print(table)

                # Try to use fzf for selection if available (include No. to support number-based filtering)
                fzf_options = [
                    f"{idx:>3} | {opt['category']:<12} | {opt['name']:<30} | {opt.get('desc', '')}"
                    for idx, opt in enumerate(options, 1)
                ]
                selected_str = fzf_select(
                    fzf_options, prompt="选择要启动的配置编号 (ESC跳过) > "
                )

                choice_index = -1
                if selected_str:
                    # Try to parse leading number before first '|'
                    try:
                        num_part = selected_str.split("|", 1)[0].strip()
                        selected_index = int(num_part)
                        if 1 <= selected_index <= len(options):
                            choice_index = selected_index - 1
                    except Exception:
                        # Fallback to equality matching if parsing fails
                        for i, fzf_opt in enumerate(fzf_options):
                            if fzf_opt == selected_str:
                                choice_index = i
                                break
                else:
                    # Fallback to manual input if fzf is not used or available
                    choice = get_single_line_input(
                        "选择要启动的配置编号，直接回车使用默认通用代理(jvs): ", default=""
                    )
                    if choice.strip():
                        try:
                            selected_index = int(choice.strip())
                            if 1 <= selected_index <= len(options):
                                choice_index = selected_index - 1
                        except ValueError:
                            pass  # Invalid input

                if choice_index != -1:
                    try:
                        sel = options[choice_index]
                        args: list[str] = []

                        if sel["category"] == "agent":
                            # jarvis-agent 支持 -f/--config（全局配置）与 -c/--agent-definition
                            args = [str(sel["cmd"]), "-c", str(sel["file"])]
                            if model_group:
                                args += ["-g", str(model_group)]
                            if config_file:
                                args += ["-f", str(config_file)]
                            if task:
                                args += ["--task", str(task)]

                        elif sel["category"] == "multi_agent":
                            # jarvis-multi-agent 需要 -c/--config，用户输入通过 -i/--input 传递
                            args = [str(sel["cmd"]), "-c", str(sel["file"])]
                            if task:
                                args += ["-i", str(task)]

                        elif sel["category"] == "roles":
                            # jarvis-platform-manager role 子命令，支持 -c/-t/-g
                            args = [str(sel["cmd"]), "role", "-c", str(sel["file"])]
                            if model_group:
                                args += ["-g", str(model_group)]

                        if args:
                            PrettyOutput.print(
                                f"正在启动: {' '.join(args)}", OutputType.INFO
                            )
                            os.execvp(args[0], args)
                    except Exception:
                        # 任何异常都不影响默认流程
                        pass
                else:
                    # User pressed Enter or provided invalid input
                    pass
        except Exception:
            # 静默忽略内置配置扫描错误，不影响主流程
            pass


@app.callback(invoke_without_command=True)
def run_cli(
    ctx: typer.Context,
    task: Optional[str] = typer.Option(
        None, "-T", "--task", help="从命令行直接输入任务内容"
    ),
    model_group: Optional[str] = typer.Option(
        None, "-g", "--llm-group", help="使用的模型组，覆盖配置文件中的设置"
    ),
    tool_group: Optional[str] = typer.Option(
        None, "-G", "--tool-group", help="使用的工具组，覆盖配置文件中的设置"
    ),
    config_file: Optional[str] = typer.Option(
        None, "-f", "--config", help="自定义配置文件路径"
    ),
    restore_session: bool = typer.Option(
        False,
        "--restore-session",
        help="从 .jarvis/saved_session.json 恢复会话",
    ),
    edit: bool = typer.Option(False, "-e", "--edit", help="编辑配置文件"),
    share_methodology: bool = typer.Option(
        False, "--share-methodology", help="分享本地方法论到中心方法论仓库"
    ),
    share_tool: bool = typer.Option(
        False, "--share-tool", help="分享本地工具到中心工具仓库"
    ),
    interactive_config: bool = typer.Option(
        False,
        "-I",
        "--interactive-config",
        help="启动交互式配置向导（基于当前配置补充设置）",
    ),
    disable_methodology_analysis: bool = typer.Option(
        False,
        "-D",
        "--disable-methodology-analysis",
        help="禁用方法论和任务分析（覆盖配置文件设置）",
    ),
) -> None:
    """Jarvis AI assistant command-line interface."""
    if ctx.invoked_subcommand is not None:
        return

    # 使用 rich 输出命令与快捷方式总览
    print_commands_overview()

    # 处理配置文件编辑
    if handle_edit_option(edit, config_file):
        return

    # 处理方法论分享
    if handle_share_methodology_option(share_methodology, config_file):
        return

    # 处理工具分享
    if handle_share_tool_option(share_tool, config_file):
        return

    # 交互式配置（基于现有配置补充设置）
    if handle_interactive_config_option(interactive_config, config_file):
        return

    # 预加载配置（仅用于读取功能开关），不会显示欢迎信息或影响后续 init_env
    preload_config_for_flags(config_file)

    # 在初始化环境前检测Git仓库，并可选择自动切换到代码开发模式（jca）
    try_switch_to_jca_if_git_repo(
        model_group, tool_group, config_file, restore_session, task
    )

    # 在进入默认通用代理前，列出内置配置供选择（agent/multi_agent/roles）
    handle_builtin_config_selector(model_group, tool_group, config_file, task)

    # 初始化环境
    init_env(
        "欢迎使用 Jarvis AI 助手，您的智能助理已准备就绪！", config_file=config_file
    )

    # 运行主流程
    try:
        agent_manager = AgentManager(
            model_group=model_group,
            tool_group=tool_group,
            restore_session=restore_session,
            use_methodology=False if disable_methodology_analysis else None,
            use_analysis=False if disable_methodology_analysis else None,
        )
        agent_manager.initialize()
        agent_manager.run_task(task)
    except typer.Exit:
        raise
    except Exception as err:  # pylint: disable=broad-except
        PrettyOutput.print(f"初始化错误: {str(err)}", OutputType.ERROR)
        raise typer.Exit(code=1)


def main() -> None:
    """Application entry point."""
    app()


if __name__ == "__main__":
    main()
