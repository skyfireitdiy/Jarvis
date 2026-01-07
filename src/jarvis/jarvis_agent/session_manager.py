# -*- coding: utf-8 -*-
import glob
import os
from datetime import datetime
from typing import TYPE_CHECKING
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

from jarvis.jarvis_utils.output import PrettyOutput

if TYPE_CHECKING:
    from jarvis.jarvis_platform.base import BasePlatform
    from jarvis.jarvis_agent import Agent


class SessionManager:
    """
    Manages the session state of an agent, including conversation history,
    user data, and persistence.
    """

    def __init__(
        self, model: "BasePlatform", agent_name: str, agent: Optional["Agent"] = None
    ):
        self.model = model
        self.agent_name = agent_name
        self.agent = agent  # 添加agent引用
        self.prompt: str = ""
        self.conversation_length: int = 0
        self.user_data: Dict[str, Any] = {}
        self.addon_prompt: str = ""
        self.last_restored_session: Optional[str] = None  # 记录最后恢复的会话文件路径
        self.non_interactive: bool = False  # 是否为非交互模式

    def set_user_data(self, key: str, value: Any) -> None:
        """Sets a value in the user data dictionary."""
        self.user_data[key] = value

    def get_user_data(self, key: str) -> Optional[Any]:
        """Gets a value from the user data dictionary."""
        return self.user_data.get(key)

    def set_addon_prompt(self, addon_prompt: str) -> None:
        """Sets the addon prompt for the next model call."""
        self.addon_prompt = addon_prompt

    def _list_session_files(self) -> List[str]:
        """
        扫描并返回所有匹配当前会话的会话文件列表。

        Returns:
            会话文件路径列表，按文件名排序。
        """
        session_dir = os.path.join(os.getcwd(), ".jarvis")
        if not os.path.exists(session_dir):
            return []

        platform_name = self.model.platform_name()
        model_name = self.model.name().replace("/", "_").replace("\\", "_")

        # 匹配新旧两种格式的会话文件
        # 旧格式：saved_session_{agent_name}_{platform_name}_{model_name}.json
        # 新格式：saved_session_{agent_name}_{platform_name}_{model_name}_{timestamp}.json
        pattern = os.path.join(
            session_dir,
            f"saved_session_{self.agent_name}_{platform_name}_{model_name}*.json",
        )

        files = sorted(glob.glob(pattern))
        return files

    def _extract_timestamp(self, filename: str) -> Optional[str]:
        """
        从会话文件名中提取时间戳。

        Args:
            filename: 会话文件名（不包含路径）。

        Returns:
            时间戳字符串（如 "20250106_084038"），如果没有时间戳则返回 None。
        """
        import re

        basename = os.path.basename(filename)
        # 新格式：saved_session_{agent_name}_{platform_name}_{model_name}_{timestamp}.json
        # 时间戳格式：YYYYMMDD_HHMMSS（8位日期_6位时间）
        # 使用正则表达式精确匹配时间戳格式
        # \d{8}_\d{6} 匹配 8位数字 + 下划线 + 6位数字
        timestamp_pattern = r"_(\d{8}_\d{6})\.json$"
        match = re.search(timestamp_pattern, basename)

        if match:
            return match.group(1)

        return None

    def _parse_session_files(self) -> List[Tuple[str, Optional[str]]]:
        """
        解析会话文件列表，返回包含文件路径和时间戳的列表。

        Returns:
            会话信息列表，每个元素为 (文件路径, 时间戳)，按时间戳降序排列。
            如果文件没有时间戳，时间戳为 None，这类文件会排在最后。
        """
        files = self._list_session_files()

        sessions = []
        for file_path in files:
            timestamp = self._extract_timestamp(file_path)
            sessions.append((file_path, timestamp))

        # 按时间戳降序排列（最新的在前），没有时间戳的排在最后
        sessions.sort(key=lambda x: (x[1] is None, x[1] or ""), reverse=True)

        return sessions

    def save_session(self) -> bool:
        """Saves the current session state to a file."""
        session_dir = os.path.join(os.getcwd(), ".jarvis")
        os.makedirs(session_dir, exist_ok=True)
        platform_name = self.model.platform_name()
        model_name = self.model.name().replace("/", "_").replace("\\", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_file = os.path.join(
            session_dir,
            f"saved_session_{self.agent_name}_{platform_name}_{model_name}_{timestamp}.json",
        )
        return self.model.save(session_file)

    def restore_session(self) -> bool:
        """Restores the session state from a file."""
        sessions = self._parse_session_files()

        if not sessions:
            PrettyOutput.auto_print("❌ 未找到可恢复的会话文件。")
            return False

        # 如果只有一个会话文件，直接恢复
        if len(sessions) == 1:
            session_file = sessions[0][0]
            timestamp = sessions[0][1]
            time_str = timestamp if timestamp else "(无时间戳)"
            PrettyOutput.auto_print(
                f"📂 恢复会话: {os.path.basename(session_file)} ({time_str})"
            )

            if self.model.restore(session_file):
                self.last_restored_session = session_file  # 记录恢复的会话文件
                PrettyOutput.auto_print("✅ 会话已恢复。")
                return True
            else:
                PrettyOutput.auto_print("❌ 会话恢复失败。")
                return False

        # 多个会话文件，显示列表让用户选择
        # 检查是否为非交互模式
        if self.non_interactive:
            # 非交互模式：自动恢复最新的会话
            session_file = sessions[0][0]
            timestamp = sessions[0][1]
            time_str = timestamp if timestamp else "(无时间戳)"
            PrettyOutput.auto_print(
                f"🤖 非交互模式：自动恢复最新会话: {os.path.basename(session_file)} ({time_str})"
            )

            if self.model.restore(session_file):
                self.last_restored_session = session_file  # 记录恢复的会话文件
                PrettyOutput.auto_print("✅ 会话已恢复。")
                return True
            else:
                PrettyOutput.auto_print("❌ 会话恢复失败。")
                return False

        # 交互模式：显示列表让用户选择
        PrettyOutput.auto_print("📋 找到多个会话文件：")
        for idx, (file_path, timestamp) in enumerate(sessions, 1):
            time_str = timestamp if timestamp else "(无时间戳)"
            PrettyOutput.auto_print(
                f"  {idx}. {os.path.basename(file_path)} [{time_str}]"
            )

        try:
            choice = input("请选择要恢复的会话（输入序号）: ").strip()

            if not choice.isdigit():
                PrettyOutput.auto_print("❌ 无效的选择。")
                return False

            choice_idx = int(choice) - 1
            if choice_idx < 0 or choice_idx >= len(sessions):
                PrettyOutput.auto_print("❌ 无效的选择。")
                return False

            session_file = sessions[choice_idx][0]
            timestamp = sessions[choice_idx][1]
            time_str = timestamp if timestamp else "(无时间戳)"
            PrettyOutput.auto_print(
                f"📂 恢复会话: {os.path.basename(session_file)} ({time_str})"
            )

            if self.model.restore(session_file):
                self.last_restored_session = session_file  # 记录恢复的会话文件
                PrettyOutput.auto_print("✅ 会话已恢复。")
                return True
            else:
                PrettyOutput.auto_print("❌ 会话恢复失败。")
                return False

        except (EOFError, KeyboardInterrupt):
            PrettyOutput.auto_print("⚠️ 用户取消恢复。")
            return False

    def clear_history(self) -> None:
        """
        Clears conversation history but keeps the system prompt by resetting the model state.
        """
        self.prompt = ""
        self.model.reset()
        self.conversation_length = 0

    def clear(self) -> None:
        """
        Clears the session state, resetting prompt and conversation length while
        preserving user_data. This method is an alias of clear_history for backward
        compatibility with existing tests and callers.
        """
        self.clear_history()
