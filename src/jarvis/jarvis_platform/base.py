# -*- coding: utf-8 -*-
from abc import ABC, abstractmethod
import re
from sys import prefix
from typing import List, Tuple

from httpx import get
from networkx import prefix_tree
from torch import le
from jarvis.jarvis_utils.config import get_max_big_content_size, get_max_input_token_count
from jarvis.jarvis_utils.embedding import split_text_into_chunks
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import get_context_token_count, while_success, while_true
from jarvis.jarvis_utils.tag import ot, ct


class BasePlatform(ABC):
    """Base class for large language models"""

    def __init__(self):
        """Initialize model"""
        self.suppress_output = True  # 添加输出控制标志
        self.web = False  # 添加web属性，默认false

    def __del__(self):
        """Destroy model"""
        self.delete_chat()

    @abstractmethod
    def set_model_name(self, model_name: str):
        """Set model name"""
        raise NotImplementedError("set_model_name is not implemented")

    def reset(self):
        """Reset model"""
        self.delete_chat()

    @abstractmethod
    def chat(self, message: str) -> str:
        """Execute conversation"""
        raise NotImplementedError("chat is not implemented")
    
    @abstractmethod
    def upload_files(self, file_list: List[str]) -> bool:
        raise NotImplementedError("upload_files is not implemented")


    
    def _chat(self, message: str):
        import time
        start_time = time.time()

        input_token_count = get_context_token_count(message)

        if input_token_count > get_max_big_content_size():
            PrettyOutput.print("错误：输入内容超过最大限制", OutputType.WARNING)
            return "错误：输入内容超过最大限制"

        if input_token_count > get_max_input_token_count():
            inputs = split_text_into_chunks(message, get_max_input_token_count() - 1024, get_max_input_token_count() - 2048)
            prefix_prompt = f"""
            我将分多次提供大量内容，在我明确告诉你内容已经全部提供完毕之前，每次仅需要输出“已收到”，明白请输出“开始接收输入”。
            """
            while_true(lambda: while_success(lambda: self.chat(prefix_prompt), 5), 5)
            submit_count = 0
            for input in inputs:
                submit_count += 1
                PrettyOutput.print(f"提交{submit_count}/{len(inputs)}次", OutputType.INFO)
                while_true(lambda: while_success(lambda: self.chat(f"<part_content>{input}</part_content>请返回已收到"), 5), 5)
            response = while_true(lambda: while_success(lambda: self.chat("内容已经全部提供完毕，请继续"), 5), 5)
        else:
            response = self.chat(message)

        end_time = time.time()
        duration = end_time - start_time
        char_count = len(response)

        # Calculate token count and tokens per second
        try:
            token_count = get_context_token_count(response)
            tokens_per_second = token_count / duration if duration > 0 else 0
        except Exception as e:
            PrettyOutput.print(f"Tokenization failed: {str(e)}", OutputType.WARNING)
            token_count = 0
            tokens_per_second = 0

        # Print statistics
        if not self.suppress_output:
            PrettyOutput.print(
                f"对话完成 - 耗时: {duration:.2f}秒, 输入字符数: {len(message)}, 输入Token数量: {input_token_count}, 输出字符数: {char_count}, 输出Token数量: {token_count}, 每秒Token数量: {tokens_per_second:.2f}",
                OutputType.INFO,
            )

        # Keep original think tag handling
        response = re.sub(ot("think")+r'.*?'+ct("think"), '', response, flags=re.DOTALL)
        return response
    
    def chat_until_success(self, message: str) -> str:
        return while_true(lambda: while_success(lambda: self._chat(message), 5), 5)

    @abstractmethod
    def name(self) -> str:
        """Model name"""
        raise NotImplementedError("name is not implemented")

    @abstractmethod
    def delete_chat(self)->bool:
        """Delete chat"""
        raise NotImplementedError("delete_chat is not implemented")

    @abstractmethod
    def set_system_message(self, message: str):
        """Set system message"""
        raise NotImplementedError("set_system_message is not implemented")

    @abstractmethod
    def get_model_list(self) -> List[Tuple[str, str]]:
        """Get model list"""
        raise NotImplementedError("get_model_list is not implemented")

    def set_suppress_output(self, suppress: bool):
        """Set whether to suppress output"""
        self.suppress_output = suppress

    def set_web(self, web: bool):
        """Set web flag"""
        self.web = web

    @abstractmethod
    def support_web(self) -> bool:
        """Check if platform supports web functionality"""
        raise NotImplementedError("support_web is not implemented")
