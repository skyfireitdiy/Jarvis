"""ContextPredictor测试模块

测试上下文预测器的各项功能。
"""

import pytest
from unittest.mock import MagicMock

from jarvis.jarvis_digital_twin.prediction import (
    PredictionContext,
    PredictionResult,
    PredictionType,
)
from jarvis.jarvis_digital_twin.prediction.context_predictor import (
    ContextPredictor,
    PredictionStrategy,
    RuleBasedEngine,
    LLMBasedEngine,
    LLMProvider,
)


# ============== Fixtures ==============


@pytest.fixture
def predictor() -> ContextPredictor:
    """创建默认预测器"""
    return ContextPredictor()


@pytest.fixture
def rule_based_predictor() -> ContextPredictor:
    """创建纯规则预测器"""
    return ContextPredictor(strategy=PredictionStrategy.RULE_BASED)


@pytest.fixture
def mock_llm_provider() -> MagicMock:
    """创建模拟LLM提供者"""
    provider = MagicMock(spec=LLMProvider)
    provider.complete.return_value = """[
        {"content": "如何编写单元测试？", "confidence": 0.85, "reasoning": "基于代码实现上下文"},
        {"content": "如何优化性能？", "confidence": 0.7, "reasoning": "基于代码复杂度"}
    ]"""
    return provider


@pytest.fixture
def basic_context() -> PredictionContext:
    """创建基础预测上下文"""
    return PredictionContext(
        current_message="How to implement this feature?",
        conversation_history=[
            {"role": "user", "content": "我想创建一个新模块"},
            {"role": "assistant", "content": "好的，我来帮你创建"},
        ],
        code_context={
            "last_action": "create_file",
            "modified_files": ["src/module.py"],
        },
        project_state={
            "current_state": "development",
            "has_errors": False,
        },
        user_profile={
            "interaction_pattern": {
                "question_pattern": {
                    "question_types": {"how": 10, "what": 5, "why": 3}
                },
                "command_pattern": {"command_categories": {"code": 20, "test": 10}},
            },
            "preferences": {
                "interaction_style": {"preferred_style": "detailed"},
                "tech_stack": {"preferred_languages": ["Python", "TypeScript"]},
            },
        },
    )


@pytest.fixture
def debug_context() -> PredictionContext:
    """创建调试场景上下文"""
    return PredictionContext(
        current_message="这个错误是什么原因？",
        conversation_history=[],
        code_context={
            "last_action": "debug",
            "modified_files": ["src/buggy.py"],
        },
        project_state={
            "current_state": "debugging",
            "has_errors": True,
        },
        user_profile={},
    )


@pytest.fixture
def empty_context() -> PredictionContext:
    """创建空上下文"""
    return PredictionContext()


# ============== ContextPredictor Tests ==============


class TestContextPredictorInit:
    """测试ContextPredictor初始化"""

    def test_default_strategy(self, predictor: ContextPredictor) -> None:
        """测试默认策略为HYBRID"""
        assert predictor.strategy == PredictionStrategy.HYBRID

    def test_rule_based_strategy(self) -> None:
        """测试设置规则策略"""
        p = ContextPredictor(strategy=PredictionStrategy.RULE_BASED)
        assert p.strategy == PredictionStrategy.RULE_BASED

    def test_llm_based_strategy(self) -> None:
        """测试设置LLM策略"""
        p = ContextPredictor(strategy=PredictionStrategy.LLM_BASED)
        assert p.strategy == PredictionStrategy.LLM_BASED

    def test_strategy_setter(self, predictor: ContextPredictor) -> None:
        """测试策略设置器"""
        predictor.strategy = PredictionStrategy.RULE_BASED
        assert predictor.strategy == PredictionStrategy.RULE_BASED

    def test_set_llm_provider(
        self, predictor: ContextPredictor, mock_llm_provider: MagicMock
    ) -> None:
        """测试设置LLM提供者"""
        predictor.set_llm_provider(mock_llm_provider)
        # 验证不抛出异常即可


