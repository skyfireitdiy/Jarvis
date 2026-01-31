# -*- coding: utf-8 -*-
"""情感理解模块 - 阶段4.3

提供情绪识别、需求预判和个性化适应能力。
"""

from .emotion_recognizer import EmotionRecognizer
from .emotion_recognizer import EmotionType
from .emotion_recognizer import EmotionResult
from .need_predictor import NeedPredictor
from .need_predictor import NeedType
from .need_predictor import NeedCategory
from .need_predictor import PredictedNeed
from .personality_adapter import PersonalityAdapter
from .personality_adapter import InteractionStyle
from .personality_adapter import UserProfile
from .personality_adapter import ExpertiseLevel
from .personality_adapter import AdaptedResponse

__all__ = [
    # 情绪识别
    "EmotionRecognizer",
    "EmotionType",
    "EmotionResult",
    # 需求预判
    "NeedPredictor",
    "NeedType",
    "NeedCategory",
    "PredictedNeed",
    # 个性化适应
    "PersonalityAdapter",
    "InteractionStyle",
    "ExpertiseLevel",
    "UserProfile",
    "AdaptedResponse",
]
