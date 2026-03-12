"""Jarvis平台管理器主模块。

该模块提供了Jarvis平台管理器的主要入口点。
"""

import os
import sys
from pathlib import Path
import yaml


from jarvis.jarvis_utils.output import PrettyOutput

# -*- coding: utf-8 -*-
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

import typer

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_platform_manager.service import start_service
from jarvis.jarvis_utils.config import (
    set_llm_group,
)
from jarvis.jarvis_utils.config import get_normal_model_name
from jarvis.jarvis_utils.config import get_normal_platform_name
from jarvis.jarvis_utils.fzf import fzf_select
from jarvis.jarvis_utils.input import get_multiline_input
from jarvis.jarvis_utils.input import get_single_line_input
from jarvis.jarvis_utils.utils import init_env

app = typer.Typer(help="Jarvis AI 平台")
manage_app = typer.Typer(help="管理 LLM 配置和模型组")
llm_app = typer.Typer(help="LLM 配置管理")
group_app = typer.Typer(help="模型组管理")
app.add_typer(manage_app, name="manage")
manage_app.add_typer(llm_app, name="llm")
manage_app.add_typer(group_app, name="group")


# ============================================================================
# 配置文件操作辅助函数
# ============================================================================


def _get_config_file_path() -> Path:
    """获取配置文件路径

    返回:
        Path: 配置文件路径 (~/.jarvis/config.yaml)
    """
    return Path.home() / ".jarvis" / "config.yaml"


def _load_config() -> Dict[str, Any]:
    """加载配置文件

    返回:
        Dict[str, Any]: 配置字典，如果文件不存在或读取失败返回空字典
    """
    config_file = _get_config_file_path()
    if not config_file.exists():
        return {}

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as exc:
        PrettyOutput.auto_print(f"❌ 读取配置文件失败: {exc}")
        return {}


def _save_config(config: Dict[str, Any]) -> bool:
    """保存配置到文件

    参数:
        config: 配置字典

    返回:
        bool: 保存成功返回 True，否则返回 False
    """
    config_file = _get_config_file_path()

    # 确保目录存在
    config_file.parent.mkdir(parents=True, exist_ok=True)

    # 备份原配置文件
    backup_file = config_file.with_suffix(".yaml.bak")
    if config_file.exists():
        try:
            import shutil

            shutil.copy2(config_file, backup_file)
        except Exception:
            pass  # 备份失败不影响主流程

    try:
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, default_flow_style=False, allow_unicode=True)
        return True
    except Exception as exc:
        PrettyOutput.auto_print(f"❌ 保存配置文件失败: {exc}")
        # 尝试恢复备份
        if backup_file.exists():
            try:
                import shutil

                shutil.copy2(backup_file, config_file)
                PrettyOutput.auto_print("ℹ️ 已恢复原配置文件")
            except Exception:
                pass
        return False


# ============================================================================
# LLM 管理子命令
# ============================================================================


@llm_app.command("list")
def llm_list() -> None:
    """列出所有 LLM 配置"""
    config = _load_config()
    llms = config.get("llms", {})

    if not llms:
        PrettyOutput.auto_print("ℹ️ 没有配置任何 LLM")
        return

    PrettyOutput.auto_print("✅ LLM 配置列表:")
    for name in sorted(llms.keys()):
        llm_config = llms[name]
        platform = llm_config.get("platform", "unknown")
        model = llm_config.get("model", "unknown")
        PrettyOutput.auto_print(f"  • {name} ({platform}/{model})")


