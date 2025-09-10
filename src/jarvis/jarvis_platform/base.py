# -*- coding: utf-8 -*-
import re
from abc import ABC, abstractmethod
from types import TracebackType
from typing import Dict, Generator, List, Optional, Tuple, Type

from typing_extensions import Self

from rich import box  # type: ignore
from rich.live import Live  # type: ignore
from rich.panel import Panel  # type: ignore
from rich.status import Status  # type: ignore
from rich.text import Text  # type: ignore

from jarvis.jarvis_utils.config import (
    get_max_input_token_count,
    get_pretty_output,
    is_print_prompt,
    is_immediate_abort,
)
from jarvis.jarvis_utils.embedding import split_text_into_chunks
from jarvis.jarvis_utils.globals import set_in_chat, get_interrupt, console
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
        self.model_group: Optional[str] = None

    def __enter__(self) -> Self:
        """Enter context manager"""
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """Exit context manager"""
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

        if input_token_count > get_max_input_token_count(self.model_group):
            max_chunk_size = (
                get_max_input_token_count(self.model_group) - 1024
            )  # 留出一些余量
            min_chunk_size = get_max_input_token_count(self.model_group) - 2048
            inputs = split_text_into_chunks(message, max_chunk_size, min_chunk_size)
            PrettyOutput.print(
                f"长上下文，分批提交，共{len(inputs)}部分...", OutputType.INFO
            )
            prefix_prompt = """
            我将分多次提供大量内容，在我明确告诉你内容已经全部提供完毕之前，每次仅需要输出"已收到"，明白请输出"开始接收输入"。
            """
            while_true(lambda: while_success(lambda: self._chat(prefix_prompt), 5), 5)
            submit_count = 0
            length = 0
            response = ""
            for input in inputs:
                submit_count += 1
                length += len(input)

                response += "\n"
                for trunk in while_true(
                    lambda: while_success(
                        lambda: self._chat(
                            f"<part_content>{input}</part_content>\n\n请返回<已收到>，不需要返回其他任何内容"
                        ),
                        5,
                    ),
                    5,
                ):
                    response += trunk

            PrettyOutput.print("提交完成", OutputType.SUCCESS)
            response += "\n" + while_true(
                lambda: while_success(
                    lambda: self._chat("内容已经全部提供完毕，请根据内容继续"), 5
                ),
                5,
            )
        else:
            response = ""

            if not self.suppress_output:
                if get_pretty_output():
                    chat_iterator = self.chat(message)
                    first_chunk = None

                    with Status(
                        f"🤔 {self.name()} 正在思考中...", spinner="dots", console=console
                    ):
                        try:
                            while True:
                                first_chunk = next(chat_iterator)
                                if first_chunk:
                                    break
                        except StopIteration:
                            return ""

                    text_content = Text(overflow="fold")
                    panel = Panel(
                        text_content,
                        title=f"[bold cyan]{self.name()}[/bold cyan]",
                        subtitle="[yellow]正在回答... (按 Ctrl+C 中断)[/yellow]",
                        border_style="bright_blue",
                        box=box.ROUNDED,
                        expand=True,  # 允许面板自动调整大小
                    )

                    buffer = []
                    buffer_count = 0
                    with Live(panel, refresh_per_second=4, transient=False) as live:
                        # Process first chunk
                        response += first_chunk
                        buffer.append(first_chunk)
                        buffer_count += 1

                        # Process rest of the chunks
                        for s in chat_iterator:
                            if not s:
                                continue
                            response += s  # Accumulate the full response string
                            buffer.append(s)
                            buffer_count += 1

                            # 积累一定量或达到最后再更新，减少闪烁
                            if buffer_count >= 5 or s == "":
                                # Append buffered content to the Text object
                                text_content.append(
                                    "".join(buffer), style="bright_white"
                                )
                                buffer.clear()
                                buffer_count = 0

                                # --- Scrolling Logic ---
                                # Calculate available height in the panel
                                max_text_height = (
                                    console.height - 5
                                )  # Leave space for borders/titles
                                if max_text_height <= 0:
                                    max_text_height = 1

                                # Get the actual number of lines the text will wrap to
                                lines = text_content.wrap(
                                    console,
                                    console.width - 4 if console.width > 4 else 1,
                                )

                                # If content overflows, truncate to show only the last few lines
                                if len(lines) > max_text_height:
                                    # Rebuild the text from the wrapped lines to ensure visual consistency
                                    # This correctly handles both wrapped long lines and explicit newlines
                                    text_content.plain = "\n".join(
                                        [line.plain for line in lines[-max_text_height:]]
                                    )

                                panel.subtitle = (
                                    "[yellow]正在回答... (按 Ctrl+C 中断)[/yellow]"
                                )
                                live.update(panel)

                            if is_immediate_abort() and get_interrupt():
                                return response  # Return the partial response immediately

                        # Ensure any remaining content in the buffer is displayed
                        if buffer:
                            text_content.append(
                                "".join(buffer), style="bright_white"
                            )

                        # At the end, display the entire response
                        text_content.plain = response

                        end_time = time.time()
                        duration = end_time - start_time
                        panel.subtitle = f"[bold green]✓ 对话完成耗时: {duration:.2f}秒[/bold green]"
                        live.update(panel)
                else:
                    # Print a clear prefix line before streaming model output (non-pretty mode)
                    console.print(
                        f"🤖 模型输出 - {self.name()}  (按 Ctrl+C 中断)",
                        soft_wrap=False,
                    )
                    for s in self.chat(message):
                        console.print(s, end="")
                        response += s
                        if is_immediate_abort() and get_interrupt():
                            return response
                    console.print()
                    end_time = time.time()
                    duration = end_time - start_time
                    console.print(f"✓ 对话完成耗时: {duration:.2f}秒")
            else:
                for s in self.chat(message):
                    response += s
                    if is_immediate_abort() and get_interrupt():
                        return response
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

    @classmethod
    @abstractmethod
    def get_required_env_keys(cls) -> List[str]:
        """Get required env keys"""
        raise NotImplementedError("get_required_env_keys is not implemented")

    @classmethod
    def get_env_defaults(cls) -> Dict[str, str]:
        """Get env default values"""
        return {}

    @classmethod
    def get_env_config_guide(cls) -> Dict[str, str]:
        """Get environment variable configuration guide

        Returns:
            Dict[str, str]: A dictionary mapping env key names to their configuration instructions
        """
        return {}

    def set_suppress_output(self, suppress: bool):
        """Set whether to suppress output"""
        self.suppress_output = suppress

    def set_model_group(self, model_group: Optional[str]):
        """Set model group"""
        self.model_group = model_group

    def set_web(self, web: bool):
        """Set web flag"""
        self.web = web

    @abstractmethod
    def support_web(self) -> bool:
        """Check if platform supports web functionality"""
        return False
