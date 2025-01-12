from typing import Dict, List, Optional
import requests
import json
import os
import mimetypes
from .base import BaseModel
from ..utils import PrettyOutput, OutputType
import time

class KimiModel(BaseModel):
    """Kimi模型实现"""
    
    def __init__(self, api_key: str = None):
        """
        初始化Kimi模型
        Args:
            api_key: Kimi API密钥，如果不提供则从环境变量获取
        """
        self.api_key = api_key or os.getenv("KIMI_API_KEY")
        if not self.api_key:
            raise Exception("KIMI_API_KEY is not set")
        self.auth_header = f"Bearer {self.api_key}"
        self.chat_id = ""
        self.uploaded_files = []  # 存储已上传文件的信息
        self.first_chat = True  # 添加标记，用于判断是否是第一次对话

    def _create_chat(self) -> bool:
        """创建新的对话会话"""
        url = "https://kimi.moonshot.cn/api/chat"
        payload = json.dumps({
            "name": "未命名会话",
            "is_example": False,
            "kimiplus_id": "kimi"
        })
        headers = {
            'Authorization': self.auth_header,
            'Content-Type': 'application/json'
        }
        try:
            response = requests.request("POST", url, headers=headers, data=payload)
            self.chat_id = response.json()["id"]
            return True
        except Exception as e:
            PrettyOutput.print(f"Failed to create chat: {e}", OutputType.ERROR)
            return False

    def _get_presigned_url(self, filename: str) -> Dict:
        """获取预签名上传URL"""
        url = "https://kimi.moonshot.cn/api/pre-sign-url"
        mime_type, _ = mimetypes.guess_type(filename)
        action = "image" if mime_type and mime_type.startswith('image/') else "file"
        
        payload = json.dumps({
            "action": action,
            "name": os.path.basename(filename)
        })
        
        headers = {
            'Authorization': self.auth_header,
            'Content-Type': 'application/json'
        }
        
        response = requests.post(url, headers=headers, data=payload)
        return response.json()

    def _upload_file(self, file_path: str, presigned_url: str) -> bool:
        """上传文件到预签名URL"""
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
                response = requests.put(presigned_url, data=content)
                return response.status_code == 200
        except Exception as e:
            PrettyOutput.print(f"Failed to upload file: {e}", OutputType.ERROR)
            return False

    def _get_file_info(self, file_data: Dict, name: str) -> Dict:
        """获取文件信息"""
        url = "https://kimi.moonshot.cn/api/file"
        payload = json.dumps({
            "type": "file",
            "name": name,
            "object_name": file_data["object_name"],
            "chat_id": self.chat_id,
            "file_id": file_data.get("file_id", "")
        })
        
        headers = {
            'Authorization': self.auth_header,
            'Content-Type': 'application/json'
        }
        
        response = requests.post(url, headers=headers, data=payload)
        return response.json()

    def _wait_for_parse(self, file_id: str) -> bool:
        """等待文件解析完成"""
        url = "https://kimi.moonshot.cn/api/file/parse_process"
        headers = {
            'Authorization': self.auth_header,
            'Content-Type': 'application/json'
        }
        
        max_retries = 30
        retry_count = 0
        
        while retry_count < max_retries:
            payload = json.dumps({"ids": [file_id]})
            response = requests.post(url, headers=headers, data=payload, stream=True)
            
            for line in response.iter_lines():
                if not line:
                    continue
                    
                line = line.decode('utf-8')
                if not line.startswith("data: "):
                    continue
                    
                try:
                    data = json.loads(line[6:])
                    if data.get("event") == "resp":
                        status = data.get("file_info", {}).get("status")
                        if status == "parsed":
                            return True
                        elif status == "failed":
                            return False
                except json.JSONDecodeError:
                    continue
            
            retry_count += 1
            time.sleep(1)
        
        return False

    def upload_files(self, file_list: List[str]) -> List[Dict]:
        """上传文件列表并返回文件信息"""
        if not file_list:
            return []

        PrettyOutput.print("开始处理文件上传...", OutputType.PROGRESS)
        
        if not self.chat_id:
            PrettyOutput.print("创建新的对话会话...", OutputType.PROGRESS)
            if not self._create_chat():
                raise Exception("Failed to create chat session")

        uploaded_files = []
        for index, file_path in enumerate(file_list, 1):
            try:
                PrettyOutput.print(f"处理文件 [{index}/{len(file_list)}]: {file_path}", OutputType.PROGRESS)
                
                # 获取预签名URL
                PrettyOutput.print("获取上传URL...", OutputType.PROGRESS)
                presigned_data = self._get_presigned_url(file_path)
                
                # 上传文件
                PrettyOutput.print("上传文件内容...", OutputType.PROGRESS)
                if self._upload_file(file_path, presigned_data["url"]):
                    # 获取文件信息
                    PrettyOutput.print("获取文件信息...", OutputType.PROGRESS)
                    file_info = self._get_file_info(presigned_data, os.path.basename(file_path))
                    
                    # 等待文件解析
                    PrettyOutput.print("等待文件解析完成...", OutputType.PROGRESS)
                    if self._wait_for_parse(file_info["id"]):
                        uploaded_files.append(file_info)
                        PrettyOutput.print(f"✓ 文件处理成功: {file_path}", OutputType.SUCCESS)
                    else:
                        PrettyOutput.print(f"✗ 文件解析失败: {file_path}", OutputType.ERROR)
                else:
                    PrettyOutput.print(f"✗ 文件上传失败: {file_path}", OutputType.ERROR)
                    
            except Exception as e:
                PrettyOutput.print(f"✗ 处理文件出错 {file_path}: {str(e)}", OutputType.ERROR)
                continue
        
        if uploaded_files:
            PrettyOutput.print(f"成功处理 {len(uploaded_files)}/{len(file_list)} 个文件", OutputType.SUCCESS)
        else:
            PrettyOutput.print("没有文件成功处理", OutputType.WARNING)
        
        self.uploaded_files = uploaded_files
        return uploaded_files

    def chat(self, message: str) -> str:
        """发送消息并获取响应"""
        if not self.chat_id:
            PrettyOutput.print("创建新的对话会话...", OutputType.PROGRESS)
            if not self._create_chat():
                raise Exception("Failed to create chat session")

        url = f"https://kimi.moonshot.cn/api/chat/{self.chat_id}/completion/stream"
        
        # 只在第一次对话时带上文件引用
        refs = []
        refs_file = []
        if self.first_chat and self.uploaded_files:
            PrettyOutput.print(f"首次对话，引用 {len(self.uploaded_files)} 个文件...", OutputType.PROGRESS)
            refs = [f["id"] for f in self.uploaded_files]
            refs_file = self.uploaded_files
            self.first_chat = False
        
        PrettyOutput.print("发送请求...", OutputType.PROGRESS)
        payload = {
            "messages": [{"role": "user", "content": message}],
            "use_search": True,
            "extend": {"sidebar": True},
            "kimiplus_id": "kimi",
            "use_research": False,
            "use_math": False,
            "refs": refs,
            "refs_file": refs_file
        }

        headers = {
            'Authorization': self.auth_header,
            'Content-Type': 'application/json'
        }

        try:
            response = requests.post(url, headers=headers, json=payload, stream=True)
            full_response = ""
            
            PrettyOutput.print("接收响应...", OutputType.PROGRESS)
            for line in response.iter_lines():
                if not line:
                    continue
                    
                line = line.decode('utf-8')
                if not line.startswith("data: "):
                    continue
                    
                try:
                    data = json.loads(line[6:])
                    if data.get("event") == "cmpl":
                        text = data.get("text", "")
                        if text:
                            PrettyOutput.print_stream(text, OutputType.SYSTEM)
                            full_response += text
                except json.JSONDecodeError:
                    continue
                    
            PrettyOutput.print_stream_end()
            return full_response

        except Exception as e:
            raise Exception(f"Chat failed: {str(e)}")

    def delete_chat(self) -> bool:
        """删除当前会话"""
        if not self.chat_id:
            return True  # 如果没有会话ID，视为删除成功
            
        url = f"https://kimi.moonshot.cn/api/chat/{self.chat_id}"
        headers = {
            'Authorization': self.auth_header,
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.delete(url, headers=headers)
            if response.status_code == 200:
                PrettyOutput.print("会话已删除", OutputType.SUCCESS)
                self.chat_id = ""  # 清除会话ID
                return True
            else:
                PrettyOutput.print(f"删除会话失败: HTTP {response.status_code}", OutputType.ERROR)
                return False
        except Exception as e:
            PrettyOutput.print(f"删除会话时发生错误: {str(e)}", OutputType.ERROR)
            return False

    def reset(self):
        """重置对话"""
        if self.chat_id:
            self.delete_chat()  # 删除现有会话
        self.chat_id = ""
        self.uploaded_files = []
        self.first_chat = True  # 重置first_chat标记


if __name__ == "__main__":
    kimi = KimiModel()
    print(kimi.chat([{"role": "user", "content": "ollama如何部署"}]))