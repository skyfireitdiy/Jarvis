import os
import importlib
import inspect
from typing import Dict, Type, Callable
from .base import BaseLLM

class LLMDiscovery:
    """Discover LLM implementations"""
    
    @staticmethod
    def discover_llms(llms_dir: str = None) -> Dict[str, Callable]:
        """Discover all LLM factory functions"""
        if llms_dir is None:
            llms_dir = os.path.dirname(os.path.abspath(__file__))
            
        print(f"Scanning directory for LLMs: {llms_dir}")
        llm_factories = {}
        
        # Get all .py files in the llms directory
        for filename in os.listdir(llms_dir):
            if filename.endswith('.py') and not filename.startswith('_'):
                print(f"Found LLM file: {filename}")
                # Convert filename to module name
                module_name = f".{filename[:-3]}"  # Remove .py
                
                try:
                    # Import the module
                    module = importlib.import_module(module_name, package="llm")
                    
                    # Look for create_llm function
                    if hasattr(module, 'create_llm'):
                        factory_name = filename[:-3]  # Remove .py
                        llm_factories[factory_name] = module.create_llm
                        print(f"Discovered LLM factory: create_llm from {filename}")
                        
                except Exception as e:
                    print(f"Error loading LLM module {filename}: {e}")
                    
        return llm_factories

class LLMRegistry:
    """Registry for LLM implementations"""
    
    def __init__(self):
        self.factories = {}
        self._discover_and_register()
    
    def _discover_and_register(self):
        """Discover and register all available LLMs"""
        discovered = LLMDiscovery.discover_llms()
        self.factories.update(discovered)
    
    def create_llm(self, model_name: str = "ollama", **kwargs) -> BaseLLM:
        """Create LLM instance by name"""
        # Extract the base model name (e.g., "zte" from "zte-nebulacoder")
        base_model = model_name.split('-')[0] if '-' in model_name else model_name
        
        # Look for factory function
        factory = self.factories.get(f"{base_model}_llm")
        if factory:
            return factory(**kwargs)
            
        raise ValueError(f"Unknown LLM model: {model_name}")