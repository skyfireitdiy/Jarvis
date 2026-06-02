# -*- coding: utf-8 -*-
"""技能搜索源抽象接口和数据模型"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SkillResult:
    """技能搜索结果（统一数据模型）"""

    # 核心字段
    name: str
    description: str
    download_url: str
    source_url: str

    # 评分字段
    relevance_score: float = 0.0  # 相关度 (0-1)
    quality_score: float = 0.0  # 质量分 (0-10)
    popularity: int = 0  # 热度 (stars/downloads)

    # 元数据
    platform: str = "unknown"
    author: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    license: Optional[str] = None

    # 内部字段
    _raw_data: Dict[str, Any] = field(default_factory=dict, repr=False)
    _fetched_at: datetime = field(default_factory=datetime.now, repr=False)

    @property
    def composite_score(self) -> float:
        """综合评分 = 相关度*60% + 质量*30% + 热度*10%"""
        popularity_normalized = min(self.popularity / 100000, 1.0)  # 归一化到 0-1
        return (
            self.relevance_score * 0.6
            + (self.quality_score / 10.0) * 0.3
            + popularity_normalized * 0.1
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于序列化）"""
        return {
            "name": self.name,
            "description": self.description,
            "download_url": self.download_url,
            "source_url": self.source_url,
            "relevance_score": self.relevance_score,
            "quality_score": self.quality_score,
            "popularity": self.popularity,
            "platform": self.platform,
            "author": self.author,
            "tags": self.tags,
            "license": self.license,
            "composite_score": self.composite_score,
        }


class ISkillSource(ABC):
    """技能搜索源抽象基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """来源名称（唯一标识）"""
        pass

    @property
    def priority(self) -> int:
        """优先级（数字越小优先级越高，默认 100）"""
        return 100

    @abstractmethod
    async def search(self, query: str, limit: int = 20) -> List[SkillResult]:
        """
        搜索技能

        参数:
            query: 搜索关键词
            limit: 返回数量限制

        返回:
            技能结果列表
        """
        pass

    async def is_available(self) -> bool:
        """检查服务是否可用（健康检查）"""
        try:
            # 默认实现：尝试一次空搜索
            await self.search("", limit=1)
            return True
        except Exception:
            return False

    def _calc_relevance(self, query: str, text: str) -> float:
        """计算相关度（子类可重写）"""
        if not text:
            return 0.0

        query_words = set(query.lower().split())
        text_lower = text.lower()

        matches = sum(1 for word in query_words if word in text_lower)
        return matches / len(query_words) if query_words else 0.0
