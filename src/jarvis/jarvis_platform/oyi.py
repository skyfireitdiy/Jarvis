import mimetypes
import os
from typing import Dict, List, Tuple
from jarvis.jarvis_platform.base import BasePlatform
import requests
import json

from jarvis.jarvis_utils.output import OutputType, PrettyOutput

class OyiModel(BasePlatform):
    """Oyi model implementation"""
    
    platform_name = "oyi"
    BASE_URL = "https://api-10086.rcouyi.com"

    def get_model_list(self) -> List[Tuple[str, str]]:
        """Get model list"""
        self.get_available_models()
        return [(name,info['desc']) for name,info in self.models.items()]
    
    def __init__(self):
        """Initialize model"""
        super().__init__()
        self.models = {}        
        self.messages = []
        self.system_message = ""
        self.conversation = None
        self.files = []
        self.first_chat = True
        
        self.token = os.getenv("OYI_API_KEY")
        if not self.token:
            PrettyOutput.print("OYI_API_KEY 未设置", OutputType.WARNING)
        
        self.model_name = os.getenv("JARVIS_MODEL") or "deepseek-chat"
        if self.model_name not in [m.split()[0] for m in self.get_available_models()]:
            PrettyOutput.print(f"警告: 选择的模型 {self.model_name} 不在可用列表中", OutputType.WARNING)
        

    def set_model_name(self, model_name: str):
        """Set model name"""

        self.model_name = model_name

        
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
                "title": "New conversation",
                "isLock": False,
                "systemMessage": "",
                "params": json.dumps({
                    "model": self.model_name,
                    "is_webSearch": True,
                    "message": [],
                    "systemMessage": None,
                    "requestMsgCount": 65536,
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
                    return True
                else:
                    PrettyOutput.print(f"创建会话失败: {data['message']}", OutputType.WARNING)
                    return False
            else:
                PrettyOutput.print(f"创建会话失败: {response.status_code}", OutputType.WARNING)
                return False
                
        except Exception as e:
            PrettyOutput.print(f"创建会话失败: {str(e)}", OutputType.ERROR)
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
                "topicId": self.conversation['result']['id'] if self.conversation else None,
                "messages": self.messages,
                "content": message,
                "contentFiles": []
            }
            
            # 如果有上传的文件，添加到请求中
            if self.first_chat:
                if self.files:
                    for file_data in self.files:
                        file_info = {
                            "contentType": 1,  # 1 表示图片
                            "fileUrl": file_data['result']['url'],
                            "fileId": file_data['result']['id'],
                            "fileName": file_data['result']['fileName']
                        }
                        payload["contentFiles"].append(file_info)
                    # 清空已使用的文件列表
                    self.files = []
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
                PrettyOutput.print(error_msg, OutputType.WARNING)
                raise Exception(error_msg)
            
            data = response.json()
            if data['code'] != 200 or data['type'] != 'success':
                error_msg = f"聊天失败: {data.get('message', '未知错误')}"
                PrettyOutput.print(error_msg, OutputType.WARNING)
                raise Exception(error_msg)
            
            message_id = data['result'][-1]
            
            # 获取响应内容
            response = requests.post(
                f"{self.BASE_URL}/chatapi/chat/message/{message_id}",
                headers=headers,
                stream=True
            )
            
            if response.status_code == 200:
                full_response = ""
                bin = b""
                for chunk in response.iter_content(decode_unicode=True):
                    if chunk:
                        bin += chunk
                        try:
                            text = bin.decode('utf-8')
                        except UnicodeDecodeError:
                            continue
                        if not self.suppress_output:
                            PrettyOutput.print_stream(text)
                        full_response += text
                        bin = b""

                PrettyOutput.print_stream_end()
                
                self.messages.append({"role": "assistant", "content": full_response})
                return full_response
            else:
                error_msg = f"获取响应失败: {response.status_code}"
                PrettyOutput.print(error_msg, OutputType.WARNING)
                raise Exception(error_msg)
        except Exception as e:
            PrettyOutput.print(f"聊天失败: {str(e)}", OutputType.ERROR)
            raise e
            
    def name(self) -> str:
        """Return model name"""
        return self.model_name
        
    def reset(self):
        """Reset model state"""
        self.messages = []
        self.conversation = None
        self.files = []
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
                    self.reset()
                    return True
                else:
                    error_msg = f"删除会话失败: {data.get('message', '未知错误')}"
                    PrettyOutput.print(error_msg, OutputType.WARNING)
                    return False
            else:
                error_msg = f"删除会话请求失败: {response.status_code}"
                PrettyOutput.print(error_msg, OutputType.WARNING)
                return False
            
        except Exception as e:
            PrettyOutput.print(f"删除会话失败: {str(e)}", OutputType.ERROR)
            return False
    
    def upload_files(self, file_list: List[str]) -> List[Dict]:
        """Upload a file to OYI API
        
        Args:
            file_path: Path to the file to upload
            
        Returns:
            Dict: Upload response data
        """
        try:
            # 检查当前模型是否支持文件上传
            model_info = self.models.get(self.model_name)
            if not model_info or not model_info.get('uploadFile', False):
                PrettyOutput.print(f"当前模型 {self.model_name} 不支持文件上传", OutputType.WARNING)
                return []
            
            headers = {
                'Authorization': f'Bearer {self.token}',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'Accept': '*/*',
                'DNT': '1',
                'Origin': 'https://ai.rcouyi.com',
                'Referer': 'https://ai.rcouyi.com/'
            }
            
            for file_path in file_list:
                # 检查文件类型
                file_type = mimetypes.guess_type(file_path)[0]
                if not file_type or not file_type.startswith(('image/', 'text/', 'application/')):
                    PrettyOutput.print(f"文件类型 {file_type} 不支持", OutputType.WARNING)
                    continue
                
                with open(file_path, 'rb') as f:
                    files = {
                        'file': (os.path.basename(file_path), f, file_type)
                    }
                
                    response = requests.post(
                        f"{self.BASE_URL}/chatapi/m_file/uploadfile",
                        headers=headers,
                        files=files
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        if data.get('code') == 200:
                            self.files.append(data)
                        else:
                            PrettyOutput.print(f"文件上传失败: {data.get('message')}", OutputType.WARNING)
                            return []
                    else:
                        PrettyOutput.print(f"文件上传失败: {response.status_code}", OutputType.WARNING)
                        return []
                
            return self.files
        except Exception as e:
            PrettyOutput.print(f"文件上传失败: {str(e)}", OutputType.ERROR)
            return []

    def get_available_models(self) -> List[str]:
        """Get available model list
        
        Returns:
            List[str]: Available model name list
        """
        try:
            if self.models:
                return list(self.models.keys())
            
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json, text/plain, */*',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'Origin': 'https://ai.rcouyi.com',
                'Referer': 'https://ai.rcouyi.com/'
            }
            
            response = requests.get(
                "https://ai.rcouyi.com/config/system.json",
                headers=headers
            )
            
            if response.status_code != 200:
                PrettyOutput.print(f"获取模型列表失败: {response.status_code}", OutputType.WARNING)
                return []
            
            data = response.json()
            
            # 保存模型信息
            self.models = {
                model['value']: model
                for model in data.get('model', [])
                if model.get('enable', False)  # 只保存启用的模型
            }
            
            # 格式化显示
            models = []
            for model in self.models.values():
                # 基本信息
                model_name = model['value']
                model_str = model['label']
                
                # 添加后缀标签
                suffix = model.get('suffix', [])
                if suffix:
                    # 处理新格式的suffix (字典列表)
                    if suffix and isinstance(suffix[0], dict):
                        suffix_str = ', '.join(s.get('tag', '') for s in suffix)
                    # 处理旧格式的suffix (字符串列表)
                    else:
                        suffix_str = ', '.join(str(s) for s in suffix)
                    model_str += f" ({suffix_str})"
                    
                # 添加描述或提示
                info = model.get('tooltip') or model.get('description', '')
                if info:
                    model_str += f" - {info}"
                    
                # 添加文件上传支持标记
                if model.get('uploadFile'):
                    model_str += " [Support file upload]"
                model['desc'] = model_str
                models.append(model_name)
                
            return sorted(models)
            
        except Exception as e:
            PrettyOutput.print(f"获取模型列表失败: {str(e)}", OutputType.WARNING)
            return []
