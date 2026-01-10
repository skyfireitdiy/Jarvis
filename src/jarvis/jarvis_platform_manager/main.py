"""Jarvis平台管理器主模块。

该模块提供了Jarvis平台管理器的主要入口点。
"""

import os
import sys

from rich import box
from rich.panel import Panel
from rich.console import Console

from jarvis.jarvis_utils.output import PrettyOutput

# -*- coding: utf-8 -*-
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

import typer

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_platform_manager.service import start_service
from jarvis.jarvis_utils.config import get_llm_config
from jarvis.jarvis_utils.config import get_normal_model_name
from jarvis.jarvis_utils.config import get_normal_platform_name
from jarvis.jarvis_utils.fzf import fzf_select
from jarvis.jarvis_utils.input import get_multiline_input
from jarvis.jarvis_utils.input import get_single_line_input
from jarvis.jarvis_utils.utils import init_env

app = typer.Typer(help="Jarvis AI 平台")


@app.command("info")
def list_platforms(
    llm_group: Optional[str] = typer.Option(
        None, "-g", "--llm-group", help="使用的模型组，覆盖配置文件中的设置"
    ),
) -> None:
    """列出所有支持的平台和模型，支持交互式选择查看特定平台的详细信息。"""
    registry = PlatformRegistry.get_global_platform_registry()
    platform_names = registry.get_available_platforms()

    if not platform_names:
        PrettyOutput.auto_print("⚠️ 没有可用的平台")
        return

    # 获取默认模型组配置，或使用指定的模型组
    current_llm_group = llm_group
    if current_llm_group:
        platform_from_config = get_normal_platform_name(current_llm_group)
        model_from_config = get_normal_model_name(current_llm_group)
        llm_config = get_llm_config("normal", current_llm_group)  # 获取完整配置
        PrettyOutput.auto_print(f"✅ 从模型组 '{current_llm_group}' 获取的配置信息:")
        PrettyOutput.auto_print(f"  平台: {platform_from_config}")
        PrettyOutput.auto_print(f"  模型: {model_from_config}")

        # 只显示配置中指定的平台信息
        platform_names = [platform_from_config]

        # 使用配置创建平台实例并显示详细信息
        try:
            platform_instance = registry.create_platform(
                platform_from_config, llm_config
            )
            if platform_instance:
                models = platform_instance.get_model_list()
                PrettyOutput.auto_print(f"✅ {platform_from_config}")
                if models:
                    for model_name, description in models:
                        if description:
                            PrettyOutput.auto_print(f"  • {model_name} - {description}")
                        else:
                            PrettyOutput.auto_print(f"  • {model_name}")
                else:
                    PrettyOutput.auto_print("⚠️   • 没有可用的模型信息")
            else:
                PrettyOutput.auto_print(f"⚠️ 创建 {platform_from_config} 平台失败")
        except Exception:
            PrettyOutput.auto_print(f"⚠️ 创建 {platform_from_config} 平台失败")
        return
    else:
        # 获取默认模型组配置
        default_llm_group = get_normal_platform_name(None)
        default_model = get_normal_model_name(None)

        # 显示默认配置信息
        PrettyOutput.auto_print("✅ 默认配置信息:")
        PrettyOutput.auto_print(f"  平台: {default_llm_group}")
        PrettyOutput.auto_print(f"  模型: {default_model}")

        # 显示默认平台的详细信息
        try:
            default_llm_config = get_llm_config("normal", None)
            platform_instance = registry.create_platform(
                default_llm_group, default_llm_config
            )
            if platform_instance:
                models = platform_instance.get_model_list()
                PrettyOutput.auto_print(f"✅ {default_llm_group} 平台详情")
                if models:
                    for model_name, description in models:
                        if description:
                            PrettyOutput.auto_print(f"  • {model_name} - {description}")
                        else:
                            PrettyOutput.auto_print(f"  • {model_name}")
                else:
                    PrettyOutput.auto_print("⚠️   • 没有可用的模型信息")
            else:
                PrettyOutput.auto_print(f"⚠️ 创建 {default_llm_group} 平台失败")
        except Exception:
            PrettyOutput.auto_print(f"⚠️ 创建 {default_llm_group} 平台失败")
        return