class TestPredictNextQuestion:
    """测试predict_next_question方法"""

    def test_predict_with_implement_context(
        self, rule_based_predictor: ContextPredictor, basic_context: PredictionContext
    ) -> None:
        """测试实现场景的问题预测"""
        result = rule_based_predictor.predict_next_question(basic_context)

        assert isinstance(result, PredictionResult)
        assert result.prediction_type == PredictionType.NEXT_QUESTION
        assert result.confidence_score > 0

    def test_predict_with_debug_context(
        self, rule_based_predictor: ContextPredictor, debug_context: PredictionContext
    ) -> None:
        """测试调试场景的问题预测"""
        result = rule_based_predictor.predict_next_question(debug_context)

        assert isinstance(result, PredictionResult)
        assert result.prediction_type == PredictionType.NEXT_QUESTION

    def test_predict_with_empty_context(
        self, rule_based_predictor: ContextPredictor, empty_context: PredictionContext
    ) -> None:
        """测试空上下文的问题预测"""
        result = rule_based_predictor.predict_next_question(empty_context)

        assert isinstance(result, PredictionResult)
        assert result.confidence_score == 0.0

    def test_predict_returns_alternatives(
        self, rule_based_predictor: ContextPredictor, basic_context: PredictionContext
    ) -> None:
        """测试预测返回备选项"""
        result = rule_based_predictor.predict_next_question(basic_context)

        # 备选项可能为空，但应该是列表
        assert isinstance(result.alternatives, list)

    def test_predict_returns_evidence(
        self, rule_based_predictor: ContextPredictor, basic_context: PredictionContext
    ) -> None:
        """测试预测返回证据"""
        result = rule_based_predictor.predict_next_question(basic_context)

        assert isinstance(result.evidence, list)


class TestPredictNextAction:
    """测试predict_next_action方法"""

    def test_predict_after_create_file(
        self, rule_based_predictor: ContextPredictor, basic_context: PredictionContext
    ) -> None:
        """测试创建文件后的操作预测"""
        result = rule_based_predictor.predict_next_action(basic_context)

        assert isinstance(result, PredictionResult)
        assert result.prediction_type == PredictionType.NEXT_ACTION
        assert result.confidence_score > 0

    def test_predict_after_debug(
        self, rule_based_predictor: ContextPredictor, debug_context: PredictionContext
    ) -> None:
        """测试调试后的操作预测"""
        result = rule_based_predictor.predict_next_action(debug_context)

        assert isinstance(result, PredictionResult)
        assert result.prediction_type == PredictionType.NEXT_ACTION

    def test_predict_with_empty_code_context(
        self, rule_based_predictor: ContextPredictor, empty_context: PredictionContext
    ) -> None:
        """测试空代码上下文的操作预测"""
        result = rule_based_predictor.predict_next_action(empty_context)

        assert isinstance(result, PredictionResult)
        assert result.confidence_score == 0.0


class TestPredictNeededHelp:
    """测试predict_needed_help方法"""

    def test_predict_help_for_debugging(
        self, rule_based_predictor: ContextPredictor, debug_context: PredictionContext
    ) -> None:
        """测试调试场景的帮助预测"""
        results = rule_based_predictor.predict_needed_help(debug_context)

        assert isinstance(results, list)
        if results:
            assert all(isinstance(r, PredictionResult) for r in results)
            assert all(r.prediction_type == PredictionType.NEEDED_HELP for r in results)

    def test_predict_help_returns_sorted_results(
        self, rule_based_predictor: ContextPredictor, debug_context: PredictionContext
    ) -> None:
        """测试帮助预测结果按置信度排序"""
        results = rule_based_predictor.predict_needed_help(debug_context)

        if len(results) > 1:
            confidences = [r.confidence_score for r in results]
            assert confidences == sorted(confidences, reverse=True)

    def test_predict_help_with_empty_context(
        self, rule_based_predictor: ContextPredictor, empty_context: PredictionContext
    ) -> None:
        """测试空上下文的帮助预测"""
        results = rule_based_predictor.predict_needed_help(empty_context)

        assert isinstance(results, list)


# ============== RuleBasedEngine Tests ==============


