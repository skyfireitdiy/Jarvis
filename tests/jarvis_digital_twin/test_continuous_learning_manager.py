"""ContinuousLearningManager 测试模块。"""

from jarvis.jarvis_digital_twin.continuous_learning import (
    ContinuousLearningManager,
    KnowledgeAcquirer,
    SkillLearner,
    ExperienceAccumulator,
    AdaptiveEngine,
    KnowledgeType,
    SkillType,
)


class TestContinuousLearningManagerInit:
    """测试 ContinuousLearningManager 初始化。"""

    def test_init_default(self) -> None:
        """测试默认初始化。"""
        manager = ContinuousLearningManager()
        assert manager.enabled is True
        assert manager.knowledge_acquirer is not None
        assert manager.skill_learner is not None
        assert manager.experience_accumulator is not None
        assert manager.adaptive_engine is not None

    def test_init_with_custom_components(self) -> None:
        """测试使用自定义组件初始化。"""
        knowledge_acquirer = KnowledgeAcquirer()
        skill_learner = SkillLearner()
        experience_accumulator = ExperienceAccumulator()
        adaptive_engine = AdaptiveEngine()

        manager = ContinuousLearningManager(
            knowledge_acquirer=knowledge_acquirer,
            skill_learner=skill_learner,
            experience_accumulator=experience_accumulator,
            adaptive_engine=adaptive_engine,
        )

        assert manager.knowledge_acquirer is knowledge_acquirer
        assert manager.skill_learner is skill_learner
        assert manager.experience_accumulator is experience_accumulator
        assert manager.adaptive_engine is adaptive_engine

    def test_enabled_property(self) -> None:
        """测试 enabled 属性。"""
        manager = ContinuousLearningManager()
        assert manager.enabled is True

        manager.enabled = False
        assert manager.enabled is False

        manager.enabled = True
        assert manager.enabled is True


class TestLearnFromInteraction:
    """测试 learn_from_interaction 方法。"""

    def test_learn_from_interaction_basic(self) -> None:
        """测试基本交互学习。"""
        manager = ContinuousLearningManager()
        result = manager.learn_from_interaction(
            user_input="How do I fix this bug?",
            assistant_response="You can fix it by...",
        )

        assert "knowledge_learned" in result
        assert "skills_learned" in result
        assert "experience_recorded" in result
        assert "adaptations_made" in result

    def test_learn_from_interaction_with_tool_call(self) -> None:
        """测试包含工具调用的交互学习。"""
        manager = ContinuousLearningManager()
        result = manager.learn_from_interaction(
            user_input="Read the file",
            assistant_response="<TOOL_CALL>read_file</TOOL_CALL>",
        )

        assert "skills_learned" in result
        # 应该学习到工具使用技能
        assert isinstance(result["skills_learned"], list)

    def test_learn_from_interaction_with_code(self) -> None:
        """测试包含代码的交互学习。"""
        manager = ContinuousLearningManager()
        result = manager.learn_from_interaction(
            user_input="Write a function",
            assistant_response="```python\ndef hello():\n    pass\n```",
        )

        assert "skills_learned" in result

    def test_learn_from_interaction_disabled(self) -> None:
        """测试禁用时的交互学习。"""
        manager = ContinuousLearningManager()
        manager.enabled = False

        result = manager.learn_from_interaction(
            user_input="test",
            assistant_response="response",
        )

        assert result["knowledge_learned"] == []
        assert result["skills_learned"] == []
        assert result["experience_recorded"] is False

    def test_learn_from_interaction_with_context(self) -> None:
        """测试带上下文的交互学习。"""
        manager = ContinuousLearningManager()
        result = manager.learn_from_interaction(
            user_input="Help me",
            assistant_response="Sure!",
            context={"session_id": "test123"},
        )

        assert "experience_recorded" in result


