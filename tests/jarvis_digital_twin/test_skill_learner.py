"""技能学习器测试模块。

测试SkillLearner类的所有功能。
"""

from unittest.mock import MagicMock

from jarvis.jarvis_digital_twin.continuous_learning import (
    Skill,
    SkillLearner,
    SkillType,
    RecencyEvaluator,
    SuccessRateEvaluator,
    UsageFrequencyEvaluator,
)


class TestSkillLearner:
    """SkillLearner类测试。"""

    def setup_method(self) -> None:
        """每个测试方法前初始化。"""
        self.learner = SkillLearner()

    # ==================== learn_tool 测试 ====================

    def test_learn_tool_basic(self) -> None:
        """测试基本工具学习。"""
        skill = self.learner.learn_tool("git", "git commit -m 'test'")
        assert skill is not None
        assert skill.name == "git"
        assert skill.type == SkillType.TOOL_USAGE
        assert "git commit" in skill.examples[0]

    def test_learn_tool_with_context(self) -> None:
        """测试带上下文的工具学习。"""
        skill = self.learner.learn_tool("docker", "docker run -it ubuntu", "容器化部署")
        assert skill.metadata["context"] == "容器化部署"

    def test_learn_tool_duplicate(self) -> None:
        """测试重复学习同一工具。"""
        skill1 = self.learner.learn_tool("npm", "npm install")
        skill2 = self.learner.learn_tool("npm", "npm run build")
        assert skill1.id == skill2.id
        assert len(skill2.examples) == 2

    def test_learn_tool_empty_example(self) -> None:
        """测试空示例的工具学习。"""
        skill = self.learner.learn_tool("curl", "")
        assert skill.examples == []

    # ==================== learn_pattern 测试 ====================

    def test_learn_pattern_basic(self) -> None:
        """测试基本模式学习。"""
        skill = self.learner.learn_pattern(
            "TDD", "测试驱动开发方法论", ["先写测试", "再写实现", "重构"]
        )
        assert skill.name == "TDD"
        assert skill.type == SkillType.METHODOLOGY
        assert len(skill.examples) == 3

    def test_learn_pattern_duplicate(self) -> None:
        """测试重复学习同一模式。"""
        skill1 = self.learner.learn_pattern("DDD", "领域驱动设计", ["聚合根"])
        skill2 = self.learner.learn_pattern("DDD", "领域驱动设计", ["值对象"])
        assert skill1.id == skill2.id
        assert "聚合根" in skill2.examples
        assert "值对象" in skill2.examples

    def test_learn_pattern_with_methodology_manager(self) -> None:
        """测试与方法论管理器集成。"""
        mock_manager = MagicMock()
        mock_manager.add = MagicMock()
        learner = SkillLearner(methodology_manager=mock_manager)
        learner.learn_pattern("SOLID", "SOLID原则", ["单一职责"])
        mock_manager.add.assert_called_once()

    # ==================== learn_language 测试 ====================

    def test_learn_language_basic(self) -> None:
        """测试基本语言学习。"""
        skill = self.learner.learn_language("Python", "print('hello')")
        assert skill.name == "python"  # 应该是小写
        assert skill.type == SkillType.LANGUAGE

    def test_learn_language_case_insensitive(self) -> None:
        """测试语言名称大小写不敏感。"""
        skill1 = self.learner.learn_language("RUST", "fn main() {}")
        skill2 = self.learner.learn_language("rust", "let x = 1;")
        assert skill1.id == skill2.id

    # ==================== learn_framework 测试 ====================

    def test_learn_framework_basic(self) -> None:
        """测试基本框架学习。"""
        skill = self.learner.learn_framework(
            "FastAPI", "Python Web框架", ["@app.get('/')"]
        )
        assert skill.name == "FastAPI"
        assert skill.type == SkillType.FRAMEWORK

    # ==================== learn_domain 测试 ====================

    def test_learn_domain_basic(self) -> None:
        """测试基本领域学习。"""
        skill = self.learner.learn_domain(
            "机器学习", "AI领域知识", ["监督学习", "无监督学习"]
        )
        assert skill.name == "机器学习"
        assert skill.type == SkillType.DOMAIN

    # ==================== evaluate_skill 测试 ====================

    def test_evaluate_skill_not_found(self) -> None:
        """测试评估不存在的技能。"""
        score = self.learner.evaluate_skill("nonexistent")
        assert score == 0.0

    def test_evaluate_skill_basic(self) -> None:
        """测试基本技能评估。"""
        skill = self.learner.learn_tool("vim", "vim file.txt")
        score = self.learner.evaluate_skill(skill.id)
        assert 0.0 <= score <= 1.0

    def test_evaluate_skill_with_usage(self) -> None:
        """测试使用后的技能评估。"""
        skill = self.learner.learn_tool("grep", "grep pattern file")
        for _ in range(10):
            self.learner.record_usage(skill.id, success=True)
        score = self.learner.evaluate_skill(skill.id)
        assert score > 0.1  # 使用后应该有提升

    # ==================== get_skill 测试 ====================

    def test_get_skill_exists(self) -> None:
        """测试获取存在的技能。"""
        skill = self.learner.learn_tool("sed", "sed 's/a/b/g'")
        retrieved = self.learner.get_skill(skill.id)
        assert retrieved is not None
        assert retrieved.id == skill.id

    def test_get_skill_not_exists(self) -> None:
        """测试获取不存在的技能。"""
        retrieved = self.learner.get_skill("nonexistent")
        assert retrieved is None

    def test_get_skill_by_name(self) -> None:
        """测试按名称获取技能。"""
        self.learner.learn_tool("awk", "awk '{print $1}'")
        skill = self.learner.get_skill_by_name("awk")
        assert skill is not None
        assert skill.name == "awk"

    def test_get_skill_by_name_case_insensitive(self) -> None:
        """测试按名称获取技能（大小写不敏感）。"""
        self.learner.learn_tool("Make", "make build")
        skill = self.learner.get_skill_by_name("make")
        assert skill is not None

    # ==================== search_skills 测试 ====================

    def test_search_skills_empty_query(self) -> None:
        """测试空查询搜索。"""
        results = self.learner.search_skills("")
        assert results == []

    def test_search_skills_by_name(self) -> None:
        """测试按名称搜索。"""
        self.learner.learn_tool("kubectl", "kubectl get pods")
        self.learner.learn_tool("docker", "docker ps")
        results = self.learner.search_skills("kube")
        assert len(results) == 1
        assert results[0].name == "kubectl"

    def test_search_skills_by_type(self) -> None:
        """测试按类型过滤搜索。"""
        self.learner.learn_tool("git", "git status")
        self.learner.learn_language("go", "package main")
        results = self.learner.search_skills("g", skill_type=SkillType.LANGUAGE)
        assert all(s.type == SkillType.LANGUAGE for s in results)

    def test_search_skills_limit(self) -> None:
        """测试搜索结果限制。"""
        for i in range(10):
            self.learner.learn_tool(f"tool{i}", f"tool{i} command")
        results = self.learner.search_skills("tool", limit=5)
        assert len(results) <= 5

    # ==================== update_proficiency 测试 ====================

    def test_update_proficiency_increase(self) -> None:
        """测试增加熟练度。"""
        skill = self.learner.learn_tool("ls", "ls -la")
        initial = skill.proficiency
        self.learner.update_proficiency(skill.id, 0.1)
        updated = self.learner.get_skill(skill.id)
        assert updated.proficiency == initial + 0.1

    def test_update_proficiency_decrease(self) -> None:
        """测试降低熟练度。"""
        skill = self.learner.learn_tool("cat", "cat file")
        self.learner.update_proficiency(skill.id, 0.5)  # 先增加
        self.learner.update_proficiency(skill.id, -0.2)  # 再降低
        updated = self.learner.get_skill(skill.id)
        assert updated.proficiency == 0.1 + 0.5 - 0.2

    def test_update_proficiency_verified_skill(self) -> None:
        """测试已验证技能不能降低熟练度。"""
        skill = self.learner.learn_tool("pwd", "pwd")
        self.learner.verify_skill(skill.id)
        result = self.learner.update_proficiency(skill.id, -0.1)
        assert result is False

    def test_update_proficiency_deprecate_low(self) -> None:
        """测试熟练度过低时自动废弃。"""
        skill = self.learner.learn_tool("obsolete", "obsolete cmd")
        self.learner.update_proficiency(skill.id, -0.1)  # 降到0.0
        # 检查是否被废弃
        all_skills = self.learner.get_all_skills(include_deprecated=False)
        assert skill.id not in [s.id for s in all_skills]

    # ==================== record_usage 测试 ====================

    def test_record_usage_success(self) -> None:
        """测试记录成功使用。"""
        skill = self.learner.learn_tool("echo", "echo hello")
        result = self.learner.record_usage(skill.id, success=True)
        assert result is True

    def test_record_usage_failure(self) -> None:
        """测试记录失败使用。"""
        skill = self.learner.learn_tool("rm", "rm -rf")
        result = self.learner.record_usage(skill.id, success=False)
        assert result is True

    def test_record_usage_not_found(self) -> None:
        """测试记录不存在技能的使用。"""
        result = self.learner.record_usage("nonexistent")
        assert result is False

    # ==================== verify_skill 测试 ====================

    def test_verify_skill_success(self) -> None:
        """测试验证技能。"""
        skill = self.learner.learn_tool("cp", "cp src dst")
        result = self.learner.verify_skill(skill.id)
        assert result is True

    def test_verify_skill_not_found(self) -> None:
        """测试验证不存在的技能。"""
        result = self.learner.verify_skill("nonexistent")
        assert result is False

    # ==================== deprecate_skill 测试 ====================

    def test_deprecate_skill_success(self) -> None:
        """测试废弃技能。"""
        skill = self.learner.learn_tool("old_tool", "old_tool cmd")
        result = self.learner.deprecate_skill(skill.id)
        assert result is True

    def test_deprecate_skill_verified(self) -> None:
        """测试不能废弃已验证的技能。"""
        skill = self.learner.learn_tool("verified_tool", "verified cmd")
        self.learner.verify_skill(skill.id)
        result = self.learner.deprecate_skill(skill.id)
        assert result is False

    # ==================== get_recommendations 测试 ====================

    def test_get_recommendations_empty_context(self) -> None:
        """测试空上下文推荐。"""
        results = self.learner.get_recommendations("")
        assert results == []

    def test_get_recommendations_by_name(self) -> None:
        """测试按名称匹配推荐。"""
        self.learner.learn_tool("git", "git status")
        self.learner.learn_tool("svn", "svn status")
        results = self.learner.get_recommendations("使用git提交代码")
        assert len(results) > 0
        assert results[0].name == "git"

    def test_get_recommendations_limit(self) -> None:
        """测试推荐结果限制。"""
        for i in range(10):
            self.learner.learn_tool(f"tool{i}", f"tool{i} cmd")
        results = self.learner.get_recommendations("tool", limit=3)
        assert len(results) <= 3

    # ==================== get_skills_by_type 测试 ====================

    def test_get_skills_by_type(self) -> None:
        """测试按类型获取技能。"""
        self.learner.learn_tool("git", "git")
        self.learner.learn_language("python", "print()")
        tools = self.learner.get_skills_by_type(SkillType.TOOL_USAGE)
        assert all(s.type == SkillType.TOOL_USAGE for s in tools)

    # ==================== get_all_skills 测试 ====================

    def test_get_all_skills(self) -> None:
        """测试获取所有技能。"""
        self.learner.learn_tool("a", "a")
        self.learner.learn_tool("b", "b")
        skills = self.learner.get_all_skills()
        assert len(skills) == 2

    def test_get_all_skills_exclude_deprecated(self) -> None:
        """测试排除已废弃技能。"""
        skill = self.learner.learn_tool("deprecated", "deprecated")
        self.learner.deprecate_skill(skill.id)
        skills = self.learner.get_all_skills(include_deprecated=False)
        assert skill.id not in [s.id for s in skills]

    # ==================== get_skill_count 测试 ====================

    def test_get_skill_count(self) -> None:
        """测试获取技能数量。"""
        self.learner.learn_tool("x", "x")
        self.learner.learn_tool("y", "y")
        assert self.learner.get_skill_count() == 2

    # ==================== clear_all 测试 ====================

    def test_clear_all(self) -> None:
        """测试清除所有技能。"""
        self.learner.learn_tool("test", "test")
        self.learner.clear_all()
        assert self.learner.get_skill_count() == 0

    # ==================== get_statistics 测试 ====================

    def test_get_statistics(self) -> None:
        """测试获取统计信息。"""
        self.learner.learn_tool("t1", "t1")
        self.learner.learn_language("py", "py")
        stats = self.learner.get_statistics()
        assert stats["total_count"] == 2
        assert "type_distribution" in stats
        assert "status_distribution" in stats

    # ==================== register_evaluator 测试 ====================

    def test_register_evaluator(self) -> None:
        """测试注册评估器。"""

        class CustomEvaluator:
            def evaluate(self, skill: Skill) -> float:
                return 0.5

        evaluator = CustomEvaluator()
        self.learner.register_evaluator(evaluator)
        skill = self.learner.learn_tool("test", "test")
        score = self.learner.evaluate_skill(skill.id)
        assert score > 0

    def test_unregister_evaluator(self) -> None:
        """测试取消注册评估器。"""

        class CustomEvaluator:
            def evaluate(self, skill: Skill) -> float:
                return 0.5

        evaluator = CustomEvaluator()
        self.learner.register_evaluator(evaluator)
        result = self.learner.unregister_evaluator(evaluator)
        assert result is True

    # ==================== extract_skills_from_context 测试 ====================

    def test_extract_skills_from_context_tool(self) -> None:
        """测试从上下文提取工具技能。"""
        context = "使用 git 工具进行版本控制"
        skills = self.learner.extract_skills_from_context(context)
        assert len(skills) > 0

    def test_extract_skills_from_context_empty(self) -> None:
        """测试空上下文提取。"""
        skills = self.learner.extract_skills_from_context("")
        assert skills == []


