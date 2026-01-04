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
from rich.prompt import Prompt, Confirm
import requests

from .output import PrettyOutput

app = typer.Typer(help="快速配置 LLM 平台信息到 Jarvis 配置文件")
console = Console()


@app.command()
def quick_config(
    platform: str = typer.Option(
        ..., "--platform", "-p", help="LLM平台类型 (claude/openai)"
    ),
    base_url: str = typer.Option(..., "--url", "-u", help="API基础URL"),
    api_key: str = typer.Option(..., "--key", "-k", help="API密钥"),
    config_name: Optional[str] = typer.Option(
        None, "--name", "-n", help="配置名称，如果未指定将使用平台名称"
    ),
    output_file: Optional[Path] = typer.Option(
        None, "--output", "-o", help="输出配置文件路径，默认为~/.jarvis/config.yaml"
    ),
):
    """快速配置 LLM 平台信息到 Jarvis 配置文件的 llms 部分"""

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
        PrettyOutput.auto_print("⚠️  警告：无法获取模型列表，将使用默认模型名称")
        if platform == "claude":
            models = ["claude-3-5-sonnet-latest"]
        else:  # openai
            models = ["gpt-4o"]

    PrettyOutput.auto_print(
        f"📋 可用模型: {', '.join(models[:10])}{'...' if len(models) > 10 else ''}"
    )

    # 询问用户选择模型
    if len(models) == 1:
        selected_model = models[0]
    else:
        console.print("[bold]请选择一个模型:[/]")
        for i, model in enumerate(models, 1):
            console.print(f"  {i}. {model}")

        model_choice = Prompt.ask("输入模型编号或名称", default=str(models[0]))

        # 处理用户输入
        if model_choice.isdigit():
            idx = int(model_choice) - 1
            if 0 <= idx < len(models):
                selected_model = models[idx]
            else:
                PrettyOutput.auto_print(f"❌ 无效的模型编号: {model_choice}")
                raise typer.Exit(code=1)
        else:
            # 假设用户输入了模型名称
            selected_model = model_choice

    PrettyOutput.auto_print(f"✅ 已选择模型: {selected_model}")

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
            if not Confirm.ask("是否继续创建新配置？", default=True):
                raise typer.Exit(code=0)

    # 创建LLM配置
    llm_config = {
        "platform": platform,
        "model": selected_model,
        "max_input_token_count": 128000,
        "llm_config": {
            f"{platform}_api_key": api_key,
            f"{platform}_base_url": base_url,
        },
    }

    # 初始化llms部分
    if "llms" not in config:
        config["llms"] = {}

    # 添加新的配置
    config["llms"][config_name] = llm_config

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
        PrettyOutput.auto_print(
            f"💡 现在可以使用 --llm-group 或 -g 参数指定 {config_name} 配置"
        )

    except Exception as e:
        PrettyOutput.auto_print(f"❌ 保存配置失败: {e}")
        raise typer.Exit(code=1)


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