@llm_app.command("show")
def llm_show(
    name: str = typer.Argument(None, help="LLM 配置名称，不指定则交互式选择"),
) -> None:
    """显示指定 LLM 配置详情"""
    config = _load_config()
    llms = config.get("llms", {})

    if not llms:
        PrettyOutput.auto_print("ℹ️ 没有配置任何 LLM")
        raise typer.Exit(code=1)

    # 如果没有指定名称，使用交互式选择
    if name is None:
        fzf_options = [
            f"{llm_name} ({llm_config.get('platform', 'unknown')}/{llm_config.get('model', 'unknown')})"
            for llm_name, llm_config in sorted(llms.items())
        ]
        selected_str = fzf_select(fzf_options, prompt="选择 LLM 配置 > ")
        if not selected_str:
            PrettyOutput.auto_print("ℹ️ 已取消")
            raise typer.Exit(code=0)
        # 从选择的字符串中提取名称（格式：name (platform/model)）
        name = selected_str.split(" (")[0].strip()

    if name not in llms:
        PrettyOutput.auto_print(f"❌ 未找到 LLM 配置: {name}")
        raise typer.Exit(code=1)

    llm_config = llms[name]
    PrettyOutput.auto_print(f"✅ LLM 配置: {name}")
    PrettyOutput.auto_print(f"  平台: {llm_config.get('platform', 'N/A')}")
    PrettyOutput.auto_print(f"  模型: {llm_config.get('model', 'N/A')}")
    PrettyOutput.auto_print(
        f"  最大token数: {llm_config.get('max_input_token_count', 'N/A')}"
    )

    llm_config_dict = llm_config.get("llm_config", {})
    if llm_config_dict:
        PrettyOutput.auto_print("  其他配置:")
        for key, value in llm_config_dict.items():
            PrettyOutput.auto_print(f"    {key}: {value}")


@llm_app.command("delete")
def llm_delete(
    name: str = typer.Argument(None, help="LLM 配置名称，不指定则交互式选择"),
) -> None:
    """删除指定的 LLM 配置"""
    config = _load_config()
    llms = config.get("llms", {})

    if not llms:
        PrettyOutput.auto_print("ℹ️ 没有配置任何 LLM")
        raise typer.Exit(code=1)

    # 如果没有指定名称，使用交互式选择
    if name is None:
        fzf_options = [
            f"{llm_name} ({llm_config.get('platform', 'unknown')}/{llm_config.get('model', 'unknown')})"
            for llm_name, llm_config in sorted(llms.items())
        ]
        selected_str = fzf_select(fzf_options, prompt="选择要删除的 LLM 配置 > ")
        if not selected_str:
            PrettyOutput.auto_print("ℹ️ 已取消")
            raise typer.Exit(code=0)
        # 从选择的字符串中提取名称（格式：name (platform/model)）
        name = selected_str.split(" (")[0].strip()

    if name not in llms:
        PrettyOutput.auto_print(f"❌ 未找到 LLM 配置: {name}")
        raise typer.Exit(code=1)

    # 检查是否被模型组引用
    llm_groups = config.get("llm_groups", {})
    for group_name, group_config in llm_groups.items():
        for key in ["normal_llm", "cheap_llm", "smart_llm"]:
            if group_config.get(key) == name:
                PrettyOutput.auto_print(f"⚠️ 该配置被模型组 '{group_name}' 引用")

    # 确认删除
    from jarvis.jarvis_utils.input import user_confirm

    if not user_confirm(f"确认删除 LLM 配置 '{name}'?", default=False):
        PrettyOutput.auto_print("ℹ️ 已取消删除")
        return

    # 删除配置
    if "llms" not in config:
        config["llms"] = {}
    config["llms"].pop(name, None)

    # 保存配置
    if _save_config(config):
        PrettyOutput.auto_print(f"✅ 已删除 LLM 配置: {name}")
    else:
        PrettyOutput.auto_print("❌ 保存配置失败")
        raise typer.Exit(code=1)


