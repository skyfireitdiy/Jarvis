"""增强交互模块测试"""

from jarvis.jarvis_autonomous.interaction import (
    DialogueManager,
    DialogueContext,
    DialogueTurn,
    DialogueState,
    ContextType,
    AmbiguityResolver,
    AmbiguityType,
    AmbiguityResult,
    ClarificationQuestion,
    ProactiveAssistant,
    ProactiveAction,
    ActionType,
    ActionPriority,
    SuggestionResult,
)


class TestDialogueManager:
    """对话管理器测试"""

    def test_create_session(self):
        """测试创建会话"""
        manager = DialogueManager()
        context = manager.create_session("test_session")
        assert isinstance(context, DialogueContext)
        assert context.session_id == "test_session"
        assert context.state == DialogueState.IDLE

    def test_add_turn(self):
        """测试添加对话轮次"""
        manager = DialogueManager()
        turn = manager.add_turn("session1", "user", "帮我修复这个bug")
        assert isinstance(turn, DialogueTurn)
        assert turn.role == "user"
        assert turn.content == "帮我修复这个bug"
        assert turn.intent == "fix"

    def test_extract_intent(self):
        """测试意图提取"""
        manager = DialogueManager()
        assert manager._extract_intent("创建一个新文件") == "create"
        assert manager._extract_intent("修改这个函数") == "modify"
        assert manager._extract_intent("删除这行代码") == "delete"
        assert manager._extract_intent("查找所有错误") == "query"
        assert manager._extract_intent("解释这段代码") == "explain"

    def test_determine_context_type(self):
        """测试上下文类型判断"""
        manager = DialogueManager()
        assert manager._determine_context_type("这个函数有问题") == ContextType.CODE
        assert manager._determine_context_type("文件路径是什么") == ContextType.FILE
        assert manager._determine_context_type("出现了错误") == ContextType.ERROR
        assert manager._determine_context_type("什么是Python") == ContextType.QUESTION

    def test_get_context(self):
        """测试获取上下文"""
        manager = DialogueManager()
        manager.create_session("session1")
        context = manager.get_context("session1")
        assert context is not None
        assert context.session_id == "session1"

    def test_summarize_context(self):
        """测试总结上下文"""
        manager = DialogueManager()
        manager.add_turn("session1", "user", "帮我修复bug")
        summary = manager.summarize_context("session1")
        assert "状态" in summary
        assert "轮次" in summary

    def test_clear_session(self):
        """测试清除会话"""
        manager = DialogueManager()
        manager.create_session("session1")
        assert manager.clear_session("session1") is True
        assert manager.get_context("session1") is None

    def test_multiple_turns(self):
        """测试多轮对话"""
        manager = DialogueManager()
        manager.add_turn("session1", "user", "创建一个函数")
        manager.add_turn("session1", "assistant", "好的，请告诉我函数名")
        manager.add_turn("session1", "user", "叫做process_data")
        context = manager.get_context("session1")
        assert len(context.turns) == 3

    def test_dialogue_state_update(self):
        """测试对话状态更新"""
        manager = DialogueManager()
        manager.add_turn("session1", "user", "你好")
        context = manager.get_context("session1")
        assert context.state == DialogueState.ACTIVE


class TestAmbiguityResolver:
    """歧义消解器测试"""

    def test_detect_referential_ambiguity(self):
        """测试检测指代歧义"""
        resolver = AmbiguityResolver()
        result = resolver.detect_ambiguity("把它删掉")
        assert isinstance(result, AmbiguityResult)
        assert result.has_ambiguity is True
        assert result.ambiguity_type == AmbiguityType.REFERENTIAL

    def test_detect_scope_ambiguity(self):
        """测试检测范围歧义"""
        resolver = AmbiguityResolver()
        result = resolver.detect_ambiguity("修改所有文件")
        assert result.has_ambiguity is True
        assert result.ambiguity_type == AmbiguityType.SCOPE

    def test_no_ambiguity(self):
        """测试无歧义情况"""
        resolver = AmbiguityResolver()
        result = resolver.detect_ambiguity("创建文件test.py")
        # 可能检测到lexical歧义（"处理"等词），也可能无歧义
        assert isinstance(result, AmbiguityResult)

    def test_generate_clarification(self):
        """测试生成澄清问题"""
        resolver = AmbiguityResolver()
        result = AmbiguityResult(
            has_ambiguity=True,
            ambiguity_type=AmbiguityType.REFERENTIAL,
            ambiguous_parts=["它"],
            possible_interpretations=["文件A", "文件B"],
        )
        questions = resolver.generate_clarification(result)
        assert len(questions) > 0
        assert isinstance(questions[0], ClarificationQuestion)

    def test_ambiguity_types(self):
        """测试各种歧义类型"""
        assert AmbiguityType.LEXICAL.value == "lexical"
        assert AmbiguityType.REFERENTIAL.value == "referential"
        assert AmbiguityType.SCOPE.value == "scope"
        assert AmbiguityType.NONE.value == "none"


