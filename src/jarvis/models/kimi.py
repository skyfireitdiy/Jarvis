from typing import Dict, List, Tuple
import requests
import json
import os
import mimetypes
import time
from jarvis.models.base import BasePlatform
from jarvis.utils import PrettyOutput, OutputType
from jarvis.utils import while_success

class KimiModel(BasePlatform):
    """Kimi model implementation"""

    platform_name = "kimi"

    def get_model_list(self) -> List[Tuple[str, str]]:
        """Get model list"""
        return [("kimi", "Based on the web Kimi, free interface")]
    
    def __init__(self):
        """
        Initialize Kimi model
        """
        super().__init__()
        self.chat_id = ""
        self.api_key = os.getenv("KIMI_API_KEY")
        if not self.api_key:
            PrettyOutput.print("\nNeed to set KIMI_API_KEY to use Jarvis. Please follow the steps below:", OutputType.INFO)
            PrettyOutput.print("\n1. Get Kimi API Key:", OutputType.INFO)
            PrettyOutput.print("   • Visit Kimi AI platform: https://kimi.moonshot.cn", OutputType.INFO)
            PrettyOutput.print("   • Login to your account", OutputType.INFO)
            PrettyOutput.print("   • Open browser developer tools (F12 or right-click -> Inspect)", OutputType.INFO)
            PrettyOutput.print("   • Switch to the Network tab", OutputType.INFO)
            PrettyOutput.print("   • Send any message", OutputType.INFO)
            PrettyOutput.print("   • Find the Authorization header in the request", OutputType.INFO)
            PrettyOutput.print("   • Copy the token value (remove the 'Bearer ' prefix)", OutputType.INFO)
            PrettyOutput.print("\n2. Set environment variable:", OutputType.INFO)
            PrettyOutput.print("   • Method 1: Create or edit ~/.jarvis_env file:", OutputType.INFO)
            PrettyOutput.print("   echo 'KIMI_API_KEY=your_key_here' > ~/.jarvis_env", OutputType.INFO)
            PrettyOutput.print("\n   • Method 2: Set environment variable directly:", OutputType.INFO)
            PrettyOutput.print("   export KIMI_API_KEY=your_key_here", OutputType.INFO)
            PrettyOutput.print("\nAfter setting, run Jarvis again.", OutputType.INFO)
            PrettyOutput.print("KIMI_API_KEY is not set", OutputType.WARNING)
        self.auth_header = f"Bearer {self.api_key}"
        self.chat_id = ""
        self.uploaded_files = []  # 存储已上传文件的信息
        self.first_chat = True  # 添加标记，用于判断是否是第一次对话
        self.system_message = ""

    def set_system_message(self, message: str):
        """Set system message"""
        self.system_message = message

    def set_model_name(self, model_name: str):
        """Set model name"""
        pass

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
            self.chat_id = response.json()["id"]
            return True
        except Exception as e:
            PrettyOutput.print(f"Error: Failed to create chat: {e}", OutputType.ERROR)
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

    def _upload_file(self, file_path: str, presigned_url: str) -> bool:
        """Upload file to presigned URL"""
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
                response = while_success(lambda: requests.put(presigned_url, data=content), sleep_time=5)
                return response.status_code == 200
        except Exception as e:
            PrettyOutput.print(f"Error: Failed to upload file: {e}", OutputType.ERROR)
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
    def upload_files(self, file_list: List[str]) -> List[Dict]:
        """Upload file list and return file information"""
        if not file_list:
            return []

        
        if not self.chat_id:
            if not self._create_chat():
                raise Exception("Failed to create chat session")

        uploaded_files = []
        for index, file_path in enumerate(file_list, 1):
            try:
                PrettyOutput.print(f"处理文件 [{index}/{len(file_list)}]: {file_path}", OutputType.PROGRESS)

                mime_type, _ = mimetypes.guess_type(file_path)
                action = "image" if mime_type and mime_type.startswith('image/') else "file"
                
                # 获取预签名URL
                presigned_data = self._get_presigned_url(file_path, action)
                
                # 上传文件
                if self._upload_file(file_path, presigned_data["url"]):
                    # 获取文件信息
                    file_info = self._get_file_info(presigned_data, os.path.basename(file_path), action)
                    file_info = self._get_file_info(presigned_data, os.path.basename(file_path), action)
                    # 等待文件解析

                    # 只有文件需要解析
                    if action == "file":
                        if self._wait_for_parse(file_info["id"]):
                            uploaded_files.append(file_info)
                        else:
                            PrettyOutput.print(f"✗ 文件解析失败: {file_path}", OutputType.ERROR)
                    else:
                        uploaded_files.append(file_info)
                else:
                    PrettyOutput.print(f"Error: 文件上传失败: {file_path}", OutputType.ERROR)
                    
            except Exception as e:
                PrettyOutput.print(f"✗ 处理文件出错 {file_path}: {str(e)}", OutputType.ERROR)
                continue
        
        self.uploaded_files = uploaded_files
        return uploaded_files

    def chat(self, message: str) -> str:
        """Send message and get response"""
        if not self.chat_id:
            if not self._create_chat():
                raise Exception("Failed to create chat session")

        url = f"https://kimi.moonshot.cn/api/chat/{self.chat_id}/completion/stream"
        
        # 只在第一次对话时带上文件引用
        refs = []
        refs_file = []
        if self.first_chat:
            if self.uploaded_files:
                refs = [f["id"] for f in self.uploaded_files]
                refs_file = self.uploaded_files
            message = self.system_message + "\n" + message
            self.first_chat = False
        
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
            response = while_success(lambda: requests.post(url, headers=headers, json=payload, stream=True), sleep_time=5)
            full_response = ""
            
            # 收集搜索和引用结果
            search_results = []
            ref_sources = []
            
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
                            if not self.suppress_output:
                                PrettyOutput.print_stream(text)
                            full_response += text
                            
                    elif event == "search_plus":
                        # 收集搜索结果
                        msg = data.get("msg", {})
                        if msg.get("type") == "get_res":
                            search_results.append({
                                "date": msg.get("date", ""),
                                "site_name": msg.get("site_name", ""),
                                "snippet": msg.get("snippet", ""),
                                "title": msg.get("title", ""),
                                "type": msg.get("type", ""),
                                "url": msg.get("url", "")
                            })
                                
                    elif event == "ref_docs":
                        # 收集引用来源
                        ref_cards = data.get("ref_cards", [])
                        for card in ref_cards:
                            ref_sources.append({
                                "idx_s": card.get("idx_s", ""),
                                "idx_z": card.get("idx_z", ""),
                                "ref_id": card.get("ref_id", ""),
                                "url": card.get("url", ""),
                                "title": card.get("title", ""),
                                "abstract": card.get("abstract", ""),
                                "source": card.get("source_label", ""),
                                "rag_segments": card.get("rag_segments", []),
                                "origin": card.get("origin", {})
                            })
                                    
                except json.JSONDecodeError:
                    continue
                    
            if not self.suppress_output:
                PrettyOutput.print_stream_end()
            

            # 显示搜索结果摘要
            if search_results and not self.suppress_output:
                PrettyOutput.print("\n搜索结果:", OutputType.PROGRESS)
                for result in search_results:
                    PrettyOutput.print(f"- {result['title']}", OutputType.PROGRESS)
                    if result['date']:
                        PrettyOutput.print(f"  日期: {result['date']}", OutputType.PROGRESS)
                    PrettyOutput.print(f"  来源: {result['site_name']}", OutputType.PROGRESS)
                    if result['snippet']:
                        PrettyOutput.print(f"  摘要: {result['snippet']}", OutputType.PROGRESS)
                    PrettyOutput.print(f"  链接: {result['url']}", OutputType.PROGRESS)
                    PrettyOutput.print("", OutputType.PROGRESS)
                        
            # 显示引用来源
            if ref_sources and not self.suppress_output:
                PrettyOutput.print("\n引用来源:", OutputType.PROGRESS)
                for source in ref_sources:
                    PrettyOutput.print(f"- [{source['ref_id']}] {source['title']} ({source['source']})", OutputType.PROGRESS)
                    PrettyOutput.print(f"  链接: {source['url']}", OutputType.PROGRESS)
                    if source['abstract']:
                        PrettyOutput.print(f"  摘要: {source['abstract']}", OutputType.PROGRESS)
                    
                    # 显示相关段落
                    if source['rag_segments']:
                        PrettyOutput.print("  相关段落:", OutputType.PROGRESS)
                        for segment in source['rag_segments']:
                            text = segment.get('text', '').replace('\n', ' ').strip()
                            if text:
                                PrettyOutput.print(f"    - {text}", OutputType.PROGRESS)
                    
                    # 显示原文引用
                    origin = source['origin']
                    if origin:
                        text = origin.get('text', '')
                        if text:
                            PrettyOutput.print(f"  原文: {text}", OutputType.PROGRESS)
                    
                    PrettyOutput.print("", OutputType.PROGRESS)

            PrettyOutput.print(full_response, OutputType.RESULT)
            
            return full_response

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
                self.reset()
                return True
            else:
                PrettyOutput.print(f"删除会话失败: HTTP {response.status_code}", OutputType.ERROR)
                return False
        except Exception as e:
            PrettyOutput.print(f"删除会话时发生错误: {str(e)}", OutputType.ERROR)
            return False

    def reset(self):
        """Reset chat"""
        self.chat_id = ""
        self.uploaded_files = []
        self.first_chat = True  # 重置first_chat标记

    def name(self) -> str:
        """Model name"""
        return "kimi"
