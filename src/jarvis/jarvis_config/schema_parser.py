"""JSON Schema 解析器

该模块提供 JSON Schema 解析功能，支持完整的 JSON Schema Draft 7+ 特性。

功能：
- 解析 JSON Schema 定义
- 获取字段类型、约束条件、默认值等元数据
- 支持嵌套对象和数组
- 支持所有基础类型验证
"""

from typing import Any, Dict, List, Optional


class SchemaParser:
    """JSON Schema 解析器，支持 Draft 7+ 规范。

    该解析器能够解析 JSON Schema 定义，并提供便捷的方法
    获取字段的各种元数据，包括类型、约束条件、默认值等。
    """

    # 支持的类型常量
    TYPE_STRING = "string"
    TYPE_NUMBER = "number"
    TYPE_INTEGER = "integer"
    TYPE_BOOLEAN = "boolean"
    TYPE_OBJECT = "object"
    TYPE_ARRAY = "array"
    TYPE_NULL = "null"

    # 所有支持的基础类型
    PRIMITIVE_TYPES = {
        TYPE_STRING,
        TYPE_NUMBER,
        TYPE_INTEGER,
        TYPE_BOOLEAN,
        TYPE_NULL,
    }

    # 复合类型
    COMPLEX_TYPES = {
        TYPE_OBJECT,
        TYPE_ARRAY,
    }

    # 所有支持类型
    ALL_TYPES = PRIMITIVE_TYPES | COMPLEX_TYPES

    def __init__(self, schema: Dict[str, Any]) -> None:
        """初始化 Schema 解析器。

        参数:
            schema: JSON Schema 定义字典，必须符合 Draft 7+ 规范

        异常:
            ValueError: 如果 schema 格式无效
        """
        if not isinstance(schema, dict):
            raise ValueError("Schema must be a dictionary")

        self.schema = schema
        self._cache: Dict[str, Any] = {}

    def parse_schema(self) -> Dict[str, Any]:
        """解析 JSON Schema，返回解析后的结构化数据。

        返回:
            包含解析结果的字典，包含以下键：
            - type: 主要类型
            - properties: object 类型的属性定义（如果是 object）
            - items: array 类型的项目定义（如果是 array）
            - required: 必填字段列表（如果是 object）
            - constraints: 约束条件字典
        """
        cache_key = "parsed_schema"
        if cache_key in self._cache:
            return self._cache[cache_key]

        result: Dict[str, Any] = {
            "type": self.get_type(),
            "constraints": self._extract_constraints(),
        }

        # 处理 object 类型
        if result["type"] == self.TYPE_OBJECT:
            result["properties"] = self.get_properties()
            result["required"] = self.get_required_fields()

        # 处理 array 类型
        elif result["type"] == self.TYPE_ARRAY:
            result["items"] = self.get_items_schema()

        self._cache[cache_key] = result
        return result

    def get_type(self) -> str:
        """获取 Schema 的主要类型。

        返回:
            类型字符串，如 'string', 'number', 'object' 等

        异常:
            ValueError: 如果类型无效或不支持
        """
        if "type" not in self.schema:
            raise ValueError("Schema must have a 'type' field")

        type_val = self.schema["type"]

        # 支持类型数组（如 ["string", "null"]）
        if isinstance(type_val, list):
            # 过滤掉 null 类型，返回第一个非 null 类型
            non_null_types = [t for t in type_val if t != self.TYPE_NULL]
            if non_null_types:
                return non_null_types[0]
            return self.TYPE_NULL

        if type_val not in self.ALL_TYPES:
            raise ValueError(f"Unsupported type: {type_val}")

        return type_val

    def get_field_type(self, field_path: str) -> str:
        """获取指定字段的类型。

        参数:
            field_path: 字段路径，如 'user.name' 或 'items.0.name'

        返回:
            字段类型字符串

        异常:
            KeyError: 如果字段不存在
        """
        field_schema = self._get_field_schema(field_path)
        return field_schema["type"]

    def is_required(self, field_path: str) -> bool:
        """检查字段是否为必填。

        参数:
            field_path: 字段路径

        返回:
            True 如果字段必填，否则 False
        """
        # 如果是根级别，总是必填
        if not field_path:
            return True

        parts = field_path.split(".")
        if len(parts) == 1:
            # 顶层字段
            required_fields = self.get_required_fields()
            return parts[0] in required_fields

        # 嵌套字段，检查其父对象是否需要该字段
        parent_path = ".".join(parts[:-1])
        field_name = parts[-1]

        try:
            parent_schema = self._get_field_schema(parent_path)
            required_fields = parent_schema.get("required", [])
            return field_name in required_fields
        except KeyError:
            return False

    def get_default_value(self, field_path: str) -> Any:
        """获取字段的默认值。

        参数:
            field_path: 字段路径

        返回:
            默认值，如果没有默认值返回 None
        """
        field_schema = self._get_field_schema(field_path)
        return field_schema.get("default")

    def get_field_description(self, field_path: str) -> Optional[str]:
        """获取字段的描述信息。

        参数:
            field_path: 字段路径

        返回:
            描述字符串，如果没有描述返回 None
        """
        field_schema = self._get_field_schema(field_path)
        return field_schema.get("description")

    def get_enum_values(self, field_path: str) -> Optional[List[Any]]:
        """获取枚举类型的可选值。

        参数:
            field_path: 字段路径

        返回:
            枚举值列表，如果不是枚举类型返回 None
        """
        field_schema = self._get_field_schema(field_path)
        return field_schema.get("enum")

    def get_properties(self) -> Dict[str, Dict[str, Any]]:
        """获取 object 类型的所有属性定义。

        返回:
            属性名字典，值为属性的 Schema 定义
        """
        if self.get_type() != self.TYPE_OBJECT:
            return {}

        return self.schema.get("properties", {})

    def get_required_fields(self) -> List[str]:
        """获取 object 类型的必填字段列表。

        返回:
            必填字段名称列表
        """
        if self.get_type() != self.TYPE_OBJECT:
            return []

        return self.schema.get("required", [])

    def get_items_schema(self) -> Optional[Dict[str, Any]]:
        """获取 array 类型的项目 Schema 定义。

        返回:
            数组项目的 Schema 定义，如果不是数组类型返回 None
        """
        if self.get_type() != self.TYPE_ARRAY:
            return None

        items = self.schema.get("items")
        if items is None:
            # 如果没有 items 定义，创建一个通用的 Schema
            return {"type": "string"}

        return items

    def get_constraints(self, field_path: str) -> Dict[str, Any]:
        """获取字段的所有约束条件。

        参数:
            field_path: 字段路径

        返回:
            约束条件字典，包含可能以下键：
            - minimum: 最小值（number/integer）
            - maximum: 最大值（number/integer）
            - minLength: 最小长度（string）
            - maxLength: 最大长度（string）
            - pattern: 正则表达式模式（string）
            - enum: 枚举值列表
            - minItems: 数组最小项数
            - maxItems: 数组最大项数
        """
        field_schema = self._get_field_schema(field_path)
        return self._extract_constraints_from_schema(field_schema)

    def has_nested_schema(self, field_path: str) -> bool:
        """检查字段是否有嵌套的 Schema（object 或 array）。

        参数:
            field_path: 字段路径

        返回:
            True 如果字段是 object 或 array 类型，否则 False
        """
        field_type = self.get_field_type(field_path)
        return field_type in self.COMPLEX_TYPES

    def get_nested_parser(self, field_path: str) -> "SchemaParser":
        """获取嵌套字段的 Schema 解析器。

        参数:
            field_path: 字段路径

        返回:
            嵌套字段的 SchemaParser 实例

        异常:
            ValueError: 如果字段没有嵌套 Schema
        """
        field_schema = self._get_field_schema(field_path)
        return SchemaParser(field_schema)

    def _get_field_schema(self, field_path: str) -> Dict[str, Any]:
        """获取指定字段的 Schema 定义。

        参数:
            field_path: 字段路径，如 'user.name'

        返回:
            字段的 Schema 定义字典

        异常:
            KeyError: 如果字段不存在
        """
        if not field_path:
            return self.schema

        parts = field_path.split(".")
        current = self.schema

        for i, part in enumerate(parts):
            if part.isdigit():
                # 数组索引（忽略具体索引值）
                _ = int(part)
                if "items" not in current:
                    raise KeyError(f"Cannot access array index at path '{field_path}'")
                current = current["items"]
            else:
                # 对象属性
                if "properties" not in current:
                    raise KeyError(
                        f"Cannot access property '{part}' at path '{field_path}'"
                    )
                if part not in current["properties"]:
                    raise KeyError(f"Property '{part}' not found in Schema")
                current = current["properties"][part]

        return current

    def _extract_constraints(self) -> Dict[str, Any]:
        """从当前 Schema 提取所有约束条件。"""
        return self._extract_constraints_from_schema(self.schema)

    def _extract_constraints_from_schema(
        self, schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """从 Schema 字典提取约束条件。

        参数:
            schema: Schema 定义字典

        返回:
            约束条件字典
        """
        constraints: Dict[str, Any] = {}

        # 数值约束
        if "minimum" in schema:
            constraints["minimum"] = schema["minimum"]
        if "maximum" in schema:
            constraints["maximum"] = schema["maximum"]
        if "exclusiveMinimum" in schema:
            constraints["exclusiveMinimum"] = schema["exclusiveMinimum"]
        if "exclusiveMaximum" in schema:
            constraints["exclusiveMaximum"] = schema["exclusiveMaximum"]

        # 字符串约束
        if "minLength" in schema:
            constraints["minLength"] = schema["minLength"]
        if "maxLength" in schema:
            constraints["maxLength"] = schema["maxLength"]
        if "pattern" in schema:
            constraints["pattern"] = schema["pattern"]
        if "format" in schema:
            constraints["format"] = schema["format"]

        # 枚举约束
        if "enum" in schema:
            constraints["enum"] = schema["enum"]

        # 数组约束
        if "minItems" in schema:
            constraints["minItems"] = schema["minItems"]
        if "maxItems" in schema:
            constraints["maxItems"] = schema["maxItems"]
        if "uniqueItems" in schema:
            constraints["uniqueItems"] = schema["uniqueItems"]

        return constraints


def parse_schema(schema: Dict[str, Any]) -> SchemaParser:
    """便捷函数：创建 SchemaParser 实例。

    参数:
        schema: JSON Schema 定义字典

    返回:
        SchemaParser 实例

    示例:
        >>> schema = {
        ...     "type": "object",
        ...     "properties": {
        ...         "name": {"type": "string"}
        ...     }
        ... }
        >>> parser = parse_schema(schema)
        >>> parser.get_type()
        'object'
    """
    return SchemaParser(schema)
