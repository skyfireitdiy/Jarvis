import requests
import json
from typing import Dict, Any, Optional
from .base import BaseLLM

class OllamaLLM(BaseLLM):
    """Ollama LLM implementation"""
    
    def __init__(self, model_name: str = "llama2", **kwargs):
        super().__init__(model_name=model_name, **kwargs)
        self.api_base = kwargs.get('api_base', 'http://localhost:11434')
    
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
    
    def get_chat_completion(self, messages: list, **kwargs) -> str:
        """Get chat completion from Ollama"""
        url = f"{self.api_base}/api/chat"
        
        data = {
            "model": self.model_name,
            "messages": messages,
            **kwargs
        }
        
        response = requests.post(url, json=data)
        response.raise_for_status()
        
        # Parse streaming response
        full_response = ""
        for line in response.text.strip().split('\n'):
            if not line:
                continue
            try:
                chunk = json.loads(line)
                if 'message' in chunk and 'content' in chunk['message']:
                    full_response += chunk['message']['content']
            except json.JSONDecodeError:
                continue
        
        return full_response
    
    def get_embedding(self, text: str) -> list:
        """Get embedding from Ollama"""
        url = f"{self.api_base}/api/embeddings"
        
        data = {
            "model": self.model_name,
            "prompt": text
        }
        
        response = requests.post(url, json=data)
        response.raise_for_status()
        
        return response.json().get('embedding', [])
    
    def get_token_count(self, text: str) -> int:
        """Get token count from Ollama"""
        # Ollama doesn't provide token counting API
        # This is a rough estimate
        return len(text.split())