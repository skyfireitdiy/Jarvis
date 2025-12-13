"""
重排模型注册表，支持动态加载自定义重排模型实现。
"""

import importlib
import inspect

from jarvis.jarvis_utils.output import PrettyOutput

# -*- coding: utf-8 -*-
import os
import sys
from typing import Dict
from typing import List
from typing import Optional
from typing import Type

from jarvis.jarvis_utils.config import get_data_dir

from ..reranker_interface import RerankerInterface


class RerankerRegistry:
    """重排模型注册表，支持动态加载自定义重排模型实现"""

    global_registry: Optional["RerankerRegistry"] = None

    @staticmethod
    def get_reranker_dir() -> str:
        """获取用户自定义重排模型目录"""
        reranker_dir = os.path.join(get_data_dir(), "rerankers")
        if not os.path.exists(reranker_dir):
            try:
                os.makedirs(reranker_dir)
                # 创建 __init__.py 使其成为 Python 包
                with open(
                    os.path.join(reranker_dir, "__init__.py"), "w", errors="ignore"
                ):
                    pass
            except Exception as e:
                PrettyOutput.auto_print(f"❌ 创建重排模型目录失败: {str(e)}")
                return ""
        return reranker_dir

    @staticmethod
    def check_reranker_implementation(
        reranker_class: Type[RerankerInterface],
    ) -> bool:
        """检查重排模型类是否实现了所有必需的方法

        参数:
            reranker_class: 要检查的重排模型类

        返回:
            bool: 是否实现了所有必需的方法
        """
        required_methods = [
            ("rerank", ["query", "documents", "top_n"]),
        ]

        missing_methods = []

        for method_name, params in required_methods:
            if not hasattr(reranker_class, method_name):
                missing_methods.append(method_name)
                continue

            method = getattr(reranker_class, method_name)
            if not callable(method):
                missing_methods.append(method_name)
                continue

            # 检查方法参数（允许有默认值）
            sig = inspect.signature(method)
            method_params = [p for p in sig.parameters if p != "self"]
            # 检查必需参数数量（不考虑有默认值的参数）
            required_params = [
                p
                for p in method_params
                if sig.parameters[p].default == inspect.Parameter.empty
            ]
            # rerank 方法需要至少 2 个必需参数（query 和 documents），top_n 可以有默认值
            if method_name == "rerank":
                if len(required_params) < 2:
                    missing_methods.append(f"{method_name}(parameter mismatch)")
            elif len(required_params) < len(params):
                missing_methods.append(f"{method_name}(parameter mismatch)")

        if missing_methods:
            PrettyOutput.auto_print(
                f"⚠️ 重排模型 {reranker_class.__name__} 缺少必要的方法: {', '.join(missing_methods)}"
            )
            return False

        return True

    @staticmethod
    def load_rerankers_from_dir(
        directory: str,
    ) -> Dict[str, Type[RerankerInterface]]:
        """从指定目录加载重排模型

        参数:
            directory: 重排模型目录路径

        返回:
            Dict[str, Type[RerankerInterface]]: 重排模型名称到类的映射
        """
        rerankers: Dict[str, Type[RerankerInterface]] = {}

        # 确保目录存在
        if not os.path.exists(directory):
            PrettyOutput.auto_print(f"⚠️ 重排模型目录不存在: {directory}")
            return rerankers

        # 获取目录的包名
        package_name = None
        if directory == os.path.dirname(__file__):
            package_name = "jarvis.jarvis_rag.rerankers"

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
                        # 检查是否是RerankerInterface的子类，但不是RerankerInterface本身
                        if (
                            inspect.isclass(obj)
                            and issubclass(obj, RerankerInterface)
                            and obj != RerankerInterface
                        ):
                            # 检查重排模型实现
                            if not RerankerRegistry.check_reranker_implementation(obj):
                                continue
                            try:
                                # 使用类名作为注册名（可以后续扩展为使用类方法获取名称）
                                reranker_name = obj.__name__
                                rerankers[reranker_name] = obj
                            except Exception as e:
                                error_lines.append(
                                    f"注册重排模型失败 {obj.__name__}: {str(e)}"
                                )
                except Exception as e:
                    error_lines.append(f"加载重排模型 {module_name} 失败: {str(e)}")

        if error_lines:
            joined_errors = "\n".join(error_lines)
            PrettyOutput.auto_print(f"❌ {joined_errors}")
        return rerankers

    @staticmethod
    def get_global_registry() -> "RerankerRegistry":
        """获取全局重排模型注册表"""
        if RerankerRegistry.global_registry is None:
            RerankerRegistry.global_registry = RerankerRegistry()
        return RerankerRegistry.global_registry

    def __init__(self) -> None:
        """初始化重排模型注册表"""
        self.rerankers: Dict[str, Type[RerankerInterface]] = {}

        # 从用户自定义目录加载额外重排模型
        reranker_dir = RerankerRegistry.get_reranker_dir()
        if reranker_dir and os.path.exists(reranker_dir):
            for (
                reranker_name,
                reranker_class,
            ) in RerankerRegistry.load_rerankers_from_dir(reranker_dir).items():
                self.register_reranker(reranker_name, reranker_class)

        # 从内置目录加载重排模型
        reranker_dir = os.path.dirname(__file__)
        if reranker_dir and os.path.exists(reranker_dir):
            for (
                reranker_name,
                reranker_class,
            ) in RerankerRegistry.load_rerankers_from_dir(reranker_dir).items():
                self.register_reranker(reranker_name, reranker_class)

    def register_reranker(
        self, name: str, reranker_class: Type[RerankerInterface]
    ) -> None:
        """注册重排模型类

        参数:
            name: 重排模型名称
            reranker_class: 重排模型类
        """
        self.rerankers[name] = reranker_class

    def create_reranker(
        self, name: str, *args, **kwargs
    ) -> Optional[RerankerInterface]:
        """创建重排模型实例

        参数:
            name: 重排模型名称
            *args: 传递给构造函数的参数
            **kwargs: 传递给构造函数的关键字参数

        返回:
            RerankerInterface: 重排模型实例
        """
        if name not in self.rerankers:
            PrettyOutput.auto_print(f"⚠️ 未找到重排模型: {name}")
            return None

        try:
            reranker = self.rerankers[name](*args, **kwargs)
            return reranker
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 创建重排模型失败: {str(e)}")
            return None

    def get_available_rerankers(self) -> List[str]:
        """获取可用的重排模型列表"""
        return list(self.rerankers.keys())

    @staticmethod
    def create_from_config() -> Optional[RerankerInterface]:
        """从配置创建重排模型实例

        从配置系统读取reranker_type、rerank_model和reranker_config，
        然后创建相应的重排模型实例。

        返回:
            Optional[RerankerInterface]: 重排模型实例，如果创建失败则返回None
        """
        from jarvis.jarvis_utils.config import get_rag_rerank_model
        from jarvis.jarvis_utils.config import get_rag_reranker_config
        from jarvis.jarvis_utils.config import get_rag_reranker_type

        reranker_type = get_rag_reranker_type()
        model_name = get_rag_rerank_model()
        reranker_config = get_rag_reranker_config()

        registry = RerankerRegistry.get_global_registry()

        from jarvis.jarvis_utils.config import get_rag_reranker_max_length

        # 构建创建参数
        create_kwargs = {"model_name": model_name}
        create_kwargs.update(reranker_config)

        # 将配置中的键名映射到 api_key 参数
        # 支持的键名：cohere_api_key, edgefn_api_key, jina_api_key
        api_key_mapping = {
            "cohere_api_key": "api_key",
            "edgefn_api_key": "api_key",
            "jina_api_key": "api_key",
        }
        for config_key, param_key in api_key_mapping.items():
            if config_key in create_kwargs:
                # 如果还没有设置 api_key，则使用配置中的值
                if param_key not in create_kwargs:
                    create_kwargs[param_key] = create_kwargs.pop(config_key)
                else:
                    # 如果已经设置了 api_key，移除配置中的键
                    create_kwargs.pop(config_key)

        # 同样处理 base_url
        base_url_mapping = {
            "cohere_api_base": "base_url",
            "edgefn_api_base": "base_url",
            "jina_api_base": "base_url",
        }
        for config_key, param_key in base_url_mapping.items():
            if config_key in create_kwargs:
                if param_key not in create_kwargs:
                    create_kwargs[param_key] = create_kwargs.pop(config_key)
                else:
                    create_kwargs.pop(config_key)

        # 添加max_length（如果配置中没有指定，使用配置系统的默认值）
        if "max_length" not in create_kwargs:
            create_kwargs["max_length"] = str(get_rag_reranker_max_length())

        return registry.create_reranker(reranker_type, **create_kwargs)
