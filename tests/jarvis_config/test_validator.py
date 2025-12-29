"""SchemaValidator 单元测试"""

from jarvis.jarvis_config.validator import (
    SchemaValidator,
    ValidationError,
    ValidationResult,
    create_validator,
)


class TestValidationError:
    """测试 ValidationError 类。"""

    def test_init(self):
        """测试初始化。"""
        error = ValidationError(
            field_path="name",
            message="错误消息",
            error_type="type",
        )
        assert error.field_path == "name"
        assert error.message == "错误消息"
        assert error.error_type == "type"

    def test_str(self):
        """测试字符串表示。"""
        error = ValidationError(
            field_path="name",
            message="错误消息",
        )
        assert str(error) == "name: 错误消息"

    def test_str_without_path(self):
        """测试无路径的字符串表示。"""
        error = ValidationError(
            field_path="",
            message="错误消息",
        )
        assert str(error) == "错误消息"


class TestValidationResult:
    """测试 ValidationResult 类。"""

    def test_init_valid(self):
        """测试初始化为有效。"""
        result = ValidationResult(is_valid=True)
        assert result.is_valid is True
        assert result.errors == []

    def test_init_invalid(self):
        """测试初始化为无效。"""
        errors = [ValidationError("name", "错误")]
        result = ValidationResult(is_valid=False, errors=errors)
        assert result.is_valid is False
        assert len(result.errors) == 1

    def test_add_error(self):
        """测试添加错误。"""
        result = ValidationResult()
        assert result.is_valid is True

        error = ValidationError("name", "错误")
        result.add_error(error)

        assert result.is_valid is False
        assert len(result.errors) == 1

    def test_get_error_messages(self):
        """测试获取错误消息。"""
        result = ValidationResult()
        result.add_error(ValidationError("name", "错误1"))
        result.add_error(ValidationError("age", "错误2"))

        messages = result.get_error_messages()
        assert len(messages) == 2
        assert "name: 错误1" in messages
        assert "age: 错误2" in messages


class TestSchemaValidatorBasic:
    """测试 SchemaValidator 基础功能。"""

    def test_init(self):
        """测试初始化。"""
        schema = {"type": "string"}
        validator = SchemaValidator(schema)
        assert validator.parser is not None

    def test_validate_string_valid(self):
        """测试验证有效的字符串。"""
        schema = {"type": "string"}
        validator = SchemaValidator(schema)

        result = validator.validate("test")
        assert result.is_valid is True

    def test_validate_number_valid(self):
        """测试验证有效的数字。"""
        schema = {"type": "number"}
        validator = SchemaValidator(schema)

        result = validator.validate(42.5)
        assert result.is_valid is True

    def test_validate_integer_valid(self):
        """测试验证有效的整数。"""
        schema = {"type": "integer"}
        validator = SchemaValidator(schema)

        result = validator.validate(42)
        assert result.is_valid is True

    def test_validate_boolean_valid(self):
        """测试验证有效的布尔值。"""
        schema = {"type": "boolean"}
        validator = SchemaValidator(schema)

        result = validator.validate(True)
        assert result.is_valid is True

    def test_validate_array_valid(self):
        """测试验证有效的数组。"""
        schema = {"type": "array"}
        validator = SchemaValidator(schema)

        result = validator.validate([1, 2, 3])
        assert result.is_valid is True

    def test_validate_object_valid(self):
        """测试验证有效的对象。"""
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        validator = SchemaValidator(schema)

        result = validator.validate({"name": "John"})
        assert result.is_valid is True


class TestTypeValidation:
    """测试类型验证。"""

    def test_string_type_invalid(self):
        """测试字符串类型无效。"""
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        validator = SchemaValidator(schema)

        result = validator.validate({"name": 123})
        assert result.is_valid is False
        assert "类型错误" in result.get_error_messages()[0]

    def test_number_type_invalid(self):
        """测试数字类型无效。"""
        schema = {"type": "object", "properties": {"age": {"type": "number"}}}
        validator = SchemaValidator(schema)

        result = validator.validate({"age": "not a number"})
        assert result.is_valid is False
        assert "类型错误" in result.get_error_messages()[0]

    def test_integer_type_invalid(self):
        """测试整数类型无效。"""
        schema = {"type": "object", "properties": {"count": {"type": "integer"}}}
        validator = SchemaValidator(schema)

        result = validator.validate({"count": 3.14})
        assert result.is_valid is False

    def test_boolean_type_invalid(self):
        """测试布尔类型无效。"""
        schema = {"type": "object", "properties": {"active": {"type": "boolean"}}}
        validator = SchemaValidator(schema)

        result = validator.validate({"active": "yes"})
        assert result.is_valid is False


