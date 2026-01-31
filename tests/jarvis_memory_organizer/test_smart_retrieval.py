"""智能检索增强模块测试

测试SmartRetriever类的所有核心功能。
"""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
import pytest

from jarvis.jarvis_memory_organizer.smart_retrieval import (
    Memory,
    RecommendationContext,
    RelevanceScore,
    SemanticQuery,
    SmartRetriever,
)


class TestMemory:
    """Memory数据类测试"""

    def test_from_dict(self):
        """测试从字典创建Memory对象"""
        data = {
            "id": "test_id",
            "type": "project_long_term",
            "tags": ["tag1", "tag2"],
            "content": "test content",
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
        }
        memory = Memory.from_dict(data)

        assert memory.id == "test_id"
        assert memory.type == "project_long_term"
        assert memory.tags == ["tag1", "tag2"]
        assert memory.content == "test content"
        assert memory.created_at == "2024-01-01T00:00:00"

    def test_from_dict_with_missing_fields(self):
        """测试从不完整字典创建Memory对象"""
        data = {"id": "test_id"}
        memory = Memory.from_dict(data)

        assert memory.id == "test_id"
        assert memory.type == ""
        assert memory.tags == []
        assert memory.content == ""

    def test_to_dict(self):
        """测试转换为字典"""
        memory = Memory(
            id="test_id",
            type="project_long_term",
            tags=["tag1", "tag2"],
            content="test content",
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
        )
        data = memory.to_dict()

        assert data["id"] == "test_id"
        assert data["type"] == "project_long_term"
        assert data["tags"] == ["tag1", "tag2"]
        assert data["content"] == "test content"


class TestSemanticQuery:
    """SemanticQuery数据类测试"""

    def test_default_values(self):
        """测试默认值"""
        query = SemanticQuery()

        assert query.query_text == ""
        assert query.extracted_keywords == []
        assert query.expanded_tags == []
        assert query.intent == ""
        assert query.context is None

    def test_with_values(self):
        """测试带值创建"""
        query = SemanticQuery(
            query_text="test query",
            extracted_keywords=["test", "query"],
            expanded_tags=["test", "testing"],
            intent="how_to",
            context="some context",
        )

        assert query.query_text == "test query"
        assert query.extracted_keywords == ["test", "query"]
        assert query.expanded_tags == ["test", "testing"]
        assert query.intent == "how_to"
        assert query.context == "some context"


class TestRecommendationContext:
    """RecommendationContext数据类测试"""

    def test_default_values(self):
        """测试默认值"""
        context = RecommendationContext()

        assert context.task_description == ""
        assert context.current_step == ""
        assert context.tool_calls == []
        assert context.errors == []

    def test_with_values(self):
        """测试带值创建"""
        context = RecommendationContext(
            task_description="implement feature",
            current_step="writing code",
            tool_calls=["read_code", "edit_file"],
            errors=["syntax error"],
        )

        assert context.task_description == "implement feature"
        assert context.current_step == "writing code"
        assert context.tool_calls == ["read_code", "edit_file"]
        assert context.errors == ["syntax error"]


class TestRelevanceScore:
    """RelevanceScore数据类测试"""

    def test_default_values(self):
        """测试默认值"""
        score = RelevanceScore()

        assert score.tag_match == 0.0
        assert score.content_similarity == 0.0
        assert score.time_freshness == 0.0
        assert score.usage_frequency == 0.0
        assert score.total == 0.0

    def test_total_calculation(self):
        """测试总分计算"""
        score = RelevanceScore(
            tag_match=100.0,
            content_similarity=100.0,
            time_freshness=100.0,
            usage_frequency=100.0,
        )

        # 30% + 40% + 15% + 15% = 100%
        expected_total = 100 * 0.3 + 100 * 0.4 + 100 * 0.15 + 100 * 0.15
        assert score.total == expected_total

    def test_weighted_total(self):
        """测试加权总分"""
        score = RelevanceScore(
            tag_match=50.0,
            content_similarity=80.0,
            time_freshness=60.0,
            usage_frequency=40.0,
        )

        expected_total = 50 * 0.3 + 80 * 0.4 + 60 * 0.15 + 40 * 0.15
        assert score.total == expected_total


