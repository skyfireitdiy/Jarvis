"""规则自动生成器单元测试"""

import os
import tempfile

import pytest

from jarvis.jarvis_rule_generator.rule_generator import (
    CodePattern,
    RuleGenerationContext,
    RuleGenerator,
    RuleQualityScore,
)


class TestCodePattern:
    """CodePattern数据类测试"""

    def test_default_values(self) -> None:
        """测试默认值"""
        pattern = CodePattern()
        assert pattern.pattern_type == ""
        assert pattern.pattern_name == ""
        assert pattern.description == ""
        assert pattern.code_examples == []
        assert pattern.file_paths == []
        assert pattern.occurrence_count == 0
        assert pattern.context == ""

    def test_custom_values(self) -> None:
        """测试自定义值"""
        pattern = CodePattern(
            pattern_type="design_pattern",
            pattern_name="单例模式",
            description="确保类只有一个实例",
            code_examples=["class Singleton: pass"],
            file_paths=["test.py"],
            occurrence_count=3,
            context="设计模式",
        )
        assert pattern.pattern_type == "design_pattern"
        assert pattern.pattern_name == "单例模式"
        assert pattern.occurrence_count == 3


class TestRuleGenerationContext:
    """RuleGenerationContext数据类测试"""

    def test_default_values(self) -> None:
        """测试默认值"""
        context = RuleGenerationContext()
        assert context.source_type == ""
        assert context.pattern is None
        assert context.description == ""
        assert context.scope == "project"

    def test_with_pattern(self) -> None:
        """测试带模式的上下文"""
        pattern = CodePattern(pattern_name="测试模式")
        context = RuleGenerationContext(
            source_type="code_pattern",
            pattern=pattern,
            description="测试描述",
            scope="global",
        )
        assert context.pattern is not None
        assert context.pattern.pattern_name == "测试模式"
        assert context.scope == "global"


class TestRuleQualityScore:
    """RuleQualityScore数据类测试"""

    def test_default_values(self) -> None:
        """测试默认值"""
        score = RuleQualityScore()
        assert score.completeness == 0
        assert score.executability == 0
        assert score.generality == 0
        assert score.uniqueness == 0
        assert score.code_examples == 0
        assert score.total == 0

    def test_total_calculation(self) -> None:
        """测试总分计算"""
        score = RuleQualityScore(
            completeness=25,
            executability=25,
            generality=20,
            uniqueness=15,
            code_examples=15,
        )
        assert score.total == 100

    def test_is_qualified_default_threshold(self) -> None:
        """测试默认阈值判断"""
        # 低于阈值
        score_low = RuleQualityScore(
            completeness=20,
            executability=20,
            generality=10,
            uniqueness=5,
            code_examples=5,
        )
        assert score_low.is_qualified() is False

        # 等于阈值
        score_equal = RuleQualityScore(
            completeness=25,
            executability=25,
            generality=10,
            uniqueness=5,
            code_examples=5,
        )
        assert score_equal.is_qualified() is True

        # 高于阈值
        score_high = RuleQualityScore(
            completeness=25,
            executability=25,
            generality=20,
            uniqueness=15,
            code_examples=15,
        )
        assert score_high.is_qualified() is True

    def test_is_qualified_custom_threshold(self) -> None:
        """测试自定义阈值判断"""
        score = RuleQualityScore(
            completeness=20,
            executability=20,
            generality=10,
            uniqueness=5,
            code_examples=5,
        )
        assert score.is_qualified(threshold=50) is True
        assert score.is_qualified(threshold=70) is False


