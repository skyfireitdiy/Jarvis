import mimetypes
import os
from typing import Dict, Generator, List, Tuple
from jarvis.jarvis_platform.base import BasePlatform
import json

from jarvis.jarvis_utils import http
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import while_success


class OyiModel(BasePlatform):
    """Oyi model implementation"""

    BASE_URL = "https://api-10086.rcouyi.com"

    def get_model_list(self) -> List[Tuple[str, str]]:
        """Get model list"""
        self.get_available_models()
        return [(name, info["desc"]) for name, info in self.models.items()]

    def __init__(self):
        """Initialize model"""
        super().__init__()
        self.models = {}
        self.messages = []
        self.system_prompt = ""
        self.conversation = None
        self.first_chat = True

        self.token = os.getenv("OYI_API_KEY")
        if not self.token:
            PrettyOutput.print("OYI_API_KEY 未设置", OutputType.WARNING)

        self.model_name = os.getenv("JARVIS_MODEL") or "deepseek-chat"
        if self.model_name not in [m.split()[0] for m in self.get_available_models()]:
            PrettyOutput.print(
                f"警告: 选择的模型 {self.model_name} 不在可用列表中", OutputType.WARNING
            )

    def set_model_name(self, model_name: str):
        """Set model name"""

        self.model_name = model_name

    def create_conversation(self) -> bool:
        """Create a new conversation"""
        try:
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            }

            payload = {
                "id": 0,
                "roleId": 0,
                "title": "New conversation",
                "isLock": False,
                "systemMessage": "",
                "params": json.dumps(
                    {
                        "model": self.model_name,
                        "is_webSearch": True,
                        "message": [],
                        "systemMessage": None,
                        "requestMsgCount": 65536,
                        "temperature": 0.8,
                        "speechVoice": "Alloy",
                        "max_tokens": 8192,
                        "chatPluginIds": [],
                    }
                ),
            }

            response = while_success(
                lambda: http.post(
                    f"{self.BASE_URL}/chatapi/chat/save", headers=headers, json=payload
                ),
                sleep_time=5,
            )

            data = response.json()
            if data["code"] == 200 and data["type"] == "success":
                self.conversation = data
                return True
            else:
                PrettyOutput.print(
                    f"创建会话失败: {data['message']}", OutputType.WARNING
                )
                return False

        except Exception as e:
            PrettyOutput.print(f"创建会话失败: {str(e)}", OutputType.ERROR)
            return False

    def set_system_prompt(self, message: str):
        """Set system message"""
        self.system_prompt = message

    def chat(self, message: str) -> Generator[str, None, None]:
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
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/plain, */*",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Origin": "https://ai.rcouyi.com",
                "Referer": "https://ai.rcouyi.com/",
            }

            payload = {
                "topicId": (
                    self.conversation["result"]["id"] if self.conversation else None
                ),
                "messages": self.messages,
                "content": message,
                "contentFiles": [],
            }

            # 如果有上传的文件，添加到请求中
            if self.first_chat:
                message = self.system_prompt + "\n" + message
                payload["content"] = message
                self.first_chat = False

            self.messages.append({"role": "user", "content": message})

            # 发送消息
            response = while_success(
                lambda: http.post(
                    f"{self.BASE_URL}/chatapi/chat/message",
                    headers=headers,
                    json=payload,
                ),
                sleep_time=5,
            )

            data = response.json()
            if data["code"] != 200 or data["type"] != "success":
                error_msg = f"聊天失败: {data.get('message', '未知错误')}"
                PrettyOutput.print(error_msg, OutputType.WARNING)
                raise Exception(error_msg)

            message_id = data["result"][-1]

            # 获取响应内容
            response = while_success(
                lambda: http.stream_post(
                    f"{self.BASE_URL}/chatapi/chat/message/{message_id}",
                    headers=headers,
                ),
                sleep_time=5,
            )

            full_response = ""
            bin = b""
            for chunk in response:
                if chunk:
                    bin += chunk
                    try:
                        text = bin.decode("utf-8")
                    except UnicodeDecodeError:
                        continue
                    full_response += text
                    bin = b""
                    yield text

            self.messages.append({"role": "assistant", "content": full_response})
            return None
        except Exception as e:
            PrettyOutput.print(f"聊天失败: {str(e)}", OutputType.ERROR)
            raise e

    def name(self) -> str:
        """Return model name"""
        return self.model_name

    @classmethod
    def platform_name(cls) -> str:
        """Return platform name"""
        return "oyi"

    def delete_chat(self) -> bool:
        """Delete current chat session"""
        try:
            if not self.conversation:
                return True

            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/plain, */*",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Origin": "https://ai.rcouyi.com",
                "Referer": "https://ai.rcouyi.com/",
            }

            response = while_success(
                lambda: http.post(
                    f"{self.BASE_URL}/chatapi/chat/{self.conversation['result']['id']}",  # type: ignore
                    headers=headers,
                    json={},
                ),
                sleep_time=5,
            )

            data = response.json()
            if data["code"] == 200 and data["type"] == "success":
                self.messages = []
                self.conversation = None
                self.first_chat = True
                return True
            else:
                error_msg = f"删除会话失败: {data.get('message', '未知错误')}"
                PrettyOutput.print(error_msg, OutputType.WARNING)
                return False

        except Exception as e:
            PrettyOutput.print(f"删除会话失败: {str(e)}", OutputType.ERROR)
            return False

    def save(self, file_path: str) -> bool:
        """Save chat session to a file."""
        if not self.conversation:
            PrettyOutput.print("没有活动的会话可供保存", OutputType.WARNING)
            return False

        state = {
            "conversation": self.conversation,
            "messages": self.messages,
            "model_name": self.model_name,
            "system_prompt": self.system_prompt,
            "first_chat": self.first_chat,
        }

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=4)
            self._saved = True
            PrettyOutput.print(f"会话已成功保存到 {file_path}", OutputType.SUCCESS)
            return True
        except Exception as e:
            PrettyOutput.print(f"保存会话失败: {str(e)}", OutputType.ERROR)
            return False

    def restore(self, file_path: str) -> bool:
        """Restore chat session from a file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                state = json.load(f)

            self.conversation = state.get("conversation")
            self.messages = state.get("messages", [])
            self.model_name = state.get("model_name", "deepseek-chat")
            self.system_prompt = state.get("system_prompt", "")
            self.first_chat = state.get("first_chat", True)
            self._saved = True

            PrettyOutput.print(f"从 {file_path} 成功恢复会话", OutputType.SUCCESS)
            return True
        except FileNotFoundError:
            PrettyOutput.print(f"会话文件未找到: {file_path}", OutputType.ERROR)
            return False
        except Exception as e:
            PrettyOutput.print(f"恢复会话失败: {str(e)}", OutputType.ERROR)
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
                "Content-Type": "application/json",
                "Accept": "application/json, text/plain, */*",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Origin": "https://ai.rcouyi.com",
                "Referer": "https://ai.rcouyi.com/",
            }

            response = while_success(
                lambda: http.get(
                    "https://ai.rcouyi.com/config/system.json", headers=headers
                ),
                sleep_time=5,
            )

            data = response.json()

            # 保存模型信息
            self.models = {
                model["value"]: model
                for model in data.get("model", [])
                if model.get("enable", False)  # 只保存启用的模型
            }

            # 格式化显示
            models = []
            for model in self.models.values():
                # 基本信息
                model_name = model["value"]
                model_str = model["label"]

                # 添加后缀标签
                suffix = model.get("suffix", [])
                if suffix:
                    # 处理新格式的suffix (字典列表)
                    if suffix and isinstance(suffix[0], dict):
                        suffix_str = ", ".join(s.get("tag", "") for s in suffix)
                    # 处理旧格式的suffix (字符串列表)
                    else:
                        suffix_str = ", ".join(str(s) for s in suffix)
                    model_str += f" ({suffix_str})"

                # 添加描述或提示
                info = model.get("tooltip") or model.get("description", "")
                if info:
                    model_str += f" - {info}"

                model["desc"] = model_str
                models.append(model_name)

            return sorted(models)

        except Exception as e:
            PrettyOutput.print(f"获取模型列表失败: {str(e)}", OutputType.WARNING)
            return []

    def support_upload_files(self) -> bool:
        return False

    def support_web(self) -> bool:
        return False

    def upload_files(self, file_list: List[str]) -> bool:
        return False
