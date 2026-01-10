# -*- coding: utf-8 -*-
import json
import os
from typing import Any
from typing import Dict
from typing import Optional
from typing import Generator
from typing import List
from typing import Tuple

from anthropic import Anthropic
from anthropic.types import MessageParam

from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_utils.output import PrettyOutput


class ClaudeModel(BasePlatform):
    def __init__(self, llm_config: Optional[Dict[str, Any]] = None):
        """
        Initialize Claude model

        参数:
            llm_config: LLM配置字典，包含 anthropic_api_key, anthropic_base_url 等
        """
        super().__init__()
        self.system_message = ""
        llm_config = llm_config or {}

        # API Key 配置
        if llm_config:
            if "anthropic_api_key" in llm_config:
                self.api_key = llm_config.get("anthropic_api_key")
            else:
                self.api_key = os.getenv("ANTHROPIC_API_KEY")
        else:
            self.api_key = os.getenv("ANTHROPIC_API_KEY")

        # Base URL 配置
        if llm_config:
            if "anthropic_base_url" in llm_config:
                self.base_url = llm_config.get("anthropic_base_url")
            else:
                self.base_url = os.getenv("ANTHROPIC_BASE_URL")
        else:
            self.base_url = os.getenv("ANTHROPIC_BASE_URL")

        # API Key 警告
        if not self.api_key and llm_config:
            PrettyOutput.auto_print("⚠️ ANTHROPIC_API_KEY 未设置")

        # 模型名称
        self.model_name = os.getenv("model") or "claude-3-5-sonnet-20241022"

        # 初始化 Anthropic 客户端
        self.client = None
        try:
            if self.base_url:
                self.client = Anthropic(api_key=self.api_key, base_url=self.base_url)
            else:
                self.client = Anthropic(api_key=self.api_key)
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 初始化 Anthropic 客户端失败: {e}")

        # 消息历史
        self.messages: List[Dict[str, str]] = []
        self.system_message = ""

    def get_model_list(self) -> List[Tuple[str, str]]:
        """
        获取可用的 Claude 模型列表

        返回:
            List[Tuple[str, str]]: 模型ID和名称的元组列表

        异常:
            当API调用失败时会打印错误信息并返回空列表
        """
        if not self.client:
            PrettyOutput.auto_print("❌ Anthropic 客户端未初始化")
            return []

        try:
            # 尝试使用models API获取实际的模型列表
            model_response = self.client.models.list()
            models = []
            for model in model_response.data:
                model_id = model.id if hasattr(model, "id") else str(model)
                model_name = model.id if hasattr(model, "id") else str(model)
                models.append((model_id, model_name))

            if models:
                PrettyOutput.auto_print("✅ 成功从API获取模型列表")
                return models
            else:
                PrettyOutput.auto_print("⚠️ API响应中没有模型数据")
                return []
        except AttributeError:
            # models API 不存在或不支持
            PrettyOutput.auto_print("❌ 模型列表API不可用")
            return []
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 获取模型列表失败: {e}")
            return []

    def set_model_name(self, model_name: str):
        """
        设置当前使用的模型名称

        参数:
            model_name: 要设置的模型名称
        """
        self.model_name = model_name

    def set_system_prompt(self, message: str):
        """
        设置系统消息(角色设定)

        参数:
            message: 系统消息内容

        说明:
            Claude 使用单独的 system 参数，不是消息列表的一部分
        """
        self.system_message = message

    def chat(self, message: str) -> Generator[str, None, None]:
        """
        执行对话并返回生成器

        参数:
            message: 用户输入的消息内容

        返回:
            Generator[str, None, None]: 生成器，逐块返回AI响应内容

        异常:
            当API调用失败时会抛出异常并打印错误信息
        """
        if not self.client:
            PrettyOutput.auto_print("❌ Anthropic 客户端未初始化")
            raise Exception("Anthropic client not initialized")

        try:
            # 转换消息格式为 Anthropic 格式
            anthropic_messages: List[MessageParam] = []
            for msg in self.messages:
                role = msg.get("role")
                content = msg.get("content")
                if role == "user" and content:
                    anthropic_messages.append({"role": "user", "content": content})
                elif role == "assistant" and content:
                    anthropic_messages.append({"role": "assistant", "content": content})

            # 添加当前用户消息
            anthropic_messages.append({"role": "user", "content": message})

            # 累计完整响应
            accumulated_response = ""

            # 准备 system 参数：后端期望数组格式，而不是字符串
            system_param = None
            if self.system_message:
                # 将字符串转换为数组格式：[{"type": "text", "text": "系统消息内容"}]
                system_param = [{"type": "text", "text": self.system_message}]

            # 调用 Anthropic API
            from typing import Union

            stream_kwargs: Dict[
                str,
                Union[
                    str,
                    List[MessageParam],
                    int,
                    List[List[Dict[str, str]]],
                    List[Dict[str, str]],
                ],
            ] = {
                "model": self.model_name,
                "messages": anthropic_messages,
                "max_tokens": 4096,
            }
            if system_param:
                stream_kwargs["system"] = system_param

            with self.client.messages.stream(**stream_kwargs) as stream:  # type: ignore
                full_response = ""
                for text in stream.text_stream:
                    full_response += text
                    accumulated_response += text
                    yield text

            # 将响应添加到消息历史
            if accumulated_response:
                self.messages.append({"role": "user", "content": message})
                self.messages.append(
                    {"role": "assistant", "content": accumulated_response}
                )

            return None

        except Exception as e:
            PrettyOutput.auto_print(f"❌ 对话失败：{str(e)}")
            raise Exception(f"Chat failed: {str(e)}")

    def name(self) -> str:
        """
        获取当前使用的模型名称

        返回:
            str: 当前配置的模型名称
        """
        return self.model_name

    @classmethod
    def platform_name(cls) -> str:
        """
        获取当前平台的名称

        返回:
            str: 当前平台的名称
        """
        return "claude"

    def delete_chat(self) -> bool:
        """
        删除当前对话历史

        返回:
            bool: 操作是否成功

        说明:
            系统消息会保留在 system_message 中
        """
        self.messages = []
        return True

    def save(self, file_path: str) -> bool:
        """
        Save chat session to a file.

        参数:
            file_path: 保存会话文件的路径

        返回:
            bool: 保存是否成功
        """
        state: Dict[str, Any] = {
            "messages": self.messages,
            "model_name": self.model_name,
            "system_message": self.system_message,
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
        """
        Restore chat session from a file.

        参数:
            file_path: 要恢复会话文件的路径

        返回:
            bool: 恢复是否成功
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                state = json.load(f)

            self.messages = state.get("messages", [])
            self.model_name = state.get("model_name", "claude-3-5-sonnet-20241022")
            self.system_message = state.get("system_message", "")
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

    def trim_messages(self) -> bool:
        """裁剪消息历史以腾出token空间

        Claude的system_message单独存储，不在messages列表中。
        丢弃开头的10条非system消息（user/assistant消息）。

        返回:
            bool: 如果成功腾出空间返回True，否则返回False
        """
        if not self.messages:
            return False

        # Claude的messages列表只包含user和assistant消息
        # 如果消息少于等于10条，无法裁剪
        if len(self.messages) <= 10:
            PrettyOutput.auto_print("⚠️ 警告：消息不足10条，无法裁剪")
            return False

        # 记录原始消息数量
        original_count = len(self.messages)

        # 丢弃开头的10条消息
        self.messages = self.messages[10:]
        trimmed_count = original_count - len(self.messages)

        # 检查裁剪后是否有剩余token
        remaining_tokens = self.get_remaining_token_count()
        if remaining_tokens > 0:
            PrettyOutput.auto_print(
                f"✅ 裁剪成功：丢弃了{trimmed_count}条消息，剩余token: {remaining_tokens}"
            )
            return True
        else:
            PrettyOutput.auto_print(
                f"⚠️ 警告：已裁剪{trimmed_count}条消息，但仍无剩余token"
            )
            return False

    @classmethod
    def get_required_env_keys(cls) -> List[str]:
        """
        获取Claude平台所需的配置键列表

        返回:
            List[str]: 配置键的列表（对应 llm_config 中的 anthropic_api_key）
        """
        return ["ANTHROPIC_API_KEY"]

    @classmethod
    def get_env_config_guide(cls) -> Dict[str, str]:
        """
        获取配置指导

        返回:
            Dict[str, str]: 配置键名到配置指导的映射
        """
        return {
            "ANTHROPIC_API_KEY": (
                "请输入您的 Anthropic API Key:\n"
                "获取方式:\n"
                "1. 登录 Anthropic 控制台: https://console.anthropic.com/\n"
                "2. 进入 API Keys 页面\n"
                "3. 创建新的 API Key\n"
                "4. 复制 API Key"
            ),
        }

    @classmethod
    def get_env_defaults(cls) -> Dict[str, str]:
        """
        获取Claude平台环境变量的默认值

        返回:
            Dict[str, str]: 环境变量默认值的字典
        """
        return {}
