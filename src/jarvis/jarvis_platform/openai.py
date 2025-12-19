# -*- coding: utf-8 -*-
import json
import os
from typing import Any
from typing import Dict
from typing import Generator
from typing import List
from typing import Optional
from typing import Tuple

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_utils.output import PrettyOutput


class OpenAIModel(BasePlatform):
    def __init__(self, llm_config: Optional[Dict[str, Any]] = None):
        """
        Initialize OpenAI model

        参数:
            llm_config: LLM配置字典，包含 openai_api_key, openai_api_base, openai_extra_headers 等
        """
        super().__init__()
        self.system_message = ""
        llm_config = llm_config or {}

        # 如果传入了 llm_config（非空字典），优先从 llm_config 读取，避免环境变量污染
        # 只有在 llm_config 中没有对应键时才从环境变量读取（向后兼容）
        # 注意：如果 llm_config 中某个键存在但值为 None 或空字符串，也使用该值，不从环境变量读取
        if llm_config:
            # 传入了 llm_config，优先使用 llm_config 中的值
            # 使用 get() 方法，如果键不存在返回 None，然后才从环境变量读取
            # 但是，如果 llm_config 是空字典 {}，说明是显式传入的空配置，应该从环境变量读取
            # 如果 llm_config 中有键但值为 None，也应该使用 None，不从环境变量读取
            if "openai_api_key" in llm_config:
                # 键存在，使用 llm_config 中的值（即使为 None 或空字符串）
                self.api_key = llm_config.get("openai_api_key")
            else:
                # 键不存在，从环境变量读取（向后兼容）
                self.api_key = os.getenv("OPENAI_API_KEY")

            if "openai_api_base" in llm_config:
                # 键存在，使用 llm_config 中的值（即使为 None 或空字符串）
                self.base_url = llm_config.get("openai_api_base")
            else:
                # 键不存在，从环境变量读取（向后兼容）
                self.base_url = os.getenv(
                    "OPENAI_API_BASE", "https://api.openai.com/v1"
                )
        else:
            # 没有传入 llm_config，从环境变量读取（向后兼容）
            self.api_key = os.getenv("OPENAI_API_KEY")
            self.base_url = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")

        # 只有当 llm_config 不为空但其中没有 openai_api_key，且环境变量也没有设置时，才打印警告
        # 如果 llm_config 为空字典，说明可能是配置还未加载完成，不打印警告（避免第一轮误报）
        if not self.api_key and llm_config:
            PrettyOutput.auto_print("⚠️ OPENAI_API_KEY 未设置")

        self.model_name = os.getenv("model") or "gpt-4o"

        # Optional: Inject extra HTTP headers via llm_config or environment variable
        # Expected format: openai_extra_headers='{"Header-Name": "value", "X-Trace": "abc"}'
        headers_value = llm_config.get("openai_extra_headers")
        if headers_value is None:
            headers_str = os.getenv("OPENAI_EXTRA_HEADERS")
        else:
            headers_str = (
                headers_value
                if isinstance(headers_value, str)
                else json.dumps(headers_value)
            )

        self.extra_headers: Dict[str, str] = {}
        if headers_str:
            try:
                parsed = (
                    json.loads(headers_str)
                    if isinstance(headers_str, str)
                    else headers_str
                )
                if isinstance(parsed, dict):
                    # Ensure all header keys/values are strings
                    self.extra_headers = {str(k): str(v) for k, v in parsed.items()}
                else:
                    PrettyOutput.auto_print(
                        "⚠️ openai_extra_headers 应为 JSON 对象，如 {'X-Source':'jarvis'}"
                    )
            except Exception as e:
                PrettyOutput.auto_print(f"⚠️ 解析 openai_extra_headers 失败: {e}")

        # Initialize OpenAI client, try to pass default headers if SDK supports it
        try:
            if self.extra_headers:
                self.client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    default_headers=self.extra_headers,
                )
            else:
                self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        except TypeError:
            # Fallback: SDK version may not support default_headers
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            if self.extra_headers:
                PrettyOutput.auto_print(
                    "⚠️ 当前 OpenAI SDK 不支持 default_headers，未能注入额外 HTTP 头"
                )
        self.messages: List[ChatCompletionMessageParam] = []
        self.system_message = ""

    def upload_files(self, file_list: List[str]) -> bool:
        """
        上传文件到OpenAI平台

        参数:
            file_list: 需要上传的文件路径列表

        返回:
            bool: 上传是否成功 (当前实现始终返回False)
        """
        return False

    def get_model_list(self) -> List[Tuple[str, str]]:
        """
        获取可用的OpenAI模型列表

        返回:
            List[Tuple[str, str]]: 模型ID和名称的元组列表

        异常:
            当API调用失败时会打印错误信息并返回空列表
        """
        try:
            models = self.client.models.list()
            model_list = []
            for model in models:
                model_list.append((model.id, model.id))
            return model_list
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 获取模型列表失败：{str(e)}")
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
        try:
            # Add user message to history
            self.messages.append({"role": "user", "content": message})

            # 累计完整响应
            accumulated_response = ""

            # 循环处理，直到不是因为长度限制而结束
            while True:
                response = self.client.chat.completions.create(
                    model=self.model_name,  # Use the configured model name
                    messages=self.messages,
                    stream=True,
                )

                full_response = ""
                finish_reason = None

                for chunk in response:
                    if chunk.choices and len(chunk.choices) > 0:
                        choice = chunk.choices[0]

                        # 检查 finish_reason（通常在最后一个 chunk 中）
                        if choice.finish_reason:
                            finish_reason = choice.finish_reason

                        # 获取内容增量
                        if choice.delta and choice.delta.content:
                            text = choice.delta.content
                            full_response += text
                            accumulated_response += text
                            yield text

                # 如果是因为长度限制而结束，继续获取剩余内容
                if finish_reason == "length":
                    # 将已获取的内容追加到消息历史中，以便下次请求时模型知道已生成的内容
                    if self.messages and self.messages[-1].get("role") == "assistant":
                        # 追加到现有的 assistant 消息
                        last_content = self.messages[-1]["content"]
                        if isinstance(last_content, str):
                            self.messages[-1]["content"] = last_content + full_response
                        else:
                            # 如果content不是字符串，创建新的消息
                            self.messages.append(
                                {"role": "assistant", "content": full_response}
                            )
                    else:
                        # 创建新的 assistant 消息
                        self.messages.append(
                            {"role": "assistant", "content": full_response}
                        )

                    # 添加一个继续请求的用户消息，让模型继续生成
                    self.messages.append({"role": "user", "content": "请继续。"})
                    # 继续循环，获取剩余内容
                    continue
                else:
                    # 正常结束（stop、null 或其他原因）
                    # 将完整响应添加到消息历史
                    if accumulated_response:
                        if (
                            self.messages
                            and self.messages[-1].get("role") == "assistant"
                        ):
                            # 如果最后一条是 assistant 消息，追加本次的内容
                            last_content = self.messages[-1]["content"]
                            if isinstance(last_content, str):
                                self.messages[-1]["content"] = (
                                    last_content + full_response
                                )
                            else:
                                # 如果content不是字符串，创建新的消息
                                self.messages.append(
                                    {
                                        "role": "assistant",
                                        "content": accumulated_response,
                                    }
                                )
                        else:
                            # 创建新的 assistant 消息，使用累计的完整响应
                            self.messages.append(
                                {"role": "assistant", "content": accumulated_response}
                            )
                    break

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
        return "openai"

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
        state = {
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
            self.model_name = state.get("model_name", "gpt-4o")
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

    def support_web(self) -> bool:
        """
        检查是否支持网页访问功能

        返回:
            bool: 当前是否支持网页访问 (OpenAI平台始终返回False)
        """
        return False

    def support_upload_files(self) -> bool:
        """
        检查是否支持上传文件功能

        返回:
            bool: 当前是否支持上传文件 (OpenAI平台始终返回False)
        """
        return False

    @classmethod
    def get_required_env_keys(cls) -> List[str]:
        """
        获取OpenAI平台所需的配置键列表（已弃用：建议使用 llm_config 配置）

        返回:
            List[str]: 配置键的列表（对应 llm_config 中的 openai_api_key, openai_api_base）
        """
        return ["OPENAI_API_KEY", "OPENAI_API_BASE"]

    @classmethod
    def get_env_config_guide(cls) -> Dict[str, str]:
        """
        获取配置指导（已弃用：建议使用 llm_config 配置）

        返回:
            Dict[str, str]: 配置键名到配置指导的映射
        """
        return {
            "OPENAI_API_KEY": (
                "请输入您的 OpenAI API Key:\n"
                "获取方式一（官方）:\n"
                "1. 登录 OpenAI 平台: https://platform.openai.com/\n"
                "2. 进入 API Keys 页面\n"
                "3. 创建新的 API Key 或使用现有的\n"
                "4. 复制 API Key (以 sk- 开头)\n"
                "\n获取方式二（第三方代理）:\n"
                "如果使用第三方代理服务，请从代理服务商处获取 API Key"
            ),
            "OPENAI_API_BASE": (
                "请输入 API Base URL:\n"
                "- 官方 API: https://api.openai.com/v1\n"
                "- 如使用代理或第三方服务，请输入对应的 Base URL\n"
                "- 例如: https://your-proxy.com/v1"
            ),
        }

    @classmethod
    def get_env_defaults(cls) -> Dict[str, str]:
        """
        获取OpenAI平台环境变量的默认值

        返回:
            Dict[str, str]: 环境变量默认值的字典
        """
        return {"OPENAI_API_BASE": "https://api.openai.com/v1"}
