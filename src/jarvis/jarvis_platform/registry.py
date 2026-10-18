# -*- coding: utf-8 -*-
import importlib
import inspect
import os
import sys
from typing import Dict
from typing import List
from typing import Optional
from typing import Type

from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_utils.config import get_cheap_platform_name
from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.config import get_eval_platform_name
from jarvis.jarvis_utils.config import get_normal_platform_name
from jarvis.jarvis_utils.config import get_smart_platform_name
from jarvis.jarvis_utils.config import is_eval_model_configured
from jarvis.jarvis_utils.output import PrettyOutput

REQUIRED_METHODS = [
    ("chat", ["message"]),  # 方法名和参数列表
    ("name", []),
    ("delete_chat", []),
    ("set_system_prompt", ["message"]),
    ("set_model_name", ["model_name"]),
    ("get_model_list", []),
]


class PlatformRegistry:
    """Platform registry"""

    global_platform_name: str = "openai"
    global_platform_registry: Optional["PlatformRegistry"] = None

    @staticmethod
    def get_platform_dir() -> str:
        user_platform_dir = os.path.join(get_data_dir(), "models")
        if not os.path.exists(user_platform_dir):
            try:
                os.makedirs(user_platform_dir)
                # 创建 __init__.py 使其成为 Python 包
                with open(
                    os.path.join(user_platform_dir, "__init__.py"), "w", errors="ignore"
                ):
                    pass
            except Exception as e:
                PrettyOutput.auto_print(f"❌ 创建平台目录失败: {str(e)}")
                return ""
        return user_platform_dir

    @staticmethod
    def check_platform_implementation(platform_class: Type[BasePlatform]) -> bool:
        """Check if the platform class implements all necessary methods

        Args:
            platform_class: The platform class to check

        Returns:
            bool: Whether all necessary methods are implemented
        """
        missing_methods = []

        for method_name, params in REQUIRED_METHODS:
            if not hasattr(platform_class, method_name):
                missing_methods.append(method_name)
                continue

            method = getattr(platform_class, method_name)
            if not callable(method):
                missing_methods.append(method_name)
                continue

            # 检查方法参数
            import inspect

            sig = inspect.signature(method)
            method_params = [p for p in sig.parameters if p != "self"]
            if len(method_params) != len(params):
                missing_methods.append(f"{method_name}(parameter mismatch)")

        if missing_methods:
            PrettyOutput.auto_print(
                f"⚠️ 平台 {platform_class.__name__} 缺少必要的方法: {', '.join(missing_methods)}"
            )
            return False

        return True

    @staticmethod
    def load_platform_from_dir(directory: str) -> Dict[str, Type[BasePlatform]]:
        """Load platforms from specified directory

        Args:
            directory: Platform directory path

        Returns:
            Dict[str, Type[BasePlatform]]: Platform name to platform class mapping
        """
        platforms: Dict[str, Type[BasePlatform]] = {}

        # 确保目录存在
        if not os.path.exists(directory):
            PrettyOutput.auto_print(f"⚠️ 平台目录不存在: {directory}")
            return platforms

        # 获取目录的包名
        package_name = None
        if directory == os.path.dirname(__file__):
            package_name = "jarvis.jarvis_platform"

        # 添加目录到Python路径
        if directory not in sys.path:
            sys.path.append(directory)

        error_lines = []
        # 遍历目录下的所有.py文件
        for filename in os.listdir(directory):
            if filename.endswith(".py") and not filename.startswith("__"):
                module_name = filename[:-3]  # 移除.py后缀
                try:
                    # 导入模块
                    if package_name:
                        module = importlib.import_module(
                            f"{package_name}.{module_name}"
                        )
                    else:
                        module = importlib.import_module(module_name)

                    # 遍历模块中的所有类
                    for _, obj in inspect.getmembers(module):
                        # 检查是否是BasePlatform的子类，但不是BasePlatform本身
                        if (
                            inspect.isclass(obj)
                            and issubclass(obj, BasePlatform)
                            and obj != BasePlatform
                        ):
                            # 检查平台实现
                            if not PlatformRegistry.check_platform_implementation(obj):
                                continue
                            try:
                                # 调用类方法 platform_name
                                platform_name = obj.platform_name()
                                platforms[platform_name] = obj
                            except Exception as e:
                                error_lines.append(
                                    f"实例化或注册平台失败 {obj.__name__}: {str(e)}"
                                )
                            break
                except Exception as e:
                    error_lines.append(f"加载平台 {module_name} 失败: {str(e)}")

        if error_lines:
            joined_errors = "\n".join(error_lines)
            PrettyOutput.auto_print(f"❌ {joined_errors}")
        return platforms

    @staticmethod
    def get_global_platform_registry() -> "PlatformRegistry":
        """Get global platform registry"""
        if PlatformRegistry.global_platform_registry is None:
            PlatformRegistry.global_platform_registry = PlatformRegistry()
        return PlatformRegistry.global_platform_registry

    def __init__(self) -> None:
        """Initialize platform registry"""
        self.platforms: Dict[str, Type[BasePlatform]] = {}
        # 插件平台来源追踪：平台名 -> 来源插件名（可逆效应，供卸载撤销）
        self._plugin_platform_sources: Dict[str, str] = {}
        # 从用户平台目录加载额外平台
        platform_dir = PlatformRegistry.get_platform_dir()
        if platform_dir and os.path.exists(platform_dir):
            for (
                platform_name,
                platform_class,
            ) in PlatformRegistry.load_platform_from_dir(platform_dir).items():
                self.register_platform(platform_name, platform_class)
        platform_dir = os.path.dirname(__file__)
        if platform_dir and os.path.exists(platform_dir):
            for (
                platform_name,
                platform_class,
            ) in PlatformRegistry.load_platform_from_dir(platform_dir).items():
                self.register_platform(platform_name, platform_class)
        # 从插件声明的平台目录加载插件平台（platforms 扩展点）
        self._load_plugin_platforms()
        # 注册为全局平台撤销器（可逆效应），供 PluginRegistry.revoke_plugin 调用
        from jarvis.jarvis_tools.plugin_registry import PluginRegistry

        PluginRegistry.instance().set_platform_revoker(self.unregister_platforms_by_plugin)

    def _load_plugin_platforms(self) -> None:
        """从插件声明的平台目录加载平台（platforms 扩展点）。

        插件 config.yaml 通过 ``platforms`` 字段声明自带的平台实现目录，目录内为
        ``BasePlatform`` 子类。加载成功后登记到 PluginRegistry（可逆效应），
        供卸载时精确撤销。
        """
        from jarvis.jarvis_utils.config import get_plugin_platform_dirs
        from jarvis.jarvis_tools.plugin_registry import PluginRegistry

        registry = PluginRegistry.instance()
        for directory in get_plugin_platform_dirs():
            if not directory or not os.path.exists(directory):
                continue
            # 从路径反推来源插件名（路径含 plugins/<name>/ 时）
            source_plugin = self._infer_source_plugin(directory)
            loaded = PlatformRegistry.load_platform_from_dir(directory)
            for platform_name, platform_class in loaded.items():
                # 命名冲突：插件平台覆盖内置/用户平台时告警，但允许注册
                if platform_name in self.platforms:
                    PrettyOutput.auto_print(
                        f"⚠️ 平台 '{platform_name}' 已存在，插件平台将覆盖它"
                    )
                self.register_platform(platform_name, platform_class)
                if source_plugin:
                    self._plugin_platform_sources[platform_name] = source_plugin
                    registry.register_platform(source_plugin, platform_name)

    @staticmethod
    def _infer_source_plugin(directory: str) -> Optional[str]:
        """从平台目录路径反推来源插件名（可逆效应来源追踪）。

        当目录路径形如 <...>/plugins/<plugin_name>/platforms 时返回插件名，
        否则返回 None（表示非插件来源的平台目录）。
        """
        try:
            normalized = directory.replace("\\", "/")
            marker = "/plugins/"
            if marker in normalized:
                return normalized.split(marker, 1)[1].split("/", 1)[0]
        except Exception:
            pass
        return None

    def unregister_platforms_by_plugin(self, plugin_name: str) -> int:
        """撤销指定插件注册的全部平台（可逆效应）。

        从 PluginRegistry 读取该插件登记的平台名并逐个撤销，同时清理
        PluginRegistry 中该插件的平台登记。

        参数:
            plugin_name: 插件名

        返回:
            int: 被撤销的平台数量
        """
        from jarvis.jarvis_tools.plugin_registry import PluginRegistry

        registry = PluginRegistry.instance()
        platform_names = registry.get_plugin_platforms(plugin_name)
        count = 0
        for name in platform_names:
            if name in self.platforms:
                del self.platforms[name]
                self._plugin_platform_sources.pop(name, None)
                count += 1
        # 仅清理 PluginRegistry 中该插件的平台登记（不影响工具/规则登记）
        registry.clear_platforms(plugin_name)
        return count

    def reload_plugin_platforms(self) -> None:
        """插件变更后免重启重载插件平台（platforms 扩展点）。

        先撤销当前已注册的全部插件平台，再按最新配置重新加载，使插件安装/
        卸载/升级后的平台声明立即生效。失败仅告警，不阻断调用方。
        """
        from jarvis.jarvis_tools.plugin_registry import PluginRegistry

        registry = PluginRegistry.instance()
        # 撤销当前已注册的全部插件平台（按来源插件名逐个撤销）
        for plugin_name in list(registry.registered_plugins()):
            if registry.get_plugin_platforms(plugin_name):
                try:
                    self.unregister_platforms_by_plugin(plugin_name)
                except Exception as e:
                    PrettyOutput.auto_print(
                        f"⚠️ 撤销插件 '{plugin_name}' 平台失败: {e}"
                    )
        # 重新加载插件平台
        try:
            self._load_plugin_platforms()
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 重载插件平台失败: {e}")

    def get_normal_platform(self) -> BasePlatform:
        """获取正常操作的平台实例"""
        platform_name = get_normal_platform_name()

        # 使用 silent=True 避免重复的错误信息，因为失败时会抛出异常
        platform = self.create_platform(
            platform_type="normal",
            silent=True,
        )
        if platform is None:
            raise RuntimeError(
                f"无法创建平台实例: 平台 '{platform_name}' 创建失败，请检查配置（如 API key 等）。"
            )
        return platform

    def get_cheap_platform(self) -> BasePlatform:
        """获取廉价操作的平台实例"""
        platform_name = get_cheap_platform_name()

        # 使用 silent=True 避免重复的错误信息，因为失败时会抛出异常
        platform = self.create_platform(
            platform_type="cheap",
            silent=True,
        )
        if platform is None:
            raise RuntimeError(
                f"无法创建平台实例: 平台 '{platform_name}' 创建失败，请检查配置（如 API key 等）"
            )
        return platform

    def get_smart_platform(self) -> BasePlatform:
        """获取智能操作的平台实例"""
        platform_name = get_smart_platform_name()

        # 使用 silent=True 避免重复的错误信息，因为失败时会抛出异常
        platform = self.create_platform(
            platform_type="smart",
            silent=True,
        )
        if platform is None:
            raise RuntimeError(
                f"无法创建平台实例: 平台 '{platform_name}' 创建失败，请检查配置（如 API key 等）"
            )
        return platform

    def get_eval_platform(self) -> Optional[BasePlatform]:
        """获取结构化评估模型平台实例。

        未配置 eval_llm 时返回 None（调用方据此回退现有流程），不抛异常。
        """
        if not is_eval_model_configured():
            return None
        return self.create_platform(
            platform_type="eval",
            silent=True,
        )

    def register_platform(self, name: str, platform_class: Type[BasePlatform]) -> None:
        """Register platform class

        Args:
            name: Platform name
            model_class: Platform class
        """
        self.platforms[name] = platform_class

    def create_platform(
        self,
        platform_type: str = "normal",
        silent: bool = False,
    ) -> Optional[BasePlatform]:
        """Create platform instance

        Args:
            name: Platform name
            platform_type: 平台类型，可选值为 'normal'、'cheap'、'smart' 或 'eval'
            silent: 如果为 True，失败时不打印错误信息（默认 False，保持向后兼容）

        Returns:
            BasePlatform: Platform instance
        """
        if platform_type == "smart":
            name = get_smart_platform_name()
        elif platform_type == "cheap":
            name = get_cheap_platform_name()
        elif platform_type == "eval":
            name = get_eval_platform_name()
        else:
            name = get_normal_platform_name()

        try:
            platform = self.platforms[name](platform_type=platform_type)
            return platform
        except Exception as e:
            if not silent:
                PrettyOutput.auto_print(f"❌ 创建平台失败: {str(e)}")
            return None

    def get_available_platforms(self) -> List[str]:
        """Get available platform list"""
        return list(self.platforms.keys())
