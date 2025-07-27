# -*- coding: utf-8 -*-
"""Jarvis平台管理器主模块。

该模块提供了Jarvis平台管理器的主要入口点。
"""
import os
import sys
from typing import Any, Dict, List, Optional

import typer

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.input import get_multiline_input, get_single_line_input
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import init_env
from jarvis.jarvis_platform_manager.service import start_service

app = typer.Typer(help="Jarvis AI 平台")


@app.command("info")
def list_platforms() -> None:
    """列出所有支持的平台和模型。"""
    registry = PlatformRegistry.get_global_platform_registry()
    platforms = registry.get_available_platforms()

    PrettyOutput.section("Supported platforms and models", OutputType.SUCCESS)

    for platform_name in platforms:
        # Create platform instance
        platform = registry.create_platform(platform_name)
        if not platform:
            continue

        # Get the list of models supported by the platform
        try:
            models = platform.get_model_list()

            # Print platform name
            PrettyOutput.section(f"{platform_name}", OutputType.SUCCESS)

            output = ""
            # Print model list
            if models:
                for model_name, description in models:
                    if description:
                        output += f"  • {model_name} - {description}\n"
                    else:
                        output += f"  • {model_name}\n"
                PrettyOutput.print(output, OutputType.SUCCESS, lang="markdown")
            else:
                PrettyOutput.print("  • 没有可用的模型信息", OutputType.WARNING)

        except Exception as exc:
            PrettyOutput.print(
                f"获取 {platform_name} 的模型列表失败: {str(exc)}", OutputType.WARNING
            )


