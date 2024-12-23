import requests
import json
from typing import Dict, Any
from .base import BaseLLM

class OllamaLLM(BaseLLM):
    """Ollama LLM implementation"""
    
    def __init__(self, model_name: str = "llama3:latest", **kwargs):
        super().__init__(model_name=model_name, **kwargs)
        self.api_base = kwargs.get('api_base', 'http://localhost:11434')
    
    def get_model_name(self) -> str:
        """Get the name of the current model"""
        return f"ollama-{self.model_name}"
    
    def get_completion(self, prompt: str, **kwargs) -> str:
        """Get completion from Ollama"""
        url = f"{self.api_base}/api/generate"
        
        data = {
            "model": self.model_name,
            "prompt": prompt,
            **kwargs
        }
        
        response = requests.post(url, json=data)
        response.raise_for_status()
        
        # Ollama returns streaming responses, we need to combine them
        full_response = ""
        for line in response.text.strip().split('\n'):
            if not line:
                continue
            try:
                chunk = json.loads(line)
                if 'response' in chunk:
                    full_response += chunk['response']
            except json.JSONDecodeError:
                continue
        
        return full_response

def create_llm(**kwargs) -> BaseLLM:
    """Create Ollama LLM instance"""
    return OllamaLLM(**kwargs)