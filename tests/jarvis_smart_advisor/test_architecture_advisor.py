"""架构决策辅助模块测试。"""

from jarvis.jarvis_smart_advisor.architecture_advisor import (
    ArchitectureAdvisor,
    ArchitectureDecision,
    ArchitectureOption,
    DecisionImpact,
    DecisionType,
)


class TestDecisionType:
    """DecisionType枚举测试"""

    def test_decision_type_values(self):
        """测试决策类型值"""
        assert DecisionType.TECHNOLOGY_CHOICE.value == "technology_choice"
        assert DecisionType.ARCHITECTURE_PATTERN.value == "architecture_pattern"
        assert DecisionType.MODULE_DESIGN.value == "module_design"
        assert DecisionType.API_DESIGN.value == "api_design"
        assert DecisionType.DATA_MODEL.value == "data_model"
        assert DecisionType.DEPENDENCY_MANAGEMENT.value == "dependency_management"


class TestDecisionImpact:
    """DecisionImpact枚举测试"""

    def test_impact_values(self):
        """测试影响程度值"""
        assert DecisionImpact.HIGH.value == "high"
        assert DecisionImpact.MEDIUM.value == "medium"
        assert DecisionImpact.LOW.value == "low"


class TestArchitectureOption:
    """ArchitectureOption数据类测试"""

    def test_create_option(self):
        """测试创建选项"""
        option = ArchitectureOption(
            name="测试选项",
            description="这是一个测试选项",
            pros=["优点1", "优点2"],
            cons=["缺点1"],
            score=80.0,
        )
        assert option.name == "测试选项"
        assert option.description == "这是一个测试选项"
        assert len(option.pros) == 2
        assert len(option.cons) == 1
        assert option.score == 80.0

    def test_option_to_dict(self):
        """测试转换为字典"""
        option = ArchitectureOption(
            name="测试",
            description="描述",
            pros=["优点"],
            cons=["缺点"],
            use_cases=["场景"],
            score=75.0,
        )
        result = option.to_dict()
        assert result["name"] == "测试"
        assert result["score"] == 75.0
        assert "优点" in result["pros"]


class TestArchitectureDecision:
    """ArchitectureDecision数据类测试"""

    def test_create_decision(self):
        """测试创建决策"""
        decision = ArchitectureDecision(
            question="应该选择什么架构模式？",
            decision_type=DecisionType.ARCHITECTURE_PATTERN,
            impact=DecisionImpact.HIGH,
        )
        assert decision.question == "应该选择什么架构模式？"
        assert decision.decision_type == DecisionType.ARCHITECTURE_PATTERN
        assert decision.impact == DecisionImpact.HIGH

    def test_decision_to_dict(self):
        """测试转换为字典"""
        option = ArchitectureOption(
            name="分层架构",
            description="分层设计",
            score=80.0,
        )
        decision = ArchitectureDecision(
            question="选择架构",
            decision_type=DecisionType.ARCHITECTURE_PATTERN,
            impact=DecisionImpact.MEDIUM,
            options=[option],
            recommendation=option,
        )
        result = decision.to_dict()
        assert result["question"] == "选择架构"
        assert result["decision_type"] == "architecture_pattern"
        assert result["impact"] == "medium"
        assert len(result["options"]) == 1
        assert result["recommendation"] is not None

    def test_decision_to_markdown(self):
        """测试转换为Markdown"""
        option = ArchitectureOption(
            name="微服务架构",
            description="将应用拆分为多个服务",
            pros=["独立部署", "技术栈灵活"],
            cons=["运维复杂"],
            use_cases=["大型系统"],
            score=85.0,
        )
        decision = ArchitectureDecision(
            question="如何设计系统架构？",
            decision_type=DecisionType.ARCHITECTURE_PATTERN,
            impact=DecisionImpact.HIGH,
            context="需要支持高并发",
            options=[option],
            recommendation=option,
            rationale="推荐使用微服务架构",
        )
        markdown = decision.to_markdown()
        assert "# 架构决策" in markdown
        assert "微服务架构" in markdown
        assert "独立部署" in markdown
        assert "运维复杂" in markdown


