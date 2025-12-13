"""
构建验证配置管理模块

管理项目级别的构建验证配置，支持禁用构建验证并仅进行基础静态检查。
"""

import os
from pathlib import Path
from typing import Any

from jarvis.jarvis_utils.output import PrettyOutput

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Dict
from typing import Optional
from typing import cast

import yaml

CONFIG_FILE_NAME = "build_validation_config.yaml"


class BuildValidationConfig:
    """构建验证配置管理器"""

    def __init__(self, project_root: str):
        self.project_root = project_root
        self.config_dir = os.path.join(project_root, ".jarvis")
        self.config_path = os.path.join(self.config_dir, CONFIG_FILE_NAME)
        self._config: Optional[Dict[str, Any]] = None

    def _ensure_config_dir(self) -> None:
        """确保配置目录存在"""
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir, exist_ok=True)

    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        if self._config is not None:
            return self._config

        if not os.path.exists(self.config_path):
            self._config = {}
            return self._config

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f) or {}
            return self._config
        except Exception as e:
            # 配置文件损坏时，返回空配置
            PrettyOutput.auto_print(f"⚠️ 加载构建验证配置失败: {e}，使用默认配置")
            self._config = {}
            return self._config

    def _save_config(self) -> bool:
        """保存配置文件"""
        try:
            self._ensure_config_dir()
            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(
                    self._config, f, allow_unicode=True, default_flow_style=False
                )
            return True
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 保存构建验证配置失败: {e}")
            return False

    def is_build_validation_disabled(self) -> bool:
        """检查是否已禁用构建验证"""
        config = self._load_config()
        return cast(bool, config.get("disable_build_validation", False))

    def disable_build_validation(self, reason: Optional[str] = None) -> bool:
        """禁用构建验证

        Args:
            reason: 禁用原因（可选）

        Returns:
            bool: 是否成功保存配置
        """
        config = self._load_config()
        config["disable_build_validation"] = True
        if reason:
            config["disable_reason"] = reason
        config["disabled_at"] = str(Path(self.project_root).resolve())
        self._config = config
        return self._save_config()

    def enable_build_validation(self) -> bool:
        """重新启用构建验证"""
        config = self._load_config()
        config["disable_build_validation"] = False
        # 保留历史信息，但清除禁用标志
        self._config = config
        return self._save_config()

    def get_disable_reason(self) -> Optional[str]:
        """获取禁用原因"""
        config = self._load_config()
        return config.get("disable_reason")

    def has_been_asked(self) -> bool:
        """检查是否已经询问过用户"""
        config = self._load_config()
        return cast(bool, config.get("has_been_asked", False))

    def mark_as_asked(self) -> bool:
        """标记为已询问"""
        config = self._load_config()
        config["has_been_asked"] = True
        self._config = config
        return self._save_config()

    def get_selected_build_system(self) -> Optional[str]:
        """获取用户选择的构建系统

        Returns:
            构建系统名称（如 "rust", "python"），如果未选择则返回None
        """
        config = self._load_config()
        return config.get("selected_build_system")

    def set_selected_build_system(self, build_system: str) -> bool:
        """保存用户选择的构建系统

        Args:
            build_system: 构建系统名称（如 "rust", "python"）

        Returns:
            bool: 是否成功保存配置
        """
        config = self._load_config()
        config["selected_build_system"] = build_system
        self._config = config
        return self._save_config()
