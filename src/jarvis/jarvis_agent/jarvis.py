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

app = typer.Typer(help="Jarvis AI 助手")


@app.callback(invoke_without_command=True)
def run_cli(
    ctx: typer.Context,
    llm_type: str = typer.Option(
        "normal",
        "-t", "--llm_type",
        help="使用的LLM类型，可选值：'normal'（普通）或 'thinking'（思考模式）",
    ),
    task: Optional[str] = typer.Option(
        None, "-T", "--task", help="从命令行直接输入任务内容"
    ),
    model_group: Optional[str] = typer.Option(
        None, "-g", "--llm_group", help="使用的模型组，覆盖配置文件中的设置"
    ),
    tool_group: Optional[str] = typer.Option(
        None, "-G", "--tool_group", help="使用的工具组，覆盖配置文件中的设置"
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
        manager = MethodologyShareManager()
        manager.run()
        return

    # 处理工具分享
    if share_tool:
        init_env("", config_file=config_file)  # 初始化配置但不显示欢迎信息
        manager = ToolShareManager()
        manager.run()
        return

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
