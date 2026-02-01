"""技能学习器模块。

    负责学习新的工具和技能，支持技能分类和评估。
与methodology模块集成，实现技能的存储和检索。
"""

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from jarvis.jarvis_digital_twin.continuous_learning.types import (
    LearningStatus,
    Skill,
    SkillEvaluatorProtocol,
    SkillType,
)


@dataclass
class SkillRecord:
    """技能记录数据类。

    用于内部存储技能及其状态。
    """

    # 技能对象
    skill: Skill
    # 学习状态
    status: LearningStatus = LearningStatus.LEARNED
    # 内容哈希（用于去重）
    content_hash: str = ""
    # 使用次数
    usage_count: int = 0
    # 成功次数
    success_count: int = 0
    # 最后使用时间
    last_used_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        """初始化后计算内容哈希。"""
        if not self.content_hash:
            self.content_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """计算技能内容的哈希值。"""
        content = f"{self.skill.type.value}:{self.skill.name}:{self.skill.description}"
        return hashlib.md5(content.encode()).hexdigest()


class UsageFrequencyEvaluator:
    """基于使用频率的技能评估器。

    根据技能的使用频率评估熟练度。
    """

    def __init__(self, max_usage_for_mastery: int = 100) -> None:
        """初始化评估器。

        Args:
            max_usage_for_mastery: 达到精通所需的最大使用次数
        """
        self._max_usage = max_usage_for_mastery
        self._usage_counts: Dict[str, int] = {}

    def record_usage(self, skill_id: str) -> None:
        """记录技能使用。

        Args:
            skill_id: 技能ID
        """
        self._usage_counts[skill_id] = self._usage_counts.get(skill_id, 0) + 1

    def evaluate(self, skill: Skill) -> float:
        """评估技能熟练度。

        Args:
            skill: 要评估的技能

        Returns:
            熟练度分数 (0-1)
        """
        usage_count = self._usage_counts.get(skill.id, 0)
        # 使用对数增长曲线，使初期增长快，后期增长慢
        if usage_count == 0:
            return 0.0
        import math

        return min(1.0, math.log(usage_count + 1) / math.log(self._max_usage + 1))


class SuccessRateEvaluator:
    """基于成功率的技能评估器。

    根据技能使用的成功率评估熟练度。
    """

    def __init__(self, min_attempts: int = 5) -> None:
        """初始化评估器。

        Args:
            min_attempts: 最小尝试次数（低于此值时降低置信度）
        """
        self._min_attempts = min_attempts
        self._attempts: Dict[str, int] = {}
        self._successes: Dict[str, int] = {}

    def record_attempt(self, skill_id: str, success: bool) -> None:
        """记录技能使用尝试。

        Args:
            skill_id: 技能ID
            success: 是否成功
        """
        self._attempts[skill_id] = self._attempts.get(skill_id, 0) + 1
        if success:
            self._successes[skill_id] = self._successes.get(skill_id, 0) + 1

    def evaluate(self, skill: Skill) -> float:
        """评估技能熟练度。

        Args:
            skill: 要评估的技能

        Returns:
            熟练度分数 (0-1)
        """
        attempts = self._attempts.get(skill.id, 0)
        successes = self._successes.get(skill.id, 0)

        if attempts == 0:
            return 0.0

        success_rate = successes / attempts

        # 如果尝试次数少于最小值，降低置信度
        if attempts < self._min_attempts:
            confidence_factor = attempts / self._min_attempts
            return success_rate * confidence_factor

        return success_rate


class RecencyEvaluator:
    """基于最近使用时间的技能评估器。

    根据技能最近使用的时间评估熟练度（长时间不用会降低）。
    """

    def __init__(self, decay_days: int = 30) -> None:
        """初始化评估器。

        Args:
            decay_days: 完全衰减所需的天数
        """
        self._decay_days = decay_days
        self._last_used: Dict[str, datetime] = {}

    def record_usage(self, skill_id: str) -> None:
        """记录技能使用时间。

        Args:
            skill_id: 技能ID
        """
        self._last_used[skill_id] = datetime.now()

    def evaluate(self, skill: Skill) -> float:
        """评估技能熟练度。

        Args:
            skill: 要评估的技能

        Returns:
            熟练度分数 (0-1)，基于最近使用时间
        """
        last_used = self._last_used.get(skill.id)
        if last_used is None:
            return 0.0

        days_since_use = (datetime.now() - last_used).days

        if days_since_use >= self._decay_days:
            return 0.0

        # 线性衰减
        return 1.0 - (days_since_use / self._decay_days)


