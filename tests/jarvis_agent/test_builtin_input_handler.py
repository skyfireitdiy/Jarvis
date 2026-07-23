# -*- coding: utf-8 -*-
"""测试 builtin_input_handler 中的工具函数"""

from jarvis.jarvis_agent.builtin_input_handler import extract_tags_from_text


class TestExtractTagsFromText:
    """测试 extract_tags_from_text 函数"""

    def test_empty_input(self):
        """测试空输入"""
        assert extract_tags_from_text("") == []
        assert extract_tags_from_text(None) == []

    def test_no_tags(self):
        """测试无标签的纯文本"""
        text = "这是一个普通的用户输入，没有任何标签"
        assert extract_tags_from_text(text) == []

    def test_single_tag(self):
        """测试单个标签"""
        text = "请帮我分析代码 '<rule:python_best_practices>'"
        assert extract_tags_from_text(text) == ["rule:python_best_practices"]

    def test_multiple_tags(self):
        """测试多个标签"""
        text = "'<rule:code_style>' 和 '<rule:security>' 都很重要"
        assert extract_tags_from_text(text) == ["rule:code_style", "rule:security"]

    def test_multimodal_list_format(self):
        """测试多模态内容（列表格式）"""
        content = [
            {"type": "text", "text": "请加载规则 '<rule:test_rule>'"},
            {"type": "image", "url": "http://example.com/image.png"},
        ]
        assert extract_tags_from_text(content) == ["rule:test_rule"]

    def test_multimodal_multiple_text_blocks(self):
        """测试多模态内容中的多个文本块"""
        content = [
            {"type": "text", "text": "'<rule:first>'"},
            {"type": "text", "text": "和 '<rule:second>'"},
        ]
        assert extract_tags_from_text(content) == ["rule:first", "rule:second"]

    def test_multimodal_empty_list(self):
        """测试空列表输入"""
        assert extract_tags_from_text([]) == []

    def test_various_tag_types(self):
        """测试不同类型的标签"""
        text = "'<Pin>' '<SetConfig>' '<rule:custom_rule>' '<AddDir>'"
        assert extract_tags_from_text(text) == [
            "Pin",
            "SetConfig",
            "rule:custom_rule",
            "AddDir",
        ]

    def test_tag_without_quotes(self):
        """测试不带单引号的标签（不应被匹配）"""
        text = "这个 <rule:test> 不会被匹配，因为没有单引号"
        assert extract_tags_from_text(text) == []

    def test_incomplete_tag(self):
        """测试不完整的标签格式"""
        text = "'<rule:incomplete"  # 缺少闭合的 > 和 >'
        assert extract_tags_from_text(text) == []
