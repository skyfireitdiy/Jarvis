import mimetypes
import os
from typing import Dict, List
from jarvis.models.base import BaseModel
from jarvis.utils import PrettyOutput, OutputType
import requests
import json

class OyiModel(BaseModel):
    """Oyi model implementation"""
    
    model_name = "oyi"
    BASE_URL = "https://api-10086.rcouyi.com"
    
    def __init__(self):
        """Initialize model"""
        PrettyOutput.section("支持的模型", OutputType.SUCCESS)
        PrettyOutput.print("gpt-4o-mini", OutputType.INFO)
        PrettyOutput.print("gpt-3.5-turbo", OutputType.INFO)
        PrettyOutput.print("gpt-4o", OutputType.INFO)
        PrettyOutput.print("gpt-4o-2024-11-20", OutputType.INFO)
        PrettyOutput.print("o1-mini", OutputType.INFO)
        PrettyOutput.print("o1-mini-2024-09-12", OutputType.INFO)
        PrettyOutput.print("gpt-4o-all", OutputType.INFO)
        PrettyOutput.print("claude-3-5-sonnet-20240620", OutputType.INFO)
        PrettyOutput.print("claude-3-opus-20240229", OutputType.INFO)
        PrettyOutput.print("deepseek-chat", OutputType.INFO)
        PrettyOutput.print("deepseek-coder", OutputType.INFO)
        PrettyOutput.print("glm-4-flash", OutputType.INFO)
        PrettyOutput.print("glm-4-air", OutputType.INFO)
        PrettyOutput.print("qwen-plus", OutputType.INFO)
        PrettyOutput.print("qwen-turbo", OutputType.INFO)
        PrettyOutput.print("Doubao-lite-4k", OutputType.INFO)
        PrettyOutput.print("Doubao-pro-4k", OutputType.INFO)
        PrettyOutput.print("yi-lightning", OutputType.INFO)
        PrettyOutput.print("step-1-flash", OutputType.INFO)
        PrettyOutput.print("moonshot-v1-8k", OutputType.INFO)
        PrettyOutput.print("lite", OutputType.INFO)
        PrettyOutput.print("generalv3.5", OutputType.INFO)
        PrettyOutput.print("gemini-pro", OutputType.INFO)
        PrettyOutput.print("llama3-70b-8192", OutputType.INFO)
        PrettyOutput.print("使用OYI_MODEL环境变量配置模型", OutputType.SUCCESS)
        
                           
        self.messages = []
        self.system_message = ""
        self.conversation = None
        self.upload_files = []
        self.first_chat = True
        self.model = os.getenv("OYI_MODEL") or "deepseek-chat"
        self.token = os.getenv("OYI_API_KEY")
        if not all([self.model, self.token]):
            raise Exception("OYI_MODEL or OYI_API_KEY is not set")
        PrettyOutput.print(f"当前使用模型: {self.model}", OutputType.SYSTEM)

        
    def create_conversation(self) -> bool:
        """Create a new conversation"""
        try:
            headers = {
                'Authorization': f'Bearer {self.token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
            }
            
            payload = {
                "id": 0,
                "roleId": 0,
                "title": "新对话",
                "isLock": False,
                "systemMessage": "",
                "params": json.dumps({
                    "model": "gpt-4o-mini",
                    "is_webSearch": True,
                    "message": [],
                    "systemMessage": None,
                    "requestMsgCount": 1000,
                    "temperature": 0.8,
                    "speechVoice": "Alloy",
                    "max_tokens": 8192,
                    "chatPluginIds": []
                })
            }
            
            response = requests.post(
                f"{self.BASE_URL}/chatapi/chat/save",
                headers=headers,
                json=payload
            )
            
            if response.status_code == 200:
                data = response.json()
                if data['code'] == 200 and data['type'] == 'success':
                    self.conversation = data
                    PrettyOutput.print(f"创建会话成功: {data['result']['id']}", OutputType.SUCCESS)
                    return True
                else:
                    PrettyOutput.print(f"创建会话失败: {data['message']}", OutputType.ERROR)
                    return False
            else:
                PrettyOutput.print(f"创建会话失败: {response.status_code}", OutputType.ERROR)
                return False
                
        except Exception as e:
            PrettyOutput.print(f"创建会话异常: {str(e)}", OutputType.ERROR)
            return False
    
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
            
            # 1. 发送消息
            headers = {
                'Authorization': f'Bearer {self.token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json, text/plain, */*',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'Origin': 'https://ai.rcouyi.com',
                'Referer': 'https://ai.rcouyi.com/'
            }
            
            payload = {
                "topicId": self.conversation['result']['id'],
                "messages": self.messages,
                "content": message,
                "contentFiles": []
            }
            
            # 如果有上传的文件，添加到请求中
            if self.first_chat:
                if self.upload_files:
                    for file_data in self.upload_files:
                        file_info = {
                            "contentType": 1,  # 1 表示图片
                            "fileUrl": file_data['result']['url'],
                            "fileId": file_data['result']['id'],
                            "fileName": file_data['result']['fileName']
                        }
                        payload["contentFiles"].append(file_info)
                    # 清空已使用的文件列表
                    self.upload_files = []
                message = self.system_message + "\n" + message
                payload["content"] = message
                self.first_chat = False

            self.messages.append({"role": "user", "content": message})
            
            # 发送消息
            response = requests.post(
                f"{self.BASE_URL}/chatapi/chat/message",
                headers=headers,
                json=payload
            )
            
            if response.status_code != 200:
                error_msg = f"聊天请求失败: {response.status_code}"
                PrettyOutput.print(error_msg, OutputType.ERROR)
                raise Exception(error_msg)
            
            data = response.json()
            if data['code'] != 200 or data['type'] != 'success':
                error_msg = f"聊天失败: {data.get('message', '未知错误')}"
                PrettyOutput.print(error_msg, OutputType.ERROR)
                raise Exception(error_msg)
            
            message_id = data['result'][-1]
            
            # 获取响应内容
            response = requests.post(
                f"{self.BASE_URL}/chatapi/chat/message/{message_id}",
                headers=headers
            )
            
            if response.status_code == 200:
                PrettyOutput.print(response.text, OutputType.SYSTEM)
                self.messages.append({"role": "assistant", "content": response.text})
                return response.text
            else:
                error_msg = f"获取响应失败: {response.status_code}"
                PrettyOutput.print(error_msg, OutputType.ERROR)
                raise Exception(error_msg)
            
        except Exception as e:
            PrettyOutput.print(f"聊天异常: {str(e)}", OutputType.ERROR)
            raise e
            
    def name(self) -> str:
        """Return model name"""
        return self.model_name
        
    def reset(self):
        """Reset model state"""
        self.messages = []
        self.conversation = None
        self.upload_files = []
        self.first_chat = True
            
    def delete_chat(self) -> bool:
        """Delete current chat session"""
        try:
            if not self.conversation:
                return True
            
            headers = {
                'Authorization': f'Bearer {self.token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json, text/plain, */*',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'Origin': 'https://ai.rcouyi.com',
                'Referer': 'https://ai.rcouyi.com/'
            }
            
            response = requests.post(
                f"{self.BASE_URL}/chatapi/chat/{self.conversation['result']['id']}",
                headers=headers,
                json={}
            )
            
            if response.status_code == 200:
                data = response.json()
                if data['code'] == 200 and data['type'] == 'success':
                    PrettyOutput.print("会话删除成功", OutputType.SUCCESS)
                    self.reset()
                    return True
                else:
                    error_msg = f"删除会话失败: {data.get('message', '未知错误')}"
                    PrettyOutput.print(error_msg, OutputType.ERROR)
                    return False
            else:
                error_msg = f"删除会话请求失败: {response.status_code}"
                PrettyOutput.print(error_msg, OutputType.ERROR)
                return False
            
        except Exception as e:
            PrettyOutput.print(f"删除会话异常: {str(e)}", OutputType.ERROR)
            return False
    
    def upload_file(self, file_path: str) -> Dict:
        """Upload a file to OYI API
        
        Args:
            file_path: Path to the file to upload
            
        Returns:
            Dict: Upload response data
        """
        try:
            headers = {
                'Authorization': f'Bearer {self.token}',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'Accept': '*/*',
                'DNT': '1',
                'Origin': 'https://ai.rcouyi.com',
                'Referer': 'https://ai.rcouyi.com/'
            }
            
            with open(file_path, 'rb') as f:
                files = {
                    'file': (os.path.basename(file_path), f, mimetypes.guess_type(file_path)[0])  # Adjust content-type based on file type
                }
                
                response = requests.post(
                    f"{self.BASE_URL}/chatapi/m_file/uploadfile",
                    headers=headers,
                    files=files
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('code') == 200:
                        PrettyOutput.print("文件上传成功", OutputType.SUCCESS)
                        print(data)
                        self.upload_files.append(data)
                        return data
                    else:
                        PrettyOutput.print(f"文件上传失败: {data.get('message')}", OutputType.ERROR)
                        return None
                else:
                    PrettyOutput.print(f"文件上传失败: {response.status_code}", OutputType.ERROR)
                    return None
                
        except Exception as e:
            PrettyOutput.print(f"文件上传异常: {str(e)}", OutputType.ERROR)
            return None
