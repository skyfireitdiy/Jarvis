"""Schema Parser 单元测试"""

import pytest

from jarvis.jarvis_config.schema_parser import SchemaParser, parse_schema


class TestSchemaParserBasic:
    """测试 Schema Parser 基础功能。"""

    def test_init_valid_schema(self):
        """测试用有效的 Schema 初始化解析器。"""
        schema = {"type": "string"}
        parser = SchemaParser(schema)
        assert parser.schema == schema

    def test_init_invalid_schema(self):
        """测试用无效的 Schema 初始化解析器。"""
        with pytest.raises(ValueError, match="Schema must be a dictionary"):
            SchemaParser("not a dict")
        with pytest.raises(ValueError, match="Schema must be a dictionary"):
            SchemaParser(None)

    def test_get_type_string(self):
        """测试获取字符串类型。"""
        schema = {"type": "string"}
        parser = SchemaParser(schema)
        assert parser.get_type() == "string"

    def test_get_type_number(self):
        """测试获取数字类型。"""
        schema = {"type": "number"}
        parser = SchemaParser(schema)
        assert parser.get_type() == "number"

    def test_get_type_integer(self):
        """测试获取整数类型。"""
        schema = {"type": "integer"}
        parser = SchemaParser(schema)
        assert parser.get_type() == "integer"

    def test_get_type_boolean(self):
        """测试获取布尔类型。"""
        schema = {"type": "boolean"}
        parser = SchemaParser(schema)
        assert parser.get_type() == "boolean"

    def test_get_type_object(self):
        """测试获取对象类型。"""
        schema = {"type": "object"}
        parser = SchemaParser(schema)
        assert parser.get_type() == "object"

    def test_get_type_array(self):
        """测试获取数组类型。"""
        schema = {"type": "array"}
        parser = SchemaParser(schema)
        assert parser.get_type() == "array"

    def test_get_type_nullable(self):
        """测试获取可空类型（类型数组）。"""
        schema = {"type": ["string", "null"]}
        parser = SchemaParser(schema)
        assert parser.get_type() == "string"

    def test_get_type_invalid(self):
        """测试获取无效类型。"""
        schema = {"type": "invalid"}
        parser = SchemaParser(schema)
        with pytest.raises(ValueError, match="Unsupported type"):
            parser.get_type()

    def test_get_type_missing(self):
        """测试缺少类型字段。"""
        schema = {"description": "test"}
        parser = SchemaParser(schema)
        with pytest.raises(ValueError, match="must have a 'type' field"):
            parser.get_type()


class TestSchemaParserObject:
    """测试 Schema Parser 对象类型功能。"""

    def test_get_properties(self):
        """测试获取对象属性。"""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        }
        parser = SchemaParser(schema)
        props = parser.get_properties()
        assert "name" in props
        assert "age" in props
        assert props["name"]["type"] == "string"

    def test_get_properties_empty(self):
        """测试空对象属性。"""
        schema = {"type": "object"}
        parser = SchemaParser(schema)
        props = parser.get_properties()
        assert props == {}

    def test_get_properties_non_object(self):
        """测试非对象类型的属性。"""
        schema = {"type": "string"}
        parser = SchemaParser(schema)
        props = parser.get_properties()
        assert props == {}

    def test_get_required_fields(self):
        """测试获取必填字段。"""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            "required": ["name"],
        }
        parser = SchemaParser(schema)
        required = parser.get_required_fields()
        assert required == ["name"]

    def test_get_required_fields_empty(self):
        """测试没有必填字段。"""
        schema = {"type": "object"}
        parser = SchemaParser(schema)
        required = parser.get_required_fields()
        assert required == []

    def test_is_required(self):
        """测试检查字段是否必填。"""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            "required": ["name"],
        }
        parser = SchemaParser(schema)
        assert parser.is_required("name") is True
        assert parser.is_required("age") is False

    def test_get_field_type(self):
        """测试获取字段类型。"""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        }
        parser = SchemaParser(schema)
        assert parser.get_field_type("name") == "string"
        assert parser.get_field_type("age") == "integer"


class TestSchemaParserArray:
    """测试 Schema Parser 数组类型功能。"""

    def test_get_items_schema(self):
        """测试获取数组项目 Schema。"""
        schema = {"type": "array", "items": {"type": "string"}}
        parser = SchemaParser(schema)
        items = parser.get_items_schema()
        assert items is not None
        assert items["type"] == "string"

    def test_get_items_schema_missing(self):
        """测试缺少 items 时的默认行为。"""
        schema = {"type": "array"}
        parser = SchemaParser(schema)
        items = parser.get_items_schema()
        assert items is not None
        assert items["type"] == "string"

    def test_get_items_schema_non_array(self):
        """测试非数组类型的 items。"""
        schema = {"type": "string"}
        parser = SchemaParser(schema)
        items = parser.get_items_schema()
        assert items is None


