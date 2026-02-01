"""歧义消解器

提供歧义检测和消解能力：
- 检测用户输入中的歧义
- 生成澄清问题
- 根据上下文消解歧义
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from ..intelligence.hybrid_engine import HybridEngine, InferenceMode
from ..intelligence.llm_reasoning import ReasoningContext, ReasoningType


class AmbiguityType(Enum):
    """歧义类型"""

    LEXICAL = "词汇歧义"  # 词汇歧义
    SYNTACTIC = "句法歧义"  # 句法歧义
    SEMANTIC = "语义歧义"  # 语义歧义
    REFERENTIAL = "指代歧义"  # 指代歧义
    SCOPE = "范围歧义"  # 范围歧义
    PRAGMATIC = "语用歧义"  # 语用歧义
    NONE = "无歧义"  # 无歧义


@dataclass
class ClarificationQuestion:
    """澄清问题"""

    question: str
    options: list[str] = field(default_factory=list)
    ambiguity_type: AmbiguityType = AmbiguityType.NONE
    context_hint: str = ""
    priority: int = 1


@dataclass
class AmbiguityResult:
    """歧义检测结果"""

    has_ambiguity: bool
    ambiguity_type: AmbiguityType = AmbiguityType.NONE
    ambiguous_parts: list[str] = field(default_factory=list)
    possible_interpretations: list[str] = field(default_factory=list)
    clarification_questions: list[ClarificationQuestion] = field(default_factory=list)
    confidence: float = 0.0
    resolved_interpretation: str = ""
    source: str = "rule"


class AmbiguityResolver(HybridEngine):
    """歧义消解器"""

    def __init__(
        self,
        llm_client: Any = None,
        mode: InferenceMode = InferenceMode.HYBRID,
    ):
        super().__init__(llm_client=llm_client, mode=mode, enable_learning=True)
        self._ambiguous_patterns = {
            AmbiguityType.REFERENTIAL: [
                "它",
                "这个",
                "那个",
                "他们",
                "这些",
                "那些",
                "前者",
                "后者",
            ],
            AmbiguityType.SCOPE: ["所有", "每个", "一些", "部分", "大多数"],
            AmbiguityType.LEXICAL: ["处理", "运行", "执行", "操作", "管理"],
        }
        self._clarification_templates = {
            AmbiguityType.REFERENTIAL: "您提到的'{term}'具体指的是什么？",
            AmbiguityType.SCOPE: "'{term}'的范围是什么？是全部还是部分？",
            AmbiguityType.LEXICAL: "'{term}'在这里是什么意思？",
            AmbiguityType.SEMANTIC: "您想要{option1}还是{option2}？",
        }

    def detect_ambiguity(
        self, text: str, context: Optional[dict[str, Any]] = None
    ) -> AmbiguityResult:
        """检测文本中的歧义"""
        # 先尝试基于模式的快速检测
        pattern_result = self._detect_by_pattern(text)
        if pattern_result and pattern_result.has_ambiguity:
            return pattern_result
        # 如果模式检测无结果，使用推理
        result = self.infer(input_data=text, context=context)
        if result.success and result.output:
            output: AmbiguityResult = result.output
            return output
        return AmbiguityResult(has_ambiguity=False, ambiguity_type=AmbiguityType.NONE)

    def _detect_by_pattern(self, text: str) -> Optional[AmbiguityResult]:
        """基于模式检测歧义"""
        for amb_type, patterns in self._ambiguous_patterns.items():
            for pattern in patterns:
                if pattern in text:
                    return AmbiguityResult(
                        has_ambiguity=True,
                        ambiguity_type=AmbiguityType(amb_type),
                        ambiguous_parts=[pattern],
                        confidence=0.7,
                        source="pattern",
                    )
        return None

    def resolve_ambiguity(
        self, text: str, clarification: str, context: Optional[dict[str, Any]] = None
    ) -> str:
        """根据澄清信息消解歧义"""
        result = self.infer(
            input_data=f"{text}\n澄清：{clarification}", context=context, mode="resolve"
        )
        if result.success and result.output:
            resolved: str = result.output.get("resolved_interpretation", text)
            return resolved
        return text

    def generate_clarification(
        self, ambiguity_result: AmbiguityResult
    ) -> list[ClarificationQuestion]:
        """生成澄清问题"""
        questions = []
        for part in ambiguity_result.ambiguous_parts:
            template = self._clarification_templates.get(
                ambiguity_result.ambiguity_type, "请澄清'{term}'的含义"
            )
            question = template.format(
                term=part,
                option1=ambiguity_result.possible_interpretations[0]
                if ambiguity_result.possible_interpretations
                else "选项1",
                option2=ambiguity_result.possible_interpretations[1]
                if len(ambiguity_result.possible_interpretations) > 1
                else "选项2",
            )
            questions.append(
                ClarificationQuestion(
                    question=question,
                    options=ambiguity_result.possible_interpretations,
                    ambiguity_type=ambiguity_result.ambiguity_type,
                )
            )
        return questions

    def _apply_rule(
        self, rule: Any, input_data: str, **kwargs: Any
    ) -> Optional[AmbiguityResult]:
        """应用学习到的规则"""
        if hasattr(rule, "tags"):
            for tag in rule.tags:
                if tag in input_data:
                    return AmbiguityResult(
                        has_ambiguity=True,
                        ambiguity_type=AmbiguityType.LEXICAL,
                        ambiguous_parts=[tag],
                        confidence=rule.confidence
                        if hasattr(rule, "confidence")
                        else 0.8,
                        source="learned_rule",
                    )
        # 基于模式检测
        for amb_type, patterns in self._ambiguous_patterns.items():
            for pattern in patterns:
                if pattern in input_data:
                    return AmbiguityResult(
                        has_ambiguity=True,
                        ambiguity_type=amb_type,
                        ambiguous_parts=[pattern],
                        confidence=0.7,
                        source="pattern",
                    )
        return None

    def _parse_llm_output(self, output: str) -> Optional[AmbiguityResult]:
        """解析LLM输出"""
        import json

        try:
            if "{" in output and "}" in output:
                start = output.index("{")
                end = output.rindex("}") + 1
                data: dict[str, Any] = json.loads(output[start:end])
                return AmbiguityResult(
                    has_ambiguity=data.get("has_ambiguity", False),
                    ambiguity_type=AmbiguityType(data.get("ambiguity_type", "none")),
                    ambiguous_parts=data.get("ambiguous_parts", []),
                    possible_interpretations=data.get("possible_interpretations", []),
                    confidence=data.get("confidence", 0.7),
                    source="llm",
                )
        except (json.JSONDecodeError, ValueError):
            pass
        return AmbiguityResult(has_ambiguity=False, source="llm")

    def _build_reasoning_context(
        self, input_data: str, **kwargs: Any
    ) -> ReasoningContext:
        """构建推理上下文"""
        context = kwargs.get("context", {})
        mode = kwargs.get("mode", "detect")
        if mode == "resolve":
            instruction = f"""根据澄清信息消解以下文本中的歧义：

文本：{input_data}
上下文：{context}

请返回消解后的明确表述。"""
        else:
            instruction = f"""分析以下文本是否存在歧义：

文本：{input_data}
上下文：{context}

请检测歧义类型（词汇歧义/句法歧义/语义歧义/指代歧义/范围歧义/语用歧义/无歧义）。"""
        return ReasoningContext(
            task_type=ReasoningType.ANALYSIS,
            input_data=input_data,
            instruction=instruction,
            output_format='{"has_ambiguity": bool, "ambiguity_type": str, "ambiguous_parts": [], "possible_interpretations": []}',
        )