class TestRequiredValidation:
    """测试必填字段验证。"""

    def test_required_field_missing(self):
        """测试必填字段缺失。"""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "email": {"type": "string"}},
            "required": ["name"],
        }
        validator = SchemaValidator(schema)

        result = validator.validate({"email": "test@example.com"})
        assert result.is_valid is False
        assert "必填项" in result.get_error_messages()[0]

    def test_required_field_null(self):
        """测试必填字段为 null。"""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        validator = SchemaValidator(schema)

        result = validator.validate({"name": None})
        assert result.is_valid is False
        assert "必填项" in result.get_error_messages()[0]

    def test_optional_field_missing(self):
        """测试可选字段缺失（应该通过）。"""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            "required": ["name"],
        }
        validator = SchemaValidator(schema)

        result = validator.validate({"name": "John"})
        assert result.is_valid is True


class TestEnumValidation:
    """测试枚举验证。"""

    def test_enum_valid(self):
        """测试有效的枚举值。"""
        schema = {
            "type": "object",
            "properties": {
                "color": {"type": "string", "enum": ["red", "green", "blue"]}
            },
        }
        validator = SchemaValidator(schema)

        result = validator.validate({"color": "red"})
        assert result.is_valid is True

    def test_enum_invalid(self):
        """测试无效的枚举值。"""
        schema = {
            "type": "object",
            "properties": {
                "color": {"type": "string", "enum": ["red", "green", "blue"]}
            },
        }
        validator = SchemaValidator(schema)

        result = validator.validate({"color": "yellow"})
        assert result.is_valid is False
        assert "值无效" in result.get_error_messages()[0]


class TestNumberConstraints:
    """测试数值约束验证。"""

    def test_minimum_valid(self):
        """测试最小值有效。"""
        schema = {
            "type": "object",
            "properties": {"age": {"type": "integer", "minimum": 0}},
        }
        validator = SchemaValidator(schema)

        result = validator.validate({"age": 18})
        assert result.is_valid is True

    def test_minimum_invalid(self):
        """测试最小值无效。"""
        schema = {
            "type": "object",
            "properties": {"age": {"type": "integer", "minimum": 18}},
        }
        validator = SchemaValidator(schema)

        result = validator.validate({"age": 10})
        assert result.is_valid is False
        assert "值太小" in result.get_error_messages()[0]

    def test_maximum_valid(self):
        """测试最大值有效。"""
        schema = {
            "type": "object",
            "properties": {"age": {"type": "integer", "maximum": 100}},
        }
        validator = SchemaValidator(schema)

        result = validator.validate({"age": 50})
        assert result.is_valid is True

    def test_maximum_invalid(self):
        """测试最大值无效。"""
        schema = {
            "type": "object",
            "properties": {"age": {"type": "integer", "maximum": 100}},
        }
        validator = SchemaValidator(schema)

        result = validator.validate({"age": 150})
        assert result.is_valid is False
        assert "值太大" in result.get_error_messages()[0]

    def test_exclusive_minimum_valid(self):
        """测试排他最小值有效。"""
        schema = {
            "type": "object",
            "properties": {"age": {"type": "integer", "exclusiveMinimum": 18}},
        }
        validator = SchemaValidator(schema)

        result = validator.validate({"age": 19})
        assert result.is_valid is True

    def test_exclusive_minimum_invalid(self):
        """测试排他最小值无效。"""
        schema = {
            "type": "object",
            "properties": {"age": {"type": "integer", "exclusiveMinimum": 18}},
        }
        validator = SchemaValidator(schema)

        result = validator.validate({"age": 18})
        assert result.is_valid is False
        assert "必须大于" in result.get_error_messages()[0]


class TestStringConstraints:
    """测试字符串约束验证。"""

    def test_min_length_valid(self):
        """测试最小长度有效。"""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string", "minLength": 3}},
        }
        validator = SchemaValidator(schema)

        result = validator.validate({"name": "John"})
        assert result.is_valid is True

    def test_min_length_invalid(self):
        """测试最小长度无效。"""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string", "minLength": 3}},
        }
        validator = SchemaValidator(schema)

        result = validator.validate({"name": "Jo"})
        assert result.is_valid is False
        assert "字符串太短" in result.get_error_messages()[0]

    def test_max_length_valid(self):
        """测试最大长度有效。"""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string", "maxLength": 20}},
        }
        validator = SchemaValidator(schema)

        result = validator.validate({"name": "John"})
        assert result.is_valid is True

    def test_max_length_invalid(self):
        """测试最大长度无效。"""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string", "maxLength": 5}},
        }
        validator = SchemaValidator(schema)

        result = validator.validate({"name": "Jonathan"})
        assert result.is_valid is False
        assert "字符串太长" in result.get_error_messages()[0]

    def test_pattern_valid(self):
        """测试模式匹配有效。"""
        schema = {
            "type": "object",
            "properties": {
                "email": {
                    "type": "string",
                    "pattern": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
                }
            },
        }
        validator = SchemaValidator(schema)

        result = validator.validate({"email": "test@example.com"})
        assert result.is_valid is True

    def test_pattern_invalid(self):
        """测试模式匹配无效。"""
        schema = {
            "type": "object",
            "properties": {
                "email": {
                    "type": "string",
                    "pattern": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
                }
            },
        }
        validator = SchemaValidator(schema)

        result = validator.validate({"email": "not-an-email"})
        assert result.is_valid is False
        assert "格式要求" in result.get_error_messages()[0]


