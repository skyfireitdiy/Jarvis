# -*- coding: utf-8 -*-
"""技能安装器 - 仅支持 Git Clone 模式"""

import os
import shutil
import subprocess
import requests
from typing import Optional, TYPE_CHECKING
from datetime import datetime
from abc import ABC, abstractmethod

# 避免循环导入
if TYPE_CHECKING:
    from jarvis.jarvis_agent.rules_manager import RulesManager

from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.exception_utils import save_exception
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

        if not repo_info or not repo_info.get("clone_url"):
            raise ValueError(
                f"技能 '{skill.name}' 缺少必要的仓库信息。\n"
                f"必须提供 repo_info.clone_url\n"
                f"当前 _raw_data: {skill._raw_data}"
            )

        # 若 subdir 为空，尝试从 repo_url 解析子目录路径
        if not repo_info.get("subdir"):
            repo_url = (
                skill._raw_data.get("repo_url", "")
                if isinstance(skill._raw_data, dict)
                else ""
            )
            parsed_subdir = self._parse_subdir_from_repo_url(repo_url)
            if parsed_subdir:
                repo_info["subdir"] = parsed_subdir

        return self._install_via_git_clone(skill, repo_info)

    def _parse_subdir_from_repo_url(self, repo_url: str) -> str:
        """从 repo_url 中解析子目录路径。

        支持格式:
        - https://github.com/owner/repo/tree/main/skills/de-slopify
        - https://github.com/owner/repo/tree/master/skills/de-slopify

        返回:
            子目录路径（如 "skills/de-slopify"），解析失败返回空字符串
        """
        if not repo_url:
            return ""
        # 匹配 /tree/<branch>/<subdir> 格式
        marker = "/tree/"
        idx = repo_url.find(marker)
        if idx == -1:
            return ""
        # 跳过 /tree/<branch>/ 部分
        rest = repo_url[idx + len(marker) :]
        parts = rest.split("/", 1)
        if len(parts) < 2:
            return ""
        return parts[1]

    def _install_via_git_clone(self, skill: SkillResult, repo_info: dict) -> str:
        """通过 git clone 安装技能包（直接克隆到规则目录，不修改原始内容）"""
        clone_url = repo_info.get("clone_url", "")
        subdir = repo_info.get("subdir", "")

        if not clone_url:
            raise ValueError(f"无效的仓库信息：{repo_info}")

        rule_name = self._sanitize_name(skill.name)
        target_skill_dir = os.path.join(self.install_dir, rule_name)

        # 清理已存在的同名目录
        if os.path.exists(target_skill_dir):
            shutil.rmtree(target_skill_dir)

        # 解析仓库名（从 clone_url 提取）
        repo_name = clone_url.rstrip("/").split("/")[-1].replace(".git", "")
        repo_dir = os.path.join(target_skill_dir, repo_name)

        # git clone --depth 1 到 <skill_name>/<repo_name>/
        result = subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, repo_dir],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            # clone 失败时清理残留目录
            if os.path.exists(target_skill_dir):
                shutil.rmtree(target_skill_dir)
            raise ValueError(f"Git clone 失败：{result.stderr}")

        # 定位技能子目录中的 SKILL.md
        skill_md_path = (
            os.path.join(repo_dir, subdir, "SKILL.md")
            if subdir
            else os.path.join(repo_dir, "SKILL.md")
        )

        if not os.path.exists(skill_md_path):
            # 尝试不带 skills 前缀的路径
            alt_subdir = (
                subdir.replace("skills/", "", 1)
                if subdir.startswith("skills/")
                else f"skills/{subdir}"
            )
            alt_skill_md_path = os.path.join(repo_dir, alt_subdir, "SKILL.md")

            if os.path.exists(alt_skill_md_path):
                skill_md_path = alt_skill_md_path
            else:
                # clone 成功但找不到 SKILL.md，清理并报错
                shutil.rmtree(target_skill_dir)
                raise ValueError(f"在子目录 {subdir} 中未找到 SKILL.md")

        # 生成 skill.md 索引文件（含 description + skill_path）
        self._generate_skill_md_index(target_skill_dir, skill, repo_name)

        # 热加载（不修改 SKILL.md，保持原始内容）
        if self.rules_manager:
            try:
                load_method = getattr(self.rules_manager, "load_rule_file", None)
                if load_method:
                    load_method(skill_md_path)
            except Exception as e:
                save_exception(
                    e,
                    module="jarvis_agent.skill_discovery.installer",
                    function="_install_via_git_clone",
                )
                pass

        return skill_md_path

    def _generate_skill_md_index(
        self, target_skill_dir: str, skill: SkillResult, repo_name: str
    ) -> None:
        """生成 skill.md 索引文件

        在 skill 目录根目录生成 skill.md，含 description 和 skill_path。
        skill_path 使用 {{ rule_file_dir }} 模板变量指向仓库子目录，
        使 rules_manager 扫描时遇 skill.md 即停止遍历子层。

        参数:
            target_skill_dir: skill 安装目录
            skill: 技能结果对象
            repo_name: 仓库子目录名
        """
        try:
            # 使用模板变量 {{ rule_file_dir }} 指向仓库子目录
            skill_path_ref = "{{ rule_file_dir }}/" + repo_name

            index_content = f"""---
name: {skill.name}
description: {skill.description or skill.name}
---

# {skill.name}

{skill.description or ""}

skill_path: {skill_path_ref}
"""

            index_path = os.path.join(target_skill_dir, "skill.md")
            with open(index_path, "w", encoding="utf-8") as f:
                f.write(index_content)
        except Exception as e:
            save_exception(
                e,
                module="jarvis_agent.skill_discovery.installer",
                function="_generate_skill_md_index",
            )

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
