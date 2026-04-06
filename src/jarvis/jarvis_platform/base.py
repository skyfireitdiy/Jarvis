import os

# -*- coding: utf-8 -*-
import re
import threading
from abc import ABC
from abc import abstractmethod
from datetime import datetime
from types import TracebackType
from typing import Any
from typing import Dict
from typing import Generator
from typing import List
from typing import Optional
from typing import Tuple
from typing import Type

from typing_extensions import Self

import jarvis.jarvis_utils.globals as G
from jarvis.jarvis_utils.config import get_cheap_max_input_token_count
from jarvis.jarvis_utils.config import get_conversation_turn_threshold
from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.config import get_max_input_token_count
from jarvis.jarvis_utils.config import get_pretty_output
from jarvis.jarvis_utils.config import get_smart_max_input_token_count
from jarvis.jarvis_utils.config import get_llm_config
from jarvis.jarvis_utils.config import get_normal_model_name
from jarvis.jarvis_utils.config import get_cheap_model_name
from jarvis.jarvis_utils.config import get_smart_model_name
from jarvis.jarvis_utils.config import is_immediate_abort
from jarvis.jarvis_utils.config import is_print_prompt
from jarvis.jarvis_utils.config import is_save_session_history
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.globals import get_interrupt
from jarvis.jarvis_utils.globals import set_interrupt
from jarvis.jarvis_utils.globals import set_in_chat
from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_utils.tag import ct
from jarvis.jarvis_utils.tag import ot
from jarvis.jarvis_utils.utils import while_success
from jarvis.jarvis_utils.utils import while_true


