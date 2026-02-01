"""ExperienceAccumulator 测试模块。"""

from jarvis.jarvis_digital_twin.continuous_learning import (
    ContextSimilarityMatcher,
    Experience,
    ExperienceAccumulator,
    ExperienceType,
    KeywordMatcher,
    OutcomeMatcher,
)


class TestExperienceRecord:
    """ExperienceRecord 测试类。"""

    def test_content_hash_computed(self):
        """测试内容哈希自动计算。"""
        from jarvis.jarvis_digital_twin.continuous_learning.experience_accumulator import (
            ExperienceRecord,
        )

        exp = Experience(
            id="test-1",
            type=ExperienceType.SUCCESS,
            context="测试上下文",
            outcome="测试结果",
        )
        record = ExperienceRecord(experience=exp)
        assert record.content_hash != ""
        assert len(record.content_hash) == 32  # MD5 hash length

    def test_same_content_same_hash(self):
        """测试相同内容产生相同哈希。"""
        from jarvis.jarvis_digital_twin.continuous_learning.experience_accumulator import (
            ExperienceRecord,
        )

        exp1 = Experience(
            id="1", type=ExperienceType.SUCCESS, context="ctx", outcome="out"
        )
        exp2 = Experience(
            id="2", type=ExperienceType.SUCCESS, context="ctx", outcome="out"
        )
        r1 = ExperienceRecord(experience=exp1)
        r2 = ExperienceRecord(experience=exp2)
        assert r1.content_hash == r2.content_hash


class TestKeywordMatcher:
    """KeywordMatcher 测试类。"""

    def test_empty_context(self):
        """测试空上下文返回空列表。"""
        matcher = KeywordMatcher()
        assert matcher.match("") == []
        assert matcher.match(None) == []

    def test_empty_experiences(self):
        """测试无经验时返回空列表。"""
        matcher = KeywordMatcher()
        assert matcher.match("some context") == []

    def test_keyword_matching(self):
        """测试关键词匹配。"""
        matcher = KeywordMatcher()
        exp1 = Experience(
            id="1", type=ExperienceType.SUCCESS, context="Python编程", outcome="成功"
        )
        exp2 = Experience(
            id="2", type=ExperienceType.FAILURE, context="Java开发", outcome="失败"
        )
        matcher.set_experiences([exp1, exp2])
        results = matcher.match("Python")
        assert len(results) == 1
        assert results[0].id == "1"

    def test_multiple_keyword_matching(self):
        """测试多关键词匹配排序。"""
        matcher = KeywordMatcher()
        exp1 = Experience(
            id="1", type=ExperienceType.SUCCESS, context="Python编程", outcome="成功"
        )
        exp2 = Experience(
            id="2",
            type=ExperienceType.SUCCESS,
            context="Python开发成功",
            outcome="完成",
        )
        matcher.set_experiences([exp1, exp2])
        results = matcher.match("Python 成功")
        assert len(results) == 2
        # 两个都匹配了关键词
        assert all(r.id in ["1", "2"] for r in results)


class TestContextSimilarityMatcher:
    """ContextSimilarityMatcher 测试类。"""

    def test_empty_context(self):
        """测试空上下文。"""
        matcher = ContextSimilarityMatcher()
        assert matcher.match("") == []

    def test_similarity_computation(self):
        """测试相似度计算。"""
        matcher = ContextSimilarityMatcher(similarity_threshold=0.3)
        sim = matcher._compute_similarity("hello world", "hello there")
        assert 0 < sim < 1

    def test_identical_texts(self):
        """测试相同文本相似度为1。"""
        matcher = ContextSimilarityMatcher()
        sim = matcher._compute_similarity("hello world", "hello world")
        assert sim == 1.0

    def test_completely_different(self):
        """测试完全不同文本相似度为0。"""
        matcher = ContextSimilarityMatcher()
        sim = matcher._compute_similarity("abc", "xyz")
        assert sim == 0.0

    def test_similarity_matching(self):
        """测试相似度匹配。"""
        matcher = ContextSimilarityMatcher(similarity_threshold=0.2)
        exp = Experience(
            id="1",
            type=ExperienceType.SUCCESS,
            context="Python programming development",
            outcome="success",
        )
        matcher.set_experiences([exp])
        results = matcher.match("Python programming")
        assert len(results) >= 1


class TestOutcomeMatcher:
    """OutcomeMatcher 测试类。"""

    def test_empty_context(self):
        """测试空上下文。"""
        matcher = OutcomeMatcher()
        assert matcher.match("") == []

    def test_priority_for_error_context(self):
        """测试错误上下文优先返回失败经验。"""
        matcher = OutcomeMatcher()
        exp_success = Experience(
            id="1", type=ExperienceType.SUCCESS, context="成功", outcome="ok"
        )
        exp_failure = Experience(
            id="2", type=ExperienceType.FAILURE, context="失败", outcome="error"
        )
        matcher.set_experiences([exp_success, exp_failure])
        results = matcher.match("遇到错误")
        assert results[0].type == ExperienceType.FAILURE

    def test_priority_for_success_context(self):
        """测试成功上下文优先返回成功经验。"""
        matcher = OutcomeMatcher()
        exp_success = Experience(
            id="1", type=ExperienceType.SUCCESS, context="成功", outcome="ok"
        )
        exp_failure = Experience(
            id="2", type=ExperienceType.FAILURE, context="失败", outcome="error"
        )
        matcher.set_experiences([exp_success, exp_failure])
        results = matcher.match("成功完成")
        assert results[0].type == ExperienceType.SUCCESS


