# -*- coding: utf-8 -*-
"""
Quick Config CLI 工具
用于快速配置 LLM 平台信息（Claude/OpenAI）到 Jarvis 配置文件的 llms 部分
"""

import json
import yaml
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
import requests

from .output import PrettyOutput
from .input import get_single_line_input, user_confirm

app = typer.Typer(help="快速配置 LLM 平台信息到 Jarvis 配置文件")
console = Console()


@app.command()
def quick_config(
    platform: Optional[str] = typer.Option(
        None, "--platform", "-p", help="LLM平台类型 (claude/openai)"
    ),
    base_url: Optional[str] = typer.Option(None, "--url", "-u", help="API基础URL"),
    api_key: Optional[str] = typer.Option(None, "--key", "-k", help="API密钥"),
    config_name: Optional[str] = typer.Option(
        None, "--name", "-n", help="配置名称，如果未指定将使用平台名称"
    ),
    output_file: Optional[Path] = typer.Option(
        None, "--output", "-o", help="输出配置文件路径，默认为~/.jarvis/config.yaml"
    ),
):
    """快速配置 LLM 平台信息到 Jarvis 配置文件的 llms 部分"""

    # 提示用户输入缺失的参数
    if platform is None:
        platform = get_single_line_input("请输入LLM平台类型 (claude/openai):")
    if base_url is None:
        base_url = get_single_line_input("请输入API基础URL:")
    if api_key is None:
        api_key = get_single_line_input("请输入API密钥:")

    # 验证平台类型
    platform = platform.lower().strip()
    if platform not in ["claude", "openai"]:
        PrettyOutput.auto_print(
            f"❌ 不支持的平台类型: {platform}，仅支持 claude 和 openai"
        )
        raise typer.Exit(code=1)

    # 如果未指定配置名称，使用平台名称
    if not config_name:
        config_name = platform

    PrettyOutput.auto_print(
        f"🚀 开始配置 {platform.upper()} 平台，配置名称: {config_name}"
    )

    # 测试API连接并获取模型列表
    models = get_models(platform, base_url, api_key)
    if not models:
        PrettyOutput.auto_print("⚠️  无法获取模型列表")

        # 提示用户是否手动输入模型名称
        use_manual_input = user_confirm("是否手动输入模型名称？", default=True)

        if use_manual_input:
            model_input = get_single_line_input(
                "请输入模型名称（多个模型用逗号分隔，如: gpt-4o,gpt-3.5-turbo）:"
            )
            # 清理输入并按逗号分割
            models = [m.strip() for m in model_input.split(",") if m.strip()]
            if not models:
                PrettyOutput.auto_print("❌ 未输入有效模型名称，配置已取消")
                raise typer.Exit(code=0)
        else:
            PrettyOutput.auto_print("❌ 未提供模型名称，配置已取消")
            raise typer.Exit(code=0)

    PrettyOutput.auto_print(
        f"📋 可用模型: {', '.join(models[:10])}{'...' if len(models) > 10 else ''}"
    )

    # 询问用户是否配置所有模型
    if len(models) > 1:
        console.print("[bold]可用模型列表:[/]")
        for i, model in enumerate(models, 1):
            console.print(f"  {i}. {model}")

        configure_all = user_confirm("是否配置所有模型？", default=False)

        if configure_all:
            selected_models = models
        else:
            model_choices = get_single_line_input(
                "请输入要配置的模型序号（用逗号分隔）:"
            )
            try:
                indices = [int(x.strip()) - 1 for x in model_choices.split(",")]
                selected_models = []
                for idx in indices:
                    if 0 <= idx < len(models):
                        selected_models.append(models[idx])
                    else:
                        PrettyOutput.auto_print(f"❌ 无效的模型序号: {idx + 1}")
                        raise typer.Exit(code=1)
                if not selected_models:
                    PrettyOutput.auto_print("❌ 没有选择任何有效模型")
                    raise typer.Exit(code=1)
            except ValueError:
                PrettyOutput.auto_print("❌ 请输入有效的数字序号，用逗号分隔")
                raise typer.Exit(code=1)
    else:
        # 单个模型情况，直接选择
        selected_models = [models[0]]

    PrettyOutput.auto_print(
        f"✅ 已选择 {len(selected_models)} 个模型: {', '.join(selected_models)}"
    )

    # 选择默认模型
    if len(selected_models) == 1:
        default_model = selected_models[0]
        PrettyOutput.auto_print(f"🎯 默认模型: {default_model}")
    else:
        console.print("[bold]请选择默认模型:[/]")
        for i, model in enumerate(selected_models, 1):
            console.print(f"  {i}. {model}")

        default_choice = get_single_line_input("请输入默认模型序号:")
        try:
            default_idx = int(default_choice.strip()) - 1
            if 0 <= default_idx < len(selected_models):
                default_model = selected_models[default_idx]
                PrettyOutput.auto_print(f"🎯 默认模型: {default_model}")
            else:
                PrettyOutput.auto_print(f"❌ 无效的模型序号: {default_choice}")
                raise typer.Exit(code=1)
        except ValueError:
            PrettyOutput.auto_print("❌ 请输入有效的数字序号")
            raise typer.Exit(code=1)

    # 测试模型API连通性
    PrettyOutput.auto_print(f"🔍 正在测试模型 {default_model} 的API连通性...")
    success, error_msg = test_model_connection(
        platform, base_url, api_key, default_model
    )

    if success:
        PrettyOutput.auto_print("✅ API连通性测试通过")
    else:
        PrettyOutput.auto_print(f"❌ API连通性测试失败: {error_msg}")

        # 询问用户是否仍要保存配置
        force_save = user_confirm("测试失败，是否仍要保存配置到文件？", default=False)
        if not force_save:
            PrettyOutput.auto_print("👋 已取消配置保存")
            raise typer.Exit(code=0)
        else:
            PrettyOutput.auto_print("⚠️  将保存配置（未通过测试）")

    # 输入默认最大token数
    default_max_tokens = 128000
    while True:
        max_tokens_input = get_single_line_input(
            f"请输入默认最大token数 (默认: {default_max_tokens}):"
        )
        if not max_tokens_input.strip():
            max_tokens = default_max_tokens
            PrettyOutput.auto_print(f"✅ 使用默认最大token数: {max_tokens}")
            break
        try:
            max_tokens = int(max_tokens_input.strip())
            if max_tokens <= 0:
                PrettyOutput.auto_print("❌ 最大token数必须为正整数")
                continue
            PrettyOutput.auto_print(f"✅ 设置最大token数为: {max_tokens}")
            break
        except ValueError:
            PrettyOutput.auto_print("❌ 请输入有效的正整数")

    # 设置默认输出文件
    if output_file is None:
        jarvis_dir = Path.home() / ".jarvis"
        output_file = jarvis_dir / "config.yaml"

    # 确保输出目录存在
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # 读取现有配置
    config: dict = {}
    if output_file.exists():
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                if output_file.suffix in (".yaml", ".yml"):
                    config = yaml.safe_load(f) or {}
                else:
                    config = json.load(f)
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️  无法读取现有配置文件 {output_file}: {e}")
            if not user_confirm("是否继续创建新配置？", default=True):
                raise typer.Exit(code=0)

    # 初始化llms部分
    if "llms" not in config:
        config["llms"] = {}

    # 初始化llm_groups部分
    if "llm_groups" not in config:
        config["llm_groups"] = {}

    # 为每个选择的模型创建配置
    for i, model in enumerate(selected_models):
        # 统一使用配置名称+模型名的方式避免命名冲突，保持单模型和多模型配置结构一致
        model_config_name = f"{config_name}_{model.replace('.', '_').replace('-', '_')}"

        # 根据平台类型生成正确的配置键名
        if platform == "openai":
            llm_config_dict = {
                "openai_api_key": api_key,
                "openai_api_base": base_url,
            }
        elif platform == "claude":
            llm_config_dict = {
                "anthropic_api_key": api_key,
                "anthropic_base_url": base_url,
            }
        else:
            llm_config_dict = {
                f"{platform}_api_key": api_key,
                f"{platform}_base_url": base_url,
            }

        llm_config = {
            "platform": platform,
            "model": model,
            "max_input_token_count": max_tokens,
            "llm_config": llm_config_dict,
        }

        # 添加模型配置
        config["llms"][model_config_name] = llm_config

        # 如果是默认模型，创建llm_groups配置
        if model == default_model:
            # 使用模型名称作为组名，替换特殊字符
            group_name = model.replace(".", "_").replace("-", "_")
            # 创建模型组配置
            config["llm_groups"][group_name] = {"normal_llm": model_config_name}
            PrettyOutput.auto_print(
                f"✅ 已创建模型组 '{group_name}'，使用 {model_config_name} 作为默认模型"
            )

    PrettyOutput.auto_print(f"✅ 已为 {len(selected_models)} 个模型创建配置")

    # 设置默认模型组
    default_group_name = default_model.replace(".", "_").replace("-", "_")
    config["llm_group"] = default_group_name
    PrettyOutput.auto_print(f"✅ 已设置默认模型组为 '{default_group_name}'")

    # 保存配置文件
    try:
        if output_file.suffix in (".yaml", ".yml"):
            with open(output_file, "w", encoding="utf-8") as f:
                yaml.safe_dump(
                    config,
                    f,
                    allow_unicode=True,
                    default_flow_style=False,
                    sort_keys=False,
                )
        else:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

        PrettyOutput.auto_print(f"✅ 配置已保存到 {output_file}")

    except Exception as e:
        PrettyOutput.auto_print(f"❌ 保存配置失败: {e}")
        raise typer.Exit(code=1)


