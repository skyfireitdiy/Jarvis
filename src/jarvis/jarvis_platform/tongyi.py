# -*- coding: utf-8 -*-
import json
import os
from typing import Generator, List, Tuple
import uuid

import requests

from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_utils.output import PrettyOutput, OutputType
from jarvis.jarvis_utils.utils import while_success


class TongyiPlatform(BasePlatform):
    """Tongyi platform implementation"""

    platform_name = "tongyi"

    def __init__(self):
        """Initialize Tongyi platform"""
        super().__init__()
        self.session_id = ""
        self.cookies = os.getenv("TONGYI_COOKIES", "")
        self.x_xsrf_token = os.getenv("TONGYI_X_XSRF_TOKEN", "")
        self.request_id = ""
        self.msg_id = ""
        self.model_name = ""


    def _get_base_headers(self):
        return {
            "Host": "api.tongyi.com",
            "Connection": "keep-alive",
            "X-Platform": "pc_tongyi",
            "sec-ch-ua-platform": "Windows",
            "X-XSRF-TOKEN": self.x_xsrf_token,
            "sec-ch-ua": '"Chromium";v="136", "Microsoft Edge";v="136", "Not.A/Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 Edg/136.0.0.0",
            "accept": "text/event-stream",
            "DNT": "1",
            "Content-Type": "application/json",
            "Origin": "https://www.tongyi.com",
            "Sec-Fetch-Site": "same-site",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": "https://www.tongyi.com/qianwen",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "Cookie": self.cookies
        }

    def set_model_name(self, model_name: str):
        """Set model name
        
        Args:
            model_name: Model name to use
        """
        self.model_name = model_name

    def _generate_request_id(self):
        self.request_id = str(uuid.uuid4()).replace("-", "")

    def chat(self, message: str) -> Generator[str, None, None]:
        if not self.request_id:
            self._generate_request_id()
        url = "https://api.tongyi.com/dialog/conversation"
        headers = self._get_base_headers()
        
        payload = {
            "model": "",
            "action": "next",
            "mode": "chat",
            "userAction": "new_top",
            "requestId": self.request_id,
            "sessionId": self.session_id,
            "sessionType": "text_chat",
            "parentMsgId": self.msg_id,
            "params": {
                "agentId": "",
                "searchType": "",
                "pptGenerate": False,
                "bizScene": "",
                "bizSceneInfo": {},
                "specifiedModel": "",
                "deepThink": False,
                "deepResearch": False
            },
            "contents": [
                {
                    "content": message,
                    "contentType": "text",
                    "role": "user",
                    "ext": {
                        "searchType": "",
                        "pptGenerate": False,
                        "deepThink": False,
                        "deepResearch": False
                    }
                }
            ]
        }

        try:
            response = while_success(lambda: requests.post(url, headers=headers, json=payload, stream=True), sleep_time=5)
            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}: {response.text}")

            for line in response.iter_lines():
                if not line:
                    continue
                line_str = line.decode('utf-8')
                if not line_str.startswith("data: "):
                    continue

                try:
                    data = json.loads(line_str[6:])
                    # 记录消息ID和会话ID
                    if "msgId" in data:
                        self.msg_id = data["msgId"]
                    if "sessionId" in data:
                        self.session_id = data["sessionId"]
                        
                    if "contents" in data and len(data["contents"]) > 0:
                        content = data["contents"][0]
                        if content.get("contentType") == "text" and content.get("content"):
                            yield content["content"]
                except json.JSONDecodeError:
                    continue

            return None

        except Exception as e:
            raise Exception(f"Chat failed: {str(e)}")
            
            

    def upload_files(self, file_list: List[str]) -> bool:
        
        return False

    def name(self) -> str:
        """Get platform name
        
        Returns:
            str: Platform name
        """
        return self.model_name

    def delete_chat(self) -> bool:
        """Delete chat history
        
        Returns:
            bool: True if deletion successful, False otherwise
        """
        if not self.session_id:
            return True

        url = "https://api.tongyi.com/dialog/session/delete"
        headers = self._get_base_headers()
        payload = {
            "sessionId": self.session_id
        }

        try:
            response = while_success(lambda: requests.post(url, headers=headers, json=payload), sleep_time=5)
            if response.status_code != 200:
                PrettyOutput.print(f"Failed to delete chat: HTTP {response.status_code}", OutputType.ERROR)
                return False
            self.request_id = ""
            self.session_id = ""
            self.msg_id = ""
            return True
        except Exception as e:
            PrettyOutput.print(f"Error deleting chat: {str(e)}", OutputType.ERROR)
            return False

    def set_system_message(self, message: str):
        """Set system message
        
        Args:
            message: System message to set
        """
        self.system_message = message

    def get_model_list(self) -> List[Tuple[str, str]]:
        """Get available model list
        
        Returns:
            List[Tuple[str, str]]: List of (model_id, model_name) tuples
        """
        return [
            ("qwen-turbo", "Qwen-Turbo"),
            ("qwen-plus", "Qwen-Plus"),
            ("qwen-max", "Qwen-Max"),
        ]

    def support_web(self) -> bool:
        """Check if platform supports web functionality
        
        Returns:
            bool: True if web is supported, False otherwise
        """
        return True
