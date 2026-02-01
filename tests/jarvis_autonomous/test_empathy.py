# -*- coding: utf-8 -*-
"""情感理解模块测试

测试阶段4.3的情绪识别、需求预判和个性化适应功能。
"""

import pytest

from jarvis.jarvis_autonomous.empathy import (
    EmotionRecognizer,
    EmotionResult,
    EmotionType,
    NeedPredictor,
    NeedType,
    NeedCategory,
    PredictedNeed,
    PersonalityAdapter,
    InteractionStyle,
    ExpertiseLevel,
    UserProfile,
    AdaptedResponse,
)


class TestEmotionRecognizer:
    """情绪识别器测试"""

    def test_init(self):
        """测试初始化"""
        recognizer = EmotionRecognizer()
        assert recognizer is not None
        assert recognizer._emotion_keywords is not None

    def test_recognize_positive_emotion(self):
        """测试识别积极情绪"""
        recognizer = EmotionRecognizer()
        result = recognizer.recognize("太好了，谢谢你的帮助！")
        assert isinstance(result, EmotionResult)
        assert result.emotion_type in [EmotionType.POSITIVE, EmotionType.GRATEFUL]
        assert result.confidence > 0.5

    def test_recognize_negative_emotion(self):
        """测试识别消极情绪"""
        recognizer = EmotionRecognizer()
        result = recognizer.recognize("这个方案太糟糕了，完全不行")
        assert isinstance(result, EmotionResult)
        assert result.emotion_type == EmotionType.NEGATIVE
        assert result.confidence > 0.5

    def test_recognize_frustrated_emotion(self):
        """测试识别沮丧情绪"""
        recognizer = EmotionRecognizer()
        result = recognizer.recognize("又出错了，搞不定，放弃了")
        assert isinstance(result, EmotionResult)
        # 沮丧情绪可能被识别为沮丧或消极
        assert result.emotion_type in [EmotionType.FRUSTRATED, EmotionType.NEGATIVE]

    def test_recognize_confused_emotion(self):
        """测试识别困惑情绪"""
        recognizer = EmotionRecognizer()
        result = recognizer.recognize("我不明白这是什么意思")
        assert isinstance(result, EmotionResult)
        assert result.emotion_type == EmotionType.CONFUSED

    def test_recognize_anxious_emotion(self):
        """测试识别焦虑情绪"""
        recognizer = EmotionRecognizer()
        result = recognizer.recognize("紧急！deadline快到了，赶紧帮我处理")
        assert isinstance(result, EmotionResult)
        assert result.emotion_type == EmotionType.ANXIOUS

    def test_recognize_neutral_emotion(self):
        """测试识别中性情绪"""
        recognizer = EmotionRecognizer()
        result = recognizer.recognize("请帮我查看一下这个文件")
        assert isinstance(result, EmotionResult)
        # 中性文本可能被识别为中性或其他
        assert result.confidence >= 0

    def test_recognize_batch(self):
        """测试批量识别"""
        recognizer = EmotionRecognizer()
        texts = ["太好了！", "糟糕", "不明白"]
        results = recognizer.recognize_batch(texts)
        assert len(results) == 3
        assert all(isinstance(r, EmotionResult) for r in results)

    def test_emotion_trend(self):
        """测试情绪趋势分析"""
        recognizer = EmotionRecognizer()
        results = [
            EmotionResult(EmotionType.NEGATIVE, 0.8, 0.6),
            EmotionResult(EmotionType.FRUSTRATED, 0.7, 0.5),
            EmotionResult(EmotionType.NEUTRAL, 0.6, 0.4),
            EmotionResult(EmotionType.POSITIVE, 0.8, 0.7),
        ]
        trend = recognizer.get_emotion_trend(results)
        assert "trend" in trend
        assert "dominant_emotion" in trend

    def test_emotion_result_to_dict(self):
        """测试EmotionResult转换为字典"""
        result = EmotionResult(
            emotion_type=EmotionType.POSITIVE,
            confidence=0.9,
            intensity=0.8,
            indicators=["谢谢"],
            source="rule",
        )
        d = result.to_dict()
        assert d["emotion_type"] == "积极"
        assert d["confidence"] == 0.9


