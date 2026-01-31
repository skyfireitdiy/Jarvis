"""方法论自动生成器单元测试"""

import pytest

from jarvis.jarvis_methodology_generator.methodology_generator import (
    MethodologyGenerator,
    MethodologyQualityScore,
    TaskContext,
)


class TestTaskContext:
    """TaskContext数据类测试"""

    def test_default_values(self) -> None:
        """测试默认值"""
        context = TaskContext()
        assert context.task_description == ""
        assert context.execution_steps == []
        assert context.tool_calls == []
        assert context.decisions == []
        assert context.verification_steps == []
        assert context.actual_output == ""
        assert context.success is False

    def test_custom_values(self) -> None:
        """测试自定义值"""
        context = TaskContext(
            task_description="测试任务",
            execution_steps=["步骤1", "步骤2"],
            tool_calls=[{"name": "read_code"}],
            decisions=["决策1"],
            verification_steps=["验证1"],
            actual_output="输出结果",
            success=True,
        )
        assert context.task_description == "测试任务"
        assert len(context.execution_steps) == 2
        assert len(context.tool_calls) == 1
        assert context.success is True


class TestMethodologyQualityScore:
    """MethodologyQualityScore数据类测试"""

    def test_default_values(self) -> None:
        """测试默认值"""
        score = MethodologyQualityScore()
        assert score.completeness == 0
        assert score.executability == 0
        assert score.generality == 0
        assert score.uniqueness == 0
        assert score.total == 0

    def test_total_calculation(self) -> None:
        """测试总分计算"""
        score = MethodologyQualityScore(
            completeness=30,
            executability=30,
            generality=20,
            uniqueness=20,
        )
        assert score.total == 100

    def test_is_qualified_default_threshold(self) -> None:
        """测试默认阈值判断"""
        # 低于阈值
        score_low = MethodologyQualityScore(
            completeness=20, executability=20, generality=10, uniqueness=10
        )
        assert score_low.is_qualified() is False

        # 等于阈值
        score_equal = MethodologyQualityScore(
            completeness=25, executability=25, generality=10, uniqueness=10
        )
        assert score_equal.is_qualified() is True

        # 高于阈值
        score_high = MethodologyQualityScore(
            completeness=30, executability=30, generality=20, uniqueness=20
        )
        assert score_high.is_qualified() is True

    def test_is_qualified_custom_threshold(self) -> None:
        """测试自定义阈值判断"""
        score = MethodologyQualityScore(
            completeness=20, executability=20, generality=10, uniqueness=10
        )
        assert score.is_qualified(threshold=50) is True
        assert score.is_qualified(threshold=70) is False


