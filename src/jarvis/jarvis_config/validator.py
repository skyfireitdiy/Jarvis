"""JSON Schema 验证器

该模块提供 JSON Schema 验证功能，支持完整的 JSON Schema Draft 7+ 特性。

功能：
- 验证数据是否符合 JSON Schema 定义
- 支持所有基础类型验证
- 支持约束条件验证
- 支持嵌套对象和数组验证
- 提供清晰的错误信息
"""

from typing import Any, Dict, List, Optional

from .schema_parser import SchemaParser


class ValidationError:
    """验证错误信息类。"""

    def __init__(
        self,
        field_path: str,
        message: str,
        error_type: str = "validation_error",
    ) -> None:
        """初始化验证错误。

        参数:
            field_path: 字段路径
            message: 错误消息
            error_type: 错误类型
        """
        self.field_path = field_path
        self.message = message
        self.error_type = error_type

    def __repr__(self) -> str:
        """返回错误信息的字符串表示。"""
        return f"ValidationError(field='{self.field_path}', type='{self.error_type}', message='{self.message}')"

    def __str__(self) -> str:
        """返回用户友好的错误信息。"""
        if self.field_path:
            return f"{self.field_path}: {self.message}"
        return self.message


class ValidationResult:
    """验证结果类。"""

    def __init__(
        self, is_valid: bool = True, errors: Optional[List[ValidationError]] = None
    ) -> None:
        """初始化验证结果。

        参数:
            is_valid: 是否验证通过
            errors: 错误列表
        """
        self.is_valid = is_valid
        self.errors: List[ValidationError] = errors or []

    def add_error(self, error: ValidationError) -> None:
        """添加一个错误。"""
        self.errors.append(error)
        self.is_valid = False

    def get_error_messages(self) -> List[str]:
        """获取所有错误消息的列表。"""
        return [str(error) for error in self.errors]

    def __repr__(self) -> str:
        """返回验证结果的字符串表示。"""
        if self.is_valid:
            return "ValidationResult(is_valid=True)"
        return f"ValidationResult(is_valid=False, errors={len(self.errors)})"

    def __str__(self) -> str:
        """返回用户友好的验证结果。"""
        if self.is_valid:
            return "验证通过"
        return "验证失败:\n" + "\n".join(
            f"  - {error}" for error in self.get_error_messages()
        )


