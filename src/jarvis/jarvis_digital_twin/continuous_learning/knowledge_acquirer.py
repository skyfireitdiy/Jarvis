"""知识获取器模块。

负责从交互中提取新知识，支持多种知识来源。
与knowledge_graph模块集成，实现知识的存储和检索。
"""

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from jarvis.jarvis_digital_twin.continuous_learning.types import (
    Knowledge,
    KnowledgeSourceProtocol,
    KnowledgeType,
    LearningStatus,
)


@dataclass
class KnowledgeRecord:
    """知识记录数据类。

    用于内部存储知识及其状态。
    """

    # 知识对象
    knowledge: Knowledge
    # 学习状态
    status: LearningStatus = LearningStatus.LEARNED
    # 内容哈希（用于去重）
    content_hash: str = ""

    def __post_init__(self) -> None:
        """初始化后计算内容哈希。"""
        if not self.content_hash:
            self.content_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """计算知识内容的哈希值。"""
        content = f"{self.knowledge.type.value}:{self.knowledge.content}"
        return hashlib.md5(content.encode()).hexdigest()


class InteractionKnowledgeSource:
    """交互知识来源。

    从对话交互中提取知识，包括概念、事实和规则。
    """

    # 概念提取模式
    CONCEPT_PATTERNS = [
        r"(?:是|指|定义为|表示)\s*[：:]?\s*(.+)",
        r"(?:means?|refers? to|is defined as)\s*[:]?\s*(.+)",
    ]

    # 事实提取模式
    FACT_PATTERNS = [
        r"(?:发现|确认|证实|注意到)\s*[：:]?\s*(.+)",
        r"(?:found|confirmed|noticed|discovered)\s*[:]?\s*(.+)",
    ]

    # 规则提取模式
    RULE_PATTERNS = [
        r"(?:规则|原则|要求|必须|应该)\s*[：:]?\s*(.+)",
        r"(?:rule|principle|must|should|always)\s*[:]?\s*(.+)",
    ]

    def __init__(self, min_content_length: int = 10) -> None:
        """初始化交互知识来源。

        Args:
            min_content_length: 最小内容长度，过短的内容将被忽略
        """
        self._min_content_length = min_content_length

    def extract(self, context: str) -> List[Knowledge]:
        """从上下文中提取知识。

        Args:
            context: 上下文信息

        Returns:
            提取的知识列表
        """
        if not context or len(context.strip()) < self._min_content_length:
            return []

        knowledge_list: List[Knowledge] = []

        # 提取概念
        knowledge_list.extend(
            self._extract_by_patterns(
                context, self.CONCEPT_PATTERNS, KnowledgeType.CONCEPT
            )
        )

        # 提取事实
        knowledge_list.extend(
            self._extract_by_patterns(context, self.FACT_PATTERNS, KnowledgeType.FACT)
        )

        # 提取规则
        knowledge_list.extend(
            self._extract_by_patterns(context, self.RULE_PATTERNS, KnowledgeType.RULE)
        )

        return knowledge_list

    def _extract_by_patterns(
        self,
        context: str,
        patterns: List[str],
        knowledge_type: KnowledgeType,
    ) -> List[Knowledge]:
        """使用模式提取知识。

        Args:
            context: 上下文
            patterns: 正则模式列表
            knowledge_type: 知识类型

        Returns:
            提取的知识列表
        """
        results: List[Knowledge] = []
        seen_contents: Set[str] = set()

        for pattern in patterns:
            matches = re.finditer(pattern, context, re.IGNORECASE)
            for match in matches:
                content = (
                    match.group(1).strip() if match.groups() else match.group(0).strip()
                )
                if (
                    len(content) >= self._min_content_length
                    and content not in seen_contents
                ):
                    seen_contents.add(content)
                    results.append(
                        Knowledge(
                            id=str(uuid.uuid4()),
                            type=knowledge_type,
                            content=content,
                            source="interaction",
                            confidence=0.7,
                        )
                    )

        return results


