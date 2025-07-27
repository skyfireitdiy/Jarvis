# -*- coding: utf-8 -*-
from typing import Optional

import typer
import yaml

from jarvis.jarvis_multi_agent import MultiAgent
from jarvis.jarvis_utils.input import get_multiline_input
from jarvis.jarvis_utils.utils import init_env

app = typer.Typer(help="多智能体系统启动器")


@app.command()
def cli(
    config: str = typer.Option(..., "--config", "-c", help="YAML配置文件路径"),
    user_input: Optional[str] = typer.Option(None, "--input", "-i", help="用户输入（可选）"),
):
    """从YAML配置文件初始化并运行多智能体系统"""
    init_env("欢迎使用 Jarvis-MultiAgent，您的多智能体系统已准备就绪！")

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
            raise typer.Exit(code=0)
        multi_agent.run(final_input)

    except typer.Exit:
        raise
    except (ValueError, RuntimeError, yaml.YAMLError) as e:
        PrettyOutput.print(f"错误: {str(e)}", OutputType.ERROR)
        raise typer.Exit(code=1)


def main() -> None:
    """Application entry point."""
    app()


if __name__ == "__main__":
    main()
