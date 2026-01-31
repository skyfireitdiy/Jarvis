"""混合引擎基类

实现双轨制架构：快路径（规则匹配）+ 慢路径（LLM推理）。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Generic, Optional, TypeVar

from jarvis.jarvis_autonomous.intelligence.llm_reasoning import (
    LLMClient,
    LLMReasoner,
    ReasoningContext,
    ReasoningType,
)
from jarvis.jarvis_autonomous.intelligence.rule_learner import (
    LearnedRule,
    RuleLearner,
)


class InferenceMode(Enum):
    """推理模式"""

    RULE_ONLY = "rule_only"  # 仅使用规则
    LLM_ONLY = "llm_only"  # 仅使用 LLM
    HYBRID = "hybrid"  # 混合模式（默认）
    AUTO = "auto"  # 自动选择


T = TypeVar("T")  # 输出类型


@dataclass
class InferenceResult(Generic[T]):
    """推理结果

    包含推理的输出和元信息。
    """

    success: bool
    output: Optional[T]  # 类型化的输出
    raw_output: str = ""  # 原始输出
    mode_used: InferenceMode = InferenceMode.HYBRID
    rule_used: Optional[str] = None  # 使用的规则 ID
    llm_used: bool = False  # 是否使用了 LLM
    confidence: float = 0.0
    latency_ms: float = 0.0
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "output": self.output,
            "raw_output": self.raw_output,
            "mode_used": self.mode_used.value,
            "rule_used": self.rule_used,
            "llm_used": self.llm_used,
            "confidence": self.confidence,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
        }


class HybridEngine(ABC, Generic[T]):
    """混合引擎基类

    实现双轨制架构：
    1. 快路径：使用预定义规则或学习到的规则快速响应
    2. 慢路径：使用 LLM 进行智能推理
    3. 学习机制：从 LLM 结果中学习新规则

    子类需要实现：
    - _apply_rule: 应用规则生成输出
    - _parse_llm_output: 解析 LLM 输出为类型化结果
    - _build_reasoning_context: 构建 LLM 推理上下文
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        mode: InferenceMode = InferenceMode.HYBRID,
        enable_learning: bool = True,
    ) -> None:
        """初始化混合引擎

        Args:
            llm_client: LLM 客户端
            mode: 推理模式
            enable_learning: 是否启用规则学习
        """
        self.mode = mode
        self.enable_learning = enable_learning

        # 初始化组件
        self.reasoner = LLMReasoner(llm_client=llm_client)
        self.rule_learner = RuleLearner()

        # 预定义规则（子类可以扩展）
        self.predefined_rules: dict[str, dict[str, Any]] = {}

        # 统计信息
        self.stats = {
            "total_inferences": 0,
            "rule_hits": 0,
            "llm_calls": 0,
            "rules_learned": 0,
        }

    def infer(self, input_data: str, **kwargs: Any) -> InferenceResult[T]:
        """执行推理

        Args:
            input_data: 输入数据
            **kwargs: 额外参数

        Returns:
            推理结果
        """
        import time

        start_time = time.time()

        self.stats["total_inferences"] += 1

        try:
            # 根据模式选择推理路径
            if self.mode == InferenceMode.RULE_ONLY:
                result = self._infer_with_rules(input_data, **kwargs)
            elif self.mode == InferenceMode.LLM_ONLY:
                result = self._infer_with_llm(input_data, **kwargs)
            elif self.mode == InferenceMode.AUTO:
                result = self._infer_auto(input_data, **kwargs)
            else:  # HYBRID
                result = self._infer_hybrid(input_data, **kwargs)

            result.latency_ms = (time.time() - start_time) * 1000
            return result

        except Exception as e:
            return InferenceResult(
                success=False,
                output=None,
                error=str(e),
                latency_ms=(time.time() - start_time) * 1000,
            )

    def _infer_hybrid(self, input_data: str, **kwargs: Any) -> InferenceResult[T]:
        """混合推理：先尝试规则，失败则使用 LLM"""
        # 1. 尝试快路径（规则匹配）
        rule_result = self._try_rule_match(input_data, **kwargs)
        if rule_result and rule_result.success:
            self.stats["rule_hits"] += 1
            return rule_result

        # 2. 使用慢路径（LLM 推理）
        llm_result = self._infer_with_llm(input_data, **kwargs)

        # 3. 学习新规则
        if self.enable_learning and llm_result.success:
            self._learn_from_result(input_data, llm_result)

        return llm_result

    def _infer_auto(self, input_data: str, **kwargs: Any) -> InferenceResult[T]:
        """自动选择推理路径"""
        # 检查是否有高置信度的规则匹配
        rule = self.rule_learner.match_rule(input_data)
        if rule and rule.confidence >= 0.8:
            return self._infer_with_rules(input_data, **kwargs)

        # 检查预定义规则
        predefined = self._match_predefined_rule(input_data)
        if predefined:
            return self._infer_with_rules(input_data, **kwargs)

        # 默认使用 LLM
        return self._infer_with_llm(input_data, **kwargs)

    def _infer_with_rules(self, input_data: str, **kwargs: Any) -> InferenceResult[T]:
        """使用规则推理"""
        # 1. 尝试匹配学习到的规则
        learned_rule = self.rule_learner.match_rule(input_data)
        if learned_rule:
            output = self._apply_rule(learned_rule, input_data, **kwargs)
            if output is not None:
                self.rule_learner.record_rule_usage(learned_rule.id, True)
                return InferenceResult(
                    success=True,
                    output=output,
                    mode_used=InferenceMode.RULE_ONLY,
                    rule_used=learned_rule.id,
                    confidence=learned_rule.confidence,
                )

        # 2. 尝试匹配预定义规则
        predefined = self._match_predefined_rule(input_data)
        if predefined:
            output = self._apply_predefined_rule(predefined, input_data, **kwargs)
            if output is not None:
                return InferenceResult(
                    success=True,
                    output=output,
                    mode_used=InferenceMode.RULE_ONLY,
                    rule_used=predefined["name"],
                    confidence=predefined.get("confidence", 0.8),
                )

        # 规则匹配失败
        return InferenceResult(
            success=False,
            output=None,
            mode_used=InferenceMode.RULE_ONLY,
            error="No matching rule found",
        )

    def _infer_with_llm(self, input_data: str, **kwargs: Any) -> InferenceResult[T]:
        """使用 LLM 推理"""
        self.stats["llm_calls"] += 1

        # 构建推理上下文
        context = self._build_reasoning_context(input_data, **kwargs)

        # 执行推理
        reasoning_result = self.reasoner.reason(
            context,
            parse_output=self._parse_llm_output,
        )

        if reasoning_result.success:
            output = self._parse_llm_output(reasoning_result.output)
            return InferenceResult(
                success=True,
                output=output,
                raw_output=reasoning_result.output,
                mode_used=InferenceMode.LLM_ONLY,
                llm_used=True,
                confidence=reasoning_result.confidence,
            )
        else:
            return InferenceResult(
                success=False,
                output=None,
                raw_output=reasoning_result.output,
                mode_used=InferenceMode.LLM_ONLY,
                llm_used=True,
                error=reasoning_result.error,
            )

    def _try_rule_match(
        self, input_data: str, **kwargs: Any
    ) -> Optional[InferenceResult[T]]:
        """尝试规则匹配"""
        result = self._infer_with_rules(input_data, **kwargs)
        if result.success:
            return result
        return None

    def _match_predefined_rule(self, input_data: str) -> Optional[dict[str, Any]]:
        """匹配预定义规则"""
        input_lower = input_data.lower()
        for rule in self.predefined_rules.values():
            keywords = rule.get("keywords", [])
            if any(kw in input_lower for kw in keywords):
                return rule
        return None

    def _learn_from_result(
        self,
        input_data: str,
        result: InferenceResult[T],
    ) -> None:
        """从推理结果中学习规则"""
        if not result.success or not result.raw_output:
            return

        learned = self.rule_learner.learn_from_reasoning(
            reasoning_input=input_data,
            reasoning_output=result.raw_output,
            reasoning_type=self._get_reasoning_type().value,
            success=True,
        )

        if learned:
            self.stats["rules_learned"] += 1

    @abstractmethod
    def _apply_rule(
        self,
        rule: LearnedRule,
        input_data: str,
        **kwargs: Any,
    ) -> Optional[T]:
        """应用学习到的规则

        Args:
            rule: 学习到的规则
            input_data: 输入数据
            **kwargs: 额外参数

        Returns:
            规则应用的输出
        """
        pass

    def _apply_predefined_rule(
        self,
        rule: dict[str, Any],
        input_data: str,
        **kwargs: Any,
    ) -> Optional[T]:
        """应用预定义规则

        默认实现，子类可以覆盖。
        """
        # 默认返回规则中的 output
        return rule.get("output")

    @abstractmethod
    def _parse_llm_output(self, output: str) -> Optional[T]:
        """解析 LLM 输出

        Args:
            output: LLM 原始输出

        Returns:
            解析后的类型化输出
        """
        pass

    @abstractmethod
    def _build_reasoning_context(
        self,
        input_data: str,
        **kwargs: Any,
    ) -> ReasoningContext:
        """构建推理上下文

        Args:
            input_data: 输入数据
            **kwargs: 额外参数

        Returns:
            推理上下文
        """
        pass

    def _get_reasoning_type(self) -> ReasoningType:
        """获取推理类型

        子类可以覆盖以指定不同的推理类型。
        """
        return ReasoningType.ANALYSIS

    def add_predefined_rule(
        self,
        name: str,
        keywords: list[str],
        output: T,
        confidence: float = 0.8,
    ) -> None:
        """添加预定义规则

        Args:
            name: 规则名称
            keywords: 触发关键词
            output: 规则输出
            confidence: 置信度
        """
        self.predefined_rules[name] = {
            "name": name,
            "keywords": keywords,
            "output": output,
            "confidence": confidence,
        }

    def set_mode(self, mode: InferenceMode) -> None:
        """设置推理模式"""
        self.mode = mode

    def get_statistics(self) -> dict[str, Any]:
        """获取统计信息"""
        result: dict[str, Any] = dict(self.stats)
        result["rule_hit_rate"] = (
            self.stats["rule_hits"] / self.stats["total_inferences"] * 100
            if self.stats["total_inferences"] > 0
            else 0
        )
        result["learned_rules"] = self.rule_learner.get_statistics()
        result["reasoning_stats"] = self.reasoner.get_statistics()
        return result

    def get_active_rules(self) -> list[LearnedRule]:
        """获取激活的学习规则"""
        return self.rule_learner.get_active_rules()

    def export_learned_rules(self) -> list[dict[str, Any]]:
        """导出学习到的规则"""
        return self.rule_learner.export_rules()

    def import_learned_rules(self, rules_data: list[dict[str, Any]]) -> int:
        """导入学习到的规则"""
        return self.rule_learner.import_rules(rules_data)