class CodePatternSource:
    """代码模式来源。

    从代码中提取模式和过程知识。
    """

    # 函数定义模式（Python）
    PYTHON_FUNC_PATTERN = r"def\s+(\w+)\s*\(([^)]*)\)\s*(?:->\s*([^:]+))?\s*:"

    # 类定义模式（Python）
    PYTHON_CLASS_PATTERN = r"class\s+(\w+)\s*(?:\(([^)]*)\))?\s*:"

    # 导入模式
    IMPORT_PATTERN = r"(?:from\s+([\w.]+)\s+)?import\s+([\w,\s]+)"

    # 装饰器模式
    DECORATOR_PATTERN = r"@(\w+)(?:\(([^)]*)\))?"

    def __init__(self) -> None:
        """初始化代码模式来源。"""
        self._language_patterns: Dict[str, Dict[str, str]] = {
            "python": {
                "function": self.PYTHON_FUNC_PATTERN,
                "class": self.PYTHON_CLASS_PATTERN,
                "import": self.IMPORT_PATTERN,
                "decorator": self.DECORATOR_PATTERN,
            }
        }

    def extract(self, context: str) -> List[Knowledge]:
        """从代码上下文中提取知识。

        Args:
            context: 代码内容

        Returns:
            提取的知识列表
        """
        # 默认使用Python模式
        return self.extract_from_code(context, "python")

    def extract_from_code(
        self,
        code: str,
        language: str,
    ) -> List[Knowledge]:
        """从代码中提取模式知识。

        Args:
            code: 代码内容
            language: 编程语言

        Returns:
            提取的知识列表
        """
        if not code or language not in self._language_patterns:
            return []

        knowledge_list: List[Knowledge] = []
        patterns = self._language_patterns[language]

        # 提取函数模式
        if "function" in patterns:
            func_matches = re.finditer(patterns["function"], code)
            for match in func_matches:
                func_name = match.group(1)
                params = (
                    match.group(2) if match.groups() and len(match.groups()) > 1 else ""
                )
                return_type = (
                    match.group(3)
                    if match.groups() and len(match.groups()) > 2
                    else None
                )

                content = f"函数 {func_name}({params})"
                if return_type:
                    content += f" -> {return_type.strip()}"

                knowledge_list.append(
                    Knowledge(
                        id=str(uuid.uuid4()),
                        type=KnowledgeType.PATTERN,
                        content=content,
                        source=f"code:{language}",
                        confidence=0.9,
                        metadata={"function_name": func_name, "language": language},
                    )
                )

        # 提取类模式
        if "class" in patterns:
            class_matches = re.finditer(patterns["class"], code)
            for match in class_matches:
                class_name = match.group(1)
                bases = (
                    match.group(2) if match.groups() and len(match.groups()) > 1 else ""
                )

                content = f"类 {class_name}"
                if bases:
                    content += f"({bases})"

                knowledge_list.append(
                    Knowledge(
                        id=str(uuid.uuid4()),
                        type=KnowledgeType.PATTERN,
                        content=content,
                        source=f"code:{language}",
                        confidence=0.9,
                        metadata={"class_name": class_name, "language": language},
                    )
                )

        return knowledge_list


