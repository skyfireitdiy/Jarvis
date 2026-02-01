"""服务触发器模块。

负责监听上下文变化并判断是否触发服务。
支持节流和防抖机制，与TimingJudge集成进行时机判断。
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

from jarvis.jarvis_digital_twin.prediction import (
    PredictionContext,
    TimingDecision,
    TimingJudge,
)
from jarvis.jarvis_digital_twin.proactive_service.types import (
    ServiceDefinition,
    TriggerContext,
    TriggerEvaluatorProtocol,
)


@dataclass
class TriggerRecord:
    """触发记录数据类。

    记录服务触发的历史信息，用于冷却期计算。
    """

    # 服务ID
    service_id: str
    # 最后触发时间
    last_triggered_at: datetime = field(default_factory=datetime.now)
    # 触发次数
    trigger_count: int = 0


class KeywordTriggerEvaluator:
    """基于关键词匹配的触发评估器。

    检查用户输入是否包含指定的关键词。
    """

    def __init__(self, case_sensitive: bool = False) -> None:
        """初始化关键词评估器。

        Args:
            case_sensitive: 是否区分大小写
        """
        self._case_sensitive = case_sensitive

    def evaluate(
        self,
        context: TriggerContext,
        conditions: List[str],
    ) -> bool:
        """评估触发条件。

        Args:
            context: 触发上下文
            conditions: 关键词列表

        Returns:
            是否满足触发条件（任一关键词匹配即返回True）
        """
        if not conditions:
            return False

        user_input = context.user_input
        if not self._case_sensitive:
            user_input = user_input.lower()
            conditions = [c.lower() for c in conditions]

        return any(keyword in user_input for keyword in conditions)

    def get_confidence(self, context: TriggerContext) -> float:
        """获取触发置信度。

        Args:
            context: 触发上下文

        Returns:
            置信度分数 (0-1)
        """
        # 基于输入长度和内容复杂度计算置信度
        user_input = context.user_input
        if not user_input:
            return 0.0

        # 基础置信度
        confidence = 0.5

        # 输入长度影响置信度
        if len(user_input) > 50:
            confidence += 0.2
        elif len(user_input) > 20:
            confidence += 0.1

        # 有对话历史增加置信度
        if context.conversation_history:
            confidence += 0.1

        # 有用户画像增加置信度
        if context.user_profile:
            confidence += 0.1

        return min(1.0, confidence)


class PatternTriggerEvaluator:
    """基于正则模式的触发评估器。

    使用正则表达式匹配用户输入。
    """

    def __init__(self, flags: int = re.IGNORECASE) -> None:
        """初始化模式评估器。

        Args:
            flags: 正则表达式标志
        """
        self._flags = flags
        self._compiled_patterns: Dict[str, re.Pattern[str]] = {}

    def _get_pattern(self, pattern: str) -> re.Pattern[str]:
        """获取编译后的正则表达式。

        Args:
            pattern: 正则表达式字符串

        Returns:
            编译后的正则表达式对象
        """
        if pattern not in self._compiled_patterns:
            self._compiled_patterns[pattern] = re.compile(pattern, self._flags)
        return self._compiled_patterns[pattern]

    def evaluate(
        self,
        context: TriggerContext,
        conditions: List[str],
    ) -> bool:
        """评估触发条件。

        Args:
            context: 触发上下文
            conditions: 正则表达式列表

        Returns:
            是否满足触发条件（任一模式匹配即返回True）
        """
        if not conditions:
            return False

        user_input = context.user_input

        for pattern in conditions:
            try:
                compiled = self._get_pattern(pattern)
                if compiled.search(user_input):
                    return True
            except re.error:
                # 无效的正则表达式，跳过
                continue

        return False

    def get_confidence(self, context: TriggerContext) -> float:
        """获取触发置信度。

        Args:
            context: 触发上下文

        Returns:
            置信度分数 (0-1)
        """
        # 正则匹配通常更精确，给予较高的基础置信度
        if not context.user_input:
            return 0.0
        return 0.7


class ContextTriggerEvaluator:
    """基于上下文状态的触发评估器。

    检查上下文中的特定状态条件。
    """

    # 支持的上下文条件
    SUPPORTED_CONDITIONS: Set[str] = {
        "has_conversation_history",
        "has_user_profile",
        "has_predictions",
        "long_input",
        "short_input",
        "has_question_mark",
        "has_error_keywords",
        "has_help_keywords",
    }

    def evaluate(
        self,
        context: TriggerContext,
        conditions: List[str],
    ) -> bool:
        """评估触发条件。

        Args:
            context: 触发上下文
            conditions: 上下文条件列表

        Returns:
            是否满足触发条件（所有支持的条件都满足才返回True）
        """
        if not conditions:
            return False

        # 过滤出支持的条件
        valid_conditions = [c for c in conditions if c in self.SUPPORTED_CONDITIONS]

        # 如果没有有效条件，返回False
        if not valid_conditions:
            return False

        # 检查所有有效条件是否都满足
        for condition in valid_conditions:
            if not self._check_condition(context, condition):
                return False

        return True

    def _check_condition(self, context: TriggerContext, condition: str) -> bool:
        """检查单个条件。

        Args:
            context: 触发上下文
            condition: 条件名称

        Returns:
            条件是否满足
        """
        if condition == "has_conversation_history":
            return bool(context.conversation_history)
        elif condition == "has_user_profile":
            return context.user_profile is not None
        elif condition == "has_predictions":
            return context.predictions is not None
        elif condition == "long_input":
            return len(context.user_input) > 100
        elif condition == "short_input":
            return len(context.user_input) <= 20
        elif condition == "has_question_mark":
            return "?" in context.user_input or "？" in context.user_input
        elif condition == "has_error_keywords":
            error_keywords = ["error", "错误", "fail", "失败", "bug", "问题"]
            return any(kw in context.user_input.lower() for kw in error_keywords)
        elif condition == "has_help_keywords":
            help_keywords = ["help", "帮助", "how", "如何", "what", "什么"]
            return any(kw in context.user_input.lower() for kw in help_keywords)

        return False

    def get_confidence(self, context: TriggerContext) -> float:
        """获取触发置信度。

        Args:
            context: 触发上下文

        Returns:
            置信度分数 (0-1)
        """
        confidence = 0.5

        # 根据上下文丰富程度调整置信度
        if context.conversation_history:
            confidence += 0.15
        if context.user_profile:
            confidence += 0.15
        if context.predictions:
            confidence += 0.1

        return min(1.0, confidence)


class ServiceTrigger:
    """服务触发器。

    负责监听上下文变化并判断是否触发服务。
    支持节流和防抖机制，与TimingJudge集成进行时机判断。
    """

    def __init__(self, timing_judge: Optional[TimingJudge] = None) -> None:
        """初始化触发器。

        Args:
            timing_judge: 时机判断器（来自阶段5.2）
        """
        self._timing_judge = timing_judge
        # 已注册的服务定义
        self._registered_services: Dict[str, ServiceDefinition] = {}
        # 服务对应的评估器
        self._evaluators: Dict[str, TriggerEvaluatorProtocol] = {}
        # 触发记录（用于冷却期计算）
        self._trigger_records: Dict[str, TriggerRecord] = {}
        # 待处理的触发
        self._pending_triggers: Dict[str, ServiceDefinition] = {}
        # 默认评估器
        self._default_evaluator = KeywordTriggerEvaluator()

    @property
    def registered_services(self) -> Dict[str, ServiceDefinition]:
        """获取已注册的服务定义。"""
        return self._registered_services.copy()

    @property
    def pending_count(self) -> int:
        """获取待处理触发数量。"""
        return len(self._pending_triggers)

    def register_trigger(
        self,
        service_def: ServiceDefinition,
        evaluator: Optional[TriggerEvaluatorProtocol] = None,
    ) -> None:
        """注册服务触发条件。

        Args:
            service_def: 服务定义
            evaluator: 自定义触发评估器（可选）
        """
        service_id = service_def.service_id
        self._registered_services[service_id] = service_def

        if evaluator:
            self._evaluators[service_id] = evaluator

        # 初始化触发记录
        if service_id not in self._trigger_records:
            self._trigger_records[service_id] = TriggerRecord(service_id=service_id)

    def unregister_trigger(self, service_id: str) -> bool:
        """取消注册触发条件。

        Args:
            service_id: 服务ID

        Returns:
            是否成功取消注册
        """
        if service_id not in self._registered_services:
            return False

        del self._registered_services[service_id]

        # 清理相关数据
        if service_id in self._evaluators:
            del self._evaluators[service_id]
        if service_id in self._trigger_records:
            del self._trigger_records[service_id]
        if service_id in self._pending_triggers:
            del self._pending_triggers[service_id]

        return True

    def check_trigger(self, context: TriggerContext) -> List[ServiceDefinition]:
        """检查是否有服务需要触发。

        Args:
            context: 触发上下文

        Returns:
            需要触发的服务定义列表
        """
        triggered_services: List[ServiceDefinition] = []

        for service_id, service_def in self._registered_services.items():
            # 检查冷却期
            if self.is_in_cooldown(service_id):
                continue

            # 获取评估器
            evaluator = self._evaluators.get(service_id, self._default_evaluator)

            # 评估触发条件
            if evaluator.evaluate(context, service_def.trigger_conditions):
                # 如果有TimingJudge，进行时机判断
                if self._timing_judge:
                    timing_result = self._should_trigger_now(context, service_def)
                    if not timing_result:
                        continue

                triggered_services.append(service_def)
                # 添加到待处理列表
                self._pending_triggers[service_id] = service_def

        return triggered_services

    def _should_trigger_now(
        self,
        context: TriggerContext,
        service_def: ServiceDefinition,
    ) -> bool:
        """使用TimingJudge判断是否应该立即触发。

        Args:
            context: 触发上下文
            service_def: 服务定义

        Returns:
            是否应该立即触发
        """
        if not self._timing_judge:
            return True

        # 将TriggerContext转换为PredictionContext
        prediction_context = PredictionContext(
            current_message=context.user_input,
            conversation_history=context.conversation_history,
            user_profile=context.user_profile or {},
        )

        # 获取时机判断结果
        timing_result = self._timing_judge.should_offer_help(prediction_context)

        # 根据决策判断是否触发
        return timing_result.decision in (
            TimingDecision.OFFER_HELP,
            TimingDecision.ASK_CONFIRMATION,
        )

    def get_pending_triggers(self) -> List[ServiceDefinition]:
        """获取待处理的触发。

        Returns:
            待处理的服务定义列表
        """
        return list(self._pending_triggers.values())

    def clear_pending(self, service_id: str) -> None:
        """清除指定服务的待处理状态。

        Args:
            service_id: 服务ID
        """
        if service_id in self._pending_triggers:
            del self._pending_triggers[service_id]

    def clear_all_pending(self) -> None:
        """清除所有待处理状态。"""
        self._pending_triggers.clear()

    def is_in_cooldown(self, service_id: str) -> bool:
        """检查服务是否在冷却期。

        Args:
            service_id: 服务ID

        Returns:
            是否在冷却期
        """
        if service_id not in self._trigger_records:
            return False

        if service_id not in self._registered_services:
            return False

        record = self._trigger_records[service_id]
        service_def = self._registered_services[service_id]

        # 如果从未触发过，不在冷却期
        if record.trigger_count == 0:
            return False

        # 计算冷却期结束时间
        cooldown_end = record.last_triggered_at + timedelta(
            seconds=service_def.cooldown_seconds
        )

        return datetime.now() < cooldown_end

    def get_cooldown_remaining(self, service_id: str) -> float:
        """获取剩余冷却时间（秒）。

        Args:
            service_id: 服务ID

        Returns:
            剩余冷却时间（秒），如果不在冷却期返回0
        """
        if not self.is_in_cooldown(service_id):
            return 0.0

        record = self._trigger_records[service_id]
        service_def = self._registered_services[service_id]

        cooldown_end = record.last_triggered_at + timedelta(
            seconds=service_def.cooldown_seconds
        )

        remaining = (cooldown_end - datetime.now()).total_seconds()
        return max(0.0, remaining)

    def record_trigger(self, service_id: str) -> None:
        """记录触发时间（用于冷却期计算）。

        Args:
            service_id: 服务ID
        """
        if service_id not in self._trigger_records:
            self._trigger_records[service_id] = TriggerRecord(service_id=service_id)

        record = self._trigger_records[service_id]
        record.last_triggered_at = datetime.now()
        record.trigger_count += 1

    def get_trigger_count(self, service_id: str) -> int:
        """获取服务的触发次数。

        Args:
            service_id: 服务ID

        Returns:
            触发次数
        """
        if service_id not in self._trigger_records:
            return 0
        return self._trigger_records[service_id].trigger_count

    def reset_trigger_record(self, service_id: str) -> None:
        """重置服务的触发记录。

        Args:
            service_id: 服务ID
        """
        if service_id in self._trigger_records:
            self._trigger_records[service_id] = TriggerRecord(service_id=service_id)
