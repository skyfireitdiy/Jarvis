"""多轮对话管理器

提供增强的上下文理解和多轮对话管理能力：
- 对话上下文跟踪
- 对话状态管理
- 上下文信息提取
- 对话历史分析
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from ..intelligence.hybrid_engine import HybridEngine
from ..intelligence.llm_reasoning import ReasoningContext, ReasoningType


class DialogueState(Enum):
    """对话状态"""

    IDLE = "idle"
    ACTIVE = "active"
    WAITING_INPUT = "waiting_input"
    WAITING_CONFIRMATION = "waiting_confirmation"
    PROCESSING = "processing"
    COMPLETED = "completed"
    SUSPENDED = "suspended"


class ContextType(Enum):
    """上下文类型"""

    TASK = "task"
    CODE = "code"
    FILE = "file"
    ERROR = "error"
    QUESTION = "question"
    DECISION = "decision"
    GENERAL = "general"


@dataclass
class DialogueTurn:
    """对话轮次"""

    turn_id: int
    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    context_type: ContextType = ContextType.GENERAL
    entities: dict[str, Any] = field(default_factory=dict)
    intent: str = ""
    sentiment: str = "neutral"


@dataclass
class DialogueContext:
    """对话上下文"""

    session_id: str
    turns: list[DialogueTurn] = field(default_factory=list)
    state: DialogueState = DialogueState.IDLE
    current_topic: str = ""
    active_entities: dict[str, Any] = field(default_factory=dict)
    pending_questions: list[str] = field(default_factory=list)
    task_stack: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


class DialogueManager(HybridEngine):
    """多轮对话管理器"""

    def __init__(self, llm_client: Any = None):
        super().__init__(llm_client)
        self._contexts: dict[str, DialogueContext] = {}
        self._max_turns = 50
        self._context_window = 10
        self._intent_keywords = {
            "create": ["创建", "新建", "生成", "添加", "写"],
            "modify": ["修改", "更改", "编辑", "更新", "改"],
            "delete": ["删除", "移除", "清除", "去掉"],
            "query": ["查询", "查找", "搜索", "找", "看看"],
            "explain": ["解释", "说明", "什么是", "为什么", "怎么"],
            "fix": ["修复", "解决", "处理", "修正", "bug"],
            "review": ["审查", "检查", "review", "看一下"],
            "help": ["帮助", "帮我", "协助", "支持"],
        }
        self._entity_patterns = {
            "file": [r"[\w/]+\.\w+", r"文件\s*[：:]\s*(\S+)"],
            "function": [r"函数\s*[：:]\s*(\w+)", r"方法\s*[：:]\s*(\w+)"],
            "class": [r"类\s*[：:]\s*(\w+)", r"class\s+(\w+)"],
            "error": [r"错误\s*[：:]\s*(.+)", r"Error:\s*(.+)"],
        }

    def create_session(self, session_id: str) -> DialogueContext:
        """创建新的对话会话"""
        context = DialogueContext(session_id=session_id)
        self._contexts[session_id] = context
        return context

    def get_context(self, session_id: str) -> Optional[DialogueContext]:
        """获取对话上下文"""
        return self._contexts.get(session_id)

    def add_turn(
        self, session_id: str, role: str, content: str, **kwargs: Any
    ) -> DialogueTurn:
        """添加对话轮次"""
        context = self._contexts.get(session_id)
        if not context:
            context = self.create_session(session_id)
        turn_id = len(context.turns) + 1
        turn = DialogueTurn(turn_id=turn_id, role=role, content=content, **kwargs)
        if role == "user":
            turn.intent = self._extract_intent(content)
            turn.entities = self._extract_entities(content)
            turn.context_type = self._determine_context_type(content)
            context.active_entities.update(turn.entities)
        context.turns.append(turn)
        context.updated_at = datetime.now()
        context.state = DialogueState.ACTIVE
        if len(context.turns) > self._max_turns:
            context.turns = context.turns[-self._max_turns :]
        return turn

    def understand_context(self, session_id: str, user_input: str) -> dict[str, Any]:
        """理解当前上下文"""
        # 添加轮次
        self.add_turn(session_id, "user", user_input)
        # 使用infer进行推理
        result = self.infer(input_data=user_input, session_id=session_id)
        if result.success and result.output:
            output: dict[str, Any] = result.output
            return output
        return {"understanding": user_input, "confidence": 0.5, "source": "fallback"}

    def _apply_rule(
        self, rule: Any, input_data: str, **kwargs: Any
    ) -> Optional[dict[str, Any]]:
        """应用学习到的规则"""
        if hasattr(rule, "tags"):
            for tag in rule.tags:
                if tag in input_data:
                    return {
                        "intent": rule.action if hasattr(rule, "action") else "unknown",
                        "confidence": rule.confidence
                        if hasattr(rule, "confidence")
                        else 0.8,
                        "source": "learned_rule",
                        "rule_id": rule.rule_id if hasattr(rule, "rule_id") else None,
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
        return {"understanding": output, "confidence": 0.7, "source": "llm"}

    def _build_reasoning_context(
        self, input_data: str, **kwargs: Any
    ) -> ReasoningContext:
        """构建推理上下文"""
        session_id = kwargs.get("session_id", "")
        context = self._contexts.get(session_id) if session_id else None
        history = ""
        if context:
            recent_turns = context.turns[-self._context_window :]
            history = "\n".join([f"{t.role}: {t.content}" for t in recent_turns])
        instruction = f"""分析以下对话上下文，理解用户意图：