@llm_app.command("add")
def llm_add(name: str = typer.Argument(..., help="LLM 配置名称")) -> None:
    """添加新的 LLM 配置（交互式）"""
    from jarvis.jarvis_utils.input import get_single_line_input

    config = _load_config()
    if "llms" not in config:
        config["llms"] = {}

    if name in config["llms"]:
        PrettyOutput.auto_print(f"❌ LLM 配置 '{name}' 已存在")
        raise typer.Exit(code=1)

    PrettyOutput.auto_print(f"📝 添加 LLM 配置: {name}")

    # 交互式输入
    platform = get_single_line_input("平台名称 (openai/claude/other): ").strip()
    if not platform:
        PrettyOutput.auto_print("❌ 平台名称不能为空")
        raise typer.Exit(code=1)

    model = get_single_line_input("模型名称 (如: gpt-4o): ").strip()
    if not model:
        PrettyOutput.auto_print("❌ 模型名称不能为空")
        raise typer.Exit(code=1)

    max_tokens_input = get_single_line_input("最大token数 (默认: 128000): ").strip()
    try:
        max_tokens = int(max_tokens_input) if max_tokens_input else 128000
    except ValueError:
        PrettyOutput.auto_print("❌ 无效的token数，使用默认值 128000")
        max_tokens = 128000

    # 创建配置
    llm_config: Dict[str, Any] = {
        "platform": platform,
        "model": model,
        "max_input_token_count": max_tokens,
    }

    # 询问是否添加额外配置
    from jarvis.jarvis_utils.input import user_confirm

    if user_confirm("是否添加额外配置 (如 API key)?", default=False):
        PrettyOutput.auto_print("ℹ️ 输入配置键和值 (留空结束)")
        llm_config["llm_config"] = {}
        while True:
            key = get_single_line_input("配置键: ").strip()
            if not key:
                break
            value = get_single_line_input(f"配置值 ({key}): ").strip()
            llm_config["llm_config"][key] = value

    # 保存配置
    config["llms"][name] = llm_config
    if _save_config(config):
        PrettyOutput.auto_print(f"✅ 已添加 LLM 配置: {name}")
    else:
        PrettyOutput.auto_print("❌ 保存配置失败")
        raise typer.Exit(code=1)


@llm_app.command("update")
def llm_update(
    name: str = typer.Argument(None, help="LLM 配置名称，不指定则交互式选择"),
) -> None:
    """更新指定的 LLM 配置（交互式）"""
    from jarvis.jarvis_utils.input import get_single_line_input

    config = _load_config()
    if "llms" not in config:
        config["llms"] = {}

    if not config["llms"]:
        PrettyOutput.auto_print("ℹ️ 没有配置任何 LLM")
        raise typer.Exit(code=1)

    # 如果没有指定名称，使用交互式选择
    if name is None:
        fzf_options = [
            f"{llm_name} ({llm_config.get('platform', 'unknown')}/{llm_config.get('model', 'unknown')})"
            for llm_name, llm_config in sorted(config["llms"].items())
        ]
        selected_str = fzf_select(fzf_options, prompt="选择要更新的 LLM 配置 > ")
        if not selected_str:
            PrettyOutput.auto_print("ℹ️ 已取消")
            raise typer.Exit(code=0)
        # 从选择的字符串中提取名称（格式：name (platform/model)）
        name = selected_str.split(" (")[0].strip()

    if name not in config["llms"]:
        PrettyOutput.auto_print(f"❌ 未找到 LLM 配置: {name}")
        raise typer.Exit(code=1)

    llm_config = config["llms"][name]
    PrettyOutput.auto_print(f"📝 更新 LLM 配置: {name}")
    PrettyOutput.auto_print(
        f"  当前值 - 平台: {llm_config.get('platform', 'N/A')}, 模型: {llm_config.get('model', 'N/A')}"
    )

    # 更新各个字段
    platform = get_single_line_input(
        f"平台名称 (当前: {llm_config.get('platform', '')}, 留空不变): "
    ).strip()
    if platform:
        llm_config["platform"] = platform

    model = get_single_line_input(
        f"模型名称 (当前: {llm_config.get('model', '')}, 留空不变): "
    ).strip()
    if model:
        llm_config["model"] = model

    max_tokens_input = get_single_line_input(
        f"最大token数 (当前: {llm_config.get('max_input_token_count', 128000)}, 留空不变): "
    ).strip()
    if max_tokens_input:
        try:
            max_tokens = int(max_tokens_input)
            llm_config["max_input_token_count"] = max_tokens
        except ValueError:
            PrettyOutput.auto_print("❌ 无效的token数，保持原值")

    # 保存配置
    if _save_config(config):
        PrettyOutput.auto_print(f"✅ 已更新 LLM 配置: {name}")
    else:
        PrettyOutput.auto_print("❌ 保存配置失败")
        raise typer.Exit(code=1)


