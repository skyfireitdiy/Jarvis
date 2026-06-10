# -*- coding: utf-8 -*-
"""
Quick Config CLI 工具
用于快速配置 LLM 平台信息（Claude/OpenAI）到 Jarvis 配置文件的 llms 部分
"""

import yaml  # type: ignore[import-untyped]
from pathlib import Path
import typer
from rich.console import Console
import requests

from .output import PrettyOutput
from .input import get_single_line_input, user_confirm
from .utils import init_env

app = typer.Typer(help="快速配置 LLM 平台信息到 Jarvis 配置文件")
console = Console()


@app.command()
def quick_config():
    """快速配置 LLM 平台信息到 Jarvis 配置文件的 llms 部分"""
    try:
        run_quick_config()
    except SystemExit:
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


def run_quick_config():
    """快速配置 LLM 平台信息（不依赖 typer，可供内置命令调用）"""
    init_env("")

    # 提示用户输入参数
    platform = get_single_line_input("请输入LLM平台类型 (claude/openai):")
    base_url = get_single_line_input("请输入API基础URL:")
    api_key = get_single_line_input("请输入API密钥:")

    # 验证平台类型
    platform = platform.lower().strip()
    if platform not in ["claude", "openai"]:
        PrettyOutput.auto_print(
            f"❌ 不支持的平台类型: {platform}，仅支持 claude 和 openai"
        )
        return

    config_name = platform
    PrettyOutput.auto_print(
        f"🚀 开始配置 {platform.upper()} 平台，配置名称: {config_name}"
    )

    # 测试API连接并获取模型列表
    models = get_models(platform, base_url, api_key)
    if not models:
        PrettyOutput.auto_print("⚠️ 未能自动获取模型列表")
        use_manual_input = user_confirm("是否手动输入模型名称？", default=True)
        if use_manual_input:
            model_input = get_single_line_input(
                "请输入模型名称（多个模型用逗号分隔，如: gpt-4o,gpt-3.5-turbo）:"
            )
            models = [m.strip() for m in model_input.split(",") if m.strip()]
            if not models:
                PrettyOutput.auto_print("❌ 未输入有效模型名称，配置已取消")
                return
        else:
            PrettyOutput.auto_print("❌ 未提供模型名称，配置已取消")
            return

    PrettyOutput.auto_print(
        f"📋 可用模型: {', '.join(models[:10])}{'...' if len(models) > 10 else ''}"
    )

    # 选择模型逻辑
    if len(models) > 1:
        manual_input_option = len(models) + 1
        table_lines = ["| 序号 | 模型名称 |", "|------|----------|"]
        for i, model in enumerate(models, 1):
            table_lines.append(f"| {i} | {model} |")
        table_lines.append(f"| {manual_input_option} | 手动输入模型名称 |")
        PrettyOutput.print_markdown("\n".join(table_lines), title="可用模型列表")

        configure_all = user_confirm("是否配置所有模型？", default=False)
        if configure_all:
            selected_models = models
        else:
            model_choices = get_single_line_input(
                f"请输入要配置的模型序号（用逗号分隔，输入 {manual_input_option} 可手动输入模型名称）:"
            )
            try:
                indices = [int(x.strip()) - 1 for x in model_choices.split(",")]
                selected_models = []
                use_manual_input = False
                for idx in indices:
                    if 0 <= idx < len(models):
                        selected_models.append(models[idx])
                    elif idx == len(models):
                        use_manual_input = True
                    else:
                        PrettyOutput.auto_print(f"❌ 无效的模型序号: {idx + 1}")
                        return
                if use_manual_input:
                    model_input = get_single_line_input(
                        "请输入模型名称（多个模型用逗号分隔）:"
                    )
                    manual_models = [
                        m.strip() for m in model_input.split(",") if m.strip()
                    ]
                    if not manual_models:
                        PrettyOutput.auto_print("❌ 未输入有效模型名称")
                        return
                    selected_models.extend(manual_models)
                selected_models = list(dict.fromkeys(selected_models))
                if not selected_models:
                    PrettyOutput.auto_print("❌ 没有选择任何有效模型")
                    return
            except ValueError:
                PrettyOutput.auto_print("❌ 请输入有效的数字序号，用逗号分隔")
                return
    else:
        selected_models = [models[0]]

    PrettyOutput.auto_print(
        f"✅ 已选择 {len(selected_models)} 个模型: {', '.join(selected_models)}"
    )

    # 读取/创建配置文件
    jarvis_dir = Path.home() / ".jarvis"
    output_file = jarvis_dir / "config.yaml"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    config = {}
    if output_file.exists():
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 读取配置文件失败: {e}")
            if not user_confirm("是否继续创建新配置？", default=True):
                return

    if "llms" not in config:
        config["llms"] = {}
    if "llm_groups" not in config:
        config["llm_groups"] = {}

    # 收集已有模型
    existing_config_models = []
    for llm_config in config.get("llms", {}).values():
        if isinstance(llm_config, dict):
            model_name = llm_config.get("model")
            if isinstance(model_name, str) and model_name.strip():
                existing_config_models.append(model_name.strip())

    role_candidate_models = list(selected_models)
    existing_candidate_models = [
        m for m in existing_config_models if m not in role_candidate_models
    ]

    if existing_candidate_models and user_confirm(
        "配置模型组时，是否也允许从配置文件中已有的模型里选择？", default=False
    ):
        role_candidate_models.extend(existing_candidate_models)
        PrettyOutput.auto_print(
            f"📚 已将配置文件中的已有模型加入候选列表: {', '.join(existing_candidate_models)}"
        )

    role_candidate_models = list(dict.fromkeys(role_candidate_models))

    # 选择 normal/smart/cheap 模型
    if len(role_candidate_models) == 1:
        normal_model = smart_model = cheap_model = role_candidate_models[0]
        PrettyOutput.auto_print(f"🎯 Normal模型: {normal_model}")
        PrettyOutput.auto_print(f"🧠 Smart模型: {smart_model}")
        PrettyOutput.auto_print(f"💰 Cheap模型: {cheap_model}")
    else:
        # Normal
        table_lines = ["| 序号 | 模型名称 |", "|------|----------|"]
        for i, model in enumerate(role_candidate_models, 1):
            table_lines.append(f"| {i} | {model} |")
        PrettyOutput.print_markdown(
            "\n".join(table_lines), title="请选择 Normal 模型（大多数场景）"
        )
        normal_choice = get_single_line_input("请输入 Normal 模型序号:")
        try:
            normal_idx = int(normal_choice.strip()) - 1
            if 0 <= normal_idx < len(role_candidate_models):
                normal_model = role_candidate_models[normal_idx]
                PrettyOutput.auto_print(f"🎯 Normal模型: {normal_model}")
            else:
                PrettyOutput.auto_print(f"❌ 无效的模型序号: {normal_choice}")
                return
        except ValueError:
            PrettyOutput.auto_print("❌ 请输入有效的数字序号")
            return
        # Smart
        table_lines = ["| 序号 | 模型名称 |", "|------|----------|"]
        for i, model in enumerate(role_candidate_models, 1):
            table_lines.append(f"| {i} | {model} |")
        PrettyOutput.print_markdown(
            "\n".join(table_lines), title="请选择 Smart 模型（代码生成）"
        )
        smart_choice = get_single_line_input("请输入 Smart 模型序号:")
        try:
            smart_idx = int(smart_choice.strip()) - 1
            if 0 <= smart_idx < len(role_candidate_models):
                smart_model = role_candidate_models[smart_idx]
                PrettyOutput.auto_print(f"🧠 Smart模型: {smart_model}")
            else:
                PrettyOutput.auto_print(f"❌ 无效的模型序号: {smart_choice}")
        except ValueError:
            PrettyOutput.auto_print("❌ 请输入有效的数字序号")
            return
        # Cheap
        table_lines = ["| 序号 | 模型名称 |", "|------|----------|"]
        for i, model in enumerate(role_candidate_models, 1):
            table_lines.append(f"| {i} | {model} |")
        PrettyOutput.print_markdown(
            "\n".join(table_lines), title="请选择 Cheap 模型（低要求、大数据量场景）"
        )
        cheap_choice = get_single_line_input("请输入 Cheap 模型序号:")
        try:
            cheap_idx = int(cheap_choice.strip()) - 1
            if 0 <= cheap_idx < len(role_candidate_models):
                cheap_model = role_candidate_models[cheap_idx]
                PrettyOutput.auto_print(f"💰 Cheap模型: {cheap_model}")
            else:
                PrettyOutput.auto_print(f"❌ 无效的模型序号: {cheap_choice}")
                return
        except ValueError:
            PrettyOutput.auto_print("❌ 请输入有效的数字序号")
            return

    # 测试API连通性
    PrettyOutput.auto_print(f"🔍 正在测试模型 {normal_model} 的API连通性...")
    success, error_msg = test_model_connection(
        platform, base_url, api_key, normal_model
    )
    if success:
        PrettyOutput.auto_print("✅ API连通性测试通过")
    else:
        PrettyOutput.auto_print(f"❌ API连通性测试失败: {error_msg}")
        force_save = user_confirm("测试失败，是否仍要保存配置到文件？", default=False)
        if not force_save:
            PrettyOutput.auto_print("👋 已取消配置保存")
            return
        PrettyOutput.auto_print("⚠️ 将在测试失败的情况下保存配置")

    # 输入模型组名称
    default_group_name = normal_model.replace(".", "_").replace("-", "_")
    group_name_input = get_single_line_input(
        f"请输入模型组名称 (默认: {default_group_name}):"
    )
    group_name = (
        group_name_input.strip() if group_name_input.strip() else default_group_name
    )
    if not group_name:
        PrettyOutput.auto_print("❌ 模型组名称不能为空")
        return
    PrettyOutput.auto_print(f"✅ 模型组名称: {group_name}")

    # 设置最大token数
    default_max_tokens = 200000
    unique_role_models = list(dict.fromkeys([normal_model, smart_model, cheap_model]))
    existing_model_configs = {
        llm_config.get("model"): llm_config
        for llm_config in config.get("llms", {}).values()
        if isinstance(llm_config, dict) and isinstance(llm_config.get("model"), str)
    }
    model_max_tokens = {}
    for model in unique_role_models:
        prev_model_config = existing_model_configs.get(model, {})
        existing_max_tokens = prev_model_config.get("max_input_token_count")
        default_token_count = (
            existing_max_tokens
            if isinstance(existing_max_tokens, int) and existing_max_tokens > 0
            else default_max_tokens
        )
        while True:
            max_tokens_input = get_single_line_input(
                f"请输入模型 {model} 的最大token数 (默认: {default_token_count}):"
            )
            if not max_tokens_input.strip():
                model_max_tokens[model] = default_token_count
                PrettyOutput.auto_print(
                    f"✅ 模型 {model} 使用默认最大token数: {default_token_count}"
                )
                break
            try:
                max_tokens = int(max_tokens_input.strip())
                if max_tokens <= 0:
                    PrettyOutput.auto_print("❌ 最大token数必须为正整数")
                    continue
                model_max_tokens[model] = max_tokens
                PrettyOutput.auto_print(
                    f"✅ 模型 {model} 最大token数设置为: {max_tokens}"
                )
                break
            except ValueError:
                PrettyOutput.auto_print("❌ 请输入有效的正整数")

    # 多模态支持
    supports_multimodal = user_confirm(
        "是否启用多模态支持（支持图片输入）？", default=False
    )

    # 创建模型配置
    model_config_names = {}
    for model in unique_role_models:
        existing_config_name = None
        existing_model_config = None
        for config_key, llm_config in config.get("llms", {}).items():
            if isinstance(llm_config, dict) and llm_config.get("model") == model:
                existing_config_name = config_key
                existing_model_config = llm_config
                break
        if existing_config_name is not None and existing_model_config is not None:
            model_config_names[model] = existing_config_name
            existing_model_config["platform"] = platform
            existing_model_config["model"] = model
            existing_model_config["max_input_token_count"] = model_max_tokens[model]
            if platform == "openai":
                existing_model_config["llm_config"] = {
                    "openai_api_key": api_key,
                    "openai_api_base": base_url,
                    "supports_multimodal": supports_multimodal,
                }
            elif platform == "claude":
                existing_model_config["llm_config"] = {
                    "anthropic_api_key": api_key,
                    "anthropic_base_url": base_url,
                    "supports_multimodal": supports_multimodal,
                }
            else:
                existing_model_config["llm_config"] = {
                    f"{platform}_api_key": api_key,
                    f"{platform}_base_url": base_url,
                    "supports_multimodal": supports_multimodal,
                }
            PrettyOutput.auto_print(
                f"✅ 已更新模型配置: {existing_config_name} -> {model}"
            )
            continue
        model_config_name = f"{config_name}_{model.replace('.', '_').replace('-', '_')}"
        if platform == "openai":
            llm_config_dict = {
                "openai_api_key": api_key,
                "openai_api_base": base_url,
                "supports_multimodal": supports_multimodal,
            }
        elif platform == "claude":
            llm_config_dict = {
                "anthropic_api_key": api_key,
                "anthropic_base_url": base_url,
                "supports_multimodal": supports_multimodal,
            }
        else:
            llm_config_dict = {
                f"{platform}_api_key": api_key,
                f"{platform}_base_url": base_url,
                "supports_multimodal": supports_multimodal,
            }
        config["llms"][model_config_name] = {
            "platform": platform,
            "model": model,
            "max_input_token_count": model_max_tokens[model],
            "llm_config": llm_config_dict,
        }
        model_config_names[model] = model_config_name

    PrettyOutput.auto_print(f"✅ 已为 {len(unique_role_models)} 个模型创建配置")

    # 创建模型组
    config["llm_groups"][group_name] = {
        "normal_llm": model_config_names[normal_model],
        "smart_llm": model_config_names[smart_model],
        "cheap_llm": model_config_names[cheap_model],
    }
    PrettyOutput.auto_print(
        f"✅ 已创建模型组 '{group_name}'，normal={normal_model}, smart={smart_model}, cheap={cheap_model}"
    )

    # 设置默认模型组
    config["llm_group"] = group_name
    PrettyOutput.auto_print(f"✅ 已设置默认模型组为 '{group_name}'")

    # 保存配置
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                config, f, allow_unicode=True, default_flow_style=False, sort_keys=False
            )
        PrettyOutput.auto_print(f"✅ 配置已保存到 {output_file}")
    except Exception as e:
        PrettyOutput.auto_print(f"❌ 保存配置失败: {e}")


if __name__ == "__main__":
    app()
