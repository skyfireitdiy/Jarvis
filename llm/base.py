from typing import Optional, Dict, Any

class LLM:
    """Base class for LLM implementations"""
    
    def __init__(self, model_name: str = None, **kwargs):
        self.model_name = model_name
        self.kwargs = kwargs
    
    def chat(self, prompt: str) -> str:
        """Send chat message and get response"""
        raise NotImplementedError("LLM must implement chat method")
    
    def get_model_name(self) -> str:
        """Get the name of the current model"""
        return self.model_name or self.__class__.__name__ 