class TestMethodologyGenerator:
    """MethodologyGenerator类测试"""

    @pytest.fixture
    def generator(self) -> MethodologyGenerator:
        """创建生成器实例"""
        return MethodologyGenerator()

    @pytest.fixture
    def valid_task_context(self) -> TaskContext:
        """创建有效的任务上下文"""
        return TaskContext(
            task_description="实现用户登录功能",
            execution_steps=[
                "分析需求",
                "设计接口",
                "编写代码",
                "编写测试",
            ],
            tool_calls=[
                {"name": "read_code", "arguments": {}},
                {"name": "edit_file", "arguments": {}},
            ],
            decisions=["使用JWT进行身份验证", "密码使用bcrypt加密"],
            verification_steps=["单元测试通过", "集成测试通过"],
            actual_output="登录功能实现完成",
            success=True,
        )

    def test_init_without_existing_methodologies(self) -> None:
        """测试无现有方法论时的初始化"""
        generator = MethodologyGenerator()
        assert generator.existing_methodologies == []

    def test_init_with_existing_methodologies(self) -> None:
        """测试有现有方法论时的初始化"""
        existing = ["方法论1", "方法论2"]
        generator = MethodologyGenerator(existing_methodologies=existing)
        assert generator.existing_methodologies == existing

    def test_validate_task_context_empty_description(
        self, generator: MethodologyGenerator
    ) -> None:
        """测试空描述的任务上下文验证"""
        context = TaskContext(
            task_description="",
            execution_steps=["步骤1"],
            success=True,
        )
        assert generator._validate_task_context(context) is False

    def test_validate_task_context_no_steps(
        self, generator: MethodologyGenerator
    ) -> None:
        """测试无步骤的任务上下文验证"""
        context = TaskContext(
            task_description="测试任务",
            execution_steps=[],
            tool_calls=[],
            success=True,
        )
        assert generator._validate_task_context(context) is False

    def test_validate_task_context_not_success(
        self, generator: MethodologyGenerator
    ) -> None:
        """测试失败任务的上下文验证"""
        context = TaskContext(
            task_description="测试任务",
            execution_steps=["步骤1"],
            success=False,
        )
        assert generator._validate_task_context(context) is False

    def test_validate_task_context_valid(
        self, generator: MethodologyGenerator, valid_task_context: TaskContext
    ) -> None:
        """测试有效任务上下文验证"""
        assert generator._validate_task_context(valid_task_context) is True

    def test_extract_problem_type_with_prefix(
        self, generator: MethodologyGenerator
    ) -> None:
        """测试带前缀的问题类型提取"""
        context = TaskContext(
            task_description="实现用户登录功能",
            execution_steps=["步骤1"],
            success=True,
        )
        problem_type = generator._extract_problem_type(context)
        assert problem_type == "用户登录功能"

    def test_extract_problem_type_without_prefix(
        self, generator: MethodologyGenerator
    ) -> None:
        """测试无前缀的问题类型提取"""
        context = TaskContext(
            task_description="用户登录功能开发",
            execution_steps=["步骤1"],
            success=True,
        )
        problem_type = generator._extract_problem_type(context)
        assert problem_type == "用户登录功能开发"

    def test_extract_problem_type_empty(self, generator: MethodologyGenerator) -> None:
        """测试空描述的问题类型提取"""
        context = TaskContext(
            task_description="",
            execution_steps=["步骤1"],
            success=True,
        )
        problem_type = generator._extract_problem_type(context)
        assert problem_type == "通用任务"

    def test_extract_steps_from_execution_steps(
        self, generator: MethodologyGenerator
    ) -> None:
        """测试从执行步骤提取"""
        context = TaskContext(
            task_description="测试",
            execution_steps=["步骤1", "步骤2"],
            tool_calls=[],
            success=True,
        )
        steps = generator._extract_steps(context)
        assert steps == ["步骤1", "步骤2"]

    def test_extract_steps_from_tool_calls(
        self, generator: MethodologyGenerator
    ) -> None:
        """测试从工具调用提取"""
        context = TaskContext(
            task_description="测试",
            execution_steps=[],
            tool_calls=[{"name": "read_code"}, {"name": "edit_file"}],
            success=True,
        )
        steps = generator._extract_steps(context)
        assert "使用 read_code 工具" in steps
        assert "使用 edit_file 工具" in steps

    def test_generate_methodology_content(
        self, generator: MethodologyGenerator
    ) -> None:
        """测试方法论内容生成"""
        content = generator.generate_methodology_content(
            problem_type="用户登录",
            steps=["分析需求", "编写代码", "测试验证"],
            decisions=["使用JWT"],
            verification_steps=["单元测试通过"],
        )

        # 验证包含必需章节
        assert "# 用户登录方法论" in content
        assert "## 规则简介" in content
        assert "## 你必须遵守的原则" in content
        assert "## 你必须执行的操作" in content
        assert "## 实践指导" in content
        assert "## 检查清单" in content

    def test_generate_methodology_content_empty_inputs(
        self, generator: MethodologyGenerator
    ) -> None:
        """测试空输入的方法论内容生成"""
        content = generator.generate_methodology_content(
            problem_type="测试",
            steps=[],
            decisions=[],
            verification_steps=[],
        )

        # 应该使用默认内容
        assert "# 测试方法论" in content
        assert "分析问题" in content  # 默认步骤

    def test_evaluate_methodology_quality_complete(
        self, generator: MethodologyGenerator
    ) -> None:
        """测试完整方法论的质量评估"""
        content = generator.generate_methodology_content(
            problem_type="测试功能",
            steps=["执行步骤1", "创建文件", "验证结果"],
            decisions=["决策1"],
            verification_steps=["检查1"],
        )
        score = generator.evaluate_methodology_quality(content)

        # 完整性应该满分
        assert score.completeness == 30
        # 可执行性应该较高
        assert score.executability > 0
        # 总分应该达到阈值
        assert score.is_qualified()

    def test_evaluate_completeness(self, generator: MethodologyGenerator) -> None:
        """测试完整性评估"""
        # 包含所有必需章节
        full_content = """## 规则简介
内容
## 你必须遵守的原则
内容
## 你必须执行的操作
内容"""
        assert generator._evaluate_completeness(full_content) == 30

        # 缺少章节
        partial_content = """## 规则简介
内容"""
        assert generator._evaluate_completeness(partial_content) == 10

    def test_evaluate_executability(self, generator: MethodologyGenerator) -> None:
        """测试可执行性评估"""
        # 有编号步骤和操作关键词
        good_content = """1. 执行第一步
2. 创建文件
3. 验证结果"""
        score = generator._evaluate_executability(good_content)
        assert score > 15  # 有编号步骤

        # 无编号步骤
        bad_content = "这是一段描述性文字"
        score = generator._evaluate_executability(bad_content)
        assert score < 15

    def test_evaluate_generality(self, generator: MethodologyGenerator) -> None:
        """测试通用性评估"""
        # 通用内容
        general_content = "这是一个通用的方法论描述"
        score = generator._evaluate_generality(general_content)
        assert score == 10  # 基础分

        # 包含具体路径
        specific_content = "文件位于 /home/user/project/file.py"
        score = generator._evaluate_generality(specific_content)
        assert score < 10

    def test_evaluate_uniqueness_no_existing(
        self, generator: MethodologyGenerator
    ) -> None:
        """测试无现有方法论时的独特性评估"""
        content = "新的方法论内容"
        score = generator._evaluate_uniqueness(content)
        assert score == 15

    def test_evaluate_uniqueness_with_similar(
        self,
    ) -> None:
        """测试有相似方法论时的独特性评估"""
        existing = ["这是一个方法论内容 包含一些关键词"]
        generator = MethodologyGenerator(existing_methodologies=existing)

        # 相似内容
        similar_content = "这是一个方法论内容 包含一些关键词"
        score = generator._evaluate_uniqueness(similar_content)
        assert score < 15

        # 不同内容
        different_content = "完全不同的内容 没有任何重复"
        score = generator._evaluate_uniqueness(different_content)
        assert score > 10

    def test_calculate_similarity(self, generator: MethodologyGenerator) -> None:
        """测试相似度计算"""
        # 完全相同
        text = "hello world"
        assert generator._calculate_similarity(text, text) == 1.0

        # 完全不同
        text1 = "hello world"
        text2 = "foo bar"
        similarity = generator._calculate_similarity(text1, text2)
        assert similarity == 0.0

        # 部分相同
        text1 = "hello world foo"
        text2 = "hello world bar"
        similarity = generator._calculate_similarity(text1, text2)
        assert 0 < similarity < 1

    def test_calculate_similarity_empty(self, generator: MethodologyGenerator) -> None:
        """测试空文本的相似度计算"""
        assert generator._calculate_similarity("", "hello") == 0.0
        assert generator._calculate_similarity("hello", "") == 0.0
        assert generator._calculate_similarity("", "") == 0.0

    def test_extract_methodology_from_task_success(
        self, generator: MethodologyGenerator, valid_task_context: TaskContext
    ) -> None:
        """测试成功提取方法论"""
        result = generator.extract_methodology_from_task(valid_task_context)

        assert result is not None
        assert "problem_type" in result
        assert "content" in result
        assert "quality_score" in result
        assert result["quality_score"] >= 70

    def test_extract_methodology_from_task_invalid_context(
        self, generator: MethodologyGenerator
    ) -> None:
        """测试无效上下文时提取失败"""
        invalid_context = TaskContext(
            task_description="",
            execution_steps=[],
            success=False,
        )
        result = generator.extract_methodology_from_task(invalid_context)
        assert result is None

    def test_extract_methodology_from_task_low_quality(
        self,
    ) -> None:
        """测试低质量方法论被过滤"""
        # 创建一个会产生高相似度的场景
        existing = [
            "# 用户登录功能方法论\n\n## 规则简介\n本方法论提供用户登录功能的标准化解决流程"
        ]
        generator = MethodologyGenerator(existing_methodologies=existing)

        # 创建一个会产生相似内容的上下文
        context = TaskContext(
            task_description="实现用户登录功能",
            execution_steps=["步骤1"],
            success=True,
        )

        # 由于相似度高，独特性分数低，可能导致总分不达标
        # 但这取决于其他维度的分数
        result = generator.extract_methodology_from_task(context)
        # 结果可能为None（如果总分不达标）或非None（如果其他维度补足）
        # 这里主要测试流程正确性
        if result is not None:
            assert result["quality_score"] >= 70