class TestLearnFromTaskResult:
    """测试 learn_from_task_result 方法。"""

    def test_learn_from_task_success(self) -> None:
        """测试成功任务的学习。"""
        manager = ContinuousLearningManager()
        result = manager.learn_from_task_result(
            task="Fix the bug in main.py",
            result="Bug fixed successfully",
            success=True,
        )

        assert "experience_recorded" in result
        assert "methodology_extracted" in result
        assert "adaptations_made" in result

    def test_learn_from_task_failure(self) -> None:
        """测试失败任务的学习。"""
        manager = ContinuousLearningManager()
        result = manager.learn_from_task_result(
            task="Deploy the application",
            result="Deployment failed: connection error",
            success=False,
        )

        assert "experience_recorded" in result
        assert "adaptations_made" in result

    def test_learn_from_task_disabled(self) -> None:
        """测试禁用时的任务学习。"""
        manager = ContinuousLearningManager()
        manager.enabled = False

        result = manager.learn_from_task_result(
            task="test task",
            result="result",
            success=True,
        )

        assert result["experience_recorded"] is False
        assert result["methodology_extracted"] is False


class TestGetRelevantKnowledge:
    """测试 get_relevant_knowledge 方法。"""

    def test_get_relevant_knowledge_basic(self) -> None:
        """测试基本知识检索。"""
        manager = ContinuousLearningManager()
        result = manager.get_relevant_knowledge(context="python programming")

        assert "knowledge" in result
        assert "total_count" in result
        assert isinstance(result["knowledge"], list)

    def test_get_relevant_knowledge_with_type(self) -> None:
        """测试带类型过滤的知识检索。"""
        manager = ContinuousLearningManager()
        result = manager.get_relevant_knowledge(
            context="design patterns",
            knowledge_type=KnowledgeType.PATTERN,
        )

        assert "knowledge" in result

    def test_get_relevant_knowledge_with_limit(self) -> None:
        """测试带数量限制的知识检索。"""
        manager = ContinuousLearningManager()
        result = manager.get_relevant_knowledge(
            context="testing",
            limit=5,
        )

        assert len(result["knowledge"]) <= 5


class TestGetApplicableSkills:
    """测试 get_applicable_skills 方法。"""

    def test_get_applicable_skills_basic(self) -> None:
        """测试基本技能检索。"""
        manager = ContinuousLearningManager()
        result = manager.get_applicable_skills(context="code review")

        assert isinstance(result, list)

    def test_get_applicable_skills_with_type(self) -> None:
        """测试带类型过滤的技能检索。"""
        manager = ContinuousLearningManager()
        result = manager.get_applicable_skills(
            context="python",
            skill_type=SkillType.LANGUAGE,
        )

        assert isinstance(result, list)


class TestGetSimilarExperiences:
    """测试 get_similar_experiences 方法。"""

    def test_get_similar_experiences_basic(self) -> None:
        """测试基本经验检索。"""
        manager = ContinuousLearningManager()
        experiences = manager.get_similar_experiences(context="debugging")

        assert isinstance(experiences, list)

    def test_get_similar_experiences_with_limit(self) -> None:
        """测试带数量限制的经验检索。"""
        manager = ContinuousLearningManager()
        experiences = manager.get_similar_experiences(
            context="deployment",
            limit=3,
        )

        assert len(experiences) <= 3


class TestAdaptBehavior:
    """测试 adapt_behavior 方法。"""

    def test_adapt_behavior_positive(self) -> None:
        """测试正向反馈适应。"""
        manager = ContinuousLearningManager()
        result = manager.adapt_behavior(
            feedback={"type": "positive", "data": {"context": "test"}}
        )

        assert "adapted" in result
        assert "adaptations" in result

    def test_adapt_behavior_negative(self) -> None:
        """测试负向反馈适应。"""
        manager = ContinuousLearningManager()
        result = manager.adapt_behavior(
            feedback={"type": "negative", "data": {"context": "test"}}
        )

        assert "adapted" in result

    def test_adapt_behavior_disabled(self) -> None:
        """测试禁用时的行为适应。"""
        manager = ContinuousLearningManager()
        manager.enabled = False

        result = manager.adapt_behavior(feedback={"type": "positive", "data": {}})

        assert result["adapted"] is False
        assert result["adaptations"] == []


