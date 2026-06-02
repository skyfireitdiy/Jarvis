# -*- coding: utf-8 -*-
"""技能搜索引擎 - 使用依赖注入管理多个发现源"""

import asyncio
from typing import List, Dict, Optional
from .sources.base import ISkillSource, SkillResult


class SkillSearchEngine:
    """
    技能搜索引擎

    使用依赖注入接收所有发现源，负责：
    1. 并行执行所有源的搜索
    2. 合并、去重、排序结果
    3. 过滤低质量结果
    """

    def __init__(
        self,
        sources: Optional[List[ISkillSource]] = None,
        min_relevance: float = 0.5,
        min_quality: float = 5.0,
        max_results: int = 20,
    ):
        """
        参数:
            sources: 发现源列表（依赖注入）
            min_relevance: 最小相关度阈值
            min_quality: 最小质量分阈值
            max_results: 最大返回结果数
        """
        # 依赖注入：发现源
        self.sources = sources or self._default_sources()

        # 配置
        self.min_relevance = min_relevance
        self.min_quality = min_quality
        self.max_results = max_results

    def _default_sources(self) -> List[ISkillSource]:
        """默认发现源（可按需覆盖）"""
        from .sources.skillhub import SkillHubSource
        from .sources.github import GitHubSkillSource

        return [
            SkillHubSource(),  # 高优先级
            GitHubSkillSource(),  # 中等优先级
        ]

    async def search_async(self, query: str) -> List[SkillResult]:
        """
        异步搜索所有源

        参数:
            query: 搜索关键词

        返回:
            按综合评分排序的结果列表
        """
        # 1. 并行执行所有源的搜索
        tasks = [source.search(query) for source in self.sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 2. 合并结果（过滤异常）
        all_skills: List[SkillResult] = []
        for result in results:
            if isinstance(result, list):
                all_skills.extend(result)
            elif isinstance(result, Exception):
                # 记录日志但不中断
                pass

        # 3. 去重（按 name）
        seen = set()
        unique_skills = []
        for skill in all_skills:
            if skill.name not in seen:
                seen.add(skill.name)
                unique_skills.append(skill)

        # 4. 过滤低质量结果
        filtered = [
            s
            for s in unique_skills
            if s.relevance_score >= self.min_relevance
            and s.quality_score >= self.min_quality
        ]

        # 5. 按综合评分排序
        filtered.sort(key=lambda s: s.composite_score, reverse=True)

        # 6. 限制返回数量
        return filtered[: self.max_results]

    def search(self, query: str) -> List[SkillResult]:
        """同步搜索包装器"""
        return asyncio.run(self.search_async(query))

    async def health_check(self) -> Dict[str, bool]:
        """检查所有源的可用性"""
        tasks = {source.name: source.is_available() for source in self.sources}

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        return {name: (result is True) for name, result in zip(tasks.keys(), results)}

    def add_source(self, source: ISkillSource) -> None:
        """动态添加发现源"""
        self.sources.append(source)
        # 按优先级排序
        self.sources.sort(key=lambda s: s.priority)

    def remove_source(self, source_name: str) -> bool:
        """移除发现源"""
        for i, source in enumerate(self.sources):
            if source.name == source_name:
                del self.sources[i]
                return True
        return False
