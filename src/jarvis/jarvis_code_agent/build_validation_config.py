"""
构建验证配置管理模块

管理项目级别的构建验证配置，支持禁用构建验证并仅进行基础静态检查。

配置采用读写分离：
- 静态用户配置（disable_build_validation / disable_reason / custom_build_command）
  合并进 config.yaml 的 build_validation 配置项，由用户主动决定；
- 运行时状态（has_been_asked / selected_build_system / disabled_at）
  保存在独立的 build_validation_state.yaml 中，由程序自动记录。
"""

import os
from pathlib import Path
from typing import Any
from typing import Dict
from typing import Optional
from typing import cast

import yaml  # type: ignore[import-untyped]

from jarvis.jarvis_utils.config import get_build_validation_config
from jarvis.jarvis_utils.config import update_build_validation_config
from jarvis.jarvis_utils.output import PrettyOutput

STATE_FILE_NAME = "build_validation_state.yaml"


class BuildValidationConfig:
    """构建验证配置管理器"""

    def __init__(self, project_root: str):
        self.project_root = project_root
        self.config_dir = os.path.join(project_root, ".jarvis")
        self.state_path = os.path.join(self.config_dir, STATE_FILE_NAME)
        self._state: Optional[Dict[str, Any]] = None

    # ---------- 运行时状态（独立文件） ----------

    def _ensure_config_dir(self) -> None:
        """确保配置目录存在"""
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir, exist_ok=True)

    def _load_state(self) -> Dict[str, Any]:
        """加载运行时状态文件"""
        if self._state is not None:
            return self._state

        if not os.path.exists(self.state_path):
            self._state = {}
            return self._state

        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                self._state = yaml.safe_load(f) or {}
            return self._state
        except Exception as e:
            # 配置文件损坏时，返回空配置
            PrettyOutput.auto_print(f"⚠️ 加载构建验证运行时状态失败: {e}，使用默认配置")
            self._state = {}
            return self._state

    def _save_state(self) -> bool:
        """保存运行时状态文件"""
        try:
            self._ensure_config_dir()
            with open(self.state_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(
                    self._state, f, allow_unicode=True, default_flow_style=False
                )
            return True
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 保存构建验证运行时状态失败: {e}")
            return False

    # ---------- 静态用户配置（config.yaml） ----------

    def is_build_validation_disabled(self) -> bool:
        """检查是否已禁用构建验证"""
        config = get_build_validation_config()
        return cast(bool, config.get("disable_build_validation", False))

    def disable_build_validation(self, reason: Optional[str] = None) -> bool:
        """禁用构建验证

        Args:
            reason: 禁用原因（可选）

        Returns:
            bool: 是否成功保存配置
        """
        updates: Dict[str, Any] = {"disable_build_validation": True}
        if reason:
            updates["disable_reason"] = reason
        ok = update_build_validation_config(self.project_root, updates)
        if ok:
            # 记录禁用时的项目路径（运行时状态）
            state = self._load_state()
            state["disabled_at"] = str(Path(self.project_root).resolve())
            self._state = state
            self._save_state()
        return ok

    def enable_build_validation(self) -> bool:
        """重新启用构建验证"""
        ok = update_build_validation_config(
            self.project_root, {"disable_build_validation": False}
        )
        # 保留历史信息，但清除禁用标志
        return ok

    def get_disable_reason(self) -> Optional[str]:
        """获取禁用原因"""
        config = get_build_validation_config()
        return config.get("disable_reason")

    def get_custom_build_command(self) -> Optional[str]:
        """获取用户自定义构建命令

        Returns:
            构建命令字符串（如 "make && make test"），如果未配置则返回None
        """
        config = get_build_validation_config()
        return config.get("custom_build_command")

    def set_custom_build_command(self, command: str) -> bool:
        """保存用户自定义构建命令

        Args:
            command: 构建命令字符串（如 "make && make test"）

        Returns:
            bool: 是否成功保存配置
        """
        return update_build_validation_config(
            self.project_root, {"custom_build_command": command}
        )

    # ---------- 运行时状态（独立文件） ----------

    def has_been_asked(self) -> bool:
        """检查是否已经询问过用户"""
        state = self._load_state()
        return cast(bool, state.get("has_been_asked", False))

    def mark_as_asked(self) -> bool:
        """标记为已询问"""
        state = self._load_state()
        state["has_been_asked"] = True
        self._state = state
        return self._save_state()

    def get_selected_build_system(self) -> Optional[str]:
        """获取用户选择的构建系统

        Returns:
            构建系统名称（如 "rust", "python"），如果未选择则返回None
        """
        state = self._load_state()
        return state.get("selected_build_system")

    def set_selected_build_system(self, build_system: str) -> bool:
        """保存用户选择的构建系统

        Args:
            build_system: 构建系统名称（如 "rust", "python"）

        Returns:
            bool: 是否成功保存配置
        """
        state = self._load_state()
        state["selected_build_system"] = build_system
        self._state = state
        return self._save_state()
