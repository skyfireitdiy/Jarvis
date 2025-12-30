"""TUI App 主类

该模块提供完整的 Textual TUI 配置界面。

功能：
- 动态生成表单界面
- 支持滚动浏览长表单
- 提供 [提交] 和 [取消] 按钮
- 实时验证输入
- 提交前完整验证
- 支持嵌套对象的层级显示
- 支持错误提示显示
"""

from typing import Any, Dict, List, Optional

try:
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical, Container, ScrollableContainer
    from textual.widgets import (
        Button,
        Static,
        Header,
        Footer,
    )
    from textual import on
    from textual.events import Key
except ImportError:
    raise ImportError(
        "Textual is not installed. Please install it with: pip install textual"
    )

from .schema_parser import SchemaParser
from .field_factory import FieldFactory


class FormSubmit:
    """表单提交事件。"""

    def __init__(self, result: Dict[str, Any]) -> None:
        self.result = result


class FormCancel:
    """表单取消事件。"""

    pass


class NestedObjectContainer(Vertical):
    """嵌套对象容器，用于显示层级结构。"""

    def __init__(self, title: str, **kwargs: Any) -> None:
        """初始化嵌套对象容器。

        参数:
            title: 对象标题
            **kwargs: 传递给父类的其他参数
        """
        super().__init__(**kwargs)
        self.title = title

    def compose(self) -> ComposeResult:
        """组合嵌套对象组件。"""
        yield Static(f"── {self.title} ──", classes="nested-title")
        yield Container()


