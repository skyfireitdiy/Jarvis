"""
CaseInsensitiveDict的单元测试

测试CaseInsensitiveDict类的所有功能，包括边界情况和异常处理。
"""

import pytest

from jarvis.jarvis_utils.collections import CaseInsensitiveDict


class TestCaseInsensitiveDict:
    """测试CaseInsensitiveDict类"""

    def test_initialization_empty(self):
        """测试空字典初始化"""
        d = CaseInsensitiveDict()
        assert len(d) == 0
        assert not d

    def test_initialization_with_dict(self):
        """测试使用普通字典初始化"""
        data = {"Content-Type": "text/plain", "Accept": "application/json"}
        d = CaseInsensitiveDict(data)
        assert len(d) == 2
        assert d["content-type"] == "text/plain"
        assert d["ACCEPT"] == "application/json"

    def test_initialization_with_case_insensitive_dict(self):
        """测试使用另一个CaseInsensitiveDict初始化"""
        original = CaseInsensitiveDict({"Test-Key": "test-value"})
        copied = CaseInsensitiveDict(original)
        assert copied["test-key"] == "test-value"
        assert copied is not original

    def test_getitem_case_insensitive(self):
        """测试大小写不敏感的键访问"""
        d = CaseInsensitiveDict({"Content-Type": "text/plain"})
        assert d["content-type"] == "text/plain"
        assert d["Content-Type"] == "text/plain"
        assert d["CONTENT-TYPE"] == "text/plain"
        assert d["Content-type"] == "text/plain"

    def test_setitem_case_insensitive(self):
        """测试大小写不敏感的键设置"""
        d = CaseInsensitiveDict()
        d["Content-Type"] = "text/plain"
        assert d["content-type"] == "text/plain"
        assert d["CONTENT-TYPE"] == "text/plain"

        # 设置相同的键（不同大小写）会覆盖原有值
        d["CONTENT-TYPE"] = "application/json"
        assert d["content-type"] == "application/json"
        assert len(d) == 1

    def test_delitem_case_insensitive(self):
        """测试大小写不敏感的键删除"""
        d = CaseInsensitiveDict({"Content-Type": "text/plain", "Accept": "json"})
        del d["content-type"]
        assert len(d) == 1
        assert "Content-Type" not in d
        assert "Accept" in d

        # 测试删除不存在的键
        with pytest.raises(KeyError):
            del d["non-existent-key"]

    def test_contains_case_insensitive(self):
        """测试大小写不敏感的键存在检查"""
        d = CaseInsensitiveDict({"Content-Type": "text/plain"})
        assert "content-type" in d
        assert "Content-Type" in d
        assert "CONTENT-TYPE" in d
        assert "non-existent" not in d

        # 测试非字符串键
        assert 123 not in d
        assert None not in d

    def test_iteration(self):
        """测试迭代功能"""
        d = CaseInsensitiveDict({"Content-Type": "text/plain", "Accept": "json"})
        keys = list(d.keys())
        assert "Content-Type" in keys
        assert "Accept" in keys
        assert len(keys) == 2

    def test_len_and_bool(self):
        """测试长度和布尔值检查"""
        d = CaseInsensitiveDict()
        assert len(d) == 0
        assert not d

        d["key"] = "value"
        assert len(d) == 1
        assert d

    def test_repr(self):
        """测试字符串表示"""
        d = CaseInsensitiveDict({"Content-Type": "text/plain"})
        repr_str = repr(d)
        assert "CaseInsensitiveDict" in repr_str
        assert "Content-Type" in repr_str
        assert "text/plain" in repr_str

    def test_equality(self):
        """测试相等性比较"""
        d1 = CaseInsensitiveDict({"Content-Type": "text/plain"})
        d2 = CaseInsensitiveDict({"content-type": "text/plain"})
        d3 = CaseInsensitiveDict({"Content-Type": "application/json"})

        assert d1 == d2
        assert d1 != d3
        assert d1 != "not a dict"

    def test_copy(self):
        """测试复制功能"""
        original = CaseInsensitiveDict({"key": "value"})
        copied = original.copy()

        assert copied == original
        assert copied is not original

        # 验证复制后的修改不影响原字典
        copied["new-key"] = "new-value"
        assert len(copied) == 2
        assert len(original) == 1

    def test_get_method(self):
        """测试get方法"""
        d = CaseInsensitiveDict({"Content-Type": "text/plain"})

        assert d.get("content-type") == "text/plain"
        assert d.get("non-existent") is None
        assert d.get("non-existent", "default") == "default"

    def test_pop_method(self):
        """测试pop方法"""
        d = CaseInsensitiveDict({"Content-Type": "text/plain", "Accept": "json"})

        value = d.pop("content-type")
        assert value == "text/plain"
        assert len(d) == 1

        # 测试默认值
        default_value = d.pop("non-existent", "default")
        assert default_value == "default"

        # 测试键不存在且没有默认值
        with pytest.raises(KeyError):
            d.pop("non-existent")

    def test_popitem_method(self):
        """测试popitem方法"""
        d = CaseInsensitiveDict({"key1": "value1", "key2": "value2"})

        original_len = len(d)
        key, value = d.popitem()
        assert len(d) == original_len - 1
        assert key in ["key1", "key2"]
        assert value in ["value1", "value2"]

        # 测试空字典
        empty = CaseInsensitiveDict()
        with pytest.raises(KeyError):
            empty.popitem()

    def test_setdefault_method(self):
        """测试setdefault方法"""
        d = CaseInsensitiveDict({"Content-Type": "text/plain"})

        # 键已存在的情况
        value = d.setdefault("content-type", "new-value")
        assert value == "text/plain"
        assert d["Content-Type"] == "text/plain"
        assert len(d) == 1

        # 键不存在的情况
        new_value = d.setdefault("New-Key", "new-value")
        assert new_value == "new-value"
        assert d["new-key"] == "new-value"
        assert len(d) == 2

    def test_update_method(self):
        """测试update方法"""
        d = CaseInsensitiveDict({"Content-Type": "text/plain"})

        # 使用字典更新
        d.update({"Accept": "application/json"})
        assert d["accept"] == "application/json"
        assert len(d) == 2

        # 使用关键字参数更新
        d.update(User_Agent="Mozilla/5.0")
        assert d["user-agent"] == "Mozilla/5.0"
        assert len(d) == 3

        # 使用可迭代对象更新
        d.update([("cache-control", "no-cache")])
        assert d["cache-control"] == "no-cache"
        assert len(d) == 4

        # 测试覆盖已有键
        d.update({"content-type": "application/xml"})
        assert d["Content-Type"] == "application/xml"
        assert len(d) == 4

    def test_clear_method(self):
        """测试clear方法"""
        d = CaseInsensitiveDict({"key1": "value1", "key2": "value2"})
        assert len(d) == 2

        d.clear()
        assert len(d) == 0
        assert not d

    def test_lower_keys_method(self):
        """测试lower_keys方法"""
        d = CaseInsensitiveDict({"Content-Type": "text/plain", "Accept": "json"})
        lower_keys = list(d.lower_keys())
        assert "content-type" in lower_keys
        assert "accept" in lower_keys
        assert len(lower_keys) == 2

    def test_error_handling(self):
        """测试错误处理"""
        d = CaseInsensitiveDict({"key": "value"})

        # 测试非字符串键
        with pytest.raises(TypeError, match="键必须是字符串类型"):
            d[123] = "value"

        with pytest.raises(TypeError, match="键必须是字符串类型"):
            d[None] = "value"

        with pytest.raises(TypeError, match="键必须是字符串类型"):
            del d[123]

        with pytest.raises(TypeError, match="键必须是字符串类型"):
            d.get(123)

        with pytest.raises(TypeError, match="键必须是字符串类型"):
            d.pop(123)

    def test_edge_cases(self):
        """测试边界情况"""
        # 空字符串键
        d = CaseInsensitiveDict({"": "empty"})
        assert d[""] == "empty"
        assert d[""] == "empty"

        # 特殊字符键
        d = CaseInsensitiveDict({"Content-Type-With-Dashes": "value"})
        assert d["content-type-with-dashes"] == "value"

        # 大写数字混合键
        d = CaseInsensitiveDict({"API-Key-123": "value"})
        assert d["api-key-123"] == "value"
        assert d["API-KEY-123"] == "value"

    def test_nested_dict_behavior(self):
        """测试嵌套字典行为"""
        d = CaseInsensitiveDict(
            {
                "headers": CaseInsensitiveDict({"Content-Type": "text/plain"}),
                "config": CaseInsensitiveDict({"timeout": 30}),
            }
        )

        assert isinstance(d["headers"], CaseInsensitiveDict)
        assert d["headers"]["content-type"] == "text/plain"

    def test_with_python_dict_conversion(self):
        """测试与Python字典的转换"""
        original = {"Content-Type": "text/plain", "ACCEPT": "json"}
        case_insensitive = CaseInsensitiveDict(original)

        # 转换为普通字典
        converted = dict(case_insensitive)
        assert "Content-Type" in converted or "content-type" in converted
        assert len(converted) == 2

    def test_key_order_preservation(self):
        """测试键顺序保持"""
        # 创建时提供的键顺序应该被保持
        original = CaseInsensitiveDict(
            {"Z-Last": "last", "A-First": "first", "M-Middle": "middle"}
        )

        keys = list(original.keys())
        assert keys == ["Z-Last", "A-First", "M-Middle"]

        # 更新不应该改变原始键的顺序
        original["z-last"] = "updated"
        keys = list(original.keys())
        assert keys == ["Z-Last", "A-First", "M-Middle"]