class TestGetLearningStatistics:
    """测试 get_learning_statistics 方法。"""

    def test_get_learning_statistics_initial(self) -> None:
        """测试初始统计信息。"""
        manager = ContinuousLearningManager()
        stats = manager.get_learning_statistics()

        assert stats["enabled"] is True
        assert stats["interaction_count"] == 0
        assert stats["task_count"] == 0
        assert "components" in stats

    def test_get_learning_statistics_after_learning(self) -> None:
        """测试学习后的统计信息。"""
        manager = ContinuousLearningManager()

        # 进行一些学习
        manager.learn_from_interaction("test", "response")
        manager.learn_from_task_result("task", "result", True)

        stats = manager.get_learning_statistics()

        assert stats["interaction_count"] == 1
        assert stats["task_count"] == 1
        assert stats["learning_history_count"] >= 2


class TestExportImportLearnings:
    """测试导出和导入学习成果。"""

    def test_export_learnings(self) -> None:
        """测试导出学习成果。"""
        manager = ContinuousLearningManager()

        # 进行一些学习
        manager.learn_from_interaction("test input", "test response")

        export_data = manager.export_learnings()

        assert "version" in export_data
        assert "exported_at" in export_data
        assert "statistics" in export_data
        assert "knowledge" in export_data
        assert "skills" in export_data
        assert "experiences" in export_data

    def test_import_learnings_valid(self) -> None:
        """测试导入有效的学习成果。"""
        manager = ContinuousLearningManager()

        import_data = {
            "version": "1.0",
            "knowledge": [
                {"type": "concept", "content": "test knowledge", "source": "test"}
            ],
            "skills": [{"type": "tool_usage", "name": "test_tool"}],
            "experiences": [{"type": "success", "context": "test", "outcome": "good"}],
        }

        result = manager.import_learnings(import_data)
        assert result is True

    def test_import_learnings_invalid(self) -> None:
        """测试导入无效的学习成果。"""
        manager = ContinuousLearningManager()

        # 缺少 version
        result = manager.import_learnings({"knowledge": []})
        assert result is False

        # 空数据
        result = manager.import_learnings({})
        assert result is False

    def test_export_import_roundtrip(self) -> None:
        """测试导出-导入往返。"""
        manager1 = ContinuousLearningManager()

        # 进行一些学习
        manager1.learn_from_interaction("hello", "world")
        manager1.learn_from_task_result("task1", "done", True)

        # 导出
        export_data = manager1.export_learnings()

        # 导入到新管理器
        manager2 = ContinuousLearningManager()
        result = manager2.import_learnings(export_data)

        assert result is True


class TestCategorizeInput:
    """测试输入分类。"""

    def test_categorize_bug_fix(self) -> None:
        """测试 bug 修复分类。"""
        manager = ContinuousLearningManager()
        assert manager._categorize_input("fix this bug") == "bug_fix"
        assert manager._categorize_input("there is an error") == "bug_fix"

    def test_categorize_feature_request(self) -> None:
        """测试功能请求分类。"""
        manager = ContinuousLearningManager()
        assert manager._categorize_input("add a new feature") == "feature_request"
        assert manager._categorize_input("create a function") == "feature_request"

    def test_categorize_refactoring(self) -> None:
        """测试重构分类。"""
        manager = ContinuousLearningManager()
        assert manager._categorize_input("refactor this code") == "refactoring"
        assert manager._categorize_input("optimize performance") == "refactoring"

    def test_categorize_question(self) -> None:
        """测试问题分类。"""
        manager = ContinuousLearningManager()
        assert manager._categorize_input("explain this") == "question"
        assert manager._categorize_input("what is this?") == "question"

    def test_categorize_testing(self) -> None:
        """测试测试分类。"""
        manager = ContinuousLearningManager()
        assert manager._categorize_input("test this function") == "testing"
        assert manager._categorize_input("verify the output") == "testing"

    def test_categorize_general(self) -> None:
        """测试通用分类。"""
        manager = ContinuousLearningManager()
        assert manager._categorize_input("hello world") == "general"
        assert manager._categorize_input("random text") == "general"
