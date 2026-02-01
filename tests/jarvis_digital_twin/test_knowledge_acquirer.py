"""KnowledgeAcquirer测试模块。

测试知识获取器的各项功能。
"""

import pytest

from jarvis.jarvis_digital_twin.continuous_learning import (
    Knowledge,
    KnowledgeType,
    LearningStatus,
)
from jarvis.jarvis_digital_twin.continuous_learning.knowledge_acquirer import (
    CodePatternSource,
    ErrorLearningSource,
    InteractionKnowledgeSource,
    KnowledgeAcquirer,
    KnowledgeRecord,
)


# ============== Fixtures ==============


@pytest.fixture
def acquirer() -> KnowledgeAcquirer:
    """创建默认知识获取器。"""
    return KnowledgeAcquirer()


@pytest.fixture
def interaction_source() -> InteractionKnowledgeSource:
    """创建交互知识来源。"""
    return InteractionKnowledgeSource()


@pytest.fixture
def code_source() -> CodePatternSource:
    """创建代码模式来源。"""
    return CodePatternSource()


@pytest.fixture
def error_source() -> ErrorLearningSource:
    """创建错误学习来源。"""
    return ErrorLearningSource()


@pytest.fixture
def sample_knowledge() -> Knowledge:
    """创建示例知识。"""
    return Knowledge(
        id="test_001",
        type=KnowledgeType.CONCEPT,
        content="测试概念内容",
        source="test",
        confidence=0.8,
    )


@pytest.fixture
def python_code() -> str:
    """创建Python代码示例。"""
    return '''
def calculate_sum(a: int, b: int) -> int:
    """计算两数之和。"""
    return a + b

class DataProcessor:
    """数据处理器类。"""
    
    def process(self, data: list) -> list:
        return [x * 2 for x in data]

@dataclass
class Config:
    name: str
    value: int
'''


@pytest.fixture
def error_message() -> str:
    """创建错误信息示例。"""
    return "TypeError: unsupported operand type(s) for +: 'int' and 'str'"


# ============== KnowledgeRecord Tests ==============


class TestKnowledgeRecord:
    """KnowledgeRecord测试类。"""

    def test_create_record(self, sample_knowledge: Knowledge) -> None:
        """测试创建知识记录。"""
        record = KnowledgeRecord(knowledge=sample_knowledge)
        assert record.knowledge == sample_knowledge
        assert record.status == LearningStatus.LEARNED
        assert record.content_hash != ""

    def test_content_hash_computed(self, sample_knowledge: Knowledge) -> None:
        """测试内容哈希自动计算。"""
        record = KnowledgeRecord(knowledge=sample_knowledge)
        assert len(record.content_hash) == 32  # MD5哈希长度

    def test_same_content_same_hash(self) -> None:
        """测试相同内容产生相同哈希。"""
        k1 = Knowledge(
            id="id1",
            type=KnowledgeType.FACT,
            content="相同内容",
            source="test",
        )
        k2 = Knowledge(
            id="id2",
            type=KnowledgeType.FACT,
            content="相同内容",
            source="test",
        )
        r1 = KnowledgeRecord(knowledge=k1)
        r2 = KnowledgeRecord(knowledge=k2)
        assert r1.content_hash == r2.content_hash

    def test_different_content_different_hash(self) -> None:
        """测试不同内容产生不同哈希。"""
        k1 = Knowledge(
            id="id1",
            type=KnowledgeType.FACT,
            content="内容A",
            source="test",
        )
        k2 = Knowledge(
            id="id2",
            type=KnowledgeType.FACT,
            content="内容B",
            source="test",
        )
        r1 = KnowledgeRecord(knowledge=k1)
        r2 = KnowledgeRecord(knowledge=k2)
        assert r1.content_hash != r2.content_hash


# ============== InteractionKnowledgeSource Tests ==============


