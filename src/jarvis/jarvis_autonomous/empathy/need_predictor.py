# -*- coding: utf-8 -*-
"""需求预判器 - 预判用户的真实需求

基于双轨制架构（HybridEngine）实现：
- 快路径：基于历史模式的需求匹配
- 慢路径：LLM意图推理
"""

import json
import re
from dataclasses import dataclass
from dataclasses import field
from enum import Enum
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

from ..intelligence.hybrid_engine import HybridEngine
from ..intelligence.hybrid_engine import InferenceMode
from ..intelligence.llm_reasoning import LLMClient
from ..intelligence.llm_reasoning import ReasoningContext
from ..intelligence.llm_reasoning import ReasoningType
from ..intelligence.rule_learner import LearnedRule

from jarvis.jarvis_utils.output import PrettyOutput


class NeedType(Enum):
    """需求类型枚举"""

    EXPLICIT = "explicit"  # 显式需求（用户明确表达）
    IMPLICIT = "implicit"  # 隐式需求（从上下文推断）
    LATENT = "latent"  # 潜在需求（用户未意识到但可能需要）


class NeedCategory(Enum):
    """需求类别枚举"""

    CODE_HELP = "code_help"  # 代码帮助
    DEBUG = "debug"  # 调试问题
    EXPLANATION = "explanation"  # 解释说明
    OPTIMIZATION = "optimization"  # 优化建议
    ARCHITECTURE = "architecture"  # 架构设计
    DOCUMENTATION = "documentation"  # 文档编写
    TESTING = "testing"  # 测试相关
    DEPLOYMENT = "deployment"  # 部署相关
    LEARNING = "learning"  # 学习资源
    OTHER = "other"  # 其他


@dataclass
class PredictedNeed:
    """预测的需求"""

    need_type: NeedType
    category: NeedCategory
    description: str  # 需求描述
    confidence: float  # 置信度 0-1
    priority: int  # 优先级 1-5（1最高）
    evidence: List[str] = field(default_factory=list)  # 推断依据
    suggested_actions: List[str] = field(default_factory=list)  # 建议行动
    source: str = "rule"  # 来源：rule/llm/hybrid

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "need_type": self.need_type.value,
            "category": self.category.value,
            "description": self.description,
            "confidence": self.confidence,
            "priority": self.priority,
            "evidence": self.evidence,
            "suggested_actions": self.suggested_actions,
            "source": self.source,
        }


