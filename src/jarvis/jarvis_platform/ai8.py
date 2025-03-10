import os
from typing import Dict, List, Tuple
from jarvis.jarvis_platform.base import BasePlatform
import requests
import json
import base64

from jarvis.jarvis_utils.output import OutputType, PrettyOutput

class AI8Model(BasePlatform):
    """AI8 model implementation"""
    
    platform_name = "ai8"
    BASE_URL = "https://ai8.rcouyi.com"

    def get_model_list(self) -> List[Tuple[str, str]]:
        """获取模型列表"""
        self.get_available_models()
        return [(name,info['desc']) for name,info in self.models.items()]
    
    def __init__(self):
        """Initialize model"""
        super().__init__()
        self.system_message = ""
        self.conversation = {}
        self.files = []
        self.models = {}  # 存储模型信息

        self.token = os.getenv("AI8_API_KEY")
        if not self.token:
            PrettyOutput.print("未设置 AI8_API_KEY", OutputType.WARNING)
        
        
        self.model_name = os.getenv("JARVIS_MODEL") or "deepseek-chat"
        if self.model_name not in self.get_available_models():
            PrettyOutput.print(f"警告: 选择的模型 {self.model_name} 不在可用列表中", OutputType.WARNING)
        

    def set_model_name(self, model_name: str):
        """Set model name"""

        self.model_name = model_name
            
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
                PrettyOutput.print(f"创建会话失败: {response.status_code}", OutputType.WARNING)
                return False
            
            data = response.json()
            if data['code'] != 0:
                PrettyOutput.print(f"创建会话失败: {data.get('msg', '未知错误')}", OutputType.WARNING)
                return False
            
            self.conversation = data['data']
            
            # 2. 更新会话设置
            session_data = {
                **self.conversation,
                "model": self.model_name,
                "contextCount": 65536,
                "prompt": self.system_message,
                "plugins": [],
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
                    return True
                else:
                    PrettyOutput.print(f"更新会话设置失败: {data.get('msg', '未知错误')}", OutputType.WARNING)
                    return False
            else:
                PrettyOutput.print(f"更新会话设置失败: {response.status_code}", OutputType.WARNING)
                return False
            
        except Exception as e:
            PrettyOutput.print(f"创建会话失败: {str(e)}", OutputType.ERROR)
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
        return self.files
    
    def set_system_message(self, message: str):
        """Set system message"""
        self.system_message = message
        
    def chat(self, message: str) -> str:
        """Execute conversation"""
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
                "sessionId": self.conversation['id'] if self.conversation else None,
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
                error_msg = f"Failed to chat: {response.status_code} {response.text}"
                PrettyOutput.print(error_msg, OutputType.WARNING)
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
                                    if not self.suppress_output:
                                        PrettyOutput.print_stream(chunk)

                        except json.JSONDecodeError:
                            continue
            
            if not self.suppress_output:
                PrettyOutput.print_stream_end()

            return full_response
            
        except Exception as e:
            PrettyOutput.print(f"对话异常: {str(e)}", OutputType.ERROR)
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
                    self.reset()
                    return True
                else:
                    error_msg = f"删除会话失败: {data.get('msg', '未知错误')}"
                    PrettyOutput.print(error_msg, OutputType.WARNING)
                    return False
            else:
                error_msg = f"删除会话请求失败: {response.status_code}"
                PrettyOutput.print(error_msg, OutputType.WARNING)
                return False
            
        except Exception as e:
            PrettyOutput.print(f"删除会话失败: {str(e)}", OutputType.ERROR)
            return False
        
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
                'X-APP-VERSION': '2.2.2',
                'Origin': self.BASE_URL,
                'Referer': f'{self.BASE_URL}/chat?_userMenuKey=chat'
            }
            
            response = requests.get(
                f"{self.BASE_URL}/api/chat/tmpl",
                headers=headers
            )
            
            if response.status_code != 200:
                PrettyOutput.print(f"获取模型列表失败: {response.status_code}", OutputType.WARNING)
                return []
            
            data = response.json()
            if data['code'] != 0:
                PrettyOutput.print(f"获取模型列表失败: {data.get('msg', '未知错误')}", OutputType.WARNING)
                return []
            
            # 保存模型信息
            self.models = {
                model['value']: model 
                for model in data['data']['models']
            }

            for model in self.models.values():
                # 添加标签
                model_str = f"{model['label']}"
                
                # 添加标签和积分信息
                attrs = []
                if model['attr'].get('tag'):
                    attrs.append(model['attr']['tag'])
                if model['attr'].get('integral'):
                    attrs.append(model['attr']['integral'])
                    
                # 添加特性标记
                features = []
                if model['attr'].get('multimodal'):
                    features.append("Multimodal")
                if model['attr'].get('plugin'):
                    features.append("Plugin support")
                if model['attr'].get('onlyImg'):
                    features.append("Image support")
                if features:
                    model_str += f" [{'|'.join(features)}]"
                    
                # 添加备注
                if model['attr'].get('note'):
                    model_str += f" - {model['attr']['note']}"
                model['desc'] = model_str
            
            return list(self.models.keys())
            
        except Exception as e:
            PrettyOutput.print(f"获取模型列表失败: {str(e)}", OutputType.ERROR)
            return []
        
