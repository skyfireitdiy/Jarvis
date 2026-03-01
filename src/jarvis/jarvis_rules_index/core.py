"""Core functionality for rules index CLI.

This module provides functions to retrieve and format rules index data.
"""

from typing import Optional

from jarvis.jarvis_agent.rules_manager import RulesManager
from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_utils.utils import get_data_dir


def get_rules_index() -> Optional[str]:
    """Get the builtin rules index.

    Returns:
        The rules index as a formatted string, or None if no rules found.
    """
    try:
        root_dir = get_data_dir()
        manager = RulesManager(root_dir=root_dir)
        index = manager._get_builtin_rules_index()
        return index
    except Exception as e:
        PrettyOutput.auto_print(f"⚠️  获取规则索引失败: {e}")
        return None


def format_rules_index(index: Optional[str], as_json: bool = False) -> str:
    """Format the rules index for output.

    Args:
        index: The rules index content.
        as_json: Whether to format as JSON.

    Returns:
        Formatted output string.
    """
    if index is None:
        return "❌ 未找到任何规则"

    return index
