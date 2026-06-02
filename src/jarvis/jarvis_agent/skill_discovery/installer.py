# -*- coding: utf-8 -*-
"""技能安装器 - 仅支持 Git Clone 模式"""

import os
import shutil
import subprocess
import tempfile
import requests
from typing import Optional, TYPE_CHECKING
from datetime import datetime
from abc import ABC, abstractmethod

# 避免循环导入
if TYPE_CHECKING:
    from jarvis.jarvis_agent.rules_manager import RulesManager

from jarvis.jarvis_utils.config import get_data_dir
from .sources.base import SkillResult


class IDownloader(ABC):
    """下载器抽象接口（保留用于向后兼容）"""

    @abstractmethod
    def download(self, url: str) -> str:
        """下载文件内容"""
        ...


class RequestsDownloader(IDownloader):
    """基于 requests 的下载器实现（保留用于向后兼容）"""

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
    技能安装器（仅支持 Git Clone 模式）

    依赖注入:
        - rules_manager: 用于加载新安装的规则
        - downloader: 保留用于向后兼容（不再使用）
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
            downloader: 下载器实例（保留用于向后兼容）
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
        安装技能（仅支持 Git Clone 模式）

        克隆整个仓库并提取子目录，保留技能的所有文件（代码、配置、脚本等）。
        禁止回退到单文件下载模式。

        参数:
            skill: 技能结果对象

        返回:
            保存的规则文件路径（SKILL.md 的完整路径）

        异常:
            ValueError: 克隆失败或仓库信息不完整时抛出
        """
        # 必须包含 repo_info 信息
        repo_info = (
            skill._raw_data.get("repo_info")
            if isinstance(skill._raw_data, dict)
            else None
        )

        if (
            not repo_info
            or not repo_info.get("clone_url")
            or not repo_info.get("subdir")
        ):
            raise ValueError(
                f"技能 '{skill.name}' 缺少必要的仓库信息。\n"
                f"必须提供 repo_info.clone_url 和 repo_info.subdir\n"
                f"当前 _raw_data: {skill._raw_data}"
            )

        return self._install_via_git_clone(skill, repo_info)

    def _install_via_git_clone(self, skill: SkillResult, repo_info: dict) -> str:
        """通过 git clone 安装技能包"""
        clone_url = repo_info.get("clone_url", "")
        subdir = repo_info.get("subdir", "")

        if not clone_url or not subdir:
            raise ValueError(f"无效的仓库信息：{repo_info}")

        rule_name = self._sanitize_name(skill.name)

        # 创建临时目录
        temp_dir = tempfile.mkdtemp(prefix="skill_install_")

        try:
            # git clone --depth 1
            result = subprocess.run(
                ["git", "clone", "--depth", "1", clone_url, temp_dir],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                raise ValueError(f"Git clone 失败：{result.stderr}")

            # 定位技能子目录
            skill_dir = os.path.join(temp_dir, subdir)
            skill_md_path = os.path.join(skill_dir, "SKILL.md")

            if not os.path.exists(skill_md_path):
                # 尝试不带 skills 前缀的路径
                alt_subdir = (
                    subdir.replace("skills/", "", 1)
                    if subdir.startswith("skills/")
                    else f"skills/{subdir}"
                )
                alt_skill_dir = os.path.join(temp_dir, alt_subdir)
                alt_skill_md_path = os.path.join(alt_skill_dir, "SKILL.md")

                if os.path.exists(alt_skill_md_path):
                    skill_dir = alt_skill_dir
                    skill_md_path = alt_skill_md_path
                else:
                    raise ValueError(f"在子目录 {subdir} 中未找到 SKILL.md")

            # 读取 SKILL.md
            with open(skill_md_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 复制整个技能目录到安装位置
            target_skill_dir = os.path.join(self.install_dir, rule_name)
            if os.path.exists(target_skill_dir):
                shutil.rmtree(target_skill_dir)
            shutil.copytree(skill_dir, target_skill_dir)

            # 添加来源注释到 SKILL.md
            content_with_header = self._add_source_header(content, skill)
            with open(
                os.path.join(target_skill_dir, "SKILL.md"), "w", encoding="utf-8"
            ) as f:
                f.write(content_with_header)

            # 热加载
            if self.rules_manager:
                try:
                    load_method = getattr(self.rules_manager, "load_rule_file", None)
                    if load_method:
                        load_method(os.path.join(target_skill_dir, "SKILL.md"))
                except Exception:
                    pass

            return os.path.join(target_skill_dir, "SKILL.md")

        finally:
            # 清理临时目录
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

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