def chat_with_model(
    platform_name: str,
    model_name: str,
    system_prompt: str,
    llm_group: Optional[str] = None,
) -> None:
    """与指定平台和模型进行对话。

    参数:
        platform_name: 平台名称
        model_name: 模型名称
        system_prompt: 系统提示语
        llm_group: 使用的模型组，覆盖配置文件中的设置

    """
    registry = PlatformRegistry.get_global_platform_registry()
    conversation_history: List[Dict[str, str]] = []  # 存储对话记录

    # 获取 llm_config，确保传递 api_key 等配置
    llm_config = get_llm_config("normal", llm_group)

    # Create platform instance
    platform = registry.create_platform(platform_name, llm_config)
    if platform:
        platform.set_model_name(model_name)

    if not platform:
        PrettyOutput.auto_print(f"⚠️ 创建平台 {platform_name} 失败")
        return

    try:
        # Set model
        platform.set_model_name(model_name)
        if system_prompt:
            platform.set_system_prompt(system_prompt)
        platform.set_suppress_output(False)
        PrettyOutput.auto_print(f"✅ 连接到 {platform_name} 平台 {model_name} 模型")
        PrettyOutput.auto_print(
            "ℹ️ 可用命令: /bye - 退出, /clear - 清除会话, /upload - 上传文件, "
            "/shell - 执行命令, /save - 保存对话, /saveall - 保存所有对话, "
            "/save_session - 保存会话状态, /load_session - 加载会话状态"
        )

        # Start conversation loop
        while True:
            # Get user input
            user_input = get_multiline_input("")

            # Check if input is cancelled
            if user_input.strip() == "/bye":
                PrettyOutput.auto_print("✅ 再见!")
                break

            # Check if input is empty
            if not user_input.strip():
                PrettyOutput.auto_print("ℹ️ 检测到空输入，退出聊天")
                break

            # Parse command and arguments
            stripped_input = user_input.strip()
            parts = stripped_input.split(None, 1)
            command = parts[0] if parts else ""
            args = parts[1] if len(parts) > 1 else ""

            # Check if it is a clear session command
            if command == "/clear":
                try:
                    platform.reset()
                    platform.set_model_name(model_name)  # Reinitialize session
                    conversation_history = []  # 重置对话记录
                    PrettyOutput.auto_print("✅ 会话已清除")
                except Exception as exc:
                    PrettyOutput.auto_print(f"❌ 清除会话失败: {str(exc)}")
                continue

            # Check if it is an upload command
            if command == "/upload":
                try:
                    file_path = args
                    if not file_path:
                        PrettyOutput.auto_print(
                            '⚠️ 请指定要上传的文件路径，例如: /upload /path/to/file 或 /upload "/path/with spaces/file"'
                        )
                        continue

                    # Remove quotes if present
                    if (file_path.startswith('"') and file_path.endswith('"')) or (
                        file_path.startswith("'") and file_path.endswith("'")
                    ):
                        file_path = file_path[1:-1]

                    PrettyOutput.auto_print(f"ℹ️ 尝试上传文件: {file_path}")
                    PrettyOutput.auto_print(
                        "⚠️ 文件上传功能已移除，平台不再支持文件上传"
                    )
                except Exception as exc:
                    PrettyOutput.auto_print(f"❌ 上传文件失败: {str(exc)}")
                continue

            # Check if it is a save command
            if command == "/save":
                try:
                    file_path = args
                    if not file_path:
                        PrettyOutput.auto_print(
                            "⚠️ 请指定保存文件名，例如: /save last_message.txt"
                        )
                        continue

                    # Remove quotes if present
                    if (file_path.startswith('"') and file_path.endswith('"')) or (
                        file_path.startswith("'") and file_path.endswith("'")
                    ):
                        file_path = file_path[1:-1]

                    # Write last message content to file
                    if conversation_history:
                        with open(file_path, "w", encoding="utf-8") as file_obj:
                            last_entry = conversation_history[-1]
                            file_obj.write(f"{last_entry['content']}\n")
                        PrettyOutput.auto_print(
                            f"✅ 最后一条消息内容已保存到 {file_path}"
                        )
                    else:
                        PrettyOutput.auto_print("⚠️ 没有可保存的消息")
                except Exception as exc:
                    PrettyOutput.auto_print(f"❌ 保存消息失败: {str(exc)}")
                continue

            # Check if it is a saveall command
            if command == "/saveall":
                try:
                    file_path = args
                    if not file_path:
                        PrettyOutput.auto_print(
                            "⚠️ 请指定保存文件名，例如: /saveall all_conversations.txt"
                        )
                        continue

                    # Remove quotes if present
                    if (file_path.startswith('"') and file_path.endswith('"')) or (
                        file_path.startswith("'") and file_path.endswith("'")
                    ):
                        file_path = file_path[1:-1]

                    # Write full conversation history to file
                    with open(file_path, "w", encoding="utf-8") as file_obj:
                        for entry in conversation_history:
                            file_obj.write(f"{entry['role']}: {entry['content']}\n\n")

                    PrettyOutput.auto_print(f"✅ 所有对话已保存到 {file_path}")
                except Exception as exc:
                    PrettyOutput.auto_print(f"❌ 保存所有对话失败: {str(exc)}")
                continue

            # Check if it is a save_session command
            if command == "/save_session":
                try:
                    file_path = args
                    if not file_path:
                        PrettyOutput.auto_print(
                            "⚠️ 请指定保存会话的文件名，例如: /save_session session.json"
                        )
                        continue

                    # Remove quotes if present
                    if (file_path.startswith('"') and file_path.endswith('"')) or (
                        file_path.startswith("'") and file_path.endswith("'")
                    ):
                        file_path = file_path[1:-1]

                    if platform.save(file_path):
                        PrettyOutput.auto_print(f"✅ 会话已保存到 {file_path}")
                    else:
                        PrettyOutput.auto_print("❌ 保存会话失败")
                except Exception as exc:
                    PrettyOutput.auto_print(f"❌ 保存会话失败: {str(exc)}")
                continue

            # Check if it is a load_session command
            if command == "/load_session":
                try:
                    file_path = args
                    if not file_path:
                        PrettyOutput.auto_print(
                            "⚠️ 请指定加载会话的文件名，例如: /load_session session.json"
                        )
                        continue

                    # Remove quotes if present
                    if (file_path.startswith('"') and file_path.endswith('"')) or (
                        file_path.startswith("'") and file_path.endswith("'")
                    ):
                        file_path = file_path[1:-1]

                    if platform.restore(file_path):
                        conversation_history = []  # Clear local history after loading
                        PrettyOutput.auto_print(f"✅ 会话已从 {file_path} 加载")
                    else:
                        PrettyOutput.auto_print("❌ 加载会话失败")
                except Exception as exc:
                    PrettyOutput.auto_print(f"❌ 加载会话失败: {str(exc)}")
                continue

            # Check if it is a shell command
            if command == "/shell":
                try:
                    shell_command = args
                    if not shell_command:
                        PrettyOutput.auto_print(
                            "⚠️ 请指定要执行的shell命令，例如: /shell ls -l"
                        )
                        continue

                    PrettyOutput.auto_print(f"ℹ️ 执行命令: {shell_command}")
                    return_code = os.system(shell_command)
                    if return_code == 0:
                        pass  # 命令执行成功，不显示提示
                    else:
                        PrettyOutput.auto_print(
                            f"❌ 命令执行失败(返回码: {return_code})"
                        )
                except Exception as exc:
                    PrettyOutput.auto_print(f"❌ 执行命令失败: {str(exc)}")
                continue

            try:
                conversation_history.append(
                    {"role": "user", "content": user_input}
                )  # 记录用户输入
                # Send to model and get reply
                response = platform.chat_until_success(user_input)
                if not response:
                    PrettyOutput.auto_print("⚠️ 没有有效的回复")
                else:
                    # 使用 Panel 打印 LLM 响应
                    console = Console()
                    panel = Panel(
                        response,
                        title=f"[bold cyan]{platform_name} · {model_name}[/bold cyan]",
                        border_style="bright_blue",
                        box=box.ROUNDED,
                        expand=True,
                    )
                    console.print(panel)
                    conversation_history.append(
                        {"role": "assistant", "content": response}
                    )  # 记录模型回复

            except Exception as exc:
                PrettyOutput.auto_print(f"❌ 聊天失败: {str(exc)}")

    except typer.Exit:
        raise
    except Exception as exc:
        PrettyOutput.auto_print(f"❌ 初始化会话失败: {str(exc)}")
        sys.exit(1)
    finally:
        # Clean up resources
        try:
            platform.reset()
        except Exception:
            pass


