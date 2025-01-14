import importlib
import inspect
import os
import sys
from typing import Dict, Type, Optional, List
from .base import BaseModel
from ..utils import PrettyOutput, OutputType

REQUIRED_METHODS = [
    ('chat', ['message']),           # 方法名和参数列表
    ('name', []),
    ('delete_chat', []),
    ('reset', []),
    ('set_system_message', ['message'])
]

class ModelRegistry:
    """模型注册器"""

    global_model_name = "kimi"
    global_model_registry = None

    @staticmethod
    def get_models_dir() -> str:
        user_models_dir = os.path.expanduser("~/.jarvis_models")
        if not os.path.exists(user_models_dir):
            try:
                os.makedirs(user_models_dir)
                # 创建 __init__.py 使其成为 Python 包
                with open(os.path.join(user_models_dir, "__init__.py"), "w") as f:
                    pass
                PrettyOutput.print(f"已创建模型目录: {user_models_dir}", OutputType.INFO)
            except Exception as e:
                PrettyOutput.print(f"创建模型目录失败: {str(e)}", OutputType.ERROR)
                return ""
        return user_models_dir

    @staticmethod
    def check_model_implementation(model_class: Type[BaseModel]) -> bool:
        """检查模型类是否实现了所有必要的方法
        
        Args:
            model_class: 要检查的模型类
            
        Returns:
            bool: 是否实现了所有必要的方法
        """
        missing_methods = []
        
        for method_name, params in REQUIRED_METHODS:
            if not hasattr(model_class, method_name):
                missing_methods.append(method_name)
                continue
                
            method = getattr(model_class, method_name)
            if not callable(method):
                missing_methods.append(method_name)
                continue
                
            # 检查方法参数
            import inspect
            sig = inspect.signature(method)
            method_params = [p for p in sig.parameters if p != 'self']
            if len(method_params) != len(params):
                missing_methods.append(f"{method_name}(参数不匹配)")
        
        if missing_methods:
            PrettyOutput.print(
                f"模型 {model_class.__name__} 缺少必要的方法: {', '.join(missing_methods)}", 
                OutputType.ERROR
            )
            return False
            
        return True

    @staticmethod
    def load_models_from_dir(directory: str) -> Dict[str, Type[BaseModel]]:
        """从指定目录加载模型
        
        Args:
            directory: 模型目录路径
            
        Returns:
            Dict[str, Type[BaseModel]]: 模型名称到模型类的映射
        """
        models = {}
        
        # 确保目录存在
        if not os.path.exists(directory):
            PrettyOutput.print(f"模型目录不存在: {directory}", OutputType.ERROR)
            return models
            
        # 获取目录的包名
        package_name = None
        if directory == os.path.dirname(__file__):
            package_name = "jarvis.models"
            
        # 添加目录到Python路径
        if directory not in sys.path:
            sys.path.append(directory)
        
        # 遍历目录下的所有.py文件
        for filename in os.listdir(directory):
            if filename.endswith('.py') and not filename.startswith('__'):
                module_name = filename[:-3]  # 移除.py后缀
                try:
                    # 导入模块
                    if package_name:
                        module = importlib.import_module(f"{package_name}.{module_name}")
                    else:
                        module = importlib.import_module(module_name)
                    
                    # 遍历模块中的所有类
                    for name, obj in inspect.getmembers(module):
                        # 检查是否是BaseModel的子类，但不是BaseModel本身
                        if (inspect.isclass(obj) and 
                            issubclass(obj, BaseModel) and 
                            obj != BaseModel and
                            hasattr(obj, 'model_name')):
                            # 检查模型实现
                            if not ModelRegistry.check_model_implementation(obj):
                                continue
                            models[obj.model_name] = obj
                            PrettyOutput.print(f"从 {directory} 加载模型: {obj.model_name}", OutputType.INFO)
                            break
                except Exception as e:
                    PrettyOutput.print(f"加载模型 {module_name} 失败: {str(e)}", OutputType.ERROR)
        
        return models


    @staticmethod
    def get_model_registry():
        """获取全局模型注册器"""
        if ModelRegistry.global_model_registry is None:
            ModelRegistry.global_model_registry = ModelRegistry()
            
            # 从用户模型目录加载额外模型
            models_dir = ModelRegistry.get_models_dir()
            if models_dir and os.path.exists(models_dir):
                for model_name, model_class in ModelRegistry.load_models_from_dir(models_dir).items():
                    ModelRegistry.global_model_registry.register_model(model_name, model_class)
            models_dir = os.path.dirname(__file__)
            if models_dir and os.path.exists(models_dir):
                for model_name, model_class in ModelRegistry.load_models_from_dir(models_dir).items():
                    ModelRegistry.global_model_registry.register_model(model_name, model_class)
        return ModelRegistry.global_model_registry
    
    def __init__(self):
        """初始化模型注册器
        """
        self.models: Dict[str, Type[BaseModel]] = {}

    @staticmethod
    def get_global_model() -> BaseModel:
        """获取全局模型实例"""
        model = ModelRegistry.get_model_registry().create_model(ModelRegistry.global_model_name)
        if not model:
            raise Exception(f"Failed to create model: {ModelRegistry.global_model_name}")
        return model
        
    def register_model(self, name: str, model_class: Type[BaseModel]):
        """注册模型类
        
        Args:
            name: 模型名称
            model_class: 模型类
        """
        self.models[name] = model_class
        PrettyOutput.print(f"已注册模型: {name}", OutputType.INFO)
            
    def create_model(self, name: str) -> Optional[BaseModel]:
        """创建模型实例
        
        Args:
            name: 模型名称
            
        Returns:
            BaseModel: 模型实例
        """
        if name not in self.models:
            PrettyOutput.print(f"未找到模型: {name}", OutputType.ERROR)
            return None
            
        try:
            model = self.models[name]()
            PrettyOutput.print(f"已创建模型实例: {name}", OutputType.INFO)
            return model
        except Exception as e:
            PrettyOutput.print(f"创建模型失败: {str(e)}", OutputType.ERROR)
            return None
            
    def get_available_models(self) -> List[str]:
        """获取可用模型列表"""
        return list(self.models.keys()) 
    
    def set_global_model(self, model_name: str):
        """设置全局模型"""
        ModelRegistry.global_model_name = model_name
