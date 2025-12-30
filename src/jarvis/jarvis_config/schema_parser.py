# -*- coding: utf-8 -*-
"""
JSON Schema 解析器和验证器

支持 JSON Schema Draft-07 规范的基本功能
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, cast


class ValidationError(Exception):
    """Schema 验证错误"""

    def __init__(self, message: str, path: str = ""):
        self.message = message
        self.path = path
        super().__init__(f"{path}: {message}" if path else message)


class SchemaParser:
    """JSON Schema 解析器和验证器

    支持 JSON Schema Draft-07 的常用功能：
    - 基本类型：string, number, integer, boolean, array, object
    - 约束：enum, default, minimum, maximum, minLength, maxLength, pattern, required
    - 复杂结构：oneOf, anyOf, 嵌套对象和数组
    """

    def __init__(self, schema_path: Union[str, Path]):
        """初始化解析器

        Args:
            schema_path: JSON Schema 文件路径
        """
        self.schema_path = Path(schema_path)
        self.schema: Dict[str, Any] = self._load_schema()

    def _load_schema(self) -> Dict[str, Any]:
        """加载 JSON Schema 文件"""
        with open(self.schema_path, "r", encoding="utf-8") as f:
            return cast(Dict[str, Any], json.load(f))

    @staticmethod
    def load_schema(path: Union[str, Path]) -> Dict[str, Any]:
        """静态方法：加载 JSON Schema 文件

        Args:
            path: Schema 文件路径

        Returns:
            Schema 字典
        """
        with open(Path(path), "r", encoding="utf-8") as f:
            return cast(Dict[str, Any], json.load(f))

    def get_schema(self) -> Dict[str, Any]:
        """获取 Schema 对象

        Returns:
            Schema 字典
        """
        return self.schema

    def get_title(self) -> str:
        """获取 Schema 标题"""
        return cast(str, self.schema.get("title", "配置"))

    def get_description(self) -> str:
        """获取 Schema 描述"""
        return cast(str, self.schema.get("description", ""))

    def get_properties(self) -> Dict[str, Any]:
        """获取顶层属性"""
        return cast(Dict[str, Any], self.schema.get("properties", {}))

    def get_property_schema(self, property_name: str) -> Dict[str, Any]:
        """获取属性的 Schema

        Args:
            property_name: 属性名

        Returns:
            属性的 Schema 定义
        """
        properties = self.get_properties()
        if property_name not in properties:
            raise ValueError(f"Property '{property_name}' not found in schema")
        return cast(Dict[str, Any], properties[property_name])

    def get_required(self) -> List[str]:
        """获取必填属性列表"""
        return cast(List[str], self.schema.get("required", []))

    def get_default_value(self, property_name: str) -> Any:
        """获取属性的默认值

        Args:
            property_name: 属性名

        Returns:
            默认值，如果没有则返回 None
        """
        prop_schema = self.get_property_schema(property_name)
        return prop_schema.get("default")

    def get_type(self, property_name: str) -> str:
        """获取属性类型

        Args:
            property_name: 属性名

        Returns:
            类型字符串
        """
        prop_schema = self.get_property_schema(property_name)
        return cast(str, prop_schema.get("type", "string"))

    def get_enum(self, property_name: str) -> Optional[List[Any]]:
        """获取属性的枚举值

        Args:
            property_name: 属性名

        Returns:
            枚举值列表，如果没有则返回 None
        """
        prop_schema = self.get_property_schema(property_name)
        enum_val = prop_schema.get("enum")
        return cast(Optional[List[Any]], enum_val)

    def get_description_for_property(self, property_name: str) -> str:
        """获取属性的描述

        Args:
            property_name: 属性名

        Returns:
            描述字符串
        """
        prop_schema = self.get_property_schema(property_name)
        return cast(str, prop_schema.get("description", ""))

    def validate_config(self, config: Dict[str, Any]) -> List[ValidationError]:
        """验证配置是否符合 Schema

        Args:
            config: 配置字典

        Returns:
            验证错误列表，如果为空则验证通过
        """
        errors: List[ValidationError] = []
        self._validate_against_schema(config, self.schema, "", errors)
        return errors

    def _validate_against_schema(
        self,
        value: Any,
        schema: Dict[str, Any],
        path: str,
        errors: List[ValidationError],
    ) -> None:
        """递归验证值是否符合 Schema

        Args:
            value: 要验证的值
            schema: Schema 定义
            path: 当前验证路径（用于错误信息）
            errors: 错误列表（累积）
        """
        # 处理 oneOf
        if "oneOf" in schema:
            one_of_errors: List[ValidationError] = []
            matched = False
            for i, sub_schema in enumerate(schema["oneOf"]):
                sub_errors: List[ValidationError] = []
                self._validate_against_schema(value, sub_schema, path, sub_errors)
                if not sub_errors:
                    matched = True
                    break
                one_of_errors.extend(sub_errors)
            if not matched:
                errors.append(
                    ValidationError("Value does not match any schema in oneOf", path)
                )
            return

        # 处理 anyOf
        if "anyOf" in schema:
            for sub_schema in schema["anyOf"]:
                any_sub_errors: List[ValidationError] = []
                self._validate_against_schema(value, sub_schema, path, any_sub_errors)
                if not any_sub_errors:
                    return  # 至少匹配一个
            errors.append(
                ValidationError("Value does not match any schema in anyOf", path)
            )
            return

        # 验证类型
        if "type" in schema:
            type_errors = self._validate_type(value, schema["type"], path)
            if type_errors:
                errors.extend(type_errors)
                return

        # 验证枚举
        if "enum" in schema:
            if value not in schema["enum"]:
                errors.append(
                    ValidationError(
                        f"Value '{value}' not in enum: {schema['enum']}", path
                    )
                )
            return

        # 根据类型进行具体验证
        if isinstance(value, str):
            self._validate_string(value, schema, path, errors)
        elif isinstance(value, (int, float)):
            self._validate_number(value, schema, path, errors)
        elif isinstance(value, list):
            self._validate_array(value, schema, path, errors)
        elif isinstance(value, dict):
            self._validate_object(value, schema, path, errors)

    def _validate_type(
        self, value: Any, expected_type: Union[str, List[str]], path: str
    ) -> List[ValidationError]:
        """验证值类型

        Args:
            value: 要验证的值
            expected_type: 期望的类型（可以是字符串或列表）
            path: 当前路径

        Returns:
            错误列表
        """
        if isinstance(expected_type, list):
            for t in expected_type:
                errors = self._validate_type(value, t, path)
                if not errors:
                    return []  # 匹配一种类型即可
            return [
                ValidationError(
                    f"Expected type one of {expected_type}, got {type(value).__name__}",
                    path,
                )
            ]

        type_map: Dict[str, Any] = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
        }

        if expected_type not in type_map:
            return []  # 未知类型，跳过验证

        expected_python_type = type_map[expected_type]
        if not isinstance(value, expected_python_type):
            return [
                ValidationError(
                    f"Expected type {expected_type}, got {type(value).__name__}", path
                )
            ]

        # integer 必须是整数，不能是 float
        if expected_type == "integer" and isinstance(value, bool):
            return [ValidationError("Expected integer, got boolean", path)]

        return []

    def _validate_string(
        self,
        value: str,
        schema: Dict[str, Any],
        path: str,
        errors: List[ValidationError],
    ) -> None:
        """验证字符串约束

        Args:
            value: 字符串值
            schema: Schema 定义
            path: 当前路径
            errors: 错误列表
        """
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(
                ValidationError(
                    f"String length {len(value)} is less than minimum {schema['minLength']}",
                    path,
                )
            )

        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(
                ValidationError(
                    f"String length {len(value)} exceeds maximum {schema['maxLength']}",
                    path,
                )
            )

        if "pattern" in schema:
            try:
                if not re.match(schema["pattern"], value):
                    errors.append(
                        ValidationError(
                            f"String '{value}' does not match pattern '{schema['pattern']}'",
                            path,
                        )
                    )
            except re.error as e:
                errors.append(ValidationError(f"Invalid pattern: {e}", path))

        if "format" in schema:
            format_value = schema["format"]
            if format_value == "uri" and not value.startswith(
                ("http://", "https://", "/")
            ):
                errors.append(ValidationError(f"Invalid URI format: {value}", path))

    def _validate_number(
        self,
        value: Union[int, float],
        schema: Dict[str, Any],
        path: str,
        errors: List[ValidationError],
    ) -> None:
        """验证数字约束

        Args:
            value: 数字值
            schema: Schema 定义
            path: 当前路径
            errors: 错误列表
        """
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(
                ValidationError(
                    f"Value {value} is less than minimum {schema['minimum']}", path
                )
            )

        if "maximum" in schema and value > schema["maximum"]:
            errors.append(
                ValidationError(
                    f"Value {value} exceeds maximum {schema['maximum']}", path
                )
            )

        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            errors.append(
                ValidationError(
                    f"Value {value} must be greater than {schema['exclusiveMinimum']}",
                    path,
                )
            )

        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            errors.append(
                ValidationError(
                    f"Value {value} must be less than {schema['exclusiveMaximum']}",
                    path,
                )
            )

    def _validate_array(
        self,
        value: List[Any],
        schema: Dict[str, Any],
        path: str,
        errors: List[ValidationError],
    ) -> None:
        """验证数组约束

        Args:
            value: 数组值
            schema: Schema 定义
            path: 当前路径
            errors: 错误列表
        """
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(
                ValidationError(
                    f"Array length {len(value)} is less than minimum {schema['minItems']}",
                    path,
                )
            )

        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(
                ValidationError(
                    f"Array length {len(value)} exceeds maximum {schema['maxItems']}",
                    path,
                )
            )

        # 验证数组项
        if "items" in schema and isinstance(schema["items"], dict):
            for i, item in enumerate(value):
                item_path = f"{path}[{i}]"
                self._validate_against_schema(item, schema["items"], item_path, errors)

    def _validate_object(
        self,
        value: Dict[str, Any],
        schema: Dict[str, Any],
        path: str,
        errors: List[ValidationError],
    ) -> None:
        """验证对象约束

        Args:
            value: 对象值
            schema: Schema 定义
            path: 当前路径
            errors: 错误列表
        """
        # 验证必填字段
        required = schema.get("required", [])
        for field in required:
            if field not in value:
                errors.append(
                    ValidationError(f"Required field '{field}' is missing", path)
                )

        # 验证属性
        properties = schema.get("properties", {})
        for field, field_value in value.items():
            if field in properties:
                field_path = f"{path}.{field}" if path else field
                self._validate_against_schema(
                    field_value, properties[field], field_path, errors
                )
            elif not schema.get("additionalProperties", True):
                errors.append(
                    ValidationError(f"Additional property '{field}' not allowed", path)
                )
