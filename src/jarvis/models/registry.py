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
    ('set_system_message', ['message']),
    ('set_model_name', ['model_name']),
    ('get_model_list', []),
    ('set_suppress_output', ['suppress']),
    ('upload_files', ['file_list'])
]

class PlatformRegistry:
    """Platform registry"""

    global_platform_name = "kimi"
    global_platform_registry = None
    suppress_output = False

    @staticmethod
    def get_platform_dir() -> str:
        user_platform_dir = os.path.expanduser("~/.jarvis_models")
        if not os.path.exists(user_platform_dir):
            try:
                os.makedirs(user_platform_dir)
                # 创建 __init__.py 使其成为 Python 包
                with open(os.path.join(user_platform_dir, "__init__.py"), "w") as f:
                    pass

                pass
            except Exception as e:
                PrettyOutput.print(f"Create platform directory failed: {str(e)}", OutputType.ERROR)
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
            method_params = [p for p in sig.parameters if p != 'self']
            if len(method_params) != len(params):
                missing_methods.append(f"{method_name}(parameter mismatch)")
        
        if missing_methods:
            PrettyOutput.print(
                f"Platform {platform_class.__name__} is missing necessary methods: {', '.join(missing_methods)}", 
                OutputType.ERROR
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
        platforms = {}
        
        # 确保目录存在
        if not os.path.exists(directory):
            PrettyOutput.print(f"Platform directory does not exist: {directory}", OutputType.ERROR)
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
                        # 检查是否是BasePlatform的子类，但不是BasePlatform本身
                        if (inspect.isclass(obj) and 
                            issubclass(obj, BasePlatform) and 
                            obj != BasePlatform and
                            hasattr(obj, 'platform_name')):
                            # 检查平台实现
                            if not PlatformRegistry.check_platform_implementation(obj):
                                continue
                            if not PlatformRegistry.suppress_output:
                                PrettyOutput.print(f"Load platform from {os.path.join(directory, filename)}: {obj.platform_name}", OutputType.SUCCESS) # type: ignore
                            platforms[obj.platform_name] = obj # type: ignore
                            break
                except Exception as e:
                    PrettyOutput.print(f"Load platform {module_name} failed: {str(e)}", OutputType.ERROR)
        
        return platforms


    @staticmethod
    def get_global_platform_registry():
        """Get global platform registry"""
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
        """Initialize platform registry"""
        self.platforms: Dict[str, Type[BasePlatform]] = {}

    def get_normal_platform(self) -> BasePlatform:
        platform_name = os.environ.get("JARVIS_PLATFORM", "kimi")
        model_name = os.environ.get("JARVIS_MODEL", "kimi")
        platform = self.create_platform(platform_name)
        platform.set_model_name(model_name) # type: ignore
        return platform # type: ignore
    
    def get_codegen_platform(self) -> BasePlatform:
        platform_name = os.environ.get("JARVIS_CODEGEN_PLATFORM", os.environ.get("JARVIS_PLATFORM", "kimi"))
        model_name = os.environ.get("JARVIS_CODEGEN_MODEL", os.environ.get("JARVIS_MODEL", "kimi"))
        platform = self.create_platform(platform_name)
        platform.set_model_name(model_name) # type: ignore
        return platform # type: ignore
    
    def get_cheap_platform(self) -> BasePlatform:
        platform_name = os.environ.get("JARVIS_CHEAP_PLATFORM", os.environ.get("JARVIS_PLATFORM", "kimi"))
        model_name = os.environ.get("JARVIS_CHEAP_MODEL", os.environ.get("JARVIS_MODEL", "kimi"))
        platform = self.create_platform(platform_name)
        platform.set_model_name(model_name) # type: ignore
        return platform # type: ignore
    
    def get_thinking_platform(self) -> BasePlatform:
        platform_name = os.environ.get("JARVIS_THINKING_PLATFORM", os.environ.get("JARVIS_PLATFORM", "kimi"))
        model_name = os.environ.get("JARVIS_THINKING_MODEL", os.environ.get("JARVIS_MODEL", "kimi"))
        platform = self.create_platform(platform_name)
        platform.set_model_name(model_name) # type: ignore
        return platform # type: ignore

    def register_platform(self, name: str, platform_class: Type[BasePlatform]):
        """Register platform class
        
        Args:
            name: Platform name
            model_class: Platform class
        """
        self.platforms[name] = platform_class
            
    def create_platform(self, name: str) -> Optional[BasePlatform]:
        """Create platform instance
        
        Args:
            name: Platform name
            
        Returns:
            BasePlatform: Platform instance
        """
        if name not in self.platforms:
            PrettyOutput.print(f"Platform not found: {name}", OutputType.ERROR)
            return None
            
        try:

            platform = self.platforms[name]()
            return platform
        except Exception as e:
            PrettyOutput.print(f"Create platform failed: {str(e)}", OutputType.ERROR)
            return None
            
    def get_available_platforms(self) -> List[str]:
        """Get available platform list"""
        return list(self.platforms.keys()) 
    
