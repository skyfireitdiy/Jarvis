from typing import List, Dict, Tuple
from jarvis.jarvis_platform.base import BasePlatform
import os

from jarvis.jarvis_utils.output import OutputType, PrettyOutput


import ollama

class OllamaPlatform(BasePlatform):
    """Ollama platform implementation"""
    
    platform_name = "ollama"
    
    def __init__(self):
        """Initialize model"""
        super().__init__()
        
        # Check environment variables and provide help information
        self.api_base = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")
        self.model_name = os.getenv("JARVIS_MODEL") or "deepseek-r1:1.5b"
        
        # Setup client based on availability
        self.client = None
        self.client = ollama.Client(host=self.api_base)
        
        # Check if Ollama service is available
        try:
            available_models = self._get_available_models()
            
            if not available_models:
                message = (
                    "需要先下载 Ollama 模型才能使用:\n"
                    "1. 安装 Ollama: https://ollama.ai\n"
                    "2. 下载模型:\n"
                    f"   ollama pull {self.model_name}"
                )
                PrettyOutput.print(message, OutputType.INFO)
                PrettyOutput.print("Ollama 没有可用的模型", OutputType.WARNING)
                
        except Exception as e:
            message = (
                f"Ollama 服务未启动或无法连接: {str(e)}\n"
                "请确保您已:\n"
                "1. 安装 Ollama: https://ollama.ai\n"
                "2. 启动 Ollama 服务\n"
                "3. 正确配置服务地址 (默认: http://localhost:11434)"
            )
            PrettyOutput.print(message, OutputType.WARNING)
            
            
        self.messages = []
        self.system_message = ""

    def _get_available_models(self) -> List[str]:
        """Get list of available models using appropriate method"""
        models_response = self.client.list() # type: ignore
        return [model["model"] for model in models_response.get("models", [])]

    def get_model_list(self) -> List[Tuple[str, str]]:
        """Get model list"""
        try:
            models = self._get_available_models()
            return [(model, "") for model in models]
        except Exception as e:
            PrettyOutput.print(f"获取模型列表失败: {str(e)}", OutputType.ERROR)
            return []

    def set_model_name(self, model_name: str):
        """Set model name"""
        self.model_name = model_name

    def chat(self, message: str) -> str:
        """Execute conversation"""
        try:
            # Build message list
            messages = []
            if self.system_message:
                messages.append({"role": "system", "content": self.system_message})
            messages.extend(self.messages)
            messages.append({"role": "user", "content": message})

            return self._chat_with_package(messages)
            
        except Exception as e:
            PrettyOutput.print(f"对话失败: {str(e)}", OutputType.ERROR)
            raise Exception(f"Chat failed: {str(e)}")

    def _chat_with_package(self, messages: List[Dict]) -> str:
        """Chat using the ollama package"""
        # The client should not be None here due to the check in the chat method
        if not self.client:
            raise ValueError("Ollama client is not initialized")
            
        # Use ollama-python's streaming API
        stream = self.client.chat(
            model=self.model_name,
            messages=messages,
            stream=True
        )
        
        # Process the streaming response
        full_response = ""
        for chunk in stream:
            if "message" in chunk and "content" in chunk["message"]:
                text = chunk["message"]["content"]
                if not self.suppress_output:
                    PrettyOutput.print_stream(text)
                full_response += text
                    
        if not self.suppress_output:
            PrettyOutput.print_stream_end()
        
        # Update message history
        self.messages.append({"role": "user", "content": messages[-1]["content"]})
        self.messages.append({"role": "assistant", "content": full_response})
        
        return full_response

        
    def name(self) -> str:
        """Return model name"""
        return self.model_name
            
    def delete_chat(self) -> bool:
        """Delete current chat session"""
        self.messages = []
        if self.system_message:
            self.messages.append({"role": "system", "content": self.system_message})
        return True
        
    def set_system_message(self, message: str):
        """Set system message"""
        self.system_message = message
        self.messages = []
        if self.system_message:
            self.messages.append({"role": "system", "content": self.system_message})
