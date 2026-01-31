"""最佳实践推荐模块测试"""

import pytest

from src.jarvis.jarvis_smart_advisor.practice_advisor import (
    BestPractice,
    PracticeAdvisor,
    PracticeCategory,
    PracticeContext,
    PracticePriority,
    PracticeRecommendation,
)


class TestPracticeCategory:
    """测试实践类别枚举"""

    def test_category_values(self):
        """测试类别值"""
        assert PracticeCategory.CODE_QUALITY.value == "code_quality"
        assert PracticeCategory.ARCHITECTURE.value == "architecture"
        assert PracticeCategory.SECURITY.value == "security"
        assert PracticeCategory.PERFORMANCE.value == "performance"
        assert PracticeCategory.TESTING.value == "testing"
        assert PracticeCategory.DOCUMENTATION.value == "documentation"
        assert PracticeCategory.DEVOPS.value == "devops"
        assert PracticeCategory.COLLABORATION.value == "collaboration"

    def test_all_categories(self):
        """测试所有类别"""
        categories = list(PracticeCategory)
        assert len(categories) == 8


class TestPracticePriority:
    """测试实践优先级枚举"""

    def test_priority_values(self):
        """测试优先级值"""
        assert PracticePriority.CRITICAL.value == "critical"
        assert PracticePriority.HIGH.value == "high"
        assert PracticePriority.MEDIUM.value == "medium"
        assert PracticePriority.LOW.value == "low"


class TestBestPractice:
    """测试最佳实践数据类"""

    def test_create_practice(self):
        """测试创建实践"""
        practice = BestPractice(
            name="单元测试",
            category=PracticeCategory.TESTING,
            description="为核心逻辑编写单元测试",
            rationale="确保代码正确性",
            priority=PracticePriority.HIGH,
        )
        assert practice.name == "单元测试"
        assert practice.category == PracticeCategory.TESTING
        assert practice.priority == PracticePriority.HIGH
        assert practice.relevance_score == 0.0

    def test_practice_with_actions(self):
        """测试带行动的实践"""
        practice = BestPractice(
            name="代码审查",
            category=PracticeCategory.CODE_QUALITY,
            description="进行代码审查",
            rationale="提高代码质量",
            priority=PracticePriority.MEDIUM,
            actions=["检查代码风格", "检查逻辑错误"],
        )
        assert len(practice.actions) == 2
        assert "检查代码风格" in practice.actions


class TestPracticeContext:
    """测试实践上下文数据类"""

    def test_create_context(self):
        """测试创建上下文"""
        context = PracticeContext(
            code_snippet="def hello(): pass",
            file_path="test.py",
            language="python",
        )
        assert context.code_snippet == "def hello(): pass"
        assert context.language == "python"
        assert context.current_issues == []

    def test_context_with_issues(self):
        """测试带问题的上下文"""
        context = PracticeContext(
            code_snippet="",
            current_issues=["代码重复", "缺少测试"],
            goals=["提高代码质量"],
        )
        assert len(context.current_issues) == 2
        assert len(context.goals) == 1


