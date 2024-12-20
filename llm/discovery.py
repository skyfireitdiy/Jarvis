import os
import importlib
import inspect
from typing import Dict, Type, Callable
from .base import BaseLLM

class LLMDiscovery:
    """LLM discovery and auto-registration"""
    
    @staticmethod
    def discover_llms(llm_dir: str = None) -> Dict[str, Callable[..., BaseLLM]]:
        """
        Discover all LLM factory functions in the llm directory
        
        Args:
            llm_dir: Directory to scan for LLMs. If None, uses current directory
        
        Returns:
            Dict of LLM name to factory function
        """
        if llm_dir is None:
            llm_dir = os.path.dirname(os.path.abspath(__file__))
        
        print(f"Scanning directory for LLMs: {llm_dir}")
        llm_factories = {}
        
        # Get all .py files in the llm directory
        for filename in os.listdir(llm_dir):
            if filename.endswith('.py') and not filename.startswith('_'):
                print(f"Found LLM file: {filename}")
                # Get module name without .py
                module_name = filename[:-3]
                
                # Skip base and discovery modules
                if module_name in ['base', 'discovery']:
                    continue
                
                try:
                    # Import the module
                    module = importlib.import_module(f".{module_name}", package="llm")
                    
                    # Find factory function that returns BaseLLM
                    for name, obj in inspect.getmembers(module):
                        if (inspect.isfunction(obj) and 
                            name == 'create_llm' and
                            inspect.signature(obj).return_annotation == BaseLLM):
                            
                            # Use module name as LLM name
                            llm_name = module_name.replace('_llm', '')
                            llm_factories[llm_name] = obj
                            print(f"Discovered LLM factory: {name} from {filename}")
                            
                except Exception as e:
                    print(f"Error loading LLM module {filename}: {e}")
                    import traceback
                    traceback.print_exc()
                    
        return llm_factories

class LLMRegistry:
    """LLM registry with auto-discovery capabilities"""
    
    def __init__(self, llm_dir: str = None):
        self.llm_factories = {}
        self.llm_dir = llm_dir
        self._discover_and_register()
    
    def _discover_and_register(self):
        """Discover and register all available LLM factories"""
        self.llm_factories = LLMDiscovery.discover_llms(self.llm_dir)
    
    def create_llm(self, llm_name: str, **kwargs) -> BaseLLM:
        """Create an LLM instance by name"""
        factory = self.llm_factories.get(llm_name)
        if factory is None:
            available = ', '.join(self.llm_factories.keys())
            raise ValueError(f"Unknown LLM: {llm_name}. Available LLMs: {available}")
        return factory(**kwargs)
    
    def list_llms(self) -> list:
        """List all registered LLM names"""
        return list(self.llm_factories.keys())