"""jarvis_config - JSON Schema TUI 配置模块

该模块提供基于 Textual 的 JSON Schema TUI 配置功能。

主要功能：
- 根据 JSON Schema 自动生成 TUI 配置界面
- 支持完整的 JSON Schema Draft 7+ 特性
- 支持嵌套对象和数组
- 提供清晰的验证和错误提示

使用示例:
    >>> from jarvis.jarvis_config import configure_by_tui
    >>>
    >>> schema = {
    ...     "type": "object",
    ...     "properties": {
    ...         "name": {"type": "string", "description": "用户名称"},
    ...         "age": {"type": "integer", "description": "用户年龄"},
    ...         "active": {"type": "boolean", "description": "是否激活"}
    ...     },
    ...     "required": ["name"]
    ... }
    >>>
    >>> result = configure_by_tui(schema, title="用户配置")
    >>> if result:
    ...     print(f"配置结果: {result}")
    ... else:
    ...     print("用户取消配置")
"""

from typing import Any, Dict, Optional

from .schema_parser import SchemaParser, parse_schema
from .validator import (
    SchemaValidator,
    ValidationError,
    ValidationResult,
    create_validator,
)
from .field_factory import FieldFactory, create_field_factory
from .tui_app import run_tui_form


__all__ = [
    # 公开 API
    "configure_by_tui",
    # Schema 解析
    "SchemaParser",
    "parse_schema",
    # 验证器
    "SchemaValidator",
    "ValidationError",
    "ValidationResult",
    "create_validator",
    # 字段工厂
    "FieldFactory",
    "create_field_factory",
    # TUI 应用
    "run_tui_form",
]


def configure_by_tui(
    schema: Dict[str, Any],
    defaults: Optional[Dict[str, Any]] = None,
    title: str = "Configuration",
) -> Optional[Dict[str, Any]]:
    """根据 JSON Schema 生成 TUI 配置界面。

    该函数根据提供的 JSON Schema 自动生成 Textual TUI 配置界面，
    用户可以在界面中填写配置，完成后返回配置结果。

    参数:
        schema: JSON Schema 定义字典，必须符合 Draft 7+ 规范。
            Schema 应该包含 type 和 properties 定义。

        defaults: 可选的默认值字典。字典中的字段名对应 Schema 中的
            属性名。如果提供了默认值，会在 TUI 界面中自动填充。
            defaults 中的值会覆盖 Schema 中定义的 default 值。

        title: TUI 应用的标题，显示在界面顶部。

    返回:
        配置结果字典，包含用户在 TUI 界面中填写和提交的值。
        如果用户点击取消按钮或按 Ctrl+C 取消，则返回 None。

    异常:
        ValueError: 如果 schema 格式无效
        ImportError: 如果 Textual 未安装

    示例:
        >>> from jarvis.jarvis_config import configure_by_tui
        >>>
        >>> # 简单配置示例
        >>> schema = {
        ...     "type": "object",
        ...     "properties": {
        ...         "name": {"type": "string", "description": "用户名称"},
        ...         "age": {"type": "integer", "description": "用户年龄"},
        ...         "email": {"type": "string", "description": "电子邮件"}
        ...     },
        ...     "required": ["name"]
        ... }
        >>>
        >>> result = configure_by_tui(schema, title="用户配置")
        >>> if result:
        ...     print(f"配置结果: {result}")
        ... else:
        ...     print("用户取消配置")

        >>> # 带默认值的配置示例
        >>> defaults = {
        ...     "name": "John",
        ...     "age": 30
        ... }
        >>> result = configure_by_tui(schema, defaults=defaults)

        >>> # 嵌套对象示例
        >>> nested_schema = {
        ...     "type": "object",
        ...     "properties": {
        ...         "user": {
        ...             "type": "object",
        ...             "properties": {
        ...                 "name": {"type": "string"},
        ...                 "email": {"type": "string"}
        ...             }
        ...         },
        ...         "settings": {
        ...             "type": "object",
        ...             "properties": {
        ...                 "theme": {"type": "string", "enum": ["light", "dark"]}
        ...             }
        ...         }
        ...     }
        ... }
        >>> result = configure_by_tui(nested_schema)

        >>> # 数组字段示例
        >>> array_schema = {
        ...     "type": "object",
        ...     "properties": {
        ...         "tags": {
        ...             "type": "array",
        ...             "items": {"type": "string"},
        ...             "description": "逗号分隔的标签"
        ...         }
        ...     }
        ... }
        >>> result = configure_by_tui(array_schema)

    注意:
        - 该函数会启动一个交互式 TUI 应用，需要在终端中运行
        - 用户必须填写所有必填字段才能提交
        - 用户可以按 Ctrl+C 或点击取消按钮来取消配置
        - 提交时会进行基本的类型验证，如果验证失败会显示错误
        - 对于数组字段，使用逗号分隔的字符串输入多个值
        - 对于嵌套对象，会以层级结构显示
    """
    return run_tui_form(schema=schema, defaults=defaults, title=title)
