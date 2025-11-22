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
    get_pretty_output,
    is_print_prompt,
    is_immediate_abort,
    is_save_session_history,
    get_data_dir,
    get_max_input_token_count,
)
from jarvis.jarvis_utils.globals import set_in_chat, get_interrupt, console
import jarvis.jarvis_utils.globals as G
from jarvis.jarvis_utils.output import OutputType, PrettyOutput  # 保留用于语法高亮
from jarvis.jarvis_utils.tag import ct, ot
from jarvis.jarvis_utils.utils import while_success, while_true
from jarvis.jarvis_utils.embedding import get_context_token_count


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

    def _format_progress_bar(self, percent: float, width: int = 20) -> str:
        """格式化进度条字符串
        
        参数:
            percent: 百分比 (0-100)
            width: 进度条宽度（字符数）
            
        返回:
            str: 格式化的进度条字符串
        """
        # 限制百分比范围
        percent = max(0, min(100, percent))
        
        # 计算填充的字符数
        filled = int(width * percent / 100)
        empty = width - filled
        
        # 根据百分比选择颜色
        if percent >= 90:
            color = "red"
        elif percent >= 80:
            color = "yellow"
        else:
            color = "green"
        
        # 构建进度条：使用 █ 表示已填充，░ 表示未填充
        bar = "█" * filled + "░" * empty
        
        return f"[{color}]{bar}[/{color}]"

    def _get_token_usage_info(self, current_response: str = "") -> Tuple[float, str, str]:
        """获取 token 使用信息
        
        参数:
            current_response: 当前响应内容（用于计算流式输出时的 token）
            
        返回:
            Tuple[float, str, str]: (usage_percent, percent_color, progress_bar)
        """
        try:
            history_tokens = self.get_used_token_count()
            current_response_tokens = get_context_token_count(current_response)
            total_tokens = history_tokens + current_response_tokens
            max_tokens = get_max_input_token_count(self.model_group)
            
            if max_tokens > 0:
                usage_percent = (total_tokens / max_tokens) * 100
                if usage_percent >= 90:
                    percent_color = "red"
                elif usage_percent >= 80:
                    percent_color = "yellow"
                else:
                    percent_color = "green"
                progress_bar = self._format_progress_bar(usage_percent, width=15)
                return usage_percent, percent_color, progress_bar
            return 0.0, "green", ""
        except Exception:
            return 0.0, "green", ""

    def _update_panel_subtitle_with_token(
        self, panel: Panel, response: str, is_completed: bool = False, duration: float = 0.0
    ) -> None:
        """更新面板的 subtitle，包含 token 使用信息
        
        参数:
            panel: 要更新的面板
            response: 当前响应内容
            is_completed: 是否已完成
            duration: 耗时（秒）
        """
        try:
            usage_percent, percent_color, progress_bar = self._get_token_usage_info(response)
            max_tokens = get_max_input_token_count(self.model_group)
            total_tokens = self.get_used_token_count() + get_context_token_count(response)
            
            if is_completed:
                if max_tokens > 0 and progress_bar:
                    panel.subtitle = (
                        f"[bold green]✓ 对话完成耗时: {duration:.2f}秒 | "
                        f"Token: {progress_bar} "
                        f"[{percent_color}]{usage_percent:.1f}% ({total_tokens}/{max_tokens})[/{percent_color}][/bold green]"
                    )
                else:
                    panel.subtitle = f"[bold green]✓ 对话完成耗时: {duration:.2f}秒[/bold green]"
            else:
                if max_tokens > 0 and progress_bar:
                    panel.subtitle = (
                        f"[yellow]正在回答... (按 Ctrl+C 中断) | "
                        f"Token: {progress_bar} "
                        f"[{percent_color}]{usage_percent:.1f}% ({total_tokens}/{max_tokens})[/{percent_color}][/yellow]"
                    )
                else:
                    panel.subtitle = "[yellow]正在回答... (按 Ctrl+C 中断)[/yellow]"
        except Exception:
            if is_completed:
                panel.subtitle = f"[bold green]✓ 对话完成耗时: {duration:.2f}秒[/bold green]"
            else:
                panel.subtitle = "[yellow]正在回答... (按 Ctrl+C 中断)[/yellow]"

    def _chat_with_pretty_output(self, message: str, start_time: float) -> str:
        """使用 pretty output 模式进行聊天
        
        参数:
            message: 用户消息
            start_time: 开始时间
            
        返回:
            str: 模型响应
        """
        import time
        
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
            expand=True,
        )

        response = ""
        with Live(panel, refresh_per_second=4, transient=False) as live:
            def _update_panel_content(content: str):
                nonlocal response
                text_content.append(content, style="bright_white")
                
                # Scrolling Logic
                max_text_height = console.height - 5
                if max_text_height <= 0:
                    max_text_height = 1

                lines = text_content.wrap(
                    console,
                    console.width - 4 if console.width > 4 else 1,
                )

                if len(lines) > max_text_height:
                    text_content.plain = "\n".join(
                        [line.plain for line in lines[-max_text_height:]]
                    )

                # 更新 token 使用信息
                self._update_panel_subtitle_with_token(panel, response, is_completed=False)
                live.update(panel)

            # Process first chunk
            response += first_chunk
            if first_chunk:
                _update_panel_content(first_chunk)

            # 缓存机制：降低更新频率，减少界面闪烁
            buffer = ""
            last_update_time = time.time()
            update_interval = 1
            min_buffer_size = 5

            def _flush_buffer():
                nonlocal buffer, last_update_time
                if buffer:
                    _update_panel_content(buffer)
                    buffer = ""
                    last_update_time = time.time()

            # Process rest of the chunks
            for s in chat_iterator:
                if not s:
                    continue
                response += s
                buffer += s

                current_time = time.time()
                should_update = (
                    len(buffer) >= min_buffer_size
                    or (current_time - last_update_time) >= update_interval
                )

                if should_update:
                    _flush_buffer()

                if is_immediate_abort() and get_interrupt():
                    _flush_buffer()
                    self._append_session_history(message, response)
                    return response

            _flush_buffer()
            text_content.plain = response

            end_time = time.time()
            duration = end_time - start_time
            self._update_panel_subtitle_with_token(panel, response, is_completed=True, duration=duration)
            live.update(panel)
            console.print()

        return response

    def _chat_with_simple_output(self, message: str, start_time: float) -> str:
        """使用简单输出模式进行聊天
        
        参数:
            message: 用户消息
            start_time: 开始时间
            
        返回:
            str: 模型响应
        """
        import time
        
        console.print(
            f"🤖 模型输出 - {(G.current_agent_name + ' · ') if G.current_agent_name else ''}{self.name()}  (按 Ctrl+C 中断)",
            soft_wrap=False,
        )
        response = ""
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
        return response

    def _chat_with_suppressed_output(self, message: str) -> str:
        """使用静默模式进行聊天
        
        参数:
            message: 用户消息
            
        返回:
            str: 模型响应
        """
        response = ""
        for s in self.chat(message):
            response += s
            if is_immediate_abort() and get_interrupt():
                self._append_session_history(message, response)
                return response
        return response

    def _process_response(self, response: str) -> str:
        """处理响应，移除 think 标签
        
        参数:
            response: 原始响应
            
        返回:
            str: 处理后的响应
        """
        response = re.sub(
            ot("think") + r".*?" + ct("think"), "", response, flags=re.DOTALL
        )
        response = re.sub(
            ot("thinking") + r".*?" + ct("thinking"), "", response, flags=re.DOTALL
        )
        return response

    def _chat(self, message: str):
        import time

        start_time = time.time()

        # 当输入为空白字符串时，打印警告并直接返回空字符串
        if message.strip() == "":
            print("⚠️ 输入为空白字符串，已忽略本次请求")
            return ""

        # 检查并截断消息以避免超出剩余token限制
        message = self._truncate_message_if_needed(message)

        # 根据输出模式选择不同的处理方式
        if not self.suppress_output:
            if get_pretty_output():
                response = self._chat_with_pretty_output(message, start_time)
            else:
                response = self._chat_with_simple_output(message, start_time)
        else:
            response = self._chat_with_suppressed_output(message)

        # 处理响应并保存会话历史
        response = self._process_response(response)
        self._append_session_history(message, response)
        return response

    def chat_until_success(self, message: str) -> str:
        """与模型对话直到成功响应。"""
        try:
            set_in_chat(True)
            if not self.suppress_output and is_print_prompt():
                PrettyOutput.print(f"{message}", OutputType.USER)  # 保留用于语法高亮
            
            result: str = ""
            result = while_true(
                lambda: while_success(lambda: self._chat(message))
            )
            
            # Check if result is empty or False (retry exhausted)
            # Convert False to empty string for type safety
            if result is False or result == "":
                raise ValueError("返回结果为空")
            
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

    def get_conversation_history(self) -> List[Dict[str, str]]:
        """获取当前对话历史
        
        返回:
            List[Dict[str, str]]: 对话历史列表，每个元素包含 role 和 content
            
        注意:
            默认实现检查是否有 messages 属性，子类可以重写此方法以提供自定义实现
        """
        if hasattr(self, "messages"):
            return getattr(self, "messages", [])
        return []

    def get_used_token_count(self) -> int:
        """计算当前对话历史使用的token数量
        
        返回:
            int: 当前对话历史使用的token数量
        """
        history = self.get_conversation_history()
        if not history:
            return 0
        
        total_tokens = 0
        for message in history:
            content = message.get("content", "")
            if content:
                total_tokens += get_context_token_count(content)
        
        return total_tokens

    def get_remaining_token_count(self) -> int:
        """获取剩余可用的token数量
        
        返回:
            int: 剩余可用的token数量（输入窗口限制 - 当前使用的token数量）
        """
        max_tokens = get_max_input_token_count(self.model_group)
        used_tokens = self.get_used_token_count()
        remaining = max_tokens - used_tokens
        return max(0, remaining)  # 确保返回值不为负数

    def _truncate_message_if_needed(self, message: str) -> str:
        """如果消息超出剩余token限制，则截断消息
        
        参数:
            message: 原始消息
            
        返回:
            str: 截断后的消息（如果不需要截断则返回原消息）
        """
        try:
            # 获取剩余token数量
            remaining_tokens = self.get_remaining_token_count()
            
            # 如果剩余token为0或负数，返回空消息
            if remaining_tokens <= 0:
                print("⚠️ 警告：剩余token为0，无法发送消息")
                return ""
            
            # 计算消息的token数量
            message_tokens = get_context_token_count(message)
            
            # 如果消息token数小于等于剩余token数，不需要截断
            if message_tokens <= remaining_tokens:
                return message
            
            # 需要截断：保留剩余token的80%用于消息，20%作为安全余量
            target_tokens = int(remaining_tokens * 0.8)
            if target_tokens <= 0:
                print("⚠️ 警告：剩余token不足，无法发送消息")
                return ""
            
            # 估算字符数（1 token ≈ 4字符）
            target_chars = target_tokens * 4
            
            # 如果消息长度小于目标字符数，不需要截断（token估算可能有误差）
            if len(message) <= target_chars:
                return message
            
            # 截断消息：保留前面的内容，添加截断提示
            truncated_message = message[:target_chars]
            # 尝试在最后一个完整句子处截断
            last_period = truncated_message.rfind('.')
            last_newline = truncated_message.rfind('\n')
            last_break = max(last_period, last_newline)
            
            if last_break > target_chars * 0.5:  # 如果找到的断点不太靠前
                truncated_message = truncated_message[:last_break + 1]
            
            truncated_message += "\n\n... (消息过长，已截断以避免超出上下文限制)"
            print(f"⚠️ 警告：消息过长（{message_tokens} tokens），已截断至约 {target_tokens} tokens")
            
            return truncated_message
        except Exception as e:
            # 如果截断过程中出错，返回原消息（避免阻塞对话）
            print(f"⚠️ 警告：检查消息长度时出错: {e}，使用原消息")
            return message

    @abstractmethod
    def support_web(self) -> bool:
        """检查平台是否支持网页功能"""
        return False