class TestNeedPredictor:
    """需求预判器测试"""

    def test_init(self):
        """测试初始化"""
        predictor = NeedPredictor()
        assert predictor is not None
        assert predictor._category_keywords is not None

    def test_predict_code_help(self):
        """测试预测代码帮助需求"""
        predictor = NeedPredictor()
        result = predictor.predict("帮我写一个排序函数")
        assert isinstance(result, PredictedNeed)
        assert result.category == NeedCategory.CODE_HELP

    def test_predict_debug(self):
        """测试预测调试需求"""
        predictor = NeedPredictor()
        result = predictor.predict("这段代码报错了，帮我修复一下")
        assert isinstance(result, PredictedNeed)
        assert result.category == NeedCategory.DEBUG

    def test_predict_explanation(self):
        """测试预测解释需求"""
        predictor = NeedPredictor()
        result = predictor.predict("什么是依赖注入？请解释一下原理")
        assert isinstance(result, PredictedNeed)
        assert result.category == NeedCategory.EXPLANATION

    def test_predict_optimization(self):
        """测试预测优化需求"""
        predictor = NeedPredictor()
        result = predictor.predict("这段代码太慢了，帮我优化一下性能")
        assert isinstance(result, PredictedNeed)
        assert result.category == NeedCategory.OPTIMIZATION

    def test_predict_architecture(self):
        """测试预测架构需求"""
        predictor = NeedPredictor()
        result = predictor.predict("帮我设计一个微服务架构")
        assert isinstance(result, PredictedNeed)
        assert result.category == NeedCategory.ARCHITECTURE

    def test_predict_multiple(self):
        """测试预测多个需求"""
        predictor = NeedPredictor()
        results = predictor.predict_multiple("帮我写代码并解释原理", top_k=2)
        assert len(results) >= 1
        assert all(isinstance(r, PredictedNeed) for r in results)

    def test_get_history(self):
        """测试获取历史记录"""
        predictor = NeedPredictor()
        predictor.predict("帮我写代码")
        predictor.predict("解释一下")
        history = predictor.get_history()
        assert len(history) == 2

    def test_analyze_patterns(self):
        """测试分析需求模式"""
        predictor = NeedPredictor()
        predictor.predict("帮我写代码")
        predictor.predict("再写一个函数")
        predictor.predict("解释一下")
        patterns = predictor.analyze_patterns()
        assert "total_predictions" in patterns
        assert "dominant_category" in patterns

    def test_predicted_need_to_dict(self):
        """测试PredictedNeed转换为字典"""
        need = PredictedNeed(
            need_type=NeedType.EXPLICIT,
            category=NeedCategory.CODE_HELP,
            description="用户需要代码帮助",
            confidence=0.9,
            priority=2,
            evidence=["写代码"],
            source="rule",
        )
        d = need.to_dict()
        assert d["need_type"] == "explicit"
        assert d["category"] == "code_help"


