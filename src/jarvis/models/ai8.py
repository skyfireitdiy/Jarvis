import os
from typing import Dict, List
from jarvis.models.base import BaseModel
from jarvis.utils import PrettyOutput, OutputType
import requests
import json
import base64

class AI8Model(BaseModel):
    """AI8 model implementation"""
    
    model_name = "ai8"
    BASE_URL = "https://ai8.rcouyi.com"
    
    def __init__(self):
        """Initialize model"""
        PrettyOutput.section("支持的模型", OutputType.SUCCESS)

        PrettyOutput.print("gpt-3.5-turbo", OutputType.INFO)
        PrettyOutput.print("gpt-4-turbo", OutputType.INFO)
        PrettyOutput.print("gpt-4o", OutputType.INFO)
        PrettyOutput.print("gpt-4o-mini", OutputType.INFO)
        PrettyOutput.print("o1-mini", OutputType.INFO)
        PrettyOutput.print("gpt-4-vision-preview", OutputType.INFO)
        PrettyOutput.print("gpt-4-turbo-preview", OutputType.INFO)
        PrettyOutput.print("o1-mini-all", OutputType.INFO)
        PrettyOutput.print("gpt-4o-all", OutputType.INFO)
        PrettyOutput.print("o1-preview", OutputType.INFO)
        PrettyOutput.print("claude-3-5-sonnet-20241022", OutputType.INFO)
        PrettyOutput.print("claude-3-opus-20240229", OutputType.INFO)
        PrettyOutput.print("claude-3-haiku-20240307", OutputType.INFO)
        PrettyOutput.print("claude-3-5-sonnet-20240620", OutputType.INFO)
        PrettyOutput.print("deepseek-chat", OutputType.INFO)
        PrettyOutput.print("deepseek-coder", OutputType.INFO)
        PrettyOutput.print("glm-4-flash", OutputType.INFO)
        PrettyOutput.print("glm-4-air", OutputType.INFO)
        PrettyOutput.print("glm-4v-flash", OutputType.INFO)
        PrettyOutput.print("qwen-plus", OutputType.INFO)
        PrettyOutput.print("qwen-vl-max", OutputType.INFO)
        PrettyOutput.print("qwen-turbo", OutputType.INFO)
        PrettyOutput.print("lite", OutputType.INFO)
        PrettyOutput.print("generalv3.5", OutputType.INFO)
        PrettyOutput.print("yi-lightning", OutputType.INFO)
        PrettyOutput.print("yi-vision", OutputType.INFO)
        PrettyOutput.print("yi-spark", OutputType.INFO)
        PrettyOutput.print("yi-medium", OutputType.INFO)
        PrettyOutput.print("Doubao-lite-4k", OutputType.INFO)
        PrettyOutput.print("Doubao-lite-32k", OutputType.INFO)
        PrettyOutput.print("Doubao-pro-4k", OutputType.INFO)
        PrettyOutput.print("Doubao-pro-32k", OutputType.INFO)
        PrettyOutput.print("step-1-flash", OutputType.INFO)
        PrettyOutput.print("step-1v-8k", OutputType.INFO)
        PrettyOutput.print("Baichuan4-Air", OutputType.INFO)
        PrettyOutput.print("Baichuan4-Turbo", OutputType.INFO)
        PrettyOutput.print("moonshot-v1-8k", OutputType.INFO)
        PrettyOutput.print("moonshot-v1-32k", OutputType.INFO)
        PrettyOutput.print("moonshot-v1-128k", OutputType.INFO)
        PrettyOutput.print("ERNIE-Speed-128K", OutputType.INFO)
        PrettyOutput.print("ERNIE-3.5-128K", OutputType.INFO)


        PrettyOutput.print("使用AI8_MODEL环境变量配置模型", OutputType.SUCCESS)
        
        self.system_message = ""
        self.conversation = None
        self.files = []
        self.model = os.getenv("AI8_MODEL") or "deepseek-chat"
        self.token = os.getenv("AI8_API_KEY")
        if not all([self.model, self.token]):
            raise Exception("AI8_MODEL or AI8_API_KEY is not set")
        PrettyOutput.print(f"当前使用模型: {self.model}", OutputType.SYSTEM)
            
    def create_conversation(self) -> bool:
        """Create a new conversation"""
        try:
            headers = {
                'Authorization': self.token,
                'Content-Type': 'application/json',
                'Accept': 'application/json, text/plain, */*',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'X-APP-VERSION': '2.2.2',
                'Origin': self.BASE_URL,
                'Referer': f'{self.BASE_URL}/chat?_userMenuKey=chat'
            }
            
            # 1. 创建会话
            response = requests.post(
                f"{self.BASE_URL}/api/chat/session",
                headers=headers
            )
            
            if response.status_code != 200:
                PrettyOutput.print(f"创建会话失败: {response.status_code}", OutputType.ERROR)
                return False
            
            data = response.json()
            if data['code'] != 0:
                PrettyOutput.print(f"创建会话失败: {data.get('msg', '未知错误')}", OutputType.ERROR)
                return False
            
            self.conversation = data['data']
            PrettyOutput.print(f"创建会话成功: {data['data']['id']}", OutputType.SUCCESS)
            
            # 2. 更新会话设置
            session_data = {
                **self.conversation,
                "model": self.model,
                "contextCount": 1024,
                "prompt": self.system_message,
                "plugins": ["tavily_search"],
                "localPlugins": None,
                "useAppId": 0
            }
            
            response = requests.put(
                f"{self.BASE_URL}/api/chat/session/{self.conversation['id']}",
                headers=headers,
                json=session_data
            )
            
            if response.status_code == 200:
                data = response.json()
                if data['code'] == 0:
                    self.conversation = data['data']
                    PrettyOutput.print("会话设置更新成功", OutputType.SUCCESS)
                    return True
                else:
                    PrettyOutput.print(f"更新会话设置失败: {data.get('msg', '未知错误')}", OutputType.ERROR)
                    return False
            else:
                PrettyOutput.print(f"更新会话设置失败: {response.status_code}", OutputType.ERROR)
                return False
            
        except Exception as e:
            PrettyOutput.print(f"创建会话异常: {str(e)}", OutputType.ERROR)
            return False
        
    def upload_files(self, file_list: List[str]) -> List[Dict]:
        for file_path in file_list:
            name = os.path.basename(file_path)
            with open(file_path, 'rb') as f:
                file_data = f.read()
            base64_data = base64.b64encode(file_data).decode('utf-8')
            self.files.append({
                "name": name,
                "data": f"data:image/png;base64,{base64_data}"
            })
            PrettyOutput.print(f"文件 {name} 已准备好发送", OutputType.SUCCESS)
    
    def set_system_message(self, message: str):
        """Set system message"""
        self.system_message = message
        
    def chat(self, message: str) -> str:
        """Execute chat with the model
        
        Args:
            message: User input message
            
        Returns:
            str: Model response
        """
        try:
            # 确保有会话ID
            if not self.conversation:
                if not self.create_conversation():
                    raise Exception("Failed to create conversation")
                
            headers = {
                'Authorization': self.token,
                'Content-Type': 'application/json',
                'Accept': 'text/event-stream',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'X-APP-VERSION': '2.2.2',
                'Origin': self.BASE_URL,
                'Referer': f'{self.BASE_URL}/chat?_userMenuKey=chat'
            }
            
            payload = {
                "text": message,
                "sessionId": self.conversation['id'],
                "files": []
            }
            
            # 如果有文件需要发送
            if self.files:
                for file_data in self.files:
                    payload["files"].append({
                        "name": file_data["name"],
                        "data": file_data["data"]
                    })
                self.files = []  # 清空已使用的文件
            
            response = requests.post(
                f"{self.BASE_URL}/api/chat/completions",
                headers=headers,
                json=payload,
                stream=True
            )
            
            if response.status_code != 200:
                error_msg = f"聊天请求失败: {response.status_code}"
                PrettyOutput.print(error_msg, OutputType.ERROR)
                raise Exception(error_msg)
            
            # 处理流式响应
            full_response = ""
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        try:
                            data = json.loads(line[6:])
                            if data.get('type') == 'string':
                                chunk = data.get('data', '')
                                if chunk:
                                    full_response += chunk
                                    PrettyOutput.print_stream(chunk)

                        except json.JSONDecodeError:
                            continue
            
            PrettyOutput.print_stream_end()

            return full_response
            
        except Exception as e:
            PrettyOutput.print(f"聊天异常: {str(e)}", OutputType.ERROR)
            raise e
            
    def name(self) -> str:
        """Return model name"""
        return self.model_name
        
    def reset(self):
        """Reset model state"""
        self.conversation = None
        self.files = []  # 清空文件列表
            
    def delete_chat(self) -> bool:
        """Delete current chat session"""
        try:
            if not self.conversation:
                return True
            
            headers = {
                'Authorization': self.token,
                'Content-Type': 'application/json',
                'Accept': 'application/json, text/plain, */*',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'X-APP-VERSION': '2.2.2',
                'Origin': self.BASE_URL,
                'Referer': f'{self.BASE_URL}/chat?_userMenuKey=chat'
            }
            
            response = requests.delete(
                f"{self.BASE_URL}/api/chat/session/{self.conversation['id']}",
                headers=headers
            )
            
            if response.status_code == 200:
                data = response.json()
                if data['code'] == 0:
                    PrettyOutput.print("会话删除成功", OutputType.SUCCESS)
                    self.reset()
                    return True
                else:
                    error_msg = f"删除会话失败: {data.get('msg', '未知错误')}"
                    PrettyOutput.print(error_msg, OutputType.ERROR)
                    return False
            else:
                error_msg = f"删除会话请求失败: {response.status_code}"
                PrettyOutput.print(error_msg, OutputType.ERROR)
                return False
            
        except Exception as e:
            PrettyOutput.print(f"删除会话异常: {str(e)}", OutputType.ERROR)
            return False
        
