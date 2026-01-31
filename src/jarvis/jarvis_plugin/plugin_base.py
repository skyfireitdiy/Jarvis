"""插件基类定义

定义所有插件必须实现的接口和元数据结构。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PluginMeta:
    """插件元数据

    Attributes:
        name: 插件名称（唯一标识）
        version: 插件版本号
        description: 插件描述
        author: 插件作者
        dependencies: 依赖的其他插件名称列表
        priority: 加载优先级（数字越小优先级越高）
        tags: 插件标签列表
        config_schema: 配置项的JSON Schema（可选）
    """

    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    dependencies: list[str] = field(default_factory=list)
    priority: int = 100
    tags: list[str] = field(default_factory=list)
    config_schema: dict[str, Any] | None = None


class PluginBase(ABC):
    """插件基类

    所有插件必须继承此类并实现抽象方法。

    生命周期：
    1. __init__: 构造函数，接收配置
    2. initialize: 初始化资源
    3. start: 启动插件
    4. stop: 停止插件
    5. cleanup: 清理资源

    Example:
        ```python
        class MyPlugin(PluginBase):
    @classmethod
    def get_meta(cls) -> PluginMeta:
                return PluginMeta(
                    name="my_plugin",
                    version="1.0.0",
                    description="My awesome plugin"
                )

    def initialize(self) -> None:
                self.db = Database()

    def start(self) -> None:
                self.db.connect()

    def stop(self) -> None:
                self.db.disconnect()

    def cleanup(self) -> None:
                self.db = None
        ```
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """初始化插件

        Args:
            config: 插件配置字典
        """
        self._config = config or {}
        self._initialized = False
        self._started = False

    @property
    def config(self) -> dict[str, Any]:
        """获取插件配置"""
        return self._config

    @property
    def is_initialized(self) -> bool:
        """是否已初始化"""
        return self._initialized

    @property
    def is_started(self) -> bool:
        """是否已启动"""
        return self._started

    @classmethod
    @abstractmethod
    def get_meta(cls) -> PluginMeta:
        """获取插件元数据

        Returns:
            插件元数据对象
        """
        ...

    def initialize(self) -> None:
        """初始化插件资源

        在插件加载后调用，用于初始化资源。
        子类可以重写此方法。
        """
        self._initialized = True

    def start(self) -> None:
        """启动插件

        在初始化后调用，用于启动插件服务。
        子类可以重写此方法。
        """
        if not self._initialized:
            raise RuntimeError("Plugin must be initialized before starting")
        self._started = True

    def stop(self) -> None:
        """停止插件

        在卸载前调用，用于停止插件服务。
        子类可以重写此方法。
        """
        self._started = False

    def cleanup(self) -> None:
        """清理插件资源

        在停止后调用，用于清理资源。
        子类可以重写此方法。
        """
        self._initialized = False

    def get_status(self) -> dict[str, Any]:
        """获取插件状态

        Returns:
            包含插件状态信息的字典
        """
        meta = self.get_meta()
        return {
            "name": meta.name,
            "version": meta.version,
            "initialized": self._initialized,
            "started": self._started,
        }
