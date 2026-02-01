# -*- coding: utf-8 -*-
"""个性化适配器 - 根据用户特征调整交互方式

基于双轨制架构（HybridEngine）实现：
- 快路径：基于用户画像的风格匹配
- 慢路径：LLM个性化生成
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


class InteractionStyle(Enum):
    """交互风格枚举"""

    FORMAL = "formal"  # 正式/专业
    CASUAL = "casual"  # 随意/轻松
    TECHNICAL = "technical"  # 技术/详细
    FRIENDLY = "friendly"  # 友好/亲切
    CONCISE = "concise"  # 简洁/直接
    VERBOSE = "verbose"  # 详细/解释性


class ExpertiseLevel(Enum):
    """专业水平枚举"""

    BEGINNER = "beginner"  # 初学者
    INTERMEDIATE = "intermediate"  # 中级
    ADVANCED = "advanced"  # 高级
    EXPERT = "expert"  # 专家


@dataclass
class UserProfile:
    """用户画像"""

    user_id: str = "default"
    preferred_style: InteractionStyle = InteractionStyle.FRIENDLY
    expertise_level: ExpertiseLevel = ExpertiseLevel.INTERMEDIATE
    preferred_language: str = "zh"  # 偏好语言
    verbosity_preference: float = 0.5  # 详细程度偏好 0-1
    technical_depth: float = 0.5  # 技术深度偏好 0-1
    interaction_count: int = 0  # 交互次数
    topics_of_interest: List[str] = field(default_factory=list)  # 感兴趣的话题
    custom_preferences: Dict[str, Any] = field(default_factory=dict)  # 自定义偏好

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "user_id": self.user_id,
            "preferred_style": self.preferred_style.value,
            "expertise_level": self.expertise_level.value,
            "preferred_language": self.preferred_language,
            "verbosity_preference": self.verbosity_preference,
            "technical_depth": self.technical_depth,
            "interaction_count": self.interaction_count,
            "topics_of_interest": self.topics_of_interest,
            "custom_preferences": self.custom_preferences,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserProfile":
        """从字典创建"""
        style_str = data.get("preferred_style", "friendly")
        level_str = data.get("expertise_level", "intermediate")

        try:
            style = InteractionStyle(style_str)
        except ValueError:
            style = InteractionStyle.FRIENDLY

        try:
            level = ExpertiseLevel(level_str)
        except ValueError:
            level = ExpertiseLevel.INTERMEDIATE

        return cls(
            user_id=data.get("user_id", "default"),
            preferred_style=style,
            expertise_level=level,
            preferred_language=data.get("preferred_language", "zh"),
            verbosity_preference=data.get("verbosity_preference", 0.5),
            technical_depth=data.get("technical_depth", 0.5),
            interaction_count=data.get("interaction_count", 0),
            topics_of_interest=data.get("topics_of_interest", []),
            custom_preferences=data.get("custom_preferences", {}),
        )


@dataclass
class AdaptedResponse:
    """适配后的响应"""

    original_content: str  # 原始内容
    adapted_content: str  # 适配后的内容
    style_applied: InteractionStyle  # 应用的风格
    adaptations_made: List[str] = field(default_factory=list)  # 做出的调整
    confidence: float = 0.8  # 置信度
    source: str = "rule"  # 来源

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "original_content": self.original_content,
            "adapted_content": self.adapted_content,
            "style_applied": self.style_applied.value,
            "adaptations_made": self.adaptations_made,
            "confidence": self.confidence,
            "source": self.source,
        }


class PersonalityAdapter(HybridEngine[AdaptedResponse]):
    """个性化适配器

    使用双轨制架构适配响应风格：
    1. 快路径：基于用户画像的规则适配
    2. 慢路径：使用LLM进行个性化生成
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        mode: InferenceMode = InferenceMode.HYBRID,
    ):
        super().__init__(llm_client=llm_client, mode=mode, enable_learning=True)
        self._user_profiles: Dict[str, UserProfile] = {}
        self._current_user_id: str = "default"
        self._init_style_rules()

    def _init_style_rules(self) -> None:
        """初始化风格规则"""
        # 风格特征映射
        self._style_features: Dict[InteractionStyle, Dict[str, Any]] = {
            InteractionStyle.FORMAL: {
                "greeting": "您好",
                "closing": "如有其他问题，请随时告知。",
                "tone": "professional",
                "use_honorifics": True,
            },
            InteractionStyle.CASUAL: {
                "greeting": "嗨",
                "closing": "有问题随时问~",
                "tone": "relaxed",
                "use_honorifics": False,
            },
            InteractionStyle.TECHNICAL: {
                "greeting": "",
                "closing": "",
                "tone": "precise",
                "include_details": True,
            },
            InteractionStyle.FRIENDLY: {
                "greeting": "你好！",
                "closing": "希望对你有帮助！",
                "tone": "warm",
                "use_emoji": True,
            },
            InteractionStyle.CONCISE: {
                "greeting": "",
                "closing": "",
                "tone": "direct",
                "max_length": 200,
            },
            InteractionStyle.VERBOSE: {
                "greeting": "你好！",
                "closing": "如果还有疑问，欢迎继续提问。",
                "tone": "explanatory",
                "include_examples": True,
            },
        }

        # 专业水平对应的解释深度
        self._expertise_depth: Dict[ExpertiseLevel, Dict[str, Any]] = {
            ExpertiseLevel.BEGINNER: {
                "explain_terms": True,
                "use_analogies": True,
                "step_by_step": True,
            },
            ExpertiseLevel.INTERMEDIATE: {
                "explain_terms": False,
                "use_analogies": False,
                "step_by_step": False,
            },
            ExpertiseLevel.ADVANCED: {
                "explain_terms": False,
                "use_analogies": False,
                "assume_knowledge": True,
            },
            ExpertiseLevel.EXPERT: {
                "explain_terms": False,
                "use_jargon": True,
                "assume_knowledge": True,
            },
        }

    def _apply_rule(
        self,
        rule: LearnedRule,
        input_data: str,
        **kwargs: Any,
    ) -> Optional[AdaptedResponse]:
        """应用学习到的规则"""
        try:
            output_data = json.loads(rule.action)
            style_str = output_data.get("style", "friendly")
            try:
                style = InteractionStyle(style_str)
            except ValueError:
                style = InteractionStyle.FRIENDLY

            return AdaptedResponse(
                original_content=input_data,
                adapted_content=output_data.get("adapted_content", input_data),
                style_applied=style,
                adaptations_made=output_data.get("adaptations", []),
                confidence=rule.confidence,
                source="rule",
            )
        except (json.JSONDecodeError, KeyError):
            return None

    def _parse_llm_output(self, output: str) -> Optional[AdaptedResponse]:
        """解析LLM输出"""
        try:
            json_match = re.search(r"\{[^{}]*\}", output, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                style_str = parsed.get("style", "friendly")
                try:
                    style = InteractionStyle(style_str)
                except ValueError:
                    style = InteractionStyle.FRIENDLY

                return AdaptedResponse(
                    original_content=parsed.get("original", ""),
                    adapted_content=parsed.get("adapted_content", ""),
                    style_applied=style,
                    adaptations_made=parsed.get("adaptations", []),
                    confidence=float(parsed.get("confidence", 0.7)),
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
        profile = kwargs.get("profile", self.get_current_profile())

        instruction = f"""根据用户画像调整以下响应内容的风格。

用户画像：
- 偏好风格：{profile.preferred_style.value}
- 专业水平：{profile.expertise_level.value}
- 详细程度偏好：{profile.verbosity_preference}
- 技术深度偏好：{profile.technical_depth}

请调整响应内容以匹配用户偏好，并以JSON格式返回：
{{
    "original": "原始内容",
    "adapted_content": "调整后的内容",
    "style": "应用的风格",
    "adaptations": ["做出的调整列表"],
    "confidence": 0.x
}}"""

        return ReasoningContext(
            task_type=ReasoningType.GENERATION,
            input_data=input_data,
            instruction=instruction,
            output_format="JSON",
        )

    def _get_reasoning_type(self) -> ReasoningType:
        """获取推理类型"""
        return ReasoningType.GENERATION

    def get_current_profile(self) -> UserProfile:
        """获取当前用户画像"""
        if self._current_user_id not in self._user_profiles:
            self._user_profiles[self._current_user_id] = UserProfile(
                user_id=self._current_user_id
            )
        return self._user_profiles[self._current_user_id]

    def set_current_user(self, user_id: str) -> None:
        """设置当前用户"""
        self._current_user_id = user_id

    def update_profile(self, profile: UserProfile) -> None:
        """更新用户画像"""
        self._user_profiles[profile.user_id] = profile

    def adapt(
        self,
        content: str,
        profile: Optional[UserProfile] = None,
    ) -> AdaptedResponse:
        """适配响应内容

        Args:
            content: 原始响应内容
            profile: 用户画像（可选，默认使用当前用户）

        Returns:
            AdaptedResponse: 适配后的响应
        """
        if profile is None:
            profile = self.get_current_profile()

        # 先尝试快速规则适配
        quick_result = self._quick_adapt(content, profile)
        if quick_result and quick_result.confidence >= 0.7:
            PrettyOutput.auto_print(
                f"🎨 个性适配: 适配风格={quick_result.style_applied.value} "
                f"(置信度: {quick_result.confidence:.2f}, 模式: 规则快路径)"
            )
            return quick_result

        # 使用双轨制推理（避免重复打印）
        result = self.infer(content, profile=profile)

        if result.success and result.output:
            adapted = result.output
            # 只有在双轨制推理使用了LLM，或者快速适配结果为None时才打印
            # 避免与前面的规则快路径打印重复
            if result.llm_used or quick_result is None:
                mode_str = "LLM" if result.llm_used else "规则"
                PrettyOutput.auto_print(
                    f"🎨 个性适配: 适配风格={adapted.style_applied.value} "
                    f"(置信度: {adapted.confidence:.2f}, 模式: {mode_str})"
                )
            return adapted

        # 回退到快速适配结果或默认值
        if quick_result:
            PrettyOutput.auto_print(
                f"🎨 个性适配: 适配风格={quick_result.style_applied.value} "
                f"(置信度: {quick_result.confidence:.2f}, 模式: 规则降级)"
            )
            return quick_result

        default_result = AdaptedResponse(
            original_content=content,
            adapted_content=content,
            style_applied=profile.preferred_style,
            confidence=0.5,
            source="default",
        )
        PrettyOutput.auto_print(
            f"🎨 个性适配: 适配风格={default_result.style_applied.value} "
            f"(置信度: {default_result.confidence:.2f}, 模式: 默认值)"
        )
        return default_result

    def _quick_adapt(self, content: str, profile: UserProfile) -> AdaptedResponse:
        """快速规则适配"""
        adapted = content
        adaptations: List[str] = []
        style = profile.preferred_style
        features = self._style_features.get(style, {})

        # 应用风格特征
        greeting = features.get("greeting", "")
        closing = features.get("closing", "")

        # 添加问候语（如果内容不以问候开头）
        if greeting and not any(
            adapted.startswith(g) for g in ["你好", "您好", "嗨", "Hi", "Hello"]
        ):
            adapted = f"{greeting}\n\n{adapted}"
            adaptations.append(f"添加问候语: {greeting}")

        # 添加结束语（如果内容不以结束语结尾）
        if closing and not any(
            adapted.endswith(c) for c in ["。", "！", "~", "?", "？"]
        ):
            adapted = f"{adapted}\n\n{closing}"
            adaptations.append(f"添加结束语: {closing}")

        # 根据详细程度偏好调整
        if profile.verbosity_preference < 0.3:
            # 简洁模式：截断过长内容
            max_len = features.get("max_length", 500)
            if len(adapted) > max_len:
                adapted = adapted[:max_len] + "..."
                adaptations.append("截断过长内容")

        # 记录交互
        profile.interaction_count += 1

        return AdaptedResponse(
            original_content=content,
            adapted_content=adapted,
            style_applied=style,
            adaptations_made=adaptations,
            confidence=0.8,
            source="rule",
        )

    def learn_from_feedback(
        self,
        original: str,
        adapted: str,
        feedback: str,
        positive: bool,
    ) -> None:
        """从用户反馈中学习

        Args:
            original: 原始内容
            adapted: 适配后的内容
            feedback: 用户反馈
            positive: 是否正面反馈
        """
        profile = self.get_current_profile()

        if positive:
            # 正面反馈：强化当前偏好
            pass
        else:
            # 负面反馈：调整偏好
            # 简单的启发式调整
            if "太长" in feedback or "简洁" in feedback:
                profile.verbosity_preference = max(
                    0, profile.verbosity_preference - 0.1
                )
            elif "太短" in feedback or "详细" in feedback:
                profile.verbosity_preference = min(
                    1, profile.verbosity_preference + 0.1
                )

            if "太技术" in feedback or "简单" in feedback:
                profile.technical_depth = max(0, profile.technical_depth - 0.1)
            elif "更技术" in feedback or "深入" in feedback:
                profile.technical_depth = min(1, profile.technical_depth + 0.1)

    def get_all_profiles(self) -> Dict[str, UserProfile]:
        """获取所有用户画像"""
        return self._user_profiles.copy()

    def export_profiles(self) -> List[Dict[str, Any]]:
        """导出所有用户画像"""
        return [p.to_dict() for p in self._user_profiles.values()]

    def import_profiles(self, profiles_data: List[Dict[str, Any]]) -> int:
        """导入用户画像"""
        count = 0
        for data in profiles_data:
            profile = UserProfile.from_dict(data)
            self._user_profiles[profile.user_id] = profile
            count += 1
        return count