class TestUsageFrequencyEvaluator:
    """UsageFrequencyEvaluator测试。"""

    def test_evaluate_no_usage(self) -> None:
        """测试无使用记录时的评估。"""
        evaluator = UsageFrequencyEvaluator()
        skill = Skill(
            id="test",
            type=SkillType.TOOL_USAGE,
            name="test",
            description="test",
        )
        score = evaluator.evaluate(skill)
        assert score == 0.0

    def test_evaluate_with_usage(self) -> None:
        """测试有使用记录时的评估。"""
        evaluator = UsageFrequencyEvaluator()
        skill = Skill(
            id="test",
            type=SkillType.TOOL_USAGE,
            name="test",
            description="test",
        )
        for _ in range(10):
            evaluator.record_usage(skill.id)
        score = evaluator.evaluate(skill)
        assert score > 0.0


class TestSuccessRateEvaluator:
    """SuccessRateEvaluator测试。"""

    def test_evaluate_no_attempts(self) -> None:
        """测试无尝试记录时的评估。"""
        evaluator = SuccessRateEvaluator()
        skill = Skill(
            id="test",
            type=SkillType.TOOL_USAGE,
            name="test",
            description="test",
        )
        score = evaluator.evaluate(skill)
        assert score == 0.0

    def test_evaluate_all_success(self) -> None:
        """测试全部成功时的评估。"""
        evaluator = SuccessRateEvaluator(min_attempts=5)
        skill = Skill(
            id="test",
            type=SkillType.TOOL_USAGE,
            name="test",
            description="test",
        )
        for _ in range(10):
            evaluator.record_attempt(skill.id, success=True)
        score = evaluator.evaluate(skill)
        assert score == 1.0

    def test_evaluate_partial_success(self) -> None:
        """测试部分成功时的评估。"""
        evaluator = SuccessRateEvaluator(min_attempts=5)
        skill = Skill(
            id="test",
            type=SkillType.TOOL_USAGE,
            name="test",
            description="test",
        )
        for _ in range(5):
            evaluator.record_attempt(skill.id, success=True)
        for _ in range(5):
            evaluator.record_attempt(skill.id, success=False)
        score = evaluator.evaluate(skill)
        assert score == 0.5


class TestRecencyEvaluator:
    """RecencyEvaluator测试。"""

    def test_evaluate_no_usage(self) -> None:
        """测试无使用记录时的评估。"""
        evaluator = RecencyEvaluator()
        skill = Skill(
            id="test",
            type=SkillType.TOOL_USAGE,
            name="test",
            description="test",
        )
        score = evaluator.evaluate(skill)
        assert score == 0.0

    def test_evaluate_recent_usage(self) -> None:
        """测试最近使用时的评估。"""
        evaluator = RecencyEvaluator(decay_days=30)
        skill = Skill(
            id="test",
            type=SkillType.TOOL_USAGE,
            name="test",
            description="test",
        )
        evaluator.record_usage(skill.id)
        score = evaluator.evaluate(skill)
        assert score > 0.9  # 刚使用应该接近1.0
