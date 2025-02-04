import requests
from typing import List, Dict, Tuple
from jarvis.models.base import BasePlatform
from jarvis.utils import OutputType, PrettyOutput
import os
import json

class OllamaPlatform(BasePlatform):
    """Ollama 平台实现"""
    
    platform_name = "ollama"
    
    def __init__(self):
        """初始化模型"""
        super().__init__()
        
        # 检查环境变量并提供帮助信息
        self.api_base = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")
        self.model_name = os.getenv("JARVIS_MODEL") or "deepseek-r1:1.5b"
        
        # 检查 Ollama 服务是否可用
        try:
            response = requests.get(f"{self.api_base}/api/tags")
            response.raise_for_status()
            available_models = [model["name"] for model in response.json().get("models", [])]
            
            if not available_models:
                PrettyOutput.print("\n需要先下载 Ollama 模型才能使用：", OutputType.INFO)
                PrettyOutput.print("1. 安装 Ollama: https://ollama.ai", OutputType.INFO)
                PrettyOutput.print("2. 下载模型:", OutputType.INFO)
                PrettyOutput.print(f"   ollama pull {self.model_name}", OutputType.INFO)
                raise Exception("No available models found")
                
        except requests.exceptions.ConnectionError:
            PrettyOutput.print("\nOllama 服务未启动或无法连接", OutputType.ERROR)
            PrettyOutput.print("请确保已经：", OutputType.INFO)
            PrettyOutput.print("1. 安装了 Ollama: https://ollama.ai", OutputType.INFO)
            PrettyOutput.print("2. 启动了 Ollama 服务", OutputType.INFO)
            PrettyOutput.print("3. 服务地址配置正确 (默认: http://localhost:11434)", OutputType.INFO)
            raise Exception("Ollama service is not available")
            
        self.messages = []
        self.system_message = ""

    def get_model_list(self) -> List[Tuple[str, str]]:
        """获取模型列表"""
        response = requests.get(f"{self.api_base}/api/tags")
        response.raise_for_status()
        return [(model["name"], "") for model in response.json().get("models", [])]

    def set_model_name(self, model_name: str):
        """设置模型名称"""
        self.model_name = model_name

    def chat(self, message: str) -> str:
        """执行对话"""
        try:
            # 构建消息列表
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
        """上传文件 (Ollama 不支持文件上传)"""
        PrettyOutput.print("Ollama 不支持文件上传", output_type=OutputType.WARNING)
        return []
        
    def reset(self):
        """重置模型状态"""
        self.messages = []
        if self.system_message:
            self.messages.append({"role": "system", "content": self.system_message})
            
    def name(self) -> str:
        """返回模型名称"""
        return self.model_name
            
    def delete_chat(self) -> bool:
        """删除当前聊天会话"""
        self.reset()
        return True
        
    def set_system_message(self, message: str):
        """设置系统消息"""
        self.system_message = message
        self.reset()  # 重置会话以应用新的系统消息 


if __name__ == "__main__":
    try:
        ollama = OllamaPlatform()
        while True:
            try:
                message = input("\n输入问题(Ctrl+C退出): ")
                ollama.chat(message)
            except KeyboardInterrupt:
                print("\n再见！")
                break
    except Exception as e:
        PrettyOutput.print(f"程序异常退出: {str(e)}", OutputType.ERROR)