对话历史：
{history}

当前输入：{input_data}"""
        return ReasoningContext(
            task_type=ReasoningType.ANALYSIS,
            input_data=input_data,
            instruction=instruction,
            output_format='{"intent": "用户意图", "entities": {}, "context_type": "上下文类型"}',
        )

    def _extract_intent(self, text: str) -> str:
        """提取用户意图"""
        for intent, keywords in self._intent_keywords.items():
            for keyword in keywords:
                if keyword in text:
                    return intent
        return "general"

    def _extract_entities(self, text: str) -> dict[str, Any]:
        """提取实体"""
        import re

        entities: dict[str, Any] = {}
        for entity_type, patterns in self._entity_patterns.items():
            for pattern in patterns:
                matches = re.findall(pattern, text)
                if matches:
                    entities[entity_type] = matches[0] if len(matches) == 1 else matches
        return entities

    def _determine_context_type(self, text: str) -> ContextType:
        """确定上下文类型"""
        type_keywords = {
            ContextType.CODE: ["代码", "函数", "类", "方法", "变量", "import"],
            ContextType.FILE: ["文件", "目录", "路径", ".py", ".js", ".ts"],
            ContextType.ERROR: ["错误", "异常", "bug", "Error", "Exception"],
            ContextType.TASK: ["任务", "完成", "实现", "开发", "创建"],
            ContextType.QUESTION: ["什么", "为什么", "怎么", "如何", "？"],
            ContextType.DECISION: ["选择", "决定", "方案", "建议", "推荐"],
        }
        for ctx_type, keywords in type_keywords.items():
            for keyword in keywords:
                if keyword in text:
                    return ctx_type
        return ContextType.GENERAL

    def get_relevant_context(self, session_id: str, query: str) -> list[DialogueTurn]:
        """获取与查询相关的上下文"""
        context = self._contexts.get(session_id)
        if not context:
            return []
        query_words = set(query.lower().split())
        relevant_turns = []
        for turn in context.turns[-self._context_window :]:
            turn_words = set(turn.content.lower().split())
            if query_words & turn_words:
                relevant_turns.append(turn)
        return relevant_turns

    def summarize_context(self, session_id: str) -> str:
        """总结对话上下文"""
        context = self._contexts.get(session_id)
        if not context:
            return "无对话上下文"
        summary_parts = [f"状态: {context.state.value}"]
        if context.current_topic:
            summary_parts.append(f"话题: {context.current_topic}")
        if context.active_entities:
            entities_str = ", ".join(
                [f"{k}: {v}" for k, v in context.active_entities.items()]
            )
            summary_parts.append(f"实体: {entities_str}")
        if context.pending_questions:
            summary_parts.append(f"待解决: {len(context.pending_questions)}个问题")
        summary_parts.append(f"轮次: {len(context.turns)}")
        return " | ".join(summary_parts)

    def clear_session(self, session_id: str) -> bool:
        """清除会话"""
        if session_id in self._contexts:
            del self._contexts[session_id]
            return True
        return False
