"""智能问答引擎测试"""

import tempfile
from pathlib import Path

from jarvis.jarvis_smart_advisor.qa_engine import (
    Answer,
    QAEngine,
    Question,
    QuestionCategory,
)


class TestQuestion:
    """Question数据类测试"""

    def test_question_default_values(self):
        """测试Question默认值"""
        question = Question(text="测试问题")
        assert question.text == "测试问题"
        assert question.category == QuestionCategory.GENERAL
        assert question.keywords == []
        assert question.intent == ""
        assert question.entities == []

    def test_question_with_all_fields(self):
        """测试Question所有字段"""
        question = Question(
            text="这个项目有哪些模块？",
            category=QuestionCategory.PROJECT_STRUCTURE,
            keywords=["项目", "模块"],
            intent="list_components",
            entities=["jarvis"],
        )
        assert question.text == "这个项目有哪些模块？"
        assert question.category == QuestionCategory.PROJECT_STRUCTURE
        assert "项目" in question.keywords
        assert question.intent == "list_components"
        assert "jarvis" in question.entities


class TestAnswer:
    """Answer数据类测试"""

    def test_answer_default_values(self):
        """测试Answer默认值"""
        answer = Answer(text="测试答案")
        assert answer.text == "测试答案"
        assert answer.confidence == 0.0
        assert answer.sources == []
        assert answer.related_knowledge == []

    def test_answer_with_all_fields(self):
        """测试Answer所有字段"""
        answer = Answer(
            text="这是答案",
            confidence=0.85,
            sources=["知识图谱: module1"],
            related_knowledge=["相关知识1"],
        )
        assert answer.text == "这是答案"
        assert answer.confidence == 0.85
        assert len(answer.sources) == 1
        assert len(answer.related_knowledge) == 1


class TestQuestionCategory:
    """QuestionCategory枚举测试"""

    def test_all_categories_exist(self):
        """测试所有类别存在"""
        assert QuestionCategory.PROJECT_STRUCTURE.value == "project_structure"
        assert QuestionCategory.CODE_FUNCTION.value == "code_function"
        assert QuestionCategory.BEST_PRACTICE.value == "best_practice"
        assert QuestionCategory.HISTORY_DECISION.value == "history_decision"
        assert QuestionCategory.GENERAL.value == "general"


