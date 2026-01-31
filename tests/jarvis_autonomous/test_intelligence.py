"""智能基础设施层测试

测试 LLMReasoner、RuleLearner 和 HybridEngine。
"""

from jarvis.jarvis_autonomous.intelligence import (
    InferenceMode,
    InferenceResult,
    LearnedRule,
    LLMReasoner,
    ReasoningContext,
    ReasoningResult,
    ReasoningType,
    RuleLearner,
    RuleStatus,
    RuleType,
)


class TestReasoningType:
    """测试推理类型枚举"""

    def test_reasoning_types(self):
        """测试所有推理类型"""
        assert ReasoningType.ANALYSIS.value == "analysis"
        assert ReasoningType.GENERATION.value == "generation"
        assert ReasoningType.EVALUATION.value == "evaluation"
        assert ReasoningType.DECISION.value == "decision"
        assert ReasoningType.EXTRACTION.value == "extraction"
        assert ReasoningType.CLASSIFICATION.value == "classification"


class TestReasoningContext:
    """测试推理上下文"""

    def test_create_context(self):
        """测试创建上下文"""
        context = ReasoningContext(
            task_type=ReasoningType.ANALYSIS,
            input_data="测试输入",
            instruction="分析这段文本",
        )
        assert context.task_type == ReasoningType.ANALYSIS
        assert context.input_data == "测试输入"
        assert context.instruction == "分析这段文本"

    def test_context_to_prompt(self):
        """测试上下文转换为 prompt"""
        context = ReasoningContext(
            task_type=ReasoningType.ANALYSIS,
            input_data="测试输入",
            instruction="分析这段文本",
            constraints=["约束1", "约束2"],
        )
        prompt = context.to_prompt()
        assert "分析这段文本" in prompt
        assert "测试输入" in prompt
        assert "约束1" in prompt


class TestLLMReasoner:
    """测试 LLM 推理器"""

    def test_create_reasoner(self):
        """测试创建推理器"""
        reasoner = LLMReasoner()
        assert reasoner is not None

    def test_analyze(self):
        """测试分析推理"""
        reasoner = LLMReasoner()
        result = reasoner.analyze(
            input_data="这是一段测试文本",
            instruction="分析文本内容",
        )
        assert isinstance(result, ReasoningResult)

    def test_generate(self):
        """测试生成推理"""
        reasoner = LLMReasoner()
        result = reasoner.generate(
            input_data="主题：Python",
            instruction="生成相关内容",
        )
        assert isinstance(result, ReasoningResult)

    def test_evaluate(self):
        """测试评估推理"""
        reasoner = LLMReasoner()
        result = reasoner.evaluate(
            input_data="代码片段",
            criteria=["可读性", "性能"],
        )
        assert isinstance(result, ReasoningResult)

    def test_decide(self):
        """测试决策推理"""
        reasoner = LLMReasoner()
        result = reasoner.decide(
            input_data="选择问题",
            options=["选项A", "选项B"],
        )
        assert isinstance(result, ReasoningResult)

    def test_get_statistics(self):
        """测试获取统计信息"""
        reasoner = LLMReasoner()
        stats = reasoner.get_statistics()
        assert "total" in stats
        assert "success_rate" in stats


class TestRuleType:
    """测试规则类型枚举"""

    def test_rule_types(self):
        """测试所有规则类型"""
        assert RuleType.PATTERN.value == "pattern"
        assert RuleType.KEYWORD.value == "keyword"
        assert RuleType.CONDITION.value == "condition"
        assert RuleType.TEMPLATE.value == "template"
        assert RuleType.HEURISTIC.value == "heuristic"


class TestRuleStatus:
    """测试规则状态枚举"""

    def test_rule_statuses(self):
        """测试所有规则状态"""
        assert RuleStatus.CANDIDATE.value == "candidate"
        assert RuleStatus.VALIDATED.value == "validated"
        assert RuleStatus.ACTIVE.value == "active"
        assert RuleStatus.DEPRECATED.value == "deprecated"


class TestLearnedRule:
    """测试学习到的规则"""

    def test_create_rule(self):
        """测试创建规则"""
        rule = LearnedRule(
            id="rule-1",
            name="测试规则",
            description="这是一个测试规则",
            rule_type=RuleType.KEYWORD,
            condition="keywords: [test]",
            action="classify: test",
        )
        assert rule.id == "rule-1"
        assert rule.name == "测试规则"
        assert rule.rule_type == RuleType.KEYWORD
        assert rule.status == RuleStatus.CANDIDATE

    def test_rule_to_dict(self):
        """测试规则转换为字典"""
        rule = LearnedRule(
            id="rule-1",
            name="测试规则",
            description="描述",
            rule_type=RuleType.KEYWORD,
            condition="condition",
            action="action",
        )
        data = rule.to_dict()
        assert data["id"] == "rule-1"
        assert data["name"] == "测试规则"
        assert data["rule_type"] == "keyword"

    def test_record_usage(self):
        """测试记录使用情况"""
        rule = LearnedRule(
            id="rule-1",
            name="测试规则",
            description="描述",
            rule_type=RuleType.KEYWORD,
            condition="condition",
            action="action",
        )
        rule.record_usage(success=True)
        assert rule.usage_count == 1
        assert rule.success_count == 1

        rule.record_usage(success=False)
        assert rule.usage_count == 2
        assert rule.success_count == 1

    def test_success_rate(self):
        """测试成功率计算"""
        rule = LearnedRule(
            id="rule-1",
            name="测试规则",
            description="描述",
            rule_type=RuleType.KEYWORD,
            condition="condition",
            action="action",
        )
        assert rule.success_rate == 0.0

        rule.record_usage(success=True)
        rule.record_usage(success=True)
        rule.record_usage(success=False)
        assert abs(rule.success_rate - 2 / 3) < 0.01


