# -*- coding: utf-8 -*-
from typing import Optional

import typer
import yaml  # type: ignore[import-untyped]
import os

from jarvis.jarvis_multi_agent import MultiAgent
from jarvis.jarvis_utils.input import get_multiline_input
from jarvis.jarvis_utils.utils import init_env
from jarvis.jarvis_utils.config import set_config
from jarvis.jarvis_utils.output import OutputType, PrettyOutput

app = typer.Typer(help="多智能体系统启动器")


@app.command()
def cli(
    config: str = typer.Option(..., "--config", "-c", help="YAML配置文件路径"),
    user_input: Optional[str] = typer.Option(
        None, "--input", "-i", help="用户输入（可选）"
    ),
    non_interactive: bool = typer.Option(
        False, "-n", "--non-interactive", help="启用非交互模式：用户无法与命令交互，脚本执行超时限制为5分钟"
    ),
):
    """从YAML配置文件初始化并运行多智能体系统"""
    # CLI 标志：非交互模式（不依赖配置文件）
    if non_interactive:
        try:
            os.environ["JARVIS_NON_INTERACTIVE"] = "true"
        except Exception:
            pass
        # 注意：全局配置同步在 init_env 之后执行，避免被覆盖
    # 非交互模式要求从命令行传入任务
    if non_interactive and not (user_input and str(user_input).strip()):
        PrettyOutput.print(
            "非交互模式已启用：必须使用 --input 传入任务内容，因多行输入不可用。",
            OutputType.ERROR,
        )
        raise typer.Exit(code=2)
    init_env("欢迎使用 Jarvis-MultiAgent，您的多智能体系统已准备就绪！")
    
    # 在初始化环境后同步 CLI 选项到全局配置，避免被 init_env 覆盖
    try:
        if non_interactive:
            set_config("JARVIS_NON_INTERACTIVE", True)
    except Exception:
        # 静默忽略同步异常，不影响主流程
        pass

    try:
        with open(config, "r", errors="ignore") as f:
            config_data = yaml.safe_load(f)

        # 获取agents配置
        agents_config = config_data.get("agents", [])

        main_agent_name = config_data.get("main_agent", "")
        if not main_agent_name:
            raise ValueError("必须指定main_agent作为主智能体")

        # 创建并运行多智能体系统
        multi_agent = MultiAgent(agents_config, main_agent_name)
        final_input = (
            user_input
            if user_input is not None
            else get_multiline_input("请输入内容（输入空行结束）：")
        )
        if not final_input:
            return
        multi_agent.run(final_input)

    except KeyboardInterrupt:
        return
    except typer.Exit:
        return
    except (ValueError, RuntimeError, yaml.YAMLError) as e:
        PrettyOutput.print(f"错误: {str(e)}", OutputType.ERROR)
        raise typer.Exit(code=1)


def main() -> None:
    """Application entry point."""
    app()


if __name__ == "__main__":
    main()
