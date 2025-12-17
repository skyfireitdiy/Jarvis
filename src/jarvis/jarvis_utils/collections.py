"""
大小写不敏感的字典和其他集合工具类。

这个模块提供了大小写不敏感的字典实现，用于处理配置键的访问，
确保无论在何种大小写形式下都能正确访问相同的键值。
"""

from typing import Any
from typing import Dict
from typing import Iterator
from typing import Mapping
from typing import Optional
from typing import Tuple
from typing import Union

from collections.abc import ItemsView
from collections.abc import KeysView
from collections.abc import ValuesView


class CaseInsensitiveDict(Mapping[str, Any]):
    """
    大小写不敏感的字典类。

    这个字典类允许使用任意大小写形式的键来访问相同的值。
    内部使用小写形式存储键，但保留了原始的键名用于迭代和显示。

    示例:
        >>> d = CaseInsensitiveDict({'Content-Type': 'text/plain'})
        >>> d['content-type']
        'text/plain'
        >>> d['CONTENT-TYPE']
        'text/plain'
        >>> d['Content-Type']
        'text/plain'
        >>> list(d.keys())
        ['Content-Type']
    """

    def __init__(
        self, data: Optional[Union[Dict[str, Any], "CaseInsensitiveDict"]] = None
    ) -> None:
        """
        初始化CaseInsensitiveDict。

        Args:
            data: 可选的初始数据，可以是字典或另一个CaseInsensitiveDict
        """
        self._data: Dict[str, Any] = {}
        self._case_map: Dict[str, str] = {}  # 小写键 -> 原始键的映射

        if data is not None:
            if isinstance(data, CaseInsensitiveDict):
                # 从另一个CaseInsensitiveDict复制
                self._data = data._data.copy()
                self._case_map = data._case_map.copy()
            elif hasattr(data, "items"):
                # 从普通字典或其他映射类型初始化
                for key, value in data.items():
                    self[key] = value

    def __getitem__(self, key: str) -> Any:
        """
        通过键获取值，大小写不敏感。

        Args:
            key: 要查找的键

        Returns:
            对应的值

        Raises:
            KeyError: 如果键不存在
        """
        if not isinstance(key, str):
            raise TypeError(f"键必须是字符串类型，得到 {type(key).__name__}")

        lower_key = key.lower()
        if lower_key not in self._case_map:
            raise KeyError(key)

        return self._data[lower_key]

    def __setitem__(self, key: str, value: Any) -> None:
        """
        设置键值对，大小写不敏感。

        Args:
            key: 要设置的键
            value: 要设置的值
        """
        if not isinstance(key, str):
            raise TypeError(f"键必须是字符串类型，得到 {type(key).__name__}")

        lower_key = key.lower()
        # 如果键已存在，保持原有的原始键名；否则使用新的键名
        if lower_key not in self._case_map:
            self._case_map[lower_key] = key  # 保留原始键名
        self._data[lower_key] = value

    def __delitem__(self, key: str) -> None:
        """
        删除键值对，大小写不敏感。

        Args:
            key: 要删除的键

        Raises:
            KeyError: 如果键不存在
        """
        if not isinstance(key, str):
            raise TypeError(f"键必须是字符串类型，得到 {type(key).__name__}")

        lower_key = key.lower()
        if lower_key not in self._case_map:
            raise KeyError(key)

        del self._case_map[lower_key]
        del self._data[lower_key]

    def __contains__(self, key: object) -> bool:
        """
        检查键是否存在，大小写不敏感。

        Args:
            key: 要检查的键

        Returns:
            如果键存在返回True，否则返回False
        """
        if not isinstance(key, str):
            return False
        return key.lower() in self._case_map

    def __iter__(self) -> Iterator[str]:
        """
        返回键的迭代器，保持原始大小写。

        Returns:
            键的迭代器
        """
        return iter(self._case_map.values())

    def __len__(self) -> int:
        """
        返回字典中的键值对数量。

        Returns:
            键值对的数量
        """
        return len(self._data)

    def __repr__(self) -> str:
        """
        返回字典的字符串表示。

        Returns:
            字符串表示
        """
        items = []
        for original_key in self._case_map.values():
            value = self._data[original_key.lower()]
            items.append(f"{original_key!r}: {value!r}")
        return f"CaseInsensitiveDict({{{', '.join(items)}}})"

    def __eq__(self, other: object) -> bool:
        """
        比较两个字典是否相等。

        Args:
            other: 要比较的对象

        Returns:
            如果相等返回True，否则返回False
        """
        if not isinstance(other, CaseInsensitiveDict):
            return NotImplemented
        return self._data == other._data

    def copy(self) -> "CaseInsensitiveDict":
        """
        创建字典的浅拷贝。

        Returns:
            新的CaseInsensitiveDict实例
        """
        return CaseInsensitiveDict(self)

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取键对应的值，如果键不存在返回默认值。

        Args:
            key: 要查找的键
            default: 如果键不存在时返回的默认值

        Returns:
            键对应的值或默认值
        """
        try:
            return self[key]
        except KeyError:
            return default

    def keys(self) -> KeysView[str]:
        """
        返回所有键的视图，保持原始大小写。

        Returns:
            键的视图对象
        """
        return KeysView(self)

    def values(self) -> ValuesView[Any]:
        """
        返回所有值的视图。

        Returns:
            值的视图对象
        """
        return ValuesView(self)

    def items(self) -> ItemsView[str, Any]:
        """
        返回所有键值对的视图，键保持原始大小写。

        Returns:
            键值对的视图对象
        """
        return ItemsView(self)

    def pop(self, key: str, *args: Any) -> Any:
        """
        移除并返回指定键的值。

        Args:
            key: 要移除的键
            *args: 如果键不存在时的默认值（可选）

        Returns:
            键对应的值

        Raises:
            KeyError: 如果键不存在且没有提供默认值
        """
        if not isinstance(key, str):
            raise TypeError(f"键必须是字符串类型，得到 {type(key).__name__}")

        lower_key = key.lower()
        if lower_key not in self._case_map:
            if args:
                return args[0]
            raise KeyError(key)

        self._case_map.pop(lower_key)
        value = self._data.pop(lower_key)
        return value

    def popitem(self) -> Tuple[str, Any]:
        """
        移除并返回最后一个键值对。

        Returns:
            键值对

        Raises:
            KeyError: 如果字典为空
        """
        if not self._data:
            raise KeyError("字典为空")

        lower_key, value = self._data.popitem()
        original_key = self._case_map.pop(lower_key)
        return original_key, value

    def setdefault(self, key: str, default: Any = None) -> Any:
        """
        如果键存在返回对应的值，否则设置键的值为默认值并返回默认值。

        Args:
            key: 要查找的键
            default: 默认值

        Returns:
            键对应的值或默认值
        """
        try:
            return self[key]
        except KeyError:
            self[key] = default
            return default

    def update(self, *args: Any, **kwargs: Any) -> None:
        """
        更新字典。

        Args:
            *args: 可以是另一个字典或键值对的可迭代对象
            **kwargs: 关键字参数形式的键值对（下划线会被转换为连字符）
        """
        if args:
            other = args[0]
            if hasattr(other, "items"):
                for key, value in other.items():
                    self[key] = value
            else:
                for key, value in other:
                    self[key] = value

        for key, value in kwargs.items():
            # 将关键字参数中的下划线转换为连字符（用于HTTP头部等场景）
            normalized_key = key.replace("_", "-")
            self[normalized_key] = value

    def clear(self) -> None:
        """
        清空字典。
        """
        self._data.clear()
        self._case_map.clear()

    def lower_keys(self) -> Iterator[str]:
        """
        返回所有键的小写形式的迭代器。

        Returns:
            小写键的迭代器
        """
        return iter(self._case_map.keys())
