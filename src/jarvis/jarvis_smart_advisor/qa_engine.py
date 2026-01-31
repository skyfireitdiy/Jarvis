"""智能问答引擎

该模块提供智能问答功能，整合知识图谱和智能检索能力，
回答项目相关问题。
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from jarvis.jarvis_knowledge_graph import KnowledgeGraph, NodeType
from jarvis.jarvis_memory_organizer.smart_retrieval import (
    Memory,
    SmartRetriever,
)


class QuestionCategory(Enum):
    """问题类别"""

    PROJECT_STRUCTURE = "project_structure"  # 项目结构问题
    CODE_FUNCTION = "code_function"  # 代码功能问题
    BEST_PRACTICE = "best_practice"  # 最佳实践问题
    HISTORY_DECISION = "history_decision"  # 历史决策问题
    GENERAL = "general"  # 通用问题


@dataclass
class Question:
    """问题数据类"""

    text: str  # 问题文本
    category: QuestionCategory = QuestionCategory.GENERAL  # 问题类别
    keywords: List[str] = field(default_factory=list)  # 关键词
    intent: str = ""  # 意图
    entities: List[str] = field(default_factory=list)  # 实体


@dataclass
class Answer:
    """答案数据类"""

    text: str  # 答案文本
    confidence: float = 0.0  # 置信度 (0-1)
    sources: List[str] = field(default_factory=list)  # 知识来源
    related_knowledge: List[str] = field(default_factory=list)  # 相关知识


class QAEngine:
    """智能问答引擎

    整合知识图谱和智能检索能力，回答项目相关问题。
    """

    # 问题类别关键词映射（按优先级排序，越靠前优先级越高）
    CATEGORY_KEYWORDS: Dict[QuestionCategory, List[str]] = {
        QuestionCategory.HISTORY_DECISION: [
            "为什么",
            "决策",
            "选择",
            "原因",
            "历史",
            "why",
            "decision",
            "choose",
            "reason",
        ],
        QuestionCategory.BEST_PRACTICE: [
            "最佳实践",
            "推荐",
            "建议",
            "规范",
            "标准",
            "best practice",
            "recommend",
            "guideline",
            "standard",
        ],
        QuestionCategory.PROJECT_STRUCTURE: [
            "模块",
            "目录",
            "结构",
            "文件",
            "组织",
            "架构",
            "module",
            "directory",
            "structure",
            "file",
        ],
        QuestionCategory.CODE_FUNCTION: [
            "函数",
            "方法",
            "类",
            "功能",
            "作用",
            "实现",
            "做什么",
            "function",
            "method",
            "class",
            "implement",
        ],
    }

    def __init__(self, project_dir: str = "."):
        """初始化问答引擎

        Args:
            project_dir: 项目目录路径
        """
        self.project_dir = Path(project_dir)
        self._knowledge_graph: Optional[KnowledgeGraph] = None
        self._smart_retriever: Optional[SmartRetriever] = None

    @property
    def knowledge_graph(self) -> KnowledgeGraph:
        """懒加载知识图谱"""
        if self._knowledge_graph is None:
            storage_dir = self.project_dir / ".jarvis" / "knowledge_graph"
            self._knowledge_graph = KnowledgeGraph(str(storage_dir))
        return self._knowledge_graph

    @property
    def smart_retriever(self) -> SmartRetriever:
        """懒加载智能检索器"""
        if self._smart_retriever is None:
            self._smart_retriever = SmartRetriever()
        return self._smart_retriever

    def answer(self, question_text: str) -> Answer:
        """回答问题

        Args:
            question_text: 问题文本

        Returns:
            答案对象
        """
        # 1. 分析问题
        question = self._analyze_question(question_text)

        # 2. 检索知识
        knowledge_context = self._retrieve_knowledge(question)

        # 3. 生成答案
        answer = self._generate_answer(question, knowledge_context)

        return answer

    def _analyze_question(self, question_text: str) -> Question:
        """分析问题

        提取关键词、识别类别和意图。
        """
        # 提取关键词
        keywords = self._extract_keywords(question_text)

        # 识别类别
        category = self._identify_category(question_text, keywords)

        # 提取实体
        entities = self._extract_entities(question_text)

        # 识别意图
        intent = self._identify_intent(question_text, category)

        return Question(
            text=question_text,
            category=category,
            keywords=keywords,
            intent=intent,
            entities=entities,
        )

    def _extract_keywords(self, text: str) -> List[str]:
        """从文本中提取关键词"""
        keywords = []

        # 移除标点符号
        clean_text = re.sub(r"[^\w\s\u4e00-\u9fff]", " ", text)

        # 英文分词
        english_words = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", clean_text)

        # 中文分词（提取连续中文，然后按2字词分割）
        chinese_segments = re.findall(r"[\u4e00-\u9fff]+", clean_text)
        chinese_words = []
        for segment in chinese_segments:
            # 如果是2字词，直接添加
            if len(segment) <= 2:
                chinese_words.append(segment)
            else:
                # 对于长词，按2字分割并保留原词
                chinese_words.append(segment)
                for i in range(len(segment) - 1):
                    chinese_words.append(segment[i : i + 2])

        # 合并所有词
        words = english_words + chinese_words

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
        }

        for word in words:
            word_lower = word.lower()
            if len(word) >= 2 and word_lower not in stop_words:
                keywords.append(word_lower)

        return list(set(keywords))

    def _identify_category(self, text: str, keywords: List[str]) -> QuestionCategory:
        """识别问题类别"""
        text_lower = text.lower()

        # 计算每个类别的匹配分数
        scores: Dict[QuestionCategory, int] = {}
        for category, category_keywords in self.CATEGORY_KEYWORDS.items():
            score = 0
            for kw in category_keywords:
                if kw.lower() in text_lower:
                    score += 2
                if kw.lower() in keywords:
                    score += 1
            scores[category] = score

        # 返回得分最高的类别
        if scores:
            best_category = max(scores, key=lambda k: scores[k])
            if scores[best_category] > 0:
                return best_category

        return QuestionCategory.GENERAL

    def _extract_entities(self, text: str) -> List[str]:
        """提取实体（模块名、函数名等）"""
        entities = []

        # 匹配可能的模块名（下划线命名，如 jarvis_smart_advisor）
        module_pattern = r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+"
        modules = re.findall(module_pattern, text)
        entities.extend(modules)

        # 匹配可能的类名（驼峰命名，如 SmartAdvisor, QAEngine）
        class_pattern = r"[A-Z][a-zA-Z0-9]+"
        classes = re.findall(class_pattern, text)
        entities.extend(classes)

        # 匹配可能的函数名（小写下划线，如 extract_keywords）
        func_pattern = r"[a-z]+_[a-z_]+"
        funcs = re.findall(func_pattern, text)
        entities.extend([f for f in funcs if len(f) > 5])

        return list(set(entities))

    def _identify_intent(self, text: str, category: QuestionCategory) -> str:
        """识别问题意图"""
        text_lower = text.lower()

        # 基于问题类别和关键词识别意图
        if category == QuestionCategory.PROJECT_STRUCTURE:
            if "有哪些" in text or "包含" in text or "what" in text_lower:
                return "list_components"
            if "在哪" in text or "位置" in text or "where" in text_lower:
                return "locate_component"
            return "describe_structure"

        if category == QuestionCategory.CODE_FUNCTION:
            if "做什么" in text or "作用" in text or "what" in text_lower:
                return "explain_function"
            if "怎么用" in text or "如何使用" in text or "how" in text_lower:
                return "usage_guide"
            return "describe_code"

        if category == QuestionCategory.BEST_PRACTICE:
            if "如何" in text or "怎么" in text or "how" in text_lower:
                return "provide_guidance"
            if "推荐" in text or "建议" in text or "recommend" in text_lower:
                return "recommend_practice"
            return "explain_practice"

        if category == QuestionCategory.HISTORY_DECISION:
            if "为什么" in text or "why" in text_lower:
                return "explain_decision"
            return "describe_history"

        return "general_query"

    def _retrieve_knowledge(self, question: Question) -> Dict[str, List[Any]]:
        """检索相关知识

        从知识图谱和记忆系统中检索相关知识。
        """
        context: Dict[str, List[Any]] = {
            "graph_nodes": [],
            "memories": [],
            "related_nodes": [],
        }

        # 1. 从知识图谱检索
        try:
            # 根据问题类别选择节点类型
            node_types = self._get_relevant_node_types(question.category)

            for node_type in node_types:
                nodes = self.knowledge_graph.query_nodes(
                    node_type=node_type,
                    tags=question.keywords[:5] if question.keywords else None,
                    limit=5,
                )
                context["graph_nodes"].extend(nodes)

            # 获取相关节点
            for node in context["graph_nodes"][:3]:
                related = self.knowledge_graph.get_related_knowledge(
                    node.node_id, depth=1, limit=3
                )
                context["related_nodes"].extend(related)
        except Exception:
            # 知识图谱可能为空或不可用
            pass

        # 2. 从记忆系统检索
        try:
            memories = self.smart_retriever.semantic_search(question.text, limit=5)
            context["memories"] = memories
        except Exception:
            # 记忆系统可能不可用
            pass

        return context

    def _get_relevant_node_types(self, category: QuestionCategory) -> List[NodeType]:
        """根据问题类别获取相关的节点类型"""
        if category == QuestionCategory.PROJECT_STRUCTURE:
            return [NodeType.FILE, NodeType.CODE, NodeType.CONCEPT]
        if category == QuestionCategory.CODE_FUNCTION:
            return [NodeType.CODE, NodeType.FILE]
        if category == QuestionCategory.BEST_PRACTICE:
            return [NodeType.RULE, NodeType.METHODOLOGY, NodeType.CONCEPT]
        if category == QuestionCategory.HISTORY_DECISION:
            return [NodeType.MEMORY, NodeType.CONCEPT]
        return [NodeType.CONCEPT, NodeType.MEMORY]

    def _generate_answer(
        self, question: Question, context: Dict[str, List[Any]]
    ) -> Answer:
        """生成答案

        基于检索到的知识生成答案。
        """
        sources: List[str] = []
        related_knowledge: List[str] = []
        answer_parts: List[str] = []

        # 从知识图谱节点生成答案
        graph_nodes = context.get("graph_nodes", [])
        if graph_nodes:
            for node in graph_nodes[:3]:
                answer_parts.append(f"- **{node.name}**: {node.description}")
                if node.source_path:
                    sources.append(f"知识图谱: {node.source_path}")
                else:
                    sources.append(f"知识图谱: {node.name}")

        # 从记忆生成答案
        memories = context.get("memories", [])
        if memories:
            for memory in memories[:3]:
                if isinstance(memory, Memory):
                    # 截取内容的前200个字符
                    content_preview = memory.content[:200]
                    if len(memory.content) > 200:
                        content_preview += "..."
                    answer_parts.append(f"- {content_preview}")
                    sources.append(f"记忆: {memory.id}")

        # 添加相关知识
        related_nodes = context.get("related_nodes", [])
        for node in related_nodes[:3]:
            related_knowledge.append(f"{node.name}: {node.description[:100]}")

        # 组装答案
        if answer_parts:
            answer_text = f"关于您的问题「{question.text}」，以下是相关信息：\n\n"
            answer_text += "\n".join(answer_parts)
            confidence = min(0.9, 0.3 + 0.2 * len(answer_parts))
        else:
            answer_text = (
                f"抱歉，关于「{question.text}」，"
                "我暂时没有找到相关的知识。\n\n"
                "您可以尝试：\n"
                "1. 使用更具体的关键词重新提问\n"
                "2. 查看项目文档或代码注释\n"
                "3. 使用代码搜索工具查找相关代码"
            )
            confidence = 0.1

        return Answer(
            text=answer_text,
            confidence=confidence,
            sources=sources,
            related_knowledge=related_knowledge,
        )
