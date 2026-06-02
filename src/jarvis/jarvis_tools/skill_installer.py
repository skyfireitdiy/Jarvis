# -*- coding: utf-8 -*-
"""技能安装器 - 使用依赖注入"""

import os
import requests
from typing import Optional, TYPE_CHECKING
from datetime import datetime

# 避免循环导入
if TYPE_CHECKING:
    from jarvis.jarvis_agent.rules_manager import RulesManager

from jarvis.jarvis_utils.config import get_data_dir
from .skill_sources.base import SkillResult


from abc import ABC, abstractmethod


class IDownloader(ABC):
    """下载器抽象接口（便于测试和替换）"""

    @abstractmethod
    def download(self, url: str) -> str:
        """下载文件内容"""
        ...


class RequestsDownloader(IDownloader):
    """基于 requests 的下载器实现"""

    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    def download(self, url: str) -> str:
        try:
            resp = requests.get(url, timeout=self.timeout)
            resp.raise_for_status()
            return resp.text
        except Exception:
            return ""


class SkillInstaller:
    """
    技能安装器

    依赖注入:
        - rules_manager: 用于加载新安装的规则
        - downloader: 用于下载技能文件
    """

    def __init__(
        self,
        rules_manager: Optional["RulesManager"] = None,
        downloader: Optional[IDownloader] = None,
        install_dir: Optional[str] = None,
    ):
        """
        参数:
            rules_manager: RulesManager 实例（用于热加载）
            downloader: 下载器实例（依赖注入）
            install_dir: 安装目录（可选）
        """
        # 依赖注入
        self.rules_manager = rules_manager
        self.downloader = downloader or RequestsDownloader()

        # 安装目录
        self.install_dir = install_dir or os.path.join(
            get_data_dir(), "rules", "auto_installed_skills"
        )
        os.makedirs(self.install_dir, exist_ok=True)

    def install(self, skill: SkillResult) -> str:
        """
        安装技能（原样保存 SKILL.md）

        参数:
            skill: 技能结果对象

        返回:
            保存的规则文件路径

        异常:
            ValueError: 下载失败时抛出
        """
        # 1. 检查是否已存在
        rule_name = self._sanitize_name(skill.name)
        rule_path = os.path.join(self.install_dir, f"{rule_name}.md")

        if os.path.exists(rule_path):
            return rule_path  # 已存在，跳过

        # 2. 下载 SKILL.md (原样下载，不转换)
        content = self.downloader.download(skill.download_url)

        if not content:
            raise ValueError(f"下载失败：{skill.download_url}")

        # 3. 添加来源注释 (便于追溯)
        content_with_header = self._add_source_header(content, skill)

        # 4. 保存
        with open(rule_path, "w", encoding="utf-8") as f:
            f.write(content_with_header)

        # 5. 热加载（如果提供了 rules_manager）
        if self.rules_manager:
            try:
                # 使用 getattr 避免类型检查错误
                load_method = getattr(self.rules_manager, "load_rule_file", None)
                if load_method:
                    load_method(rule_path)
            except Exception:
                # 加载失败不影响安装成功
                pass

        return rule_path

    def _add_source_header(self, content: str, skill: SkillResult) -> str:
        """在原始内容前添加来源注释"""
        header = f"""<!-- 
  自动安装的 Skill
  来源：{skill.platform}
  原始链接：{skill.source_url}
  安装时间：{datetime.now().isoformat()}
  作者：{skill.author or "Unknown"}
  标签：{", ".join(skill.tags) if skill.tags else "None"}
-->

"""
        return header + content

    def _sanitize_name(self, name: str) -> str:
        """清理文件名"""
        return (
            name.replace("/", "-")
            .replace("\\", "-")
            .replace(" ", "_")
            .replace(":", "-")
        )
