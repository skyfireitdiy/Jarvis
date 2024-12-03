# -*- coding: utf-8 -*-
"""优化器配置管理模块。"""

import json
from pathlib import Path


def load_additional_notes(crate_dir: Path) -> str:
    """从配置文件加载附加说明。"""
    try:
        from jarvis.jarvis_c2rust.constants import CONFIG_JSON

        # 尝试从项目根目录读取配置（crate_dir 的父目录或同级目录）
        # 首先尝试 crate_dir 的父目录
        project_root = crate_dir.parent
        config_path = project_root / ".jarvis" / "c2rust" / CONFIG_JSON
        if config_path.exists():
            with config_path.open("r", encoding="utf-8") as f:
                config = json.load(f)
                if isinstance(config, dict):
                    return str(config.get("additional_notes", "") or "").strip()
        # 如果父目录没有，尝试当前目录
        config_path = crate_dir / ".jarvis" / "c2rust" / CONFIG_JSON
        if config_path.exists():
            with config_path.open("r", encoding="utf-8") as f:
                config = json.load(f)
                if isinstance(config, dict):
                    return str(config.get("additional_notes", "") or "").strip()
    except Exception:
        pass
    return ""


def append_additional_notes(prompt: str, additional_notes: str) -> str:
    """
    在提示词末尾追加附加说明（如果存在）。

    Args:
        prompt: 原始提示词
        additional_notes: 附加说明

    Returns:
        追加了附加说明的提示词
    """
    if additional_notes and additional_notes.strip():
        return (
            prompt + "\n\n" + "【附加说明（用户自定义）】\n" + additional_notes.strip()
        )
    return prompt
