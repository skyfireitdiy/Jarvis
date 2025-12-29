"""字段 Widget 工厂

该模块提供根据 JSON Schema 类型创建 Textual Widget 的功能。

功能：
- 根据 JSON Schema 类型创建对应的 Textual Widget
- 支持所有基础类型（string, number, integer, boolean, object, array）
- 支持必填标记（红星）
- 支持默认值填充
- 支持字段描述显示
- 支持约束条件验证
"""

from typing import Any, Dict, List, Optional, Union

try:
    from textual.widgets import (
        Input,
        TextArea,
        Select,
        Switch,
        Label,
        Static,
    )
    from textual.containers import Container
    from textual.reactive import reactive
except ImportError:
    raise ImportError(
        "Textual is not installed. Please install it with: pip install textual"
    )

from .schema_parser import SchemaParser


class FieldContainer(Container):
    """字段容器，包含标签、描述和输入控件。"""

    def __init__(
        self,
        field_name: str,
        field_type: str,
        is_required: bool = False,
        description: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """初始化字段容器。

        参数:
            field_name: 字段名称
            field_type: 字段类型
            is_required: 是否必填
            description: 字段描述
            **kwargs: 传递给父类的其他参数
        """
        super().__init__(**kwargs)
        self.field_name = field_name
        self.field_type = field_type
        self.is_required = is_required
        self.description = description

    def compose(self):
        """组合字段组件。"""
        # 创建标签（带必填标记）
        required_mark = " *" if self.is_required else ""
        label_text = f"{self.field_name}{required_mark}"
        yield Label(label_text, classes="field-label")

        # 创建描述
        if self.description:
            yield Static(self.description, classes="field-description")


class InputField(FieldContainer):
    """文本输入字段。"""

    value = reactive("")

    def __init__(
        self,
        field_name: str,
        field_type: str,
        is_required: bool = False,
        description: Optional[str] = None,
        default: str = "",
        placeholder: str = "",
        password: bool = False,
        **kwargs: Any,
    ) -> None:
        """初始化输入字段。

        参数:
            field_name: 字段名称
            field_type: 字段类型（string, number, integer）
            is_required: 是否必填
            description: 字段描述
            default: 默认值
            placeholder: 占位符
            password: 是否为密码字段
            **kwargs: 传递给父类的其他参数
        """
        super().__init__(
            field_name=field_name,
            field_type=field_type,
            is_required=is_required,
            description=description,
            **kwargs,
        )
        self._default_value = default
        self._placeholder = placeholder
        self._password = password

    def compose(self):
        """组合字段组件。"""
        yield from super().compose()
        yield Input(
            value=self._default_value,
            placeholder=self._placeholder,
            password=self._password,
            id=f"input-{self.field_name}",
            classes="field-input",
        )

    def get_value(self) -> str:
        """获取输入值。"""
        input_widget = self.query_one("#input-{}".format(self.field_name), Input)
        return input_widget.value

    def set_value(self, value: str) -> None:
        """设置输入值。"""
        input_widget = self.query_one("#input-{}".format(self.field_name), Input)
        input_widget.value = value


class NumberField(InputField):
    """数字输入字段。"""

    def __init__(
        self,
        field_name: str,
        field_type: str,
        is_required: bool = False,
        description: Optional[str] = None,
        default: Union[int, float] = 0,
        placeholder: str = "",
        min_value: Optional[Union[int, float]] = None,
        max_value: Optional[Union[int, float]] = None,
        **kwargs: Any,
    ) -> None:
        """初始化数字字段。

        参数:
            field_name: 字段名称
            field_type: 字段类型（number, integer）
            is_required: 是否必填
            description: 字段描述
            default: 默认值
            placeholder: 占位符
            min_value: 最小值
            max_value: 最大值
            **kwargs: 传递给父类的其他参数
        """
        super().__init__(
            field_name=field_name,
            field_type=field_type,
            is_required=is_required,
            description=description,
            default=str(default),
            placeholder=placeholder,
            **kwargs,
        )
        self._min_value = min_value
        self._max_value = max_value

    def get_value(self) -> Union[int, float]:
        """获取数字值。"""
        value_str = super().get_value()
        if not value_str:
            return 0
        if self.field_type == SchemaParser.TYPE_INTEGER:
            return int(value_str)
        return float(value_str)

    def set_value(self, value: Union[int, float]) -> None:
        """设置数字值。"""
        super().set_value(str(value))


class EnumField(FieldContainer):
    """枚举选择字段。"""

    def __init__(
        self,
        field_name: str,
        field_type: str,
        is_required: bool = False,
        description: Optional[str] = None,
        enum_values: List[Any] = [],
        default: Optional[Any] = None,
        allow_multiple: bool = False,
        **kwargs: Any,
    ) -> None:
        """初始化枚举字段。

        参数:
            field_name: 字段名称
            field_type: 字段类型（string, array）
            is_required: 是否必填
            description: 字段描述
            enum_values: 枚举值列表
            default: 默认值
            allow_multiple: 是否允许多选
            **kwargs: 传递给父类的其他参数
        """
        super().__init__(
            field_name=field_name,
            field_type=field_type,
            is_required=is_required,
            description=description,
            **kwargs,
        )
        self._enum_values = enum_values
        self._default_value = default
        self._allow_multiple = allow_multiple

    def compose(self):
        """组合字段组件。"""
        yield from super().compose()

        # 创建选项列表
        options = [(str(v), v) for v in self._enum_values]

        yield Select(
            options,
            value=self._default_value,
            allow_blank=not self.is_required,
            id=f"select-{self.field_name}",
            classes="field-select",
        )

    def get_value(self) -> Any:
        """获取选中的值。"""
        select_widget = self.query_one("#select-{}".format(self.field_name), Select)
        return select_widget.value

    def set_value(self, value: Any) -> None:
        """设置选中的值。"""
        select_widget = self.query_one("#select-{}".format(self.field_name), Select)
        select_widget.value = value


class BooleanField(FieldContainer):
    """布尔开关字段。"""

    def __init__(
        self,
        field_name: str,
        field_type: str,
        is_required: bool = False,
        description: Optional[str] = None,
        default: bool = False,
        **kwargs: Any,
    ) -> None:
        """初始化布尔字段。

        参数:
            field_name: 字段名称
            field_type: 字段类型（boolean）
            is_required: 是否必填
            description: 字段描述
            default: 默认值
            **kwargs: 传递给父类的其他参数
        """
        super().__init__(
            field_name=field_name,
            field_type=field_type,
            is_required=is_required,
            description=description,
            **kwargs,
        )
        self._default_value = default

    def compose(self):
        """组合字段组件。"""
        yield from super().compose()
        yield Switch(
            value=self._default_value,
            id=f"switch-{self.field_name}",
            classes="field-switch",
        )

    def get_value(self) -> bool:
        """获取开关值。"""
        switch_widget = self.query_one("#switch-{}".format(self.field_name), Switch)
        return switch_widget.value

    def set_value(self, value: bool) -> None:
        """设置开关值。"""
        switch_widget = self.query_one("#switch-{}".format(self.field_name), Switch)
        switch_widget.value = value


class ArrayField(FieldContainer):
    """数组输入字段（文本区域，逗号分隔）。"""

    def __init__(
        self,
        field_name: str,
        field_type: str,
        is_required: bool = False,
        description: Optional[str] = None,
        default: List[Any] = [],
        **kwargs: Any,
    ) -> None:
        """初始化数组字段。

        参数:
            field_name: 字段名称
            field_type: 字段类型（array）
            is_required: 是否必填
            description: 字段描述
            default: 默认值
            **kwargs: 传递给父类的其他参数
        """
        super().__init__(
            field_name=field_name,
            field_type=field_type,
            is_required=is_required,
            description=description,
            **kwargs,
        )
        self._default_value = default

    def compose(self):
        """组合字段组件。"""
        yield from super().compose()

        # 将默认列表转换为逗号分隔的字符串
        default_text = (
            ", ".join(str(v) for v in self._default_value)
            if self._default_value
            else ""
        )

        yield TextArea(
            default_text,
            id=f"textarea-{self.field_name}",
            classes="field-textarea",
        )

    def get_value(self) -> List[Any]:
        """获取数组值。"""
        textarea_widget = self.query_one(
            "#textarea-{}".format(self.field_name), TextArea
        )
        text = textarea_widget.text.strip()
        if not text:
            return []
        return [item.strip() for item in text.split(",")]

    def set_value(self, value: List[Any]) -> None:
        """设置数组值。"""
        textarea_widget = self.query_one(
            "#textarea-{}".format(self.field_name), TextArea
        )
        text = ", ".join(str(v) for v in value)
        textarea_widget.text = text


class FieldFactory:
    """字段 Widget 工厂，根据 JSON Schema 创建对应的 Textual Widget。"""

    def __init__(self, schema_parser: SchemaParser) -> None:
        """初始化字段工厂。

        参数:
            schema_parser: Schema 解析器实例
        """
        self.schema_parser = schema_parser

    def create_field(
        self,
        field_path: str,
        field_name: str,
        defaults: Optional[Dict[str, Any]] = None,
    ) -> FieldContainer:
        """创建字段 Widget。

        参数:
            field_path: 字段路径（用于嵌套字段）
            field_name: 字段显示名称
            defaults: 默认值字典

        返回:
            字段 Widget 实例

        异常:
            ValueError: 如果字段类型不支持
        """
        if defaults is None:
            defaults = {}

        # 获取字段信息
        field_type = self.schema_parser.get_field_type(field_path)
        is_required = self.schema_parser.is_required(field_path)
        description = self.schema_parser.get_field_description(field_path)
        default_value = self.schema_parser.get_default_value(field_path)

        # 如果 defaults 中有值，优先使用
        if field_path in defaults:
            default_value = defaults[field_path]

        # 检查是否为枚举类型
        enum_values = self.schema_parser.get_enum_values(field_path)

        # 根据类型创建 Widget
        if enum_values:
            # 枚举类型
            return self._create_enum_field(
                field_name=field_name,
                field_type=field_type,
                is_required=is_required,
                description=description,
                enum_values=enum_values,
                default_value=default_value,
            )

        if field_type == SchemaParser.TYPE_STRING:
            return self._create_string_field(
                field_name=field_name,
                field_type=field_type,
                is_required=is_required,
                description=description,
                default_value=default_value,
                field_path=field_path,
            )

        elif field_type in (SchemaParser.TYPE_NUMBER, SchemaParser.TYPE_INTEGER):
            return self._create_number_field(
                field_name=field_name,
                field_type=field_type,
                is_required=is_required,
                description=description,
                default_value=default_value,
                field_path=field_path,
            )

        elif field_type == SchemaParser.TYPE_BOOLEAN:
            return self._create_boolean_field(
                field_name=field_name,
                field_type=field_type,
                is_required=is_required,
                description=description,
                default_value=default_value,
            )

        elif field_type == SchemaParser.TYPE_ARRAY:
            # 检查数组项是否为枚举
            field_schema = self.schema_parser._get_field_schema(field_path)
            items_schema = field_schema.get("items", {})
            items_enum = None
            if "enum" in items_schema:
                items_enum = items_schema["enum"]

            if items_enum:
                return self._create_enum_field(
                    field_name=field_name,
                    field_type=field_type,
                    is_required=is_required,
                    description=description,
                    enum_values=items_enum,
                    default_value=default_value,
                    allow_multiple=True,
                )
            else:
                return self._create_array_field(
                    field_name=field_name,
                    field_type=field_type,
                    is_required=is_required,
                    description=description,
                    default_value=default_value,
                )

        elif field_type == SchemaParser.TYPE_OBJECT:
            # 嵌套对象，返回 None 由调用者处理
            return None

        elif field_type == SchemaParser.TYPE_NULL:
            # null 类型，返回空字段
            return FieldContainer(
                field_name=field_name,
                field_type=field_type,
                is_required=is_required,
                description=description,
            )

        else:
            raise ValueError(f"Unsupported field type: {field_type}")

    def _create_string_field(
        self,
        field_name: str,
        field_type: str,
        is_required: bool,
        description: Optional[str],
        default_value: Any,
        field_path: str,
    ) -> InputField:
        """创建字符串输入字段。"""
        # 获取约束条件（暂未使用，预留验证扩展）
        # constraints = self.schema_parser.get_constraints(field_path)

        # 转换默认值
        default_str = str(default_value) if default_value is not None else ""

        # 检查是否为密码字段（通过 description 或字段名判断）
        is_password = "password" in field_name.lower() or (
            description and "password" in description.lower()
        )

        return InputField(
            field_name=field_name,
            field_type=field_type,
            is_required=is_required,
            description=description,
            default=default_str,
            password=is_password,
        )

    def _create_number_field(
        self,
        field_name: str,
        field_type: str,
        is_required: bool,
        description: Optional[str],
        default_value: Any,
        field_path: str,
    ) -> NumberField:
        """创建数字输入字段。"""
        # 获取约束条件（暂未使用，预留验证扩展）
        # constraints = self.schema_parser.get_constraints(field_path)

        # 转换默认值
        if default_value is None:
            default_num = 0
        elif field_type == SchemaParser.TYPE_INTEGER:
            default_num = int(default_value)
        else:
            default_num = float(default_value)

        return NumberField(
            field_name=field_name,
            field_type=field_type,
            is_required=is_required,
            description=description,
            default=default_num,
        )

    def _create_boolean_field(
        self,
        field_name: str,
        field_type: str,
        is_required: bool,
        description: Optional[str],
        default_value: Any,
    ) -> BooleanField:
        """创建布尔开关字段。"""
        default_bool = bool(default_value) if default_value is not None else False

        return BooleanField(
            field_name=field_name,
            field_type=field_type,
            is_required=is_required,
            description=description,
            default=default_bool,
        )

    def _create_enum_field(
        self,
        field_name: str,
        field_type: str,
        is_required: bool,
        description: Optional[str],
        enum_values: List[Any],
        default_value: Any,
        allow_multiple: bool = False,
    ) -> EnumField:
        """创建枚举选择字段。"""
        return EnumField(
            field_name=field_name,
            field_type=field_type,
            is_required=is_required,
            description=description,
            enum_values=enum_values,
            default=default_value,
            allow_multiple=allow_multiple,
        )

    def _create_array_field(
        self,
        field_name: str,
        field_type: str,
        is_required: bool,
        description: Optional[str],
        default_value: Any,
    ) -> ArrayField:
        """创建数组输入字段。"""
        default_list = list(default_value) if default_value else []

        return ArrayField(
            field_name=field_name,
            field_type=field_type,
            is_required=is_required,
            description=description,
            default=default_list,
        )


def create_field_factory(schema: Dict[str, Any]) -> FieldFactory:
    """便捷函数：创建字段工厂实例。

    参数:
        schema: JSON Schema 定义字典

    返回:
        FieldFactory 实例
    """
    parser = SchemaParser(schema)
    return FieldFactory(parser)
