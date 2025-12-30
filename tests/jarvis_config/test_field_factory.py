"""Field Factory 单元测试"""

import pytest

from jarvis.jarvis_config.field_factory import (
    FieldFactory,
    InputField,
    NumberField,
    EnumField,
    BooleanField,
    ArrayField,
    ArrayItemField,
    ObjectEditModal,
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


class TestArrayFieldNewFeatures:
    """测试 ArrayField 新增功能。"""

    def test_array_field_with_items_schema(self):
        """测试带 items_schema 的数组字段创建。"""
        schema = {
            "type": "object",
            "properties": {"tags": {"type": "array", "items": {"type": "string"}}},
        }
        parser = SchemaParser(schema)
        factory = FieldFactory(parser)

        field = factory.create_field(
            "tags", "Tags", defaults={"tags": ["tag1", "tag2"]}
        )
        assert field is not None
        assert isinstance(field, ArrayField)
        assert field.field_name == "Tags"
        assert field.field_type == "array"
        assert field.items_schema == {"type": "string"}

    def test_array_field_with_number_items(self):
        """测试数字类型数组字段。"""
        schema = {
            "type": "object",
            "properties": {"scores": {"type": "array", "items": {"type": "number"}}},
        }
        parser = SchemaParser(schema)
        factory = FieldFactory(parser)

        field = factory.create_field("scores", "Scores")
        assert field is not None
        assert isinstance(field, ArrayField)
        assert field.items_schema == {"type": "number"}

    def test_array_field_with_integer_items(self):
        """测试整数类型数组字段。"""
        schema = {
            "type": "object",
            "properties": {"counts": {"type": "array", "items": {"type": "integer"}}},
        }
        parser = SchemaParser(schema)
        factory = FieldFactory(parser)

        field = factory.create_field("counts", "Counts")
        assert field is not None
        assert isinstance(field, ArrayField)
        assert field.items_schema == {"type": "integer"}

    def test_array_field_with_boolean_items(self):
        """测试布尔类型数组字段。"""
        schema = {
            "type": "object",
            "properties": {"flags": {"type": "array", "items": {"type": "boolean"}}},
        }
        parser = SchemaParser(schema)
        factory = FieldFactory(parser)

        field = factory.create_field("flags", "Flags")
        assert field is not None
        assert isinstance(field, ArrayField)
        assert field.items_schema == {"type": "boolean"}

    def test_array_field_with_object_items(self):
        """测试对象类型数组字段。"""
        schema = {
            "type": "object",
            "properties": {
                "users": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "age": {"type": "integer"},
                        },
                    },
                }
            },
        }
        parser = SchemaParser(schema)
        factory = FieldFactory(parser)

        field = factory.create_field("users", "Users")
        assert field is not None
        assert isinstance(field, ArrayField)
        assert field.items_schema == {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        }


class TestArrayItemField:
    """测试 ArrayItemField 类。"""

    def test_array_item_field_string(self):
        """测试字符串类型数组项。"""
        items_schema = {"type": "string"}
        item = ArrayItemField(items_schema=items_schema, index=0, value="test")
        assert item.index == 0
        assert item.value == "test"
        assert item.items_schema == items_schema

    def test_array_item_field_number(self):
        """测试数字类型数组项。"""
        items_schema = {"type": "number"}
        item = ArrayItemField(items_schema=items_schema, index=1, value=3.14)
        assert item.index == 1
        assert item.value == 3.14

    def test_array_item_field_boolean(self):
        """测试布尔类型数组项。"""
        items_schema = {"type": "boolean"}
        item = ArrayItemField(items_schema=items_schema, index=2, value=True)
        assert item.index == 2
        assert item.value is True

    def test_array_item_field_object(self):
        """测试对象类型数组项。"""
        items_schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        item = ArrayItemField(
            items_schema=items_schema, index=0, value={"name": "test"}
        )
        assert item.index == 0
        assert item.value == {"name": "test"}