class SchemaValidator:
    """JSON Schema 验证器，支持 Draft 7+ 规范。

    该验证器能够根据 JSON Schema 定义验证数据，
    提供详细的错误信息。
    """

    def __init__(self, schema: Dict[str, Any]) -> None:
        """初始化 Schema 验证器。

        参数:
            schema: JSON Schema 定义字典，必须符合 Draft 7+ 规范

        异常:
            ValueError: 如果 schema 格式无效
        """
        self.parser = SchemaParser(schema)

    def validate(self, data: Dict[str, Any]) -> ValidationResult:
        """验证数据是否符合 Schema 定义。

        参数:
            data: 要验证的数据字典

        返回:
            ValidationResult 对象，包含验证结果和错误信息
        """
        result = ValidationResult()

        # 获取 Schema 的主要类型
        schema_type = self.parser.get_type()

        if schema_type == SchemaParser.TYPE_OBJECT:
            # 验证对象类型
            self._validate_object("", data, result)
        else:
            # 单个值验证
            error = self._validate_value("", data, "")
            if error:
                result.add_error(error)

        return result

    def validate_field(self, field_path: str, value: Any) -> Optional[ValidationError]:
        """验证单个字段值。

        参数:
            field_path: 字段路径
            value: 字段值

        返回:
            ValidationError 对象，验证通过返回 None
        """
        return self._validate_value(field_path, value, field_path)

    def _validate_object(
        self,
        field_path: str,
        data: Dict[str, Any],
        result: ValidationResult,
    ) -> None:
        """验证对象类型数据。

        参数:
            field_path: 字段路径
            data: 对象数据
            result: 验证结果对象
        """
        # 检查必填字段
        required_fields = self.parser.get_required_fields()
        for required_field in required_fields:
            if required_field not in data or data[required_field] is None:
                error = ValidationError(
                    field_path=required_field,
                    message="该字段为必填项",
                    error_type="required",
                )
                result.add_error(error)

        # 验证每个字段
        for field_name, field_value in data.items():
            current_path = f"{field_path}.{field_name}" if field_path else field_name

            # 验证字段值
            error = self._validate_value(current_path, field_value, current_path)
            if error:
                result.add_error(error)

    def _validate_value(
        self,
        field_path: str,
        value: Any,
        schema_path: str,
    ) -> Optional[ValidationError]:
        """验证单个值。

        参数:
            field_path: 用于错误信息的字段路径
            value: 要验证的值
            schema_path: 用于获取 Schema 定义的路径

        返回:
            ValidationError 对象，验证通过返回 None
        """
        try:
            field_type = self.parser.get_field_type(schema_path)
        except KeyError:
            # 字段不在 Schema 中，跳过验证
            return None

        # 如果值为 None 且字段非必填，跳过验证
        if value is None:
            if self.parser.is_required(schema_path):
                return ValidationError(
                    field_path=field_path,
                    message="该字段为必填项",
                    error_type="required",
                )
            return None

        # 类型验证
        type_error = self._validate_type(field_path, value, field_type, schema_path)
        if type_error:
            return type_error

        # 约束条件验证
        constraint_error = self._validate_constraints(
            field_path,
            value,
            field_type,
            schema_path,
        )
        if constraint_error:
            return constraint_error

        # 嵌套结构验证
        if field_type == SchemaParser.TYPE_OBJECT:
            return self._validate_nested_object(field_path, value, schema_path)
        elif field_type == SchemaParser.TYPE_ARRAY:
            return self._validate_array(field_path, value, schema_path)

        return None

    def _validate_type(
        self,
        field_path: str,
        value: Any,
        expected_type: str,
        schema_path: str,
    ) -> Optional[ValidationError]:
        """验证值类型。

        参数:
            field_path: 字段路径
            value: 要验证的值
            expected_type: 期望的类型
            schema_path: Schema 路径

        返回:
            ValidationError 对象，验证通过返回 None
        """
        # null 类型特殊处理
        if expected_type == SchemaParser.TYPE_NULL:
            if value is not None:
                return ValidationError(
                    field_path=field_path,
                    message=f"类型错误：期望 null，实际为 {type(value).__name__}",
                    error_type="type",
                )
            return None

        # 检查类型
        if expected_type == SchemaParser.TYPE_STRING:
            if not isinstance(value, str):
                return ValidationError(
                    field_path=field_path,
                    message=f"类型错误：期望 string，实际为 {type(value).__name__}",
                    error_type="type",
                )
        elif expected_type == SchemaParser.TYPE_NUMBER:
            try:
                float(value)
            except (ValueError, TypeError):
                return ValidationError(
                    field_path=field_path,
                    message=f"类型错误：期望 number，实际为 {type(value).__name__}",
                    error_type="type",
                )
        elif expected_type == SchemaParser.TYPE_INTEGER:
            try:
                int(value)
                if isinstance(value, float) and not value.is_integer():
                    raise ValueError("Not an integer")
            except (ValueError, TypeError):
                return ValidationError(
                    field_path=field_path,
                    message=f"类型错误：期望 integer，实际为 {type(value).__name__}",
                    error_type="type",
                )
        elif expected_type == SchemaParser.TYPE_BOOLEAN:
            if not isinstance(value, bool):
                return ValidationError(
                    field_path=field_path,
                    message=f"类型错误：期望 boolean，实际为 {type(value).__name__}",
                    error_type="type",
                )
        elif expected_type == SchemaParser.TYPE_ARRAY:
            if not isinstance(value, list):
                return ValidationError(
                    field_path=field_path,
                    message=f"类型错误：期望 array，实际为 {type(value).__name__}",
                    error_type="type",
                )
        elif expected_type == SchemaParser.TYPE_OBJECT:
            if not isinstance(value, dict):
                return ValidationError(
                    field_path=field_path,
                    message=f"类型错误：期望 object，实际为 {type(value).__name__}",
                    error_type="type",
                )

        return None

    def _validate_constraints(
        self,
        field_path: str,
        value: Any,
        field_type: str,
        schema_path: str,
    ) -> Optional[ValidationError]:
        """验证约束条件。

        参数:
            field_path: 字段路径
            value: 要验证的值
            field_type: 字段类型
            schema_path: Schema 路径

        返回:
            ValidationError 对象，验证通过返回 None
        """
        constraints = self.parser.get_constraints(schema_path)

        # 枚举验证
        if "enum" in constraints:
            enum_values = constraints["enum"]
            if value not in enum_values:
                return ValidationError(
                    field_path=field_path,
                    message=f"值无效：必须是以下之一 {enum_values}，实际为 '{value}'",
                    error_type="enum",
                )

        # 数值约束
        if field_type in (SchemaParser.TYPE_NUMBER, SchemaParser.TYPE_INTEGER):
            # 转换为数值类型
            num_value = (
                float(value) if field_type == SchemaParser.TYPE_NUMBER else int(value)
            )

            if "minimum" in constraints:
                min_val = constraints["minimum"]
                if num_value < min_val:
                    return ValidationError(
                        field_path=field_path,
                        message=f"值太小：最小值为 {min_val}，实际为 {num_value}",
                        error_type="minimum",
                    )

            if "maximum" in constraints:
                max_val = constraints["maximum"]
                if num_value > max_val:
                    return ValidationError(
                        field_path=field_path,
                        message=f"值太大：最大值为 {max_val}，实际为 {num_value}",
                        error_type="maximum",
                    )

            if "exclusiveMinimum" in constraints:
                ex_min_val = constraints["exclusiveMinimum"]
                if num_value <= ex_min_val:
                    return ValidationError(
                        field_path=field_path,
                        message=f"值必须大于 {ex_min_val}，实际为 {num_value}",
                        error_type="exclusiveMinimum",
                    )

            if "exclusiveMaximum" in constraints:
                ex_max_val = constraints["exclusiveMaximum"]
                if num_value >= ex_max_val:
                    return ValidationError(
                        field_path=field_path,
                        message=f"值必须小于 {ex_max_val}，实际为 {num_value}",
                        error_type="exclusiveMaximum",
                    )

        # 字符串约束
        elif field_type == SchemaParser.TYPE_STRING:
            str_value = str(value)

            if "minLength" in constraints:
                min_len = constraints["minLength"]
                if len(str_value) < min_len:
                    return ValidationError(
                        field_path=field_path,
                        message=f"字符串太短：最小长度为 {min_len}，实际为 {len(str_value)}",
                        error_type="minLength",
                    )

            if "maxLength" in constraints:
                max_len = constraints["maxLength"]
                if len(str_value) > max_len:
                    return ValidationError(
                        field_path=field_path,
                        message=f"字符串太长：最大长度为 {max_len}，实际为 {len(str_value)}",
                        error_type="maxLength",
                    )

            if "pattern" in constraints:
                import re

                pattern = constraints["pattern"]
                if not re.match(pattern, str_value):
                    return ValidationError(
                        field_path=field_path,
                        message=f"字符串不符合格式要求：{pattern}",
                        error_type="pattern",
                    )

        # 数组约束
        elif field_type == SchemaParser.TYPE_ARRAY:
            if not isinstance(value, list):
                return None

            if "minItems" in constraints:
                min_items = constraints["minItems"]
                if len(value) < min_items:
                    return ValidationError(
                        field_path=field_path,
                        message=f"数组项太少：最小项数为 {min_items}，实际为 {len(value)}",
                        error_type="minItems",
                    )

            if "maxItems" in constraints:
                max_items = constraints["maxItems"]
                if len(value) > max_items:
                    return ValidationError(
                        field_path=field_path,
                        message=f"数组项太多：最大项数为 {max_items}，实际为 {len(value)}",
                        error_type="maxItems",
                    )

            if "uniqueItems" in constraints and constraints["uniqueItems"]:
                if len(value) != len(set(value)):
                    return ValidationError(
                        field_path=field_path,
                        message="数组项必须唯一",
                        error_type="uniqueItems",
                    )

        return None

    def _validate_nested_object(
        self,
        field_path: str,
        value: Dict[str, Any],
        schema_path: str,
    ) -> Optional[ValidationError]:
        """验证嵌套对象。

        参数:
            field_path: 字段路径
            value: 对象值
            schema_path: Schema 路径

        返回:
            ValidationError 对象，验证通过返回 None
        """
        # 获取嵌套对象的验证器
        nested_parser = self.parser.get_nested_parser(schema_path)
        nested_validator = SchemaValidator(nested_parser.schema)

        # 验证嵌套对象
        result = nested_validator.validate(value)

        # 如果有错误，只返回第一个错误
        if not result.is_valid and result.errors:
            error = result.errors[0]
            # 修正错误路径
            error.field_path = (
                f"{field_path}.{error.field_path}" if error.field_path else field_path
            )
            return error

        return None

    def _validate_array(
        self,
        field_path: str,
        value: List[Any],
        schema_path: str,
    ) -> Optional[ValidationError]:
        """验证数组。

        参数:
            field_path: 字段路径
            value: 数组值
            schema_path: Schema 路径

        返回:
            ValidationError 对象，验证通过返回 None
        """
        # 获取当前字段的 Schema
        field_schema = self.parser._get_field_schema(schema_path)

        # 获取数组项的 Schema
        items_schema = field_schema.get("items", {})

        if not items_schema:
            # 如果没有定义 items schema，跳过验证
            return None

        # 验证每个数组项
        for i, item in enumerate(value):
            # 创建临时验证器验证数组项
            item_validator = SchemaValidator(items_schema)
            error = item_validator.validate_field("", item)

            if error:
                # 修正错误路径
                error.field_path = f"{field_path}[{i}]"
                return error

        return None


def create_validator(schema: Dict[str, Any]) -> SchemaValidator:
    """便捷函数：创建 SchemaValidator 实例。

    参数:
        schema: JSON Schema 定义字典

    返回:
        SchemaValidator 实例

    示例:
        >>> schema = {
        ...     "type": "object",
        ...     "properties": {
        ...         "name": {"type": "string"}
        ...     }
        ... }
        >>> validator = create_validator(schema)
        >>> result = validator.validate({"name": "John"})
        >>> result.is_valid
        True
    """
    return SchemaValidator(schema)
