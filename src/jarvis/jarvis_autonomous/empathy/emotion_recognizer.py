# -*- coding: utf-8 -*-
"""情绪识别器 - 识别用户的情绪状态

基于双轨制架构（HybridEngine）实现：
- 快路径：基于关键词和模式的情绪识别
- 慢路径：LLM深度情感分析
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


class EmotionType(Enum):
    """情绪类型枚举"""

    POSITIVE = "积极"  # 积极/满意
    NEGATIVE = "消极"  # 消极/不满
    NEUTRAL = "中性"  # 中性
    FRUSTRATED = "沮丧"  # 沮丧/受挫
    CONFUSED = "困惑"  # 困惑
    EXCITED = "兴奋"  # 兴奋/期待
    ANXIOUS = "焦虑"  # 焦虑/担忧
    GRATEFUL = "感激"  # 感激
    IMPATIENT = "不耐烦"  # 不耐烦


@dataclass
class EmotionResult:
    """情绪识别结果"""

    emotion_type: EmotionType
    confidence: float  # 置信度 0-1
    intensity: float  # 强度 0-1
    indicators: List[str] = field(default_factory=list)  # 识别依据
    context_factors: Dict[str, Any] = field(default_factory=dict)  # 上下文因素
    source: str = "rule"  # 来源：rule/llm/hybrid

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "emotion_type": self.emotion_type.value,
            "confidence": self.confidence,
            "intensity": self.intensity,
            "indicators": self.indicators,
            "context_factors": self.context_factors,
            "source": self.source,
        }


class EmotionRecognizer(HybridEngine[EmotionResult]):
    """情绪识别器

    使用双轨制架构识别用户情绪：
    1. 快路径：基于预定义的情绪关键词和模式
    2. 慢路径：使用LLM进行深度情感分析
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        mode: InferenceMode = InferenceMode.HYBRID,
    ):
        super().__init__(llm_client=llm_client, mode=mode, enable_learning=True)
        self._init_emotion_patterns()
        self._init_predefined_rules()

    def _init_emotion_patterns(self) -> None:
        """初始化情绪识别模式"""
        # 情绪关键词映射
        self._emotion_keywords: Dict[EmotionType, List[str]] = {
            EmotionType.POSITIVE: [
                "谢谢",
                "感谢",
                "太好了",
                "很棒",
                "完美",
                "excellent",
                "great",
                "perfect",
                "awesome",
                "wonderful",
                "nice",
                "good job",
                "well done",
                "满意",
                "开心",
                "高兴",
            ],
            EmotionType.NEGATIVE: [
                "不行",
                "不好",
                "糟糕",
                "失败",
                "错误",
                "bad",
                "wrong",
                "terrible",
                "awful",
                "horrible",
                "失望",
                "不满",
                "讨厌",
            ],
            EmotionType.FRUSTRATED: [
                "为什么不行",
                "又出错了",
                "还是不对",
                "搞不定",
                "放弃",
                "frustrated",
                "stuck",
                "give up",
                "无语",
                "崩溃",
                "烦死了",
            ],
            EmotionType.CONFUSED: [
                "不明白",
                "不理解",
                "什么意思",
                "怎么回事",
                "confused",
                "don't understand",
                "what do you mean",
                "unclear",
                "迷惑",
                "搞不懂",
                "看不懂",
            ],
            EmotionType.EXCITED: [
                "太棒了",
                "期待",
                "迫不及待",
                "excited",
                "can't wait",
                "amazing",
                "fantastic",
                "兴奋",
                "激动",
                "终于",
            ],
            EmotionType.ANXIOUS: [
                "担心",
                "紧急",
                "着急",
                "赶紧",
                "worried",
                "urgent",
                "asap",
                "hurry",
                "deadline",
                "焦虑",
                "来不及",
            ],
            EmotionType.GRATEFUL: [
                "非常感谢",
                "太感谢了",
                "多谢",
                "thank you so much",
                "really appreciate",
                "grateful",
                "帮大忙了",
                "救命",
            ],
            EmotionType.IMPATIENT: [
                "快点",
                "怎么这么慢",
                "等不及了",
                "hurry up",
                "too slow",
                "come on",
                "催",
                "急",
                "马上",
            ],
        }

        # 情绪强度修饰词
        self._intensity_modifiers: Dict[str, float] = {
            "非常": 1.5,
            "太": 1.4,
            "特别": 1.3,
            "很": 1.2,
            "有点": 0.7,
            "稍微": 0.6,
            "really": 1.4,
            "very": 1.3,
            "so": 1.3,
            "quite": 1.1,
            "a bit": 0.7,
            "slightly": 0.6,
        }

        # 否定词
        self._negation_words = [
            "不",
            "没",
            "别",
            "无",
            "not",
            "no",
            "don't",
            "doesn't",
            "didn't",
            "won't",
            "never",
        ]

    def _init_predefined_rules(self) -> None:
        """初始化预定义规则"""
        # 添加一些高置信度的预定义规则
        for emotion_type, keywords in self._emotion_keywords.items():
            self.add_predefined_rule(
                name=f"emotion_{emotion_type.value}",
                keywords=keywords[:5],  # 使用前5个关键词
                output=EmotionResult(
                    emotion_type=emotion_type,
                    confidence=0.8,
                    intensity=0.5,
                    indicators=keywords[:5],
                    source="rule",
                ),
                confidence=0.8,
            )

    def _apply_rule(
        self,
        rule: LearnedRule,
        input_data: str,
        **kwargs: Any,
    ) -> Optional[EmotionResult]:
        """应用学习到的规则"""
        # 从规则的action中提取情绪类型
        try:
            output_data = json.loads(rule.action)
            emotion_str = output_data.get("emotion_type", "中性")
            try:
                emotion_type = EmotionType(emotion_str)
            except ValueError:
                emotion_type = EmotionType.NEUTRAL  # 默认为中性

            return EmotionResult(
                emotion_type=emotion_type,
                confidence=rule.confidence,
                intensity=output_data.get("intensity", 0.5),
                indicators=rule.tags,
                source="rule",
            )
        except (json.JSONDecodeError, KeyError):
            return None

    def _parse_llm_output(self, output: str) -> Optional[EmotionResult]:
        """解析LLM输出"""
        try:
            # 尝试从响应中提取JSON
            json_match = re.search(r"\{[^{}]*\}", output, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                emotion_str = parsed.get("emotion_type", "中性")
                try:
                    emotion_type = EmotionType(emotion_str)
                except ValueError:
                    emotion_type = EmotionType.NEUTRAL

                return EmotionResult(
                    emotion_type=emotion_type,
                    confidence=float(parsed.get("confidence", 0.7)),
                    intensity=float(parsed.get("intensity", 0.5)),
                    indicators=parsed.get("indicators", []),
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
        instruction = """分析以下文本的情绪状态。

请识别：
1. 主要情绪类型（积极/消极/中性/沮丧/困惑/兴奋/焦虑/感激/不耐烦）
2. 置信度（0-1）
3. 情绪强度（0-1）
4. 识别依据

以JSON格式返回：
{
    "emotion_type": "...",
    "confidence": 0.x,
    "intensity": 0.x,
    "indicators": ["..."]
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

    def recognize(
        self, text: str, history: Optional[List[str]] = None
    ) -> EmotionResult:
        """识别文本中的情绪

        Args:
            text: 要分析的文本
            history: 历史对话记录（可选）

        Returns:
            EmotionResult: 情绪识别结果
        """
        # 先尝试快速规则匹配
        quick_result = self._quick_rule_match(text)
        if quick_result and quick_result.confidence >= 0.7:
            PrettyOutput.auto_print(
                f"🎭 情绪识别: {quick_result.emotion_type.value} "
                f"(置信度: {quick_result.confidence:.2f}, 模式: 规则快路径)"
            )
            return quick_result

        # 使用双轨制推理（避免重复打印）
        result = self.infer(text, history=history)

        if result.success and result.output:
            emotion_result = result.output
            # 只有在双轨制推理使用了LLM，或者快速匹配结果为None时才打印
            # 避免与前面的规则快路径打印重复
            if result.llm_used or quick_result is None:
                mode_str = "LLM" if result.llm_used else "规则"
                PrettyOutput.auto_print(
                    f"🎭 情绪识别: {emotion_result.emotion_type.value} "
                    f"(置信度: {emotion_result.confidence:.2f}, 模式: {mode_str})"
                )
            return emotion_result

        # 回退到快速匹配结果或默认值
        if quick_result:
            PrettyOutput.auto_print(
                f"🎭 情绪识别: {quick_result.emotion_type.value} "
                f"(置信度: {quick_result.confidence:.2f}, 模式: 规则降级)"
            )
            return quick_result

        default_result = EmotionResult(
            emotion_type=EmotionType.NEUTRAL,
            confidence=0.5,
            intensity=0.5,
            source="default",
        )
        PrettyOutput.auto_print(
            f"🎭 情绪识别: {default_result.emotion_type.value} "
            f"(置信度: {default_result.confidence:.2f}, 模式: 默认值)"
        )
        return default_result

    def _quick_rule_match(self, text: str) -> Optional[EmotionResult]:
        """快速规则匹配（不使用LLM）"""
        text_lower = text.lower()
        detected_emotions: List[tuple] = []

        for emotion_type, keywords in self._emotion_keywords.items():
            matched_keywords = []
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    matched_keywords.append(keyword)

            if matched_keywords:
                confidence = min(0.5 + len(matched_keywords) * 0.15, 0.95)
                detected_emotions.append((emotion_type, confidence, matched_keywords))

        if not detected_emotions:
            return None

        # 选择置信度最高的情绪
        detected_emotions.sort(key=lambda x: x[1], reverse=True)
        best_emotion, confidence, indicators = detected_emotions[0]

        # 检查否定词
        has_negation = any(neg in text_lower for neg in self._negation_words)
        if has_negation and best_emotion in [EmotionType.POSITIVE, EmotionType.EXCITED]:
            best_emotion = EmotionType.NEGATIVE
            confidence *= 0.8

        # 计算强度
        intensity = 0.5
        for modifier, factor in self._intensity_modifiers.items():
            if modifier.lower() in text_lower:
                intensity = min(intensity * factor, 1.0)
                break

        return EmotionResult(
            emotion_type=best_emotion,
            confidence=confidence,
            intensity=intensity,
            indicators=indicators,
            source="rule",
        )

    def recognize_batch(
        self, texts: List[str], history: Optional[List[str]] = None
    ) -> List[EmotionResult]:
        """批量识别情绪"""
        return [self.recognize(text, history) for text in texts]

    def get_emotion_trend(self, results: List[EmotionResult]) -> Dict[str, Any]:
        """分析情绪趋势"""
        if not results:
            return {"trend": "unknown", "dominant_emotion": None}

        # 统计情绪分布
        emotion_counts: Dict[EmotionType, int] = {}
        total_intensity = 0.0

        for result in results:
            emotion_counts[result.emotion_type] = (
                emotion_counts.get(result.emotion_type, 0) + 1
            )
            total_intensity += result.intensity

        # 找出主导情绪
        dominant_emotion = max(emotion_counts.keys(), key=lambda k: emotion_counts[k])
        avg_intensity = total_intensity / len(results)

        # 分析趋势
        mid = len(results) // 2
        if mid > 0:
            positive_emotions = {
                EmotionType.POSITIVE,
                EmotionType.EXCITED,
                EmotionType.GRATEFUL,
            }
            first_half_positive = sum(
                1 for r in results[:mid] if r.emotion_type in positive_emotions
            )
            second_half_positive = sum(
                1 for r in results[mid:] if r.emotion_type in positive_emotions
            )

            if second_half_positive > first_half_positive:
                trend = "improving"
            elif second_half_positive < first_half_positive:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"

        return {
            "trend": trend,
            "dominant_emotion": dominant_emotion.value,
            "emotion_distribution": {k.value: v for k, v in emotion_counts.items()},
            "average_intensity": avg_intensity,
        }