class TestRuleLearner:
    """测试规则学习器"""

    def test_create_learner(self):
        """测试创建学习器"""
        learner = RuleLearner()
        assert learner is not None
        assert len(learner.rules) == 0

    def test_learn_from_reasoning(self):
        """测试从推理结果学习"""
        learner = RuleLearner()
        rule = learner.learn_from_reasoning(
            reasoning_input="测试输入包含关键词",
            reasoning_output='{"category": "test", "confidence": 0.8}',
            reasoning_type="classification",
            success=True,
        )
        # 可能学习到规则，也可能没有
        if rule:
            assert rule.id in learner.rules

    def test_learn_only_from_success(self):
        """测试只从成功的推理中学习"""
        learner = RuleLearner()
        rule = learner.learn_from_reasoning(
            reasoning_input="测试输入",
            reasoning_output="输出",
            reasoning_type="classification",
            success=False,
        )
        assert rule is None

    def test_match_rule(self):
        """测试规则匹配"""
        learner = RuleLearner()
        # 添加一个已验证的规则
        rule = LearnedRule(
            id="rule-1",
            name="测试规则",
            description="描述",
            rule_type=RuleType.KEYWORD,
            condition="keywords: ['test', 'keyword']",
            action="classify: test",
            status=RuleStatus.VALIDATED,
            confidence=0.8,
        )
        learner.rules[rule.id] = rule

        # 匹配
        matched = learner.match_rule("this is a test with keyword")
        assert matched is not None
        assert matched.id == "rule-1"

    def test_get_active_rules(self):
        """测试获取激活的规则"""
        learner = RuleLearner()
        # 添加不同状态的规则
        for i, status in enumerate(
            [RuleStatus.CANDIDATE, RuleStatus.ACTIVE, RuleStatus.DEPRECATED]
        ):
            rule = LearnedRule(
                id=f"rule-{i}",
                name=f"规则{i}",
                description="描述",
                rule_type=RuleType.KEYWORD,
                condition="condition",
                action="action",
                status=status,
            )
            learner.rules[rule.id] = rule

        active = learner.get_active_rules()
        assert len(active) == 1
        assert active[0].status == RuleStatus.ACTIVE

    def test_get_statistics(self):
        """测试获取统计信息"""
        learner = RuleLearner()
        stats = learner.get_statistics()
        assert "total_rules" in stats
        assert "by_status" in stats
        assert "by_type" in stats

    def test_export_import_rules(self):
        """测试导出和导入规则"""
        learner = RuleLearner()
        rule = LearnedRule(
            id="rule-1",
            name="测试规则",
            description="描述",
            rule_type=RuleType.KEYWORD,
            condition="condition",
            action="action",
        )
        learner.rules[rule.id] = rule

        # 导出
        exported = learner.export_rules()
        assert len(exported) == 1

        # 导入到新学习器
        new_learner = RuleLearner()
        imported = new_learner.import_rules(exported)
        assert imported == 1
        assert len(new_learner.rules) == 1


class TestInferenceMode:
    """测试推理模式枚举"""

    def test_inference_modes(self):
        """测试所有推理模式"""
        assert InferenceMode.RULE_ONLY.value == "rule_only"
        assert InferenceMode.LLM_ONLY.value == "llm_only"
        assert InferenceMode.HYBRID.value == "hybrid"
        assert InferenceMode.AUTO.value == "auto"


class TestInferenceResult:
    """测试推理结果"""

    def test_create_result(self):
        """测试创建结果"""
        result = InferenceResult(
            success=True,
            output="测试输出",
            confidence=0.9,
        )
        assert result.success is True
        assert result.output == "测试输出"
        assert result.confidence == 0.9

    def test_result_to_dict(self):
        """测试结果转换为字典"""
        result = InferenceResult(
            success=True,
            output="测试输出",
            mode_used=InferenceMode.HYBRID,
        )
        data = result.to_dict()
        assert data["success"] is True
        assert data["output"] == "测试输出"
        assert data["mode_used"] == "hybrid"
