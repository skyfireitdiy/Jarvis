# -*- coding: utf-8 -*-
"""jarvis_c2rust.llm_module_agent 模块单元测试"""


from jarvis.jarvis_c2rust.llm_module_agent import _sanitize_mod_name


class TestSanitizeModName:
    """测试 _sanitize_mod_name 函数"""

    def test_simple_name(self):
        """测试简单名称"""
        result = _sanitize_mod_name("test")
        assert result == "test"

    def test_name_with_colons(self):
        """测试包含双冒号的名称"""
        result = _sanitize_mod_name("test::module::name")
        assert result == "test__module__name"

    def test_name_with_special_chars(self):
        """测试包含特殊字符的名称"""
        result = _sanitize_mod_name("test-module@name")
        assert result == "test_module_name"

    def test_name_with_spaces(self):
        """测试包含空格的名称"""
        result = _sanitize_mod_name("test module name")
        assert result == "test_module_name"

    def test_uppercase_name(self):
        """测试大写名称（应转换为小写）"""
        result = _sanitize_mod_name("TEST_MODULE")
        assert result == "test_module"

    def test_mixed_case_name(self):
        """测试混合大小写名称"""
        result = _sanitize_mod_name("TestModuleName")
        assert result == "testmodulename"

    def test_name_with_numbers(self):
        """测试包含数字的名称"""
        result = _sanitize_mod_name("test123module")
        assert result == "test123module"

    def test_name_with_leading_underscores(self):
        """测试前导下划线（应被去除）"""
        result = _sanitize_mod_name("___test")
        assert result == "test"

    def test_name_with_trailing_underscores(self):
        """测试尾随下划线（应被去除）"""
        result = _sanitize_mod_name("test___")
        assert result == "test"

    def test_name_with_both_underscores(self):
        """测试前后都有下划线"""
        result = _sanitize_mod_name("___test___")
        assert result == "test"

    def test_empty_string(self):
        """测试空字符串（应返回 'mod'）"""
        result = _sanitize_mod_name("")
        assert result == "mod"

    def test_none(self):
        """测试 None（应返回 'mod'）"""
        result = _sanitize_mod_name(None)
        assert result == "mod"

    def test_long_name(self):
        """测试超长名称（应截断到80字符）"""
        long_name = "a" * 100
        result = _sanitize_mod_name(long_name)
        assert len(result) == 80
        assert result == "a" * 80

    def test_long_name_with_special_chars(self):
        """测试超长名称包含特殊字符"""
        long_name = "test-" * 30  # 150 characters
        result = _sanitize_mod_name(long_name)
        assert len(result) <= 80
        # 特殊字符会被替换为下划线，所以结果会是 test_test_test_...
        assert result.startswith("test")

    def test_only_special_chars(self):
        """测试只有特殊字符（应返回 'mod'）"""
        result = _sanitize_mod_name("---")
        assert result == "mod"

    def test_only_underscores(self):
        """测试只有下划线（应返回 'mod'）"""
        result = _sanitize_mod_name("___")
        assert result == "mod"

    def test_complex_name(self):
        """测试复杂名称"""
        result = _sanitize_mod_name("MyModule::SubModule::Function123")
        assert result == "mymodule__submodule__function123"

    def test_name_with_unicode(self):
        """测试包含 Unicode 字符的名称"""
        result = _sanitize_mod_name("测试模块")
        # Unicode 字符的 isalnum() 返回 True，所以会被保留并转换为小写
        # 如果所有字符都是 Unicode，结果可能保留原样或变成 "mod"
        assert isinstance(result, str)
        assert len(result) > 0

