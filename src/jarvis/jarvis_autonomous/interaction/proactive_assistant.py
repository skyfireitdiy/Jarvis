"""主动交互助手

提供主动交互能力：
- 主动提问澄清
- 主动提供建议
- 主动报告进度
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from ..intelligence.hybrid_engine import HybridEngine
from ..intelligence.llm_reasoning import ReasoningContext, ReasoningType


class ActionType(Enum):
    """主动行为类型"""

    CLARIFY = "clarify"  # 澄清
    SUGGEST = "suggest"  # 建议
    REPORT = "report"  # 报告
    WARN = "warn"  # 警告
    REMIND = "remind"  # 提醒
    CONFIRM = "confirm"  # 确认


class ActionPriority(Enum):
    """行为优先级"""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4


@dataclass
class ProactiveAction:
    """主动行为"""

    action_type: ActionType
    content: str
    priority: ActionPriority = ActionPriority.MEDIUM
    trigger_condition: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    executed: bool = False


@dataclass
class SuggestionResult:
    """建议结果"""

    suggestions: list[str] = field(default_factory=list)
    reasoning: str = ""
    confidence: float = 0.0
    source: str = "rule"
    related_context: dict[str, Any] = field(default_factory=dict)


class ProactiveAssistant(HybridEngine):
    """主动交互助手"""

    def __init__(self, llm_client: Any = None):
        super().__init__(llm_client)
        self._pending_actions: list[ProactiveAction] = []
        self._action_history: list[ProactiveAction] = []
        self._suggestion_triggers = {
            "error": ["错误", "异常", "失败", "bug", "Error"],
            "performance": ["慢", "卡顿", "性能", "优化"],
            "security": ["安全", "漏洞", "风险", "权限"],
            "best_practice": ["最佳实践", "规范", "标准", "建议"],
        }
        self._clarification_triggers = ["不确定", "可能", "也许", "大概", "或者"]

    def analyze_for_proactive_action(
        self, context: dict[str, Any], user_input: str = ""
    ) -> list[ProactiveAction]:
        """分析上下文，决定是否需要主动行为"""
        result = self.infer(input_data=user_input, context=context, mode="analyze")
        actions = []
        if result.success and result.output:
            output: dict[str, Any] = result.output
            if output.get("needs_clarification"):
                actions.append(
                    ProactiveAction(
                        action_type=ActionType.CLARIFY,
                        content=output.get("clarification_question", "请提供更多信息"),
                        priority=ActionPriority.HIGH,
                    )
                )
            if output.get("has_suggestion"):
                actions.append(
                    ProactiveAction(
                        action_type=ActionType.SUGGEST,
                        content=output.get("suggestion", ""),
                        priority=ActionPriority.MEDIUM,
                    )
                )
        self._pending_actions.extend(actions)
        return actions

    def generate_suggestions(self, context: dict[str, Any]) -> SuggestionResult:
        """生成建议"""
        result = self.infer(input_data=str(context), context=context, mode="suggest")
        if result.success and result.output:
            output: dict[str, Any] = result.output
            return SuggestionResult(
                suggestions=output.get("suggestions", []),
                reasoning=output.get("reasoning", ""),
                confidence=output.get("confidence", 0.7),
                source="llm" if result.llm_used else "rule",
            )
        return SuggestionResult()

    def report_progress(self, task_info: dict[str, Any]) -> ProactiveAction:
        """生成进度报告"""
        progress = task_info.get("progress", 0)
        status = task_info.get("status", "进行中")
        content = f"任务进度：{progress}%，状态：{status}"
        if task_info.get("blockers"):
            content += f"\n阻塞问题：{task_info['blockers']}"
        action = ProactiveAction(
            action_type=ActionType.REPORT,
            content=content,
            priority=ActionPriority.LOW,
            context=task_info,
        )
        self._pending_actions.append(action)
        return action

    def should_ask_clarification(self, user_input: str) -> bool:
        """判断是否需要澄清"""
        for trigger in self._clarification_triggers:
            if trigger in user_input:
                return True
        return False

    def get_pending_actions(
        self, priority: Optional[ActionPriority] = None
    ) -> list[ProactiveAction]:
        """获取待执行的主动行为"""
        if priority:
            return [a for a in self._pending_actions if a.priority == priority]
        return self._pending_actions

    def execute_action(self, action: ProactiveAction) -> bool:
        """执行主动行为"""
        action.executed = True
        self._action_history.append(action)
        if action in self._pending_actions:
            self._pending_actions.remove(action)
        return True

    def _apply_rule(
        self, rule: Any, input_data: str, **kwargs: Any
    ) -> Optional[dict[str, Any]]:
        """应用学习到的规则"""
        mode = kwargs.get("mode", "analyze")
        # 检查是否需要澄清
        if mode == "analyze":
            for trigger in self._clarification_triggers:
                if trigger in input_data:
                    return {
                        "needs_clarification": True,
                        "clarification_question": f"您提到'{trigger}'，能否更明确一些？",
                    }
            # 检查是否有建议触发
            for category, triggers in self._suggestion_triggers.items():
                for trigger in triggers:
                    if trigger in input_data:
                        return {
                            "has_suggestion": True,
                            "suggestion": f"检测到{category}相关内容，建议进一步分析",
                        }
        return None

    def _parse_llm_output(self, output: str) -> Optional[dict[str, Any]]:
        """解析LLM输出"""
        import json

        try:
            if "{" in output and "}" in output:
                start = output.index("{")
                end = output.rindex("}") + 1
                parsed: dict[str, Any] = json.loads(output[start:end])
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
        return {"suggestions": [], "reasoning": output}

    def _build_reasoning_context(
        self, input_data: str, **kwargs: Any
    ) -> ReasoningContext:
        """构建推理上下文"""
        context = kwargs.get("context", {})
        mode = kwargs.get("mode", "analyze")
        if mode == "suggest":
            instruction = f"""基于以下上下文生成有价值的建议：

上下文：{context}
输入：{input_data}

请提供具体、可操作的建议。"""
        else:
            instruction = f"""分析以下内容，判断是否需要主动交互：

输入：{input_data}
上下文：{context}

判断是否需要澄清或提供建议。"""
        return ReasoningContext(
            task_type=ReasoningType.ANALYSIS,
            input_data=input_data,
            instruction=instruction,
            output_format='{"needs_clarification": bool, "has_suggestion": bool, "suggestions": []}',
        )
