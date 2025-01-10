import re
import time
from typing import Dict, List, Optional, Tuple
from duckduckgo_search import DDGS
import ollama
from abc import ABC, abstractmethod
import yaml

from .utils import OutputType, PrettyOutput

class BaseModel(ABC):
    """大语言模型基类"""
    
    @abstractmethod
    def chat(self, messages: List[Dict]) -> str:
        """执行对话"""
        pass


class DDGSModel(BaseModel):
    def __init__(self, model_name: str = "gpt-4o-mini"):
        """
        [1]: gpt-4o-mini
        [2]: claude-3-haiku
        [3]: llama-3.1-70b
        [4]: mixtral-8x7b
        """
        self.model_name = model_name

    def __make_prompt(self, messages: List[Dict]) -> str:
        prompt = ""
        for message in messages:
            prompt += f"[{message['role']}]: {message['content']}\n"
        return prompt

    def chat(self, messages: List[Dict]) -> str:
        ddgs = DDGS()
        prompt = self.__make_prompt(messages)
        content = ddgs.chat(prompt)
        PrettyOutput.print_stream(content, OutputType.SYSTEM)
        return content


class OllamaModel(BaseModel):
    """Ollama模型实现"""
    
    def __init__(self, model_name: str = "qwen2.5:14b", api_base: str = "http://localhost:11434"):
        self.model_name = model_name
        self.api_base = api_base
        self.client = ollama.Client(host=api_base)

    def chat(self, messages: List[Dict]) -> str:
        """调用Ollama API获取响应"""
        try:
            # 使用流式调用
            stream = self.client.chat(
                model=self.model_name,
                messages=messages,
                stream=True
            )

            # 收集完整响应
            content_parts = []
            for chunk in stream:
                if chunk.message.content:
                    content_parts.append(chunk.message.content)
                    # 实时打印内容
                    PrettyOutput.print_stream(chunk.message.content, OutputType.SYSTEM)

            PrettyOutput.print_stream_end()

            # 合并完整内容
            return "".join(content_parts)
            
        except Exception as e:
            raise Exception(f"Ollama API调用失败: {str(e)}") 