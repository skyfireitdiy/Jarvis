# -*- coding: utf-8 -*-

# 人类交互平台实现模块

# 提供与真实人类交互的模拟接口

import random
import string
from typing import Generator, List, Tuple

from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_utils.input import get_multiline_input
from jarvis.jarvis_utils.output import OutputType, PrettyOutput


class HumanPlatform(BasePlatform):
    """人类交互平台实现，模拟大模型但实际上与人交互"""

    platform_name = "human"

    def get_model_list(self) -> List[Tuple[str, str]]:
        """获取支持的模型列表"""
        return [("human", "Human Interaction")]

    def __init__(self):
        """初始化人类交互平台"""
        super().__init__()
        self.conversation_id = ""  # 会话ID，用于标识当前对话
        self.model_name = "human"  # 默认模型名称
        self.system_message = ""  # 系统消息，用于初始化对话
        self.first_message = True

    def set_system_prompt(self, message: str):
        """设置系统消息"""
        self.system_message = message

    def set_model_name(self, model_name: str):
        """设置模型名称"""
        if model_name == "human":
            self.model_name = model_name
        else:
            PrettyOutput.print(f"错误：不支持的模型: {model_name}", OutputType.ERROR)

    def chat(self, message: str) -> Generator[str, None, None]:
        """发送消息并获取人类响应"""
        if not self.conversation_id:
            self.conversation_id = "".join(
                random.choices(string.ascii_letters + string.digits, k=8)
            )
            session_info = f"(会话ID: {self.conversation_id})"
        else:
            session_info = f"(会话ID: {self.conversation_id})"

        if self.system_message and self.first_message:
            prompt = f"{self.system_message}\n\n{message} {session_info}"
            self.first_message = False
        else:
            prompt = f"{message} {session_info}"

        # 将prompt复制到剪贴板
        import subprocess
        try:
            subprocess.run(['xsel', '-ib'], input=prompt.encode('utf-8'), check=True)
            PrettyOutput.print("提示已复制到剪贴板", OutputType.INFO)
        except subprocess.CalledProcessError as e:
            PrettyOutput.print(f"无法复制到剪贴板: {e}", OutputType.WARNING)

        response = get_multiline_input(prompt + "\n\n请回复:")
        yield response
        return None

    def upload_files(self, file_list: List[str]) -> bool:
        """文件上传功能，人类平台不需要实际处理"""
        PrettyOutput.print("人类交互平台不支持文件上传", OutputType.WARNING)
        return False

    def delete_chat(self) -> bool:
        """删除当前会话"""
        self.conversation_id = ""
        self.first_message = True
        return True

    def name(self) -> str:
        """平台名称"""
        return self.model_name

    def support_web(self) -> bool:
        """是否支持网页浏览功能"""
        return False

    def support_upload_files(self) -> bool:
        """是否支持文件上传功能"""
        return False
