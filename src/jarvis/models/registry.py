import importlib
import inspect
import os
import sys
from typing import Dict, Type, Optional, List
from .base import BasePlatform
from ..utils import PrettyOutput, OutputType

REQUIRED_METHODS = [
    ('chat', ['message']),           # 方法名和参数列表
    ('name', []),
    ('delete_chat', []),
    ('reset', []),
    ('set_system_message', ['message'])
]

class PlatformRegistry:
    """平台注册器"""

    global_platform_name = "kimi"
    global_platform_registry = None

    @staticmethod
    def get_platform_dir() -> str:
        user_platform_dir = os.path.expanduser("~/.jarvis_models")
        if not os.path.exists(user_platform_dir):
            try:
                os.makedirs(user_platform_dir)
                # 创建 __init__.py 使其成为 Python 包
                with open(os.path.join(user_platform_dir, "__init__.py"), "w") as f:
                    pass
                PrettyOutput.print(f"已创建平台目录: {user_platform_dir}", OutputType.INFO)
            except Exception as e:
                PrettyOutput.print(f"创建平台目录失败: {str(e)}", OutputType.ERROR)
                return ""
        return user_platform_dir

    @staticmethod
    def check_platform_implementation(platform_class: Type[BasePlatform]) -> bool:
        """检查平台类是否实现了所有必要的方法
        
        Args:
            platform_class: 要检查的平台类
            
        Returns:
            bool: 是否实现了所有必要的方法
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
            method_params = [p for p in sig.parameters if p != 'self']
            if len(method_params) != len(params):
                missing_methods.append(f"{method_name}(参数不匹配)")
        
        if missing_methods:
            PrettyOutput.print(
                f"平台 {platform_class.__name__} 缺少必要的方法: {', '.join(missing_methods)}", 
                OutputType.ERROR
            )
            return False
            
        return True

    @staticmethod
    def load_platform_from_dir(directory: str) -> Dict[str, Type[BasePlatform]]:
        """从指定目录加载平台
        
        Args:
            directory: 平台目录路径
            
        Returns:
            Dict[str, Type[BaseModel]]: 平台名称到平台类的映射
        """
        platforms = {}
        
        # 确保目录存在
        if not os.path.exists(directory):
            PrettyOutput.print(f"平台目录不存在: {directory}", OutputType.ERROR)
            return platforms
            
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
                            issubclass(obj, BasePlatform) and 
                            obj != BasePlatform and
                            hasattr(obj, 'platform_name')):
                            # 检查平台实现
                            if not PlatformRegistry.check_platform_implementation(obj):
                                continue
                            platforms[obj.platform_name] = obj
                            PrettyOutput.print(f"从 {directory} 加载平台: {obj.platform_name}", OutputType.INFO)
                            break
                except Exception as e:
                    PrettyOutput.print(f"加载平台 {module_name} 失败: {str(e)}", OutputType.ERROR)
        
        return platforms


    @staticmethod
    def get_global_platform_registry():
        """获取全局平台注册器"""
        if PlatformRegistry.global_platform_registry is None:
            PlatformRegistry.global_platform_registry = PlatformRegistry()
            
            # 从用户平台目录加载额外平台
            platform_dir = PlatformRegistry.get_platform_dir()
            if platform_dir and os.path.exists(platform_dir):
                for platform_name, platform_class in PlatformRegistry.load_platform_from_dir(platform_dir).items():
                    PlatformRegistry.global_platform_registry.register_platform(platform_name, platform_class)
            platform_dir = os.path.dirname(__file__)
            if platform_dir and os.path.exists(platform_dir):
                for platform_name, platform_class in PlatformRegistry.load_platform_from_dir(platform_dir).items():
                    PlatformRegistry.global_platform_registry.register_platform(platform_name, platform_class)
        return PlatformRegistry.global_platform_registry
    
    def __init__(self):
        """初始化平台注册器
        """
        self.platforms: Dict[str, Type[BasePlatform]] = {}

    @staticmethod
    def get_global_platform() -> BasePlatform:
        """获取全局平台实例"""
        platform = PlatformRegistry.get_global_platform_registry().create_platform(PlatformRegistry.global_platform_name)
        if not platform:
            raise Exception(f"Failed to create platform: {PlatformRegistry.global_platform_name}")
        return platform
        
    def register_platform(self, name: str, platform_class: Type[BasePlatform]):
        """注册平台类
        
        Args:
            name: 平台名称
            model_class: 平台类
        """
        self.platforms[name] = platform_class
        PrettyOutput.print(f"已注册平台: {name}", OutputType.INFO)
            
    def create_platform(self, name: str) -> Optional[BasePlatform]:
        """创建平台实例
        
        Args:
            name: 平台名称
            
        Returns:
            BaseModel: 平台实例
        """
        if name not in self.platforms:
            PrettyOutput.print(f"未找到平台: {name}", OutputType.ERROR)
            return None
            
        try:
            platform = self.platforms[name]()
            PrettyOutput.print(f"已创建平台实例: {name}", OutputType.INFO)
            return platform
        except Exception as e:
            PrettyOutput.print(f"创建平台失败: {str(e)}", OutputType.ERROR)
            return None
            
    def get_available_platforms(self) -> List[str]:
        """获取可用平台列表"""
        return list(self.platforms.keys()) 
    
    def set_global_platform_name(self, platform_name: str):
        """设置全局平台"""
        PlatformRegistry.global_platform_name = platform_name

    def get_global_platform_name(self) -> str:
        """获取全局平台名称"""
        return PlatformRegistry.global_platform_name
