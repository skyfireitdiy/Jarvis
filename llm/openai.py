import openai
from typing import Optional
from .base import LLM

class OpenAILLM(LLM):
    """OpenAI LLM implementation"""
    
    def __init__(self, model_name: str = "gpt-3.5-turbo", api_key: str = None, **kwargs):
        super().__init__(model_name, **kwargs)
        if api_key:
            openai.api_key = api_key
    
    def chat(self, prompt: str) -> str:
        """Send chat message to OpenAI"""
        response = openai.ChatCompletion.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            **self.kwargs
        )
        return response.choices[0].message.content 