class TestCaseInsensitiveDictIntegration:
    """测试CaseInsensitiveDict的集成使用场景"""

    def test_config_usage_simulation(self):
        """模拟配置文件使用场景"""
        config = CaseInsensitiveDict(
            {
                "DATABASE_URL": "postgresql://localhost:5432/mydb",
                "API_KEY": "secret123",
                "TIMEOUT": 30,
                "DEBUG": True,
            }
        )

        # 各种大小写形式的访问都应该工作
        assert config["database_url"] == "postgresql://localhost:5432/mydb"
        assert config["API_KEY"] == "secret123"
        assert config["timeout"] == 30
        assert config["debug"] is True

        # 更新配置
        config["timeout"] = 60
        assert config["TIMEOUT"] == 60
        assert len(config) == 4

    def test_http_headers_simulation(self):
        """模拟HTTP头部使用场景"""
        headers = CaseInsensitiveDict(
            {
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0",
                "Authorization": "Bearer token123",
            }
        )

        # HTTP客户端通常会使用不同大小写形式的头部名称
        assert headers["content-type"] == "application/json"
        assert headers["USER-AGENT"] == "Mozilla/5.0"
        assert headers["authorization"] == "Bearer token123"

        # 添加新的头部
        headers["Accept"] = "application/json"
        assert headers["ACCEPT"] == "application/json"

    def test_environment_variables_simulation(self):
        """模拟环境变量使用场景"""
        env = CaseInsensitiveDict(
            {
                "PATH": "/usr/local/bin:/usr/bin",
                "HOME": "/home/user",
                "USER": "username",
            }
        )

        # 环境变量通常不区分大小写
        assert env["path"] == "/usr/local/bin:/usr/bin"
        assert env["HOME"] == "/home/user"
        assert env["user"] == "username"


if __name__ == "__main__":
    pytest.main([__file__])
