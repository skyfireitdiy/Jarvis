# -*- coding: utf-8 -*-
import os
from typing import Optional

import typer
import yaml  # type: ignore[import-untyped]

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_utils.input import get_multiline_input
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import init_env

app = typer.Typer(help="Jarvis AI 助手")


def load_config(config_path: str) -> dict:
    """从YAML文件加载配置

    参数:
        config_path: YAML配置文件的路径

    返回:
        dict: 配置字典
    """
    if not os.path.exists(config_path):
        PrettyOutput.print(
            f"配置文件 {config_path} 不存在，使用默认配置", OutputType.WARNING
        )
        return {}

    with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
        try:
            config = yaml.safe_load(f)
            return config if config else {}
        except yaml.YAMLError as e:
            PrettyOutput.print(f"配置文件解析失败: {str(e)}", OutputType.ERROR)
            return {}


@app.command()
def cli(
    config_file: Optional[str] = typer.Option(
        None, "-f", "--config", help="代理配置文件路径"
    ),
    agent_definition: Optional[str] = typer.Option(
        None, "-c", "--agent-definition", help="代理定义文件路径"
    ),
    task: Optional[str] = typer.Option(None, "-T", "--task", help="初始任务内容"),

    model_group: Optional[str] = typer.Option(
        None, "-g", "--llm-group", help="使用的模型组，覆盖配置文件中的设置"
    ),
):
    """Main entry point for Jarvis agent"""
    # Initialize environment
    init_env(
        "欢迎使用 Jarvis AI 助手，您的智能助理已准备就绪！", config_file=config_file
    )

    # Load configuration
    config = load_config(agent_definition) if agent_definition else {}

    # Override config with command-line arguments if provided

    if model_group:
        config["model_group"] = model_group

    # Create and run agent
    try:
        agent = Agent(**config)

        # Run agent with initial task if specified
        if task:
            PrettyOutput.print(f"执行初始任务: {task}", OutputType.INFO)
            agent.run(task)
            return

        try:
            user_input = get_multiline_input("请输入你的任务（输入空行退出）:")
            if not user_input:
                return
            agent.set_addon_prompt(
                "如果有必要，请先指定出行动计划，然后根据计划一步步执行，如果任务过于复杂，可以拆分子Agent进行执行，拆的子Agent需要掌握所有必要的任务信息，否则无法执行"
            )
            agent.run(user_input)
        except KeyboardInterrupt:
            # 用户主动取消输入，正常退出
            return
        except typer.Exit:
            # 来自输入流程的正常退出
            return
        except Exception as e:
            PrettyOutput.print(f"错误: {str(e)}", OutputType.ERROR)

    except typer.Exit:
        return
    except Exception as e:
        PrettyOutput.print(f"初始化错误: {str(e)}", OutputType.ERROR)
        raise typer.Exit(code=1)


def main() -> None:
    """Application entry point."""
    app()


if __name__ == "__main__":
    main()
