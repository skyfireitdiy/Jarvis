"""NeedInferrer 测试模块

测试需求推理器的各项功能。
"""

import pytest
from jarvis.jarvis_digital_twin.prediction import (
    InferenceResult,
    PredictionContext,
    PredictionType,
)
from jarvis.jarvis_digital_twin.prediction.need_inferrer import (
    EvidenceItem,
    InferenceChainStep,
    InferenceStrategy,
    NeedInferrer,
    PatternBasedInferrer,
    RuleBasedInferrer,
)


# ============ Fixtures ============


@pytest.fixture
def rule_inferrer() -> RuleBasedInferrer:
    """创建规则推理引擎"""
    return RuleBasedInferrer()


@pytest.fixture
def pattern_inferrer() -> PatternBasedInferrer:
    """创建模式推理引擎"""
    return PatternBasedInferrer()


@pytest.fixture
def need_inferrer() -> NeedInferrer:
    """创建需求推理器"""
    return NeedInferrer()


@pytest.fixture
def basic_context() -> PredictionContext:
    """创建基础预测上下文"""
    return PredictionContext(
        current_message="我需要实现一个新功能",
        conversation_history=[
            {"role": "user", "content": "帮我创建一个文件"},
            {"role": "assistant", "content": "好的，已创建"},
        ],
        code_context={"modified_files": ["src/main.py"]},
        project_state={"has_errors": False},
        user_profile={
            "preferences": {
                "tech_stack": {"preferred_languages": ["Python", "TypeScript"]},
                "code_style": {"prefers_type_hints": True},
            },
            "interaction_pattern": {
                "question_pattern": {"question_types": {"how_to": 5, "debug": 3}},
                "command_pattern": {"command_categories": {"file": 10, "git": 5}},
            },
            "goals": [
                {"type": "feature", "description": "完成用户模块", "progress": 50},
            ],
        },
    )


@pytest.fixture
def empty_context() -> PredictionContext:
    """创建空上下文"""
    return PredictionContext()


# ============ RuleBasedInferrer Tests ============


class TestRuleBasedInferrer:
    """规则推理引擎测试"""

    def test_infer_implicit_needs_implement_feature(
        self, rule_inferrer: RuleBasedInferrer
    ):
        """测试实现功能的隐式需求推理"""
        results = rule_inferrer.infer_implicit_needs("implement a new feature")
        assert len(results) > 0
        contents = [r[0] for r in results]
        assert "write_tests" in contents

    def test_infer_implicit_needs_fix_bug(self, rule_inferrer: RuleBasedInferrer):
        """测试修复bug的隐式需求推理"""
        results = rule_inferrer.infer_implicit_needs("fix this bug")
        assert len(results) > 0
        contents = [r[0] for r in results]
        assert "add_regression_test" in contents

    def test_infer_implicit_needs_unknown(self, rule_inferrer: RuleBasedInferrer):
        """测试未知需求类型"""
        results = rule_inferrer.infer_implicit_needs("random text")
        assert len(results) == 0

    def test_infer_implicit_needs_empty(self, rule_inferrer: RuleBasedInferrer):
        """测试空输入"""
        results = rule_inferrer.infer_implicit_needs("")
        assert len(results) == 0

    def test_infer_follow_up_tasks_create_file(self, rule_inferrer: RuleBasedInferrer):
        """测试创建文件的后续任务推理"""
        results = rule_inferrer.infer_follow_up_tasks("create a new file")
        assert len(results) > 0
        contents = [r[0] for r in results]
        assert "implement_logic" in contents

    def test_infer_follow_up_tasks_write_test(self, rule_inferrer: RuleBasedInferrer):
        """测试编写测试的后续任务推理"""
        results = rule_inferrer.infer_follow_up_tasks("write test cases")
        assert len(results) > 0
        contents = [r[0] for r in results]
        assert "run_test" in contents

    def test_infer_root_cause_import_error(self, rule_inferrer: RuleBasedInferrer):
        """测试导入错误的根本原因推理"""
        results = rule_inferrer.infer_root_cause("ImportError: No module named xyz")
        assert len(results) > 0
        contents = [r[0] for r in results]
        assert "missing_dependency" in contents

    def test_infer_root_cause_type_error(self, rule_inferrer: RuleBasedInferrer):
        """测试类型错误的根本原因推理"""
        results = rule_inferrer.infer_root_cause("TypeError: expected str")
        assert len(results) > 0
        contents = [r[0] for r in results]
        assert "wrong_argument_type" in contents

    def test_identify_type_with_keywords(self, rule_inferrer: RuleBasedInferrer):
        """测试关键词识别"""
        result = rule_inferrer._identify_type(
            "implement feature", rule_inferrer.KEYWORD_MAPPINGS["need"]
        )
        assert result == "implement_feature"

    def test_identify_type_unknown(self, rule_inferrer: RuleBasedInferrer):
        """测试未知类型识别"""
        result = rule_inferrer._identify_type(
            "xyz abc", rule_inferrer.KEYWORD_MAPPINGS["need"]
        )
        assert result == "unknown"


