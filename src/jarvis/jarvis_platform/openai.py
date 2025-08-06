# -*- coding: utf-8 -*-
import json
import os
from typing import Dict, Generator, List, Tuple

from openai import OpenAI

from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_utils.output import OutputType, PrettyOutput


class OpenAIModel(BasePlatform):

    def __init__(self):
        """
        Initialize OpenAI model
        """
        super().__init__()
        self.system_message = ""
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            PrettyOutput.print("OPENAI_API_KEY 未设置", OutputType.WARNING)

        self.base_url = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
        self.model_name = os.getenv("JARVIS_MODEL") or "gpt-4o"

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.messages: List[Dict[str, str]] = []
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
            PrettyOutput.print(f"获取模型列表失败：{str(e)}", OutputType.ERROR)
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

            response = self.client.chat.completions.create(
                model=self.model_name,  # Use the configured model name
                messages=self.messages,  # type: ignore
                stream=True,
            )  # type: ignore

            full_response = ""
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    full_response += text
                    yield text

            # Add assistant reply to history
            self.messages.append({"role": "assistant", "content": full_response})

            return None

        except Exception as e:
            PrettyOutput.print(f"对话失败：{str(e)}", OutputType.ERROR)
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

            self.messages = state.get("messages", [])
            self.model_name = state.get("model_name", "gpt-4o")
            # atexit.register(self.delete_chat)
            self._saved = True

            PrettyOutput.print(f"从 {file_path} 成功恢复会话", OutputType.SUCCESS)
            return True
        except FileNotFoundError:
            PrettyOutput.print(f"会话文件未找到: {file_path}", OutputType.ERROR)
            return False
        except Exception as e:
            PrettyOutput.print(f"恢复会话失败: {str(e)}", OutputType.ERROR)
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
        获取OpenAI平台所需的环境变量键列表

        返回:
            List[str]: 环境变量键的列表
        """
        return ["OPENAI_API_KEY", "OPENAI_API_BASE"]

    @classmethod
    def get_env_config_guide(cls) -> Dict[str, str]:
        """
        获取环境变量配置指导

        返回:
            Dict[str, str]: 环境变量名到配置指导的映射
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
