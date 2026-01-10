# -*- coding: utf-8 -*-
import json
import os
from typing import Any
from typing import Dict
from typing import Generator
from typing import List
from typing import Optional
from typing import Tuple

from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_utils import http
from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_utils.tag import ct
from jarvis.jarvis_utils.tag import ot
from jarvis.jarvis_utils.utils import while_success


class YuanbaoPlatform(BasePlatform):
    """Hunyuan模型实现"""

    def get_model_list(self) -> List[Tuple[str, str]]:
        """获取支持的模型列表"""
        return [
            ("deep_seek", "DeepSeek-R1"),
            ("deep_seek_v3", "DeepSeek-v3"),
            ("hunyuan_gpt_175B_0404", "Tencent Hunyuan"),
            ("hunyuan_t1", "Tencent Hunyuan-T1"),
        ]

    def __init__(self, llm_config: Optional[Dict[str, Any]] = None):
        """
        初始化Hunyuan模型

        参数:
            llm_config: LLM配置字典，包含 yuanbao_cookies 等
        """
        super().__init__()
        PrettyOutput.auto_print(
            "⚠️ 警告：yuanbao 平台将在未来版本中被废弃，建议迁移到 openai 或 claude 平台。"
        )
        self.conversation_id = ""  # 会话ID，用于标识当前对话
        llm_config = llm_config or {}

        # 从 llm_config 获取配置，如果没有则从环境变量获取（向后兼容）
        self.cookies = llm_config.get("yuanbao_cookies") or os.getenv("YUANBAO_COOKIES")
        self.agent_id = "naQivTmsDa"

        if not self.cookies:
            raise ValueError(
                "yuanbao_cookies 未设置。请在 llm_config 中配置 yuanbao_cookies 或设置 YUANBAO_COOKIES 环境变量。"
            )

        self.system_message = ""  # 系统消息，用于初始化对话
        self.first_chat = True  # 标识是否为第一次对话
        self.model_name = "deep_seek_v3"  # 默认模型名称，使用下划线保持一致

    def set_system_prompt(self, message: str):
        """设置系统消息"""
        self.system_message = message

    def set_model_name(self, model_name: str):
        # 模型映射表，可以根据需要扩展
        model_mapping = [m[0] for m in self.get_model_list()]

        if model_name in model_mapping:
            self.model_name = model_name
        else:
            PrettyOutput.auto_print(f"❌ 错误：不支持的模型: {model_name}")

    def _get_base_headers(self):
        """获取API请求的基础头部信息"""
        return {
            "Host": "yuanbao.tencent.com",
            "X-Language": "zh-CN",
            "X-Requested-With": "XMLHttpRequest",
            "chat_version": "v1",
            "X-Instance-ID": "5",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "sec-ch-ua-mobile": "?0",
            "Origin": "https://yuanbao.tencent.com",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0",
            "Referer": f"https://yuanbao.tencent.com/chat/{self.agent_id}",
            "X-Source": "web",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "Cookie": self.cookies,
        }

    def _create_conversation(self) -> bool:
        """创建一个新的对话会话"""
        url = "https://yuanbao.tencent.com/api/user/agent/conversation/create"

        headers = self._get_base_headers()

        payload = json.dumps({"agentId": self.agent_id})

        try:
            response = while_success(
                lambda: http.post(url, headers=headers, data=payload),
            )
            response_json = response.json()

            if "id" in response_json:
                self.conversation_id = response_json["id"]
                return True
            else:
                PrettyOutput.auto_print(f"❌ 错误：创建会话失败，响应: {response_json}")
                return False
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 错误：创建会话失败：{e}")
            return False

    def trim_messages(self) -> bool:
        """未实现：不支持裁剪消息历史

        返回:
            bool: 返回False表示不支持裁剪
        """
        return False

    def chat(self, message: str) -> Generator[str, None, None]:
        """发送消息并获取响应，可选文件附件

        参数:
            message: 要发送的消息文本

        返回:
            模型的响应
        """
        if not self.conversation_id:
            if not self._create_conversation():
                raise Exception("Failed to create conversation session")

        url = f"https://yuanbao.tencent.com/api/chat/{self.conversation_id}"

        headers = self._get_base_headers()

        chat_model_ext_info = {
            "modelId": self.model_name,
            "subModelId": "",
            "supportFunctions": ["autoInternetSearch"],
        }

        # 准备消息内容
        payload = {
            "model": "gpt_175B_0404",
            "prompt": message,
            "plugin": "Adaptive",
            "displayPrompt": message,
            "displayPromptType": 1,
            "options": {
                "imageIntention": {
                    "needIntentionModel": True,
                    "backendUpdateFlag": 2,
                    "intentionStatus": True,
                }
            },
            "agentId": self.agent_id,
            "supportHint": 1,
            "version": "v2",
            "supportFunctions": chat_model_ext_info["supportFunctions"],
            "chatModelId": self.model_name,
        }

        if self.first_chat:
            payload["chatModelExtInfo"] = (json.dumps(chat_model_ext_info),)

        # 添加系统消息（如果是第一次对话）
        if self.first_chat and self.system_message:
            payload["prompt"] = f"{self.system_message}\n\n{message}"
            payload["displayPrompt"] = payload["prompt"]

        try:
            # 使用新的stream_post接口发送消息请求，获取流式响应
            response_stream = while_success(
                lambda: http.stream_post(url, headers=headers, json=payload),
            )

            in_thinking = False

            # 处理流式响应
            for line in response_stream:
                if not line.strip():
                    continue

                # SSE格式的行通常以"data: "开头
                if line.startswith("data: "):
                    try:
                        data_str = line[6:]  # 移除"data: "前缀

                        # 检查结束标志
                        if data_str == "[DONE]":
                            self.first_chat = False
                            return

                        data = json.loads(data_str)

                        # 处理文本类型的消息
                        if data.get("type") == "text":
                            if in_thinking:
                                yield f"{ct('think')}\n"
                                in_thinking = False
                            msg = data.get("msg", "")
                            if msg:
                                yield msg

                        # 处理思考中的消息
                        elif data.get("type") == "think":
                            if not in_thinking:
                                yield f"{ot('think')}\n"
                                in_thinking = True
                            think_content = data.get("content", "")
                            if think_content:
                                yield think_content

                    except Exception:
                        pass
                else:
                    try:
                        data = json.loads(line)
                        if "msg" in data:
                            yield data["msg"]
                    except Exception:
                        pass

            self.first_chat = False
            return

        except Exception as e:
            raise Exception(f"对话失败: {str(e)}")

    def delete_chat(self) -> bool:
        """删除当前会话"""
        if not self.conversation_id:
            return True  # 如果没有会话ID，视为删除成功

        # Hunyuan使用专门的clear API来清除会话
        url = "https://yuanbao.tencent.com/api/user/agent/conversation/v1/clear"

        # 为这个请求获取基础头部
        headers = self._get_base_headers()

        # 更新X-AgentID头部，需要包含会话ID
        headers.update({"X-AgentID": f"{self.agent_id}/{self.conversation_id}"})

        # 创建请求体，包含要删除的会话ID
        payload = {"conversationIds": [self.conversation_id]}

        try:
            response = while_success(
                lambda: http.post(url, headers=headers, json=payload),
            )

            if response.status_code == 200:
                self.conversation_id = ""
                self.first_chat = True
                return True
            else:
                PrettyOutput.auto_print(f"⚠️ 删除会话失败: HTTP {response.status_code}")
                if hasattr(response, "text"):
                    PrettyOutput.auto_print(f"⚠️ 响应: {response.text}")
                return False
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 删除会话时发生错误: {str(e)}")
            return False

    def save(self, file_path: str) -> bool:
        """Save chat session to a file."""
        if not self.conversation_id:
            PrettyOutput.auto_print("⚠️ 没有活动的会话可供保存")
            return False

        state: Dict[str, Any] = {
            "conversation_id": self.conversation_id,
            "system_message": self.system_message,
            "first_chat": self.first_chat,
            "model_name": self.model_name,
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

            self.conversation_id = state.get("conversation_id", "")
            self.system_message = state.get("system_message", "")
            self.first_chat = state.get("first_chat", True)
            self.model_name = state.get("model_name", "deep_seek_v3")
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
        """模型名称"""
        return self.model_name

    @classmethod
    def platform_name(cls) -> str:
        """平台名称"""
        return "yuanbao"

    @classmethod
    def get_required_env_keys(cls) -> List[str]:
        """
        获取元宝平台所需的配置键列表（已弃用：建议使用 llm_config 配置）

        返回:
            List[str]: 配置键的列表（对应 llm_config 中的 yuanbao_cookies）
        """
        return ["YUANBAO_COOKIES"]

    @classmethod
    def get_env_config_guide(cls) -> Dict[str, str]:
        """
        获取配置指导（已弃用：建议使用 llm_config 配置）

        返回:
            Dict[str, str]: 配置键名到配置指导的映射
        """
        return {
            "YUANBAO_COOKIES": (
                "1. 登录腾讯元宝网页版: https://yuanbao.tencent.com/\n"
                "2. 打开浏览器开发者工具 (F12)\n"
                '3. 切换到"网络"(Network)标签页\n'
                "4. 刷新页面，找到任意一个发往 yuanbao.tencent.com 的请求\n"
                '5. 在"请求标头"中复制完整的 Cookie 值'
            )
        }
