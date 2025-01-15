from typing import Dict, List
import os
from openai import OpenAI
from jarvis.models.base import BasePlatform
from jarvis.utils import PrettyOutput, OutputType

class OpenAIModel(BasePlatform):
    """DeepSeek模型实现"""

    platform_name = "openai"
    
    def __init__(self):
        """
        初始化DeepSeek模型
        """
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            PrettyOutput.print("\n需要设置以下环境变量才能使用 OpenAI 模型：", OutputType.INFO)
            PrettyOutput.print("  • OPENAI_API_KEY: API 密钥", OutputType.INFO)
            PrettyOutput.print("  • OPENAI_API_BASE: (可选) API 基础地址，默认使用 https://api.deepseek.com", OutputType.INFO)
            PrettyOutput.print("\n可以通过以下方式设置：", OutputType.INFO)
            PrettyOutput.print("1. 创建或编辑 ~/.jarvis_env 文件:", OutputType.INFO)
            PrettyOutput.print("   OPENAI_API_KEY=your_api_key", OutputType.INFO)
            PrettyOutput.print("   OPENAI_API_BASE=your_api_base", OutputType.INFO)
            PrettyOutput.print("   OPENAI_MODEL_NAME=your_model_name", OutputType.INFO)
            PrettyOutput.print("\n2. 或者直接设置环境变量:", OutputType.INFO)
            PrettyOutput.print("   export OPENAI_API_KEY=your_api_key", OutputType.INFO)
            PrettyOutput.print("   export OPENAI_API_BASE=your_api_base", OutputType.INFO)
            PrettyOutput.print("   export OPENAI_MODEL_NAME=your_model_name", OutputType.INFO)
            raise Exception("OPENAI_API_KEY is not set")
            
        self.base_url = os.getenv("OPENAI_API_BASE", "https://api.deepseek.com")
        self.model_name = os.getenv("OPENAI_MODEL_NAME", "deepseek-chat")

        PrettyOutput.print(f"当前使用模型: {self.model_name}", OutputType.SYSTEM)
            
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        self.messages: List[Dict[str, str]] = []
        self.system_message = ""

    def set_model_name(self, model_name: str):
        """设置模型名称"""
        self.model_name = model_name

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
                    PrettyOutput.print_stream(text)
                    full_response += text
                    
            PrettyOutput.print_stream_end()
            
            # 添加助手回复到历史记录
            self.messages.append({"role": "assistant", "content": full_response})
            
            return full_response
            
        except Exception as e:
            PrettyOutput.print(f"对话失败: {str(e)}", OutputType.ERROR)
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
        self.reset()
        return True