# ============ PatternBasedInferrer Tests ============


class TestPatternBasedInferrer:
    """模式推理引擎测试"""

    def test_infer_from_profile_empty(self, pattern_inferrer: PatternBasedInferrer):
        """测试空用户画像"""
        results = pattern_inferrer.infer_from_profile({}, "implicit_need")
        assert len(results) == 0

    def test_infer_from_interaction_pattern(
        self, pattern_inferrer: PatternBasedInferrer
    ):
        """测试从交互模式推理"""
        profile = {
            "interaction_pattern": {
                "question_pattern": {"question_types": {"how_to": 10, "debug": 5}},
            }
        }
        results = pattern_inferrer.infer_from_profile(profile, "implicit_need")
        assert len(results) > 0

    def test_infer_from_command_pattern(self, pattern_inferrer: PatternBasedInferrer):
        """测试从命令模式推理后续任务"""
        profile = {
            "interaction_pattern": {
                "command_pattern": {"command_categories": {"file": 10, "git": 5}},
            }
        }
        results = pattern_inferrer.infer_from_profile(profile, "follow_up")
        assert len(results) > 0

    def test_infer_from_preferences(self, pattern_inferrer: PatternBasedInferrer):
        """测试从偏好推理"""
        profile = {
            "preferences": {
                "tech_stack": {"preferred_languages": ["Python"]},
                "code_style": {"prefers_type_hints": True, "prefers_docstrings": True},
            }
        }
        results = pattern_inferrer.infer_from_profile(profile, "implicit_need")
        assert len(results) > 0

    def test_infer_from_goals(self, pattern_inferrer: PatternBasedInferrer):
        """测试从目标推理"""
        profile = {
            "goals": [
                {"type": "feature", "description": "完成模块", "progress": 50},
            ]
        }
        results = pattern_inferrer.infer_from_profile(profile, "follow_up")
        assert len(results) > 0


# ============ NeedInferrer Tests ============


class TestNeedInferrer:
    """需求推理器测试"""

    def test_init_default_strategy(self):
        """测试默认策略"""
        inferrer = NeedInferrer()
        assert inferrer.strategy == InferenceStrategy.HYBRID

    def test_init_custom_strategy(self):
        """测试自定义策略"""
        inferrer = NeedInferrer(strategy=InferenceStrategy.RULE_BASED)
        assert inferrer.strategy == InferenceStrategy.RULE_BASED

    def test_strategy_setter(self, need_inferrer: NeedInferrer):
        """测试策略设置"""
        need_inferrer.strategy = InferenceStrategy.PATTERN_BASED
        assert need_inferrer.strategy == InferenceStrategy.PATTERN_BASED

    def test_infer_implicit_needs_empty_input(
        self, need_inferrer: NeedInferrer, basic_context: PredictionContext
    ):
        """测试空输入的隐式需求推理"""
        results = need_inferrer.infer_implicit_needs(basic_context, "")
        assert len(results) == 0

    def test_infer_implicit_needs_with_context(
        self, need_inferrer: NeedInferrer, basic_context: PredictionContext
    ):
        """测试带上下文的隐式需求推理"""
        results = need_inferrer.infer_implicit_needs(
            basic_context, "implement a feature"
        )
        assert len(results) > 0
        assert all(isinstance(r, InferenceResult) for r in results)

    def test_infer_implicit_needs_sorted_by_confidence(
        self, need_inferrer: NeedInferrer, basic_context: PredictionContext
    ):
        """测试结果按置信度排序"""
        results = need_inferrer.infer_implicit_needs(basic_context, "implement feature")
        if len(results) > 1:
            for i in range(len(results) - 1):
                assert results[i].confidence_score >= results[i + 1].confidence_score

    def test_infer_follow_up_tasks_empty_input(
        self, need_inferrer: NeedInferrer, basic_context: PredictionContext
    ):
        """测试空输入的后续任务推理"""
        results = need_inferrer.infer_follow_up_tasks(basic_context, "")
        assert len(results) == 0

    def test_infer_follow_up_tasks_with_context(
        self, need_inferrer: NeedInferrer, basic_context: PredictionContext
    ):
        """测试带上下文的后续任务推理"""
        results = need_inferrer.infer_follow_up_tasks(
            basic_context, "create a new file"
        )
        assert len(results) > 0
        assert all(isinstance(r, InferenceResult) for r in results)

    def test_infer_root_cause_empty_input(
        self, need_inferrer: NeedInferrer, basic_context: PredictionContext
    ):
        """测试空输入的根本原因推理"""
        result = need_inferrer.infer_root_cause(basic_context, "")
        assert isinstance(result, InferenceResult)
        assert result.confidence_score == 0.0

    def test_infer_root_cause_with_context(
        self, need_inferrer: NeedInferrer, basic_context: PredictionContext
    ):
        """测试带上下文的根本原因推理"""
        result = need_inferrer.infer_root_cause(
            basic_context, "ImportError: module not found"
        )
        assert isinstance(result, InferenceResult)
        assert result.confidence_score > 0

    def test_infer_root_cause_unknown_problem(
        self, need_inferrer: NeedInferrer, basic_context: PredictionContext
    ):
        """测试未知问题的根本原因推理"""
        result = need_inferrer.infer_root_cause(basic_context, "some random issue xyz")
        assert isinstance(result, InferenceResult)
        assert result.confidence_score <= 0.1


