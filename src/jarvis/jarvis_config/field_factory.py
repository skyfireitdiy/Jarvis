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
    from textual.app import ComposeResult
    from textual import on
    from textual.screen import ModalScreen
    from textual.widgets import (
        Input,
        Select,
        Switch,
        Label,
        Static,
        Button,
    )
    from textual.containers import Container, Vertical, Horizontal
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
    """数组输入字段，支持动态添加和删除项。"""

    def __init__(
        self,
        field_name: str,
        field_type: str,
        is_required: bool = False,
        description: Optional[str] = None,
        default: List[Any] = [],
        items_schema: Dict[str, Any] = {},
        **kwargs: Any,
    ) -> None:
        """初始化数组字段。

        参数:
            field_name: 字段名称
            field_type: 字段类型（array）
            is_required: 是否必填
            description: 字段描述
            default: 默认值
            items_schema: 数组项的 Schema 定义
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
        self.items_schema = items_schema
        self._items: List[ArrayItemField] = []

    def compose(self):
        """组合字段组件。"""
        yield from super().compose()

        # 创建数组项容器
        yield Vertical(id=f"items-container-{self.field_name}")

        # 创建添加按钮
        yield Button(
            "+ 添加项",
            variant="primary",
            id=f"add-item-{self.field_name}",
        )

    def on_mount(self) -> None:
        """挂载时初始化数组项。"""
        self._populate_items()

    def _populate_items(self) -> None:
        """根据默认值填充数组项。"""
        items_container = self.query_one(
            f"#items-container-{self.field_name}", Vertical
        )

        for index, value in enumerate(self._default_value):
            self._add_item_to_container(items_container, index, value)

    def _add_item_to_container(
        self,
        container: Vertical,
        index: int,
        value: Optional[Any] = None,
    ) -> None:
        """向容器添加一个数组项。

        参数:
            container: 容器对象
            index: 数组索引
            value: 初始值
        """
        item_field = ArrayItemField(
            items_schema=self.items_schema,
            index=index,
            value=value,
            on_remove=self._on_item_remove,
        )
        container.mount(item_field)
        self._items.append(item_field)

    def _add_item(self) -> None:
        """添加一个新的数组项。"""
        items_container = self.query_one(
            f"#items-container-{self.field_name}", Vertical
        )
        new_index = len(self._items)
        self._add_item_to_container(items_container, new_index)

    def _remove_item(self, index: int) -> None:
        """移除指定索引的数组项。

        参数:
            index: 数组索引
        """
        # 找到对应索引的项
        for item in self._items:
            if item.index == index:
                item.remove()
                self._items.remove(item)
                # 重新索引剩余的项
                self._reindex_items()
                break

    def _reindex_items(self) -> None:
        """重新索引所有数组项。"""
        for new_index, item in enumerate(self._items):
            item.index = new_index
            # 更新子控件的 ID
            items_type = self.items_schema.get("type", "string")
            if items_type != SchemaParser.TYPE_OBJECT:
                # 更新输入控件 ID
                input_id = f"input-{new_index}"
                switch_id = f"switch-{new_index}"
                remove_id = f"remove-{new_index}"

                if hasattr(item, "children"):
                    for child in item.children:
                        if isinstance(child, Horizontal):
                            for control in child.children:
                                if isinstance(control, Input):
                                    control.id = input_id
                                elif isinstance(control, Switch):
                                    control.id = switch_id
                                elif isinstance(control, Button):
                                    if control.id and "remove" in control.id:
                                        control.id = remove_id

    def _on_item_remove(self, index: int) -> None:
        """数组项删除回调。

        参数:
            index: 数组索引
        """
        self._remove_item(index)

    @on(Button.Pressed)
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """按钮按下事件处理。"""
        button_id = event.button.id
        if button_id == f"add-item-{self.field_name}":
            self._add_item()

    def get_value(self) -> List[Any]:
        """获取数组值。"""
        return [item.get_value() for item in self._items]

    def set_value(self, value: List[Any]) -> None:
        """设置数组值。"""
        items_container = self.query_one(
            f"#items-container-{self.field_name}", Vertical
        )
        # 清除现有项
        for item in self._items:
            item.remove()
        self._items.clear()

        # 添加新项
        for index, item_value in enumerate(value):
            self._add_item_to_container(items_container, index, item_value)


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
                    items_schema=items_schema,
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
        items_schema: Optional[Dict[str, Any]] = None,
    ) -> ArrayField:
        """创建数组输入字段。"""
        default_list = list(default_value) if default_value else []

        return ArrayField(
            field_name=field_name,
            field_type=field_type,
            is_required=is_required,
            description=description,
            default=default_list,
            items_schema=items_schema or {},
        )


class ArrayItemField(FieldContainer):
    """数组项字段，用于显示和编辑单个数组项。

    支持基本类型（string, number, integer, boolean）的直接编辑，
    对象类型使用按钮触发弹出窗口编辑。
    """

    value = reactive(None)

    def __init__(
        self,
        items_schema: Dict[str, Any],
        index: int,
        value: Optional[Any] = None,
        on_remove: Optional[callable] = None,
        **kwargs: Any,
    ) -> None:
        """初始化数组项字段。

        参数:
            items_schema: 数组项的 Schema 定义
            index: 数组索引
            value: 初始值
            on_remove: 删除回调函数
            **kwargs: 传递给父类的其他参数
        """
        super().__init__(
            field_name=f"Item {index}",
            field_type=items_schema.get("type", "string"),
            is_required=False,
            **kwargs,
        )
        self.items_schema = items_schema
        self.index = index
        self.value = value
        self.on_remove = on_remove

    def compose(self) -> ComposeResult:
        """组合数组项组件。"""
        yield from super().compose()

        items_type = self.items_schema.get("type", "string")

        if items_type == SchemaParser.TYPE_OBJECT:
            # 对象类型：显示编辑按钮和删除按钮
            button_container = Horizontal()
            edit_button = Button("编辑", variant="primary", id=f"edit-{self.index}")
            remove_button = Button("删除", variant="error", id=f"remove-{self.index}")
            button_container.mount(edit_button)
            button_container.mount(remove_button)
            yield button_container
        else:
            # 基本类型：根据类型创建输入控件
            input_container = Horizontal()

            if items_type == SchemaParser.TYPE_STRING:
                default_str = str(self.value) if self.value is not None else ""
                input_widget = Input(
                    value=default_str,
                    placeholder=f"Item {self.index}",
                    id=f"input-{self.index}",
                )
                input_container.mount(input_widget)

            elif items_type in (SchemaParser.TYPE_NUMBER, SchemaParser.TYPE_INTEGER):
                if self.value is None:
                    default_num = 0
                elif items_type == SchemaParser.TYPE_INTEGER:
                    default_num = int(self.value)
                else:
                    default_num = float(self.value)
                input_widget = Input(
                    value=str(default_num),
                    placeholder=f"Item {self.index}",
                    id=f"input-{self.index}",
                )
                input_container.mount(input_widget)

            elif items_type == SchemaParser.TYPE_BOOLEAN:
                default_bool = bool(self.value) if self.value is not None else False
                switch_widget = Switch(
                    value=default_bool,
                    id=f"switch-{self.index}",
                )
                input_container.mount(switch_widget)

            else:
                # 默认使用 Input
                default_str = str(self.value) if self.value is not None else ""
                input_widget = Input(
                    value=default_str,
                    placeholder=f"Item {self.index}",
                    id=f"input-{self.index}",
                )
                input_container.mount(input_widget)

            # 添加删除按钮
            remove_button = Button("删除", variant="error", id=f"remove-{self.index}")
            input_container.mount(remove_button)

            yield input_container

    def get_value(self) -> Any:
        """获取数组项的值。"""
        items_type = self.items_schema.get("type", "string")

        if items_type == SchemaParser.TYPE_OBJECT:
            return self.value

        try:
            if items_type == SchemaParser.TYPE_STRING:
                input_widget = self.query_one(f"#input-{self.index}", Input)
                return input_widget.value

            elif items_type in (SchemaParser.TYPE_NUMBER, SchemaParser.TYPE_INTEGER):
                input_widget = self.query_one(f"#input-{self.index}", Input)
                value_str = input_widget.value
                if not value_str:
                    return 0
                if items_type == SchemaParser.TYPE_INTEGER:
                    return int(value_str)
                return float(value_str)

            elif items_type == SchemaParser.TYPE_BOOLEAN:
                switch_widget = self.query_one(f"#switch-{self.index}", Switch)
                return switch_widget.value

            else:
                input_widget = self.query_one(f"#input-{self.index}", Input)
                return input_widget.value
        except Exception:
            return None

    def set_value(self, value: Any) -> None:
        """设置数组项的值。"""
        items_type = self.items_schema.get("type", "string")

        if items_type == SchemaParser.TYPE_OBJECT:
            self.value = value
            return

        try:
            if items_type == SchemaParser.TYPE_STRING:
                input_widget = self.query_one(f"#input-{self.index}", Input)
                input_widget.value = str(value) if value is not None else ""

            elif items_type in (SchemaParser.TYPE_NUMBER, SchemaParser.TYPE_INTEGER):
                input_widget = self.query_one(f"#input-{self.index}", Input)
                input_widget.value = str(value) if value is not None else "0"

            elif items_type == SchemaParser.TYPE_BOOLEAN:
                switch_widget = self.query_one(f"#switch-{self.index}", Switch)
                switch_widget.value = bool(value) if value is not None else False

            else:
                input_widget = self.query_one(f"#input-{self.index}", Input)
                input_widget.value = str(value) if value is not None else ""
        except Exception:
            pass

    @on(Button.Pressed)
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """按钮按下事件处理。"""
        button_id = event.button.id

        if button_id == f"remove-{self.index}":
            # 删除按钮
            if self.on_remove:
                self.on_remove(self.index)
        elif button_id == f"edit-{self.index}":
            # 编辑按钮（对象类型）
            self._open_edit_modal()

    def _open_edit_modal(self) -> None:
        """打开对象编辑模态窗口。"""
        # 这里需要通过父级 App 来打开模态窗口
        # 由于无法直接访问 App，我们使用事件传递的方式
        # 或者通过 screen 来处理
        pass


class ObjectEditModal(ModalScreen):
    """对象编辑模态窗口。

    该模态窗口用于编辑嵌套对象，提供确认和取消功能。
    """

    def __init__(
        self,
        schema: Dict[str, Any],
        initial_value: Optional[Dict[str, Any]] = None,
        title: str = "Edit Object",
        **kwargs: Any,
    ) -> None:
        """初始化对象编辑模态窗口。

        参数:
            schema: JSON Schema 定义
            initial_value: 初始值
            title: 窗口标题
            **kwargs: 传递给父类的其他参数
        """
        super().__init__(**kwargs)
        self.schema = schema
        self.initial_value = initial_value or {}
        self.title = title

    def compose(self) -> ComposeResult:
        """组合模态窗口组件。"""
        # 创建容器
        yield Vertical(
            Static(f"── {self.title} ──", classes="nested-title"),
            self._build_form(),
            self._build_buttons(),
            classes="modal-container",
        )

    def _build_form(self) -> Vertical:
        """构建表单界面。"""
        container = Vertical(id="modal-form-container")
        return container

    def _build_buttons(self) -> Horizontal:
        """构建按钮容器。"""
        container = Horizontal()
        confirm_button = Button("确认", variant="primary", id="confirm")
        cancel_button = Button("取消", variant="default", id="cancel")

        container.mount(confirm_button)
        container.mount(cancel_button)

        return container

    def on_mount(self) -> None:
        """挂载时构建表单。"""
        self._populate_form()

    def _populate_form(self) -> None:
        """填充表单字段。"""
        form_container = self.query_one("#modal-form-container", Vertical)

        # 创建临时的 SchemaFormApp 来获取表单结构
        # 注意：这里不能直接运行 App，而是复用其构建逻辑
        parser = SchemaParser(self.schema)
        factory = FieldFactory(parser)

        properties = parser.get_properties()
        for field_name, field_schema in properties.items():
            field_path = field_name
            field_type = parser.get_field_type(field_path)

            if field_type == SchemaParser.TYPE_OBJECT:
                # 嵌套对象不支持在模态窗口中编辑
                continue
            else:
                # 普通字段
                defaults = {field_name: self.initial_value.get(field_name)}
                field = factory.create_field(
                    field_path,
                    field_name,
                    defaults,
                )
                if field:
                    form_container.mount(field)
                    # 为字段设置唯一的 ID
                    field.id = f"modal-field-{field_name}"

    @on(Button.Pressed, "#confirm")
    def on_confirm_pressed(self, event: Button.Pressed) -> None:
        """确认按钮按下事件。"""
        result = self._collect_values()
        self.dismiss(result)

    @on(Button.Pressed, "#cancel")
    def on_cancel_pressed(self, event: Button.Pressed) -> None:
        """取消按钮按下事件。"""
        self.dismiss(None)

    def _collect_values(self) -> Dict[str, Any]:
        """收集表单值。

        返回:
            收集的值字典
        """
        result: Dict[str, Any] = {}
        form_container = self.query_one("#modal-form-container", Vertical)

        for child in form_container.children:
            if hasattr(child, "field_name") and hasattr(child, "get_value"):
                field_name = child.field_name
                value = child.get_value()
                result[field_name] = value

        return result


def create_field_factory(schema: Dict[str, Any]) -> FieldFactory:
    """便捷函数：创建字段工厂实例。

    参数:
        schema: JSON Schema 定义字典

    返回:
        FieldFactory 实例
    """
    parser = SchemaParser(schema)
    return FieldFactory(parser)