class TestObjectEditModal:
    """测试 ObjectEditModal 类。"""

    def test_object_edit_modal_init(self):
        """测试对象编辑模态窗口初始化。"""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        }
        modal = ObjectEditModal(
            schema=schema, initial_value={"name": "John", "age": 30}, title="Edit User"
        )
        assert modal.schema == schema
        assert modal.initial_value == {"name": "John", "age": 30}
        assert modal.title == "Edit User"

    def test_object_edit_modal_collect_values(self):
        """测试收集表单值（在没有实际 Widget 的情况下测试逻辑）。"""
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        modal = ObjectEditModal(
            schema=schema, initial_value={"name": "John"}, title="Edit User"
        )
        # _collect_values 方法需要实际的 Widget 环境
        # 这里只测试基本初始化
        assert modal.schema == schema


class TestArrayFieldMethods:
    """测试 ArrayField 的核心方法。"""

    def test_array_field_get_value_empty(self):
        """测试空数组的 get_value 方法。"""
        schema = {
            "type": "object",
            "properties": {"tags": {"type": "array", "items": {"type": "string"}}},
        }
        parser = SchemaParser(schema)
        factory = FieldFactory(parser)

        field = factory.create_field("tags", "Tags", defaults={"tags": []})
        assert field is not None
        # 空数组的 get_value 应返回空列表
        assert field.get_value() == []

    def test_array_field_get_value_with_defaults(self):
        """测试有默认值的 get_value 方法。"""
        schema = {
            "type": "object",
            "properties": {"numbers": {"type": "array", "items": {"type": "integer"}}},
        }
        parser = SchemaParser(schema)
        factory = FieldFactory(parser)

        # 创建带默认值的字段
        field = factory.create_field(
            "numbers", "Numbers", defaults={"numbers": [1, 2, 3]}
        )
        assert field is not None
        # 注意：get_value 的实际值需要 Widget 环境，这里测试初始化
        assert field._default_value == [1, 2, 3]

    def test_array_field_set_value(self):
        """测试 set_value 方法（需要在 Widget 环境中完整测试）。"""
        schema = {
            "type": "object",
            "properties": {"items": {"type": "array", "items": {"type": "string"}}},
        }
        parser = SchemaParser(schema)
        factory = FieldFactory(parser)

        field = factory.create_field("items", "Items", defaults={"items": ["a", "b"]})
        assert field is not None

        # set_value 方法需要 Widget 环境（query_one、mount 等）
        # 这里测试方法存在性和基本参数处理
        assert hasattr(field, "set_value")
        assert callable(field.set_value)

    def test_array_field_items_management(self):
        """测试数组项管理相关的属性和方法。"""
        schema = {
            "type": "object",
            "properties": {"flags": {"type": "array", "items": {"type": "boolean"}}},
        }
        parser = SchemaParser(schema)
        factory = FieldFactory(parser)

        field = factory.create_field(
            "flags", "Flags", defaults={"flags": [True, False]}
        )
        assert field is not None

        # 验证 items_schema 属性
        assert field.items_schema == {"type": "boolean"}

        # 验证 _items 列表初始化
        assert hasattr(field, "_items")
        assert isinstance(field._items, list)

        # 验证管理方法存在
        assert hasattr(field, "_add_item")
        assert hasattr(field, "_remove_item")
        assert hasattr(field, "_reindex_items")

        # 注意：这些方法的实际功能需要完整的 Widget 环境
        # 需要通过集成测试或端到端测试来验证