class TestSchemaParserConstraints:
    """测试 Schema Parser 约束条件功能。"""

    def test_get_constraints_number(self):
        """测试数值约束。"""
        schema = {
            "type": "number",
            "minimum": 0,
            "maximum": 100,
            "exclusiveMinimum": True,
        }
        parser = SchemaParser(schema)
        constraints = parser._extract_constraints()
        assert "minimum" in constraints
        assert "maximum" in constraints
        assert "exclusiveMinimum" in constraints

    def test_get_constraints_string(self):
        """测试字符串约束。"""
        schema = {
            "type": "string",
            "minLength": 1,
            "maxLength": 100,
            "pattern": "^[a-z]+$",
        }
        parser = SchemaParser(schema)
        constraints = parser._extract_constraints()
        assert "minLength" in constraints
        assert "maxLength" in constraints
        assert "pattern" in constraints

    def test_get_enum_values(self):
        """测试获取枚举值。"""
        schema = {"type": "string", "enum": ["red", "green", "blue"]}
        parser = SchemaParser(schema)
        enum_values = parser.get_enum_values("")
        assert enum_values == ["red", "green", "blue"]

    def test_get_enum_values_none(self):
        """测试非枚举类型。"""
        schema = {"type": "string"}
        parser = SchemaParser(schema)
        enum_values = parser.get_enum_values("")
        assert enum_values is None


class TestSchemaParserDefaults:
    """测试 Schema Parser 默认值功能。"""

    def test_get_default_value(self):
        """测试获取默认值。"""
        schema = {"type": "string", "default": "hello"}
        parser = SchemaParser(schema)
        default = parser.get_default_value("")
        assert default == "hello"

    def test_get_default_value_none(self):
        """测试没有默认值。"""
        schema = {"type": "string"}
        parser = SchemaParser(schema)
        default = parser.get_default_value("")
        assert default is None

    def test_get_default_value_nested(self):
        """测试嵌套字段的默认值。"""
        schema = {
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {"name": {"type": "string", "default": "John"}},
                }
            },
        }
        parser = SchemaParser(schema)
        default = parser.get_default_value("user.name")
        assert default == "John"


class TestSchemaParserDescription:
    """测试 Schema Parser 描述功能。"""

    def test_get_field_description(self):
        """测试获取字段描述。"""
        schema = {"type": "string", "description": "A name field"}
        parser = SchemaParser(schema)
        desc = parser.get_field_description("")
        assert desc == "A name field"

    def test_get_field_description_none(self):
        """测试没有描述。"""
        schema = {"type": "string"}
        parser = SchemaParser(schema)
        desc = parser.get_field_description("")
        assert desc is None


class TestSchemaParserNested:
    """测试 Schema Parser 嵌套功能。"""

    def test_get_field_type_nested(self):
        """测试嵌套字段类型。"""
        schema = {
            "type": "object",
            "properties": {
                "user": {"type": "object", "properties": {"name": {"type": "string"}}}
            },
        }
        parser = SchemaParser(schema)
        assert parser.get_field_type("user.name") == "string"

    def test_has_nested_schema(self):
        """测试检查是否有嵌套 Schema。"""
        schema = {
            "type": "object",
            "properties": {
                "user": {"type": "object"},
                "tags": {"type": "array"},
                "name": {"type": "string"},
            },
        }
        parser = SchemaParser(schema)
        assert parser.has_nested_schema("user") is True
        assert parser.has_nested_schema("tags") is True
        assert parser.has_nested_schema("name") is False

    def test_get_nested_parser(self):
        """测试获取嵌套解析器。"""
        schema = {
            "type": "object",
            "properties": {
                "user": {"type": "object", "properties": {"name": {"type": "string"}}}
            },
        }
        parser = SchemaParser(schema)
        nested_parser = parser.get_nested_parser("user")
        assert isinstance(nested_parser, SchemaParser)
        assert nested_parser.get_type() == "object"
        assert "name" in nested_parser.get_properties()


class TestSchemaParserParseSchema:
    """测试 parse_schema 方法。"""

    def test_parse_schema_object(self):
        """测试解析对象 Schema。"""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        parser = SchemaParser(schema)
        parsed = parser.parse_schema()
        assert parsed["type"] == "object"
        assert "name" in parsed["properties"]
        assert "name" in parsed["required"]

    def test_parse_schema_array(self):
        """测试解析数组 Schema。"""
        schema = {"type": "array", "items": {"type": "string"}}
        parser = SchemaParser(schema)
        parsed = parser.parse_schema()
        assert parsed["type"] == "array"
        assert parsed["items"]["type"] == "string"


class TestParseSchemaFunction:
    """测试 parse_schema 便捷函数。"""

    def test_parse_schema_function(self):
        """测试 parse_schema 函数。"""
        schema = {"type": "string"}
        parser = parse_schema(schema)
        assert isinstance(parser, SchemaParser)
        assert parser.get_type() == "string"
