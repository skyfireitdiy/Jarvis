# -*- coding: utf-8 -*-
from typing import Dict, List, Tuple
import os
from openai import OpenAI
from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_utils.output import OutputType, PrettyOutput

class OpenAIModel(BasePlatform):
    platform_name = "openai"

    def __init__(self):
        """
        Initialize OpenAI model
        """
        super().__init__()
        self.system_message = ""
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            message = (
                "需要设置以下环境变量才能使用 OpenAI 模型:\n"
                "  • OPENAI_API_KEY: API 密钥\n"
                "  • OPENAI_API_BASE: (可选) API 基础地址, 默认使用 https://api.openai.com/v1\n"
                "您可以通过以下方式设置它们:\n"
                "1. 创建或编辑 ~/.jarvis/env 文件:\n"
                "   OPENAI_API_KEY=your_api_key\n"
                "   OPENAI_API_BASE=your_api_base\n"
                "   OPENAI_MODEL_NAME=your_model_name\n"
                "2. 直接设置环境变量:\n"
                "   export OPENAI_API_KEY=your_api_key\n"
                "   export OPENAI_API_BASE=your_api_base\n"
                "   export OPENAI_MODEL_NAME=your_model_name"
            )
            PrettyOutput.print(message, OutputType.INFO)
            PrettyOutput.print("OPENAI_API_KEY 未设置", OutputType.WARNING)

        self.base_url = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
        self.model_name =  os.getenv("JARVIS_MODEL") or "gpt-4o"


        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        self.messages: List[Dict[str, str]] = []
        self.system_message = ""

    def upload_files(self, file_list: List[str]) -> bool:
        return False

    def get_model_list(self) -> List[Tuple[str, str]]:
        """Get model list"""
        try:
            models = self.client.models.list()
            model_list = []
            for model in models:
                model_list.append((model.id, model.id))
            return model_list
        except Exception as e:
            PrettyOutput.print(f"获取模型列表失败：{str(e)}", OutputType.ERROR)
            return []

    def set_model_name(self, model_name: str):
        """Set model name"""

        self.model_name = model_name

    def set_system_message(self, message: str):
        """Set system message"""
        self.system_message = message
        self.messages.append({"role": "system", "content": self.system_message})

    def chat(self, message: str) -> str:
        """Execute conversation"""
        try:

            # Add user message to history
            self.messages.append({"role": "user", "content": message})

            response = self.client.chat.completions.create(
                model=self.model_name,  # Use the configured model name
                messages=self.messages, # type: ignore
                stream=True
            ) # type: ignore

            full_response = ""

            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    if not self.suppress_output:
                        PrettyOutput.print_stream(text)
                    full_response += text

            if not self.suppress_output:
                PrettyOutput.print_stream_end()

            # Add assistant reply to history
            self.messages.append({"role": "assistant", "content": full_response})

            return full_response

        except Exception as e:
            PrettyOutput.print(f"对话失败：{str(e)}", OutputType.ERROR)
            raise Exception(f"Chat failed: {str(e)}")

    def name(self) -> str:
        """Return model name"""
        return self.model_name


    def delete_chat(self)->bool:
        """Delete conversation"""
        if self.system_message:
            self.messages = [{"role": "system", "content": self.system_message}]
        else:
            self.messages = []
        return True