# ============================================================================
# 模型组管理子命令
# ============================================================================


@group_app.command("list")
def group_list() -> None:
    """列出所有模型组"""
    config = _load_config()
    llm_groups = config.get("llm_groups", {})

    if not llm_groups:
        PrettyOutput.auto_print("ℹ️ 没有配置任何模型组")
        return

    PrettyOutput.auto_print("✅ 模型组列表:")
    for name in sorted(llm_groups.keys()):
        group_config = llm_groups[name]
        normal_llm = group_config.get("normal_llm", "N/A")
        PrettyOutput.auto_print(f"  • {name} (normal: {normal_llm})")


@group_app.command("show")
def group_show(
    name: str = typer.Argument(None, help="模型组名称，不指定则交互式选择"),
) -> None:
    """显示指定模型组详情"""
    config = _load_config()
    llm_groups = config.get("llm_groups", {})

    if not llm_groups:
        PrettyOutput.auto_print("ℹ️ 没有配置任何模型组")
        raise typer.Exit(code=1)

    # 如果没有指定名称，使用交互式选择
    if name is None:
        fzf_options = [
            f"{group_name} (normal: {group_config.get('normal_llm', 'N/A')})"
            for group_name, group_config in sorted(llm_groups.items())
        ]
        selected_str = fzf_select(fzf_options, prompt="选择模型组 > ")
        if not selected_str:
            PrettyOutput.auto_print("ℹ️ 已取消")
            raise typer.Exit(code=0)
        # 从选择的字符串中提取名称（格式：group_name (normal: xxx)）
        name = selected_str.split(" (")[0].strip()

    if name not in llm_groups:
        PrettyOutput.auto_print(f"❌ 未找到模型组: {name}")
        raise typer.Exit(code=1)

    group_config = llm_groups[name]
    PrettyOutput.auto_print(f"✅ 模型组: {name}")
    PrettyOutput.auto_print(f"  normal_llm: {group_config.get('normal_llm', 'N/A')}")
    PrettyOutput.auto_print(f"  cheap_llm: {group_config.get('cheap_llm', 'N/A')}")
    PrettyOutput.auto_print(f"  smart_llm: {group_config.get('smart_llm', 'N/A')}")


@group_app.command("delete")
def group_delete(
    name: str = typer.Argument(None, help="模型组名称，不指定则交互式选择"),
) -> None:
    """删除指定的模型组"""
    config = _load_config()
    llm_groups = config.get("llm_groups", {})

    if not llm_groups:
        PrettyOutput.auto_print("ℹ️ 没有配置任何模型组")
        raise typer.Exit(code=1)

    # 如果没有指定名称，使用交互式选择
    if name is None:
        fzf_options = [
            f"{group_name} (normal: {group_config.get('normal_llm', 'N/A')})"
            for group_name, group_config in sorted(llm_groups.items())
        ]
        selected_str = fzf_select(fzf_options, prompt="选择要删除的模型组 > ")
        if not selected_str:
            PrettyOutput.auto_print("ℹ️ 已取消")
            raise typer.Exit(code=0)
        # 从选择的字符串中提取名称（格式：group_name (normal: xxx)）
        name = selected_str.split(" (")[0].strip()

    if name not in llm_groups:
        PrettyOutput.auto_print(f"❌ 未找到模型组: {name}")
        raise typer.Exit(code=1)

    # 确认删除
    from jarvis.jarvis_utils.input import user_confirm

    if not user_confirm(f"确认删除模型组 '{name}'?", default=False):
        PrettyOutput.auto_print("ℹ️ 已取消删除")
        return

    # 删除配置
    if "llm_groups" not in config:
        config["llm_groups"] = {}
    config["llm_groups"].pop(name, None)

    # 保存配置
    if _save_config(config):
        PrettyOutput.auto_print(f"✅ 已删除模型组: {name}")
    else:
        PrettyOutput.auto_print("❌ 保存配置失败")
        raise typer.Exit(code=1)


