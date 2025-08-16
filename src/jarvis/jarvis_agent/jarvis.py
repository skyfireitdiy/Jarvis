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
from jarvis.jarvis_utils.input import user_confirm, get_single_line_input
import os
import sys
import subprocess
from pathlib import Path
import yaml  # type: ignore
from rich.table import Table
from rich.console import Console

app = typer.Typer(help="Jarvis AI 助手")


@app.callback(invoke_without_command=True)
def run_cli(
    ctx: typer.Context,
    llm_type: str = typer.Option(
        "normal",
        "-t",
        "--llm-type",
        help="使用的LLM类型，可选值：'normal'（普通）或 'thinking'（思考模式）",
    ),
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
) -> None:
    """Jarvis AI assistant command-line interface."""
    if ctx.invoked_subcommand is not None:
        return

    # 处理配置文件编辑
    if edit:
        ConfigEditor.edit_config(config_file)
        return

    # 处理方法论分享
    if share_methodology:
        init_env("", config_file=config_file)  # 初始化配置但不显示欢迎信息
        methodology_manager = MethodologyShareManager()
        methodology_manager.run()
        return

    # 处理工具分享
    if share_tool:
        init_env("", config_file=config_file)  # 初始化配置但不显示欢迎信息
        tool_manager = ToolShareManager()
        tool_manager.run()
        return

    # 在初始化环境前检测Git仓库，并可选择自动切换到代码开发模式（jca）
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
                    if llm_type:
                        args += ["-t", llm_type]
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

    # 在进入默认通用代理前，列出内置配置供选择（agent/multi_agent/roles）
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
            dir_path = builtin_root / cat
            if not dir_path.exists():
                continue
            for fpath in sorted(dir_path.glob(pattern)):
                # 解析YAML以获取可读名称/描述（失败时静默降级为文件名）
                name = fpath.stem
                desc = ""
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                        data = yaml.safe_load(fh) or {}
                    if isinstance(data, dict):
                        name = data.get("name") or data.get("title") or name
                        desc = data.get("description") or data.get("desc") or ""
                        if cat == "roles" and isinstance(data.get("roles"), list):
                            if not desc:
                                desc = f"{len(data['roles'])} 个角色"
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
                                lines.append(f"{rname} - {rdesc}" if rdesc else rname)
                        details = "\n".join([ln for ln in lines if ln])
                    # 如果没有角色详情，退回到统计信息
                    if not details and isinstance((data or {}).get("roles"), list):
                        details = f"{len(data['roles'])} 个角色"

                options.append(
                    {
                        "category": cat,
                        "cmd": cmd,
                        "file": str(fpath),
                        "name": str(name),
                        "desc": str(desc),
                        "details": str(details),
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
            table.add_column("描述/详情", style="white")

            for idx, opt in enumerate(options, 1):
                category = opt.get("category", "")
                name = opt.get("name", "")
                file_path = opt.get("file", "")
                # multi_agent: 优先显示顶层描述
                # roles: 显示每个角色名称与描述（多行）
                # 其他：显示 desc
                if category == "roles" and opt.get("details"):
                    detail = opt["details"]
                else:
                    detail = opt.get("desc", "")

                table.add_row(str(idx), category, name, file_path, detail)

            Console().print(table)

            choice = get_single_line_input(
                "选择要启动的配置编号，直接回车使用默认通用代理(jvs): ", default=""
            )

            if choice.strip():
                try:
                    index = int(choice.strip())
                    if 1 <= index <= len(options):
                        sel = options[index - 1]
                        args = []

                        if sel["category"] == "agent":
                            # jarvis-agent 支持 -f/--config（全局配置）与 -c/--agent-definition
                            args = [sel["cmd"], "-c", sel["file"]]
                            if llm_type:
                                args += ["--llm-type", llm_type]
                            if model_group:
                                args += ["-g", model_group]
                            if config_file:
                                args += ["-f", config_file]
                            if task:
                                args += ["--task", task]

                        elif sel["category"] == "multi_agent":
                            # jarvis-multi-agent 需要 -c/--config，用户输入通过 -i/--input 传递
                            args = [sel["cmd"], "-c", sel["file"]]
                            if task:
                                args += ["-i", task]

                        elif sel["category"] == "roles":
                            # jarvis-platform-manager role 子命令，支持 -c/-t/-g
                            args = [sel["cmd"], "role", "-c", sel["file"]]
                            if llm_type:
                                args += ["-t", llm_type]
                            if model_group:
                                args += ["-g", model_group]

                        if args:
                            PrettyOutput.print(
                                f"正在启动: {' '.join(args)}", OutputType.INFO
                            )
                            os.execvp(args[0], args)
                except Exception:
                    # 任何异常都不影响默认流程
                    pass
    except Exception:
        # 静默忽略内置配置扫描错误，不影响主流程
        pass

    # 初始化环境
    init_env(
        "欢迎使用 Jarvis AI 助手，您的智能助理已准备就绪！", config_file=config_file
    )

    # 运行主流程
    try:
        agent_manager = AgentManager(
            llm_type=llm_type,
            model_group=model_group,
            tool_group=tool_group,
            restore_session=restore_session,
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
