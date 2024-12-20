import openai
from typing import Dict, Any
from .base import BaseLLM

class OpenAILLM(BaseLLM):
    """OpenAI LLM implementation"""
    
    def __init__(self, model_name: str = "gpt-3.5-turbo", api_key: str = None, **kwargs):
        super().__init__(model_name=model_name, **kwargs)
        if api_key:
            openai.api_key = api_key
    
    def get_completion(self, prompt: str, **kwargs) -> str:
        """Get completion from OpenAI"""
        response = openai.ChatCompletion.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            **kwargs
        )
        return response.choices[0].message.content

def create_llm(**kwargs) -> BaseLLM:
    """Create OpenAI LLM instance"""
    return OpenAILLM(**kwargs)