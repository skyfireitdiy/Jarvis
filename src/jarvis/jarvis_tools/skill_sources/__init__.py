# -*- coding: utf-8 -*-
"""技能搜索源模块"""

from .base import ISkillSource, SkillResult
from .skillhub import SkillHubSource
from .github import GitHubSkillSource

__all__ = [
    "ISkillSource",
    "SkillResult",
    "SkillHubSource",
    "GitHubSkillSource",
]