class TestArchitectureAdvisor:
    """ArchitectureAdvisor类测试"""

    def test_init(self):
        """测试初始化"""
        advisor = ArchitectureAdvisor()
        assert advisor.project_dir.exists()

    def test_get_architecture_options_pattern(self):
        """测试获取架构模式选项"""
        advisor = ArchitectureAdvisor()
        options = advisor.get_architecture_options(
            DecisionType.ARCHITECTURE_PATTERN, "需要一个简单的Web应用架构"
        )
        assert len(options) > 0
        # 应该包含分层架构
        names = [o.name for o in options]
        assert "分层架构" in names

    def test_get_architecture_options_technology(self):
        """测试获取技术选型选项"""
        advisor = ArchitectureAdvisor()
        options = advisor.get_architecture_options(
            DecisionType.TECHNOLOGY_CHOICE, "需要选择一个数据库"
        )
        assert len(options) > 0
        # 应该包含数据库选项
        names = [o.name for o in options]
        assert any(
            "SQL" in name or "Mongo" in name or "Redis" in name for name in names
        )

    def test_analyze_decision_architecture(self):
        """测试分析架构决策"""
        advisor = ArchitectureAdvisor()
        decision = advisor.analyze_decision(
            "应该选择什么架构模式？",
            "这是一个需要高扩展性的分布式系统",
        )
        assert decision.question == "应该选择什么架构模式？"
        assert decision.decision_type == DecisionType.ARCHITECTURE_PATTERN
        assert len(decision.options) > 0
        assert decision.recommendation is not None

    def test_analyze_decision_technology(self):
        """测试分析技术选型决策"""
        advisor = ArchitectureAdvisor()
        decision = advisor.analyze_decision(
            "应该选择什么数据库？",
            "需要支持复杂查询和事务",
        )
        assert decision.decision_type == DecisionType.TECHNOLOGY_CHOICE
        assert len(decision.options) > 0

    def test_identify_decision_type(self):
        """测试识别决策类型"""
        advisor = ArchitectureAdvisor()

        # 架构模式
        dt = advisor._identify_decision_type("应该选择什么架构模式？")
        assert dt == DecisionType.ARCHITECTURE_PATTERN

        # 技术选型
        dt = advisor._identify_decision_type("应该选择什么数据库？")
        assert dt == DecisionType.TECHNOLOGY_CHOICE

        # API设计
        dt = advisor._identify_decision_type("如何设计API接口？")
        assert dt == DecisionType.API_DESIGN

        # 模块设计
        dt = advisor._identify_decision_type("如何拆分模块？")
        assert dt == DecisionType.MODULE_DESIGN

    def test_assess_impact(self):
        """测试评估影响程度"""
        advisor = ArchitectureAdvisor()

        # 高影响
        impact = advisor._assess_impact("核心架构重构", "")
        assert impact == DecisionImpact.HIGH

        # 低影响
        impact = advisor._assess_impact("小的局部调整", "临时方案")
        assert impact == DecisionImpact.LOW

        # 中等影响
        impact = advisor._assess_impact("普通功能开发", "")
        assert impact == DecisionImpact.MEDIUM

    def test_calculate_pattern_score(self):
        """测试计算架构模式评分"""
        advisor = ArchitectureAdvisor()

        # 分层架构在简单场景下应该得分较高
        score = advisor._calculate_pattern_score("layered", "简单的Web应用")
        assert score > 50

        # 微服务在分布式场景下应该得分较高
        score = advisor._calculate_pattern_score("microservices", "分布式系统")
        assert score > 50

    def test_calculate_tech_score(self):
        """测试计算技术选型评分"""
        advisor = ArchitectureAdvisor()

        # PostgreSQL在复杂查询场景下应该得分较高
        score = advisor._calculate_tech_score("postgresql", "复杂查询")
        assert score > 50

        # Redis在缓存场景下应该得分较高
        score = advisor._calculate_tech_score("redis", "缓存")
        assert score > 50

    def test_detect_technology_category(self):
        """测试检测技术类别"""
        advisor = ArchitectureAdvisor()

        # 数据库
        category = advisor._detect_technology_category("需要选择数据库")
        assert category == "database"

        # Web框架
        category = advisor._detect_technology_category("需要选择Web框架")
        assert category == "web_framework"

        # 未知类别
        category = advisor._detect_technology_category("其他内容")
        assert category is None

    def test_generate_rationale(self):
        """测试生成推荐理由"""
        advisor = ArchitectureAdvisor()
        option = ArchitectureOption(
            name="测试选项",
            description="描述",
            pros=["优点1", "优点2"],
            cons=["缺点1"],
            use_cases=["场景1"],
            score=80.0,
        )
        rationale = advisor._generate_rationale(option, "")
        assert "测试选项" in rationale
        assert "优点1" in rationale
        assert "场景1" in rationale


class TestArchitectureAdvisorPatterns:
    """ArchitectureAdvisor架构模式测试"""

    def test_all_patterns_available(self):
        """测试所有架构模式可用"""
        advisor = ArchitectureAdvisor()
        options = advisor.get_architecture_options(
            DecisionType.ARCHITECTURE_PATTERN, ""
        )
        names = [o.name for o in options]
        assert "分层架构" in names
        assert "微服务架构" in names
        assert "事件驱动架构" in names
        assert "整洁架构" in names
        assert "六边形架构" in names

    def test_pattern_has_pros_and_cons(self):
        """测试架构模式有优缺点"""
        advisor = ArchitectureAdvisor()
        options = advisor.get_architecture_options(
            DecisionType.ARCHITECTURE_PATTERN, ""
        )
        for option in options:
            assert len(option.pros) > 0, f"{option.name} 缺少优点"
            assert len(option.cons) > 0, f"{option.name} 缺少缺点"
            assert len(option.use_cases) > 0, f"{option.name} 缺少适用场景"


class TestArchitectureAdvisorTechnology:
    """ArchitectureAdvisor技术选型测试"""

    def test_database_options(self):
        """测试数据库选项"""
        advisor = ArchitectureAdvisor()
        options = advisor.get_architecture_options(
            DecisionType.TECHNOLOGY_CHOICE, "数据库"
        )
        names = [o.name for o in options]
        assert "PostgreSQL" in names
        assert "MySQL" in names
        assert "MongoDB" in names
        assert "Redis" in names

    def test_web_framework_options(self):
        """测试Web框架选项"""
        advisor = ArchitectureAdvisor()
        options = advisor.get_architecture_options(
            DecisionType.TECHNOLOGY_CHOICE, "Web框架"
        )
        names = [o.name for o in options]
        assert "FastAPI" in names
        assert "Django" in names
        assert "Flask" in names