class TestSmartRetriever:
    """SmartRetriever类测试"""

    @pytest.fixture
    def temp_memory_dir(self):
        """创建临时记忆目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / ".jarvis" / "memory"
            project_dir.mkdir(parents=True)
            yield tmpdir, project_dir

    @pytest.fixture
    def retriever_with_memories(self, temp_memory_dir):
        """创建带有测试记忆的检索器"""
        tmpdir, project_dir = temp_memory_dir

        # 创建测试记忆
        memories = [
            {
                "id": "memory_1",
                "type": "project_long_term",
                "tags": ["code", "python", "testing"],
                "content": "Python代码测试最佳实践",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            },
            {
                "id": "memory_2",
                "type": "project_long_term",
                "tags": ["architecture", "design", "python"],
                "content": "Python架构设计模式",
                "created_at": (datetime.now() - timedelta(days=30)).isoformat(),
                "updated_at": (datetime.now() - timedelta(days=30)).isoformat(),
            },
            {
                "id": "memory_3",
                "type": "project_long_term",
                "tags": ["error", "bug", "fix"],
                "content": "常见错误修复方法",
                "created_at": (datetime.now() - timedelta(days=7)).isoformat(),
                "updated_at": (datetime.now() - timedelta(days=7)).isoformat(),
            },
        ]

        for memory in memories:
            memory_file = project_dir / f"{memory['id']}.json"
            with open(memory_file, "w", encoding="utf-8") as f:
                json.dump(memory, f, ensure_ascii=False)

        # 创建检索器并设置目录
        retriever = SmartRetriever()
        retriever.project_memory_dir = project_dir

        return retriever

    def test_init(self):
        """测试初始化"""
        retriever = SmartRetriever()

        assert retriever.project_memory_dir == Path(".jarvis/memory")
        assert retriever._usage_stats == {}

    def test_extract_keywords(self):
        """测试关键词提取"""
        retriever = SmartRetriever()

        keywords = retriever._extract_keywords("如何编写Python代码测试")

        # 简单分词会将整个中文字符串作为一个词
        assert len(keywords) > 0
        # 检查是否包含python（小写）
        assert any("python" in k.lower() for k in keywords)

    def test_extract_keywords_english(self):
        """测试英文关键词提取"""
        retriever = SmartRetriever()

        keywords = retriever._extract_keywords("How to write Python code tests")

        assert "python" in keywords
        assert "code" in keywords
        assert "tests" in keywords
        # 停用词应该被过滤
        assert "how" not in keywords
        assert "to" not in keywords

    def test_expand_tags(self):
        """测试标签扩展"""
        retriever = SmartRetriever()

        expanded = retriever._expand_tags(["代码", "测试"])

        # 应该包含原始关键词
        assert "代码" in expanded
        assert "测试" in expanded
        # 应该包含扩展的标签
        assert "code" in expanded or "coding" in expanded
        assert "test" in expanded or "testing" in expanded

    def test_identify_intent_how_to(self):
        """测试意图识别 - how_to"""
        retriever = SmartRetriever()

        assert retriever._identify_intent("如何编写测试") == "how_to"
        assert retriever._identify_intent("怎么修复bug") == "how_to"
        assert retriever._identify_intent("How to write tests") == "how_to"

    def test_identify_intent_definition(self):
        """测试意图识别 - definition"""
        retriever = SmartRetriever()

        assert retriever._identify_intent("什么是单元测试") == "definition"
        assert retriever._identify_intent("What is unit testing") == "definition"

    def test_identify_intent_troubleshooting(self):
        """测试意图识别 - troubleshooting"""
        retriever = SmartRetriever()

        # 使用明确的错误相关查询（不包含其他意图的关键词）
        assert retriever._identify_intent("代码有错误") == "troubleshooting"
        assert retriever._identify_intent("bug in code") == "troubleshooting"

    def test_identify_intent_general(self):
        """测试意图识别 - general"""
        retriever = SmartRetriever()

        assert retriever._identify_intent("Python代码") == "general"

    def test_analyze_query(self):
        """测试查询分析"""
        retriever = SmartRetriever()

        query = retriever._analyze_query("如何编写Python测试代码")

        assert query.query_text == "如何编写Python测试代码"
        assert len(query.extracted_keywords) > 0
        assert len(query.expanded_tags) > 0
        assert query.intent == "how_to"

    def test_calculate_content_similarity(self):
        """测试内容相似度计算"""
        retriever = SmartRetriever()

        # 相同文本
        similarity = retriever._calculate_content_similarity(
            "Python code test", "Python code test"
        )
        assert similarity == 1.0

        # 部分相似（使用英文以便正确分词）
        similarity = retriever._calculate_content_similarity(
            "Python code test", "Python code write"
        )
        assert 0 < similarity < 1

        # 完全不同
        similarity = retriever._calculate_content_similarity(
            "Python code", "Java architecture"
        )
        assert similarity < 1.0

        # 空文本
        similarity = retriever._calculate_content_similarity("", "test")
        assert similarity == 0.0

    def test_calculate_time_freshness(self):
        """测试时间新鲜度计算"""
        retriever = SmartRetriever()

        # 今天创建的记忆
        freshness = retriever._calculate_time_freshness(datetime.now().isoformat())
        assert freshness == 100.0

        # 30天前创建的记忆
        old_date = (datetime.now() - timedelta(days=30)).isoformat()
        freshness = retriever._calculate_time_freshness(old_date)
        assert freshness < 100.0

        # 空时间
        freshness = retriever._calculate_time_freshness("")
        assert freshness == 50.0

    def test_calculate_usage_frequency(self):
        """测试使用频率计算"""
        retriever = SmartRetriever()

        # 未使用的记忆
        frequency = retriever._calculate_usage_frequency("unknown_id")
        assert frequency == 0.0

        # 使用过的记忆
        retriever._usage_stats["test_id"] = 5
        frequency = retriever._calculate_usage_frequency("test_id")
        assert frequency == 50.0

        # 使用次数超过10次
        retriever._usage_stats["popular_id"] = 15
        frequency = retriever._calculate_usage_frequency("popular_id")
        assert frequency == 100.0

    def test_update_usage_stats(self):
        """测试使用统计更新"""
        retriever = SmartRetriever()

        retriever._update_usage_stats("test_id")
        assert retriever._usage_stats["test_id"] == 1

        retriever._update_usage_stats("test_id")
        assert retriever._usage_stats["test_id"] == 2

    def test_semantic_search(self, retriever_with_memories):
        """测试语义检索"""
        retriever = retriever_with_memories

        results = retriever.semantic_search("Python代码测试", limit=5)

        assert len(results) > 0
        # 第一个结果应该是最相关的
        assert any("python" in m.tags or "testing" in m.tags for m in results)

    def test_semantic_search_empty_query(self, retriever_with_memories):
        """测试空查询"""
        retriever = retriever_with_memories

        results = retriever.semantic_search("", limit=5)

        # 空查询应该返回空结果或所有结果
        assert isinstance(results, list)

    def test_recommend_knowledge(self, retriever_with_memories):
        """测试知识推荐"""
        retriever = retriever_with_memories

        context = RecommendationContext(
            task_description="编写Python单元测试",
            current_step="创建测试文件",
            tool_calls=["read_code", "edit_file"],
            errors=[],
        )

        results = retriever.recommend_knowledge(context, limit=3)

        assert len(results) > 0
        assert isinstance(results[0], Memory)

    def test_recommend_knowledge_with_errors(self, retriever_with_memories):
        """测试带错误的知识推荐"""
        retriever = retriever_with_memories

        context = RecommendationContext(
            task_description="修复代码错误",
            current_step="分析错误",
            tool_calls=[],
            errors=["SyntaxError: invalid syntax"],
        )

        results = retriever.recommend_knowledge(context, limit=3)

        assert isinstance(results, list)

    def test_find_related_knowledge(self, retriever_with_memories):
        """测试查找相关知识"""
        retriever = retriever_with_memories

        # 查找与memory_1相关的知识
        results = retriever.find_related_knowledge("memory_1", limit=3)

        assert isinstance(results, list)
        # 不应该包含自身
        assert all(m.id != "memory_1" for m in results)

    def test_find_related_knowledge_not_found(self, retriever_with_memories):
        """测试查找不存在的记忆的相关知识"""
        retriever = retriever_with_memories

        results = retriever.find_related_knowledge("nonexistent_id", limit=3)

        assert results == []

    def test_load_memories_by_type(self, retriever_with_memories):
        """测试按类型加载记忆"""
        retriever = retriever_with_memories

        memories = retriever._load_memories_by_type("project_long_term")

        assert len(memories) == 3
        assert all(isinstance(m, Memory) for m in memories)

    def test_load_memories_by_type_invalid(self):
        """测试加载无效类型的记忆"""
        retriever = SmartRetriever()

        memories = retriever._load_memories_by_type("invalid_type")

        assert memories == []

    def test_load_memory_by_id(self, retriever_with_memories):
        """测试按ID加载记忆"""
        retriever = retriever_with_memories

        memory = retriever._load_memory_by_id("memory_1")

        assert memory is not None
        assert memory.id == "memory_1"

    def test_load_memory_by_id_not_found(self, retriever_with_memories):
        """测试加载不存在的记忆"""
        retriever = retriever_with_memories

        memory = retriever._load_memory_by_id("nonexistent_id")

        assert memory is None

    def test_retrieve_candidates(self, retriever_with_memories):
        """测试检索候选记忆"""
        retriever = retriever_with_memories

        candidates = retriever._retrieve_candidates(
            ["python", "code"], ["project_long_term"]
        )

        assert len(candidates) > 0
        # 应该包含带有python或code标签的记忆
        assert any("python" in m.tags or "code" in m.tags for m in candidates)

    def test_retrieve_candidates_no_tags(self, retriever_with_memories):
        """测试无标签检索候选记忆"""
        retriever = retriever_with_memories

        candidates = retriever._retrieve_candidates([], ["project_long_term"])

        # 无标签时应该返回所有记忆
        assert len(candidates) == 3

    def test_calculate_relevance_score(self, retriever_with_memories):
        """测试相关性得分计算"""
        retriever = retriever_with_memories

        memory = Memory(
            id="test",
            type="project_long_term",
            tags=["python", "code"],
            content="Python code testing best practices",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )

        query = SemanticQuery(
            query_text="Python code",
            extracted_keywords=["python", "code"],
            expanded_tags=["python", "code", "coding"],
            intent="general",
        )

        score = retriever._calculate_relevance_score(memory, query)

        assert isinstance(score, RelevanceScore)
        assert score.tag_match > 0
        assert score.content_similarity > 0  # 现在应该能正确计算
        assert score.time_freshness > 0
        assert score.total > 0

    def test_extract_keywords_from_context(self):
        """测试从上下文提取关键词"""
        retriever = SmartRetriever()

        context = RecommendationContext(
            task_description="编写Python测试",
            current_step="创建测试文件",
            tool_calls=["read_code"],
            errors=["ImportError"],
        )

        keywords = retriever._extract_keywords_from_context(context)

        assert len(keywords) > 0
        assert isinstance(keywords, list)

    def test_calculate_recommendation_score(self, retriever_with_memories):
        """测试推荐得分计算"""
        retriever = retriever_with_memories

        memory = Memory(
            id="test",
            type="project_long_term",
            tags=["python", "testing"],
            content="Python测试最佳实践",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )

        context = RecommendationContext(
            task_description="编写Python测试",
            current_step="创建测试",
            tool_calls=[],
            errors=[],
        )

        score = retriever._calculate_recommendation_score(
            memory, context, ["python", "测试"]
        )

        assert isinstance(score, float)
        assert score >= 0


class TestSmartRetrieverIntegration:
    """SmartRetriever集成测试"""

    @pytest.fixture
    def temp_memory_setup(self):
        """创建完整的临时记忆环境"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / ".jarvis" / "memory"
            project_dir.mkdir(parents=True)

            # 创建多种类型的记忆
            memories = [
                {
                    "id": "arch_1",
                    "type": "project_long_term",
                    "tags": ["architecture", "design", "pattern"],
                    "content": "软件架构设计模式：单例模式、工厂模式、观察者模式",
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                },
                {
                    "id": "test_1",
                    "type": "project_long_term",
                    "tags": ["testing", "pytest", "unit"],
                    "content": "单元测试最佳实践：使用pytest框架，编写独立的测试用例",
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                },
                {
                    "id": "code_1",
                    "type": "project_long_term",
                    "tags": ["code", "python", "best_practice"],
                    "content": "Python编码规范：遵循PEP8，使用类型注解",
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                },
            ]

            for memory in memories:
                memory_file = project_dir / f"{memory['id']}.json"
                with open(memory_file, "w", encoding="utf-8") as f:
                    json.dump(memory, f, ensure_ascii=False)

            retriever = SmartRetriever()
            retriever.project_memory_dir = project_dir

            yield retriever

    def test_full_search_workflow(self, temp_memory_setup):
        """测试完整的搜索工作流"""
        retriever = temp_memory_setup

        # 1. 语义搜索
        results = retriever.semantic_search("如何编写单元测试", limit=3)
        assert len(results) > 0

        # 2. 知识推荐
        context = RecommendationContext(
            task_description="重构代码架构",
            current_step="设计新架构",
            tool_calls=[],
            errors=[],
        )
        recommendations = retriever.recommend_knowledge(context, limit=3)
        assert len(recommendations) > 0

        # 3. 查找相关知识
        if results:
            related = retriever.find_related_knowledge(results[0].id, limit=3)
            assert isinstance(related, list)

    def test_search_relevance_ordering(self, temp_memory_setup):
        """测试搜索结果的相关性排序"""
        retriever = temp_memory_setup

        # 搜索测试相关内容
        results = retriever.semantic_search("pytest单元测试", limit=3)

        if len(results) >= 2:
            # 第一个结果应该比后面的更相关
            # 检查第一个结果是否包含更多相关标签
            first_tags = set(results[0].tags)
            relevant_tags = {"testing", "pytest", "unit", "test"}
            first_match = len(first_tags & relevant_tags)
            assert first_match > 0

    def test_usage_stats_persistence(self, temp_memory_setup):
        """测试使用统计的持久性"""
        retriever = temp_memory_setup

        # 执行多次搜索
        for _ in range(3):
            retriever.semantic_search("Python代码", limit=1)

        # 检查使用统计是否更新
        assert len(retriever._usage_stats) > 0
        assert any(count > 0 for count in retriever._usage_stats.values())
