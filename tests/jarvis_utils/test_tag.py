# -*- coding: utf-8 -*-
"""jarvis_utils.tag 模块单元测试"""


from jarvis.jarvis_utils.tag import ot, ct


class TestTagFunctions:
    """测试标签生成函数"""

    def test_ot_basic(self):
        """测试 ot 函数基本功能"""
        assert ot("test") == "<test>"
        assert ot("div") == "<div>"
        assert ot("span") == "<span>"

    def test_ot_with_underscore(self):
        """测试带下划线的标签名"""
        assert ot("test_tag") == "<test_tag>"
        assert ot("my_tag") == "<my_tag>"

    def test_ot_with_dash(self):
        """测试带连字符的标签名"""
        assert ot("test-tag") == "<test-tag>"
        assert ot("my-tag") == "<my-tag>"

    def test_ct_basic(self):
        """测试 ct 函数基本功能"""
        assert ct("test") == "</test>"
        assert ct("div") == "</div>"
        assert ct("span") == "</span>"

    def test_ct_with_underscore(self):
        """测试带下划线的标签名"""
        assert ct("test_tag") == "</test_tag>"
        assert ct("my_tag") == "</my_tag>"

    def test_ct_with_dash(self):
        """测试带连字符的标签名"""
        assert ct("test-tag") == "</test-tag>"
        assert ct("my-tag") == "</my-tag>"

    def test_ot_ct_pair(self):
        """测试 ot 和 ct 配对使用"""
        tag_name = "message"
        open_tag = ot(tag_name)
        close_tag = ct(tag_name)
        assert open_tag == "<message>"
        assert close_tag == "</message>"

    def test_empty_string(self):
        """测试空字符串标签名"""
        assert ot("") == "<>"
        assert ct("") == "</>"

    def test_special_characters(self):
        """测试特殊字符"""
        assert ot("test@123") == "<test@123>"
        assert ct("test@123") == "</test@123>"

