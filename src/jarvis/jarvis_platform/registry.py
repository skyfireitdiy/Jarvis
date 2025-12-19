# -*- coding: utf-8 -*-
import importlib
import inspect
import os
import sys
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Type

from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_utils.config import get_cheap_model_name
from jarvis.jarvis_utils.config import get_cheap_platform_name
from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.config import get_llm_config
from jarvis.jarvis_utils.config import get_normal_model_name
from jarvis.jarvis_utils.config import get_normal_platform_name
from jarvis.jarvis_utils.config import get_smart_model_name
from jarvis.jarvis_utils.config import get_smart_platform_name
from jarvis.jarvis_utils.output import PrettyOutput

REQUIRED_METHODS = [
    ("chat", ["message"]),  # 方法名和参数列表
    ("name", []),
    ("delete_chat", []),
    ("set_system_prompt", ["message"]),
    ("set_model_name", ["model_name"]),
    ("get_model_list", []),
    ("upload_files", ["file_list"]),
]


class PlatformRegistry:
    """Platform registry"""

    global_platform_name: str = "yuanbao"
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

    def get_normal_platform(
        self, model_group_override: Optional[str] = None
    ) -> BasePlatform:
        """获取正常操作的平台实例"""
        platform_name = get_normal_platform_name(model_group_override)
        model_name = get_normal_model_name(model_group_override)
        llm_config = get_llm_config("normal", model_group_override)

        # 调试：检查配置中是否包含 API key
        if not llm_config.get("openai_api_key") and platform_name in (
            "openai",
            "deepseek",
            "anthropic",
        ):
            import os

            env_key = (
                os.getenv("OPENAI_API_KEY")
                or os.getenv("DEEPSEEK_API_KEY")
                or os.getenv("ANTHROPIC_API_KEY")
            )
            if not env_key:
                from jarvis.jarvis_utils.output import PrettyOutput

                PrettyOutput.auto_print(
                    f"⚠️ 警告: 创建平台 '{platform_name}' 时，配置中未找到 API key，"
                    f"环境变量中也未设置。model_group={model_group_override}, "
                    f"llm_config keys={list(llm_config.keys())}"
                )

        # 使用 silent=True 避免重复的错误信息，因为失败时会抛出异常
        platform = self.create_platform(platform_name, llm_config, silent=True)
        if platform is None:
            raise RuntimeError(
                f"无法创建平台实例: 平台 '{platform_name}' 创建失败，请检查配置（如 API key 等）。"
                f"model_group={model_group_override}, llm_config keys={list(llm_config.keys())}"
            )
        platform.set_model_name(model_name)  # type: ignore
        return platform  # type: ignore

    def get_cheap_platform(
        self, model_group_override: Optional[str] = None
    ) -> BasePlatform:
        """获取廉价操作的平台实例"""
        platform_name = get_cheap_platform_name(model_group_override)
        model_name = get_cheap_model_name(model_group_override)
        llm_config = get_llm_config("cheap", model_group_override)
        # 使用 silent=True 避免重复的错误信息，因为失败时会抛出异常
        platform = self.create_platform(platform_name, llm_config, silent=True)
        if platform is None:
            raise RuntimeError(
                f"无法创建平台实例: 平台 '{platform_name}' 创建失败，请检查配置（如 API key 等）"
            )
        platform.set_model_name(model_name)  # type: ignore
        platform.set_platform_type("cheap")  # type: ignore
        return platform  # type: ignore

    def get_smart_platform(
        self, model_group_override: Optional[str] = None
    ) -> BasePlatform:
        """获取智能操作的平台实例"""
        platform_name = get_smart_platform_name(model_group_override)
        model_name = get_smart_model_name(model_group_override)
        llm_config = get_llm_config("smart", model_group_override)
        # 使用 silent=True 避免重复的错误信息，因为失败时会抛出异常
        platform = self.create_platform(platform_name, llm_config, silent=True)
        if platform is None:
            raise RuntimeError(
                f"无法创建平台实例: 平台 '{platform_name}' 创建失败，请检查配置（如 API key 等）"
            )
        platform.set_model_name(model_name)  # type: ignore
        platform.set_platform_type("smart")  # type: ignore
        return platform  # type: ignore

    def register_platform(self, name: str, platform_class: Type[BasePlatform]) -> None:
        """Register platform class

        Args:
            name: Platform name
            model_class: Platform class
        """
        self.platforms[name] = platform_class

    def create_platform(
        self,
        name: str,
        llm_config: Optional[Dict[str, Any]] = None,
        silent: bool = False,
    ) -> Optional[BasePlatform]:
        """Create platform instance

        Args:
            name: Platform name
            llm_config: LLM配置字典，包含平台特定的配置参数（如 api_key, base_url 等）
            silent: 如果为 True，失败时不打印错误信息（默认 False，保持向后兼容）

        Returns:
            BasePlatform: Platform instance
        """
        if name not in self.platforms:
            if not silent:
                PrettyOutput.auto_print(f"⚠️ 未找到平台: {name}")
            return None

        try:
            platform = self.platforms[name](llm_config=llm_config or {})
            return platform
        except Exception as e:
            if not silent:
                PrettyOutput.auto_print(f"❌ 创建平台失败: {str(e)}")
            return None

    def get_available_platforms(self) -> List[str]:
        """Get available platform list"""
        return list(self.platforms.keys())
