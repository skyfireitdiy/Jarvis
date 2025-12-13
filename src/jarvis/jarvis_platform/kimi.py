# -*- coding: utf-8 -*-
# Kimi 平台实现模块
# 提供与 Moonshot AI 的 Kimi 大模型交互功能
import json
import mimetypes
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

    def support_upload_files(self) -> bool:
        """Check if platform supports upload files"""
        return True

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

    def upload_files(self, file_list: List[str]) -> bool:
        """Upload file list and return file information"""
        if not file_list:
            return True

        if not self.chat_id:
            PrettyOutput.auto_print("ℹ️ 正在创建聊天会话...")
            if not self._create_chat():
                PrettyOutput.auto_print("❌ 创建聊天会话失败")
                return False
            PrettyOutput.auto_print("✅ 创建聊天会话成功")

        uploaded_files = []
        for index, file_path in enumerate(file_list, 1):
            file_name = os.path.basename(file_path)
            log_lines: List[str] = [f"处理文件 [{index}/{len(file_list)}]: {file_name}"]
            try:
                mime_type, _ = mimetypes.guess_type(file_path)
                action = (
                    "image" if mime_type and mime_type.startswith("image/") else "file"
                )

                # 获取预签名URL
                log_lines.append(f"获取上传URL: {file_name}")
                presigned_data = self._get_presigned_url(file_path, action)

                # 上传文件
                log_lines.append(f"上传文件: {file_name}")
                if self._upload_file(file_path, presigned_data["url"]):
                    # 获取文件信息
                    log_lines.append(f"获取文件信息: {file_name}")
                    file_info = self._get_file_info(presigned_data, file_name, action)

                    # 只有文件需要解析
                    if action == "file":
                        log_lines.append(f"等待文件解析: {file_name}")
                        if self._wait_for_parse(file_info["id"]):
                            uploaded_files.append(file_info)
                            log_lines.append(f"文件处理完成: {file_name}")
                        else:
                            log_lines.append(f"文件解析失败: {file_name}")
                            joined_logs = "\n".join(log_lines)
                            PrettyOutput.auto_print(f"❌ {joined_logs}")
                            return False
                    else:
                        uploaded_files.append(file_info)
                        log_lines.append(f"图片处理完成: {file_name}")
                else:
                    log_lines.append(f"文件上传失败: {file_name}")
                    joined_logs = "\n".join(log_lines)
                    PrettyOutput.auto_print(f"❌ {joined_logs}")
                    return False

                # 成功路径统一输出本文件的处理日志
                joined_logs = "\n".join(log_lines)
                PrettyOutput.auto_print(f"ℹ️ {joined_logs}")

            except Exception as e:
                log_lines.append(f"处理文件出错 {file_path}: {str(e)}")
                joined_logs = "\n".join(log_lines)
                PrettyOutput.auto_print(f"❌ {joined_logs}")
                return False

        self.uploaded_files = uploaded_files
        return True

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

        state = {
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

    def support_web(self) -> bool:
        """Kimi平台支持web功能"""
        return True

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
