from typing import Optional, List, Dict
import os
from openai import OpenAI
from .base import BaseModel
from ..utils import PrettyOutput, OutputType

class OpenAIModel(BaseModel):
    """DeepSeek模型实现"""
    
    def __init__(self, verbose: bool = False):
        """
        初始化DeepSeek模型
        Args:
            verbose: 是否显示详细输出
        """
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise Exception("OPENAI_API_KEY is not set")
            
        self.base_url = os.getenv("OPENAI_API_BASE", "https://api.deepseek.com")
        self.model_name = os.getenv("OPENAI_API_MODEL", "deepseek-chat")
            
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        self.verbose = verbose
        self.messages: List[Dict[str, str]] = []
        self.system_message = ""

    def set_system_message(self, message: str):
        """设置系统消息"""
        self.system_message = message
        self.messages.append({"role": "system", "content": self.system_message})

    def chat(self, message: str) -> str:
        """执行对话"""
        try:
            PrettyOutput.print("发送请求...", OutputType.PROGRESS)
            
            # 添加用户消息到历史记录
            self.messages.append({"role": "user", "content": message})
            
            response = self.client.chat.completions.create(
                model=self.model_name,  # 使用配置的模型名称
                messages=self.messages,
                stream=True
            )
            
            PrettyOutput.print("接收响应...", OutputType.PROGRESS)
            full_response = ""
            
            for chunk in response:
                if chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    PrettyOutput.print_stream(text, OutputType.SYSTEM)
                    full_response += text
                    
            PrettyOutput.print_stream_end()
            
            # 添加助手回复到历史记录
            self.messages.append({"role": "assistant", "content": full_response})
            
            return full_response
            
        except Exception as e:
            raise Exception(f"Chat failed: {str(e)}")

    def name(self) -> str:
        """返回模型名称"""
        return self.model_name

    def reset(self):
        """重置模型状态"""
        # 清空对话历史，只保留system message
        if self.system_message:
            self.messages = [{"role": "system", "content": self.system_message}]
        else:
            self.messages = []

    def delete_chat(self)->bool:
        """删除对话"""
        pass

if __name__ == "__main__":
    model = OpenAIModel()
    print(model.chat("Hello! How are you?")) 