class TestInteractionKnowledgeSource:
    """InteractionKnowledgeSource测试类。"""

    def test_extract_concept(
        self, interaction_source: InteractionKnowledgeSource
    ) -> None:
        """测试提取概念知识。"""
        context = "API是Application Programming Interface的缩写，是应用程序编程接口"
        knowledge = interaction_source.extract(context)
        # 可能提取到概念
        assert isinstance(knowledge, list)

    def test_extract_fact(self, interaction_source: InteractionKnowledgeSource) -> None:
        """测试提取事实知识。"""
        context = "发现这个函数在处理大数据时性能较差"
        knowledge = interaction_source.extract(context)
        assert isinstance(knowledge, list)

    def test_extract_rule(self, interaction_source: InteractionKnowledgeSource) -> None:
        """测试提取规则知识。"""
        context = "规则：所有API必须进行身份验证"
        knowledge = interaction_source.extract(context)
        assert isinstance(knowledge, list)
        # 应该提取到规则
        rules = [k for k in knowledge if k.type == KnowledgeType.RULE]
        assert len(rules) > 0

    def test_empty_context(
        self, interaction_source: InteractionKnowledgeSource
    ) -> None:
        """测试空上下文。"""
        knowledge = interaction_source.extract("")
        assert knowledge == []

    def test_short_context(
        self, interaction_source: InteractionKnowledgeSource
    ) -> None:
        """测试过短上下文。"""
        knowledge = interaction_source.extract("短")
        assert knowledge == []

    def test_min_content_length(self) -> None:
        """测试最小内容长度配置。"""
        source = InteractionKnowledgeSource(min_content_length=5)
        # 短内容应该被过滤
        knowledge = source.extract("ab")
        assert knowledge == []


# ============== CodePatternSource Tests ==============


class TestCodePatternSource:
    """CodePatternSource测试类。"""

    def test_extract_function(
        self, code_source: CodePatternSource, python_code: str
    ) -> None:
        """测试提取函数模式。"""
        knowledge = code_source.extract_from_code(python_code, "python")
        # 应该提取到函数模式
        func_patterns = [k for k in knowledge if "函数" in k.content]
        assert len(func_patterns) > 0

    def test_extract_class(
        self, code_source: CodePatternSource, python_code: str
    ) -> None:
        """测试提取类模式。"""
        knowledge = code_source.extract_from_code(python_code, "python")
        # 应该提取到类模式
        class_patterns = [k for k in knowledge if "类" in k.content]
        assert len(class_patterns) > 0

    def test_empty_code(self, code_source: CodePatternSource) -> None:
        """测试空代码。"""
        knowledge = code_source.extract_from_code("", "python")
        assert knowledge == []

    def test_unsupported_language(self, code_source: CodePatternSource) -> None:
        """测试不支持的语言。"""
        knowledge = code_source.extract_from_code("some code", "unknown_lang")
        assert knowledge == []

    def test_extract_via_protocol(
        self, code_source: CodePatternSource, python_code: str
    ) -> None:
        """测试通过Protocol接口提取。"""
        knowledge = code_source.extract(python_code)
        assert isinstance(knowledge, list)


# ============== ErrorLearningSource Tests ==============


class TestErrorLearningSource:
    """ErrorLearningSource测试类。"""

    def test_learn_type_error(
        self, error_source: ErrorLearningSource, error_message: str
    ) -> None:
        """测试学习类型错误。"""
        knowledge = error_source.learn_from_error(error_message, "")
        assert len(knowledge) > 0
        assert all(k.type == KnowledgeType.RULE for k in knowledge)

    def test_learn_value_error(self, error_source: ErrorLearningSource) -> None:
        """测试学习值错误。"""
        error = "ValueError: invalid literal for int() with base 10: 'abc'"
        knowledge = error_source.learn_from_error(error, "")
        assert len(knowledge) > 0

    def test_learn_import_error(self, error_source: ErrorLearningSource) -> None:
        """测试学习导入错误。"""
        error = "ImportError: No module named 'nonexistent'"
        knowledge = error_source.learn_from_error(error, "")
        assert len(knowledge) > 0

    def test_empty_error(self, error_source: ErrorLearningSource) -> None:
        """测试空错误信息。"""
        knowledge = error_source.learn_from_error("", "")
        assert knowledge == []

    def test_error_with_context(self, error_source: ErrorLearningSource) -> None:
        """测试带上下文的错误学习。"""
        error = "KeyError: 'missing_key'"
        context = "在处理用户配置时发生"
        knowledge = error_source.learn_from_error(error, context)
        assert len(knowledge) > 0
        # 上下文应该包含在知识内容中
        assert any(context[:10] in k.content for k in knowledge)

    def test_error_statistics(self, error_source: ErrorLearningSource) -> None:
        """测试错误统计。"""
        error_source.learn_from_error("TypeError: test", "")
        error_source.learn_from_error("TypeError: another", "")
        stats = error_source.get_error_statistics()
        assert "TypeError" in stats
        assert stats["TypeError"] >= 2


