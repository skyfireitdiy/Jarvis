import json
import re
import time
from typing import Dict, List, Optional
from duckduckgo_search import DDGS
import ollama
from abc import ABC, abstractmethod

from .utils import OutputType, PrettyOutput

class BaseModel(ABC):
    """大语言模型基类"""
    
    @abstractmethod
    def chat(self, messages: List[Dict], tools: Optional[List[Dict]] = None) -> Dict:
        """执行对话"""
        pass

    @staticmethod
    def extract_tool_calls(content: str) -> List[Dict]:
        """从内容中提取工具调用"""
        tool_calls = []
        # 修改正则表达式以更好地处理多行内容
        pattern = re.compile(
            r'<tool_call>\s*({(?:[^{}]|(?:{[^{}]*})|(?:{(?:[^{}]|{[^{}]*})*}))*})\s*</tool_call>',
            re.DOTALL  # 添加DOTALL标志以匹配跨行内容
        )
        
        matches = pattern.finditer(content)
        for match in matches:
            try:
                tool_call_str = match.group(1).strip()
                tool_call = json.loads(tool_call_str)
                if isinstance(tool_call, dict) and "name" in tool_call and "arguments" in tool_call:
                    tool_calls.append({
                        "function": {
                            "name": tool_call["name"],
                            "arguments": tool_call["arguments"]
                        }
                    })
                else:
                    PrettyOutput.print(f"无效的工具调用格式: {tool_call_str}", OutputType.ERROR)
            except json.JSONDecodeError as e:
                PrettyOutput.print(f"JSON解析错误: {str(e)}", OutputType.ERROR)
                PrettyOutput.print(f"解析内容: {tool_call_str}", OutputType.ERROR)
                continue
        
        return tool_calls


class DDGSModel(BaseModel):
    def __init__(self, model_name: str = "gpt-4o-mini"):
        """
        [1]: gpt-4o-mini
        [2]: claude-3-haiku
        [3]: llama-3.1-70b
        [4]: mixtral-8x7b
        """
        self.model_name = model_name

    def __make_prompt(self, messages: List[Dict], tools: Optional[List[Dict]] = None) -> str:
        prompt = "You are an AI Agent skilled in utilizing tools and planning tasks. Based on the task input by the user and the list of available tools, you output the tool invocation methods in a specified format. The user will provide feedback on the results of the tool execution, allowing you to continue analyzing and ultimately complete the user's designated task. Below is the list of tools and their usage methods. Let's use them step by step to accomplish the user's task.\n"
        for tool in tools:
            prompt += f"- Tool: {tool['function']['name']}\n"
            prompt += f"  Description: {tool['function']['description']}\n"
            prompt += f"  Arguments: {tool['function']['parameters']}\n"
        for message in messages:
            prompt += f"[{message['role']}]: {message['content']}\n"
        return prompt

    def chat(self, messages: List[Dict], tools: Optional[List[Dict]] = None) -> Dict:
        ddgs = DDGS()
        prompt = self.__make_prompt(messages, tools)
        content = ddgs.chat(prompt)
        tool_calls = BaseModel.extract_tool_calls(content)
        return {
            "message": {
                "content": content,
                "tool_calls": tool_calls
            }
        }


class OllamaModel(BaseModel):
    """Ollama模型实现"""
    
    def __init__(self, model_name: str = "qwen2.5:14b", api_base: str = "http://localhost:11434"):
        self.model_name = model_name
        self.api_base = api_base
        self.client = ollama.Client(host=api_base)

    def chat(self, messages: List[Dict], tools: Optional[List[Dict]] = None) -> Dict:
        """调用Ollama API获取响应"""
        try:
            response = self.client.chat(
                model=self.model_name,
                messages=messages,
                tools=tools
            )

            content = response.message.content
            tool_calls = response.message.tool_calls or BaseModel.extract_tool_calls(content)
            
            # 转换响应格式
            return {
                "message": {
                    "content": content,
                    "tool_calls": tool_calls
                }
            }
        except Exception as e:
            raise Exception(f"Ollama API调用失败: {str(e)}") 