# -*- coding: utf-8 -*-
import json
import os
import time
import uuid
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
from jarvis.jarvis_utils.tag import ct
from jarvis.jarvis_utils.tag import ot
from jarvis.jarvis_utils.utils import while_success


class TongyiPlatform(BasePlatform):
    """Tongyi platform implementation"""

    # Supported image formats
    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"}

    def __init__(self, llm_config: Optional[Dict[str, Any]] = None):
        """
        Initialize Tongyi platform

        参数:
            llm_config: LLM配置字典，包含 tongyi_cookies 等
        """
        super().__init__()
        self.session_id = ""
        llm_config = llm_config or {}

        # 从 llm_config 获取配置，如果没有则从环境变量获取（向后兼容）
        self.cookies = llm_config.get("tongyi_cookies") or os.getenv(
            "TONGYI_COOKIES", ""
        )
        self.request_id = ""
        self.msg_id = ""
        self.model_name = ""
        self.uploaded_file_info: List[Dict[str, Any]] = []
        self.system_message = ""  # System message for initialization
        self.first_chat = True  # Flag for first chat

    def _get_base_headers(self):
        return {
            "Host": "api.tongyi.com",
            "Connection": "keep-alive",
            "X-Platform": "pc_tongyi",
            "sec-ch-ua-platform": "Windows",
            "sec-ch-ua": '"Chromium";v="136", "Microsoft Edge";v="136", "Not.A/Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 Edg/136.0.0.0",
            "accept": "application/json, text/plain, */*",
            "DNT": "1",
            "Content-Type": "application/json",
            "Origin": "https://www.tongyi.com",
            "Sec-Fetch-Site": "same-site",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": "https://www.tongyi.com/qianwen",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "Cookie": self.cookies,
        }

    def set_model_name(self, model_name: str):
        """Set model name

        Args:
            model_name: Model name to use
        """
        self.model_name = model_name

    def _generate_request_id(self):
        self.request_id = str(uuid.uuid4()).replace("-", "")

    def support_upload_files(self) -> bool:
        """Check if platform supports upload files"""
        return True

    def chat(self, message: str) -> Generator[str, None, None]:
        if not self.request_id:
            self._generate_request_id()
        url = "https://api.tongyi.com/dialog/conversation"
        headers = self._get_base_headers()

        headers["accept"] = "text/event-stream"

        # Prepare contents array with message
        contents = [
            {
                "content": message,
                "contentType": "text",
                "role": "user",
                "ext": {
                    "searchType": "depth" if self.web else "",
                    "pptGenerate": False,
                    "deepThink": self.model_name == "Thinking",
                    "deepResearch": self.model_name == "Deep-Research",
                },
            }
        ]

        # Add system message if it's first chat
        if self.first_chat and self.system_message:
            contents.insert(
                0,
                {
                    "content": self.system_message,
                    "contentType": "text",
                    "role": "system",
                    "ext": {
                        "searchType": "depth" if self.web else "",
                        "pptGenerate": False,
                        "deepThink": self.model_name == "Thinking",
                        "deepResearch": self.model_name == "Deep-Research",
                    },
                },
            )
            self.first_chat = False

        # Add uploaded files to contents if available and clear after use
        if self.uploaded_file_info:
            for file_info in self.uploaded_file_info:
                # Determine content type based on fileKey extension
                file_ext = os.path.splitext(file_info["fileKey"])[1].lower()
                is_image = file_ext in self.IMAGE_EXTENSIONS

                contents.append(
                    {
                        "role": "user",
                        "contentType": "image" if is_image else "file",
                        "content": file_info["url"],
                        "ext": {
                            "fileSize": file_info.get("fileSize", 0),
                            "batchId": file_info.get("batchId", ""),
                            "docId": file_info.get("docId", ""),
                        },
                    }
                )
            # Clear uploaded file info after using it
            self.uploaded_file_info = []

        payload: Dict[str, Any] = {
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
                "searchType": "depth" if self.web else "",
                "pptGenerate": False,
                "bizScene": "code_chat" if self.model_name == "Code-Chat" else "",
                "bizSceneInfo": {},
                "specifiedModel": "",
                "deepThink": self.model_name == "Thinking",
                "deepResearch": self.model_name == "Deep-Research",
                "fileUploadBatchId": (
                    self.uploaded_file_info[0]["batchId"]
                    if self.uploaded_file_info
                    else ""
                ),
            },
            "contents": contents,
        }

        try:
            # 使用新的stream_post接口发送消息请求，获取流式响应
            response_stream = while_success(
                lambda: http.stream_post(url, headers=headers, json=payload),
            )

            msg_id = ""
            session_id = ""
            thinking_content = ""
            text_content = ""
            in_thinking = False

            # 处理流式响应
            for line in response_stream:
                if not line.strip():
                    continue

                # SSE格式的行通常以"data: "开头
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        # 记录消息ID和会话ID
                        if "msgId" in data:
                            msg_id = data["msgId"]
                        if "sessionId" in data:
                            session_id = data["sessionId"]

                        if "contents" in data and len(data["contents"]) > 0:
                            for content in data["contents"]:
                                if content.get("contentType") == "think":
                                    if not in_thinking:
                                        yield f"{ot('think')}\n\n"
                                        in_thinking = True
                                    if content.get("incremental"):
                                        tmp_content = json.loads(
                                            content.get("content")
                                        )["content"]
                                        thinking_content += tmp_content
                                        yield tmp_content
                                    else:
                                        tmp_content = json.loads(
                                            content.get("content")
                                        )["content"]
                                        if len(thinking_content) < len(tmp_content):
                                            yield tmp_content[len(thinking_content) :]
                                            thinking_content = tmp_content
                                        else:
                                            yield f"\r\n{ct('think')}\n"[
                                                len(thinking_content)
                                                - len(tmp_content) :
                                            ]
                                            thinking_content = tmp_content
                                        in_thinking = False
                                elif content.get("contentType") == "text":
                                    if in_thinking:
                                        continue
                                    if content.get("incremental"):
                                        tmp_content = content.get("content")
                                        text_content += tmp_content
                                        yield tmp_content
                                    else:
                                        tmp_content = content.get("content")
                                        if len(text_content) < len(tmp_content):
                                            yield tmp_content[len(text_content) :]
                                            text_content = tmp_content

                    except Exception:
                        continue

            self.msg_id = msg_id
            self.session_id = session_id

            return

        except Exception as e:
            raise Exception(f"Chat failed: {str(e)}")

    def _get_upload_token(self) -> Dict[str, Any]:
        """Get upload token from Tongyi API

        Returns:
            Dict[str, Any]: Upload token information including accessId, bucketName, etc.
        """
        url = "https://api.tongyi.com/dialog/uploadToken"
        headers = self._get_base_headers()
        payload: Dict[str, Any] = {}

        try:
            response = while_success(
                lambda: http.post(url, headers=headers, json=payload)
            )
            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}: {response.text}")

            result = response.json()
            if not result.get("success"):
                raise Exception(f"Failed to get upload token: {result.get('errorMsg')}")

            return cast(Dict[str, Any], result.get("data", {}))

        except Exception as e:
            raise Exception(f"Failed to get upload token: {str(e)}")

    def upload_files(self, file_list: List[str]) -> bool:
        """Upload files to Tongyi platform and get download links

        Args:
            file_list: List of file paths to upload

        Returns:
            List[Dict[str, str]]: List of dictionaries containing file info and download URLs
        """
        try:
            upload_token = self._get_upload_token()
            uploaded_files = []

            for file_path in file_list:
                file_name = os.path.basename(file_path)
                log_lines: List[str] = []
                log_lines.append(f"上传文件 {file_name}")
                try:
                    if not os.path.exists(file_path):
                        # 先输出已收集的日志与错误后返回
                        log_lines.append(f"文件不存在: {file_path}")
                        joined_logs = "\n".join(log_lines)
                        PrettyOutput.auto_print(f"❌ {joined_logs}")
                        return False

                    # Get file name and content type
                    content_type = self._get_content_type(file_path)

                    log_lines.append(f"准备上传文件: {file_name}")

                    # Prepare form data
                    form_data = {
                        "OSSAccessKeyId": upload_token["accessId"],
                        "policy": upload_token["policy"],
                        "signature": upload_token["signature"],
                        "key": f"{upload_token['dir']}{file_name}",
                        "dir": upload_token["dir"],
                        "success_action_status": "200",
                    }

                    # Prepare files
                    files = {"file": (file_name, open(file_path, "rb"), content_type)}

                    log_lines.append(f"正在上传文件: {file_name}")

                    # Upload file
                    response = http.post(
                        upload_token["host"], data=form_data, files=files
                    )

                    if response.status_code != 200:
                        log_lines.append(
                            f"上传失败 {file_name}: HTTP {response.status_code}"
                        )
                        joined_logs = "\n".join(log_lines)
                        PrettyOutput.auto_print(f"❌ {joined_logs}")
                        return False

                    # Determine file type based on extension
                    file_ext = os.path.splitext(file_path)[1].lower()
                    is_image = file_ext in self.IMAGE_EXTENSIONS

                    uploaded_files.append(
                        {
                            "fileKey": file_name,
                            "fileType": "image" if is_image else "file",
                            "dir": upload_token["dir"],
                        }
                    )

                    log_lines.append(f"获取下载链接: {file_name}")

                    # Get download links for uploaded files
                    url = "https://api.tongyi.com/dialog/downloadLink/batch"
                    headers = self._get_base_headers()
                    payload = {
                        "fileKeys": [f["fileKey"] for f in uploaded_files],
                        "fileType": (
                            "image"
                            if any(f["fileType"] == "image" for f in uploaded_files)
                            else "file"
                        ),
                        "dir": upload_token["dir"],
                    }

                    response = http.post(url, headers=headers, json=payload)
                    if response.status_code != 200:
                        log_lines.append(
                            f"获取下载链接失败: HTTP {response.status_code}"
                        )
                        joined_logs = "\n".join(log_lines)
                        PrettyOutput.auto_print(f"❌ {joined_logs}")
                        return False

                    result = response.json()
                    if not result.get("success"):
                        log_lines.append(f"获取下载链接失败: {result.get('errorMsg')}")
                        joined_logs = "\n".join(log_lines)
                        PrettyOutput.auto_print(f"❌ {joined_logs}")
                        return False

                    # Add files to chat
                    self.uploaded_file_info = result.get("data", {}).get("results", [])
                    for file_info in self.uploaded_file_info:
                        log_lines.append(f"添加文件到对话: {file_name}")
                        add_url = "https://api.tongyi.com/assistant/api/chat/file/add"
                        add_payload = {
                            "workSource": "chat",
                            "terminal": "web",
                            "workCode": "0",
                            "channel": "home",
                            "workType": "file",
                            "module": "uploadhistory",
                            "workName": file_info["fileKey"],
                            "workId": file_info["docId"],
                            "workResourcePath": file_info["url"],
                            "sessionId": "",
                            "batchId": str(uuid.uuid4()).replace("-", "")[
                                :32
                            ],  # Generate random batchId
                            "fileSize": os.path.getsize(file_path),
                        }

                        add_response = http.post(
                            add_url, headers=headers, json=add_payload
                        )
                        if add_response.status_code != 200:
                            log_lines.append(
                                f"添加文件到对话失败: HTTP {add_response.status_code}"
                            )
                            continue

                        add_result = add_response.json()
                        if not add_result.get("success"):
                            log_lines.append(
                                f"添加文件到对话失败: {add_result.get('errorMsg')}"
                            )
                            continue

                        file_info.update(add_result.get("data", {}))

                    log_lines.append(f"文件 {file_name} 上传成功")
                    joined_logs = "\n".join(log_lines)
                    PrettyOutput.auto_print(f"ℹ️ {joined_logs}")
                    time.sleep(1)  # 短暂暂停以便用户看到成功状态

                except Exception as e:
                    log_lines.append(f"上传文件 {file_name} 时出错: {str(e)}")
                    joined_logs = "\n".join(log_lines)
                    PrettyOutput.auto_print(f"❌ {joined_logs}")
                    return False
            return True

        except Exception as e:
            PrettyOutput.auto_print(f"❌ Error uploading files: {str(e)}")
            return False

    def _get_content_type(self, file_path: str) -> str:
        """Get content type for file

        Args:
            file_path: Path to file

        Returns:
            str: Content type
        """
        ext = os.path.splitext(file_path)[1].lower()
        content_types = {
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".xls": "application/vnd.ms-excel",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".pdf": "application/pdf",
            ".epub": "application/epub+zip",
            ".mobi": "application/x-mobipocket-ebook",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
            ".tiff": "image/tiff",
        }
        return content_types.get(ext, "application/octet-stream")

    def name(self) -> str:
        """Get platform name

        Returns:
            str: Platform name
        """
        return self.model_name

    @classmethod
    def platform_name(cls) -> str:
        """Get platform name

        Returns:
            str: Platform name
        """
        return "tongyi"

    def delete_chat(self) -> bool:
        """Delete chat history

        Returns:
            bool: True if deletion successful, False otherwise
        """
        if not self.session_id:
            return True

        url = "https://api.tongyi.com/dialog/session/delete"
        headers = self._get_base_headers()
        payload: Dict[str, Any] = {"sessionId": self.session_id}

        try:
            response = while_success(
                lambda: http.post(url, headers=headers, json=payload)
            )
            if response.status_code != 200:
                PrettyOutput.auto_print(
                    f"❌ Failed to delete chat: HTTP {response.status_code}"
                )
                return False
            self.request_id = ""
            self.session_id = ""
            self.msg_id = ""
            self.first_chat = True  # Reset first_chat flag
            return True
        except Exception as e:
            PrettyOutput.auto_print(f"❌ Error deleting chat: {str(e)}")
            return False

    def save(self, file_path: str) -> bool:
        """Save chat session to a file."""
        if not self.session_id:
            PrettyOutput.auto_print("⚠️ 没有活动的会话可供保存")
            return False

        state = {
            "session_id": self.session_id,
            "request_id": self.request_id,
            "msg_id": self.msg_id,
            "model_name": self.model_name,
            "uploaded_file_info": self.uploaded_file_info,
            "system_message": self.system_message,
            "first_chat": self.first_chat,
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

            self.session_id = state.get("session_id", "")
            self.request_id = state.get("request_id", "")
            self.msg_id = state.get("msg_id", "")
            self.model_name = state.get("model_name", "")
            self.uploaded_file_info = state.get("uploaded_file_info", [])
            self.system_message = state.get("system_message", "")
            self.first_chat = state.get("first_chat", True)
            self._saved = True

            PrettyOutput.auto_print(f"✅ 从 {file_path} 成功恢复会话")
            return True
        except FileNotFoundError:
            PrettyOutput.auto_print(f"❌ 会话文件未找到: {file_path}")
            return False
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 恢复会话失败: {str(e)}")
            return False

    def set_system_prompt(self, message: str):
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
            ("Normal", "Normal"),
            ("Thinking", "Thinking"),
            ("Deep-Research", "Deep-Research"),
            ("Code-Chat", "Code-Chat"),
        ]

    def support_web(self) -> bool:
        """Check if platform supports web functionality

        Returns:
            bool: True if web is supported, False otherwise
        """
        return True

    @classmethod
    def get_required_env_keys(cls) -> List[str]:
        """
        获取通义平台所需的配置键列表（已弃用：建议使用 llm_config 配置）

        返回:
            List[str]: 配置键的列表（对应 llm_config 中的 tongyi_cookies）
        """
        return ["TONGYI_COOKIES"]

    @classmethod
    def get_env_config_guide(cls) -> Dict[str, str]:
        """
        获取配置指导（已弃用：建议使用 llm_config 配置）

        返回:
            Dict[str, str]: 配置键名到配置指导的映射
        """
        return {
            "TONGYI_COOKIES": (
                "1. 登录通义千问网页版: https://tongyi.aliyun.com/\n"
                "2. 打开浏览器开发者工具 (F12)\n"
                '3. 切换到"网络"(Network)标签页\n'
                "4. 刷新页面或发送一条消息\n"
                "5. 找到 conversation 请求或任意发往 api.tongyi.com 的请求\n"
                '6. 在"请求标头"中复制完整的 Cookie 值'
            )
        }