# ============ Data Classes Tests ============


class TestDataClasses:
    """数据类测试"""

    def test_inference_chain_step_creation(self):
        """测试推理链步骤创建"""
        step = InferenceChainStep(
            step_number=1,
            description="识别问题类型",
            input_data="ImportError",
            output_data="import_error",
            confidence=0.9,
        )
        assert step.step_number == 1
        assert step.confidence == 0.9

    def test_evidence_item_creation(self):
        """测试证据项创建"""
        evidence = EvidenceItem(
            content="发现导入错误",
            source="error_log",
            weight=0.8,
            is_supporting=True,
        )
        assert evidence.content == "发现导入错误"
        assert evidence.is_supporting is True

    def test_evidence_item_default_values(self):
        """测试证据项默认值"""
        evidence = EvidenceItem(content="test", source="test_source")
        assert evidence.weight == 1.0
        assert evidence.is_supporting is True


# ============ Edge Cases Tests ============


class TestEdgeCases:
    """边界情况测试"""

    def test_infer_with_empty_context(
        self, need_inferrer: NeedInferrer, empty_context: PredictionContext
    ):
        """测试空上下文"""
        results = need_inferrer.infer_implicit_needs(empty_context, "implement feature")
        assert isinstance(results, list)

    def test_infer_with_none_profile(self, need_inferrer: NeedInferrer):
        """测试None用户画像"""
        context = PredictionContext(user_profile={})
        results = need_inferrer.infer_implicit_needs(context, "fix bug")
        assert isinstance(results, list)

    def test_inference_result_has_reasoning_chain(
        self, need_inferrer: NeedInferrer, basic_context: PredictionContext
    ):
        """测试推理结果包含推理链"""
        results = need_inferrer.infer_implicit_needs(basic_context, "implement feature")
        if results:
            assert hasattr(results[0], "reasoning_chain")
            assert isinstance(results[0].reasoning_chain, list)

    def test_inference_result_has_evidence(
        self, need_inferrer: NeedInferrer, basic_context: PredictionContext
    ):
        """测试推理结果包含证据"""
        results = need_inferrer.infer_implicit_needs(basic_context, "implement feature")
        if results:
            assert hasattr(results[0], "supporting_evidence")
            assert hasattr(results[0], "opposing_evidence")

    def test_root_cause_has_related_inferences(
        self, need_inferrer: NeedInferrer, basic_context: PredictionContext
    ):
        """测试根本原因包含相关推理"""
        result = need_inferrer.infer_root_cause(basic_context, "ImportError: no module")
        assert hasattr(result, "related_inferences")

    def test_inference_type_correct(
        self, need_inferrer: NeedInferrer, basic_context: PredictionContext
    ):
        """测试推理类型正确"""
        results = need_inferrer.infer_implicit_needs(basic_context, "implement feature")
        if results:
            assert results[0].inference_type == PredictionType.IMPLICIT_NEED

        results = need_inferrer.infer_follow_up_tasks(basic_context, "create file")
        if results:
            assert results[0].inference_type == PredictionType.FOLLOW_UP_TASK

        result = need_inferrer.infer_root_cause(basic_context, "TypeError")
        assert result.inference_type == PredictionType.ROOT_CAUSE

    def test_rule_based_strategy_only(self, basic_context: PredictionContext):
        """测试仅规则策略"""
        inferrer = NeedInferrer(strategy=InferenceStrategy.RULE_BASED)
        results = inferrer.infer_implicit_needs(basic_context, "implement feature")
        assert isinstance(results, list)

    def test_pattern_based_strategy_only(self, basic_context: PredictionContext):
        """测试仅模式策略"""
        inferrer = NeedInferrer(strategy=InferenceStrategy.PATTERN_BASED)
        results = inferrer.infer_implicit_needs(basic_context, "implement feature")
        assert isinstance(results, list)
