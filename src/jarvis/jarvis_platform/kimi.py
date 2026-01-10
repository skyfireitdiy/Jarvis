# -*- coding: utf-8 -*-
# Kimi 平台实现模块
# 提供与 Moonshot AI 的 Kimi 大模型交互功能
import json
import os
import time
from typing import Any
from typing import Dict
from typing import Generator
from typing import List
from typing import Optional
from typing import Tuple
from typing import cast

from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_utils import http
from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_utils.utils import while_success


class KimiModel(BasePlatform):
    """Kimi 大模型平台实现类
    封装了与 Kimi 大模型交互的所有功能，包括：
    - 会话管理
    - 文件上传
    - 消息收发
    """

    def get_model_list(self) -> List[Tuple[str, str]]:
        """Get model list"""
        return [
            ("k1.5", "基于网页的 Kimi，免费接口"),
            ("k1.5-thinking", "基于网页的 Kimi，深度思考模型"),
            ("k2", "基于网页的 Kimi，深度思考模型 K2"),
        ]

    def __init__(self, llm_config: Optional[Dict[str, Any]] = None):
        """
        Initialize Kimi model

        参数:
            llm_config: LLM配置字典，包含 kimi_api_key 等
        """
        super().__init__()
        PrettyOutput.auto_print(
            "⚠️ 警告：kimi 平台将在未来版本中被废弃，建议迁移到 openai 或 claude 平台。"
        )
        self.chat_id = ""  # 当前会话ID
        llm_config = llm_config or {}

        # 从 llm_config 获取配置，如果没有则从环境变量获取（向后兼容）
        self.api_key = llm_config.get("kimi_api_key") or os.getenv("KIMI_API_KEY")
        if not self.api_key:
            PrettyOutput.auto_print("⚠️ KIMI_API_KEY 未设置")
        self.auth_header = f"Bearer {self.api_key}"  # 认证头信息
        self.uploaded_files: List[Dict[str, Any]] = []  # 存储已上传文件的信息
        self.chat_id = ""  # 当前会话ID
        self.first_chat = True  # 标记是否是第一次对话
        self.system_message = ""  # 系统提示消息
        self.model_name = "kimi"  # 默认模型名称

    def set_system_prompt(self, message: str):
        """Set system message"""
        self.system_message = message

    def set_model_name(self, model_name: str):
        """Set model name"""
        self.model_name = model_name

    def _create_chat(self) -> bool:
        """Create a new chat session"""
        url = "https://kimi.moonshot.cn/api/chat"
        payload = json.dumps(
            {"name": "Unnamed session", "is_example": False, "kimiplus_id": "kimi"}
        )
        headers = {
            "Authorization": self.auth_header,
            "Content-Type": "application/json",
        }
        try:
            response = while_success(
                lambda: http.post(url, headers=headers, data=payload)
            )
            if response.status_code != 200:
                PrettyOutput.auto_print(f"❌ 错误：创建会话失败：{response.json()}")
                return False
            self.chat_id = cast(str, cast(Dict[str, Any], response.json())["id"])
            return True
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 错误：创建会话失败：{e}")
            return False

    def _get_presigned_url(self, filename: str, action: str) -> Dict:
        """Get presigned upload URL"""
        url = "https://kimi.moonshot.cn/api/pre-sign-url"

        payload = json.dumps(
            {"action": action, "name": os.path.basename(filename)}, ensure_ascii=False
        )

        headers = {
            "Authorization": self.auth_header,
            "Content-Type": "application/json",
        }

        response = while_success(lambda: http.post(url, headers=headers, data=payload))
        return cast(Dict[str, Any], response.json())

    def trim_messages(self) -> bool:
        """未实现：不支持裁剪消息历史

        返回:
            bool: 返回False表示不支持裁剪
        """
        return False

    def _upload_file(self, file_path: str, presigned_url: str) -> bool:
        """Upload file to presigned URL"""
        try:
            with open(file_path, "rb") as f:
                content = f.read()
                response = while_success(lambda: http.put(presigned_url, data=content))
                return bool(response.status_code == 200)
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 错误：上传文件失败：{e}")
            return False

    def _get_file_info(self, file_data: Dict, name: str, file_type: str) -> Dict:
        """Get file information"""
        url = "https://kimi.moonshot.cn/api/file"
        payload = json.dumps(
            {
                "type": file_type,
                "name": name,
                "object_name": file_data["object_name"],
                "chat_id": self.chat_id,
                "file_id": file_data.get("file_id", ""),
            },
            ensure_ascii=False,
        )

        headers = {
            "Authorization": self.auth_header,
            "Content-Type": "application/json",
        }

        response = while_success(lambda: http.post(url, headers=headers, data=payload))
        return cast(Dict[str, Any], response.json())

    def _wait_for_parse(self, file_id: str) -> bool:
        """Wait for file parsing to complete"""
        url = "https://kimi.moonshot.cn/api/file/parse_process"
        headers = {
            "Authorization": self.auth_header,
            "Content-Type": "application/json",
        }

        max_retries = 30
        retry_count = 0

        while retry_count < max_retries:
            payload = {"ids": [file_id]}
            response_stream = while_success(
                lambda: http.stream_post(url, headers=headers, json=payload),
            )

            # 处理流式响应
            for line in response_stream:
                if not line.strip():
                    continue

                # SSE格式的行通常以"data: "开头
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        if data.get("event") == "resp":
                            status = data.get("file_info", {}).get("status")
                            if status == "parsed":
                                return True
                            elif status == "failed":
                                return False
                    except Exception:
                        continue

            retry_count += 1
            time.sleep(1)

        return False

    def chat(self, message: str) -> Generator[str, None, None]:
        """发送消息并获取响应流
        参数:
            message: 要发送的消息内容
        返回:
            生成器，逐块返回模型响应
        """
        if not self.chat_id:
            if not self._create_chat():
                raise Exception("Failed to create chat session")

        url = f"https://kimi.moonshot.cn/api/chat/{self.chat_id}/completion/stream"

        refs: List[str] = []
        refs_file: List[Dict[str, Any]] = []

        if self.first_chat:
            message = self.system_message + "\n" + message
            self.first_chat = False

        payload = {
            "messages": [{"role": "user", "content": message}],
            "use_search": False,
            "extend": {"sidebar": True},
            "kimiplus_id": "kimi",
            "use_deep_research": False,
            "use_semantic_memory": True,
            "history": [],
            "refs": refs,
            "refs_file": refs_file,
            "model": self.model_name,
        }

        headers = {
            "Authorization": self.auth_header,
            "Content-Type": "application/json",
        }

        try:
            # 使用新的stream_post接口发送消息请求，获取流式响应
            response_stream = while_success(
                lambda: http.stream_post(url, headers=headers, json=payload),
            )

            # 处理流式响应
            for line in response_stream:
                if not line.strip():
                    continue

                # SSE格式的行通常以"data: "开头
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        event = data.get("event")

                        if event == "cmpl":
                            # 处理补全文本
                            text = data.get("text", "")
                            if text:
                                yield text
                    except Exception:
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
            "Authorization": self.auth_header,
            "Content-Type": "application/json",
        }

        try:
            response = while_success(lambda: http.delete(url, headers=headers))
            if response.status_code == 200:
                self.chat_id = ""
                self.uploaded_files = []
                self.first_chat = True  # 重置first_chat标记
                return True
            else:
                PrettyOutput.auto_print(f"⚠️ 删除会话失败: HTTP {response.status_code}")
                return False
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 删除会话时发生错误: {str(e)}")
            return False

    def save(self, file_path: str) -> bool:
        """Save chat session to a file."""
        if not self.chat_id:
            PrettyOutput.auto_print("⚠️ 没有活动的会话可供保存")
            return False

        state: Dict[str, Any] = {
            "chat_id": self.chat_id,
            "model_name": self.model_name,
            "system_message": self.system_message,
            "first_chat": self.first_chat,
            "uploaded_files": self.uploaded_files,
        }

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=4)
            self._saved = True
            PrettyOutput.auto_print(f"✅ 会话已成功保存到 {file_path}")
            return True
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 保存会话失败: {str(e)}")
            return False

    def restore(self, file_path: str) -> bool:
        """Restore chat session from a file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                state = json.load(f)

            self.chat_id = state.get("chat_id", "")
            self.model_name = state.get("model_name", "kimi")
            self.system_message = state.get("system_message", "")
            self.first_chat = state.get("first_chat", True)
            self.uploaded_files = state.get("uploaded_files", [])
            # 处理start_commit信息（如果存在）
            # start_commit = state.get("start_commit", None)
            # 可以根据需要使用start_commit信息
            self._saved = True

            PrettyOutput.auto_print(f"✅ 从 {file_path} 成功恢复会话")
            return True
        except FileNotFoundError:
            PrettyOutput.auto_print(f"❌ 会话文件未找到: {file_path}")
            return False
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 恢复会话失败: {str(e)}")
            return False

    def name(self) -> str:
        """Model name"""
        return self.model_name

    @classmethod
    def platform_name(cls) -> str:
        """Platform name"""
        return "kimi"

    @classmethod
    def get_required_env_keys(cls) -> List[str]:
        """
        获取Kimi平台所需的配置键列表（已弃用：建议使用 llm_config 配置）

        返回:
            List[str]: 配置键的列表（对应 llm_config 中的 kimi_api_key）
        """
        return ["KIMI_API_KEY"]

    @classmethod
    def get_env_config_guide(cls) -> Dict[str, str]:
        """
        获取配置指导（已弃用：建议使用 llm_config 配置）

        返回:
            Dict[str, str]: 配置键名到配置指导的映射
        """
        return {
            "KIMI_API_KEY": (
                "1. 登录 Kimi 网页版: https://kimi.moonshot.cn/\n"
                "2. 打开浏览器开发者工具 (F12)\n"
                '3. 切换到"网络"(Network)标签页\n'
                "4. 在 Kimi 中发送一条消息\n"
                "5. 找到 stream 请求\n"
                '6. 在"请求标头"中找到 authorization 字段\n'
                "7. 复制 Bearer 后面的 API Key 部分"
            )
        }