class BasePlatform(ABC):
    """大语言模型基类"""

    def __init__(
        self,
        platform_type: str = "normal",
        agent: Optional[Any] = None,
    ):
        """初始化模型

        参数:
            platform_type: 平台类型，可选值为 'normal'、'cheap' 或 'smart'
            agent: Agent实例，用于回调触发总结等功能
        """
        self.suppress_output = True  # 添加输出控制标志
        self._saved = False
        self._panel_lock = threading.RLock()  # 用于保护 panel 更新的线程锁

        self._session_history_file: Optional[str] = None
        self.platform_type: str = platform_type  # 平台类型：normal/cheap/smart
        self.agent = agent  # 保存Agent引用，用于回调

        # 根据 platform_type 获取对应的 model_name
        if platform_type == "cheap":
            self.model_name = get_cheap_model_name()
        elif platform_type == "smart":
            self.model_name = get_smart_model_name()
        else:
            self.model_name = get_normal_model_name()

        # 获取 llm_config 供子类使用
        self._llm_config = get_llm_config(platform_type)

    def get_conversation_turn(self) -> int:
        """获取当前对话轮次数"""
        return len(self.get_messages()) // 2

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
    def set_messages(self, messages: List[Dict[str, str]]) -> None:
        """设置对话历史"""
        raise NotImplementedError("set_messages is not implemented")

    @abstractmethod
    def get_messages(self) -> List[Dict[str, str]]:
        """获取对话历史"""
        raise NotImplementedError("get_messages is not implemented")

    @abstractmethod
    def set_model_name(self, model_name: str):
        """设置模型名称"""
        raise NotImplementedError("set_model_name is not implemented")

    def reset(self) -> None:
        """重置模型"""
        self.delete_chat()
        self._session_history_file = None

    @abstractmethod
    def chat(self, message: str) -> Generator[Tuple[str, str], None, None]:
        """执行对话
        
        返回:
            Generator[Tuple[str, str], None, None]: 生成器，逐块返回 (类型, 内容) 元组
            类型: "reason" 表示推理过程，"content" 表示正文内容
        """
        raise NotImplementedError("chat is not implemented")

    def complete(self, prompt: str, **kwargs: Any) -> str:
        """无状态补全方法

        每次调用前自动重置对话状态，确保多次调用之间不会累积上下文。
        适用于：情绪分析、歧义检测、代码分析等一次性推理任务。

        参数:
            prompt: 提示词
            **kwargs: 额外参数（预留）

        返回:
            str: 完整的响应内容

        注意:
            - 此方法会调用 delete_chat() 重置状态
            - 不会影响主对话的 messages 历史
            - 每次调用都是独立的，无状态
        """
        # 先重置对话状态，确保无状态
        self.delete_chat()

        # 调用 chat 方法并收集所有响应（只收集 content 类型）
        response = ""
        for chunk_type, chunk_content in self.chat(prompt):
            if chunk_type == "content":
                response += chunk_content

        return response

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

        # 构建进度条：使用 █ 表示已填充，░ 表示未填充
        bar = "█" * filled + "░" * empty

        return bar

    def _get_token_usage_info(
        self, current_response: str = ""
    ) -> Tuple[float, str, str]:
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
            max_tokens = self._get_platform_max_input_token_count()

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

    def _chat_with_pretty_output(
        self, message: str, start_time: float, max_output: int = 0
    ) -> Tuple[str, float]:
        """使用 pretty output 模式进行聊天（封装到 PrettyOutput）"""
        return PrettyOutput.stream_chat_with_panel(
            chat_iterator=self.chat(message),
            title=self.name(),
            status_message=f"🤔 {(G.get_current_agent_name() + ' · ') if G.get_current_agent_name() else ''}{self.name()} 正在思考中...",
            get_used_token_count=self.get_used_token_count,
            get_conversation_turn=self.get_conversation_turn,
            get_platform_max_input_token_count=self._get_platform_max_input_token_count,
            get_context_token_count=get_context_token_count,
            append_session_history=self._append_session_history,
            start_time=start_time,
            message=message,
            max_output=max_output,
            check_interrupt=lambda: bool(get_interrupt()),
            panel_lock=self._panel_lock,
        )

    def _chat_with_simple_output(
        self, message: str, start_time: float, max_output: int = 0
    ) -> str:
        """使用简单输出模式进行聊天（封装到 PrettyOutput）"""
        response, _ = PrettyOutput.stream_chat_simple(
            chat_iterator=self.chat(message),
            prefix=f"🤖 模型输出 - {(G.get_current_agent_name() + ' · ') if G.get_current_agent_name() else ''}{self.name()}  (按 Ctrl+C 中断)",
            start_time=start_time,
            message=message,
            max_output=max_output,
            check_interrupt=lambda: bool(is_immediate_abort() and get_interrupt()),
            append_session_history=self._append_session_history,
            get_context_token_count=get_context_token_count,
        )
        return response

    def _chat_with_suppressed_output(self, message: str, max_output: int = 0) -> str:
        """使用无人值守模式进行聊天

        参数:
            message: 用户消息
            max_output: 最大输出长度，0表示无限制

        返回:
            str: 模型响应
        """
        response = ""
        for chunk_type, chunk_content in self.chat(message):
            # 只拼接 content 类型
            if chunk_type == "content":
                response += chunk_content
            # 检查是否达到最大输出长度
            if max_output > 0 and len(response) >= max_output:
                self._append_session_history(message, response)
                return response
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

    def _chat(self, message: str, max_output: int = 0):
        import time

        start_time = time.time()

        # 当输入为空白字符串时，打印警告并直接返回空字符串
        if message.strip() == "":
            PrettyOutput.auto_print("⚠️ 输入为空白字符串，已忽略本次请求")
            return ""

        # 检查并截断消息以避免超出剩余token限制
        message = self._truncate_message_if_needed(message)

        # 根据输出模式选择不同的处理方式
        first_token_time = 0.0
        if not self.suppress_output:
            if get_pretty_output():
                response, first_token_time = self._chat_with_pretty_output(
                    message, start_time, max_output
                )
            else:
                response = self._chat_with_simple_output(
                    message, start_time, max_output
                )

            # 计算响应时间并打印总结
            end_time = time.time()
            duration = end_time - start_time

            # 计算性能指标
            response_tokens = get_context_token_count(response)
            generation_time = max(
                0.0,
                duration - first_token_time
                if duration > first_token_time
                else duration,
            )
            tokens_per_second = (
                response_tokens / generation_time if generation_time > 0 else 0.0
            )

            # 获取Token使用信息
            try:
                usage_percent, percent_color, progress_bar = self._get_token_usage_info(
                    response
                )
                threshold = get_conversation_turn_threshold()
                PrettyOutput.auto_print(
                    f"✅ {self.name()}模型响应完成: {duration:.2f}秒 | 轮次: {self.get_conversation_turn()}/{threshold} | "
                    f"首token: {first_token_time:.2f}秒 | 速度: {tokens_per_second:.1f} tokens/s | Token: {usage_percent:.1f}%"
                )
            except Exception:
                threshold = get_conversation_turn_threshold()
                PrettyOutput.auto_print(
                    f"✅ {self.name()}模型响应完成: {duration:.2f}秒 | 轮次: {self.get_conversation_turn()}/{threshold} | "
                    f"首token: {first_token_time:.2f}秒 | 速度: {tokens_per_second:.1f} tokens/s"
                )
        else:
            response = self._chat_with_suppressed_output(message, max_output)

        # 处理响应并保存会话历史
        response = self._process_response(response)
        self._append_session_history(message, response)

        # 确保消息被正确添加到 messages 中（特别是中断的情况下）
        # 如果发生中断，chat() 方法可能没有完成，导致助手的消息没加到 messages 中
        if response:  # 只有在有响应时才检查
            try:
                messages = self.get_messages()
                # 检查最后一条消息是否是助手消息
                if messages:
                    last_message = messages[-1]
                    if last_message.get("role") != "assistant":
                        # 最后一条消息不是助手消息，需要手动添加
                        # 检查最后一条消息是否是用户消息（且内容匹配）
                        if (
                            last_message.get("role") == "user"
                            and last_message.get("content") == message
                        ):
                            # 最后一条是用户消息，只需要添加助手响应
                            messages.append({"role": "assistant", "content": response})
                        else:
                            # 最后一条不是用户消息，需要添加用户消息和助手响应
                            messages.append({"role": "user", "content": message})
                            messages.append({"role": "assistant", "content": response})
                        # 更新消息列表
                        self.set_messages(messages)
                else:
                    # messages 为空，直接添加用户消息和助手响应
                    messages = [
                        {"role": "user", "content": message},
                        {"role": "assistant", "content": response},
                    ]
                    self.set_messages(messages)
            except Exception as e:
                # 如果更新消息失败，不影响对话流程，只打印警告
                PrettyOutput.auto_print(f"⚠️ 警告：更新消息列表失败: {e}")

        return response

    def chat_until_success(self, message: str, max_output: int = 0) -> str:
        """与模型对话直到成功响应。

        参数:
            message: 用户消息
            max_output: 最大输出长度，0表示无限制

        返回:
            str: 模型响应
        """
        try:
            # 清除中断标志，确保每次新的对话都从干净的状态开始
            # 这可以防止之前的中断（如Ctrl+C）影响新对话的首次调用
            # 修复问题：用户中断后再次执行任务时，方法论加载失败（返回结果为空）
            set_interrupt(False)
            set_in_chat(True)
            if not self.suppress_output and is_print_prompt():
                PrettyOutput.auto_print(f"👤 {message}")  # 保留用于语法高亮

            # 记录用户输入（模型输入）
            from jarvis.jarvis_utils.dialogue_recorder import record_user_message

            record_user_message(message)

            result: str = ""
            result = while_true(
                lambda: while_success(lambda: self._chat(message, max_output))
            )

            # Check if result is empty or False (retry exhausted)
            # Convert False to empty string for type safety
            if result is False or result == "":
                raise ValueError("返回结果为空")

            # 记录模型输出
            from jarvis.jarvis_utils.dialogue_recorder import record_assistant_message

            record_assistant_message(result)

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
        import json

        state = {
            "messages": self.get_messages(),
        }
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=4)
            self._saved = True
            from jarvis.jarvis_utils.output import PrettyOutput

            PrettyOutput.auto_print(f"✅ 会话已成功保存到 {file_path}")
            return True
        except Exception as e:
            from jarvis.jarvis_utils.output import PrettyOutput

            PrettyOutput.auto_print(f"❌ 保存会话失败: {str(e)}")
            return False

    def restore(self, file_path: str) -> bool:
        """从文件恢复对话会话。

        参数:
            file_path: 要恢复会话文件的路径。

        返回:
            如果恢复成功返回True，否则返回False。
        """
        import json
        from jarvis.jarvis_utils.output import PrettyOutput

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            messages = state.get("messages", [])
            self.set_messages(messages)
            self._saved = True
            return True
        except FileNotFoundError:
            PrettyOutput.auto_print(f"❌ 会话文件未找到: {file_path}")
            return False
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 恢复会话失败: {str(e)}")
            return False

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

    def set_platform_type(self, platform_type: str):
        """设置平台类型

        参数:
            platform_type: 平台类型，可选值为 'normal'、'cheap' 或 'smart'
        """
        self.platform_type = platform_type

    def _get_platform_max_input_token_count(self) -> int:
        """根据平台类型获取对应的最大输入token数量

        返回:
            int: 模型能处理的最大输入token数量
        """
        if self.platform_type == "cheap":
            return get_cheap_max_input_token_count()
        elif self.platform_type == "smart":
            return get_smart_max_input_token_count()
        else:
            return get_max_input_token_count()

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
                    session_dir,
                    f"session_history_{safe_platform}_{safe_model}_{ts}.log",
                )

            # Append record
            with open(
                self._session_history_file, "a", encoding="utf-8", errors="ignore"
            ) as f:
                ts_line = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"===== {ts_line} =====\n")
                f.write("USER:\n")
                f.write(f"{user_input}\n")
                f.write("\nASSISTANT:\n")
                f.write(f"{model_output}\n\n")
        except Exception:
            # Do not break chat flow if writing history fails
            pass

    def get_used_token_count(self) -> int:
        """计算当前对话历史使用的token数量

        返回:
            int: 当前对话历史使用的token数量
        """
        history = self.get_messages()
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
        max_tokens = self._get_platform_max_input_token_count()
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

            # 如果剩余token为0或负数，尝试裁剪历史消息以腾出空间
            if remaining_tokens <= 0:
                PrettyOutput.auto_print("⚠️ 警告：剩余token为0，尝试裁剪历史消息...")
                if self.trim_messages():
                    # 裁剪成功，重新计算剩余token
                    remaining_tokens = self.get_remaining_token_count()
                    PrettyOutput.auto_print(
                        f"✅ 裁剪成功，当前剩余token: {remaining_tokens}"
                    )
                    if remaining_tokens > 0:
                        # 裁剪后仍有空间，继续处理消息
                        pass
                    else:
                        PrettyOutput.auto_print(
                            "⚠️ 警告：裁剪后仍无剩余token，无法发送消息"
                        )
                        return ""
                else:
                    # trim_messages失败（消息不足10条），尝试直接截断当前消息
                    PrettyOutput.auto_print(
                        "⚠️ 警告：裁剪失败（消息不足10条），尝试直接截断当前消息..."
                    )
                    # 计算消息的token数量
                    message_tokens = get_context_token_count(message)
                    # 即使remaining_tokens为0，也尝试保留消息的一部分（使用固定比例）
                    # 使用模型最大输入token的5%作为目标
                    max_tokens = self._get_platform_max_input_token_count()
                    target_tokens = int(max_tokens * 0.05)  # 5% of max tokens
                    if target_tokens <= 100:
                        target_tokens = 100  # 至少保留100 tokens

                    # 估算字符数（1 token ≈ 4字符）
                    target_chars = target_tokens * 4

                    # 如果消息长度小于目标字符数，直接返回（token估算可能有误差）
                    if len(message) <= target_chars:
                        PrettyOutput.auto_print(
                            f"✅ 消息长度在可接受范围内，直接发送（约 {message_tokens} tokens）"
                        )
                        return message

                    # 截断消息：保留前面的内容，添加截断提示
                    truncated_message = message[:target_chars]
                    # 尝试在最后一个完整句子处截断
                    last_period = truncated_message.rfind(".")
                    last_newline = truncated_message.rfind("\n")
                    last_break = max(last_period, last_newline)

                    if last_break > target_chars * 0.5:  # 如果找到的断点不太靠前
                        truncated_message = truncated_message[: last_break + 1]

                    truncated_message += (
                        "\n\n... (消息过长，已截断以避免超出上下文限制)"
                    )
                    PrettyOutput.auto_print(
                        f"✅ 消息已截断至约 {target_tokens} tokens（原始约 {message_tokens} tokens）"
                    )

                    return truncated_message

            # 计算消息的token数量
            message_tokens = get_context_token_count(message)

            # 如果消息token数小于等于剩余token数，不需要截断
            if message_tokens <= remaining_tokens:
                return message

            # 需要截断：保留剩余token的80%用于消息，20%作为安全余量
            target_tokens = int(remaining_tokens * 0.8)
            if target_tokens <= 0:
                PrettyOutput.auto_print("⚠️ 警告：剩余token不足，无法发送消息")
                return ""

            # 估算字符数（1 token ≈ 4字符）
            target_chars = target_tokens * 4

            # 如果消息长度小于目标字符数，不需要截断（token估算可能有误差）
            if len(message) <= target_chars:
                return message

            # 截断消息：保留前面的内容，添加截断提示
            truncated_message = message[:target_chars]
            # 尝试在最后一个完整句子处截断
            last_period = truncated_message.rfind(".")
            last_newline = truncated_message.rfind("\n")
            last_break = max(last_period, last_newline)

            if last_break > target_chars * 0.5:  # 如果找到的断点不太靠前
                truncated_message = truncated_message[: last_break + 1]

            truncated_message += "\n\n... (消息过长，已截断以避免超出上下文限制)"
            PrettyOutput.auto_print(
                f"⚠️ 警告：消息过长（{message_tokens} tokens），已截断至约 {target_tokens} tokens"
            )

            return truncated_message
        except Exception as e:
            # 如果截断过程中出错，返回原消息（避免阻塞对话）
            PrettyOutput.auto_print(f"⚠️ 警告：检查消息长度时出错: {e}，使用原消息")
            return message

    @abstractmethod
    def trim_messages(self) -> bool:
        """裁剪消息历史以腾出token空间

        当剩余token不足时，通过裁剪历史消息来腾出空间。
        默认实现应保留system消息，并丢弃开头的10条非system消息。

        返回:
            bool: 如果成功腾出空间返回True，否则返回False
        """
        raise NotImplementedError("trim_messages is not implemented")
