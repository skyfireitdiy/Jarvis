# -*- coding: utf-8 -*-
import json
import mimetypes
import os
import time
from typing import Dict, Generator, List, Tuple

import requests  # type: ignore

from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import while_success


class KimiModel(BasePlatform):
    """Kimi model implementation"""

    platform_name = "kimi"

    def get_model_list(self) -> List[Tuple[str, str]]:
        """Get model list"""
        return [
            ("kimi", "基于网页的 Kimi，免费接口"),
            ("k1", "基于网页的 Kimi，深度思考模型")
            ]

    def __init__(self):
        """
        Initialize Kimi model
        """
        super().__init__()
        self.chat_id = ""
        self.api_key = os.getenv("KIMI_API_KEY")
        if not self.api_key:
            PrettyOutput.print("KIMI_API_KEY 未设置", OutputType.WARNING)
        self.auth_header = f"Bearer {self.api_key}"
        self.uploaded_files = []  # 存储已上传文件的信息
        self.chat_id = ""
        self.first_chat = True  # 添加标记，用于判断是否是第一次对话
        self.system_message = ""
        self.model_name = "kimi"

    def set_system_prompt(self, message: str):
        """Set system message"""
        self.system_message = message

    def set_model_name(self, model_name: str):
        """Set model name"""
        self.model_name = model_name

    def _create_chat(self) -> bool:
        """Create a new chat session"""
        url = "https://kimi.moonshot.cn/api/chat"
        payload = json.dumps({
            "name": "Unnamed session",
            "is_example": False,
            "kimiplus_id": "kimi"
        })
        headers = {
            'Authorization': self.auth_header,
            'Content-Type': 'application/json'
        }
        try:
            response = while_success(lambda: requests.request("POST", url, headers=headers, data=payload), sleep_time=5)
            if response.status_code != 200:
                PrettyOutput.print(f"错误：创建会话失败：{response.json()}", OutputType.ERROR)
                return False
            self.chat_id = response.json()["id"]
            return True
        except Exception as e:
            PrettyOutput.print(f"错误：创建会话失败：{e}", OutputType.ERROR)
            return False
        
    def _get_presigned_url(self, filename: str, action: str) -> Dict:
        """Get presigned upload URL"""
        url = "https://kimi.moonshot.cn/api/pre-sign-url"
        
        
        
        payload = json.dumps({
            "action": action,
            "name": os.path.basename(filename)
        }, ensure_ascii=False)
        
        headers = {
            'Authorization': self.auth_header,
            'Content-Type': 'application/json'
        }
        
        response = while_success(lambda: requests.post(url, headers=headers, data=payload), sleep_time=5)
        return response.json()
    
    def support_upload_files(self) -> bool:
        """Check if platform supports upload files"""
        return True

    def _upload_file(self, file_path: str, presigned_url: str) -> bool:
        """Upload file to presigned URL"""
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
                response = while_success(lambda: requests.put(presigned_url, data=content), sleep_time=5)
                return response.status_code == 200
        except Exception as e:
            PrettyOutput.print(f"错误：上传文件失败：{e}", OutputType.ERROR)
            return False

    def _get_file_info(self, file_data: Dict, name: str, file_type: str) -> Dict:
        """Get file information"""
        url = "https://kimi.moonshot.cn/api/file"
        payload = json.dumps({
            "type": file_type,
            "name": name,
            "object_name": file_data["object_name"],
            "chat_id": self.chat_id,
            "file_id": file_data.get("file_id", "")
        }, ensure_ascii=False)
        
        headers = {
            'Authorization': self.auth_header,
            'Content-Type': 'application/json'
        }
        
        response = while_success(lambda: requests.post(url, headers=headers, data=payload), sleep_time=5)
        return response.json()

    def _wait_for_parse(self, file_id: str) -> bool:
        """Wait for file parsing to complete"""
        url = "https://kimi.moonshot.cn/api/file/parse_process"
        headers = {
            'Authorization': self.auth_header,
            'Content-Type': 'application/json'
        }
        
        max_retries = 30
        retry_count = 0
        
        while retry_count < max_retries:
            payload = json.dumps({"ids": [file_id]}, ensure_ascii=False)
            response = while_success(lambda: requests.post(url, headers=headers, data=payload, stream=True), sleep_time=5)
            
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
    def upload_files(self, file_list: List[str]) -> bool:
        """Upload file list and return file information"""
        if not file_list:
            return True

        from yaspin import yaspin  # type: ignore
        
        if not self.chat_id:
            with yaspin(text="创建聊天会话...", color="yellow") as spinner:
                if not self._create_chat():
                    yaspin.text = "创建聊天会话失败"
                    spinner.fail("❌")
                    return False
                spinner.text = "创建聊天会话成功"
                spinner.ok("✅")

        uploaded_files = []
        for index, file_path in enumerate(file_list, 1):
            file_name = os.path.basename(file_path)
            with yaspin(text=f"处理文件 [{index}/{len(file_list)}]: {file_name}", color="yellow") as spinner:
                try:
                    mime_type, _ = mimetypes.guess_type(file_path)
                    action = "image" if mime_type and mime_type.startswith('image/') else "file"
                    
                    # 获取预签名URL
                    spinner.text = f"获取上传URL: {file_name}"
                    presigned_data = self._get_presigned_url(file_path, action)
                    
                    # 上传文件
                    spinner.text = f"上传文件: {file_name}"
                    if self._upload_file(file_path, presigned_data["url"]):
                        # 获取文件信息
                        spinner.text = f"获取文件信息: {file_name}"
                        file_info = self._get_file_info(presigned_data, file_name, action)
                        
                        # 只有文件需要解析
                        if action == "file":
                            spinner.text = f"等待文件解析: {file_name}"
                            if self._wait_for_parse(file_info["id"]):
                                uploaded_files.append(file_info)
                                spinner.text = f"文件处理完成: {file_name}"
                                spinner.ok("✅")
                            else:
                                spinner.text = f"❌文件解析失败: {file_name}"
                                spinner.fail("")
                                return False
                        else:
                            uploaded_files.append(file_info)
                            spinner.write( f"✅图片处理完成: {file_name}")
                    else:
                        spinner.text = f"文件上传失败: {file_name}"
                        spinner.fail("❌")
                        return False
                    
                except Exception as e:
                    spinner.text = f"处理文件出错 {file_path}: {str(e)}"
                    spinner.fail("❌")
                    return False
        
        self.uploaded_files = uploaded_files
        return True


    def chat(self, message: str) -> Generator[str, None, None]:
        """Send message and get response"""
        if not self.chat_id:
            if not self._create_chat():
                raise Exception("Failed to create chat session")

        url = f"https://kimi.moonshot.cn/api/chat/{self.chat_id}/completion/stream"

        refs = []
        refs_file = []
        if self.uploaded_files:
            refs = [f["id"] for f in self.uploaded_files]
            refs_file = self.uploaded_files
            self.uploaded_files = []

        if self.first_chat:
            message = self.system_message + "\n" + message
            self.first_chat = False

        payload = {
            "messages": [{"role": "user", "content": message}],
            "use_search": True if self.web else False,
            "extend": {"sidebar": True},
            "kimiplus_id": "kimi",
            "use_research": False,
            "use_math": False,
            "refs": refs,
            "refs_file": refs_file,
            "model": self.model_name,
        }

        headers = {
            'Authorization': self.auth_header,
            'Content-Type': 'application/json'
        }

        try:
            response = while_success(lambda: requests.post(url, headers=headers, json=payload, stream=True), sleep_time=5)
            # 如果禁止输出，则静默处理
            for line in response.iter_lines():
                if not line:
                    continue

                line = line.decode('utf-8')
                if not line.startswith("data: "):
                    continue

                try:
                    data = json.loads(line[6:])
                    event = data.get("event")

                    if event == "cmpl":
                        # 处理补全文本
                        text = data.get("text", "")
                        if text:
                            yield text
                except json.JSONDecodeError:
                    continue


            return None

        except Exception as e:
            raise Exception(f"Chat failed: {str(e)}")

    def delete_chat(self) -> bool:
        """Delete current session"""
        if not self.chat_id:
            return True  # 如果没有会话ID，视为删除成功

        url = f"https://kimi.moonshot.cn/api/chat/{self.chat_id}"
        headers = {
            'Authorization': self.auth_header,
            'Content-Type': 'application/json'
        }

        try:
            response = while_success(lambda: requests.delete(url, headers=headers), sleep_time=5)
            if response.status_code == 200:
                self.chat_id = ""
                self.uploaded_files = []
                self.first_chat = True  # 重置first_chat标记
                return True
            else:
                PrettyOutput.print(f"删除会话失败: HTTP {response.status_code}", OutputType.WARNING)
                return False
        except Exception as e:
            PrettyOutput.print(f"删除会话时发生错误: {str(e)}", OutputType.ERROR)
            return False


    def name(self) -> str:
        """Model name"""
        return self.model_name

    def support_web(self) -> bool:
        """Kimi平台支持web功能"""
        return True
