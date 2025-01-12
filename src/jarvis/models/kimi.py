from typing import Dict, List
import requests
import json
import os
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

    def chat(self, messages: List[Dict]) -> str:
        """
        实现BaseModel的chat方法
        Args:
            messages: 对话消息列表
        Returns:
            str: 模型的回复内容
        """
        if not self.chat_id:
            if not self._create_chat():
                raise Exception("Failed to create chat")
        
        url = f"https://kimi.moonshot.cn/api/chat/{self.chat_id}/completion/stream"
        payload = json.dumps({
            "messages": [messages[-1]],
            "use_search": True,
            "extend": {
                "sidebar": True
            },
            "kimiplus_id": "kimi",
            "use_research": False,
            "use_math": False,
            "refs": [],
            "refs_file": []
        })
        headers = {
            'Authorization': self.auth_header,
            'Content-Type': 'application/json'
        }

        try:
            response = requests.request("POST", url, headers=headers, data=payload, stream=True)
            full_response = ""
            references = []
            
            for line in response.iter_lines():
                if not line:
                    continue
                
                line = line.decode('utf-8')
                if not line.startswith("data: "):
                    continue
                
                try:
                    data = json.loads(line[6:])  # 去掉 "data: " 前缀
                    
                    # 处理不同类型的事件
                    if data.get("event") == "cmpl":
                        if "text" in data:
                            text = data["text"]
                            PrettyOutput.print_stream(text, OutputType.SYSTEM)  # 使用统一的流式输出
                            full_response += text
                    elif data.get("event") == "ref_docs":
                        if "ref_cards" in data:
                            for ref in data["ref_cards"]:
                                reference = {
                                    "title": ref.get("title", ""),
                                    "url": ref.get("url", ""),
                                    "abstract": ref.get("abstract", "")
                                }
                                references.append(reference)
                                PrettyOutput.print(f"\n参考来源: {reference['title']} - {reference['url']}", 
                                                 OutputType.INFO)
                    elif data.get("event") == "error":
                        error_msg = data.get("error", "Unknown error")
                        raise Exception(f"Chat error: {error_msg}")
                    elif data.get("event") == "all_done":
                        break
                    
                except json.JSONDecodeError:
                    continue
            
            # 如果有参考文献，在回答后面添加引用信息
            if references:
                full_response += "\n\n参考来源:\n"
                for i, ref in enumerate(references, 1):
                    full_response += f"{i}. {ref['title']} - {ref['url']}\n"
            
            PrettyOutput.print_stream_end()  # 结束流式输出
            return full_response

        except Exception as e:
            raise Exception(f"Kimi API调用失败: {str(e)}")
        
    def reset(self):
        """重置模型"""
        self.chat_id = ""


if __name__ == "__main__":
    kimi = KimiModel()
    print(kimi.chat([{"role": "user", "content": "ollama如何部署"}]))