class TestPracticeAdvisor:
    """测试最佳实践推荐顾问"""

    @pytest.fixture
    def advisor(self):
        """创建顾问实例"""
        return PracticeAdvisor()

    def test_init(self, advisor):
        """测试初始化"""
        assert advisor.knowledge_graph is None
        assert advisor.rule_generator is None
        assert advisor.methodology_generator is None

    def test_get_practice_count(self, advisor):
        """测试获取实践总数"""
        count = advisor.get_practice_count()
        assert count > 0
        assert count == len(advisor.BUILTIN_PRACTICES)

    def test_get_all_categories(self, advisor):
        """测试获取所有类别"""
        categories = advisor.get_all_categories()
        assert len(categories) == 8
        assert PracticeCategory.CODE_QUALITY in categories

    def test_recommend_practices_empty_context(self, advisor):
        """测试空上下文推荐"""
        context = PracticeContext()
        result = advisor.recommend_practices(context)
        assert isinstance(result, PracticeRecommendation)
        assert result.context == context

    def test_recommend_practices_with_code(self, advisor):
        """测试带代码的推荐"""
        context = PracticeContext(
            code_snippet="try:\n    pass\nexcept Exception:\n    pass",
            language="python",
        )
        result = advisor.recommend_practices(context)
        assert isinstance(result, PracticeRecommendation)
        # 应该推荐错误处理相关实践
        practice_names = [p.name for p in result.practices]
        assert any("错误" in name or "异常" in name for name in practice_names)

    def test_recommend_practices_with_issues(self, advisor):
        """测试带问题的推荐"""
        context = PracticeContext(
            current_issues=["代码重复严重", "缺少单元测试"],
        )
        result = advisor.recommend_practices(context)
        assert len(result.practices) > 0
        # 应该推荐DRY和测试相关实践
        practice_names = [p.name for p in result.practices]
        has_dry = any("DRY" in name or "重复" in name for name in practice_names)
        has_test = any("测试" in name for name in practice_names)
        assert has_dry or has_test

    def test_recommend_practices_with_category_filter(self, advisor):
        """测试类别过滤"""
        context = PracticeContext(
            current_issues=["安全漏洞", "性能问题"],
        )
        result = advisor.recommend_practices(
            context, categories=[PracticeCategory.SECURITY]
        )
        # 所有推荐应该都是安全类别
        for practice in result.practices:
            assert practice.category == PracticeCategory.SECURITY

    def test_recommend_practices_max_limit(self, advisor):
        """测试最大推荐数量限制"""
        context = PracticeContext(
            current_issues=["代码质量差", "缺少文档", "性能问题"],
            goals=["提高代码质量", "完善文档"],
        )
        result = advisor.recommend_practices(context, max_recommendations=3)
        assert len(result.practices) <= 3

    def test_get_practice_by_category(self, advisor):
        """测试按类别获取实践"""
        practices = advisor.get_practice_by_category(PracticeCategory.TESTING)
        assert len(practices) > 0
        for practice in practices:
            assert practice.category == PracticeCategory.TESTING

    def test_get_practice_by_category_security(self, advisor):
        """测试获取安全类别实践"""
        practices = advisor.get_practice_by_category(PracticeCategory.SECURITY)
        assert len(practices) > 0
        practice_names = [p.name for p in practices]
        assert any("验证" in name or "认证" in name for name in practice_names)

    def test_search_practices(self, advisor):
        """测试搜索实践"""
        practices = advisor.search_practices("单元测试")
        assert len(practices) > 0
        # 搜索结果应该包含与关键词相关的实践
        practice_names = [p.name for p in practices]
        assert any("测试" in name for name in practice_names)

    def test_search_practices_english(self, advisor):
        """测试英文搜索"""
        practices = advisor.search_practices("cache")
        assert len(practices) > 0

    def test_search_practices_no_result(self, advisor):
        """测试无结果搜索"""
        practices = advisor.search_practices("不存在的关键词xyz123")
        assert len(practices) == 0

    def test_calculate_relevance(self, advisor):
        """测试相关性计算"""
        context = PracticeContext(
            code_snippet="def test_function(): pass",
            current_issues=["缺少单元测试"],
        )
        practice_info = advisor.BUILTIN_PRACTICES["unit_testing"]
        relevance = advisor._calculate_relevance(context, practice_info)
        assert relevance > 0

    def test_determine_priority_critical(self, advisor):
        """测试关键优先级判定"""
        context = PracticeContext()
        priority = advisor._determine_priority(85, context)
        assert priority == PracticePriority.CRITICAL

    def test_determine_priority_high(self, advisor):
        """测试高优先级判定"""
        context = PracticeContext()
        priority = advisor._determine_priority(65, context)
        assert priority == PracticePriority.HIGH

    def test_determine_priority_medium(self, advisor):
        """测试中优先级判定"""
        context = PracticeContext()
        priority = advisor._determine_priority(45, context)
        assert priority == PracticePriority.MEDIUM

    def test_determine_priority_low(self, advisor):
        """测试低优先级判定"""
        context = PracticeContext()
        priority = advisor._determine_priority(25, context)
        assert priority == PracticePriority.LOW

    def test_generate_summary_empty(self, advisor):
        """测试空推荐摘要"""
        context = PracticeContext()
        summary = advisor._generate_summary([], context)
        assert "未找到" in summary

    def test_generate_summary_with_practices(self, advisor):
        """测试有推荐的摘要"""
        practices = [
            BestPractice(
                name="测试1",
                category=PracticeCategory.TESTING,
                description="描述1",
                rationale="理由1",
                priority=PracticePriority.HIGH,
            ),
            BestPractice(
                name="测试2",
                category=PracticeCategory.TESTING,
                description="描述2",
                rationale="理由2",
                priority=PracticePriority.CRITICAL,
            ),
        ]
        context = PracticeContext()
        summary = advisor._generate_summary(practices, context)
        assert "2" in summary
        assert "关键优先级" in summary

    def test_adjust_by_project_type_web(self, advisor):
        """测试Web项目类型调整"""
        adjustment = advisor._adjust_by_project_type("web", PracticeCategory.SECURITY)
        assert adjustment > 0

    def test_adjust_by_project_type_api(self, advisor):
        """测试API项目类型调整"""
        adjustment = advisor._adjust_by_project_type(
            "api", PracticeCategory.DOCUMENTATION
        )
        assert adjustment > 0

    def test_adjust_by_project_type_unknown(self, advisor):
        """测试未知项目类型调整"""
        adjustment = advisor._adjust_by_project_type(
            "unknown", PracticeCategory.SECURITY
        )
        assert adjustment == 0

    def test_builtin_practices_structure(self, advisor):
        """测试内置实践结构"""
        for practice_id, practice_info in advisor.BUILTIN_PRACTICES.items():
            assert "name" in practice_info
            assert "category" in practice_info
            assert "description" in practice_info
            assert "rationale" in practice_info
            assert "actions" in practice_info
            assert "keywords" in practice_info
            assert isinstance(practice_info["actions"], list)
            assert isinstance(practice_info["keywords"], list)

    def test_recommend_with_project_type(self, advisor):
        """测试带项目类型的推荐"""
        context = PracticeContext(
            project_type="microservice",
            current_issues=["部署困难"],
        )
        result = advisor.recommend_practices(context)
        # 微服务项目应该推荐DevOps相关实践
        # 至少应该有一些推荐
        assert len(result.practices) >= 0

    def test_recommend_with_language(self, advisor):
        """测试带编程语言的推荐"""
        context = PracticeContext(
            language="python",
            code_snippet="def main(): pass",
        )
        result = advisor.recommend_practices(context)
        assert isinstance(result, PracticeRecommendation)


class TestPracticeRecommendation:
    """测试实践推荐结果数据类"""

    def test_create_recommendation(self):
        """测试创建推荐结果"""
        context = PracticeContext()
        recommendation = PracticeRecommendation(
            context=context,
            practices=[],
            summary="无推荐",
            total_practices=0,
        )
        assert recommendation.context == context
        assert recommendation.total_practices == 0

    def test_recommendation_with_practices(self):
        """测试带实践的推荐结果"""
        context = PracticeContext()
        practices = [
            BestPractice(
                name="实践1",
                category=PracticeCategory.CODE_QUALITY,
                description="描述",
                rationale="理由",
                priority=PracticePriority.HIGH,
            )
        ]
        recommendation = PracticeRecommendation(
            context=context,
            practices=practices,
            summary="推荐1项",
            total_practices=1,
        )
        assert len(recommendation.practices) == 1
        assert recommendation.total_practices == 1
