import yaml
from jarvis.jarvis_multi_agent import MultiAgent
from jarvis.jarvis_utils.utils import init_env
from jarvis.jarvis_utils.input import get_multiline_input

def main():
    """从YAML配置文件初始化并运行多智能体系统

    Returns:
        最终处理结果
    """
    init_env()
    import argparse
    parser = argparse.ArgumentParser(description="多智能体系统启动器")
    parser.add_argument("--config", "-c", required=True, help="YAML配置文件路径")
    parser.add_argument("--input", "-i", help="用户输入（可选）")
    args = parser.parse_args()

    try:
        with open(args.config, 'r', errors="ignore") as f:
            config_data = yaml.safe_load(f)

        # 获取agents配置
        agents_config = config_data.get('agents', [])

        main_agent_name = config_data.get('main_agent', '')
        if not main_agent_name:
            raise ValueError("必须指定main_agent作为主智能体")

        # 创建并运行多智能体系统
        multi_agent = MultiAgent(agents_config, main_agent_name)
        user_input = args.input if args.input is not None else get_multiline_input("请输入内容（输入空行结束）：")
        if user_input == "":
            return
        return multi_agent.run(user_input)

    except yaml.YAMLError as e:
        raise ValueError(f"YAML配置文件解析错误: {str(e)}")
    except Exception as e:
        raise RuntimeError(f"多智能体系统初始化失败: {str(e)}")

if __name__ == "__main__":
    result = main()