def validate_platform_model(platform: Optional[str], model: Optional[str]) -> bool:
    """验证平台和模型参数。

    参数:
        platform: 平台名称。
        model: 模型名称。

    返回:
        bool: 如果平台和模型有效返回True，否则返回False。
    """
    if not platform or not model:
        PrettyOutput.auto_print(
            "⚠️ 请指定平台和模型。使用 'jarvis info' 查看可用平台和模型。"
        )
        return False
    return True


@app.command("chat")
def chat_command(
    llm_group: Optional[str] = typer.Option(
        None, "-g", "--llm-group", help="使用的模型组，覆盖配置文件中的设置"
    ),
) -> None:
    """与指定平台和模型聊天。"""
    # 从config获取默认值
    platform = get_normal_platform_name(llm_group)
    model = get_normal_model_name(llm_group)

    if not validate_platform_model(platform, model):
        return
    chat_with_model(platform, model, "", llm_group)


@app.command("service")
def service_command(
    host: str = typer.Option("127.0.0.1", help="服务主机地址 (默认: 127.0.0.1)"),
    port: int = typer.Option(8000, help="服务端口 (默认: 8000)"),
) -> None:
    """启动OpenAI兼容的API服务。"""
    # 从config获取默认值
    platform = get_normal_platform_name()
    model = get_normal_model_name()
    start_service(host=host, port=port, default_platform=platform, default_model=model)