@group_app.command("add")
def group_add(name: str = typer.Argument(..., help="模型组名称")) -> None:
    """添加新的模型组（交互式）"""
    from jarvis.jarvis_utils.input import get_single_line_input

    config = _load_config()
    if "llm_groups" not in config:
        config["llm_groups"] = {}

    if name in config["llm_groups"]:
        PrettyOutput.auto_print(f"❌ 模型组 '{name}' 已存在")
        raise typer.Exit(code=1)

    # 获取可用的 LLM 配置列表
    llms = config.get("llms", {})
    if not llms:
        PrettyOutput.auto_print("❌ 没有可用的 LLM 配置，请先添加 LLM 配置")
        raise typer.Exit(code=1)

    PrettyOutput.auto_print(f"📝 添加模型组: {name}")
    PrettyOutput.auto_print("可用的 LLM 配置:")
    for llm_name in sorted(llms.keys()):
        PrettyOutput.auto_print(f"  • {llm_name}")

    # 交互式输入
    normal_llm = get_single_line_input("Normal LLM 配置名称 (必需): ").strip()
    if not normal_llm:
        PrettyOutput.auto_print("❌ Normal LLM 配置名称不能为空")
        raise typer.Exit(code=1)

    if normal_llm not in llms:
        PrettyOutput.auto_print(f"❌ 未找到 LLM 配置: {normal_llm}")
        raise typer.Exit(code=1)

    # 可选的 cheap 和 smart
    cheap_llm = get_single_line_input(
        "Cheap LLM 配置名称 (留空则与 normal 相同): "
    ).strip()
    if cheap_llm and cheap_llm not in llms:
        PrettyOutput.auto_print(f"❌ 未找到 LLM 配置: {cheap_llm}")
        raise typer.Exit(code=1)

    smart_llm = get_single_line_input(
        "Smart LLM 配置名称 (留空则与 normal 相同): "
    ).strip()
    if smart_llm and smart_llm not in llms:
        PrettyOutput.auto_print(f"❌ 未找到 LLM 配置: {smart_llm}")
        raise typer.Exit(code=1)

    # 创建配置
    group_config = {
        "normal_llm": normal_llm,
    }
    if cheap_llm:
        group_config["cheap_llm"] = cheap_llm
    if smart_llm:
        group_config["smart_llm"] = smart_llm

    # 保存配置
    config["llm_groups"][name] = group_config
    if _save_config(config):
        PrettyOutput.auto_print(f"✅ 已添加模型组: {name}")
    else:
        PrettyOutput.auto_print("❌ 保存配置失败")
        raise typer.Exit(code=1)


