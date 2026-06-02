# -*- coding: utf-8 -*-
"""技能发现模块

提供对全球 AI Skill 生态的按需自动发现与安装能力。

核心组件:
    - SkillSearchEngine: 多源搜索引擎
    - SkillInstaller: 极简安装器
    - ISkillSource: 发现源抽象接口
    - SkillResult: 统一结果模型

使用示例:
    >>> from jarvis.jarvis_agent.skill_discovery import SkillSearchEngine, SkillInstaller
    >>>
    >>> # 搜索技能
    >>> engine = SkillSearchEngine()
    >>> results = engine.search("PDF reader")
    >>>
    >>> # 安装技能
    >>> installer = SkillInstaller(rules_manager=rules_manager)
    >>> for skill in results[:3]:
    ...     installer.install(skill)
"""

from .search_engine import SkillSearchEngine
from .installer import SkillInstaller
from .sources.base import ISkillSource, SkillResult

__all__ = [
    "SkillSearchEngine",
    "SkillInstaller",
    "ISkillSource",
    "SkillResult",
]
