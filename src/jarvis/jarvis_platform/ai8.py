import os
from typing import Generator, List, Tuple
from jarvis.jarvis_platform.base import BasePlatform
import json

from jarvis.jarvis_utils import http
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import while_success


class AI8Model(BasePlatform):
    """AI8 model implementation"""

    platform_name = "ai8"
    BASE_URL = "https://ai8.rcouyi.com"

    def get_model_list(self) -> List[Tuple[str, str]]:
        """获取模型列表"""
        self.get_available_models()
        return [(name, info["desc"]) for name, info in self.models.items()]

    def __init__(self):
        """Initialize model"""
        super().__init__()
        self.system_prompt = ""
        self.conversation = {}
        self.models = {}  # 存储模型信息

        self.token = os.getenv("AI8_API_KEY")
        if not self.token:
            PrettyOutput.print("未设置 AI8_API_KEY", OutputType.WARNING)

        self.headers = {
            "Authorization": self.token,
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "X-APP-VERSION": "2.3.0",
            "Origin": self.BASE_URL,
            "Referer": f"{self.BASE_URL}/chat?_userMenuKey=chat",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
        }

        self.model_name = os.getenv("JARVIS_MODEL") or "deepseek-chat"
        if self.model_name not in self.get_available_models():
            PrettyOutput.print(
                f"警告: 选择的模型 {self.model_name} 不在可用列表中", OutputType.WARNING
            )

    def set_model_name(self, model_name: str):
        """Set model name"""

        self.model_name = model_name

    def create_conversation(self) -> bool:
        """Create a new conversation"""
        try:

            # 1. 创建会话
            response = while_success(
                lambda: http.post(
                    f"{self.BASE_URL}/api/chat/session", headers=self.headers, json={}
                ),
                sleep_time=5,
            )

            data = response.json()
            if data["code"] != 0:
                PrettyOutput.print(
                    f"创建会话失败: {data.get('msg', '未知错误')}", OutputType.WARNING
                )
                return False

            self.conversation = data["data"]

            # 2. 更新会话设置
            session_data = {
                **self.conversation,
                "model": self.model_name,
                "contextCount": 65536,
                "prompt": self.system_prompt,
                "plugins": [],
                "localPlugins": None,
                "useAppId": 0,
            }

            response = while_success(
                lambda: http.put(
                    f"{self.BASE_URL}/api/chat/session/{self.conversation['id']}",  # type: ignore
                    headers=self.headers,
                    json=session_data,
                ),
                sleep_time=5,
            )

            data = response.json()
            if data["code"] == 0:
                self.conversation = data["data"]
                return True
            else:
                PrettyOutput.print(
                    f"更新会话设置失败: {data.get('msg', '未知错误')}",
                    OutputType.WARNING,
                )
                return False

        except Exception as e:
            PrettyOutput.print(f"创建会话失败: {str(e)}", OutputType.ERROR)
            return False

    def set_system_prompt(self, message: str):
        """Set system message"""
        self.system_prompt = message

    def chat(self, message: str) -> Generator[str, None, None]:
        """Execute conversation"""
        try:

            # 确保有会话ID
            if not self.conversation:
                if not self.create_conversation():
                    raise Exception("Failed to create conversation")

            payload = {
                "text": message,
                "sessionId": self.conversation["id"] if self.conversation else None,
                "files": [],
            }

            # 使用stream_post进行流式请求
            response_stream = while_success(
                lambda: http.stream_post(
                    f"{self.BASE_URL}/api/chat/completions",
                    headers=self.headers,
                    json=payload,
                ),
                sleep_time=5,
            )

            # 处理流式响应
            for chunk in response_stream:
                if chunk:
                    try:
                        line = chunk.decode("utf-8")
                        if line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])
                                if data.get("type") == "string":
                                    chunk_data = data.get("data", "")
                                    if chunk_data:
                                        yield chunk_data

                            except json.JSONDecodeError:
                                continue

                    except UnicodeDecodeError:
                        continue

            return None

        except Exception as e:
            PrettyOutput.print(f"对话异常: {str(e)}", OutputType.ERROR)
            raise e

    def name(self) -> str:
        """Return model name"""
        return self.model_name

    def delete_chat(self) -> bool:
        """Delete current chat session"""
        try:
            if not self.conversation:
                return True

            response = while_success(
                lambda: http.delete(
                    f"{self.BASE_URL}/api/chat/session/{self.conversation['id']}",  # type: ignore
                    headers=self.headers,
                ),
                sleep_time=5,
            )

            data = response.json()
            if data["code"] == 0:
                self.conversation = None
                return True
            else:
                error_msg = f"删除会话失败: {data.get('msg', '未知错误')}"
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

            response = while_success(
                lambda: http.get(
                    f"{self.BASE_URL}/api/chat/tmpl", headers=self.headers
                ),
                sleep_time=5,
            )

            data = response.json()
            if data["code"] != 0:
                PrettyOutput.print(
                    f"获取模型列表失败: {data.get('msg', '未知错误')}",
                    OutputType.WARNING,
                )
                return []

            # 保存模型信息
            self.models = {model["value"]: model for model in data["data"]["models"]}

            for model in self.models.values():
                # 添加标签
                model_str = f"{model['label']}"

                # 添加特性标记
                features = []
                if model["attr"].get("multimodal"):
                    features.append("Multimodal")
                if model["attr"].get("plugin"):
                    features.append("Plugin support")
                if model["attr"].get("onlyImg"):
                    features.append("Image support")
                if model["attr"].get("tag"):
                    features.append(model["attr"]["tag"])
                if model["attr"].get("integral"):
                    features.append(model["attr"]["integral"])
                # 添加备注
                if model["attr"].get("note"):
                    model_str += f" - {model['attr']['note']}"
                if features:
                    model_str += f" [{'|'.join(features)}]"

                model["desc"] = model_str

            return list(self.models.keys())

        except Exception as e:
            PrettyOutput.print(f"获取模型列表失败: {str(e)}", OutputType.ERROR)
            return []

    def support_upload_files(self) -> bool:
        return False

    def support_web(self) -> bool:
        return False

    def upload_files(self, file_list: List[str]) -> bool:
        return False