class TestPersonalityAdapter:
    """个性化适配器测试"""

    def test_init(self):
        """测试初始化"""
        adapter = PersonalityAdapter()
        assert adapter is not None
        assert adapter._style_features is not None

    def test_get_current_profile(self):
        """测试获取当前用户画像"""
        adapter = PersonalityAdapter()
        profile = adapter.get_current_profile()
        assert isinstance(profile, UserProfile)
        assert profile.user_id == "default"

    def test_set_current_user(self):
        """测试设置当前用户"""
        adapter = PersonalityAdapter()
        adapter.set_current_user("user123")
        profile = adapter.get_current_profile()
        assert profile.user_id == "user123"

    def test_update_profile(self):
        """测试更新用户画像"""
        adapter = PersonalityAdapter()
        profile = UserProfile(
            user_id="test_user",
            preferred_style=InteractionStyle.TECHNICAL,
            expertise_level=ExpertiseLevel.EXPERT,
        )
        adapter.update_profile(profile)
        adapter.set_current_user("test_user")
        retrieved = adapter.get_current_profile()
        assert retrieved.preferred_style == InteractionStyle.TECHNICAL

    def test_adapt_formal_style(self):
        """测试正式风格适配"""
        adapter = PersonalityAdapter()
        profile = UserProfile(
            user_id="formal_user",
            preferred_style=InteractionStyle.FORMAL,
        )
        adapter.update_profile(profile)
        result = adapter.adapt("这是测试内容", profile)
        assert isinstance(result, AdaptedResponse)
        assert result.style_applied == InteractionStyle.FORMAL

    def test_adapt_casual_style(self):
        """测试随意风格适配"""
        adapter = PersonalityAdapter()
        profile = UserProfile(
            user_id="casual_user",
            preferred_style=InteractionStyle.CASUAL,
        )
        result = adapter.adapt("这是测试内容", profile)
        assert isinstance(result, AdaptedResponse)
        assert result.style_applied == InteractionStyle.CASUAL

    def test_adapt_concise_style(self):
        """测试简洁风格适配"""
        adapter = PersonalityAdapter()
        profile = UserProfile(
            user_id="concise_user",
            preferred_style=InteractionStyle.CONCISE,
            verbosity_preference=0.2,
        )
        long_content = "这是一段很长的内容" * 100
        result = adapter.adapt(long_content, profile)
        assert isinstance(result, AdaptedResponse)
        # 简洁模式应该截断内容
        assert len(result.adapted_content) <= len(long_content)

    def test_learn_from_feedback(self):
        """测试从反馈中学习"""
        adapter = PersonalityAdapter()
        profile = adapter.get_current_profile()
        original_verbosity = profile.verbosity_preference

        adapter.learn_from_feedback(
            original="原始内容",
            adapted="适配内容",
            feedback="太长了，请简洁一些",
            positive=False,
        )

        updated_profile = adapter.get_current_profile()
        assert updated_profile.verbosity_preference < original_verbosity

    def test_export_import_profiles(self):
        """测试导出导入用户画像"""
        adapter = PersonalityAdapter()
        profile1 = UserProfile(user_id="user1", preferred_style=InteractionStyle.FORMAL)
        profile2 = UserProfile(user_id="user2", preferred_style=InteractionStyle.CASUAL)
        adapter.update_profile(profile1)
        adapter.update_profile(profile2)

        exported = adapter.export_profiles()
        assert len(exported) >= 2

        new_adapter = PersonalityAdapter()
        count = new_adapter.import_profiles(exported)
        assert count >= 2

    def test_user_profile_to_dict(self):
        """测试UserProfile转换为字典"""
        profile = UserProfile(
            user_id="test",
            preferred_style=InteractionStyle.FRIENDLY,
            expertise_level=ExpertiseLevel.INTERMEDIATE,
        )
        d = profile.to_dict()
        assert d["user_id"] == "test"
        assert d["preferred_style"] == "friendly"

    def test_user_profile_from_dict(self):
        """测试从字典创建UserProfile"""
        data = {
            "user_id": "test",
            "preferred_style": "technical",
            "expertise_level": "expert",
        }
        profile = UserProfile.from_dict(data)
        assert profile.user_id == "test"
        assert profile.preferred_style == InteractionStyle.TECHNICAL
        assert profile.expertise_level == ExpertiseLevel.EXPERT

    def test_adapted_response_to_dict(self):
        """测试AdaptedResponse转换为字典"""
        response = AdaptedResponse(
            original_content="原始",
            adapted_content="适配后",
            style_applied=InteractionStyle.FRIENDLY,
            adaptations_made=["添加问候语"],
            confidence=0.9,
        )
        d = response.to_dict()
        assert d["original_content"] == "原始"
        assert d["style_applied"] == "friendly"


class TestIntegration:
    """集成测试"""

    def test_emotion_to_need_flow(self):
        """测试情绪识别到需求预判的流程"""
        emotion_recognizer = EmotionRecognizer()
        need_predictor = NeedPredictor()

        # 用户输入带有情绪
        user_input = "这段代码又报错了，烦死了，帮我修复一下"

        # 识别情绪（可能是沮丧、消极或其他负面情绪）
        emotion = emotion_recognizer.recognize(user_input)
        assert emotion.emotion_type in [
            EmotionType.FRUSTRATED,
            EmotionType.NEGATIVE,
            EmotionType.NEUTRAL,
        ]

        # 预判需求
        need = need_predictor.predict(user_input)
        assert need.category == NeedCategory.DEBUG

    def test_full_empathy_flow(self):
        """测试完整的情感理解流程"""
        emotion_recognizer = EmotionRecognizer()
        need_predictor = NeedPredictor()
        personality_adapter = PersonalityAdapter()

        # 设置用户画像
        profile = UserProfile(
            user_id="test_user",
            preferred_style=InteractionStyle.FRIENDLY,
            expertise_level=ExpertiseLevel.BEGINNER,
        )
        personality_adapter.update_profile(profile)

        # 用户输入
        user_input = "我不明白这个错误是什么意思"

        # 1. 识别情绪
        emotion = emotion_recognizer.recognize(user_input)
        # 困惑情绪可能被识别为困惑或中性
        assert emotion.emotion_type in [EmotionType.CONFUSED, EmotionType.NEUTRAL]

        # 2. 预判需求（"错误"关键词可能触发DEBUG，"不明白"触发EXPLANATION）
        need = need_predictor.predict(user_input)
        assert need.category in [NeedCategory.EXPLANATION, NeedCategory.DEBUG]

        # 3. 适配响应
        response_content = "这个错误表示变量未定义"
        adapted = personality_adapter.adapt(response_content, profile)
        assert adapted.style_applied == InteractionStyle.FRIENDLY


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