# ============== KnowledgeAcquirer Tests ==============


class TestKnowledgeAcquirer:
    """KnowledgeAcquirer测试类。"""

    def test_create_acquirer(self, acquirer: KnowledgeAcquirer) -> None:
        """测试创建知识获取器。"""
        assert acquirer is not None
        assert acquirer.get_knowledge_count() == 0

    def test_extract_knowledge(self, acquirer: KnowledgeAcquirer) -> None:
        """测试提取知识。"""
        context = "规则：代码必须通过所有测试才能合并"
        knowledge = acquirer.extract_knowledge(context)
        assert isinstance(knowledge, list)

    def test_extract_empty_context(self, acquirer: KnowledgeAcquirer) -> None:
        """测试空上下文提取。"""
        knowledge = acquirer.extract_knowledge("")
        assert knowledge == []

    def test_learn_from_code(
        self, acquirer: KnowledgeAcquirer, python_code: str
    ) -> None:
        """测试从代码学习。"""
        knowledge = acquirer.learn_from_code(python_code)
        assert len(knowledge) > 0
        assert all(k.type == KnowledgeType.PATTERN for k in knowledge)

    def test_learn_from_empty_code(self, acquirer: KnowledgeAcquirer) -> None:
        """测试从空代码学习。"""
        knowledge = acquirer.learn_from_code("")
        assert knowledge == []

    def test_learn_from_error(
        self, acquirer: KnowledgeAcquirer, error_message: str
    ) -> None:
        """测试从错误学习。"""
        knowledge = acquirer.learn_from_error(error_message)
        assert len(knowledge) > 0
        assert all(k.type == KnowledgeType.RULE for k in knowledge)

    def test_learn_from_empty_error(self, acquirer: KnowledgeAcquirer) -> None:
        """测试从空错误学习。"""
        knowledge = acquirer.learn_from_error("")
        assert knowledge == []

    def test_store_knowledge(
        self, acquirer: KnowledgeAcquirer, sample_knowledge: Knowledge
    ) -> None:
        """测试存储知识。"""
        result = acquirer.store_knowledge(sample_knowledge)
        assert result is True
        assert acquirer.get_knowledge_count() == 1

    def test_store_duplicate_knowledge(self, acquirer: KnowledgeAcquirer) -> None:
        """测试存储重复知识。"""
        k1 = Knowledge(
            id="id1",
            type=KnowledgeType.FACT,
            content="重复内容测试",
            source="test",
            confidence=0.5,
        )
        k2 = Knowledge(
            id="id2",
            type=KnowledgeType.FACT,
            content="重复内容测试",
            source="test",
            confidence=0.5,
        )
        assert acquirer.store_knowledge(k1) is True
        assert acquirer.store_knowledge(k2) is False  # 重复，不存储
        assert acquirer.get_knowledge_count() == 1
        # 置信度应该增加
        stored = acquirer.get_knowledge("id1")
        assert stored is not None
        assert stored.confidence > 0.5

    def test_get_knowledge(
        self, acquirer: KnowledgeAcquirer, sample_knowledge: Knowledge
    ) -> None:
        """测试获取知识。"""
        acquirer.store_knowledge(sample_knowledge)
        retrieved = acquirer.get_knowledge(sample_knowledge.id)
        assert retrieved is not None
        assert retrieved.id == sample_knowledge.id

    def test_get_nonexistent_knowledge(self, acquirer: KnowledgeAcquirer) -> None:
        """测试获取不存在的知识。"""
        retrieved = acquirer.get_knowledge("nonexistent_id")
        assert retrieved is None

    def test_search_knowledge(self, acquirer: KnowledgeAcquirer) -> None:
        """测试搜索知识。"""
        k1 = Knowledge(
            id="id1",
            type=KnowledgeType.CONCEPT,
            content="Python是一种编程语言",
            source="test",
        )
        k2 = Knowledge(
            id="id2",
            type=KnowledgeType.CONCEPT,
            content="Java是另一种编程语言",
            source="test",
        )
        acquirer.store_knowledge(k1)
        acquirer.store_knowledge(k2)

        results = acquirer.search_knowledge("Python")
        assert len(results) == 1
        assert results[0].id == "id1"

    def test_search_empty_query(self, acquirer: KnowledgeAcquirer) -> None:
        """测试空查询搜索。"""
        results = acquirer.search_knowledge("")
        assert results == []

    def test_search_with_type_filter(self, acquirer: KnowledgeAcquirer) -> None:
        """测试带类型过滤的搜索。"""
        k1 = Knowledge(
            id="id1",
            type=KnowledgeType.CONCEPT,
            content="测试内容A",
            source="test",
        )
        k2 = Knowledge(
            id="id2",
            type=KnowledgeType.RULE,
            content="测试内容B",
            source="test",
        )
        acquirer.store_knowledge(k1)
        acquirer.store_knowledge(k2)

        results = acquirer.search_knowledge(
            "测试", knowledge_type=KnowledgeType.CONCEPT
        )
        assert len(results) == 1
        assert results[0].type == KnowledgeType.CONCEPT

    def test_update_confidence(
        self, acquirer: KnowledgeAcquirer, sample_knowledge: Knowledge
    ) -> None:
        """测试更新置信度。"""
        acquirer.store_knowledge(sample_knowledge)
        original_confidence = sample_knowledge.confidence

        result = acquirer.update_confidence(sample_knowledge.id, 0.1)
        assert result is True

        updated = acquirer.get_knowledge(sample_knowledge.id)
        assert updated is not None
        assert updated.confidence == original_confidence + 0.1

    def test_update_confidence_bounds(self, acquirer: KnowledgeAcquirer) -> None:
        """测试置信度边界。"""
        k = Knowledge(
            id="id1",
            type=KnowledgeType.FACT,
            content="测试置信度边界",
            source="test",
            confidence=0.9,
        )
        acquirer.store_knowledge(k)

        # 增加超过1.0
        acquirer.update_confidence("id1", 0.5)
        updated = acquirer.get_knowledge("id1")
        assert updated is not None
        assert updated.confidence == 1.0  # 不超过1.0

    def test_update_confidence_deprecate(self, acquirer: KnowledgeAcquirer) -> None:
        """测试置信度过低自动废弃。"""
        k = Knowledge(
            id="id1",
            type=KnowledgeType.FACT,
            content="测试自动废弃功能",
            source="test",
            confidence=0.15,
        )
        acquirer.store_knowledge(k)

        # 降低置信度到0.1以下
        acquirer.update_confidence("id1", -0.1)

        # 知识应该被废弃，不在正常列表中
        all_knowledge = acquirer.get_all_knowledge(include_deprecated=False)
        assert not any(kn.id == "id1" for kn in all_knowledge)

    def test_verify_knowledge(
        self, acquirer: KnowledgeAcquirer, sample_knowledge: Knowledge
    ) -> None:
        """测试验证知识。"""
        acquirer.store_knowledge(sample_knowledge)
        result = acquirer.verify_knowledge(sample_knowledge.id)
        assert result is True

    def test_deprecate_knowledge(
        self, acquirer: KnowledgeAcquirer, sample_knowledge: Knowledge
    ) -> None:
        """测试废弃知识。"""
        acquirer.store_knowledge(sample_knowledge)
        result = acquirer.deprecate_knowledge(sample_knowledge.id)
        assert result is True

        # 废弃的知识不应该在正常列表中
        all_knowledge = acquirer.get_all_knowledge(include_deprecated=False)
        assert not any(k.id == sample_knowledge.id for k in all_knowledge)

    def test_get_all_knowledge(self, acquirer: KnowledgeAcquirer) -> None:
        """测试获取所有知识。"""
        k1 = Knowledge(
            id="id1", type=KnowledgeType.FACT, content="内容1", source="test"
        )
        k2 = Knowledge(
            id="id2", type=KnowledgeType.RULE, content="内容2", source="test"
        )
        acquirer.store_knowledge(k1)
        acquirer.store_knowledge(k2)

        all_knowledge = acquirer.get_all_knowledge()
        assert len(all_knowledge) == 2

    def test_get_knowledge_by_type(self, acquirer: KnowledgeAcquirer) -> None:
        """测试按类型获取知识。"""
        k1 = Knowledge(
            id="id1", type=KnowledgeType.CONCEPT, content="概念1", source="test"
        )
        k2 = Knowledge(
            id="id2", type=KnowledgeType.RULE, content="规则1", source="test"
        )
        k3 = Knowledge(
            id="id3", type=KnowledgeType.CONCEPT, content="概念2", source="test"
        )
        acquirer.store_knowledge(k1)
        acquirer.store_knowledge(k2)
        acquirer.store_knowledge(k3)

        concepts = acquirer.get_knowledge_by_type(KnowledgeType.CONCEPT)
        assert len(concepts) == 2
        assert all(k.type == KnowledgeType.CONCEPT for k in concepts)

    def test_clear_all(
        self, acquirer: KnowledgeAcquirer, sample_knowledge: Knowledge
    ) -> None:
        """测试清除所有知识。"""
        acquirer.store_knowledge(sample_knowledge)
        assert acquirer.get_knowledge_count() == 1

        acquirer.clear_all()
        assert acquirer.get_knowledge_count() == 0

    def test_get_statistics(self, acquirer: KnowledgeAcquirer) -> None:
        """测试获取统计信息。"""
        k1 = Knowledge(
            id="id1", type=KnowledgeType.CONCEPT, content="概念", source="test"
        )
        k2 = Knowledge(id="id2", type=KnowledgeType.RULE, content="规则", source="test")
        acquirer.store_knowledge(k1)
        acquirer.store_knowledge(k2)

        stats = acquirer.get_statistics()
        assert stats["total_count"] == 2
        assert "type_distribution" in stats
        assert "status_distribution" in stats
        assert "average_confidence" in stats