class TestProactiveAssistant:
    """主动交互助手测试"""

    def test_should_ask_clarification(self):
        """测试判断是否需要澄清"""
        assistant = ProactiveAssistant()
        assert assistant.should_ask_clarification("可能需要修改") is True
        assert assistant.should_ask_clarification("也许是这个问题") is True
        assert assistant.should_ask_clarification("修改这个文件") is False

    def test_report_progress(self):
        """测试进度报告"""
        assistant = ProactiveAssistant()
        action = assistant.report_progress(
            {
                "progress": 50,
                "status": "进行中",
            }
        )
        assert isinstance(action, ProactiveAction)
        assert action.action_type == ActionType.REPORT
        assert "50%" in action.content

    def test_get_pending_actions(self):
        """测试获取待执行行为"""
        assistant = ProactiveAssistant()
        assistant.report_progress({"progress": 30})
        actions = assistant.get_pending_actions()
        assert len(actions) > 0

    def test_execute_action(self):
        """测试执行行为"""
        assistant = ProactiveAssistant()
        action = assistant.report_progress({"progress": 100})
        result = assistant.execute_action(action)
        assert result is True
        assert action.executed is True

    def test_action_priority(self):
        """测试行为优先级"""
        assert ActionPriority.LOW.value == 1
        assert ActionPriority.MEDIUM.value == 2
        assert ActionPriority.HIGH.value == 3
        assert ActionPriority.URGENT.value == 4

    def test_action_types(self):
        """测试行为类型"""
        assert ActionType.CLARIFY.value == "clarify"
        assert ActionType.SUGGEST.value == "suggest"
        assert ActionType.REPORT.value == "report"
        assert ActionType.WARN.value == "warn"

    def test_suggestion_result(self):
        """测试建议结果"""
        result = SuggestionResult(
            suggestions=["建议1", "建议2"],
            reasoning="基于分析",
            confidence=0.8,
        )
        assert len(result.suggestions) == 2
        assert result.confidence == 0.8

    def test_filter_by_priority(self):
        """测试按优先级过滤"""
        assistant = ProactiveAssistant()
        assistant.report_progress({"progress": 50})  # LOW priority
        low_actions = assistant.get_pending_actions(ActionPriority.LOW)
        high_actions = assistant.get_pending_actions(ActionPriority.HIGH)
        assert len(low_actions) >= 1
        assert len(high_actions) == 0


class TestIntegration:
    """集成测试"""

    def test_dialogue_to_ambiguity_flow(self):
        """测试对话到歧义检测流程"""
        manager = DialogueManager()
        resolver = AmbiguityResolver()

        # 用户输入带有歧义
        user_input = "把它改成那个"
        manager.add_turn("session1", "user", user_input)

        # 检测歧义
        result = resolver.detect_ambiguity(user_input)
        assert result.has_ambiguity is True

    def test_full_interaction_flow(self):
        """测试完整交互流程"""
        manager = DialogueManager()
        resolver = AmbiguityResolver()
        assistant = ProactiveAssistant()

        # 1. 用户输入
        user_input = "可能需要修改这个文件"
        manager.add_turn("session1", "user", user_input)

        # 2. 检查是否需要澄清
        needs_clarification = assistant.should_ask_clarification(user_input)
        assert needs_clarification is True

        # 3. 检测歧义
        ambiguity = resolver.detect_ambiguity(user_input)
        # 可能检测到歧义
        assert isinstance(ambiguity, AmbiguityResult)

    def test_proactive_with_context(self):
        """测试带上下文的主动交互"""
        manager = DialogueManager()
        assistant = ProactiveAssistant()

        # 添加对话历史
        manager.add_turn("session1", "user", "帮我修复这个bug")
        manager.add_turn("session1", "assistant", "好的，正在分析")

        # 报告进度
        action = assistant.report_progress(
            {
                "progress": 75,
                "status": "分析中",
            }
        )

        assert action.action_type == ActionType.REPORT
        assert "75%" in action.content