class NeedPredictor(HybridEngine[PredictedNeed]):
    """需求预判器

    使用双轨制架构预判用户需求：
    1. 快路径：基于关键词和模式匹配
    2. 慢路径：使用LLM进行深度意图分析
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        mode: InferenceMode = InferenceMode.HYBRID,
    ):
        super().__init__(llm_client=llm_client, mode=mode, enable_learning=True)
        self._init_need_patterns()
        self._init_predefined_rules()
        self._history: List[PredictedNeed] = []

    def _init_need_patterns(self) -> None:
        """初始化需求识别模式"""
        self._category_keywords: Dict[NeedCategory, List[str]] = {
            NeedCategory.CODE_HELP: [
                "怎么写",
                "如何实现",
                "代码",
                "函数",
                "方法",
                "how to",
                "implement",
                "code",
                "function",
                "写一个",
                "帮我写",
            ],
            NeedCategory.DEBUG: [
                "报错",
                "错误",
                "bug",
                "不工作",
                "失败",
                "error",
                "exception",
                "crash",
                "fix",
                "修复",
                "为什么不行",
            ],
            NeedCategory.EXPLANATION: [
                "什么意思",
                "解释",
                "为什么",
                "原理",
                "explain",
                "what is",
                "why",
                "how does",
                "理解",
                "含义",
            ],
            NeedCategory.OPTIMIZATION: [
                "优化",
                "性能",
                "更快",
                "效率",
                "optimize",
                "performance",
                "faster",
                "improve",
                "重构",
                "refactor",
            ],
            NeedCategory.ARCHITECTURE: [
                "架构",
                "设计",
                "结构",
                "模式",
                "architecture",
                "design",
                "pattern",
                "structure",
                "系统设计",
            ],
            NeedCategory.DOCUMENTATION: [
                "文档",
                "注释",
                "说明",
                "readme",
                "document",
                "comment",
                "doc",
                "写文档",
            ],
            NeedCategory.TESTING: [
                "测试",
                "单元测试",
                "test",
                "unittest",
                "pytest",
                "coverage",
                "测试用例",
            ],
            NeedCategory.DEPLOYMENT: [
                "部署",
                "发布",
                "上线",
                "deploy",
                "release",
                "docker",
                "kubernetes",
                "ci/cd",
            ],
            NeedCategory.LEARNING: [
                "学习",
                "教程",
                "入门",
                "learn",
                "tutorial",
                "guide",
                "beginner",
                "推荐资源",
            ],
        }

        self._implicit_patterns: List[Dict[str, Any]] = [
            {
                "pattern": r"(又|再次|还是).*(错|问题|bug)",
                "need": "可能需要更系统的调试方法或代码审查",
                "category": NeedCategory.DEBUG,
            },
            {
                "pattern": r"(太慢|很慢|卡|性能差)",
                "need": "可能需要性能优化建议",
                "category": NeedCategory.OPTIMIZATION,
            },
            {
                "pattern": r"(不明白|看不懂|confused)",
                "need": "可能需要更详细的解释或示例",
                "category": NeedCategory.EXPLANATION,
            },
            {
                "pattern": r"(项目|代码).*(乱|混乱|难维护)",
                "need": "可能需要架构重构建议",
                "category": NeedCategory.ARCHITECTURE,
            },
        ]

    def _init_predefined_rules(self) -> None:
        """初始化预定义规则"""
        for category, keywords in self._category_keywords.items():
            self.add_predefined_rule(
                name=f"need_{category.value}",
                keywords=keywords[:5],
                output=PredictedNeed(
                    need_type=NeedType.EXPLICIT,
                    category=category,
                    description=f"用户需要{category.value}相关帮助",
                    confidence=0.8,
                    priority=2,
                    evidence=keywords[:5],
                    source="rule",
                ),
                confidence=0.8,
            )

    def _apply_rule(
        self,
        rule: LearnedRule,
        input_data: str,
        **kwargs: Any,
    ) -> Optional[PredictedNeed]:
        """应用学习到的规则"""
        try:
            output_data = json.loads(rule.action)
            need_type_str = output_data.get("need_type", "explicit")
            category_str = output_data.get("category", "other")

            try:
                need_type = NeedType(need_type_str)
            except ValueError:
                need_type = NeedType.EXPLICIT

            try:
                category = NeedCategory(category_str)
            except ValueError:
                category = NeedCategory.OTHER

            return PredictedNeed(
                need_type=need_type,
                category=category,
                description=output_data.get("description", ""),
                confidence=rule.confidence,
                priority=output_data.get("priority", 3),
                evidence=rule.tags,
                source="rule",
            )
        except (json.JSONDecodeError, KeyError):
            return None

    def _parse_llm_output(self, output: str) -> Optional[PredictedNeed]:
        """解析LLM输出"""
        try:
            json_match = re.search(r"\{[^{}]*\}", output, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())

                need_type_str = parsed.get("need_type", "explicit")
                category_str = parsed.get("category", "other")

                try:
                    need_type = NeedType(need_type_str)
                except ValueError:
                    need_type = NeedType.EXPLICIT

                try:
                    category = NeedCategory(category_str)
                except ValueError:
                    category = NeedCategory.OTHER

                return PredictedNeed(
                    need_type=need_type,
                    category=category,
                    description=parsed.get("description", "未知需求"),
                    confidence=float(parsed.get("confidence", 0.7)),
                    priority=int(parsed.get("priority", 3)),
                    evidence=parsed.get("evidence", []),
                    suggested_actions=parsed.get("suggested_actions", []),
                    source="llm",
                )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            pass

        return None

    def _build_reasoning_context(
        self,
        input_data: str,
        **kwargs: Any,
    ) -> ReasoningContext:
        """构建推理上下文"""
        instruction = """分析以下用户输入，预判其真实需求。

请分析：
1. 需求类型（explicit/implicit/latent）
2. 需求类别（code_help/debug/explanation/optimization/architecture/documentation/testing/deployment/learning/other）
3. 需求描述
4. 置信度（0-1）
5. 优先级（1-5，1最高）
6. 推断依据
7. 建议行动