class TestExperienceAccumulator:
    """ExperienceAccumulator 测试类。"""

    def test_init(self):
        """测试初始化。"""
        acc = ExperienceAccumulator()
        assert acc.get_experience_count() == 0

    def test_record_experience(self):
        """测试记录经验。"""
        acc = ExperienceAccumulator()
        exp = acc.record_experience(
            context="Python开发",
            outcome="成功完成",
            exp_type=ExperienceType.SUCCESS,
            lessons=["使用虚拟环境"],
        )
        assert exp.id is not None
        assert exp.type == ExperienceType.SUCCESS
        assert acc.get_experience_count() == 1

    def test_record_with_tags(self):
        """测试带标签记录经验。"""
        acc = ExperienceAccumulator()
        exp = acc.record_experience(
            context="测试",
            outcome="结果",
            exp_type=ExperienceType.SUCCESS,
            tags=["python", "testing"],
        )
        assert "tags" in exp.metadata
        assert "python" in exp.metadata["tags"]

    def test_get_experience(self):
        """测试获取经验。"""
        acc = ExperienceAccumulator()
        exp = acc.record_experience("ctx", "out", ExperienceType.SUCCESS)
        retrieved = acc.get_experience(exp.id)
        assert retrieved is not None
        assert retrieved.id == exp.id

    def test_get_nonexistent_experience(self):
        """测试获取不存在的经验。"""
        acc = ExperienceAccumulator()
        assert acc.get_experience("nonexistent") is None

    def test_search_experiences(self):
        """测试搜索经验。"""
        acc = ExperienceAccumulator()
        acc.record_experience("Python编程", "成功", ExperienceType.SUCCESS)
        acc.record_experience("Java开发", "失败", ExperienceType.FAILURE)
        results = acc.search_experiences("Python")
        assert len(results) == 1
        assert "Python" in results[0].context

    def test_search_by_type(self):
        """测试按类型搜索。"""
        acc = ExperienceAccumulator()
        acc.record_experience("ctx1", "out1", ExperienceType.SUCCESS)
        acc.record_experience("ctx2", "out2", ExperienceType.FAILURE)
        results = acc.search_experiences("ctx", exp_type=ExperienceType.SUCCESS)
        assert len(results) == 1
        assert results[0].type == ExperienceType.SUCCESS

    def test_add_lesson(self):
        """测试添加教训。"""
        acc = ExperienceAccumulator()
        exp = acc.record_experience("ctx", "out", ExperienceType.SUCCESS)
        assert acc.add_lesson(exp.id, "新教训")
        updated = acc.get_experience(exp.id)
        assert "新教训" in updated.lessons

    def test_add_duplicate_lesson(self):
        """测试添加重复教训。"""
        acc = ExperienceAccumulator()
        exp = acc.record_experience(
            "ctx", "out", ExperienceType.SUCCESS, lessons=["教训1"]
        )
        assert not acc.add_lesson(exp.id, "教训1")  # 重复不添加

    def test_find_similar_experience(self):
        """测试查找相似经验。"""
        acc = ExperienceAccumulator()
        acc.record_experience("Python编程开发", "成功", ExperienceType.SUCCESS)
        acc.record_experience("Java企业开发", "完成", ExperienceType.SUCCESS)
        results = acc.find_similar_experience("Python编程")
        assert len(results) >= 1

    def test_extract_methodology_empty(self):
        """测试空经验提取方法论。"""
        acc = ExperienceAccumulator()
        methodology = acc.extract_methodology([])
        assert methodology["patterns"] == []
        assert methodology["best_practices"] == []

    def test_extract_methodology(self):
        """测试提取方法论。"""
        acc = ExperienceAccumulator()
        exp1 = acc.record_experience(
            "ctx1", "成功做法", ExperienceType.SUCCESS, lessons=["教训1"]
        )
        exp2 = acc.record_experience(
            "ctx2", "失败原因", ExperienceType.FAILURE, lessons=["教训2"]
        )
        exp3 = acc.record_experience("ctx3", "洞察内容", ExperienceType.INSIGHT)
        methodology = acc.extract_methodology([exp1, exp2, exp3])
        assert len(methodology["best_practices"]) >= 1
        assert len(methodology["anti_patterns"]) >= 1
        assert len(methodology["patterns"]) >= 1

    def test_apply_experience(self):
        """测试应用经验。"""
        acc = ExperienceAccumulator()
        exp = acc.record_experience(
            "Python development project",
            "use pytest",
            ExperienceType.SUCCESS,
            lessons=["write tests"],
        )
        result = acc.apply_experience(exp, "Python development project work")
        assert result["applicable"]
        assert len(result["suggestions"]) >= 1

    def test_apply_failure_experience(self):
        """测试应用失败经验。"""
        acc = ExperienceAccumulator()
        exp = acc.record_experience(
            "deployment problem issue", "config error", ExperienceType.FAILURE
        )
        result = acc.apply_experience(exp, "deployment problem")
        assert result["applicable"]
        assert len(result["warnings"]) >= 1

    def test_get_experiences_by_type(self):
        """测试按类型获取经验。"""
        acc = ExperienceAccumulator()
        acc.record_experience("ctx1", "out1", ExperienceType.SUCCESS)
        acc.record_experience("ctx2", "out2", ExperienceType.FAILURE)
        acc.record_experience("ctx3", "out3", ExperienceType.SUCCESS)
        results = acc.get_experiences_by_type(ExperienceType.SUCCESS)
        assert len(results) == 2
        assert all(e.type == ExperienceType.SUCCESS for e in results)

    def test_get_experiences_by_tag(self):
        """测试按标签获取经验。"""
        acc = ExperienceAccumulator()
        acc.record_experience("ctx1", "out1", ExperienceType.SUCCESS, tags=["python"])
        acc.record_experience("ctx2", "out2", ExperienceType.SUCCESS, tags=["java"])
        results = acc.get_experiences_by_tag("python")
        assert len(results) == 1

    def test_get_all_experiences(self):
        """测试获取所有经验。"""
        acc = ExperienceAccumulator()
        acc.record_experience("ctx1", "out1", ExperienceType.SUCCESS)
        acc.record_experience("ctx2", "out2", ExperienceType.FAILURE)
        results = acc.get_all_experiences()
        assert len(results) == 2

    def test_verify_experience(self):
        """测试验证经验。"""
        acc = ExperienceAccumulator()
        exp = acc.record_experience("ctx", "out", ExperienceType.SUCCESS)
        assert acc.verify_experience(exp.id)
        updated = acc.get_experience(exp.id)
        assert "verified_at" in updated.metadata

    def test_deprecate_experience(self):
        """测试废弃经验。"""
        acc = ExperienceAccumulator()
        exp = acc.record_experience("ctx", "out", ExperienceType.SUCCESS)
        assert acc.deprecate_experience(exp.id)
        # 废弃后不计入数量
        assert acc.get_experience_count() == 0

    def test_clear_all(self):
        """测试清除所有经验。"""
        acc = ExperienceAccumulator()
        acc.record_experience("ctx1", "out1", ExperienceType.SUCCESS)
        acc.record_experience("ctx2", "out2", ExperienceType.FAILURE)
        acc.clear_all()
        assert acc.get_experience_count() == 0

    def test_get_statistics(self):
        """测试获取统计信息。"""
        acc = ExperienceAccumulator()
        acc.record_experience("ctx1", "out1", ExperienceType.SUCCESS, lessons=["l1"])
        acc.record_experience(
            "ctx2", "out2", ExperienceType.FAILURE, lessons=["l2", "l3"]
        )
        stats = acc.get_statistics()
        assert stats["total_count"] == 2
        assert stats["total_lessons"] == 3
        assert "success" in stats["type_distribution"]

    def test_register_matcher(self):
        """测试注册匹配器。"""
        acc = ExperienceAccumulator()
        matcher = KeywordMatcher()
        acc.register_matcher(matcher)
        stats = acc.get_statistics()
        assert stats["registered_matchers"] == 1

    def test_unregister_matcher(self):
        """测试取消注册匹配器。"""
        acc = ExperienceAccumulator()
        matcher = KeywordMatcher()
        acc.register_matcher(matcher)
        assert acc.unregister_matcher(matcher)
        stats = acc.get_statistics()
        assert stats["registered_matchers"] == 0

    def test_duplicate_experience_updates_lessons(self):
        """测试重复经验更新教训。"""
        acc = ExperienceAccumulator()
        acc.record_experience("ctx", "out", ExperienceType.SUCCESS, lessons=["l1"])
        acc.record_experience("ctx", "out", ExperienceType.SUCCESS, lessons=["l2"])
        # 应该只有一条经验，但教训合并
        assert acc.get_experience_count() == 1
        all_exp = acc.get_all_experiences()
        assert "l1" in all_exp[0].lessons
        assert "l2" in all_exp[0].lessons

    def test_apply_experience_not_applicable(self):
        """测试应用不相关经验。"""
        acc = ExperienceAccumulator()
        exp = acc.record_experience("完全不同的上下文", "结果", ExperienceType.SUCCESS)
        result = acc.apply_experience(exp, "xyz")
        assert not result["applicable"]

    def test_apply_experience_empty(self):
        """测试空参数应用经验。"""
        acc = ExperienceAccumulator()
        result = acc.apply_experience(None, "context")
        assert not result["applicable"]
        exp = acc.record_experience("ctx", "out", ExperienceType.SUCCESS)
        result = acc.apply_experience(exp, "")
        assert not result["applicable"]
