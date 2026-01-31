"""规则学习器

从 LLM 推理结果中提取和学习新规则。
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class RuleType(Enum):
    """规则类型"""

    PATTERN = "pattern"  # 模式匹配规则
    KEYWORD = "keyword"  # 关键词规则
    CONDITION = "condition"  # 条件规则
    TEMPLATE = "template"  # 模板规则
    HEURISTIC = "heuristic"  # 启发式规则


class RuleStatus(Enum):
    """规则状态"""

    CANDIDATE = "candidate"  # 候选规则
    VALIDATED = "validated"  # 已验证
    ACTIVE = "active"  # 激活使用中
    DEPRECATED = "deprecated"  # 已废弃


@dataclass
class LearnedRule:
    """学习到的规则

    从 LLM 推理结果中提取的规则。
    """

    id: str
    name: str
    description: str
    rule_type: RuleType
    condition: str  # 触发条件
    action: str  # 执行动作
    status: RuleStatus = RuleStatus.CANDIDATE
    confidence: float = 0.5  # 置信度
    usage_count: int = 0  # 使用次数
    success_count: int = 0  # 成功次数
    source: str = ""  # 来源（LLM 推理 ID）
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "rule_type": self.rule_type.value,
            "condition": self.condition,
            "action": self.action,
            "status": self.status.value,
            "confidence": self.confidence,
            "usage_count": self.usage_count,
            "success_count": self.success_count,
            "success_rate": self.success_rate,
            "source": self.source,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }

    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.usage_count == 0:
            return 0.0
        return self.success_count / self.usage_count

    def record_usage(self, success: bool) -> None:
        """记录使用情况"""
        self.usage_count += 1
        if success:
            self.success_count += 1
        self.updated_at = datetime.now()
        # 更新置信度
        self._update_confidence()

    def _update_confidence(self) -> None:
        """更新置信度"""
        if self.usage_count < 3:
            return  # 样本太少，不更新
        # 基于成功率调整置信度
        self.confidence = 0.3 + 0.7 * self.success_rate


class RuleLearner:
    """规则学习器

    从 LLM 推理结果中学习新规则，并管理规则生命周期。
    """

    def __init__(
        self,
        min_confidence_for_activation: float = 0.7,
        min_usage_for_validation: int = 3,
    ) -> None:
        """初始化规则学习器

        Args:
            min_confidence_for_activation: 激活规则的最小置信度
            min_usage_for_validation: 验证规则的最小使用次数
        """
        self.rules: dict[str, LearnedRule] = {}
        self.rule_counter = 0
        self.min_confidence_for_activation = min_confidence_for_activation
        self.min_usage_for_validation = min_usage_for_validation

    def _generate_id(self) -> str:
        """生成唯一ID"""
        self.rule_counter += 1
        return f"rule-{self.rule_counter}"

    def learn_from_reasoning(
        self,
        reasoning_input: str,
        reasoning_output: str,
        reasoning_type: str,
        success: bool,
        source_id: str = "",
    ) -> Optional[LearnedRule]:
        """从推理结果中学习规则

        Args:
            reasoning_input: 推理输入
            reasoning_output: 推理输出
            reasoning_type: 推理类型
            success: 推理是否成功
            source_id: 来源推理 ID

        Returns:
            学习到的规则（如果有）
        """
        if not success:
            return None  # 只从成功的推理中学习

        # 尝试提取规则
        rule = self._extract_rule(reasoning_input, reasoning_output, reasoning_type)
        if rule:
            rule.source = source_id
            self.rules[rule.id] = rule
            return rule

        return None

    def _extract_rule(
        self,
        input_data: str,
        output_data: str,
        reasoning_type: str,
    ) -> Optional[LearnedRule]:
        """从输入输出中提取规则"""
        # 尝试解析输出为 JSON
        try:
            output_json = json.loads(output_data)
        except json.JSONDecodeError:
            output_json = {}

        # 根据推理类型提取规则
        if reasoning_type == "classification":
            return self._extract_classification_rule(input_data, output_json)
        elif reasoning_type == "decision":
            return self._extract_decision_rule(input_data, output_json)
        elif reasoning_type == "analysis":
            return self._extract_analysis_rule(input_data, output_json)

        return None

    def _extract_classification_rule(
        self,
        input_data: str,
        output: dict[str, Any],
    ) -> Optional[LearnedRule]:
        """提取分类规则"""
        category = output.get("category")
        if not category:
            return None

        # 提取关键词
        keywords = self._extract_keywords(input_data)
        if not keywords:
            return None

        return LearnedRule(
            id=self._generate_id(),
            name=f"分类规则: {category}",
            description=f"当输入包含关键词 {keywords} 时，分类为 {category}",
            rule_type=RuleType.KEYWORD,
            condition=f"keywords: {keywords}",
            action=f"classify: {category}",
            confidence=output.get("confidence", 0.5),
            tags=["classification", category],
        )

    def _extract_decision_rule(
        self,
        input_data: str,
        output: dict[str, Any],
    ) -> Optional[LearnedRule]:
        """提取决策规则"""
        decision = output.get("decision")
        reasoning = output.get("reasoning", "")
        if not decision:
            return None

        return LearnedRule(
            id=self._generate_id(),
            name=f"决策规则: {decision[:30]}",
            description=f"决策: {decision}\n理由: {reasoning}",
            rule_type=RuleType.HEURISTIC,
            condition=f"context: {input_data[:100]}",
            action=f"decide: {decision}",
            confidence=output.get("confidence", 0.5),
            tags=["decision"],
        )

    def _extract_analysis_rule(
        self,
        input_data: str,
        output: dict[str, Any],
    ) -> Optional[LearnedRule]:
        """提取分析规则"""
        key_points = output.get("key_points", [])
        if not key_points:
            return None

        return LearnedRule(
            id=self._generate_id(),
            name="分析规则",
            description=f"分析要点: {', '.join(key_points[:3])}",
            rule_type=RuleType.TEMPLATE,
            condition=f"input_pattern: {input_data[:50]}",
            action=f"analyze: {key_points}",
            confidence=output.get("confidence", 0.5),
            tags=["analysis"],
        )

    def _extract_keywords(self, text: str) -> list[str]:
        """从文本中提取关键词"""
        # 简单的关键词提取
        words = text.lower().split()
        # 过滤停用词和短词
        stopwords = {"的", "是", "在", "和", "了", "a", "the", "is", "in", "and"}
        keywords = [w for w in words if len(w) > 2 and w not in stopwords]
        return keywords[:5]  # 返回前5个关键词

    def match_rule(self, input_data: str) -> Optional[LearnedRule]:
        """匹配适用的规则

        Args:
            input_data: 输入数据

        Returns:
            匹配的规则（如果有）
        """
        input_lower = input_data.lower()
        best_match: Optional[LearnedRule] = None
        best_score = 0.0

        for rule in self.rules.values():
            if rule.status not in [RuleStatus.VALIDATED, RuleStatus.ACTIVE]:
                continue

            score = self._calculate_match_score(rule, input_lower)
            if score > best_score and score > 0.5:
                best_score = score
                best_match = rule

        return best_match

    def _calculate_match_score(self, rule: LearnedRule, input_data: str) -> float:
        """计算规则匹配分数"""
        score = 0.0

        # 基于规则类型计算匹配分数
        if rule.rule_type == RuleType.KEYWORD:
            # 检查关键词匹配
            condition = rule.condition
            if "keywords:" in condition:
                keywords_str = condition.split("keywords:")[1].strip()
                keywords = keywords_str.strip("[]").replace("'", "").split(", ")
                matched = sum(1 for kw in keywords if kw in input_data)
                if keywords:
                    score = matched / len(keywords)

        elif rule.rule_type == RuleType.PATTERN:
            # 模式匹配
            if rule.condition in input_data:
                score = 0.8

        elif rule.rule_type == RuleType.HEURISTIC:
            # 启发式匹配 - 基于相似度
            score = self._text_similarity(rule.condition, input_data)

        # 考虑规则置信度
        score *= rule.confidence

        return score

    def _text_similarity(self, text1: str, text2: str) -> float:
        """计算文本相似度（简单实现）"""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        if not words1 or not words2:
            return 0.0
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union)

    def record_rule_usage(self, rule_id: str, success: bool) -> None:
        """记录规则使用情况

        Args:
            rule_id: 规则 ID
            success: 是否成功
        """
        rule = self.rules.get(rule_id)
        if rule:
            rule.record_usage(success)
            self._update_rule_status(rule)

    def _update_rule_status(self, rule: LearnedRule) -> None:
        """更新规则状态"""
        # 候选规则 -> 验证规则
        if rule.status == RuleStatus.CANDIDATE:
            if rule.usage_count >= self.min_usage_for_validation:
                if rule.success_rate >= 0.5:
                    rule.status = RuleStatus.VALIDATED
                else:
                    rule.status = RuleStatus.DEPRECATED

        # 验证规则 -> 激活规则
        elif rule.status == RuleStatus.VALIDATED:
            if rule.confidence >= self.min_confidence_for_activation:
                rule.status = RuleStatus.ACTIVE
            elif rule.success_rate < 0.3:
                rule.status = RuleStatus.DEPRECATED

        # 激活规则 -> 废弃
        elif rule.status == RuleStatus.ACTIVE:
            if rule.success_rate < 0.3 and rule.usage_count > 10:
                rule.status = RuleStatus.DEPRECATED

    def get_active_rules(self) -> list[LearnedRule]:
        """获取所有激活的规则"""
        return [
            rule for rule in self.rules.values() if rule.status == RuleStatus.ACTIVE
        ]

    def get_rules_by_type(self, rule_type: RuleType) -> list[LearnedRule]:
        """按类型获取规则"""
        return [rule for rule in self.rules.values() if rule.rule_type == rule_type]

    def get_rules_by_tag(self, tag: str) -> list[LearnedRule]:
        """按标签获取规则"""
        return [rule for rule in self.rules.values() if tag in rule.tags]

    def export_rules(self) -> list[dict[str, Any]]:
        """导出所有规则"""
        return [rule.to_dict() for rule in self.rules.values()]

    def import_rules(self, rules_data: list[dict[str, Any]]) -> int:
        """导入规则

        Args:
            rules_data: 规则数据列表

        Returns:
            导入的规则数量
        """
        imported = 0
        for data in rules_data:
            try:
                rule = LearnedRule(
                    id=data.get("id", self._generate_id()),
                    name=data["name"],
                    description=data.get("description", ""),
                    rule_type=RuleType(data.get("rule_type", "pattern")),
                    condition=data.get("condition", ""),
                    action=data.get("action", ""),
                    status=RuleStatus(data.get("status", "candidate")),
                    confidence=data.get("confidence", 0.5),
                    tags=data.get("tags", []),
                )
                self.rules[rule.id] = rule
                imported += 1
            except (KeyError, ValueError):
                continue
        return imported

    def get_statistics(self) -> dict[str, Any]:
        """获取规则统计"""
        total = len(self.rules)
        by_status: dict[str, int] = {}
        by_type: dict[str, int] = {}

        for rule in self.rules.values():
            status = rule.status.value
            by_status[status] = by_status.get(status, 0) + 1

            rtype = rule.rule_type.value
            by_type[rtype] = by_type.get(rtype, 0) + 1

        active_rules = self.get_active_rules()
        avg_confidence = (
            sum(r.confidence for r in active_rules) / len(active_rules)
            if active_rules
            else 0
        )

        return {
            "total_rules": total,
            "by_status": by_status,
            "by_type": by_type,
            "active_count": len(active_rules),
            "avg_active_confidence": avg_confidence,
        }

    def clear_deprecated(self) -> int:
        """清除废弃的规则

        Returns:
            清除的规则数量
        """
        deprecated_ids = [
            rule_id
            for rule_id, rule in self.rules.items()
            if rule.status == RuleStatus.DEPRECATED
        ]
        for rule_id in deprecated_ids:
            del self.rules[rule_id]
        return len(deprecated_ids)