@group_app.command("update")
def group_update(
    name: str = typer.Argument(None, help="模型组名称，不指定则交互式选择"),
) -> None:
    """更新指定的模型组（交互式）"""
    from jarvis.jarvis_utils.input import get_single_line_input

    config = _load_config()
    if "llm_groups" not in config:
        config["llm_groups"] = {}

    if not config["llm_groups"]:
        PrettyOutput.auto_print("ℹ️ 没有配置任何模型组")
        raise typer.Exit(code=1)

    # 如果没有指定名称，使用交互式选择
    if name is None:
        fzf_options = [
            f"{group_name} (normal: {group_config.get('normal_llm', 'N/A')})"
            for group_name, group_config in sorted(config["llm_groups"].items())
        ]
        selected_str = fzf_select(fzf_options, prompt="选择要更新的模型组 > ")
        if not selected_str:
            PrettyOutput.auto_print("ℹ️ 已取消")
            raise typer.Exit(code=0)
        # 从选择的字符串中提取名称（格式：group_name (normal: xxx)）
        name = selected_str.split(" (")[0].strip()

    if name not in config["llm_groups"]:
        PrettyOutput.auto_print(f"❌ 未找到模型组: {name}")
        raise typer.Exit(code=1)

    # 获取可用的 LLM 配置列表
    llms = config.get("llms", {})

    group_config = config["llm_groups"][name]
    PrettyOutput.auto_print(f"📝 更新模型组: {name}")
    PrettyOutput.auto_print(
        f"  当前值 - normal: {group_config.get('normal_llm', 'N/A')}, cheap: {group_config.get('cheap_llm', 'N/A')}, smart: {group_config.get('smart_llm', 'N/A')}"
    )
    PrettyOutput.auto_print("可用的 LLM 配置:")
    for llm_name in sorted(llms.keys()):
        PrettyOutput.auto_print(f"  • {llm_name}")

    # 更新各个字段
    normal_llm = get_single_line_input(
        f"Normal LLM (当前: {group_config.get('normal_llm', '')}, 留空不变): "
    ).strip()
    if normal_llm:
        if normal_llm not in llms:
            PrettyOutput.auto_print(f"❌ 未找到 LLM 配置: {normal_llm}")
            raise typer.Exit(code=1)
        group_config["normal_llm"] = normal_llm

    cheap_llm = get_single_line_input(
        f"Cheap LLM (当前: {group_config.get('cheap_llm', '')}, 留空不变): "
    ).strip()
    if cheap_llm:
        if cheap_llm not in llms:
            PrettyOutput.auto_print(f"❌ 未找到 LLM 配置: {cheap_llm}")
            raise typer.Exit(code=1)
        group_config["cheap_llm"] = cheap_llm

    smart_llm = get_single_line_input(
        f"Smart LLM (当前: {group_config.get('smart_llm', '')}, 留空不变): "
    ).strip()
    if smart_llm:
        if smart_llm not in llms:
            PrettyOutput.auto_print(f"❌ 未找到 LLM 配置: {smart_llm}")
            raise typer.Exit(code=1)
        group_config["smart_llm"] = smart_llm

    # 保存配置
    if _save_config(config):
        PrettyOutput.auto_print(f"✅ 已更新模型组: {name}")
    else:
        PrettyOutput.auto_print("❌ 保存配置失败")
        raise typer.Exit(code=1)