def load_role_config(config_path: str) -> Dict[str, Any]:
    """从YAML文件加载角色配置

    参数:
        config_path: YAML配置文件的路径

    返回:
        dict: 角色配置字典
    """
    import yaml

    if not os.path.exists(config_path):
        PrettyOutput.auto_print(f"❌ 角色配置文件 {config_path} 不存在")
        return {}

    with open(config_path, "r", encoding="utf-8", errors="ignore") as file_obj:
        try:
            config = yaml.safe_load(file_obj)
            return config if config else {}
        except yaml.YAMLError as exc:
            PrettyOutput.auto_print(f"❌ 角色配置文件解析失败: {str(exc)}")
            return {}


@app.command("role")
def role_command(
    config_file: str = typer.Option(
        "~/.jarvis/roles.yaml",
        "--config",
        "-c",
        help="角色配置文件路径(YAML格式，默认: ~/.jarvis/roles.yaml)",
    ),
    llm_group: Optional[str] = typer.Option(
        None, "-g", "--llm-group", help="使用的模型组，覆盖配置文件中的设置"
    ),
) -> None:
    """加载角色配置文件并开始对话。"""
    config_path = os.path.expanduser(config_file)
    config = load_role_config(config_path)
    if not config or "roles" not in config:
        PrettyOutput.auto_print("❌ 无效的角色配置文件")
        return

    # 显示可选角色列表
    PrettyOutput.auto_print("✅ 可用角色")
    output_str = "\n".join(
        [
            f"{i}. {role['name']} - {role.get('description', '')}"
            for i, role in enumerate(config["roles"], 1)
        ]
    )
    PrettyOutput.auto_print(f"ℹ️ {output_str}")

    # 让用户选择角色（优先 fzf，回退编号输入）
    selected_role = None
    fzf_options = [
        f"{i:>3} | {role['name']} - {role.get('description', '')}"
        for i, role in enumerate(config["roles"], 1)
    ]
    selected_str = fzf_select(fzf_options, prompt="选择角色编号 (Enter退出) > ")
    if selected_str:
        try:
            num_part = selected_str.split("|", 1)[0].strip()
            idx = int(num_part)
            if 1 <= idx <= len(config["roles"]):
                selected_role = config["roles"][idx - 1]
        except Exception:
            selected_role = None

    if selected_role is None:
        raw_choice = get_single_line_input("请选择角色(输入编号，直接回车退出): ")
        if not raw_choice.strip():
            PrettyOutput.auto_print("ℹ️ 已取消，退出程序")
            raise typer.Exit(code=0)
        try:
            choice = int(raw_choice)
            selected_role = config["roles"][choice - 1]
        except (ValueError, IndexError):
            PrettyOutput.auto_print("❌ 无效的选择")
            return

    # 初始化平台和模型
    # 如果提供了 llm_group，则从配置中获取
    # 否则使用角色配置中的platform和model
    if llm_group:
        platform_name = get_normal_platform_name(llm_group)
    else:
        platform_name = selected_role.get("platform")
        if not platform_name:
            # 如果角色配置中没有platform，使用默认配置
            platform_name = get_normal_platform_name()

    if llm_group:
        model_name = get_normal_model_name(llm_group)
    else:
        model_name = selected_role.get("model")
        if not model_name:
            # 如果角色配置中没有model，使用默认配置
            model_name = get_normal_model_name()

    system_prompt = selected_role.get("system_prompt", "")

    # 开始对话
    PrettyOutput.auto_print(f"✅ 已选择角色: {selected_role['name']}")
    chat_with_model(platform_name, model_name, system_prompt, llm_group)


def main() -> None:
    """Jarvis平台管理器的主入口点。"""
    init_env()
    app()


if __name__ == "__main__":
    main()