以JSON格式返回：
{
    "need_type": "...",
    "category": "...",
    "description": "...",
    "confidence": 0.x,
    "priority": x,
    "evidence": ["..."],
    "suggested_actions": ["..."]
}"""

        return ReasoningContext(
            task_type=ReasoningType.ANALYSIS,
            input_data=input_data,
            instruction=instruction,
            output_format="JSON",
        )

    def _get_reasoning_type(self) -> ReasoningType:
        """获取推理类型"""
        return ReasoningType.ANALYSIS

    def predict(self, text: str, history: Optional[List[str]] = None) -> PredictedNeed:
        """预测用户需求"""
        # 先尝试快速规则匹配
        quick_result = self._quick_rule_match(text)
        if quick_result and quick_result.confidence >= 0.7:
            PrettyOutput.auto_print(
                f"🔮 需求预测: {quick_result.category.value} "
                f"(置信度: {quick_result.confidence:.2f}, 模式: 规则快路径)"
            )
            self._history.append(quick_result)
            return quick_result

        # 使用双轨制推理（避免重复打印）
        result = self.infer(text, history=history)

        if result.success and result.output:
            need = result.output
            # 只有在双轨制推理使用了LLM，或者快速匹配结果为None时才打印
            # 避免与前面的规则快路径打印重复
            if result.llm_used or quick_result is None:
                mode_str = "LLM" if result.llm_used else "规则"
                PrettyOutput.auto_print(
                    f"🔮 需求预测: {need.category.value} "
                    f"(置信度: {need.confidence:.2f}, 模式: {mode_str})"
                )
            self._history.append(need)
            return need

        # 回退到快速匹配结果或默认值
        if quick_result:
            PrettyOutput.auto_print(
                f"🔮 需求预测: {quick_result.category.value} "
                f"(置信度: {quick_result.confidence:.2f}, 模式: 规则降级)"
            )
            self._history.append(quick_result)
            return quick_result

        default_result = PredictedNeed(
            need_type=NeedType.EXPLICIT,
            category=NeedCategory.OTHER,
            description="无法确定具体需求",
            confidence=0.3,
            priority=5,
            source="default",
        )
        PrettyOutput.auto_print(
            f"🔮 需求预测: {default_result.category.value} "
            f"(置信度: {default_result.confidence:.2f}, 模式: 默认值)"
        )
        self._history.append(default_result)
        return default_result

    def _quick_rule_match(self, text: str) -> Optional[PredictedNeed]:
        """快速规则匹配"""
        text_lower = text.lower()
        detected_needs: List[Dict[str, Any]] = []

        # 检测显式需求
        for category, keywords in self._category_keywords.items():
            matched_keywords = []
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    matched_keywords.append(keyword)

            if matched_keywords:
                confidence = min(0.5 + len(matched_keywords) * 0.1, 0.9)
                detected_needs.append(
                    {
                        "need_type": NeedType.EXPLICIT,
                        "category": category,
                        "description": f"用户需要{category.value}相关帮助",
                        "confidence": confidence,
                        "evidence": matched_keywords,
                        "priority": 2,
                    }
                )

        # 检测隐式需求
        for pattern_info in self._implicit_patterns:
            if re.search(pattern_info["pattern"], text, re.IGNORECASE):
                detected_needs.append(
                    {
                        "need_type": NeedType.IMPLICIT,
                        "category": pattern_info["category"],
                        "description": pattern_info["need"],
                        "confidence": 0.6,
                        "evidence": [f"匹配模式: {pattern_info['pattern']}"],
                        "priority": 3,
                    }
                )

        if not detected_needs:
            return None

        # 返回置信度最高的需求
        detected_needs.sort(key=lambda x: x["confidence"], reverse=True)
        best = detected_needs[0]

        return PredictedNeed(
            need_type=best["need_type"],
            category=best["category"],
            description=best["description"],
            confidence=best["confidence"],
            priority=best["priority"],
            evidence=best["evidence"],
            source="rule",
        )

    def predict_multiple(
        self, text: str, history: Optional[List[str]] = None, top_k: int = 3
    ) -> List[PredictedNeed]:
        """预测多个可能的需求"""
        text_lower = text.lower()
        all_needs: List[PredictedNeed] = []

        for category, keywords in self._category_keywords.items():
            matched_keywords = []
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    matched_keywords.append(keyword)

            if matched_keywords:
                confidence = min(0.5 + len(matched_keywords) * 0.1, 0.9)
                all_needs.append(
                    PredictedNeed(
                        need_type=NeedType.EXPLICIT,
                        category=category,
                        description=f"用户需要{category.value}相关帮助",
                        confidence=confidence,
                        priority=2,
                        evidence=matched_keywords,
                        source="rule",
                    )
                )

        if not all_needs:
            return [self.predict(text, history)]

        all_needs.sort(key=lambda x: x.confidence, reverse=True)
        return all_needs[:top_k]

    def get_history(self) -> List[PredictedNeed]:
        """获取历史预测记录"""
        return self._history.copy()

    def analyze_patterns(self) -> Dict[str, Any]:
        """分析历史需求模式"""
        if not self._history:
            return {"pattern": "unknown", "dominant_category": None}

        category_counts: Dict[NeedCategory, int] = {}
        type_counts: Dict[NeedType, int] = {}

        for need in self._history:
            category_counts[need.category] = category_counts.get(need.category, 0) + 1
            type_counts[need.need_type] = type_counts.get(need.need_type, 0) + 1

        dominant_category = max(
            category_counts.keys(), key=lambda k: category_counts[k]
        )
        dominant_type = max(type_counts.keys(), key=lambda k: type_counts[k])

        return {
            "total_predictions": len(self._history),
            "dominant_category": dominant_category.value,
            "dominant_type": dominant_type.value,
            "category_distribution": {k.value: v for k, v in category_counts.items()},
            "type_distribution": {k.value: v for k, v in type_counts.items()},
        }
