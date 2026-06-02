# -*- coding: utf-8 -*-
"""技能安装器 - 使用依赖注入"""

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
        rules_manager: Optional['RulesManager'] = None,
        downloader: Optional[IDownloader] = None,
        install_dir: Optional[str] = None
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
            get_data_dir(),
            "rules",
            "auto_installed_skills"
        )
        os.makedirs(self.install_dir, exist_ok=True)

    def install(self, skill: SkillResult) -> str:
        """
        安装技能

        支持两种模式:
        1. Git Clone 模式：如果 skill._raw_data 包含 repo_info，则克隆整个仓库并提取子目录
        2. 单文件模式：直接下载 SKILL.md 文件

        参数:
            skill: 技能结果对象

        返回:
            保存的规则文件路径

        异常:
            ValueError: 下载/克隆失败时抛出
        """
        # 检查是否为 git clone 模式
        repo_info = skill._raw_data.get("repo_info") if isinstance(skill._raw_data, dict) else None
        
        if repo_info and repo_info.get("subdir"):
            return self._install_via_git_clone(skill, repo_info)
        else:
            return self._install_single_file(skill)

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
                timeout=60
            )
            
            if result.returncode != 0:
                raise ValueError(f"Git clone 失败：{result.stderr}")
            
            # 定位技能子目录
            skill_dir = os.path.join(temp_dir, subdir)
            skill_md_path = os.path.join(skill_dir, "SKILL.md")
            
            if not os.path.exists(skill_md_path):
                # 尝试不带 skills 前缀的路径
                alt_subdir = subdir.replace("skills/", "", 1) if subdir.startswith("skills/") else f"skills/{subdir}"
                alt_skill_dir = os.path.join(temp_dir, alt_subdir)
                alt_skill_md_path = os.path.join(alt_skill_dir, "SKILL.md")
                
                if os.path.exists(alt_skill_md_path):
                    skill_dir = alt_skill_dir
                    skill_md_path = alt_skill_md_path
                else:
                    raise ValueError(f"在子目录 {subdir} 中未找到 SKILL.md")
            
            # 读取 SKILL.md
            with open(skill_md_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 复制整个技能目录到安装位置
            target_skill_dir = os.path.join(self.install_dir, rule_name)
            if os.path.exists(target_skill_dir):
                shutil.rmtree(target_skill_dir)
            shutil.copytree(skill_dir, target_skill_dir)
            
            # 添加来源注释到 SKILL.md
            content_with_header = self._add_source_header(content, skill)
            with open(os.path.join(target_skill_dir, "SKILL.md"), 'w', encoding='utf-8') as f:
                f.write(content_with_header)
            
            # 热加载
            if self.rules_manager:
                try:
                    load_method = getattr(self.rules_manager, 'load_rule_file', None)
                    if load_method:
                        load_method(os.path.join(target_skill_dir, "SKILL.md"))
                except Exception:
                    pass
            
            return os.path.join(target_skill_dir, "SKILL.md")
            
        finally:
            # 清理临时目录
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    def _install_single_file(self, skill: SkillResult) -> str:
        """安装单个 SKILL.md 文件（旧模式）"""
        # 1. 检查是否已存在
        rule_name = self._sanitize_name(skill.name)
        rule_path = os.path.join(self.install_dir, f"{rule_name}.md")

        if os.path.exists(rule_path):
            return rule_path  # 已存在，跳过

        # 2. 下载 SKILL.md
        content = self.downloader.download(skill.download_url)

        if not content:
            raise ValueError(f"下载失败：{skill.download_url}")

        # 3. 添加来源注释
        content_with_header = self._add_source_header(content, skill)

        # 4. 保存
        with open(rule_path, 'w', encoding='utf-8') as f:
            f.write(content_with_header)

        # 5. 热加载
        if self.rules_manager:
            try:
                load_method = getattr(self.rules_manager, 'load_rule_file', None)
                if load_method:
                    load_method(rule_path)
            except Exception:
                pass

        return rule_path

    def _add_source_header(self, content: str, skill: SkillResult) -> str:
        """在原始内容前添加来源注释"""
        header = f"""<!--
  自动安装的 Skill
  来源：{skill.platform}
  原始链接：{skill.source_url}
  安装时间：{datetime.now().isoformat()}
  作者：{skill.author or 'Unknown'}
  标签：{', '.join(skill.tags) if skill.tags else 'None'}
-->

"""
        return header + content

    def _sanitize_name(self, name: str) -> str:
        """清理文件名"""
        return (
            name
            .replace('/', '-')
            .replace('\\', '-')
            .replace(' ', '_')
            .replace(':', '-')
        )
