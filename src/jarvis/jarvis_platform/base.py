# -*- coding: utf-8 -*-
import re
from abc import ABC, abstractmethod
from typing import Generator, List, Tuple

from rich import box  # type: ignore
from rich.live import Live  # type: ignore
from rich.panel import Panel  # type: ignore
from rich.text import Text  # type: ignore

from jarvis.jarvis_utils.config import (
    get_max_input_token_count,
    get_pretty_output,
    is_print_prompt,
)
from jarvis.jarvis_utils.embedding import split_text_into_chunks
from jarvis.jarvis_utils.globals import set_in_chat
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.tag import ct, ot
from jarvis.jarvis_utils.utils import get_context_token_count, while_success, while_true


class BasePlatform(ABC):
    """Base class for large language models"""

    def __init__(self):
        """Initialize model"""
        self.suppress_output = True  # 添加输出控制标志
        self.web = False  # 添加web属性，默认false
        self._saved = False

    def __del__(self):
        """Destroy model"""
        if not self._saved:
            self.delete_chat()

    @abstractmethod
    def set_model_name(self, model_name: str):
        """Set model name"""
        raise NotImplementedError("set_model_name is not implemented")

    def reset(self):
        """Reset model"""
        self.delete_chat()

    @abstractmethod
    def chat(self, message: str) -> Generator[str, None, None]:
        """Execute conversation"""
        raise NotImplementedError("chat is not implemented")

    @abstractmethod
    def upload_files(self, file_list: List[str]) -> bool:
        raise NotImplementedError("upload_files is not implemented")

    @abstractmethod
    def support_upload_files(self) -> bool:
        """Check if platform supports upload files"""
        return False

    def _chat(self, message: str):
        import time

        start_time = time.time()

        input_token_count = get_context_token_count(message)

        if input_token_count > get_max_input_token_count():
            max_chunk_size = get_max_input_token_count() - 1024  # 留出一些余量
            min_chunk_size = get_max_input_token_count() - 2048
            inputs = split_text_into_chunks(message, max_chunk_size, min_chunk_size)
            print("📤 正在提交长上下文...")
            prefix_prompt = f"""
            我将分多次提供大量内容，在我明确告诉你内容已经全部提供完毕之前，每次仅需要输出"已收到"，明白请输出"开始接收输入"。
            """
            while_true(lambda: while_success(lambda: self.chat(prefix_prompt), 5), 5)
            submit_count = 0
            length = 0
            response = ""
            for input in inputs:
                submit_count += 1
                length += len(input)
                print(
                    f"📤 正在提交第{submit_count}部分（共{len(inputs)}部分({length}/{len(message)})）"
                )

                response += "\n"
                for trunk in while_true(
                    lambda: while_success(
                        lambda: self.chat(
                            f"<part_content>{input}</part_content>\n\n请返回<已收到>，不需要返回其他任何内容"
                        ),
                        5,
                    ),
                    5,
                ):
                    response += trunk

                print(
                    f"📤 提交第{submit_count}部分完成，当前进度：{length}/{len(message)}"
                )
            print("✅ 提交完成")
            response += "\n" + while_true(
                lambda: while_success(
                    lambda: self._chat("内容已经全部提供完毕，请根据内容继续"), 5
                ),
                5,
            )
        else:
            response = ""

            text_content = Text()
            panel = Panel(
                text_content,
                title=f"[bold cyan]{self.name()}[/bold cyan]",
                subtitle="[dim]思考中...[/dim]",
                border_style="bright_blue",
                box=box.ROUNDED,
            )

            if not self.suppress_output:
                if get_pretty_output():
                    with Live(panel, refresh_per_second=10, transient=False) as live:
                        for s in self.chat(message):
                            response += s
                            text_content.append(s, style="bright_white")
                            panel.subtitle = "[yellow]正在回答...[/yellow]"
                            live.update(panel)
                        end_time = time.time()
                        duration = end_time - start_time
                        char_count = len(response)
                        # Calculate token count and tokens per second
                        try:
                            token_count = get_context_token_count(response)
                            tokens_per_second = (
                                token_count / duration if duration > 0 else 0
                            )
                        except Exception as e:
                            PrettyOutput.print(
                                f"Tokenization failed: {str(e)}", OutputType.WARNING
                            )
                            token_count = 0
                            tokens_per_second = 0
                        panel.subtitle = f"[bold green]✓ 对话完成耗时: {duration:.2f}秒, 输入字符数: {len(message)}, 输入Token数量: {input_token_count}, 输出字符数: {char_count}, 输出Token数量: {token_count}, 每秒Token数量: {tokens_per_second:.2f}[/bold green]"
                        live.update(panel)
                else:
                    for s in self.chat(message):
                        print(s, end="", flush=True)
                        response += s
                    print()
            else:
                for s in self.chat(message):
                    response += s
        # Keep original think tag handling
        response = re.sub(
            ot("think") + r".*?" + ct("think"), "", response, flags=re.DOTALL
        )
        response = re.sub(
            ot("thinking") + r".*?" + ct("thinking"), "", response, flags=re.DOTALL
        )
        return response

    def chat_until_success(self, message: str) -> str:
        """Chat with model until successful response"""
        try:
            set_in_chat(True)
            if not self.suppress_output and is_print_prompt():
                PrettyOutput.print(f"{message}", OutputType.USER)
            result: str = while_true(
                lambda: while_success(lambda: self._chat(message), 5), 5
            )
            from jarvis.jarvis_utils.globals import set_last_message

            set_last_message(result)
            return result
        finally:
            set_in_chat(False)

    @abstractmethod
    def name(self) -> str:
        """Model name"""
        raise NotImplementedError("name is not implemented")

    @classmethod
    @abstractmethod
    def platform_name(cls) -> str:
        """Platform name"""
        raise NotImplementedError("platform_name is not implemented")

    @abstractmethod
    def delete_chat(self) -> bool:
        """Delete chat"""
        raise NotImplementedError("delete_chat is not implemented")

    @abstractmethod
    def save(self, file_path: str) -> bool:
        """Save chat session to a file.

        Note:
            Implementations of this method should set `self._saved = True` upon successful saving
            to prevent the session from being deleted on object destruction.

        Args:
            file_path: The path to save the session file.

        Returns:
            True if saving is successful, False otherwise.
        """
        raise NotImplementedError("save is not implemented")

    @abstractmethod
    def restore(self, file_path: str) -> bool:
        """Restore chat session from a file.

        Args:
            file_path: The path to restore the session file from.

        Returns:
            True if restoring is successful, False otherwise.
        """
        raise NotImplementedError("restore is not implemented")

    @abstractmethod
    def set_system_prompt(self, message: str):
        """Set system message"""
        raise NotImplementedError("set_system_prompt is not implemented")

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