class TestArrayItemFieldMethods:
    """测试 ArrayItemField 的核心方法。"""

    def test_array_item_field_get_value_string(self):
        """测试字符串类型数组项的 get_value 方法基础逻辑。"""
        items_schema = {"type": "string"}
        item = ArrayItemField(items_schema=items_schema, index=0, value="test value")
        assert item.value == "test value"
        # get_value 需要 Widget 环境（query_one 获取 Input）
        assert hasattr(item, "get_value")
        assert callable(item.get_value)

    def test_array_item_field_set_value_number(self):
        """测试数字类型数组项的 set_value 方法基础逻辑。"""
        items_schema = {"type": "number"}
        item = ArrayItemField(items_schema=items_schema, index=0, value=3.14)
        assert item.value == 3.14
        # set_value 需要 Widget 环境（query_one 获取 Input）
        assert hasattr(item, "set_value")
        assert callable(item.set_value)

    def test_array_item_field_on_remove_callback(self):
        """测试删除回调函数的设置。"""
        items_schema = {"type": "string"}
        removed_indices = []

        def mock_remove_callback(index):
            removed_indices.append(index)

        item = ArrayItemField(
            items_schema=items_schema,
            index=5,
            value="test",
            on_remove=mock_remove_callback,
        )
        assert item.on_remove is not None
        assert callable(item.on_remove)


class TestArrayFieldIntegration:
    """测试 ArrayField 的集成功能（使用 Mock 模拟 Widget 环境）。"""

    def test_add_item_with_mock(self):
        """测试添加项功能（使用 Mock 模拟 Widget 环境）。"""
        from unittest.mock import MagicMock

        schema = {
            "type": "object",
            "properties": {"items": {"type": "array", "items": {"type": "string"}}},
        }
        parser = SchemaParser(schema)
        factory = FieldFactory(parser)

        # 创建 ArrayField 实例
        field = factory.create_field("items", "Items", defaults={"items": ["a", "b"]})
        assert field is not None

        # Mock 容器和子控件
        mock_container = MagicMock()
        mock_container.mount = MagicMock()

        # Mock query_one 方法
        original_items = field._items[:]

        # 使用 Mock 模拟 Vertical 容器
        mock_vertical = MagicMock()
        mock_vertical.mount = MagicMock()

        # 调用 _add_item_to_container 方法
        field._add_item_to_container(mock_vertical, 2, "c")

        # 验证项数增加
        assert len(field._items) == len(original_items) + 1
        # 验证新项的索引
        assert field._items[-1].index == 2
        # 验证容器被调用了 mount
        mock_vertical.mount.assert_called()

    def test_remove_item_with_mock(self):
        """测试删除项功能（使用 Mock 模拟 Widget 环境）。"""
        from unittest.mock import MagicMock

        schema = {
            "type": "object",
            "properties": {"items": {"type": "array", "items": {"type": "string"}}},
        }
        parser = SchemaParser(schema)
        factory = FieldFactory(parser)

        # 创建 ArrayField 实例
        field = factory.create_field(
            "items", "Items", defaults={"items": ["a", "b", "c"]}
        )
        assert field is not None

        # 创建 Mock 的数组项
        from jarvis.jarvis_config.field_factory import ArrayItemField

        # 手动添加三个项
        item0 = ArrayItemField(items_schema={"type": "string"}, index=0, value="a")
        item1 = ArrayItemField(items_schema={"type": "string"}, index=1, value="b")
        item2 = ArrayItemField(items_schema={"type": "string"}, index=2, value="c")

        # Mock remove 方法
        item0.remove = MagicMock()
        item1.remove = MagicMock()
        item2.remove = MagicMock()

        field._items = [item0, item1, item2]

        # 删除索引为 1 的项
        field._remove_item(1)

        # 验证项数减少
        assert len(field._items) == 2
        # 验证删除的项调用了 remove
        item1.remove.assert_called()
        # 验证剩余项的索引已更新
        assert field._items[0].index == 0
        assert field._items[1].index == 1

    def test_reindex_items(self):
        """测试删除后重新索引功能。"""
        from jarvis.jarvis_config.field_factory import ArrayItemField

        schema = {
            "type": "object",
            "properties": {"items": {"type": "array", "items": {"type": "string"}}},
        }
        parser = SchemaParser(schema)
        factory = FieldFactory(parser)

        # 创建 ArrayField 实例
        field = factory.create_field(
            "items", "Items", defaults={"items": ["a", "b", "c"]}
        )
        assert field is not None

        # 创建数组项
        item0 = ArrayItemField(items_schema={"type": "string"}, index=0, value="a")
        item1 = ArrayItemField(
            items_schema={"type": "string"}, index=2, value="b"
        )  # 故意设置错误的索引
        item2 = ArrayItemField(
            items_schema={"type": "string"}, index=5, value="c"
        )  # 故意设置错误的索引

        field._items = [item0, item1, item2]

        # 调用重新索引
        field._reindex_items()

        # 验证索引已更新
        assert field._items[0].index == 0
        assert field._items[1].index == 1
        assert field._items[2].index == 2

    def test_get_value_with_mock(self):
        """测试 get_value 方法（使用 Mock 模拟 Widget 环境）。"""
        from unittest.mock import MagicMock
        from jarvis.jarvis_config.field_factory import ArrayItemField

        schema = {
            "type": "object",
            "properties": {"items": {"type": "array", "items": {"type": "string"}}},
        }
        parser = SchemaParser(schema)
        factory = FieldFactory(parser)

        # 创建 ArrayField 实例
        field = factory.create_field("items", "Items", defaults={"items": []})
        assert field is not None

        # 创建数组项并 Mock get_value 方法
        item0 = ArrayItemField(items_schema={"type": "string"}, index=0, value="a")
        item1 = ArrayItemField(items_schema={"type": "string"}, index=1, value="b")

        # Mock get_value 方法（因为原方法需要 Widget 环境）
        item0.get_value = MagicMock(return_value="a")
        item1.get_value = MagicMock(return_value="b")

        field._items = [item0, item1]

        # 获取值
        values = field.get_value()

        # 验证返回值
        assert values == ["a", "b"]
        # 验证每个项的 get_value 被调用
        item0.get_value.assert_called()
        item1.get_value.assert_called()

    def test_set_value_with_mock(self):
        """测试 set_value 方法（使用 Mock 模拟 Widget 环境）。"""
        from unittest.mock import MagicMock

        schema = {
            "type": "object",
            "properties": {"items": {"type": "array", "items": {"type": "string"}}},
        }
        parser = SchemaParser(schema)
        factory = FieldFactory(parser)

        # 创建 ArrayField 实例
        field = factory.create_field(
            "items", "Items", defaults={"items": ["old1", "old2"]}
        )
        assert field is not None

        # Mock 容器
        mock_container = MagicMock()
        mock_container.children = []
        mock_container.mount = MagicMock()

        # Mock query_one 方法
        field.query_one = MagicMock(return_value=mock_container)

        # 设置新值
        field.set_value(["new1", "new2", "new3"])

        # 验证现有项被清除（每个项的 remove 被调用）
        # 验证新项被添加
        # 由于 _add_item_to_container 使用的是真实的 ArrayItemField
        # 我们只需验证项数正确
        assert len(field._items) == 3