def test_model_connection(
    platform: str, base_url: str, api_key: str, model: str
) -> tuple[bool, str]:
    """测试模型API连通性

    Args:
        platform: 平台类型 (claude/openai)
        base_url: API基础URL
        api_key: API密钥
        model: 模型名称

    Returns:
        (是否成功, 错误信息)
    """
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        if platform == "openai":
            # OpenAI API 测试
            url = f"{base_url.rstrip('/')}/chat/completions"
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 5,
            }
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            if response.status_code == 200:
                return True, ""
            else:
                error_msg = (
                    response.json().get("error", {}).get("message", response.text)
                )
                return (
                    False,
                    f"API返回错误 (状态码: {response.status_code}): {error_msg}",
                )

        elif platform == "claude":
            # Claude API 测试
            url = f"{base_url.rstrip('/')}/messages"
            payload = {
                "model": model,
                "max_tokens": 5,
                "messages": [{"role": "user", "content": "Hi"}],
            }
            headers["anthropic-version"] = "2023-06-01"
            # Claude 使用 x-api-key 而不是 Authorization
            headers.pop("Authorization")
            headers["x-api-key"] = api_key

            response = requests.post(url, headers=headers, json=payload, timeout=10)
            if response.status_code == 200:
                return True, ""
            else:
                error_data = response.json()
                error_msg = error_data.get("error", {}).get("message", response.text)
                return (
                    False,
                    f"API返回错误 (状态码: {response.status_code}): {error_msg}",
                )

    except requests.exceptions.Timeout:
        return False, "请求超时，请检查网络连接或API服务是否可用"
    except requests.exceptions.ConnectionError:
        return False, "无法连接到API服务，请检查base_url是否正确"
    except Exception as e:
        return False, f"测试失败，错误: {str(e)}"

    return False, "未知的平台类型"


def get_models(platform: str, base_url: str, api_key: str) -> list:
    """获取平台的模型列表"""
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        if platform == "openai":
            url = f"{base_url}/models" if not base_url.endswith("/models") else base_url
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                models = [item["id"] for item in data.get("data", [])]
                return models
        elif platform == "claude":
            # Claude API doesn't have a direct models endpoint, use a common model list
            # For Claude, we'll return a list of known Claude models
            known_claude_models = [
                "claude-3-5-sonnet-latest",
                "claude-3-5-sonnet-20241022",
                "claude-3-5-sonnet-20240620",
                "claude-3-opus-latest",
                "claude-3-opus-20240229",
                "claude-3-sonnet-latest",
                "claude-3-sonnet-20240229",
                "claude-3-haiku-latest",
                "claude-3-haiku-20240307",
            ]
            return known_claude_models
    except Exception as e:
        PrettyOutput.auto_print(f"⚠️  获取模型列表失败: {e}")

    return []


if __name__ == "__main__":
    app()