class ErrorLearningSource:
    """错误学习来源。

    从错误信息中学习规则知识。
    """

    # 常见错误模式
    ERROR_PATTERNS = [
        (r"(\w+Error):\s*(.+)", "Python错误"),
        (r"(\w+Exception):\s*(.+)", "Java异常"),
        (r"error\[E\d+\]:\s*(.+)", "Rust错误"),
        (r"TypeError:\s*(.+)", "类型错误"),
        (r"ValueError:\s*(.+)", "值错误"),
        (r"ImportError:\s*(.+)", "导入错误"),
        (r"AttributeError:\s*(.+)", "属性错误"),
        (r"KeyError:\s*(.+)", "键错误"),
        (r"IndexError:\s*(.+)", "索引错误"),
    ]

    def __init__(self) -> None:
        """初始化错误学习来源。"""
        self._error_history: Dict[str, int] = {}  # 错误类型 -> 出现次数

    def extract(self, context: str) -> List[Knowledge]:
        """从错误上下文中提取知识。

        Args:
            context: 错误信息

        Returns:
            提取的知识列表
        """
        return self.learn_from_error(context, "")

    def learn_from_error(
        self,
        error: str,
        context: str,
    ) -> List[Knowledge]:
        """从错误中学习规则知识。

        Args:
            error: 错误信息
            context: 错误发生的上下文

        Returns:
            提取的知识列表
        """
        if not error:
            return []

        knowledge_list: List[Knowledge] = []

        for pattern, error_category in self.ERROR_PATTERNS:
            matches = re.finditer(pattern, error, re.IGNORECASE)
            for match in matches:
                if match.groups():
                    error_type = (
                        match.group(1) if len(match.groups()) > 1 else error_category
                    )
                    error_msg = (
                        match.group(2) if len(match.groups()) > 1 else match.group(1)
                    )
                else:
                    error_type = error_category
                    error_msg = match.group(0)

                # 记录错误历史
                self._error_history[error_type] = (
                    self._error_history.get(error_type, 0) + 1
                )

                # 生成规则知识
                rule_content = f"避免 {error_type}: {error_msg.strip()}"
                if context:
                    rule_content += f" (上下文: {context[:100]})"

                knowledge_list.append(
                    Knowledge(
                        id=str(uuid.uuid4()),
                        type=KnowledgeType.RULE,
                        content=rule_content,
                        source="error",
                        confidence=0.8,
                        metadata={
                            "error_type": error_type,
                            "occurrence_count": self._error_history[error_type],
                        },
                    )
                )

        return knowledge_list

    def get_error_statistics(self) -> Dict[str, int]:
        """获取错误统计信息。

        Returns:
            错误类型到出现次数的映射
        """
        return dict(self._error_history)