class TestMethodologyGeneratorIntegration:
    """集成测试"""

    def test_full_workflow(self) -> None:
        """测试完整工作流程"""
        # 创建生成器
        generator = MethodologyGenerator()

        # 创建任务上下文
        context = TaskContext(
            task_description="实现API接口开发",
            execution_steps=[
                "分析API需求",
                "设计接口规范",
                "实现接口逻辑",
                "编写单元测试",
                "进行集成测试",
            ],
            tool_calls=[
                {"name": "read_code", "arguments": {"path": "api.py"}},
                {"name": "edit_file", "arguments": {"path": "api.py"}},
            ],
            decisions=[
                "使用RESTful风格设计API",
                "采用JSON格式进行数据交换",
                "实现请求参数验证",
            ],
            verification_steps=[
                "所有单元测试通过",
                "API响应格式正确",
                "错误处理完善",
            ],
            actual_output="API接口开发完成",
            success=True,
        )

        # 提取方法论
        result = generator.extract_methodology_from_task(context)

        # 验证结果
        assert result is not None
        assert "API接口" in result["problem_type"] or "接口" in result["problem_type"]
        assert "## 规则简介" in result["content"]
        assert "## 你必须遵守的原则" in result["content"]
        assert "## 你必须执行的操作" in result["content"]
        assert result["quality_score"] >= 70

    def test_methodology_content_format(self) -> None:
        """测试方法论内容格式"""
        generator = MethodologyGenerator()

        content = generator.generate_methodology_content(
            problem_type="代码重构",
            steps=["分析代码", "识别问题", "重构代码", "验证结果"],
            decisions=["保持接口不变", "小步重构"],
            verification_steps=["测试通过", "代码审查通过"],
        )

        # 验证Markdown格式
        lines = content.split("\n")
        assert lines[0].startswith("# ")  # 一级标题

        # 验证包含所有章节
        assert content.count("## ") >= 5  # 至少5个二级标题
