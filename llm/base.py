from typing import Dict, Any, Optional

class BaseLLM:
    """Base class for LLM implementations"""
    
    def __init__(self, model_name: str, **kwargs):
        self.model_name = model_name
        self.kwargs = kwargs
    
    def get_model_name(self) -> str:
        """Get the name of the current model"""
        return self.model_name
    
    def get_completion(self, prompt: str, **kwargs) -> str:
        """Get completion from LLM"""
        raise NotImplementedError("Subclass must implement get_completion method")