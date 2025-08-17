# -*- coding: utf-8 -*-
import os
from typing import Any, Dict, Optional, TYPE_CHECKING

from jarvis.jarvis_utils.output import OutputType, PrettyOutput

if TYPE_CHECKING:
    from jarvis.jarvis_platform.base import BasePlatform


class SessionManager:
    """
    Manages the session state of an agent, including conversation history,
    user data, and persistence.
    """

    def __init__(self, model: "BasePlatform", agent_name: str):
        self.model = model
        self.agent_name = agent_name
        self.prompt: str = ""
        self.conversation_length: int = 0
        self.user_data: Dict[str, Any] = {}
        self.addon_prompt: str = ""

    def set_user_data(self, key: str, value: Any):
        """Sets a value in the user data dictionary."""
        self.user_data[key] = value

    def get_user_data(self, key: str) -> Optional[Any]:
        """Gets a value from the user data dictionary."""
        return self.user_data.get(key)

    def set_addon_prompt(self, addon_prompt: str):
        """Sets the addon prompt for the next model call."""
        self.addon_prompt = addon_prompt

    def save_session(self) -> bool:
        """Saves the current session state to a file."""
        session_dir = os.path.join(os.getcwd(), ".jarvis")
        os.makedirs(session_dir, exist_ok=True)
        platform_name = self.model.platform_name()
        model_name = self.model.name().replace("/", "_").replace("\\", "_")
        session_file = os.path.join(
            session_dir,
            f"saved_session_{self.agent_name}_{platform_name}_{model_name}.json",
        )
        return self.model.save(session_file)

    def restore_session(self) -> bool:
        """Restores the session state from a file."""
        platform_name = self.model.platform_name()
        model_name = self.model.name().replace("/", "_").replace("\\", "_")
        session_file = os.path.join(
            os.getcwd(),
            ".jarvis",
            f"saved_session_{self.agent_name}_{platform_name}_{model_name}.json",
        )
        if not os.path.exists(session_file):
            return False

        if self.model.restore(session_file):
            try:
                os.remove(session_file)
                PrettyOutput.print("会话已恢复，并已删除会话文件。", OutputType.SUCCESS)
            except OSError as e:
                PrettyOutput.print(f"删除会话文件失败: {e}", OutputType.ERROR)
            return True
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
