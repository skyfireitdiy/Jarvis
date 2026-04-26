# -*- coding: utf-8 -*-
"""SchemaParser 模块单元测试"""

import pytest

from jarvis.jarvis_config.schema_parser import SchemaParser


class TestSchemaParser:
    """测试 SchemaParser 类"""

    def test_schema_initialization(self, parser_with_schema):
        """测试 Schema 初始化"""
        assert parser_with_schema is not None
        assert isinstance(parser_with_schema, SchemaParser)
        assert parser_with_schema.schema_path is not None

    def test_get_title(self, parser_with_schema):
        """测试获取 Schema 标题"""
        title = parser_with_schema.get_title()
        assert title == "测试配置"

    def test_get_description(self, parser_with_schema):
        """测试获取 Schema 描述"""
        description = parser_with_schema.get_description()
        assert description == "用于测试的配置 Schema"

    def test_get_schema(self, parser_with_schema):
        """测试获取 Schema 对象"""
        schema = parser_with_schema.get_schema()
        assert isinstance(schema, dict)
        assert "title" in schema
        assert "properties" in schema

    def test_get_properties(self, parser_with_schema):
        """测试获取顶层属性"""
        properties = parser_with_schema.get_properties()
        assert isinstance(properties, dict)
        assert "name" in properties
        assert "count" in properties
        assert "enabled" in properties
        assert "tags" in properties
        assert "metadata" in properties

    def test_get_required(self, parser_with_schema):
        """测试获取必填属性列表"""
        required = parser_with_schema.get_required()
        assert isinstance(required, list)
        assert "name" in required
        assert "count" in required
        assert "enabled" not in required

    def test_get_property_schema(self, parser_with_schema):
        """测试获取属性的 Schema"""
        prop_schema = parser_with_schema.get_property_schema("name")
        assert prop_schema["type"] == "string"
        assert "minLength" in prop_schema

    def test_get_property_schema_not_found(self, parser_with_schema):
        """测试获取不存在的属性 Schema"""
        with pytest.raises(ValueError, match="Property 'unknown' not found"):
            parser_with_schema.get_property_schema("unknown")

    def test_get_default_value(self, parser_with_schema):
        """测试获取属性的默认值"""
        assert parser_with_schema.get_default_value("name") == "test"
        assert parser_with_schema.get_default_value("count") == 1
        assert parser_with_schema.get_default_value("enabled") is True
        assert parser_with_schema.get_default_value("tags") == []

    def test_get_default_value_not_exist(self, parser_with_schema):
        """测试获取不存在的属性默认值"""
        with pytest.raises(ValueError):
            parser_with_schema.get_default_value("unknown")

    def test_validate_valid_config(self, parser_with_schema, valid_config_data):
        """测试验证有效配置"""
        errors = parser_with_schema.validate_config(valid_config_data)
        assert len(errors) == 0

    def test_validate_missing_required_field(self, parser_with_schema):
        """测试缺少必填字段的验证"""
        config = {
            "count": 10
            # 缺少必填字段 'name'
        }
        errors = parser_with_schema.validate_config(config)
        assert len(errors) > 0
        assert any("Required field 'name' is missing" in str(e) for e in errors)

    def test_validate_string_min_length(self, parser_with_schema):
        """测试字符串最小长度约束"""
        config = {
            "name": "",  # 违反 minLength: 1
            "count": 10,
        }
        errors = parser_with_schema.validate_config(config)
        assert len(errors) > 0
        assert any("less than minimum" in str(e).lower() for e in errors)

    def test_validate_string_max_length(self, parser_with_schema):
        """测试字符串最大长度约束"""
        config = {
            "name": "x" * 101,  # 违反 maxLength: 100
            "count": 10,
        }
        errors = parser_with_schema.validate_config(config)
        assert len(errors) > 0
        assert any("exceeds maximum" in str(e).lower() for e in errors)

    def test_validate_integer_minimum(self, parser_with_schema):
        """测试整数最小值约束"""
        config = {
            "name": "test",
            "count": -1,  # 违反 minimum: 0
        }
        errors = parser_with_schema.validate_config(config)
        assert len(errors) > 0
        assert any("less than minimum" in str(e).lower() for e in errors)

    def test_validate_integer_maximum(self, parser_with_schema):
        """测试整数最大值约束"""
        config = {
            "name": "test",
            "count": 101,  # 违反 maximum: 100
        }
        errors = parser_with_schema.validate_config(config)
        assert len(errors) > 0
        assert any("exceeds maximum" in str(e).lower() for e in errors)

    def test_validate_number_minimum(self, parser_with_schema):
        """测试浮点数最小值约束"""
        config = {
            "name": "test",
            "count": 10,
            "rate": -0.1,  # 违反 minimum: 0.0
        }
        errors = parser_with_schema.validate_config(config)
        assert len(errors) > 0
        assert any("less than minimum" in str(e).lower() for e in errors)

    def test_validate_number_maximum(self, parser_with_schema):
        """测试浮点数最大值约束"""
        config = {
            "name": "test",
            "count": 10,
            "rate": 1.5,  # 违反 maximum: 1.0
        }
        errors = parser_with_schema.validate_config(config)
        assert len(errors) > 0
        assert any("exceeds maximum" in str(e).lower() for e in errors)

    def test_validate_enum(self, parser_with_schema):
        """测试枚举值约束"""
        config = {
            "name": "test",
            "count": 10,
            "status": "invalid_status",  # 不在枚举中
        }
        errors = parser_with_schema.validate_config(config)
        assert len(errors) > 0
        assert any("not in enum" in str(e).lower() for e in errors)

    def test_validate_boolean_type(self, parser_with_schema):
        """测试布尔类型验证"""
        config = {
            "name": "test",
            "count": 10,
            "enabled": "not-a-boolean",  # 类型错误
        }
        errors = parser_with_schema.validate_config(config)
        assert len(errors) > 0
        assert any("Expected type boolean" in str(e) for e in errors)

    def test_validate_array_min_items(self, parser_with_schema):
        """测试数组最小项数约束"""
        config = {"name": "test", "count": 10}
        # tags 是可选字段，如果提供需要符合约束
        # 测试空数组（minItems: 0）
        config["tags"] = []
        errors = parser_with_schema.validate_config(config)
        # 空数组应该通过，因为 minItems 是 0
        assert len([e for e in errors if "tags" in e.path]) == 0

    def test_validate_array_max_items(self, parser_with_schema):
        """测试数组最大项数约束"""
        config = {
            "name": "test",
            "count": 10,
            "tags": [f"tag{i}" for i in range(11)],  # 违反 maxItems: 10
        }
        errors = parser_with_schema.validate_config(config)
        assert len(errors) > 0
        assert any("exceeds maximum" in str(e).lower() for e in errors)

    def test_validate_nested_object(self, parser_with_schema):
        """测试嵌套对象验证"""
        config = {
            "name": "test",
            "count": 10,
            "metadata": {
                "key1": "value",
                "key2": "not-an-integer",  # 类型错误
            },
        }
        errors = parser_with_schema.validate_config(config)
        assert len(errors) > 0
        # 检查是否有关于 metadata.key2 的错误
        metadata_errors = [e for e in errors if "metadata" in e.path]
        assert len(metadata_errors) > 0

    def test_validate_valid_nested_object(self, parser_with_schema):
        """测试有效的嵌套对象"""
        config = {
            "name": "test",
            "count": 10,
            "metadata": {"key1": "value1", "key2": 42},
        }
        errors = parser_with_schema.validate_config(config)
        assert len(errors) == 0

    def test_validation_error_path(self, parser_with_schema):
        """测试验证错误包含路径信息"""
        config = {"name": "test", "count": -1}
        errors = parser_with_schema.validate_config(config)
        assert len(errors) > 0
        # 检查错误是否包含路径信息
        count_errors = [e for e in errors if "count" in e.path]
        assert len(count_errors) > 0

    def test_static_load_schema(self, sample_schema_file):
        """测试静态方法 load_schema"""
        schema = SchemaParser.load_schema(sample_schema_file)
        assert isinstance(schema, dict)
        assert schema["title"] == "测试配置"
