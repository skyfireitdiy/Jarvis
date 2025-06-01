# -*- coding: utf-8 -*-
import argparse
import os

import yaml

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_utils.input import get_multiline_input
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import init_env


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


def main():
    """Main entry point for Jarvis agent"""
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Jarvis AI assistant")
    parser.add_argument(
        "-f", "--config", type=str, required=False, help="Path to agent config file"
    )
    parser.add_argument(
        "-c", "--agent_definition", type=str, help="Path to agent definition file"
    )
    parser.add_argument("-t", "--task", type=str, help="Initial task to execute")
    args = parser.parse_args()

    # Initialize environment
    init_env(
        "欢迎使用 Jarvis AI 助手，您的智能助理已准备就绪！", config_file=args.config
    )

    # Load configuration
    config = load_config(args.agent_definition) if args.agent_definition else {}

    # Create and run agent
    try:
        agent = Agent(**config)

        # Run agent with initial task if specified
        if args.task:
            PrettyOutput.print(f"执行初始任务: {args.task}", OutputType.INFO)
            agent.run(args.task)
            return 0

        try:
            user_input = get_multiline_input("请输入你的任务（输入空行退出）:")
            if not user_input:
                return 0
            agent.set_addon_prompt(
                "如果有必要，请先指定出行动计划，然后根据计划一步步执行，如果任务过于复杂，可以拆分子Agent进行执行，拆的子Agent需要掌握所有必要的任务信息，否则无法执行"
            )
            agent.run(user_input)
        except Exception as e:
            PrettyOutput.print(f"错误: {str(e)}", OutputType.ERROR)

    except Exception as e:
        PrettyOutput.print(f"初始化错误: {str(e)}", OutputType.ERROR)
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