# ============== Custom Source Tests ==============


class CustomKnowledgeSource:
    """自定义知识来源（用于测试）。"""

    def extract(self, context: str) -> list[Knowledge]:
        """提取知识。"""
        if "custom" in context.lower():
            return [
                Knowledge(
                    id="custom_001",
                    type=KnowledgeType.FACT,
                    content="自定义来源提取的知识",
                    source="custom",
                )
            ]
        return []


class TestCustomSource:
    """自定义来源测试类。"""

    def test_register_source(self, acquirer: KnowledgeAcquirer) -> None:
        """测试注册自定义来源。"""
        source = CustomKnowledgeSource()
        acquirer.register_source(source)
        stats = acquirer.get_statistics()
        assert stats["registered_sources"] == 1

    def test_unregister_source(self, acquirer: KnowledgeAcquirer) -> None:
        """测试取消注册来源。"""
        source = CustomKnowledgeSource()
        acquirer.register_source(source)
        result = acquirer.unregister_source(source)
        assert result is True
        stats = acquirer.get_statistics()
        assert stats["registered_sources"] == 0

    def test_unregister_nonexistent_source(self, acquirer: KnowledgeAcquirer) -> None:
        """测试取消注册不存在的来源。"""
        source = CustomKnowledgeSource()
        result = acquirer.unregister_source(source)
        assert result is False

    def test_custom_source_extraction(self, acquirer: KnowledgeAcquirer) -> None:
        """测试自定义来源提取。"""
        source = CustomKnowledgeSource()
        acquirer.register_source(source)

        knowledge = acquirer.extract_knowledge("This is a custom context")
        # 应该包含自定义来源提取的知识
        custom_knowledge = [k for k in knowledge if k.source == "custom"]
        assert len(custom_knowledge) > 0
