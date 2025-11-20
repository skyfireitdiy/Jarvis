# -*- coding: utf-8 -*-
import re
import os
from datetime import datetime
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
    is_save_session_history,
    get_data_dir,
)
from jarvis.jarvis_utils.embedding import split_text_into_chunks
from jarvis.jarvis_utils.globals import set_in_chat, get_interrupt, console
import jarvis.jarvis_utils.globals as G
from jarvis.jarvis_utils.output import OutputType, PrettyOutput  # 保留用于语法高亮
from jarvis.jarvis_utils.tag import ct, ot
from jarvis.jarvis_utils.utils import get_context_token_count, while_success, while_true


class BasePlatform(ABC):
    """大语言模型基类"""

    def __init__(self):
        """初始化模型"""
        self.suppress_output = True  # 添加输出控制标志
        self.web = False  # 添加web属性，默认false
        self._saved = False
        self.model_group: Optional[str] = None
        self._session_history_file: Optional[str] = None

    def __enter__(self) -> Self:
        """进入上下文管理器"""
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """退出上下文管理器"""
        if not self._saved:
            self.delete_chat()

    @abstractmethod
    def set_model_name(self, model_name: str):
        """设置模型名称"""
        raise NotImplementedError("set_model_name is not implemented")

    def reset(self):
        """重置模型"""
        self.delete_chat()
        self._session_history_file = None

    @abstractmethod
    def chat(self, message: str) -> Generator[str, None, None]:
        """执行对话"""
        raise NotImplementedError("chat is not implemented")

    @abstractmethod
    def upload_files(self, file_list: List[str]) -> bool:
        raise NotImplementedError("upload_files is not implemented")

    @abstractmethod
    def support_upload_files(self) -> bool:
        """检查平台是否支持文件上传"""
        return False

    def _submit_part_with_split(self, part_content: str, threshold_factor: float = 1.0) -> str:
        """提交单个部分，如果反复失败则将其拆分。
        
        参数:
            part_content: 要提交的内容。
            threshold_factor: 调整token阈值的因素。
            
        返回:
            提交部分后的响应。
        """
        try:
            response = ""
            for trunk in while_true(
                lambda: while_success(
                    lambda: self._chat(
                        f"<part_content>{part_content}</part_content>\n\n请返回<已收到>，不需要返回其他任何内容"
                    )
                )
            ):
                response += trunk
            return response
        except Exception as e:
            # 如果单个part反复失败，尝试将其拆分成两份
            part_token_count = get_context_token_count(part_content)
            base_max_token = get_max_input_token_count(self.model_group)
            adjusted_max_token = int(base_max_token * threshold_factor)
            min_chunk_size = adjusted_max_token - 2048
            
            # 如果part已经很小（小于最小chunk size），或者token数已经很小，不再拆分
            if part_token_count <= min_chunk_size or len(part_content) < 100:
                print(f"⚠️ Part提交失败且已无法进一步拆分，重新抛出异常: {e}")
                raise
            
            print(f"⚠️ Part提交失败，尝试拆分成两份: {e}")
            # 将part拆分成两份，使用更小的max_length以确保拆分成功
            # 使用更保守的阈值因子（进一步降低20%）来拆分
            split_threshold_factor = threshold_factor * 0.8
            split_max_token = int(base_max_token * split_threshold_factor)
            split_max_chunk_size = split_max_token - 1024
            chunks = split_text_into_chunks(part_content, split_max_chunk_size, split_max_chunk_size // 2)
            if len(chunks) < 2:
                # 如果无法拆分，直接抛出异常
                print(f"⚠️ 无法拆分part，重新抛出异常: {e}")
                raise
            
            # 递归处理两个更小的部分，使用更保守的阈值因子
            response = ""
            for i, chunk in enumerate(chunks, 1):
                print(f"ℹ️ 处理拆分后的第{i}/{len(chunks)}部分...")
                chunk_response = self._submit_part_with_split(chunk, split_threshold_factor)
                response += "\n" + chunk_response
            return response

    def _handle_long_context(self, message: str, threshold_factor: float = 1.0) -> str:
        """通过拆分和分块提交来处理长上下文。
        
        参数:
            message: 要拆分和提交的较长消息。
            threshold_factor: 调整token阈值的因素（默认为1.0）。
                             使用小于1.0的值（例如0.8）在重试时降低阈值。
            
        返回:
            所有块提交的累积响应。
        """
        base_max_token = get_max_input_token_count(self.model_group)
        adjusted_max_token = int(base_max_token * threshold_factor)
        max_chunk_size = adjusted_max_token - 1024  # 留出一些余量
        min_chunk_size = adjusted_max_token - 2048
        inputs = split_text_into_chunks(message, max_chunk_size, min_chunk_size)
        print(f"ℹ️ 长上下文，分批提交，共{len(inputs)}部分...")
        prefix_prompt = """
        我将分多次提供大量内容，在我明确告诉你内容已经全部提供完毕之前，每次仅需要输出"已收到"，明白请输出"开始接收输入"。
        """
        while_true(lambda: while_success(lambda: self._chat(prefix_prompt)))
        submit_count = 0
        length = 0
        response = ""
        for input in inputs:
            submit_count += 1
            length += len(input)

            response += "\n"
            try:
                part_response = self._submit_part_with_split(input, threshold_factor)
                response += part_response
            except Exception as e:
                print(f"⚠️ 第{submit_count}部分提交最终失败: {e}")
                raise

        print("✅ 提交完成")
        response += "\n" + while_true(
            lambda: while_success(
                lambda: self._chat("内容已经全部提供完毕，请根据内容继续")
            )
        )
        return response

    def _chat(self, message: str):
        import time

        start_time = time.time()

        # 当输入为空白字符串时，打印警告并直接返回空字符串
        if message.strip() == "":
            print("⚠️ 输入为空白字符串，已忽略本次请求")
            return ""

        input_token_count = get_context_token_count(message)

        if input_token_count > get_max_input_token_count(self.model_group):
            response = self._handle_long_context(message)
        else:
            response = ""

            if not self.suppress_output:
                if get_pretty_output():
                    chat_iterator = self.chat(message)
                    first_chunk = None

                    with Status(
                        f"🤔 {(G.current_agent_name + ' · ') if G.current_agent_name else ''}{self.name()} 正在思考中...",
                        spinner="dots",
                        console=console,
                    ):
                        try:
                            while True:
                                first_chunk = next(chat_iterator)
                                if first_chunk:
                                    break
                        except StopIteration:
                            self._append_session_history(message, "")
                            return ""

                    text_content = Text(overflow="fold")
                    panel = Panel(
                        text_content,
                        title=f"[bold cyan]{(G.current_agent_name + ' · ') if G.current_agent_name else ''}{self.name()}[/bold cyan]",
                        subtitle="[yellow]正在回答... (按 Ctrl+C 中断)[/yellow]",
                        border_style="bright_blue",
                        box=box.ROUNDED,
                        expand=True,  # 允许面板自动调整大小
                    )

                    with Live(panel, refresh_per_second=4, transient=False) as live:

                        def _update_panel_content(content: str):
                            text_content.append(content, style="bright_white")
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

                        # Process first chunk
                        response += first_chunk
                        if first_chunk:
                            _update_panel_content(first_chunk)

                        # 缓存机制：降低更新频率，减少界面闪烁
                        buffer = ""  # 内容缓存
                        last_update_time = time.time()  # 上次更新时间
                        update_interval = 0.5  # 最小更新间隔（秒）
                        min_buffer_size = 5  # 最小缓存大小（字符数）

                        def _flush_buffer():
                            """刷新缓存内容到面板"""
                            nonlocal buffer, last_update_time
                            if buffer:
                                _update_panel_content(buffer)
                                buffer = ""
                                last_update_time = time.time()

                        # Process rest of the chunks
                        for s in chat_iterator:
                            if not s:
                                continue
                            response += s  # Accumulate the full response string
                            buffer += s  # 累积到缓存

                            # 检查是否需要更新：缓存达到阈值或超过时间间隔
                            current_time = time.time()
                            should_update = (
                                len(buffer) >= min_buffer_size
                                or (current_time - last_update_time) >= update_interval
                            )

                            if should_update:
                                _flush_buffer()

                            if is_immediate_abort() and get_interrupt():
                                # 中断时也要刷新剩余缓存
                                _flush_buffer()
                                self._append_session_history(message, response)
                                return response  # Return the partial response immediately

                        # 循环结束时，刷新所有剩余缓存内容
                        _flush_buffer()

                        # At the end, display the entire response
                        text_content.plain = response

                        end_time = time.time()
                        duration = end_time - start_time
                        panel.subtitle = f"[bold green]✓ 对话完成耗时: {duration:.2f}秒[/bold green]"
                        live.update(panel)
                    console.print()
                else:
                    # Print a clear prefix line before streaming model output (non-pretty mode)
                    console.print(
                        f"🤖 模型输出 - {(G.current_agent_name + ' · ') if G.current_agent_name else ''}{self.name()}  (按 Ctrl+C 中断)",
                        soft_wrap=False,
                    )
                    for s in self.chat(message):
                        console.print(s, end="")
                        response += s
                        if is_immediate_abort() and get_interrupt():
                            self._append_session_history(message, response)
                            return response
                    console.print()
                    end_time = time.time()
                    duration = end_time - start_time
                    console.print(f"✓ 对话完成耗时: {duration:.2f}秒")
            else:
                for s in self.chat(message):
                    response += s
                    if is_immediate_abort() and get_interrupt():
                        self._append_session_history(message, response)
                        return response
        # Keep original think tag handling
        response = re.sub(
            ot("think") + r".*?" + ct("think"), "", response, flags=re.DOTALL
        )
        response = re.sub(
            ot("thinking") + r".*?" + ct("thinking"), "", response, flags=re.DOTALL
        )
        # Save session history (input and full response)
        self._append_session_history(message, response)
        return response

    def chat_until_success(self, message: str) -> str:
        """与模型对话直到成功响应。
        
        如果初始尝试失败（可能是由于token估算不准确），
        自动使用长上下文处理重试。
        """
        try:
            set_in_chat(True)
            if not self.suppress_output and is_print_prompt():
                PrettyOutput.print(f"{message}", OutputType.USER)  # 保留用于语法高亮
            
            # Check if we should use long context handling based on token count
            input_token_count = get_context_token_count(message)
            max_token_count = get_max_input_token_count(self.model_group)
            use_long_context = input_token_count > max_token_count
            
            result: str = ""
            threshold_factor = 1.0  # 初始阈值因子
            try:
                if use_long_context:
                    # Use long context handling directly
                    result = while_true(
                        lambda: while_success(lambda: self._handle_long_context(message, threshold_factor))
                    )
                else:
                    # Try normal chat first
                    result = while_true(
                        lambda: while_success(lambda: self._chat(message))
                    )
                
                # Check if result is empty or False (retry exhausted)
                # Convert False to empty string for type safety
                if result is False or result == "":
                    raise ValueError("返回结果为空")
            except Exception as e:
                # If normal chat failed and we haven't tried long context yet,
                # retry with long context handling (token estimation might be inaccurate)
                if not use_long_context:
                    print(f"⚠️ 首次尝试失败，可能是token估算不准确，尝试使用长上下文处理: {e}")
                    # 重试时降低阈值，使用更保守的判断，避免再次超出
                    # 降低20%的阈值，或者至少降低1024个token
                    adjusted_max_token = max(
                        int(max_token_count * 0.8),
                        max_token_count - 1024
                    )
                    if input_token_count > adjusted_max_token:
                        # 如果降低阈值后仍然超出，直接使用长上下文处理，并降低阈值因子
                        threshold_factor = 0.8
                        result = while_true(
                            lambda: while_success(lambda: self._handle_long_context(message, threshold_factor))
                        )
                    else:
                        # 如果降低阈值后不超出，再次尝试正常chat
                        result = while_true(
                            lambda: while_success(lambda: self._chat(message))
                        )
                    if result is False or result == "":
                        raise ValueError("长上下文处理也失败，返回结果为空")
                else:
                    # Already tried long context, retry with lowered threshold
                    print(f"⚠️ 长上下文处理失败，降低阈值后重试: {e}")
                    threshold_factor = 0.8  # 降低20%的阈值
                    result = while_true(
                        lambda: while_success(lambda: self._handle_long_context(message, threshold_factor))
                    )
                    if result is False or result == "":
                        raise ValueError("降低阈值后长上下文处理仍然失败，返回结果为空")
            
            from jarvis.jarvis_utils.globals import set_last_message

            set_last_message(result)
            return result
        finally:
            set_in_chat(False)

    @abstractmethod
    def name(self) -> str:
        """模型名称"""
        raise NotImplementedError("name is not implemented")

    @classmethod
    @abstractmethod
    def platform_name(cls) -> str:
        """平台名称"""
        raise NotImplementedError("platform_name is not implemented")

    @abstractmethod
    def delete_chat(self) -> bool:
        """删除对话"""
        raise NotImplementedError("delete_chat is not implemented")

    @abstractmethod
    def save(self, file_path: str) -> bool:
        """保存对话会话到文件。

        注意:
            此方法的实现应在成功保存后将`self._saved`设置为True，
            以防止在对象销毁时删除会话。

        参数:
            file_path: 保存会话文件的路径。

        返回:
            如果保存成功返回True，否则返回False。
        """
        raise NotImplementedError("save is not implemented")

    @abstractmethod
    def restore(self, file_path: str) -> bool:
        """从文件恢复对话会话。

        参数:
            file_path: 要恢复会话文件的路径。

        返回:
            如果恢复成功返回True，否则返回False。
        """
        raise NotImplementedError("restore is not implemented")

    @abstractmethod
    def set_system_prompt(self, message: str):
        """设置系统消息"""
        raise NotImplementedError("set_system_prompt is not implemented")

    @abstractmethod
    def get_model_list(self) -> List[Tuple[str, str]]:
        """获取模型列表"""
        raise NotImplementedError("get_model_list is not implemented")

    @classmethod
    @abstractmethod
    def get_required_env_keys(cls) -> List[str]:
        """获取必需的环境变量键"""
        raise NotImplementedError("get_required_env_keys is not implemented")

    @classmethod
    def get_env_defaults(cls) -> Dict[str, str]:
        """获取环境变量默认值"""
        return {}

    @classmethod
    def get_env_config_guide(cls) -> Dict[str, str]:
        """获取环境变量配置指南

        返回:
            Dict[str, str]: 将环境变量键名映射到其配置说明的字典
        """
        return {}

    def set_suppress_output(self, suppress: bool):
        """设置是否抑制输出"""
        self.suppress_output = suppress

    def set_model_group(self, model_group: Optional[str]):
        """设置模型组"""
        self.model_group = model_group

    def set_web(self, web: bool):
        """设置网页标志"""
        self.web = web

    def _append_session_history(self, user_input: str, model_output: str) -> None:
        """
        Append the user input and model output to a session history file if enabled.
        The file name is generated on first save and reused until reset.
        """
        try:
            if not is_save_session_history():
                return

            if self._session_history_file is None:
                # Ensure session history directory exists under data directory
                data_dir = get_data_dir()
                session_dir = os.path.join(data_dir, "session_history")
                os.makedirs(session_dir, exist_ok=True)

                # Build a safe filename including platform, model and timestamp
                try:
                    platform_name = type(self).platform_name()
                except Exception:
                    platform_name = "unknown_platform"

                try:
                    model_name = self.name()
                except Exception:
                    model_name = "unknown_model"

                safe_platform = re.sub(r"[^\w\-\.]+", "_", str(platform_name))
                safe_model = re.sub(r"[^\w\-\.]+", "_", str(model_name))
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")

                self._session_history_file = os.path.join(
                    session_dir, f"session_history_{safe_platform}_{safe_model}_{ts}.log"
                )

            # Append record
            with open(self._session_history_file, "a", encoding="utf-8", errors="ignore") as f:
                ts_line = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"===== {ts_line} =====\n")
                f.write("USER:\n")
                f.write(f"{user_input}\n")
                f.write("\nASSISTANT:\n")
                f.write(f"{model_output}\n\n")
        except Exception:
            # Do not break chat flow if writing history fails
            pass

    @abstractmethod
    def support_web(self) -> bool:
        """检查平台是否支持网页功能"""
        return False
