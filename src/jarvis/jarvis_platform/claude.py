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
    def __init__(
        self,
        platform_type: str = "normal",
        agent: Optional[Any] = None,
    ):
        """
        Initialize Claude model

        参数:
            platform_type: 平台类型，可选值为 'normal'、'cheap' 或 'smart'
        """
        super().__init__(platform_type=platform_type, agent=agent)
        self.system_message = ""
        llm_config = self._llm_config or {}

        # 如果传入了 llm_config（非空字典），优先从 llm_config 读取，避免环境变量污染
        # 只有在 llm_config 中没有对应键时才从环境变量读取（向后兼容）
        # 注意：如果 llm_config 中某个键存在但值为 None 或空字符串，也使用该值，不从环境变量读取
        if llm_config:
            # 传入了 llm_config，优先使用 llm_config 中的值
            # 使用 get() 方法，如果键不存在返回 None，然后才从环境变量读取
            # 但是，如果 llm_config 是空字典 {}，说明是显式传入的空配置，应该从环境变量读取
            # 如果 llm_config 中有键但值为 None，也应该使用 None，不从环境变量读取
            if "anthropic_api_key" in llm_config:
                # 键存在，使用 llm_config 中的值（即使为 None 或空字符串）
                self.api_key = llm_config.get("anthropic_api_key")
            else:
                # 键不存在，从环境变量读取（向后兼容）
                self.api_key = os.getenv("ANTHROPIC_API_KEY")

            if "anthropic_base_url" in llm_config:
                # 键存在，使用 llm_config 中的值（即使为 None 或空字符串）
                self.base_url = llm_config.get("anthropic_base_url")
            else:
                # 键不存在，从环境变量读取（向后兼容）
                self.base_url = os.getenv("ANTHROPIC_BASE_URL")
        else:
            # 没有传入 llm_config，从环境变量读取（向后兼容）
            self.api_key = os.getenv("ANTHROPIC_API_KEY")
            self.base_url = os.getenv("ANTHROPIC_BASE_URL")

        # 只有当 llm_config 不为空但其中没有 anthropic_api_key，且环境变量也没有设置时，才打印警告
        # 如果 llm_config 为空字典，说明可能是配置还未加载完成，不打印警告（避免第一轮误报）
        if not self.api_key and llm_config:
            PrettyOutput.auto_print("⚠️ ANTHROPIC_API_KEY 未设置")

        # model_name 已在基类 BasePlatform.__init__ 中根据 platform_type 设置

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

    def set_messages(self, messages: List[Dict[str, str]]) -> None:
        """替换对话历史

        参数:
            messages: 新的对话历史列表，每个元素包含 role 和 content

        注意:
            - 会根据 messages 重新计算 conversation_turn（统计非 system 消息中的 user 消息数量）
            - 如果消息列表包含系统消息，会同时更新 system_message 属性
        """
        self.messages = messages

        # 如果消息列表包含系统消息，更新 system_message 属性
        for msg in messages:
            if msg.get("role") == "system":
                self.system_message = msg.get("content", "")
                break

        # 计算 conversation_turn：统计非 system 消息中的 user 消息数量
        non_system_messages = [msg for msg in messages if msg.get("role") != "system"]
        self._conversation_turn = sum(
            1 for msg in non_system_messages if msg.get("role") == "user"
        )

    def get_messages(self) -> List[Dict[str, str]]:
        """获取对话历史

        返回:
            List[Dict[str, str]]: 对话历史列表，每个元素包含 role 和 content
        """
        return self.messages

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
            设置后会立即添加到消息历史中
        """
        self.messages = []
        self.system_message = message
        self.messages.append({"role": "system", "content": self.system_message})

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

        # 记录添加用户消息前的消息列表长度，用于失败时回滚
        messages_before_user = len(self.messages)

        try:
            # 转换消息格式为 Anthropic 格式，同时提取系统消息
            anthropic_messages: List[MessageParam] = []
            system_content = None
            for msg in self.messages:
                role = msg.get("role")
                content = msg.get("content")
                if role == "system" and content:
                    # 提取系统消息用于 API 调用，并同步到 system_message 属性
                    system_content = content
                    self.system_message = content
                elif role == "user" and content:
                    anthropic_messages.append({"role": "user", "content": content})
                elif role == "assistant" and content:
                    anthropic_messages.append({"role": "assistant", "content": content})

            # 添加当前用户消息
            anthropic_messages.append({"role": "user", "content": message})

            # 累计完整响应
            accumulated_response = ""

            # 准备 system 参数：后端期望数组格式，而不是字符串
            system_param = None
            if system_content:
                # 将字符串转换为数组格式：[{"type": "text", "text": "系统消息内容"}]
                system_param = [{"type": "text", "text": system_content}]

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
            else:
                raise Exception("No response from model")

        except Exception as e:
            # 失败时回滚：移除已添加的用户消息（如果存在）
            if len(self.messages) > messages_before_user:
                self.messages = self.messages[:messages_before_user]
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
            如果设置了系统消息，会保留系统消息
        """
        if self.system_message:
            self.messages = [{"role": "system", "content": self.system_message}]
        else:
            self.messages = []
        return True

    def save(self, file_path: str) -> bool:
        """Save chat session to a file."""
        state: Dict[str, Any] = {
            "messages": self.messages,
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

            self.messages = state.get("messages", [])
            self.model_name = state.get("model_name", "claude-3-5-sonnet-20241022")
            # 处理start_commit信息（如果存在）
            # start_commit = state.get("start_commit", None)
            # 可以根据需要使用start_commit信息
            # atexit.register(self.delete_chat)
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

        保留所有system消息，并丢弃开头的10条非system消息。

        返回:
            bool: 如果成功腾出空间返回True，否则返回False
        """
        if not self.messages:
            return False

        # 分离system消息和非system消息
        system_messages = [msg for msg in self.messages if msg.get("role") == "system"]
        non_system_messages = [
            msg for msg in self.messages if msg.get("role") != "system"
        ]

        # 如果非system消息少于等于10条，无法裁剪
        if len(non_system_messages) <= 10:
            PrettyOutput.auto_print("⚠️ 警告：非system消息不足10条，无法裁剪")
            return False

        # 丢弃开头的10条非system消息
        trimmed_messages = non_system_messages[10:]
        trimmed_count = len(non_system_messages) - len(trimmed_messages)

        # 重新组装消息列表：system消息 + 裁剪后的非system消息
        self.messages = system_messages + trimmed_messages

        # 检查裁剪后是否有剩余token
        remaining_tokens = self.get_remaining_token_count()
        if remaining_tokens > 0:
            PrettyOutput.auto_print(
                f"✅ 裁剪成功：丢弃了{trimmed_count}条非system消息，剩余token: {remaining_tokens}"
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
