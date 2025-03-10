import requests
from typing import List, Dict, Tuple
from jarvis.jarvis_platform.base import BasePlatform
import os
import json

from jarvis.jarvis_utils.input import get_single_line_input
from jarvis.jarvis_utils.output import OutputType, PrettyOutput

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
                message = (
                    "需要先下载 Ollama 模型才能使用:\n"
                    "1. 安装 Ollama: https://ollama.ai\n"
                    "2. 下载模型:\n"
                    f"   ollama pull {self.model_name}"
                )
                PrettyOutput.print(message, OutputType.INFO)
                PrettyOutput.print("Ollama 没有可用的模型", OutputType.WARNING)
                
        except requests.exceptions.ConnectionError:
            message = (
                "Ollama 服务未启动或无法连接\n"
                "请确保您已:\n"
                "1. 安装 Ollama: https://ollama.ai\n"
                "2. 启动 Ollama 服务\n"
                "3. 正确配置服务地址 (默认: http://localhost:11434)"
            )
            PrettyOutput.print(message, OutputType.WARNING)
            
            
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
            PrettyOutput.print(f"对话失败: {str(e)}", OutputType.ERROR)
            raise Exception(f"Chat failed: {str(e)}")

    def upload_files(self, file_list: List[str]) -> List[Dict]:
        """Upload files (Ollama does not support file upload)"""
        PrettyOutput.print("Ollama 不支持文件上传", output_type=OutputType.WARNING)
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
                message = get_single_line_input("输入问题 (Ctrl+C 退出)")
                ollama.chat_until_success(message)
            except KeyboardInterrupt:
                print("再见!")
                break
    except Exception as e:
        PrettyOutput.print(f"程序异常退出: {str(e)}", OutputType.ERROR)