@group_app.command("set")
def group_set(
    name: str = typer.Argument(None, help="模型组名称，不指定则交互式选择"),
) -> None:
    """设置当前激活的模型组"""
    config = _load_config()
    llm_groups = config.get("llm_groups", {})

    if not llm_groups:
        PrettyOutput.auto_print("ℹ️ 没有配置任何模型组")
        raise typer.Exit(code=1)

    # 如果没有指定名称，使用交互式选择
    if name is None:
        fzf_options = [
            f"{group_name} (normal: {group_config.get('normal_llm', 'N/A')})"
            for group_name, group_config in sorted(llm_groups.items())
        ]
        selected_str = fzf_select(fzf_options, prompt="选择要设置的模型组 > ")
        if not selected_str:
            PrettyOutput.auto_print("ℹ️ 已取消")
            raise typer.Exit(code=0)
        # 从选择的字符串中提取名称（格式：group_name (normal: xxx)）
        name = selected_str.split(" (")[0].strip()

    if name not in llm_groups:
        PrettyOutput.auto_print(f"❌ 未找到模型组: {name}")
        raise typer.Exit(code=1)

    # 设置当前模型组
    if "llm_group" not in config:
        config["llm_group"] = ""
    config["llm_group"] = name

    # 保存配置
    if _save_config(config):
        PrettyOutput.auto_print(f"✅ 已设置当前模型组: {name}")
    else:
        PrettyOutput.auto_print("❌ 保存配置失败")
        raise typer.Exit(code=1)


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
    set_llm_group(llm_group)
    if llm_group:
        platform_name = get_normal_platform_name()
        model_name = get_normal_model_name()
        PrettyOutput.auto_print(f"✅ 从模型组 '{llm_group}' 获取的配置信息:")
        PrettyOutput.auto_print(f"  平台: {platform_name}")
        PrettyOutput.auto_print(f"  模型: {model_name}")

        # 只显示配置中指定的平台信息
        platform_names = [platform_name]

        # 使用配置创建平台实例并显示详细信息
        try:
            platform_instance = registry.create_platform("normal")
            if platform_instance:
                models = platform_instance.get_model_list()
                PrettyOutput.auto_print(f"✅ {platform_name}")
                if models:
                    for model_name, description in models:
                        if description:
                            PrettyOutput.auto_print(f"  • {model_name} - {description}")
                        else:
                            PrettyOutput.auto_print(f"  • {model_name}")
                else:
                    PrettyOutput.auto_print("⚠️   • 没有可用的模型信息")
            else:
                PrettyOutput.auto_print(f"⚠️ 创建 {platform_name} 平台失败")
        except Exception:
            PrettyOutput.auto_print(f"⚠️ 创建 {platform_name} 平台失败")
        return
    else:
        # 获取默认模型组配置
        platform_name = get_normal_platform_name()
        default_model = get_normal_model_name()

        # 显示默认配置信息
        PrettyOutput.auto_print("✅ 默认配置信息:")
        PrettyOutput.auto_print(f"  平台: {platform_name}")
        PrettyOutput.auto_print(f"  模型: {default_model}")

        # 显示默认平台的详细信息
        try:
            platform_instance = registry.create_platform("normal")
            if platform_instance:
                models = platform_instance.get_model_list()
                PrettyOutput.auto_print(f"✅ {platform_name} 平台详情")
                if models:
                    for model_name, description in models:
                        if description:
                            PrettyOutput.auto_print(f"  • {model_name} - {description}")
                        else:
                            PrettyOutput.auto_print(f"  • {model_name}")
                else:
                    PrettyOutput.auto_print("⚠️   • 没有可用的模型信息")
            else:
                PrettyOutput.auto_print(f"⚠️ 创建 {platform_name} 平台失败")
        except Exception:
            PrettyOutput.auto_print(f"⚠️ 创建 {platform_name} 平台失败")
        return


def chat_with_model(
    system_prompt: str,
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

    platform_name = get_normal_platform_name()
    model_name = get_normal_model_name()

    # Create platform instance
    platform = registry.create_platform("normal")
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
        PrettyOutput.auto_print("ℹ️ 输入 /bye 退出聊天")

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

            try:
                conversation_history.append(
                    {"role": "user", "content": user_input}
                )  # 记录用户输入
                # Send to model and get reply
                response = platform.chat_until_success(user_input)
                if not response:
                    PrettyOutput.auto_print("⚠️ 没有有效的回复")
                else:
                    # 使用 PrettyOutput.print_markdown 打印 LLM 响应（带markdown高亮）
                    title = f"[bold cyan]{platform_name} · {model_name}[/bold cyan]"
                    PrettyOutput.print_markdown(
                        response, title=title, border_style="cyan"
                    )
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
    set_llm_group(llm_group)
    platform = get_normal_platform_name()
    model = get_normal_model_name()

    if not validate_platform_model(platform, model):
        return
    chat_with_model("")


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
    set_llm_group(llm_group)

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

    system_prompt = selected_role.get("system_prompt", "")

    # 开始对话
    PrettyOutput.auto_print(f"✅ 已选择角色: {selected_role['name']}")
    chat_with_model(system_prompt)


def main() -> None:
    """Jarvis平台管理器的主入口点。"""
    init_env()
    app()


if __name__ == "__main__":
    main()