class SchemaFormApp(App):
    """JSON Schema 表单应用。

    该应用根据 JSON Schema 动态生成表单界面，
    支持完整的表单交互流程。
    """

    CSS = """
    .field-container {
        padding: 1;
        margin-bottom: 1;
        border: solid $primary;
        background: $surface;
    }
    
    .field-label {
        color: $text;
        text-style: bold;
    }
    
    .field-description {
        color: $text-muted;
        padding-left: 2;
        margin-bottom: 1;
    }
    
    .nested-title {
        color: $accent;
        text-style: bold;
        padding: 1;
        background: $panel;
        margin-top: 1;
    }
    
    .error-message {
        color: $error;
        padding: 1;
        margin-bottom: 1;
        border: solid $error;
        background: $error-darken-3;
    }
    
    .button-container {
        height: 3;
        dock: bottom;
    }
    
    Button {
        width: 20;
        margin-right: 1;
    }
    """

    def __init__(
        self,
        schema: Dict[str, Any],
        defaults: Optional[Dict[str, Any]] = None,
        title: str = "Configuration",
        **kwargs: Any,
    ) -> None:
        """初始化表单应用。

        参数:
            schema: JSON Schema 定义
            defaults: 默认值字典
            title: 应用标题
            **kwargs: 传递给父类的其他参数
        """
        super().__init__(**kwargs)
        self.schema = schema
        self.defaults = defaults or {}
        self.title = title

        # 初始化解析器和工厂
        self.parser = SchemaParser(schema)
        self.factory = FieldFactory(self.parser)

        # 存储字段引用
        self.fields: Dict[str, Any] = {}

        # 结果存储
        self._result: Optional[Dict[str, Any]] = None
        self._cancelled: bool = False

    def compose(self) -> ComposeResult:
        """组合应用组件。"""
        yield Header()
        yield self._build_form()
        yield self._build_buttons()
        yield Footer()

    def on_mount(self) -> None:
        """应用挂载时调用。"""
        self.title = self.title

    def _build_form(self) -> ScrollableContainer:
        """构建表单界面。"""
        container = ScrollableContainer(id="form-container")

        # 根据类型构建表单
        schema_type = self.parser.get_type()

        if schema_type == SchemaParser.TYPE_OBJECT:
            self._build_object_form(container, "")
        else:
            # 单个字段
            field = self.factory.create_field("", "Value", self.defaults)
            if field:
                container.mount(field)
                self.fields[""] = field

        return container

    def _build_object_form(
        self,
        container: ScrollableContainer,
        parent_path: str,
    ) -> None:
        """构建对象类型的表单。

        参数:
            container: 容器对象
            parent_path: 父级路径
        """
        properties = self.parser.get_properties()

        for field_name, field_schema in properties.items():
            field_path = f"{parent_path}.{field_name}" if parent_path else field_name

            # 检查是否为嵌套对象或数组
            field_type = self.parser.get_field_type(field_path)

            if field_type == SchemaParser.TYPE_ARRAY:
                # 数组类型字段
                field = self.factory.create_field(
                    field_path,
                    field_name,
                    self.defaults,
                )
                if field:
                    container.mount(field)
                    self.fields[field_path] = field
            elif field_type == SchemaParser.TYPE_OBJECT:
                # 嵌套对象
                nested_container = NestedObjectContainer(field_name)
                container.mount(nested_container)

                # 获取嵌套对象的内部容器
                inner_container = nested_container.children[1]

                # 递归构建嵌套表单
                nested_parser = self.parser.get_nested_parser(field_path)
                nested_factory = FieldFactory(nested_parser)

                nested_properties = nested_parser.get_properties()
                for nested_field_name in nested_properties:
                    nested_field_path = f"{field_path}.{nested_field_name}"
                    nested_field = nested_factory.create_field(
                        nested_field_path,
                        nested_field_name,
                        self.defaults,
                    )
                    if nested_field:
                        inner_container.mount(nested_field)
                        self.fields[nested_field_path] = nested_field
            else:
                # 普通字段
                field = self.factory.create_field(
                    field_path,
                    field_name,
                    self.defaults,
                )
                if field:
                    container.mount(field)
                    self.fields[field_path] = field

    def _build_buttons(self) -> Horizontal:
        """构建按钮容器。"""
        container = Horizontal(classes="button-container")

        submit_button = Button("提交", variant="primary", id="submit")
        cancel_button = Button("取消", variant="default", id="cancel")

        container.mount(submit_button)
        container.mount(cancel_button)

        return container

    @on(Button.Pressed, "#submit")
    def on_submit_pressed(self, event: Button.Pressed) -> None:
        """提交按钮按下事件。"""
        # 验证并收集数据
        result = self._validate_and_collect()

        if result is None:
            # 验证失败，显示错误
            return

        # 保存结果并退出
        self._result = result
        self.exit(result=result)

    @on(Button.Pressed, "#cancel")
    def on_cancel_pressed(self, event: Button.Pressed) -> None:
        """取消按钮按下事件。"""
        self._cancelled = True
        self.exit()

    def on_key(self, event: Key) -> None:
        """按键事件处理。"""
        if event.key == "c" and event.ctrl:
            # Ctrl+C 取消
            self._cancelled = True
            self.exit()

    def _validate_and_collect(self) -> Optional[Dict[str, Any]]:
        """验证表单并收集数据。

        返回:
            收集的数据字典，验证失败返回 None
        """
        result: Dict[str, Any] = {}
        errors: List[str] = []

        for field_path, field in self.fields.items():
            try:
                # 获取字段值
                value = field.get_value()

                # 检查必填字段
                is_required = self.parser.is_required(field_path)
                if is_required and not value:
                    errors.append(f"字段 '{field}' 为必填项")
                    continue

                # 简单类型验证（基础验证）
                field_type = self.parser.get_field_type(field_path)
                if value:
                    if field_type == SchemaParser.TYPE_NUMBER:
                        try:
                            float(value)
                        except (ValueError, TypeError):
                            errors.append(f"字段 '{field}' 必须是数字")
                    elif field_type == SchemaParser.TYPE_INTEGER:
                        try:
                            int(value)
                        except (ValueError, TypeError):
                            errors.append(f"字段 '{field}' 必须是整数")

                # 存储值
                if field_path:
                    # 处理嵌套路径
                    self._set_nested_value(result, field_path, value)
                else:
                    # 根级值
                    result["value"] = value
            except Exception as e:
                errors.append(f"字段 '{field}' 获取值失败: {e}")

        # 如果有错误，显示并返回 None
        if errors:
            self._show_errors(errors)
            return None

        return result

    def _set_nested_value(self, data: Dict[str, Any], path: str, value: Any) -> None:
        """设置嵌套字典的值。

        参数:
            data: 目标字典
            path: 字段路径（如 'user.name'）
            value: 要设置的值
        """
        parts = path.split(".")
        current = data

        for i, part in enumerate(parts[:-1]):
            if part not in current:
                current[part] = {}
            elif not isinstance(current[part], dict):
                # 遇到冲突，需要处理
                current[part] = {}
            current = current[part]

        current[parts[-1]] = value

    def _show_errors(self, errors: List[str]) -> None:
        """显示错误信息。

        参数:
            errors: 错误信息列表
        """
        # 创建错误显示
        error_text = "\n".join(f"• {error}" for error in errors)
        error_widget = Static(error_text, classes="error-message", id="error-display")

        # 移除旧的错误显示
        old_error = self.query("#error-display")
        if old_error:
            old_error.remove()

        # 在表单容器顶部插入错误
        form_container = self.query_one("#form-container", ScrollableContainer)
        form_container.mount(error_widget, before=0)

        # 滚动到顶部
        form_container.scroll_home()

    def get_result(self) -> Optional[Dict[str, Any]]:
        """获取表单结果。

        返回:
            表单结果字典，用户取消返回 None
        """
        return self._result

    def is_cancelled(self) -> bool:
        """检查用户是否取消。"""
        return self._cancelled


def run_tui_form(
    schema: Dict[str, Any],
    defaults: Optional[Dict[str, Any]] = None,
    title: str = "Configuration",
) -> Optional[Dict[str, Any]]:
    """运行 TUI 表单应用。

    参数:
        schema: JSON Schema 定义
        defaults: 默认值字典
        title: 应用标题

    返回:
        表单结果字典，用户取消返回 None

    示例:
        >>> schema = {
        ...     "type": "object",
        ...     "properties": {
        ...         "name": {"type": "string"}
        ...     }
        ... }
        >>> result = run_tui_form(schema)
        >>> print(result)
        {'name': 'John'}
    """
    app = SchemaFormApp(schema=schema, defaults=defaults, title=title)

    try:
        result = app.run()
        return result
    except KeyboardInterrupt:
        return None
    except Exception:
        # 发生错误，返回 None
        return None