def chat_with_model(platform_name: str, model_name: str, system_prompt: str) -> None:
    """与指定平台和模型进行对话。"""
    registry = PlatformRegistry.get_global_platform_registry()
    conversation_history: List[Dict[str, str]] = []  # 存储对话记录

    # Create platform instance
    platform = registry.create_platform(platform_name)
    if not platform:
        PrettyOutput.print(f"创建平台 {platform_name} 失败", OutputType.WARNING)
        return

    try:
        # Set model
        platform.set_model_name(model_name)
        if system_prompt:
            platform.set_system_prompt(system_prompt)
        platform.set_suppress_output(False)
        PrettyOutput.print(
            f"连接到 {platform_name} 平台 {model_name} 模型", OutputType.SUCCESS
        )
        PrettyOutput.print(
            "可用命令: /bye - 退出, /clear - 清除会话, /upload - 上传文件, "
            "/shell - 执行命令, /save - 保存对话, /saveall - 保存所有对话, "
            "/save_session - 保存会话状态, /load_session - 加载会话状态",
            OutputType.INFO,
        )

        # Start conversation loop
        while True:
            # Get user input
            user_input = get_multiline_input("")

            # Check if input is cancelled
            if user_input.strip() == "/bye":
                PrettyOutput.print("再见!", OutputType.SUCCESS)
                break

            # Check if input is empty
            if not user_input.strip():
                PrettyOutput.print("检测到空输入，退出聊天", OutputType.INFO)
                break

            # Check if it is a clear session command
            if user_input.strip() == "/clear":
                try:
                    platform.reset()
                    platform.set_model_name(model_name)  # Reinitialize session
                    conversation_history = []  # 重置对话记录
                    PrettyOutput.print("会话已清除", OutputType.SUCCESS)
                except Exception as exc:
                    PrettyOutput.print(f"清除会话失败: {str(exc)}", OutputType.ERROR)
                continue

            # Check if it is an upload command
            if user_input.strip().startswith("/upload"):
                try:
                    file_path = user_input.strip()[8:].strip()
                    if not file_path:
                        PrettyOutput.print(
                            '请指定要上传的文件路径，例如: /upload /path/to/file 或 /upload "/path/with spaces/file"',
                            OutputType.WARNING,
                        )
                        continue

                    # Remove quotes if present
                    if (file_path.startswith('"') and file_path.endswith('"')) or (
                        file_path.startswith("'") and file_path.endswith("'")
                    ):
                        file_path = file_path[1:-1]

                    if not platform.support_upload_files():
                        PrettyOutput.print("平台不支持上传文件", OutputType.ERROR)
                        continue

                    PrettyOutput.print(f"正在上传文件: {file_path}", OutputType.INFO)
                    if platform.upload_files([file_path]):
                        PrettyOutput.print("文件上传成功", OutputType.SUCCESS)
                    else:
                        PrettyOutput.print("文件上传失败", OutputType.ERROR)
                except Exception as exc:
                    PrettyOutput.print(f"上传文件失败: {str(exc)}", OutputType.ERROR)
                continue

            # Check if it is a save command
            if user_input.strip().startswith("/save"):
                try:
                    file_path = user_input.strip()[5:].strip()
                    if not file_path:
                        PrettyOutput.print(
                            "请指定保存文件名，例如: /save last_message.txt",
                            OutputType.WARNING,
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
                        PrettyOutput.print(
                            f"最后一条消息内容已保存到 {file_path}", OutputType.SUCCESS
                        )
                    else:
                        PrettyOutput.print("没有可保存的消息", OutputType.WARNING)
                except Exception as exc:
                    PrettyOutput.print(f"保存消息失败: {str(exc)}", OutputType.ERROR)
                continue

            # Check if it is a saveall command
            if user_input.strip().startswith("/saveall"):
                try:
                    file_path = user_input.strip()[8:].strip()
                    if not file_path:
                        PrettyOutput.print(
                            "请指定保存文件名，例如: /saveall all_conversations.txt",
                            OutputType.WARNING,
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

                    PrettyOutput.print(
                        f"所有对话已保存到 {file_path}", OutputType.SUCCESS
                    )
                except Exception as exc:
                    PrettyOutput.print(
                        f"保存所有对话失败: {str(exc)}", OutputType.ERROR
                    )
                continue

            # Check if it is a save_session command
            if user_input.strip().startswith("/save_session"):
                try:
                    file_path = user_input.strip()[14:].strip()
                    if not file_path:
                        PrettyOutput.print(
                            "请指定保存会话的文件名，例如: /save_session session.json",
                            OutputType.WARNING,
                        )
                        continue

                    # Remove quotes if present
                    if (file_path.startswith('"') and file_path.endswith('"')) or (
                        file_path.startswith("'") and file_path.endswith("'")
                    ):
                        file_path = file_path[1:-1]

                    if platform.save(file_path):
                        PrettyOutput.print(
                            f"会话已保存到 {file_path}", OutputType.SUCCESS
                        )
                    else:
                        PrettyOutput.print("保存会话失败", OutputType.ERROR)
                except Exception as exc:
                    PrettyOutput.print(f"保存会话失败: {str(exc)}", OutputType.ERROR)
                continue

            # Check if it is a load_session command
            if user_input.strip().startswith("/load_session"):
                try:
                    file_path = user_input.strip()[14:].strip()
                    if not file_path:
                        PrettyOutput.print(
                            "请指定加载会话的文件名，例如: /load_session session.json",
                            OutputType.WARNING,
                        )
                        continue

                    # Remove quotes if present
                    if (file_path.startswith('"') and file_path.endswith('"')) or (
                        file_path.startswith("'") and file_path.endswith("'")
                    ):
                        file_path = file_path[1:-1]

                    if platform.restore(file_path):
                        conversation_history = []  # Clear local history after loading
                        PrettyOutput.print(
                            f"会话已从 {file_path} 加载", OutputType.SUCCESS
                        )
                    else:
                        PrettyOutput.print("加载会话失败", OutputType.ERROR)
                except Exception as exc:
                    PrettyOutput.print(f"加载会话失败: {str(exc)}", OutputType.ERROR)
                continue

            # Check if it is a shell command
            if user_input.strip().startswith("/shell"):
                try:
                    command = user_input.strip()[6:].strip()
                    if not command:
                        PrettyOutput.print(
                            "请指定要执行的shell命令，例如: /shell ls -l",
                            OutputType.WARNING,
                        )
                        continue

                    PrettyOutput.print(f"执行命令: {command}", OutputType.INFO)
                    return_code = os.system(command)
                    if return_code == 0:
                        PrettyOutput.print("命令执行完成", OutputType.SUCCESS)
                    else:
                        PrettyOutput.print(
                            f"命令执行失败(返回码: {return_code})", OutputType.ERROR
                        )
                except Exception as exc:
                    PrettyOutput.print(f"执行命令失败: {str(exc)}", OutputType.ERROR)
                continue

            try:
                conversation_history.append(
                    {"role": "user", "content": user_input}
                )  # 记录用户输入
                # Send to model and get reply
                response = platform.chat_until_success(user_input)
                if not response:
                    PrettyOutput.print("没有有效的回复", OutputType.WARNING)
                else:
                    conversation_history.append(
                        {"role": "assistant", "content": response}
                    )  # 记录模型回复

            except Exception as exc:
                PrettyOutput.print(f"聊天失败: {str(exc)}", OutputType.ERROR)

    except typer.Exit:
        raise
    except Exception as exc:
        PrettyOutput.print(f"初始化会话失败: {str(exc)}", OutputType.ERROR)
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
        PrettyOutput.print(
            "请指定平台和模型。使用 'jarvis info' 查看可用平台和模型。",
            OutputType.WARNING,
        )
        return False
    return True


@app.command("chat")
def chat_command(
    platform: Optional[str] = typer.Option(None, "--platform", "-p", help="指定要使用的平台"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="指定要使用的模型"),
) -> None:
    """与指定平台和模型聊天。"""
    if not validate_platform_model(platform, model):
        return
    chat_with_model(platform, model, "") # type: ignore


@app.command("service")
def service_command(
    host: str = typer.Option("127.0.0.1", help="服务主机地址 (默认: 127.0.0.1)"),
    port: int = typer.Option(8000, help="服务端口 (默认: 8000)"),
    platform: Optional[str] = typer.Option(
        None, "-p", "--platform", help="指定默认平台，当客户端未指定平台时使用"
    ),
    model: Optional[str] = typer.Option(
        None, "-m", "--model", help="指定默认模型，当客户端未指定平台时使用"
    ),
) -> None:
    """启动OpenAI兼容的API服务。"""
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
        PrettyOutput.print(f"角色配置文件 {config_path} 不存在", OutputType.ERROR)
        return {}

    with open(config_path, "r", encoding="utf-8", errors="ignore") as file_obj:
        try:
            config = yaml.safe_load(file_obj)
            return config if config else {}
        except yaml.YAMLError as exc:
            PrettyOutput.print(f"角色配置文件解析失败: {str(exc)}", OutputType.ERROR)
            return {}


@app.command("role")
def role_command(
    config_file: str = typer.Option(
        "~/.jarvis/roles.yaml",
        "--config",
        "-c",
        help="角色配置文件路径(YAML格式，默认: ~/.jarvis/roles.yaml)",
    ),
    platform: Optional[str] = typer.Option(
        None, "--platform", "-p", help="指定要使用的平台，覆盖角色配置"
    ),
    model: Optional[str] = typer.Option(
        None, "--model", "-m", help="指定要使用的模型，覆盖角色配置"
    ),
) -> None:
    """加载角色配置文件并开始对话。"""
    config_path = os.path.expanduser(config_file)
    config = load_role_config(config_path)
    if not config or "roles" not in config:
        PrettyOutput.print("无效的角色配置文件", OutputType.ERROR)
        return

    # 显示可选角色列表
    PrettyOutput.section("可用角色", OutputType.SUCCESS)
    output_str = "\n".join(
        [
            f"{i}. {role['name']} - {role.get('description', '')}"
            for i, role in enumerate(config["roles"], 1)
        ]
    )
    PrettyOutput.print(output_str, OutputType.INFO)

    # 让用户选择角色
    try:
        choice = int(get_single_line_input("请选择角色(输入编号): "))
        selected_role = config["roles"][choice - 1]
    except (ValueError, IndexError):
        PrettyOutput.print("无效的选择", OutputType.ERROR)
        return

    # 初始化平台和模型
    platform_name = platform or selected_role["platform"]
    model_name = model or selected_role["model"]
    system_prompt = selected_role.get("system_prompt", "")

    # 开始对话
    PrettyOutput.print(f"已选择角色: {selected_role['name']}", OutputType.SUCCESS)
    chat_with_model(platform_name, model_name, system_prompt)


def main() -> None:
    """Jarvis平台管理器的主入口点。"""
    init_env("欢迎使用 Jarvis-PlatformManager，您的平台管理助手已准备就绪！")
    app()


if __name__ == "__main__":
    main()
