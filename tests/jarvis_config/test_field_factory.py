"""Field Factory 单元测试"""

import pytest

from jarvis.jarvis_config.field_factory import (
    FieldFactory,
    InputField,
    NumberField,
    EnumField,
    BooleanField,
    ArrayField,
    create_field_factory,
)
from jarvis.jarvis_config.schema_parser import SchemaParser


# 标记需要 Textual 环境的测试
pytestmark = pytest.mark.skipif(
    pytest.importorskip("textual", reason="Textual not available") is None,
    reason="Textual not available",
)


class TestFieldFactoryBasic:
    """测试 FieldFactory 基础功能。"""

    def test_init(self):
        """测试初始化。"""
        schema = {"type": "string"}
        parser = SchemaParser(schema)
        factory = FieldFactory(parser)
        assert factory.schema_parser == parser

    def test_create_string_field(self):
        """测试创建字符串字段。"""
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        parser = SchemaParser(schema)
        factory = FieldFactory(parser)

        field = factory.create_field("name", "Name")
        assert field is not None
        assert isinstance(field, InputField)
        assert field.field_name == "Name"
        assert field.field_type == "string"

    def test_create_number_field(self):
        """测试创建数字字段。"""
        schema = {"type": "object", "properties": {"age": {"type": "integer"}}}
        parser = SchemaParser(schema)
        factory = FieldFactory(parser)

        field = factory.create_field("age", "Age")
        assert field is not None
        assert isinstance(field, NumberField)
        assert field.field_name == "Age"
        assert field.field_type == "integer"

    def test_create_boolean_field(self):
        """测试创建布尔字段。"""
        schema = {"type": "object", "properties": {"active": {"type": "boolean"}}}
        parser = SchemaParser(schema)
        factory = FieldFactory(parser)

        field = factory.create_field("active", "Active")
        assert field is not None
        assert isinstance(field, BooleanField)
        assert field.field_name == "Active"
        assert field.field_type == "boolean"

    def test_create_array_field(self):
        """测试创建数组字段。"""
        schema = {
            "type": "object",
            "properties": {"tags": {"type": "array", "items": {"type": "string"}}},
        }
        parser = SchemaParser(schema)
        factory = FieldFactory(parser)

        field = factory.create_field("tags", "Tags")
        assert field is not None
        assert isinstance(field, ArrayField)
        assert field.field_name == "Tags"
        assert field.field_type == "array"


class TestFieldFactoryEnum:
    """测试枚举字段创建。"""

    def test_create_enum_field(self):
        """测试创建枚举字段。"""
        schema = {
            "type": "object",
            "properties": {
                "color": {"type": "string", "enum": ["red", "green", "blue"]}
            },
        }
        parser = SchemaParser(schema)
        factory = FieldFactory(parser)

        field = factory.create_field("color", "Color")
        assert field is not None
        assert isinstance(field, EnumField)
        assert field.field_name == "Color"

    def test_create_enum_array_field(self):
        """测试创建枚举数组字段。"""
        schema = {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["a", "b", "c"]},
                }
            },
        }
        parser = SchemaParser(schema)
        factory = FieldFactory(parser)

        field = factory.create_field("tags", "Tags")
        assert field is not None
        assert isinstance(field, EnumField)
        assert field.field_name == "Tags"


class TestFieldFactoryRequired:
    """测试必填字段标记。"""

    def test_required_field(self):
        """测试必填字段。"""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        parser = SchemaParser(schema)
        factory = FieldFactory(parser)

        field = factory.create_field("name", "Name")
        assert field.is_required is True

    def test_optional_field(self):
        """测试可选字段。"""
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        parser = SchemaParser(schema)
        factory = FieldFactory(parser)

        field = factory.create_field("name", "Name")
        assert field.is_required is False


class TestFieldFactoryDefaults:
    """测试默认值处理。"""

    def test_default_from_schema(self):
        """测试从 Schema 获取默认值。"""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string", "default": "John"}},
        }
        parser = SchemaParser(schema)
        factory = FieldFactory(parser)

        field = factory.create_field("name", "Name")
        assert field._default_value == "John"

    def test_default_from_defaults_dict(self):
        """测试从 defaults 字典获取默认值。"""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string", "default": "John"}},
        }
        parser = SchemaParser(schema)
        factory = FieldFactory(parser)

        # defaults 字典优先级更高
        field = factory.create_field("name", "Name", defaults={"name": "Jane"})
        assert field._default_value == "Jane"


class TestFieldFactoryDescription:
    """测试字段描述。"""

    def test_field_description(self):
        """测试字段描述。"""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "User's name"}},
        }
        parser = SchemaParser(schema)
        factory = FieldFactory(parser)

        field = factory.create_field("name", "Name")
        assert field.description == "User's name"


class TestFieldFactoryNested:
    """测试嵌套字段。"""

    def test_nested_object_field(self):
        """测试嵌套对象字段。"""
        schema = {
            "type": "object",
            "properties": {
                "user": {"type": "object", "properties": {"name": {"type": "string"}}}
            },
        }
        parser = SchemaParser(schema)
        factory = FieldFactory(parser)

        # 嵌套对象应返回 None
        field = factory.create_field("user", "User")
        assert field is None

    def test_nested_field_path(self):
        """测试嵌套字段路径。"""
        schema = {
            "type": "object",
            "properties": {
                "user": {"type": "object", "properties": {"name": {"type": "string"}}}
            },
        }
        parser = SchemaParser(schema)
        factory = FieldFactory(parser)

        # 嵌套字段
        field = factory.create_field("user.name", "Name")
        assert field is not None
        assert isinstance(field, InputField)


class TestCreateFieldFactoryFunction:
    """测试 create_field_factory 便捷函数。"""

    def test_create_field_factory(self):
        """测试创建字段工厂。"""
        schema = {"type": "string"}
        factory = create_field_factory(schema)
        assert isinstance(factory, FieldFactory)
        assert isinstance(factory.schema_parser, SchemaParser)