class TestObjectEditModalIntegration:
    """测试 ObjectEditModal 的集成功能。"""

    def test_modal_initialization(self):
        """测试模态窗口的初始化和属性。"""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        }
        initial_value = {"name": "John", "age": 30}

        modal = ObjectEditModal(
            schema=schema, initial_value=initial_value, title="Edit User"
        )

        # 验证属性设置
        assert modal.schema == schema
        assert modal.initial_value == initial_value
        assert modal.title == "Edit User"

    def test_modal_dismiss_result(self):
        """测试模态窗口的 dismiss 方法。"""
        from unittest.mock import MagicMock, patch

        schema = {"type": "object", "properties": {"name": {"type": "string"}}}

        modal = ObjectEditModal(
            schema=schema, initial_value={"name": "John"}, title="Edit User"
        )

        # Mock query_one 方法以避免 NoMatches 错误
        modal.query_one = MagicMock(return_value=MagicMock(children=[]))

        # Mock 父类的 dismiss 方法
        with patch.object(
            ObjectEditModal.__bases__[0], "dismiss", MagicMock()
        ) as mock_dismiss:
            # 模拟确认
            modal.on_confirm_pressed(None)
            mock_dismiss.assert_called()

            # 模拟取消
            modal.on_cancel_pressed(None)
            assert mock_dismiss.call_count == 2