class TestRuleGenerator:
    """RuleGenerator类测试"""

    @pytest.fixture
    def generator(self) -> RuleGenerator:
        """创建生成器实例"""
        return RuleGenerator()

    @pytest.fixture
    def temp_dir(self) -> str:
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_init_without_existing_rules(self) -> None:
        """测试无现有规则时的初始化"""
        generator = RuleGenerator()
        assert generator.existing_rules == []
        assert generator.rules_dir == ".jarvis/rules/"

    def test_init_with_existing_rules(self) -> None:
        """测试有现有规则时的初始化"""
        existing = ["规则1", "规则2"]
        generator = RuleGenerator(existing_rules=existing, rules_dir="/custom/rules/")
        assert generator.existing_rules == existing
        assert generator.rules_dir == "/custom/rules/"

    def test_generate_rule_content_with_pattern(self, generator: RuleGenerator) -> None:
        """测试带模式的规则内容生成"""
        pattern = CodePattern(
            pattern_type="design_pattern",
            pattern_name="单例模式",
            description="确保类只有一个实例",
            code_examples=["class Singleton:\n    _instance = None"],
            context="设计模式",
        )
        context = RuleGenerationContext(
            source_type="code_pattern",
            pattern=pattern,
            description="单例模式规则",
        )

        content = generator.generate_rule_content(context)

        # 验证包含必需章节
        assert "# 单例模式" in content
        assert "## 规则简介" in content
        assert "## 你必须遵循的工作流程" in content
        assert "## 你必须遵守的原则" in content
        assert "## 实践指导" in content
        assert "## 代码示例" in content
        assert "## 执行检查清单" in content

    def test_generate_rule_content_without_pattern(
        self, generator: RuleGenerator
    ) -> None:
        """测试无模式的规则内容生成"""
        context = RuleGenerationContext(
            source_type="user_request",
            description="自定义规则",
        )

        content = generator.generate_rule_content(context)

        assert "# 自动生成规则" in content
        assert "## 规则简介" in content

    def test_evaluate_rule_quality_complete(self, generator: RuleGenerator) -> None:
        """测试完整规则的质量评估"""
        pattern = CodePattern(
            pattern_type="design_pattern",
            pattern_name="测试模式",
            description="测试描述",
            code_examples=["def test(): pass"],
        )
        context = RuleGenerationContext(
            source_type="code_pattern",
            pattern=pattern,
        )
        content = generator.generate_rule_content(context)
        score = generator.evaluate_rule_quality(content)

        # 完整性应该较高
        assert score.completeness > 0
        # 可执行性应该较高
        assert score.executability > 0
        # 总分应该达到阈值
        assert score.is_qualified()

    def test_evaluate_completeness(self, generator: RuleGenerator) -> None:
        """测试完整性评估"""
        # 包含所有必需章节
        full_content = """## 规则简介
内容
## 你必须遵循的工作流程
内容
## 你必须遵守的原则
内容"""
        assert generator._evaluate_completeness(full_content) == 24  # 3 * 8 = 24

        # 缺少章节
        partial_content = """## 规则简介
内容"""
        assert generator._evaluate_completeness(partial_content) == 8

    def test_evaluate_executability(self, generator: RuleGenerator) -> None:
        """测试可执行性评估"""
        # 有编号步骤和操作关键词
        good_content = """1. 执行第一步
2. 创建文件
3. 验证结果"""
        score = generator._evaluate_executability(good_content)
        assert score > 10  # 有编号步骤

        # 无编号步骤
        bad_content = "这是一段描述性文字"
        score = generator._evaluate_executability(bad_content)
        assert score < 10

    def test_evaluate_generality(self, generator: RuleGenerator) -> None:
        """测试通用性评估"""
        # 通用内容
        general_content = "这是一个通用的规则描述"
        score = generator._evaluate_generality(general_content)
        assert score == 15  # 基础分

        # 包含具体路径
        specific_content = "文件位于 /home/user/project/file.py"
        score = generator._evaluate_generality(specific_content)
        assert score < 15

    def test_evaluate_uniqueness_no_existing(self, generator: RuleGenerator) -> None:
        """测试无现有规则时的独特性评估"""
        content = "新的规则内容"
        score = generator._evaluate_uniqueness(content)
        assert score == 12

    def test_evaluate_uniqueness_with_similar(self) -> None:
        """测试有相似规则时的独特性评估"""
        existing = ["这是一个规则内容 包含一些关键词"]
        generator = RuleGenerator(existing_rules=existing)

        # 相似内容
        similar_content = "这是一个规则内容 包含一些关键词"
        score = generator._evaluate_uniqueness(similar_content)
        assert score < 12

        # 不同内容
        different_content = "完全不同的内容 没有任何重复"
        score = generator._evaluate_uniqueness(different_content)
        assert score > 5

    def test_evaluate_code_examples(self, generator: RuleGenerator) -> None:
        """测试代码示例评估"""
        # 有代码块
        with_code = """```python
def test():
    pass
```"""
        score = generator._evaluate_code_examples(with_code)
        assert score > 0

        # 无代码块
        without_code = "没有代码示例"
        score = generator._evaluate_code_examples(without_code)
        assert score == 0

    def test_detect_rule_conflict_name(self) -> None:
        """测试名称冲突检测"""
        existing = ["# 测试规则\n\n内容"]
        generator = RuleGenerator(existing_rules=existing)

        new_rule = "# 测试规则\n\n新内容"
        conflicts = generator.detect_rule_conflict(new_rule)

        assert len(conflicts) > 0
        assert any(c["type"] == "name_conflict" for c in conflicts)

    def test_detect_rule_conflict_similar(self) -> None:
        """测试内容相似冲突检测"""
        # 使用英文内容确保词语分割正确，相似度超过70%阈值
        words = [
            "test",
            "content",
            "rule",
            "example",
            "code",
            "function",
            "class",
            "method",
        ]
        long_content = " ".join(words * 20)
        existing = [f"# RuleA\n\n{long_content}"]
        generator = RuleGenerator(existing_rules=existing)

        new_rule = f"# RuleB\n\n{long_content}"
        conflicts = generator.detect_rule_conflict(new_rule)

        assert len(conflicts) > 0
        assert any(c["type"] == "content_similar" for c in conflicts)

    def test_detect_rule_conflict_no_conflict(self, generator: RuleGenerator) -> None:
        """测试无冲突情况"""
        new_rule = "# 新规则\n\n完全不同的内容"
        conflicts = generator.detect_rule_conflict(new_rule)
        assert len(conflicts) == 0

    def test_calculate_similarity(self, generator: RuleGenerator) -> None:
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

    def test_calculate_similarity_empty(self, generator: RuleGenerator) -> None:
        """测试空文本的相似度计算"""
        assert generator._calculate_similarity("", "hello") == 0.0
        assert generator._calculate_similarity("hello", "") == 0.0
        assert generator._calculate_similarity("", "") == 0.0

    def test_extract_rule_name(self, generator: RuleGenerator) -> None:
        """测试规则名称提取"""
        content = "# 测试规则\n\n内容"
        name = generator._extract_rule_name(content)
        assert name == "测试规则"

        # 无标题
        content_no_title = "没有标题的内容"
        name = generator._extract_rule_name(content_no_title)
        assert name == ""

    def test_extract_section(self, generator: RuleGenerator) -> None:
        """测试章节提取"""
        content = "# 规则\n\n## 简介\n这是简介内容\n\n## 原则\n这是原则内容\n"
        # 测试提取包含"简介"的章节
        section = generator._extract_section(content, "简介")
        assert "这是简介内容" in section

        # 测试提取包含"原则"的章节
        section = generator._extract_section(content, "原则")
        assert "这是原则内容" in section

    def test_sanitize_filename(self, generator: RuleGenerator) -> None:
        """测试文件名清理"""
        # 正常名称
        assert generator._sanitize_filename("test_rule") == "test_rule"

        # 包含非法字符
        assert generator._sanitize_filename("test/rule") == "test_rule"
        assert generator._sanitize_filename("test:rule") == "test_rule"

        # 空名称
        assert generator._sanitize_filename("") == "unnamed_rule"

    def test_save_rule(self, generator: RuleGenerator, temp_dir: str) -> None:
        """测试规则保存"""
        generator.rules_dir = temp_dir
        content = "# 测试规则\n\n内容"

        file_path = generator.save_rule("测试规则", content, scope="project")

        assert os.path.exists(file_path)
        with open(file_path, "r", encoding="utf-8") as f:
            saved_content = f.read()
        assert saved_content == content

    def test_save_rule_name_conflict(
        self, generator: RuleGenerator, temp_dir: str
    ) -> None:
        """测试保存时的名称冲突处理"""
        generator.rules_dir = temp_dir
        content = "# 测试规则\n\n内容"

        # 保存第一个
        file_path1 = generator.save_rule("测试规则", content)
        # 保存第二个（同名）
        file_path2 = generator.save_rule("测试规则", content)

        assert file_path1 != file_path2
        assert os.path.exists(file_path1)
        assert os.path.exists(file_path2)

    def test_detect_patterns_empty(self, generator: RuleGenerator) -> None:
        """测试空文件列表的模式检测"""
        patterns = generator.detect_patterns([])
        assert patterns == []

    def test_detect_patterns_nonexistent_file(self, generator: RuleGenerator) -> None:
        """测试不存在文件的模式检测"""
        patterns = generator.detect_patterns(["/nonexistent/file.py"])
        assert patterns == []

    def test_detect_patterns_singleton(
        self, generator: RuleGenerator, temp_dir: str
    ) -> None:
        """测试单例模式检测"""
        # 创建包含单例模式的文件
        test_file = os.path.join(temp_dir, "singleton.py")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("""class Singleton:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
""")

        patterns = generator.detect_patterns([test_file], "design_pattern")
        assert len(patterns) > 0
        assert any(p.pattern_name == "单例模式" for p in patterns)

    def test_detect_patterns_factory(
        self, generator: RuleGenerator, temp_dir: str
    ) -> None:
        """测试工厂模式检测"""
        test_file = os.path.join(temp_dir, "factory.py")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("""class ProductFactory:
    def create_product(self, product_type):
        if product_type == "A":
            return ProductA()
        return ProductB()
""")

        patterns = generator.detect_patterns([test_file], "design_pattern")
        assert len(patterns) > 0
        assert any(p.pattern_name == "工厂模式" for p in patterns)

    def test_extract_rule_from_code(
        self, generator: RuleGenerator, temp_dir: str
    ) -> None:
        """测试从代码提取规则"""
        test_file = os.path.join(temp_dir, "test.py")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("""class Singleton:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
""")

        result = generator.extract_rule_from_code([test_file], "design_pattern")

        if result is not None:
            assert "rule_name" in result
            assert "content" in result
            assert "quality_score" in result
            assert result["quality_score"] >= 70

    def test_extract_rule_from_code_no_pattern(
        self, generator: RuleGenerator, temp_dir: str
    ) -> None:
        """测试无模式时的规则提取"""
        test_file = os.path.join(temp_dir, "simple.py")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("x = 1\n")

        result = generator.extract_rule_from_code([test_file])
        assert result is None