class KnowledgeAcquirer:
    """知识获取器。

    负责从交互中提取新知识，支持多种知识来源。
    实现知识的存储、检索和去重。
    """

    def __init__(
        self,
        knowledge_graph: Optional[Any] = None,
        memory_manager: Optional[Any] = None,
        llm_client: Optional[Any] = None,
    ) -> None:
        """初始化知识获取器。

        Args:
            knowledge_graph: 知识图谱实例（可选）
            memory_manager: 记忆管理器实例（可选）
            llm_client: LLM客户端（可选）
        """
        self._llm_client = llm_client
        self._knowledge_graph = knowledge_graph
        self._memory_manager = memory_manager

        # 内部知识存储
        self._knowledge_store: Dict[str, KnowledgeRecord] = {}
        # 内容哈希索引（用于去重）
        self._content_hash_index: Dict[str, str] = {}  # hash -> knowledge_id

        # 注册的知识来源
        self._sources: List[KnowledgeSourceProtocol] = []

        # 内置知识来源
        self._interaction_source = InteractionKnowledgeSource()
        self._code_source = CodePatternSource()
        self._error_source = ErrorLearningSource()

    def register_source(self, source: KnowledgeSourceProtocol) -> None:
        """注册知识来源。

        Args:
            source: 实现KnowledgeSourceProtocol的知识来源
        """
        if source not in self._sources:
            self._sources.append(source)

    def unregister_source(self, source: KnowledgeSourceProtocol) -> bool:
        """取消注册知识来源。

        Args:
            source: 要取消的知识来源

        Returns:
            是否成功取消
        """
        if source in self._sources:
            self._sources.remove(source)
            return True
        return False

    def extract_knowledge(
        self,
        context: str,
        source: str = "interaction",
    ) -> List[Knowledge]:
        """从交互中提取知识。

        Args:
            context: 交互上下文
            source: 来源标识

        Returns:
            提取的知识列表
        """
        if not context:
            return []

        knowledge_list: List[Knowledge] = []

        # 使用内置交互来源
        extracted = self._interaction_source.extract(context)
        for k in extracted:
            k.source = source
        knowledge_list.extend(extracted)

        # 使用注册的自定义来源
        for custom_source in self._sources:
            try:
                custom_extracted = custom_source.extract(context)
                knowledge_list.extend(custom_extracted)
            except Exception:
                # 忽略来源提取错误，继续处理其他来源
                pass

        # 存储提取的知识（自动去重）
        stored_knowledge: List[Knowledge] = []
        for knowledge in knowledge_list:
            if self.store_knowledge(knowledge):
                stored_knowledge.append(knowledge)

        return stored_knowledge

    def learn_from_code(
        self,
        code: str,
        language: str = "python",
    ) -> List[Knowledge]:
        """从代码中学习模式。

        Args:
            code: 代码内容
            language: 编程语言

        Returns:
            提取的知识列表
        """
        if not code:
            return []

        knowledge_list = self._code_source.extract_from_code(code, language)

        # 存储提取的知识（自动去重）
        stored_knowledge: List[Knowledge] = []
        for knowledge in knowledge_list:
            if self.store_knowledge(knowledge):
                stored_knowledge.append(knowledge)

        return stored_knowledge

    def learn_from_error(
        self,
        error: str,
        context: str = "",
    ) -> List[Knowledge]:
        """从错误中学习。

        Args:
            error: 错误信息
            context: 错误发生的上下文

        Returns:
            提取的知识列表
        """
        if not error:
            return []

        knowledge_list = self._error_source.learn_from_error(error, context)

        # 存储提取的知识（自动去重）
        stored_knowledge: List[Knowledge] = []
        for knowledge in knowledge_list:
            if self.store_knowledge(knowledge):
                stored_knowledge.append(knowledge)

        return stored_knowledge

    def store_knowledge(self, knowledge: Knowledge) -> bool:
        """存储知识。

        自动进行去重检查，相同内容的知识不会重复存储。

        Args:
            knowledge: 要存储的知识

        Returns:
            是否成功存储（如果是重复知识则返回False）
        """
        record = KnowledgeRecord(knowledge=knowledge)

        # 检查是否重复
        if record.content_hash in self._content_hash_index:
            existing_id = self._content_hash_index[record.content_hash]
            # 更新已有知识的置信度
            if existing_id in self._knowledge_store:
                existing_record = self._knowledge_store[existing_id]
                # 增加置信度（最高1.0）
                new_confidence = min(1.0, existing_record.knowledge.confidence + 0.1)
                existing_record.knowledge.confidence = new_confidence
                existing_record.knowledge.updated_at = datetime.now()
            return False

        # 存储新知识
        self._knowledge_store[knowledge.id] = record
        self._content_hash_index[record.content_hash] = knowledge.id

        # 如果有知识图谱，同步存储
        if self._knowledge_graph is not None:
            try:
                # 假设knowledge_graph有add_node方法
                if hasattr(self._knowledge_graph, "add_node"):
                    self._knowledge_graph.add_node(
                        node_type="knowledge",
                        name=knowledge.content[:50],
                        description=knowledge.content,
                        tags=[knowledge.type.value, knowledge.source],
                    )
            except Exception:
                # 忽略知识图谱存储错误
                pass

        return True

    def get_knowledge(self, knowledge_id: str) -> Optional[Knowledge]:
        """获取知识。

        Args:
            knowledge_id: 知识ID

        Returns:
            知识对象，如果不存在则返回None
        """
        record = self._knowledge_store.get(knowledge_id)
        return record.knowledge if record else None

    def search_knowledge(
        self,
        query: str,
        limit: int = 10,
        knowledge_type: Optional[KnowledgeType] = None,
    ) -> List[Knowledge]:
        """搜索知识。

        Args:
            query: 搜索查询
            limit: 返回结果数量限制
            knowledge_type: 可选的知识类型过滤

        Returns:
            匹配的知识列表
        """
        if not query:
            return []

        results: List[Knowledge] = []
        query_lower = query.lower()

        for record in self._knowledge_store.values():
            knowledge = record.knowledge

            # 类型过滤
            if knowledge_type and knowledge.type != knowledge_type:
                continue

            # 内容匹配
            if query_lower in knowledge.content.lower():
                results.append(knowledge)

            if len(results) >= limit:
                break

        # 按置信度排序
        results.sort(key=lambda k: k.confidence, reverse=True)

        return results[:limit]

    def update_confidence(
        self,
        knowledge_id: str,
        delta: float,
    ) -> bool:
        """更新知识置信度。

        Args:
            knowledge_id: 知识ID
            delta: 置信度变化量（可正可负）

        Returns:
            是否成功更新
        """
        record = self._knowledge_store.get(knowledge_id)
        if not record:
            return False

        # 更新置信度，保持在[0, 1]范围内
        new_confidence = max(0.0, min(1.0, record.knowledge.confidence + delta))
        record.knowledge.confidence = new_confidence
        record.knowledge.updated_at = datetime.now()

        # 如果置信度过低，标记为废弃
        if new_confidence < 0.1:
            record.status = LearningStatus.DEPRECATED

        return True

    def verify_knowledge(self, knowledge_id: str) -> bool:
        """验证知识。

        将知识状态更新为已验证。

        Args:
            knowledge_id: 知识ID

        Returns:
            是否成功验证
        """
        record = self._knowledge_store.get(knowledge_id)
        if not record:
            return False

        record.status = LearningStatus.VERIFIED
        record.knowledge.confidence = min(1.0, record.knowledge.confidence + 0.2)
        record.knowledge.updated_at = datetime.now()
        return True

    def deprecate_knowledge(self, knowledge_id: str) -> bool:
        """废弃知识。

        将知识状态更新为已废弃。

        Args:
            knowledge_id: 知识ID

        Returns:
            是否成功废弃
        """
        record = self._knowledge_store.get(knowledge_id)
        if not record:
            return False

        record.status = LearningStatus.DEPRECATED
        record.knowledge.updated_at = datetime.now()
        return True

    def get_all_knowledge(
        self,
        include_deprecated: bool = False,
    ) -> List[Knowledge]:
        """获取所有知识。

        Args:
            include_deprecated: 是否包含已废弃的知识

        Returns:
            知识列表
        """
        results: List[Knowledge] = []
        for record in self._knowledge_store.values():
            if not include_deprecated and record.status == LearningStatus.DEPRECATED:
                continue
            results.append(record.knowledge)
        return results

    def get_knowledge_by_type(
        self,
        knowledge_type: KnowledgeType,
    ) -> List[Knowledge]:
        """按类型获取知识。

        Args:
            knowledge_type: 知识类型

        Returns:
            指定类型的知识列表
        """
        return [
            record.knowledge
            for record in self._knowledge_store.values()
            if record.knowledge.type == knowledge_type
            and record.status != LearningStatus.DEPRECATED
        ]

    def get_knowledge_count(self) -> int:
        """获取知识数量。

        Returns:
            存储的知识数量（不包括已废弃的）
        """
        return sum(
            1
            for record in self._knowledge_store.values()
            if record.status != LearningStatus.DEPRECATED
        )

    def clear_all(self) -> None:
        """清除所有知识。"""
        self._knowledge_store.clear()
        self._content_hash_index.clear()

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息。

        Returns:
            统计信息字典
        """
        type_counts: Dict[str, int] = {}
        status_counts: Dict[str, int] = {}
        total_confidence = 0.0

        for record in self._knowledge_store.values():
            # 类型统计
            type_name = record.knowledge.type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1

            # 状态统计
            status_name = record.status.value
            status_counts[status_name] = status_counts.get(status_name, 0) + 1

            # 置信度累计
            total_confidence += record.knowledge.confidence

        total_count = len(self._knowledge_store)
        avg_confidence = total_confidence / total_count if total_count > 0 else 0.0

        return {
            "total_count": total_count,
            "type_distribution": type_counts,
            "status_distribution": status_counts,
            "average_confidence": avg_confidence,
            "registered_sources": len(self._sources),
            "error_statistics": self._error_source.get_error_statistics(),
        }
