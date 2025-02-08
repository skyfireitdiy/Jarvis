import requests
from typing import List, Dict, Tuple
from jarvis.models.base import BasePlatform
from jarvis.utils import OutputType, PrettyOutput
import os
import json

class OllamaPlatform(BasePlatform):
    """Ollama platform implementation"""
    
    platform_name = "ollama"
    
    def __init__(self):
        """Initialize model"""
        super().__init__()
        
        # Check environment variables and provide help information
        self.api_base = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")
        self.model_name = os.getenv("JARVIS_MODEL") or "deepseek-r1:1.5b"
        
        # Check if Ollama service is available
        try:
            response = requests.get(f"{self.api_base}/api/tags")
            response.raise_for_status()
            available_models = [model["name"] for model in response.json().get("models", [])]
            
            if not available_models:
                PrettyOutput.print("\nNeed to download Ollama model first to use:", OutputType.INFO)
                PrettyOutput.print("1. Install Ollama: https://ollama.ai", OutputType.INFO)
                PrettyOutput.print("2. Download model:", OutputType.INFO)
                PrettyOutput.print(f"   ollama pull {self.model_name}", OutputType.INFO)
                PrettyOutput.print("Ollama has no available models", OutputType.WARNING)
                
        except requests.exceptions.ConnectionError:
            PrettyOutput.print("\nOllama service is not started or cannot be connected", OutputType.WARNING)
            PrettyOutput.print("Please ensure that you have:", OutputType.INFO)
            PrettyOutput.print("1. Installed Ollama: https://ollama.ai", OutputType.INFO)
            PrettyOutput.print("2. Started Ollama service", OutputType.INFO)
            PrettyOutput.print("3. Service address configured correctly (default: http://localhost:11434)", OutputType.INFO)
            
            
        self.messages = []
        self.system_message = ""

    def get_model_list(self) -> List[Tuple[str, str]]:
        """Get model list"""
        response = requests.get(f"{self.api_base}/api/tags")
        response.raise_for_status()
        return [(model["name"], "") for model in response.json().get("models", [])]

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
            
            # 构建请求数据
            data = {
                "model": self.model_name,
                "messages": messages,
                "stream": True  # 启用流式输出
            }
            
            # 发送请求
            response = requests.post(
                f"{self.api_base}/api/chat",
                json=data,
                stream=True
            )
            response.raise_for_status()
            
            # 处理流式响应
            full_response = ""
            for line in response.iter_lines():
                if line:
                    chunk = line.decode()
                    try:
                        result = json.loads(chunk)
                        if "message" in result and "content" in result["message"]:
                            text = result["message"]["content"]
                            if not self.suppress_output:
                                PrettyOutput.print_stream(text)
                            full_response += text
                    except json.JSONDecodeError:
                        continue
                        
            if not self.suppress_output:
                PrettyOutput.print_stream_end()
            
            # 更新消息历史
            self.messages.append({"role": "user", "content": message})
            self.messages.append({"role": "assistant", "content": full_response})
            
            return full_response
            
        except Exception as e:
            PrettyOutput.print(f"Chat failed: {str(e)}", OutputType.ERROR)
            raise Exception(f"Chat failed: {str(e)}")

    def upload_files(self, file_list: List[str]) -> List[Dict]:
        """Upload files (Ollama does not support file upload)"""
        PrettyOutput.print("Ollama does not support file upload", output_type=OutputType.WARNING)
        return []
        
    def reset(self):
        """Reset model state"""
        self.messages = []
        if self.system_message:
            self.messages.append({"role": "system", "content": self.system_message})
            
    def name(self) -> str:
        """Return model name"""
        return self.model_name
            
    def delete_chat(self) -> bool:
        """Delete current chat session"""
        self.reset()
        return True
        
    def set_system_message(self, message: str):
        """Set system message"""
        self.system_message = message
        self.reset()  # 重置会话以应用新的系统消息 


if __name__ == "__main__":
    try:
        ollama = OllamaPlatform()
        while True:
            try:
                message = input("\nInput question (Ctrl+C to exit): ")
                ollama.chat_until_success(message)
            except KeyboardInterrupt:
                print("\nGoodbye!")
                break
    except Exception as e:
        PrettyOutput.print(f"Program exited with an exception: {str(e)}", OutputType.ERROR)