class TestRuleBasedEngine:
    """测试规则引擎"""

    @pytest.fixture
    def engine(self) -> RuleBasedEngine:
        return RuleBasedEngine()

    def test_predict_question_with_implement_keyword(
        self, engine: RuleBasedEngine
    ) -> None:
        """测试实现关键词的问题预测"""
        context = PredictionContext(current_message="如何implement这个功能")
        results = engine.predict(context, PredictionType.NEXT_QUESTION)

        assert len(results) > 0
        assert all(isinstance(r, tuple) and len(r) == 3 for r in results)

    def test_predict_question_with_error_keyword(self, engine: RuleBasedEngine) -> None:
        """测试错误关键词的问题预测"""
        context = PredictionContext(current_message="这个error是什么")
        results = engine.predict(context, PredictionType.NEXT_QUESTION)

        assert len(results) > 0

    def test_predict_action_with_create_context(self, engine: RuleBasedEngine) -> None:
        """测试创建操作的预测"""
        context = PredictionContext(code_context={"last_action": "create new file"})
        results = engine.predict(context, PredictionType.NEXT_ACTION)

        assert len(results) > 0

    def test_predict_action_with_test_files(self, engine: RuleBasedEngine) -> None:
        """测试修改测试文件的操作预测"""
        context = PredictionContext(code_context={"modified_files": ["test_module.py"]})
        results = engine.predict(context, PredictionType.NEXT_ACTION)

        assert len(results) > 0

    def test_predict_help_with_error_state(self, engine: RuleBasedEngine) -> None:
        """测试错误状态的帮助预测"""
        context = PredictionContext(project_state={"has_errors": True})
        results = engine.predict(context, PredictionType.NEEDED_HELP)

        assert len(results) > 0

    def test_predict_help_with_testing_state(self, engine: RuleBasedEngine) -> None:
        """测试测试状态的帮助预测"""
        context = PredictionContext(project_state={"running_tests": True})
        results = engine.predict(context, PredictionType.NEEDED_HELP)

        assert len(results) > 0

    def test_predict_with_unknown_type(self, engine: RuleBasedEngine) -> None:
        """测试未知预测类型"""
        context = PredictionContext()
        results = engine.predict(context, PredictionType.IMPLICIT_NEED)

        assert results == []


# ============== LLMBasedEngine Tests ==============


class TestLLMBasedEngine:
    """测试LLM引擎"""

    @pytest.fixture
    def engine(self) -> LLMBasedEngine:
        return LLMBasedEngine()

    @pytest.fixture
    def engine_with_provider(self, mock_llm_provider: MagicMock) -> LLMBasedEngine:
        engine = LLMBasedEngine(mock_llm_provider)
        return engine

    def test_predict_without_provider(self, engine: LLMBasedEngine) -> None:
        """测试无LLM提供者时的预测"""
        context = PredictionContext(current_message="测试消息")
        results = engine.predict(context, PredictionType.NEXT_QUESTION)

        assert results == []

    def test_predict_with_provider(self, engine_with_provider: LLMBasedEngine) -> None:
        """测试有LLM提供者时的预测"""
        context = PredictionContext(current_message="测试消息")
        results = engine_with_provider.predict(context, PredictionType.NEXT_QUESTION)

        assert len(results) > 0
        assert all(isinstance(r, tuple) and len(r) == 3 for r in results)

    def test_set_llm_provider(
        self, engine: LLMBasedEngine, mock_llm_provider: MagicMock
    ) -> None:
        """测试设置LLM提供者"""
        engine.set_llm_provider(mock_llm_provider)
        context = PredictionContext(current_message="测试")
        results = engine.predict(context, PredictionType.NEXT_QUESTION)

        assert len(results) > 0

    def test_parse_invalid_json_response(
        self, engine_with_provider: LLMBasedEngine, mock_llm_provider: MagicMock
    ) -> None:
        """测试解析无效JSON响应"""
        mock_llm_provider.complete.return_value = "这不是有效的JSON"
        context = PredictionContext(current_message="测试")
        results = engine_with_provider.predict(context, PredictionType.NEXT_QUESTION)

        assert results == []

    def test_parse_partial_json_response(
        self, engine_with_provider: LLMBasedEngine, mock_llm_provider: MagicMock
    ) -> None:
        """测试解析部分有效的JSON响应"""
        mock_llm_provider.complete.return_value = (
            """一些文本 [{"content": "问题", "confidence": 0.8}] 更多文本"""
        )
        context = PredictionContext(current_message="测试")
        results = engine_with_provider.predict(context, PredictionType.NEXT_QUESTION)

        assert len(results) == 1
