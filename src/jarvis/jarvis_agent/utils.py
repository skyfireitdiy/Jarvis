# -*- coding: utf-8 -*-
"""
工具函数（jarvis_agent.utils）

- join_prompts: 统一的提示拼接策略（支持纯文本和多模态内容）
- is_auto_complete: 统一的自动完成标记检测
- fix_tool_call_with_llm: 使用大模型修复工具调用格式
"""

from enum import Enum
from typing import Any, List
from typing import Iterable
from typing import Optional, Union
from typing import cast


from jarvis.jarvis_platform.content_types import ContentBlock
from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_utils.tag import ct
from jarvis.jarvis_utils.tag import ot


def join_prompts(
    parts: Iterable[Union[str, List[ContentBlock]]],
) -> Union[str, List[ContentBlock]]:
    """
    将多个提示片段按统一规则拼接：
    - 支持纯文本和多模态内容
    - 如果所有部分都是字符串，返回拼接后的字符串
    - 如果任何部分是多模态内容，返回合并后的内容块列表
    """
    try:
        all_parts = list(parts)
    except Exception:
        # 防御性处理：若 parts 不可迭代或出现异常，直接返回空字符串
        return ""

    # 检查是否有多模态内容
    has_multimodal = any(isinstance(p, list) for p in all_parts)

    if not has_multimodal:
        # 所有部分都是字符串，使用原有逻辑
        non_empty: list[str] = [p for p in all_parts if isinstance(p, str) and p]
        return "\n\n".join(non_empty)

    # 有多模态内容，需要合并
    result_blocks: List[ContentBlock] = []

    for part in all_parts:
        if isinstance(part, str):
            if part.strip():
                # 将非空字符串转换为文本内容块
                result_blocks.append({"type": "text", "text": part})
        elif isinstance(part, list):
            # 直接添加内容块列表
            result_blocks.extend(part)

    return result_blocks


def is_auto_complete(response: str) -> bool:
    """
    检测是否包含自动完成标记。
    当前实现：包含 ot('!!!COMPLETE!!!') 即视为自动完成。
    """
    try:
        return ot("!!!COMPLETE!!!") in response
    except Exception:
        # 防御性处理：即使 ot 出现异常，也不阻塞主流程
        return "!!!COMPLETE!!!" in response


def normalize_next_action(next_action: Any) -> str:
    """
    规范化下一步动作为字符串:
    - 如果是 Enum, 返回其 value（若为字符串）
    - 如果是 str, 原样返回
    - 其他情况返回空字符串
    """
    try:
        if isinstance(next_action, Enum):
            value = getattr(next_action, "value", None)
            return value if isinstance(value, str) else ""
        if isinstance(next_action, str):
            return next_action
        return ""
    except Exception:
        return ""


def build_fix_prompt(content: str, error_msg: str, tool_usage: str) -> str:
    """构建修复工具调用的提示词

    参数:
        content: 包含错误工具调用的内容
        error_msg: 错误消息
        tool_usage: 工具使用说明

    返回:
        str: 构建好的提示字符串
    """
    return f"""你之前的工具调用格式有误，请根据工具使用说明修复以下内容。

**错误信息：**
{error_msg}

**工具使用说明：**
{tool_usage}

**错误的工具调用内容：**
{content}

请修复上述工具调用内容，确保：
1. 包含完整的 {ot("TOOL_CALL")} 和 {ct("TOOL_CALL")} 标签
2. JSON格式正确，包含 name、arguments、want 三个字段
3. 如果使用多行字符串，直接换行即可

请直接返回修复后的完整工具调用内容，不要添加其他说明文字。"""


def fix_tool_call_with_llm(content: str, agent: Any, error_msg: str) -> Optional[str]:
    """使用大模型修复工具调用格式

    参数:
        content: 包含错误工具调用的内容
        agent: Agent实例，用于调用大模型
        error_msg: 错误消息

    返回:
        Optional[str]: 修复后的内容，如果修复失败则返回None
    """
    try:
        # 获取工具使用说明
        tool_usage = agent.get_tool_usage_prompt()

        # 构建修复提示
        fix_prompt = build_fix_prompt(content, error_msg, tool_usage)

        # 调用大模型修复
        PrettyOutput.auto_print("🤖 尝试使用大模型修复工具调用格式...")
        fixed_content: Any = agent.model.chat_until_success(fix_prompt)

        # 类型检查：确保返回的是字符串
        if fixed_content and isinstance(fixed_content, str):
            PrettyOutput.auto_print("✅ 大模型修复完成")
            # 类型断言：确保返回类型匹配函数签名
            return cast(Optional[str], fixed_content)
        else:
            PrettyOutput.auto_print("❌ 大模型修复失败：返回内容为空")
            return None

    except Exception as e:
        PrettyOutput.auto_print(f"❌ 大模型修复失败：{str(e)}")
        return None


__all__ = [
    "join_prompts",
    "is_auto_complete",
    "normalize_next_action",
    "fix_tool_call_with_llm",
]
