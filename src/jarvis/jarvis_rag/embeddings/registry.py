"""
嵌入模型注册表，支持动态加载自定义嵌入模型实现。
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

from ..embedding_interface import EmbeddingInterface


class EmbeddingRegistry:
    """嵌入模型注册表，支持动态加载自定义嵌入模型实现"""

    global_registry: Optional["EmbeddingRegistry"] = None

    @staticmethod
    def get_embedding_dir() -> str:
        """获取用户自定义嵌入模型目录"""
        embedding_dir = os.path.join(get_data_dir(), "embeddings")
        if not os.path.exists(embedding_dir):
            try:
                os.makedirs(embedding_dir)
                # 创建 __init__.py 使其成为 Python 包
                with open(
                    os.path.join(embedding_dir, "__init__.py"), "w", errors="ignore"
                ):
                    pass
            except Exception as e:
                PrettyOutput.auto_print(f"❌ 创建嵌入模型目录失败: {str(e)}")
                return ""
        return embedding_dir

    @staticmethod
    def check_embedding_implementation(
        embedding_class: Type[EmbeddingInterface],
    ) -> bool:
        """检查嵌入模型类是否实现了所有必需的方法

        参数:
            embedding_class: 要检查的嵌入模型类

        返回:
            bool: 是否实现了所有必需的方法
        """
        required_methods = [
            ("embed_documents", ["texts"]),
            ("embed_query", ["text"]),
        ]

        missing_methods = []

        for method_name, params in required_methods:
            if not hasattr(embedding_class, method_name):
                missing_methods.append(method_name)
                continue

            method = getattr(embedding_class, method_name)
            if not callable(method):
                missing_methods.append(method_name)
                continue

            # 检查方法参数
            sig = inspect.signature(method)
            method_params = [p for p in sig.parameters if p != "self"]
            if len(method_params) != len(params):
                missing_methods.append(f"{method_name}(parameter mismatch)")

        if missing_methods:
            PrettyOutput.auto_print(
                f"⚠️ 嵌入模型 {embedding_class.__name__} 缺少必要的方法: {', '.join(missing_methods)}"
            )
            return False

        return True

    @staticmethod
    def load_embeddings_from_dir(
        directory: str,
    ) -> Dict[str, Type[EmbeddingInterface]]:
        """从指定目录加载嵌入模型

        参数:
            directory: 嵌入模型目录路径

        返回:
            Dict[str, Type[EmbeddingInterface]]: 嵌入模型名称到类的映射
        """
        embeddings: Dict[str, Type[EmbeddingInterface]] = {}

        # 确保目录存在
        if not os.path.exists(directory):
            PrettyOutput.auto_print(f"⚠️ 嵌入模型目录不存在: {directory}")
            return embeddings

        # 获取目录的包名
        package_name = None
        if directory == os.path.dirname(__file__):
            package_name = "jarvis.jarvis_rag.embeddings"

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
                        # 检查是否是EmbeddingInterface的子类，但不是EmbeddingInterface本身
                        if (
                            inspect.isclass(obj)
                            and issubclass(obj, EmbeddingInterface)
                            and obj != EmbeddingInterface
                        ):
                            # 检查嵌入模型实现
                            if not EmbeddingRegistry.check_embedding_implementation(
                                obj
                            ):
                                continue
                            try:
                                # 使用类名作为注册名（可以后续扩展为使用类方法获取名称）
                                embedding_name = obj.__name__
                                embeddings[embedding_name] = obj
                            except Exception as e:
                                error_lines.append(
                                    f"注册嵌入模型失败 {obj.__name__}: {str(e)}"
                                )
                except Exception as e:
                    error_lines.append(f"加载嵌入模型 {module_name} 失败: {str(e)}")

        if error_lines:
            joined_errors = "\n".join(error_lines)
            PrettyOutput.auto_print(f"❌ {joined_errors}")
        return embeddings

    @staticmethod
    def get_global_registry() -> "EmbeddingRegistry":
        """获取全局嵌入模型注册表"""
        if EmbeddingRegistry.global_registry is None:
            EmbeddingRegistry.global_registry = EmbeddingRegistry()
        return EmbeddingRegistry.global_registry

    def __init__(self) -> None:
        """初始化嵌入模型注册表"""
        self.embeddings: Dict[str, Type[EmbeddingInterface]] = {}

        # 从用户自定义目录加载额外嵌入模型
        embedding_dir = EmbeddingRegistry.get_embedding_dir()
        if embedding_dir and os.path.exists(embedding_dir):
            for (
                embedding_name,
                embedding_class,
            ) in EmbeddingRegistry.load_embeddings_from_dir(embedding_dir).items():
                self.register_embedding(embedding_name, embedding_class)

        # 从内置目录加载嵌入模型
        embedding_dir = os.path.dirname(__file__)
        if embedding_dir and os.path.exists(embedding_dir):
            for (
                embedding_name,
                embedding_class,
            ) in EmbeddingRegistry.load_embeddings_from_dir(embedding_dir).items():
                self.register_embedding(embedding_name, embedding_class)

    def register_embedding(
        self, name: str, embedding_class: Type[EmbeddingInterface]
    ) -> None:
        """注册嵌入模型类

        参数:
            name: 嵌入模型名称
            embedding_class: 嵌入模型类
        """
        self.embeddings[name] = embedding_class

    def create_embedding(
        self, name: str, *args, **kwargs
    ) -> Optional[EmbeddingInterface]:
        """创建嵌入模型实例

        参数:
            name: 嵌入模型名称
            *args: 传递给构造函数的参数
            **kwargs: 传递给构造函数的关键字参数

        返回:
            EmbeddingInterface: 嵌入模型实例
        """
        if name not in self.embeddings:
            PrettyOutput.auto_print(f"⚠️ 未找到嵌入模型: {name}")
            return None

        try:
            embedding = self.embeddings[name](*args, **kwargs)
            return embedding
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 创建嵌入模型失败: {str(e)}")
            return None

    def get_available_embeddings(self) -> List[str]:
        """获取可用的嵌入模型列表"""
        return list(self.embeddings.keys())

    @staticmethod
    def create_from_config() -> Optional[EmbeddingInterface]:
        """从配置创建嵌入模型实例

        从配置系统读取embedding_type、embedding_model和embedding_config，
        然后创建相应的嵌入模型实例。

        返回:
            Optional[EmbeddingInterface]: 嵌入模型实例，如果创建失败则返回None
        """
        from jarvis.jarvis_utils.config import get_rag_embedding_cache_path
        from jarvis.jarvis_utils.config import get_rag_embedding_config
        from jarvis.jarvis_utils.config import get_rag_embedding_model
        from jarvis.jarvis_utils.config import get_rag_embedding_type

        embedding_type = get_rag_embedding_type()
        model_name = get_rag_embedding_model()
        embedding_config = get_rag_embedding_config()

        registry = EmbeddingRegistry.get_global_registry()

        from jarvis.jarvis_utils.config import get_rag_embedding_max_length

        # 构建创建参数
        create_kwargs = {"model_name": model_name}
        create_kwargs.update(embedding_config)

        # 将配置中的键名映射到 api_key 参数
        # 支持的键名：openai_api_key, cohere_api_key, edgefn_api_key, jina_api_key
        api_key_mapping = {
            "openai_api_key": "api_key",
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
            "openai_api_base": "base_url",
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
            create_kwargs["max_length"] = str(get_rag_embedding_max_length())

        # 如果是LocalEmbeddingModel，需要添加cache_dir
        if embedding_type == "LocalEmbeddingModel":
            create_kwargs["cache_dir"] = get_rag_embedding_cache_path()

        return registry.create_embedding(embedding_type, **create_kwargs)