class SkillLearner:
    """技能学习器。

    负责学习新的工具和技能，支持技能分类和评估。
    实现技能的存储、检索和熟练度管理。
    """

    # 工具使用模式
    TOOL_PATTERNS = [
        r"使用\s*(\w+)\s*工具",
        r"调用\s*(\w+)\s*命令",
        r"执行\s*(\w+)\s*操作",
        r"use\s+(\w+)\s+tool",
        r"call\s+(\w+)\s+command",
        r"run\s+(\w+)",
    ]

    # 编程语言模式
    LANGUAGE_PATTERNS = [
        r"```(\w+)\n",
        r"语言[：:]\s*(\w+)",
        r"language[：:]\s*(\w+)",
    ]

    def __init__(
        self,
        methodology_manager: Optional[Any] = None,
        llm_client: Optional[Any] = None,
    ) -> None:
        """初始化技能学习器。

        Args:
            methodology_manager: 方法论管理器实例（可选）
            llm_client: LLM客户端（可选）
        """
        self._llm_client = llm_client
        self._methodology_manager = methodology_manager

        # 内部技能存储
        self._skill_store: Dict[str, SkillRecord] = {}
        # 内容哈希索引（用于去重）
        self._content_hash_index: Dict[str, str] = {}  # hash -> skill_id
        # 名称索引（用于快速查找）
        self._name_index: Dict[str, str] = {}  # name -> skill_id

        # 注册的技能评估器
        self._evaluators: List[SkillEvaluatorProtocol] = []

        # 内置评估器
        self._usage_evaluator = UsageFrequencyEvaluator()
        self._success_evaluator = SuccessRateEvaluator()
        self._recency_evaluator = RecencyEvaluator()

    def register_evaluator(self, evaluator: SkillEvaluatorProtocol) -> None:
        """注册技能评估器。

        Args:
            evaluator: 实现SkillEvaluatorProtocol的评估器
        """
        if evaluator not in self._evaluators:
            self._evaluators.append(evaluator)

    def unregister_evaluator(self, evaluator: SkillEvaluatorProtocol) -> bool:
        """取消注册技能评估器。

        Args:
            evaluator: 要取消的评估器

        Returns:
            是否成功取消
        """
        if evaluator in self._evaluators:
            self._evaluators.remove(evaluator)
            return True
        return False

    def learn_tool(
        self,
        tool_name: str,
        usage_example: str,
        context: str = "",
    ) -> Skill:
        """学习新工具使用。

        Args:
            tool_name: 工具名称
            usage_example: 使用示例
            context: 上下文信息

        Returns:
            学习到的技能对象
        """
        # 检查是否已存在同名技能
        existing_skill = self.get_skill_by_name(tool_name)
        if existing_skill:
            # 更新已有技能的示例
            record = self._skill_store.get(existing_skill.id)
            if record and usage_example not in record.skill.examples:
                record.skill.examples.append(usage_example)
                record.skill.metadata["updated_at"] = datetime.now().isoformat()
            return existing_skill

        # 创建新技能
        skill = Skill(
            id=str(uuid.uuid4()),
            type=SkillType.TOOL_USAGE,
            name=tool_name,
            description=f"工具 {tool_name} 的使用技能",
            proficiency=0.1,  # 初始熟练度
            examples=[usage_example] if usage_example else [],
            created_at=datetime.now(),
            metadata={
                "context": context,
                "source": "learn_tool",
            },
        )

        self._store_skill(skill)
        return skill

    def learn_pattern(
        self,
        pattern_name: str,
        description: str,
        examples: List[str],
    ) -> Skill:
        """学习问题解决模式。

        Args:
            pattern_name: 模式名称
            description: 模式描述
            examples: 使用示例列表

        Returns:
            学习到的技能对象
        """
        # 检查是否已存在同名技能
        existing_skill = self.get_skill_by_name(pattern_name)
        if existing_skill:
            # 更新已有技能的示例
            record = self._skill_store.get(existing_skill.id)
            if record:
                for example in examples:
                    if example not in record.skill.examples:
                        record.skill.examples.append(example)
                record.skill.metadata["updated_at"] = datetime.now().isoformat()
            return existing_skill

        # 创建新技能
        skill = Skill(
            id=str(uuid.uuid4()),
            type=SkillType.METHODOLOGY,
            name=pattern_name,
            description=description,
            proficiency=0.1,
            examples=list(examples),
            created_at=datetime.now(),
            metadata={
                "source": "learn_pattern",
            },
        )

        self._store_skill(skill)

        # 如果有方法论管理器，同步存储
        if self._methodology_manager is not None:
            try:
                if hasattr(self._methodology_manager, "add"):
                    self._methodology_manager.add(
                        problem_type=pattern_name,
                        content=description,
                    )
            except Exception:
                pass

        return skill

    def learn_language(
        self,
        language: str,
        code_sample: str,
    ) -> Skill:
        """学习编程语言特性。

        Args:
            language: 编程语言名称
            code_sample: 代码示例

        Returns:
            学习到的技能对象
        """
        # 标准化语言名称
        language_lower = language.lower()

        # 检查是否已存在同名技能
        existing_skill = self.get_skill_by_name(language_lower)
        if existing_skill:
            # 更新已有技能的示例
            record = self._skill_store.get(existing_skill.id)
            if record and code_sample not in record.skill.examples:
                record.skill.examples.append(code_sample)
                record.skill.metadata["updated_at"] = datetime.now().isoformat()
            return existing_skill

        # 创建新技能
        skill = Skill(
            id=str(uuid.uuid4()),
            type=SkillType.LANGUAGE,
            name=language_lower,
            description=f"编程语言 {language} 的使用技能",
            proficiency=0.1,
            examples=[code_sample] if code_sample else [],
            created_at=datetime.now(),
            metadata={
                "source": "learn_language",
                "original_name": language,
            },
        )

        self._store_skill(skill)
        return skill

    def learn_framework(
        self,
        framework_name: str,
        description: str,
        examples: List[str],
    ) -> Skill:
        """学习框架使用。

        Args:
            framework_name: 框架名称
            description: 框架描述
            examples: 使用示例列表

        Returns:
            学习到的技能对象
        """
        # 检查是否已存在同名技能
        existing_skill = self.get_skill_by_name(framework_name)
        if existing_skill:
            record = self._skill_store.get(existing_skill.id)
            if record:
                for example in examples:
                    if example not in record.skill.examples:
                        record.skill.examples.append(example)
                record.skill.metadata["updated_at"] = datetime.now().isoformat()
            return existing_skill

        skill = Skill(
            id=str(uuid.uuid4()),
            type=SkillType.FRAMEWORK,
            name=framework_name,
            description=description,
            proficiency=0.1,
            examples=list(examples),
            created_at=datetime.now(),
            metadata={
                "source": "learn_framework",
            },
        )

        self._store_skill(skill)
        return skill

    def learn_domain(
        self,
        domain_name: str,
        description: str,
        concepts: List[str],
    ) -> Skill:
        """学习领域知识。

        Args:
            domain_name: 领域名称
            description: 领域描述
            concepts: 相关概念列表

        Returns:
            学习到的技能对象
        """
        existing_skill = self.get_skill_by_name(domain_name)
        if existing_skill:
            record = self._skill_store.get(existing_skill.id)
            if record:
                for concept in concepts:
                    if concept not in record.skill.examples:
                        record.skill.examples.append(concept)
                record.skill.metadata["updated_at"] = datetime.now().isoformat()
            return existing_skill

        skill = Skill(
            id=str(uuid.uuid4()),
            type=SkillType.DOMAIN,
            name=domain_name,
            description=description,
            proficiency=0.1,
            examples=list(concepts),
            created_at=datetime.now(),
            metadata={
                "source": "learn_domain",
            },
        )

        self._store_skill(skill)
        return skill

    def evaluate_skill(
        self,
        skill_id: str,
        context: str = "",
    ) -> float:
        """评估技能掌握程度。

        综合多个评估器的结果计算最终熟练度。

        Args:
            skill_id: 技能ID
            context: 评估上下文

        Returns:
            熟练度分数 (0-1)
        """
        record = self._skill_store.get(skill_id)
        if not record:
            return 0.0

        skill = record.skill
        scores: List[float] = []

        # 使用内置评估器
        scores.append(self._usage_evaluator.evaluate(skill))
        scores.append(self._success_evaluator.evaluate(skill))
        scores.append(self._recency_evaluator.evaluate(skill))

        # 使用注册的自定义评估器
        for evaluator in self._evaluators:
            try:
                score = evaluator.evaluate(skill)
                scores.append(score)
            except Exception:
                pass

        # 计算加权平均（过滤掉0分）
        non_zero_scores = [s for s in scores if s > 0]
        if not non_zero_scores:
            return skill.proficiency  # 返回当前熟练度

        avg_score = sum(non_zero_scores) / len(non_zero_scores)

        # 更新技能熟练度
        record.skill.proficiency = avg_score

        return avg_score

    def get_skill(self, skill_id: str) -> Optional[Skill]:
        """获取技能。

        Args:
            skill_id: 技能ID

        Returns:
            技能对象，如果不存在则返回None
        """
        record = self._skill_store.get(skill_id)
        return record.skill if record else None

    def get_skill_by_name(self, name: str) -> Optional[Skill]:
        """按名称获取技能。

        Args:
            name: 技能名称

        Returns:
            技能对象，如果不存在则返回None
        """
        skill_id = self._name_index.get(name.lower())
        if skill_id:
            return self.get_skill(skill_id)
        return None

    def search_skills(
        self,
        query: str,
        skill_type: Optional[SkillType] = None,
        limit: int = 10,
    ) -> List[Skill]:
        """搜索技能。

        Args:
            query: 搜索查询
            skill_type: 可选的技能类型过滤
            limit: 返回结果数量限制

        Returns:
            匹配的技能列表
        """
        if not query:
            return []

        results: List[Skill] = []
        query_lower = query.lower()

        for record in self._skill_store.values():
            skill = record.skill

            # 状态过滤（排除已废弃的）
            if record.status == LearningStatus.DEPRECATED:
                continue

            # 类型过滤
            if skill_type and skill.type != skill_type:
                continue

            # 名称或描述匹配
            if (
                query_lower in skill.name.lower()
                or query_lower in skill.description.lower()
            ):
                results.append(skill)

            if len(results) >= limit:
                break

        # 按熟练度排序
        results.sort(key=lambda s: s.proficiency, reverse=True)

        return results[:limit]

    def update_proficiency(
        self,
        skill_id: str,
        delta: float,
    ) -> bool:
        """更新技能熟练度。

        Args:
            skill_id: 技能ID
            delta: 熟练度变化量（可正可负）

        Returns:
            是否成功更新
        """
        record = self._skill_store.get(skill_id)
        if not record:
            return False

        # 检查是否是已验证的技能，已验证的技能不能降低熟练度
        if record.status == LearningStatus.VERIFIED and delta < 0:
            return False

        # 更新熟练度，保持在[0, 1]范围内
        new_proficiency = max(0.0, min(1.0, record.skill.proficiency + delta))
        record.skill.proficiency = new_proficiency

        # 如果熟练度过低，标记为废弃
        if new_proficiency < 0.05:
            record.status = LearningStatus.DEPRECATED

        return True

    def record_usage(
        self,
        skill_id: str,
        success: bool = True,
    ) -> bool:
        """记录技能使用。

        Args:
            skill_id: 技能ID
            success: 是否成功使用

        Returns:
            是否成功记录
        """
        record = self._skill_store.get(skill_id)
        if not record:
            return False

        # 更新使用统计
        record.usage_count += 1
        if success:
            record.success_count += 1
        record.last_used_at = datetime.now()

        # 更新内置评估器
        self._usage_evaluator.record_usage(skill_id)
        self._success_evaluator.record_attempt(skill_id, success)
        self._recency_evaluator.record_usage(skill_id)

        # 根据使用情况调整熟练度
        if success:
            self.update_proficiency(skill_id, 0.02)
        else:
            self.update_proficiency(skill_id, -0.01)

        return True

    def verify_skill(self, skill_id: str) -> bool:
        """验证技能。

        将技能状态更新为已验证，已验证的技能不会被覆盖。

        Args:
            skill_id: 技能ID

        Returns:
            是否成功验证
        """
        record = self._skill_store.get(skill_id)
        if not record:
            return False

        record.status = LearningStatus.VERIFIED
        record.skill.proficiency = min(1.0, record.skill.proficiency + 0.2)
        return True

    def deprecate_skill(self, skill_id: str) -> bool:
        """废弃技能。

        Args:
            skill_id: 技能ID

        Returns:
            是否成功废弃
        """
        record = self._skill_store.get(skill_id)
        if not record:
            return False

        # 已验证的技能不能废弃
        if record.status == LearningStatus.VERIFIED:
            return False

        record.status = LearningStatus.DEPRECATED
        return True

    def get_recommendations(
        self,
        context: str,
        limit: int = 5,
    ) -> List[Skill]:
        """根据上下文推荐技能。

        Args:
            context: 当前上下文
            limit: 返回结果数量限制

        Returns:
            推荐的技能列表
        """
        if not context:
            return []

        recommendations: List[tuple[Skill, float]] = []
        context_lower = context.lower()

        for record in self._skill_store.values():
            if record.status == LearningStatus.DEPRECATED:
                continue

            skill = record.skill
            relevance = 0.0

            # 计算相关性分数
            # 1. 名称匹配
            if skill.name.lower() in context_lower:
                relevance += 0.5

            # 2. 描述关键词匹配
            desc_words = skill.description.lower().split()
            for word in desc_words:
                if len(word) > 3 and word in context_lower:
                    relevance += 0.1

            # 3. 示例匹配
            for example in skill.examples:
                if example.lower() in context_lower:
                    relevance += 0.2
                    break

            # 4. 熟练度加成
            relevance += skill.proficiency * 0.2

            if relevance > 0:
                recommendations.append((skill, relevance))

        # 按相关性排序
        recommendations.sort(key=lambda x: x[1], reverse=True)

        return [skill for skill, _ in recommendations[:limit]]

    def get_skills_by_type(
        self,
        skill_type: SkillType,
    ) -> List[Skill]:
        """按类型获取技能。

        Args:
            skill_type: 技能类型

        Returns:
            指定类型的技能列表
        """
        return [
            record.skill
            for record in self._skill_store.values()
            if record.skill.type == skill_type
            and record.status != LearningStatus.DEPRECATED
        ]

    def get_all_skills(
        self,
        include_deprecated: bool = False,
    ) -> List[Skill]:
        """获取所有技能。

        Args:
            include_deprecated: 是否包含已废弃的技能

        Returns:
            技能列表
        """
        results: List[Skill] = []
        for record in self._skill_store.values():
            if not include_deprecated and record.status == LearningStatus.DEPRECATED:
                continue
            results.append(record.skill)
        return results

    def get_skill_count(self) -> int:
        """获取技能数量。

        Returns:
            存储的技能数量（不包括已废弃的）
        """
        return sum(
            1
            for record in self._skill_store.values()
            if record.status != LearningStatus.DEPRECATED
        )

    def clear_all(self) -> None:
        """清除所有技能。"""
        self._skill_store.clear()
        self._content_hash_index.clear()
        self._name_index.clear()

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息。

        Returns:
            统计信息字典
        """
        type_counts: Dict[str, int] = {}
        status_counts: Dict[str, int] = {}
        total_proficiency = 0.0
        total_usage = 0

        for record in self._skill_store.values():
            # 类型统计
            type_name = record.skill.type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1

            # 状态统计
            status_name = record.status.value
            status_counts[status_name] = status_counts.get(status_name, 0) + 1

            # 熟练度累计
            total_proficiency += record.skill.proficiency

            # 使用次数累计
            total_usage += record.usage_count

        total_count = len(self._skill_store)
        avg_proficiency = total_proficiency / total_count if total_count > 0 else 0.0

        return {
            "total_count": total_count,
            "type_distribution": type_counts,
            "status_distribution": status_counts,
            "average_proficiency": avg_proficiency,
            "total_usage": total_usage,
            "registered_evaluators": len(self._evaluators),
        }

    def _store_skill(self, skill: Skill) -> bool:
        """存储技能。

        自动进行去重检查。

        Args:
            skill: 要存储的技能

        Returns:
            是否成功存储
        """
        record = SkillRecord(skill=skill)

        # 检查是否重复
        if record.content_hash in self._content_hash_index:
            return False

        # 存储新技能
        self._skill_store[skill.id] = record
        self._content_hash_index[record.content_hash] = skill.id
        self._name_index[skill.name.lower()] = skill.id

        return True

    def extract_skills_from_context(
        self,
        context: str,
    ) -> List[Skill]:
        """从上下文中自动提取技能。

        Args:
            context: 上下文信息

        Returns:
            提取的技能列表
        """
        if not context:
            return []

        skills: List[Skill] = []

        # 提取工具使用
        for pattern in self.TOOL_PATTERNS:
            matches = re.finditer(pattern, context, re.IGNORECASE)
            for match in matches:
                tool_name = match.group(1)
                skill = self.learn_tool(tool_name, match.group(0), context)
                skills.append(skill)

        # 提取编程语言
        for pattern in self.LANGUAGE_PATTERNS:
            matches = re.finditer(pattern, context, re.IGNORECASE)
            for match in matches:
                language = match.group(1)
                # 提取代码示例（如果有）
                code_sample = ""
                code_match = re.search(
                    rf"```{language}\n(.*?)```", context, re.DOTALL | re.IGNORECASE
                )
                if code_match:
                    code_sample = code_match.group(1)
                skill = self.learn_language(language, code_sample)
                skills.append(skill)

        return skills
