import openai
from typing import Dict, Any, Optional
from .base import BaseLLM

class OpenAILLM(BaseLLM):
    """OpenAI LLM implementation"""
    
    def __init__(self, model_name: str = "gpt-3.5-turbo", api_key: str = None, **kwargs):
        super().__init__(model_name=model_name, **kwargs)
        if api_key:
            openai.api_key = api_key
    
    def get_completion(self, prompt: str, **kwargs) -> str:
        """Get completion from OpenAI"""
        messages = [{"role": "user", "content": prompt}]
        return self.get_chat_completion(messages, **kwargs)
    
    def get_chat_completion(self, messages: list, **kwargs) -> str:
        """Get chat completion from OpenAI"""
        response = openai.ChatCompletion.create(
            model=self.model_name,
            messages=messages,
            **kwargs
        )
        return response.choices[0].message.content
    
    def get_embedding(self, text: str) -> list:
        """Get embedding from OpenAI"""
        response = openai.Embedding.create(
            model="text-embedding-ada-002",
            input=text
        )
        return response.data[0].embedding
    
    def get_token_count(self, text: str) -> int:
        """Get token count from OpenAI"""
        # This is a rough estimate
        return len(text.split()) * 1.3