class TestQAEngineInit:
    """QAEngine初始化测试"""

    def test_init_default_project_dir(self):
        """测试默认项目目录"""
        engine = QAEngine()
        assert engine.project_dir == Path(".")

    def test_init_custom_project_dir(self):
        """测试自定义项目目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = QAEngine(tmpdir)
            assert engine.project_dir == Path(tmpdir)

    def test_lazy_load_knowledge_graph(self):
        """测试懒加载知识图谱"""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = QAEngine(tmpdir)
            assert engine._knowledge_graph is None
            # 访问属性触发懒加载
            kg = engine.knowledge_graph
            assert kg is not None
            assert engine._knowledge_graph is not None

    def test_lazy_load_smart_retriever(self):
        """测试懒加载智能检索器"""
        engine = QAEngine()
        assert engine._smart_retriever is None
        # 访问属性触发懒加载
        sr = engine.smart_retriever
        assert sr is not None
        assert engine._smart_retriever is not None


class TestQAEngineExtractKeywords:
    """QAEngine关键词提取测试"""

    def test_extract_keywords_chinese(self):
        """测试中文关键词提取"""
        engine = QAEngine()
        keywords = engine._extract_keywords("这个项目有哪些模块")
        assert "项目" in keywords
        assert "模块" in keywords
        # 停用词应被过滤
        assert "这" not in keywords
        assert "有" not in keywords

    def test_extract_keywords_english(self):
        """测试英文关键词提取"""
        engine = QAEngine()
        keywords = engine._extract_keywords("What modules does this project have")
        assert "modules" in keywords
        assert "project" in keywords
        # 停用词应被过滤
        assert "the" not in keywords
        assert "does" not in keywords

    def test_extract_keywords_mixed(self):
        """测试中英混合关键词提取"""
        engine = QAEngine()
        keywords = engine._extract_keywords("jarvis项目的module结构")
        assert "jarvis" in keywords
        assert "项目" in keywords
        assert "module" in keywords
        assert "结构" in keywords

    def test_extract_keywords_empty(self):
        """测试空文本"""
        engine = QAEngine()
        keywords = engine._extract_keywords("")
        assert keywords == []

    def test_extract_keywords_short_words_filtered(self):
        """测试短词被过滤"""
        engine = QAEngine()
        keywords = engine._extract_keywords("a b c test")
        assert "test" in keywords
        assert "a" not in keywords
        assert "b" not in keywords


class TestQAEngineIdentifyCategory:
    """QAEngine类别识别测试"""

    def test_identify_project_structure(self):
        """测试识别项目结构问题"""
        engine = QAEngine()
        category = engine._identify_category("这个项目有哪些模块", ["项目", "模块"])
        assert category == QuestionCategory.PROJECT_STRUCTURE

    def test_identify_code_function(self):
        """测试识别代码功能问题"""
        engine = QAEngine()
        category = engine._identify_category("这个函数是做什么的", ["函数"])
        assert category == QuestionCategory.CODE_FUNCTION

    def test_identify_best_practice(self):
        """测试识别最佳实践问题"""
        engine = QAEngine()
        category = engine._identify_category(
            "单元测试的最佳实践是什么", ["单元测试", "最佳实践"]
        )
        assert category == QuestionCategory.BEST_PRACTICE

    def test_identify_history_decision(self):
        """测试识别历史决策问题"""
        engine = QAEngine()
        category = engine._identify_category("为什么选择这个方案", ["选择", "方案"])
        assert category == QuestionCategory.HISTORY_DECISION

    def test_identify_general(self):
        """测试识别通用问题"""
        engine = QAEngine()
        category = engine._identify_category("今天天气好吗", ["天气"])
        assert category == QuestionCategory.GENERAL


class TestQAEngineExtractEntities:
    """QAEngine实体提取测试"""

    def test_extract_module_names(self):
        """测试提取模块名"""
        engine = QAEngine()
        entities = engine._extract_entities("jarvis_smart_advisor模块")
        assert "jarvis_smart_advisor" in entities

    def test_extract_class_names(self):
        """测试提取类名"""
        engine = QAEngine()
        entities = engine._extract_entities("SmartAdvisor类的功能")
        assert "SmartAdvisor" in entities

    def test_extract_mixed_entities(self):
        """测试提取混合实体"""
        engine = QAEngine()
        entities = engine._extract_entities("QAEngine类在qa_engine模块中")
        assert "QAEngine" in entities
        assert "qa_engine" in entities


class TestQAEngineIdentifyIntent:
    """QAEngine意图识别测试"""

    def test_identify_list_components_intent(self):
        """测试识别列出组件意图"""
        engine = QAEngine()
        intent = engine._identify_intent(
            "这个项目有哪些模块",
            QuestionCategory.PROJECT_STRUCTURE,
        )
        assert intent == "list_components"

    def test_identify_locate_component_intent(self):
        """测试识别定位组件意图"""
        engine = QAEngine()
        intent = engine._identify_intent(
            "配置文件在哪里",
            QuestionCategory.PROJECT_STRUCTURE,
        )
        assert intent == "locate_component"

    def test_identify_explain_function_intent(self):
        """测试识别解释功能意图"""
        engine = QAEngine()
        intent = engine._identify_intent(
            "这个函数做什么",
            QuestionCategory.CODE_FUNCTION,
        )
        assert intent == "explain_function"

    def test_identify_provide_guidance_intent(self):
        """测试识别提供指导意图"""
        engine = QAEngine()
        intent = engine._identify_intent(
            "如何实现单元测试",
            QuestionCategory.BEST_PRACTICE,
        )
        assert intent == "provide_guidance"

    def test_identify_explain_decision_intent(self):
        """测试识别解释决策意图"""
        engine = QAEngine()
        intent = engine._identify_intent(
            "为什么选择这个方案",
            QuestionCategory.HISTORY_DECISION,
        )
        assert intent == "explain_decision"


class TestQAEngineAnalyzeQuestion:
    """QAEngine问题分析测试"""

    def test_analyze_question_complete(self):
        """测试完整的问题分析"""
        engine = QAEngine()
        question = engine._analyze_question("这个项目有哪些模块")

        assert question.text == "这个项目有哪些模块"
        assert question.category == QuestionCategory.PROJECT_STRUCTURE
        assert len(question.keywords) > 0
        assert question.intent == "list_components"

    def test_analyze_question_with_entities(self):
        """测试带实体的问题分析"""
        engine = QAEngine()
        question = engine._analyze_question("SmartAdvisor类是做什么的")

        assert "SmartAdvisor" in question.entities
        assert question.category == QuestionCategory.CODE_FUNCTION


class TestQAEngineGetRelevantNodeTypes:
    """QAEngine获取相关节点类型测试"""

    def test_get_node_types_for_project_structure(self):
        """测试项目结构问题的节点类型"""
        from jarvis.jarvis_knowledge_graph import NodeType

        engine = QAEngine()
        node_types = engine._get_relevant_node_types(QuestionCategory.PROJECT_STRUCTURE)

        assert NodeType.FILE in node_types
        assert NodeType.CODE in node_types

    def test_get_node_types_for_best_practice(self):
        """测试最佳实践问题的节点类型"""
        from jarvis.jarvis_knowledge_graph import NodeType

        engine = QAEngine()
        node_types = engine._get_relevant_node_types(QuestionCategory.BEST_PRACTICE)

        assert NodeType.RULE in node_types
        assert NodeType.METHODOLOGY in node_types


class TestQAEngineAnswer:
    """QAEngine回答问题测试"""

    def test_answer_returns_answer_object(self):
        """测试回答返回Answer对象"""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = QAEngine(tmpdir)
            answer = engine.answer("这个项目有哪些模块")

            assert isinstance(answer, Answer)
            assert answer.text != ""
            assert 0 <= answer.confidence <= 1

    def test_answer_no_knowledge_found(self):
        """测试没有找到知识时的回答"""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = QAEngine(tmpdir)
            answer = engine.answer("一个完全无关的问题xyz123")

            assert "抱歉" in answer.text or "没有找到" in answer.text
            assert answer.confidence < 0.5

    def test_answer_includes_sources(self):
        """测试回答包含来源"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建知识图谱目录
            kg_dir = Path(tmpdir) / ".jarvis" / "knowledge_graph"
            kg_dir.mkdir(parents=True, exist_ok=True)

            engine = QAEngine(tmpdir)
            answer = engine.answer("测试问题")

            # 即使没有知识，也应该返回有效的Answer对象
            assert isinstance(answer.sources, list)
            assert isinstance(answer.related_knowledge, list)


class TestQAEngineGenerateAnswer:
    """QAEngine答案生成测试"""

    def test_generate_answer_empty_context(self):
        """测试空上下文生成答案"""
        engine = QAEngine()
        question = Question(text="测试问题")
        context = {"graph_nodes": [], "memories": [], "related_nodes": []}

        answer = engine._generate_answer(question, context)

        assert "抱歉" in answer.text
        assert answer.confidence < 0.5

    def test_generate_answer_with_context(self):
        """测试有上下文生成答案"""
        from jarvis.jarvis_knowledge_graph import KnowledgeNode, NodeType

        engine = QAEngine()
        question = Question(text="测试问题")

        # 创建模拟节点
        node = KnowledgeNode(
            node_id="test_node",
            node_type=NodeType.CONCEPT,
            name="测试概念",
            description="这是一个测试概念的描述",
            source_path="test/path.py",
        )

        context = {
            "graph_nodes": [node],
            "memories": [],
            "related_nodes": [],
        }

        answer = engine._generate_answer(question, context)

        assert "测试概念" in answer.text
        assert answer.confidence > 0.3
        assert len(answer.sources) > 0