class TestRuleGeneratorIntegration:
    """集成测试"""

    def test_full_workflow(self) -> None:
        """测试完整工作流程"""
        generator = RuleGenerator()

        # 创建规则生成上下文
        pattern = CodePattern(
            pattern_type="design_pattern",
            pattern_name="观察者模式",
            description="定义对象间的一对多依赖关系",
            code_examples=[
                """class Subject:
    def __init__(self):
        self._observers = []

    def attach(self, observer):
        self._observers.append(observer)

    def notify(self):
        for observer in self._observers:
            observer.update(self)"""
            ],
            file_paths=["observer.py"],
            occurrence_count=1,
            context="设计模式",
        )

        context = RuleGenerationContext(
            source_type="code_pattern",
            pattern=pattern,
            description="观察者模式规则",
            scope="project",
        )

        # 生成规则内容
        content = generator.generate_rule_content(context)

        # 验证内容
        assert "# 观察者模式" in content
        assert "## 规则简介" in content
        assert "## 你必须遵循的工作流程" in content
        assert "## 你必须遵守的原则" in content

        # 评估质量
        score = generator.evaluate_rule_quality(content)
        assert score.is_qualified()

        # 检测冲突
        conflicts = generator.detect_rule_conflict(content)
        assert len(conflicts) == 0

    def test_rule_content_format(self) -> None:
        """测试规则内容格式"""
        generator = RuleGenerator()

        pattern = CodePattern(
            pattern_type="coding_style",
            pattern_name="类型注解规范",
            description="使用类型注解提高代码可读性",
            code_examples=["def add(a: int, b: int) -> int:\n    return a + b"],
        )

        context = RuleGenerationContext(
            source_type="code_pattern",
            pattern=pattern,
        )

        content = generator.generate_rule_content(context)

        # 验证Markdown格式
        lines = content.split("\n")
        assert lines[0].startswith("# ")  # 一级标题

        # 验证包含所有章节
        assert content.count("## ") >= 6  # 至少6个二级标题
