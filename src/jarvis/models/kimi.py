from typing import Dict, List, Optional
import requests
import json
import os
import mimetypes
from .base import BaseModel
from ..utils import PrettyOutput, OutputType, while_success
import time

class KimiModel(BaseModel):
    """Kimi模型实现"""
    
    def __init__(self, verbose: bool = False):
        """
        初始化Kimi模型
        Args:
            verbose: 是否显示详细输出
        """
        self.api_key = os.getenv("KIMI_API_KEY")
        if not self.api_key:
            raise Exception("KIMI_API_KEY is not set")
        self.auth_header = f"Bearer {self.api_key}"
        self.chat_id = ""
        self.uploaded_files = []  # 存储已上传文件的信息
        self.first_chat = True  # 添加标记，用于判断是否是第一次对话
        self.verbose = verbose  # 添加verbose属性
        self.system_message = ""

    def set_system_message(self, message: str):
        """设置系统消息"""
        self.system_message = message

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
            response = while_success(lambda: requests.request("POST", url, headers=headers, data=payload), sleep_time=5)
            self.chat_id = response.json()["id"]
            return True
        except Exception as e:
            PrettyOutput.print(f"Failed to create chat: {e}", OutputType.ERROR)
            return False

    def _get_presigned_url(self, filename: str, action: str) -> Dict:
        """获取预签名上传URL"""
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
        """上传文件到预签名URL"""
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
                response = while_success(lambda: requests.put(presigned_url, data=content), sleep_time=5)
                return response.status_code == 200
        except Exception as e:
            PrettyOutput.print(f"Failed to upload file: {e}", OutputType.ERROR)
            return False

    def _get_file_info(self, file_data: Dict, name: str, file_type: str) -> Dict:
        """获取文件信息"""
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
        """等待文件解析完成"""
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
                print(data)
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

                mime_type, _ = mimetypes.guess_type(file_path)
                action = "image" if mime_type and mime_type.startswith('image/') else "file"
                
                # 获取预签名URL
                PrettyOutput.print("获取上传URL...", OutputType.PROGRESS)
                presigned_data = self._get_presigned_url(file_path, action)
                
                # 上传文件
                PrettyOutput.print("上传文件内容...", OutputType.PROGRESS)
                if self._upload_file(file_path, presigned_data["url"]):
                    # 获取文件信息
                    PrettyOutput.print("获取文件信息...", OutputType.PROGRESS)
                    file_info = self._get_file_info(presigned_data, os.path.basename(file_path), action)
                    # 等待文件解析
                    PrettyOutput.print("等待文件解析完成...", OutputType.PROGRESS)

                    # 只有文件需要解析
                    if action == "file":
                        if self._wait_for_parse(file_info["id"]):
                            uploaded_files.append(file_info)
                            PrettyOutput.print(f"✓ 文件处理成功: {file_path}", OutputType.SUCCESS)
                        else:
                            PrettyOutput.print(f"✗ 文件解析失败: {file_path}", OutputType.ERROR)
                    else:
                        uploaded_files.append(file_info)
                        PrettyOutput.print(f"✓ 文件处理成功: {file_path}", OutputType.SUCCESS)
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
        if self.first_chat:
            if self.uploaded_files:
                PrettyOutput.print(f"首次对话，引用 {len(self.uploaded_files)} 个文件...", OutputType.PROGRESS)
                refs = [f["id"] for f in self.uploaded_files]
                refs_file = self.uploaded_files
            message = self.system_message + "\n" + message
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
            response = while_success(lambda: requests.post(url, headers=headers, json=payload, stream=True), sleep_time=5)
            full_response = ""
            
            # 收集搜索和引用结果
            search_results = []
            ref_sources = []
            
            PrettyOutput.print("接收响应...", OutputType.PROGRESS)
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
                            PrettyOutput.print_stream(text, OutputType.SYSTEM)
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
                    
            PrettyOutput.print_stream_end()
            
            # 只在verbose模式下显示搜索和引用信息
            if self.verbose:
                # 显示搜索结果摘要
                if search_results:
                    PrettyOutput.print("\n搜索结果:", OutputType.INFO)
                    for result in search_results:
                        PrettyOutput.print(f"- {result['title']}", OutputType.INFO)
                        if result['date']:
                            PrettyOutput.print(f"  日期: {result['date']}", OutputType.INFO)
                        PrettyOutput.print(f"  来源: {result['site_name']}", OutputType.INFO)
                        if result['snippet']:
                            PrettyOutput.print(f"  摘要: {result['snippet']}", OutputType.INFO)
                        PrettyOutput.print(f"  链接: {result['url']}", OutputType.INFO)
                        PrettyOutput.print("", OutputType.INFO)
                        
                # 显示引用来源
                if ref_sources:
                    PrettyOutput.print("\n引用来源:", OutputType.INFO)
                    for source in ref_sources:
                        PrettyOutput.print(f"- [{source['ref_id']}] {source['title']} ({source['source']})", OutputType.INFO)
                        PrettyOutput.print(f"  链接: {source['url']}", OutputType.INFO)
                        if source['abstract']:
                            PrettyOutput.print(f"  摘要: {source['abstract']}", OutputType.INFO)
                        
                        # 显示相关段落
                        if source['rag_segments']:
                            PrettyOutput.print("  相关段落:", OutputType.INFO)
                            for segment in source['rag_segments']:
                                text = segment.get('text', '').replace('\n', ' ').strip()
                                if text:
                                    PrettyOutput.print(f"    - {text}", OutputType.INFO)
                        
                        # 显示原文引用
                        origin = source['origin']
                        if origin:
                            text = origin.get('text', '')
                            if text:
                                PrettyOutput.print(f"  原文: {text}", OutputType.INFO)
                        
                        PrettyOutput.print("", OutputType.INFO)
            
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
            response = while_success(lambda: requests.delete(url, headers=headers), sleep_time=5)
            if response.status_code == 200:
                PrettyOutput.print("会话已删除", OutputType.SUCCESS)
                self.reset()
                return True
            else:
                PrettyOutput.print(f"删除会话失败: HTTP {response.status_code}", OutputType.ERROR)
                return False
        except Exception as e:
            PrettyOutput.print(f"删除会话时发生错误: {str(e)}", OutputType.ERROR)
            return False

    def reset(self):
        """重置对话"""
        self.chat_id = ""
        self.uploaded_files = []
        self.first_chat = True  # 重置first_chat标记

    def name(self) -> str:
        """模型名称"""
        return "kimi"

if __name__ == "__main__":
    kimi = KimiModel()
    print(kimi.chat([{"role": "user", "content": "ollama如何部署"}]))