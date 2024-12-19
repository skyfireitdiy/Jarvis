import ollama
from typing import Optional
from .base import LLM

class OllamaLLM(LLM):
    """Ollama LLM implementation"""
    
    def __init__(self, model_name: str = "llama2:latest", **kwargs):
        super().__init__(model_name, **kwargs)
    
    def chat(self, prompt: str) -> str:
        """Send chat message to Ollama"""
        response = ollama.chat(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            **self.kwargs
        )
        return response["message"]["content"] 