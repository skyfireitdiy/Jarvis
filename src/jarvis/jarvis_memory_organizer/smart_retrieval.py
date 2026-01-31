"""智能检索增强模块

该模块提供知识智能检索增强功能，包括：
- 语义检索：基于查询意图和关键词的智能检索
- 知识推荐：基于任务上下文的知识推荐
- 相关知识关联：查找与指定记忆相关的知识
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from jarvis.jarvis_utils.config import get_data_dir


@dataclass
class Memory:
    """记忆数据类

    存储记忆的基本信息。
    """

    id: str = ""
    type: str = ""
    tags: List[str] = field(default_factory=list)
    content: str = ""
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Memory":
        """从字典创建Memory对象"""
        return cls(
            id=data.get("id", ""),
            type=data.get("type", ""),
            tags=data.get("tags", []),
            content=data.get("content", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "type": self.type,
            "tags": self.tags,
            "content": self.content,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class SemanticQuery:
    """语义查询数据类

    存储查询分析的结果。
    """

    query_text: str = ""  # 原始查询文本
    extracted_keywords: List[str] = field(default_factory=list)  # 提取的关键词
    expanded_tags: List[str] = field(default_factory=list)  # 扩展的标签
    intent: str = ""  # 查询意图
    context: Optional[str] = None  # 上下文信息


@dataclass
class RecommendationContext:
    """推荐上下文数据类

    存储任务执行的上下文信息，用于知识推荐。
    """

    task_description: str = ""  # 任务描述
    current_step: str = ""  # 当前步骤
    tool_calls: List[str] = field(default_factory=list)  # 工具调用列表
    errors: List[str] = field(default_factory=list)  # 错误列表


@dataclass
class RelevanceScore:
    """相关性得分数据类

    存储各维度的相关性得分。
    """

    tag_match: float = 0.0  # 标签匹配度（30%）
    content_similarity: float = 0.0  # 内容语义相似度（40%）
    time_freshness: float = 0.0  # 时间新鲜度（15%）
    usage_frequency: float = 0.0  # 使用频率（15%）

    @property
    def total(self) -> float:
        """计算加权总分"""
        return (
            self.tag_match * 0.3
            + self.content_similarity * 0.4
            + self.time_freshness * 0.15
            + self.usage_frequency * 0.15
        )


class SmartRetriever:
    """智能检索器

    提供语义检索、知识推荐和相关知识关联功能。
    """

    # 常用关键词到标签的映射
    KEYWORD_TAG_MAPPING: Dict[str, List[str]] = {
        "代码": ["code", "coding", "programming", "代码"],
        "测试": ["test", "testing", "pytest", "测试"],
        "重构": ["refactoring", "refactor", "重构"],
        "架构": ["architecture", "design", "架构"],
        "配置": ["config", "configuration", "配置"],
        "部署": ["deploy", "deployment", "部署"],
        "文档": ["doc", "documentation", "文档"],
        "安全": ["security", "安全"],
        "性能": ["performance", "性能"],
        "错误": ["error", "bug", "fix", "错误"],
        "方法论": ["methodology", "方法论"],
        "记忆": ["memory", "记忆"],
        "规则": ["rule", "规则"],
    }

    def __init__(self):
        """初始化智能检索器"""
        self.project_memory_dir = Path(".jarvis/memory")
        self.global_memory_dir = Path(get_data_dir()) / "memory"
        self._usage_stats: Dict[str, int] = {}  # 记忆使用统计

    def semantic_search(
        self,
        query: str,
        memory_types: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[Memory]:
        """语义检索

        基于查询意图和关键词进行智能检索。

        Args:
            query: 查询文本
            memory_types: 要检索的记忆类型列表，默认检索所有类型
            limit: 返回结果的最大数量

        Returns:
            按相关性排序的记忆列表
        """
        # 1. 分析查询
        semantic_query = self._analyze_query(query)

        # 2. 确定检索类型
        if memory_types is None:
            memory_types = ["project_long_term", "global_long_term"]

        # 3. 检索候选记忆
        candidates = self._retrieve_candidates(
            semantic_query.expanded_tags, memory_types
        )

        # 4. 计算相关性得分并排序
        scored_memories = []
        for memory in candidates:
            score = self._calculate_relevance_score(memory, semantic_query)
            scored_memories.append((memory, score.total))

        # 5. 按得分排序
        scored_memories.sort(key=lambda x: x[1], reverse=True)

        # 6. 返回前N个结果
        result = [m for m, _ in scored_memories[:limit]]

        # 更新使用统计
        for memory in result:
            self._update_usage_stats(memory.id)

        return result

    def recommend_knowledge(
        self,
        context: RecommendationContext,
        limit: int = 5,
    ) -> List[Memory]:
        """知识推荐

        基于任务上下文推荐相关知识。

        Args:
            context: 推荐上下文
            limit: 返回结果的最大数量

        Returns:
            推荐的记忆列表
        """
        # 1. 从上下文提取关键词
        keywords = self._extract_keywords_from_context(context)

        # 2. 扩展标签
        expanded_tags = self._expand_tags(keywords)

        # 3. 检索候选记忆
        candidates = self._retrieve_candidates(
            expanded_tags, ["project_long_term", "global_long_term"]
        )

        # 4. 计算推荐得分
        scored_memories = []
        for memory in candidates:
            score = self._calculate_recommendation_score(memory, context, keywords)
            scored_memories.append((memory, score))

        # 5. 按得分排序
        scored_memories.sort(key=lambda x: x[1], reverse=True)

        # 6. 返回前N个结果
        return [m for m, _ in scored_memories[:limit]]

    def find_related_knowledge(
        self,
        memory_id: str,
        limit: int = 5,
    ) -> List[Memory]:
        """查找相关知识

        查找与指定记忆相关的其他知识。

        Args:
            memory_id: 记忆ID
            limit: 返回结果的最大数量

        Returns:
            相关的记忆列表
        """
        # 1. 加载目标记忆
        target_memory = self._load_memory_by_id(memory_id)
        if target_memory is None:
            return []

        # 2. 加载所有记忆
        all_memories = self._load_all_memories(
            ["project_long_term", "global_long_term"]
        )

        # 3. 计算关联得分
        related_memories = []
        for memory in all_memories:
            if memory.id == memory_id:
                continue

            # 计算标签关联
            tag_overlap = len(set(target_memory.tags) & set(memory.tags))

            # 计算内容相似度
            content_similarity = self._calculate_content_similarity(
                target_memory.content, memory.content
            )

            # 综合得分：标签关联（50%）+ 内容相似度（50%）
            score = tag_overlap * 0.5 + content_similarity * 0.5

            # 只保留有一定关联的记忆（至少2个共享标签或相似度≥0.3）
            if tag_overlap >= 2 or content_similarity >= 0.3:
                related_memories.append((memory, score))

        # 4. 按得分排序
        related_memories.sort(key=lambda x: x[1], reverse=True)

        # 5. 返回前N个结果
        return [m for m, _ in related_memories[:limit]]

    def _analyze_query(self, query: str) -> SemanticQuery:
        """分析查询文本

        提取关键词、扩展标签、识别意图。
        """
        # 提取关键词
        keywords = self._extract_keywords(query)

        # 扩展标签
        expanded_tags = self._expand_tags(keywords)

        # 识别意图
        intent = self._identify_intent(query)

        return SemanticQuery(
            query_text=query,
            extracted_keywords=keywords,
            expanded_tags=expanded_tags,
            intent=intent,
        )

    def _extract_keywords(self, text: str) -> List[str]:
        """从文本中提取关键词"""
        keywords = []

        # 使用简单的分词和关键词提取
        # 移除标点符号
        clean_text = re.sub(r"[^\w\s]", " ", text)

        # 分词
        words = clean_text.split()

        # 过滤停用词和短词
        stop_words = {
            "的",
            "是",
            "在",
            "和",
            "了",
            "有",
            "我",
            "你",
            "他",
            "她",
            "它",
            "这",
            "那",
            "什么",
            "怎么",
            "如何",
            "为什么",
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "can",
            "to",
            "of",
            "in",
            "for",
            "on",
            "with",
            "at",
            "by",
            "from",
            "as",
            "into",
            "through",
            "during",
            "before",
            "after",
            "above",
            "below",
            "between",
            "under",
            "again",
            "further",
            "then",
            "once",
            "here",
            "there",
            "when",
            "where",
            "why",
            "how",
            "all",
            "each",
            "few",
            "more",
            "most",
            "other",
            "some",
            "such",
            "no",
            "nor",
            "not",
            "only",
            "own",
            "same",
            "so",
            "than",
            "too",
            "very",
            "just",
            "and",
            "but",
            "if",
            "or",
            "because",
            "until",
            "while",
        }

        for word in words:
            word_lower = word.lower()
            if len(word) >= 2 and word_lower not in stop_words:
                keywords.append(word_lower)

        return list(set(keywords))

    def _expand_tags(self, keywords: List[str]) -> List[str]:
        """扩展关键词为标签"""
        expanded_tags = set(keywords)

        for keyword in keywords:
            # 检查关键词映射
            for key, tags in self.KEYWORD_TAG_MAPPING.items():
                if keyword in key or key in keyword:
                    expanded_tags.update(tags)

        return list(expanded_tags)

    def _identify_intent(self, query: str) -> str:
        """识别查询意图"""
        query_lower = query.lower()

        # 简单的意图识别规则
        if any(word in query_lower for word in ["如何", "怎么", "how", "方法"]):
            return "how_to"
        elif any(word in query_lower for word in ["什么", "是什么", "what", "定义"]):
            return "definition"
        elif any(word in query_lower for word in ["为什么", "why", "原因"]):
            return "reason"
        elif any(
            word in query_lower for word in ["错误", "问题", "error", "bug", "fix"]
        ):
            return "troubleshooting"
        elif any(word in query_lower for word in ["最佳", "推荐", "best", "recommend"]):
            return "recommendation"
        else:
            return "general"

    def _retrieve_candidates(
        self, tags: List[str], memory_types: List[str]
    ) -> List[Memory]:
        """检索候选记忆"""
        candidates = []

        for memory_type in memory_types:
            memories = self._load_memories_by_type(memory_type)
            for memory in memories:
                # 检查标签匹配
                if tags:
                    memory_tags_lower = [t.lower() for t in memory.tags]
                    tags_lower = [t.lower() for t in tags]
                    if any(tag in memory_tags_lower for tag in tags_lower):
                        candidates.append(memory)
                else:
                    candidates.append(memory)

        return candidates

    def _load_memories_by_type(self, memory_type: str) -> List[Memory]:
        """加载指定类型的所有记忆"""
        memories: List[Memory] = []

        if memory_type == "project_long_term":
            memory_dir = self.project_memory_dir
        elif memory_type == "global_long_term":
            memory_dir = self.global_memory_dir / memory_type
        else:
            return memories

        if not memory_dir.exists():
            return memories

        for memory_file in memory_dir.glob("*.json"):
            try:
                with open(memory_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    memories.append(Memory.from_dict(data))
            except Exception:
                continue

        return memories

    def _load_all_memories(self, memory_types: List[str]) -> List[Memory]:
        """加载所有指定类型的记忆"""
        all_memories = []
        for memory_type in memory_types:
            all_memories.extend(self._load_memories_by_type(memory_type))
        return all_memories

    def _load_memory_by_id(self, memory_id: str) -> Optional[Memory]:
        """根据ID加载记忆"""
        # 在项目记忆中查找
        memory_file = self.project_memory_dir / f"{memory_id}.json"
        if memory_file.exists():
            try:
                with open(memory_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return Memory.from_dict(data)
            except Exception:
                pass

        # 在全局记忆中查找
        for memory_type in ["global_long_term"]:
            memory_file = self.global_memory_dir / memory_type / f"{memory_id}.json"
            if memory_file.exists():
                try:
                    with open(memory_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        return Memory.from_dict(data)
                except Exception:
                    pass

        return None

    def _calculate_relevance_score(
        self, memory: Memory, query: SemanticQuery
    ) -> RelevanceScore:
        """计算相关性得分"""
        score = RelevanceScore()

        # 1. 标签匹配度（0-100）
        if query.expanded_tags:
            memory_tags_lower = [t.lower() for t in memory.tags]
            query_tags_lower = [t.lower() for t in query.expanded_tags]
            matched_tags = sum(
                1 for tag in query_tags_lower if tag in memory_tags_lower
            )
            score.tag_match = min(100, matched_tags * 20)  # 每个匹配标签20分

        # 2. 内容语义相似度（0-100）
        score.content_similarity = (
            self._calculate_content_similarity(query.query_text, memory.content) * 100
        )

        # 3. 时间新鲜度（0-100）
        score.time_freshness = self._calculate_time_freshness(memory.created_at)

        # 4. 使用频率（0-100）
        score.usage_frequency = self._calculate_usage_frequency(memory.id)

        return score

    def _calculate_content_similarity(self, text1: str, text2: str) -> float:
        """计算内容相似度（简单的词重叠方法）"""
        if not text1 or not text2:
            return 0.0

        # 提取关键词
        keywords1 = set(self._extract_keywords(text1))
        keywords2 = set(self._extract_keywords(text2))

        if not keywords1 or not keywords2:
            return 0.0

        # 计算Jaccard相似度
        intersection = len(keywords1 & keywords2)
        union = len(keywords1 | keywords2)

        return intersection / union if union > 0 else 0.0

    def _calculate_time_freshness(self, created_at: str) -> float:
        """计算时间新鲜度（0-100）"""
        if not created_at:
            return 50.0  # 默认中等新鲜度

        try:
            # 解析时间
            created_time = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            now = (
                datetime.now(created_time.tzinfo)
                if created_time.tzinfo
                else datetime.now()
            )

            # 计算天数差
            days_diff = (now - created_time).days

            # 新鲜度衰减：7天内100分，之后每7天减10分，最低10分
            if days_diff <= 7:
                return 100.0
            else:
                freshness = 100.0 - ((days_diff - 7) / 7) * 10
                return max(10.0, freshness)
        except Exception:
            return 50.0

    def _calculate_usage_frequency(self, memory_id: str) -> float:
        """计算使用频率得分（0-100）"""
        usage_count = self._usage_stats.get(memory_id, 0)

        # 使用次数越多，得分越高，最高100分
        # 每次使用增加10分，最高100分
        return min(100.0, usage_count * 10)

    def _update_usage_stats(self, memory_id: str) -> None:
        """更新使用统计"""
        self._usage_stats[memory_id] = self._usage_stats.get(memory_id, 0) + 1

    def _extract_keywords_from_context(
        self, context: RecommendationContext
    ) -> List[str]:
        """从推荐上下文中提取关键词"""
        keywords = []

        # 从任务描述提取
        if context.task_description:
            keywords.extend(self._extract_keywords(context.task_description))

        # 从当前步骤提取
        if context.current_step:
            keywords.extend(self._extract_keywords(context.current_step))

        # 从工具调用提取
        for tool_call in context.tool_calls:
            keywords.extend(self._extract_keywords(tool_call))

        # 从错误信息提取
        for error in context.errors:
            keywords.extend(self._extract_keywords(error))

        return list(set(keywords))

    def _calculate_recommendation_score(
        self,
        memory: Memory,
        context: RecommendationContext,
        keywords: List[str],
    ) -> float:
        """计算推荐得分"""
        # 1. 标签匹配度（30%）
        expanded_tags = self._expand_tags(keywords)
        memory_tags_lower = [t.lower() for t in memory.tags]
        tags_lower = [t.lower() for t in expanded_tags]
        matched_tags = sum(1 for tag in tags_lower if tag in memory_tags_lower)
        tag_score = min(100, matched_tags * 20)

        # 2. 内容相似度（40%）
        combined_text = f"{context.task_description} {context.current_step}"
        content_score = (
            self._calculate_content_similarity(combined_text, memory.content) * 100
        )

        # 3. 时间新鲜度（15%）
        time_score = self._calculate_time_freshness(memory.created_at)

        # 4. 使用频率（15%）
        usage_score = self._calculate_usage_frequency(memory.id)

        # 加权总分
        return (
            tag_score * 0.3
            + content_score * 0.4
            + time_score * 0.15
            + usage_score * 0.15
        )