class TestArrayConstraints:
    """测试数组约束验证。"""

    def test_min_items_valid(self):
        """测试最小项数有效。"""
        schema = {
            "type": "object",
            "properties": {"tags": {"type": "array", "minItems": 1}},
        }
        validator = SchemaValidator(schema)

        result = validator.validate({"tags": ["a", "b"]})
        assert result.is_valid is True

    def test_min_items_invalid(self):
        """测试最小项数无效。"""
        schema = {
            "type": "object",
            "properties": {"tags": {"type": "array", "minItems": 2}},
        }
        validator = SchemaValidator(schema)

        result = validator.validate({"tags": ["a"]})
        assert result.is_valid is False
        assert "数组项太少" in result.get_error_messages()[0]

    def test_max_items_valid(self):
        """测试最大项数有效。"""
        schema = {
            "type": "object",
            "properties": {"tags": {"type": "array", "maxItems": 3}},
        }
        validator = SchemaValidator(schema)

        result = validator.validate({"tags": ["a", "b"]})
        assert result.is_valid is True

    def test_max_items_invalid(self):
        """测试最大项数无效。"""
        schema = {
            "type": "object",
            "properties": {"tags": {"type": "array", "maxItems": 2}},
        }
        validator = SchemaValidator(schema)

        result = validator.validate({"tags": ["a", "b", "c"]})
        assert result.is_valid is False
        assert "数组项太多" in result.get_error_messages()[0]

    def test_unique_items_valid(self):
        """测试唯一项有效。"""
        schema = {
            "type": "object",
            "properties": {"tags": {"type": "array", "uniqueItems": True}},
        }
        validator = SchemaValidator(schema)

        result = validator.validate({"tags": ["a", "b", "c"]})
        assert result.is_valid is True

    def test_unique_items_invalid(self):
        """测试唯一项无效。"""
        schema = {
            "type": "object",
            "properties": {"tags": {"type": "array", "uniqueItems": True}},
        }
        validator = SchemaValidator(schema)

        result = validator.validate({"tags": ["a", "b", "a"]})
        assert result.is_valid is False
        assert "必须唯一" in result.get_error_messages()[0]


class TestNestedObjectValidation:
    """测试嵌套对象验证。"""

    def test_nested_object_valid(self):
        """测试嵌套对象有效。"""
        schema = {
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "age": {"type": "integer"},
                    },
                }
            },
        }
        validator = SchemaValidator(schema)

        result = validator.validate({"user": {"name": "John", "age": 30}})
        assert result.is_valid is True

    def test_nested_object_invalid(self):
        """测试嵌套对象无效。"""
        schema = {
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                }
            },
        }
        validator = SchemaValidator(schema)

        result = validator.validate({"user": {}})
        assert result.is_valid is False

    def test_multiple_nested_objects(self):
        """测试多层嵌套对象。"""
        schema = {
            "type": "object",
            "properties": {
                "config": {
                    "type": "object",
                    "properties": {
                        "database": {
                            "type": "object",
                            "properties": {"host": {"type": "string"}},
                        }
                    },
                }
            },
        }
        validator = SchemaValidator(schema)

        result = validator.validate({"config": {"database": {"host": "localhost"}}})
        assert result.is_valid is True


class TestValidateField:
    """测试 validate_field 方法。"""

    def test_validate_field_valid(self):
        """测试验证单个字段有效。"""
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        validator = SchemaValidator(schema)

        error = validator.validate_field("name", "John")
        assert error is None

    def test_validate_field_invalid(self):
        """测试验证单个字段无效。"""
        schema = {"type": "object", "properties": {"age": {"type": "integer"}}}
        validator = SchemaValidator(schema)

        error = validator.validate_field("age", "not an integer")
        assert error is not None
        assert "类型错误" in error.message


class TestCreateValidator:
    """测试 create_validator 便捷函数。"""

    def test_create_validator(self):
        """测试创建验证器。"""
        schema = {"type": "string"}
        validator = create_validator(schema)
        assert isinstance(validator, SchemaValidator)
