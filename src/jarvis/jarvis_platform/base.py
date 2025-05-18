# -*- coding: utf-8 -*-
from abc import ABC, abstractmethod
import re
from typing import List, Tuple

from yaspin import yaspin
from jarvis.jarvis_utils.config import get_max_input_token_count
from jarvis.jarvis_utils.embedding import split_text_into_chunks
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import get_context_token_count, is_context_overflow, while_success, while_true
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
        if is_context_overflow(message):
            PrettyOutput.print("错误：输入内容超过最大限制", OutputType.WARNING)
            return "错误：输入内容超过最大限制"

        if input_token_count > get_max_input_token_count():
            current_suppress_output = self.suppress_output
            self.set_suppress_output(True)
            max_chunk_size = get_max_input_token_count() - 1024  # 留出一些余量
            min_chunk_size = max_chunk_size // 2  # 最小块大小设为最大块大小的一半
            inputs = split_text_into_chunks(message, max_chunk_size, min_chunk_size)
            with yaspin(text="正在提交长上下文...", color="cyan") as spinner:
                prefix_prompt = f"""
                我将分多次提供大量内容，在我明确告诉你内容已经全部提供完毕之前，每次仅需要输出"已收到"，明白请输出"开始接收输入"。
                """
                while_true(lambda: while_success(lambda: self.chat(prefix_prompt), 5), 5)
                submit_count = 0
                for input in inputs:
                    submit_count += 1
                    spinner.text = f"正在提交第{submit_count}部分（共{len(inputs)}部分）"
                    while_true(lambda: while_success(lambda: self.chat(f"<part_content>{input}</part_content>请返回已收到"), 5), 5)
                spinner.text = "提交完成"
                spinner.ok("✅")
            self.set_suppress_output(current_suppress_output)
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
            PrettyOutput.section(
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
        return False
