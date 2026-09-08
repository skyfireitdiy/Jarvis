# -*- coding: utf-8 -*-
"""原生 function calling 的 provider 中立消息模型与工具 schema 工具函数。

本模块定义一套平台中立的"规范消息"dict，OpenAI 与 Anthropic 平台共享：
- assistant 含工具调用：``{"role": "assistant", "content": <str|None>,
  "tool_calls": [{"id", "name", "arguments": <dict>}]}``
- 工具结果：``{"role": "tool", "tool_call_id", "name", "content": <str>}``

提供向 OpenAI / Anthropic 两条消息数组的序列化，以及给压缩、摘要、会话
恢复等纯文本消费者使用的 ``to_text`` 拍平。
"""

import json
from typing import Any, Dict, List, Optional


def make_tool_call_msg(
    content: Optional[str], tool_calls: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """构造 assistant 含工具调用的规范消息。"""
    return {
        "role": "assistant",
        "content": content,
        "tool_calls": list(tool_calls),
    }


def make_tool_call(call_id: str, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """构造单个工具调用项。"""
    return {"id": call_id, "name": name, "arguments": dict(arguments)}


def make_tool_result_msg(
    tool_call_id: str, name: str, content: str
) -> Dict[str, Any]:
    """构造工具结果消息（role=tool）。"""
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": name,
        "content": content,
    }


def is_tool_call_msg(msg: Any) -> bool:
    return (
        isinstance(msg, dict)
        and msg.get("role") == "assistant"
        and bool(msg.get("tool_calls"))
    )


def is_tool_result_msg(msg: Any) -> bool:
    return isinstance(msg, dict) and msg.get("role") == "tool"


def msg_content_text(msg: Any) -> str:
    """稳健地取出消息的可读文本（兼容 str / 内容块列表 / 纯文本 dict）。"""
    if not isinstance(msg, dict):
        return str(msg) if msg is not None else ""
    content = msg.get("content")
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts: List[str] = []
    blocks = content if isinstance(content, list) else [content]
    for block in blocks:
        if isinstance(block, dict):
            block_type = block.get("type")
            if block_type in (None, "text"):
                parts.append(block.get("text", ""))
            else:
                parts.append(json.dumps(block, ensure_ascii=False))
        else:
            parts.append(str(block))
    return "".join(parts)


def to_text(msg: Any) -> str:
    """把任意（含 native 工具）消息拍平为一段文本，供压缩/摘要等消费。"""
    if is_tool_result_msg(msg):
        return f"[工具 {msg.get('name', '')} 结果]\n{msg.get('content') or ''}"
    if is_tool_call_msg(msg):
        text = msg_content_text(msg)
        for tc in msg.get("tool_calls") or []:
            args = tc.get("arguments")
            arg_str = (
                json.dumps(args, ensure_ascii=False)
                if isinstance(args, dict)
                else str(args)
            )
            text += f"\n[调用工具 {tc.get('name')} 参数: {arg_str}]"
        return text
    return msg_content_text(msg)


def to_openai_message(msg: Dict[str, Any]) -> Dict[str, Any]:
    """单条规范消息 -> OpenAI ChatCompletion 消息。"""
    role = msg.get("role")
    if is_tool_call_msg(msg):
        content = msg.get("content") or ""
        tool_calls = []
        for tc in msg.get("tool_calls") or []:
            args = tc.get("arguments")
            arg_str = (
                json.dumps(args, ensure_ascii=False)
                if isinstance(args, dict)
                else str(args)
            )
            tool_calls.append(
                {
                    "id": tc.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": tc.get("name", ""),
                        "arguments": arg_str,
                    },
                }
            )
        return {"role": "assistant", "content": content, "tool_calls": tool_calls}
    if is_tool_result_msg(msg):
        return {
            "role": "tool",
            "tool_call_id": msg.get("tool_call_id", ""),
            "content": msg.get("content") or "",
        }
    out = dict(msg)
    if out.get("content") is None:
        out["content"] = ""
    return out


def to_openai_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [to_openai_message(m) for m in messages]


def to_anthropic_messages(
    messages: List[Dict[str, Any]],
) -> tuple[Optional[str], List[Dict[str, Any]]]:
    """规范消息列表 -> (system_text, anthropic 消息列表)。

    - system 消息拼接为顶层 system 文本；
    - assistant 工具调用转成 content 块（text + tool_use）；
    - 连续的 role=tool 结果合并进紧随其后的 user 消息的 tool_result 内容块。
    """
    system_parts: List[str] = []
    out: List[Dict[str, Any]] = []
    pending_results: List[Dict[str, Any]] = []

    def flush_results() -> None:
        if not pending_results:
            return
        blocks = [
            {
                "type": "tool_result",
                "tool_use_id": r.get("tool_call_id", ""),
                "content": r.get("content") or "",
            }
            for r in pending_results
        ]
        pending_results.clear()
        # 工具结果必须放在一条 user 消息里；若上一条是纯文本 user，合并会导致内容错位，
        # 因此总是新开一条仅含 tool_result 的 user 消息（Anthropic 允许）。
        out.append({"role": "user", "content": blocks})

    for msg in messages:
        role = msg.get("role")
        if role == "system":
            system_parts.append(msg_content_text(msg))
            continue
        if is_tool_result_msg(msg):
            pending_results.append(msg)
            continue
        flush_results()
        if is_tool_call_msg(msg):
            blocks: List[Dict[str, Any]] = []
            text = msg_content_text(msg)
            if text:
                blocks.append({"type": "text", "text": text})
            for tc in msg.get("tool_calls") or []:
                args = tc.get("arguments")
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": tc.get("name", ""),
                        "input": args if isinstance(args, dict) else {},
                    }
                )
            out.append({"role": "assistant", "content": blocks})
            continue
        content = msg.get("content")
        out.append(
            {"role": role, "content": content if content is not None else ""}
        )
    flush_results()
    return ("\n".join(system_parts) if system_parts else None, out)


# 与文本协议一致的定时/延迟调用参数：可附加到任意工具参数 schema，
# 供模型以原生方式声明 after/at/loop。
_TIMER_PROPERTIES: Dict[str, Any] = {
    "after": {
        "type": "integer",
        "description": "延迟执行：N 秒后执行本工具（与其它实参一起用，不要单独使用）",
    },
    "at": {
        "type": "string",
        "description": "定时执行：ISO8601 时间点执行本工具（与其它实参一起用，不要单独使用）",
    },
    "loop": {
        "type": "integer",
        "description": "循环执行：每 N 秒执行一次本工具（与其它实参一起用，不要单独使用）",
    },
}
_TIMER_KEYS = ("after", "at", "loop")


def with_timer_params(schema: Dict[str, Any]) -> Dict[str, Any]:
    """在工具参数 schema 上附加可选定时参数（若工具自身未定义同名参数）。"""
    if not isinstance(schema, dict):
        return schema
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return schema
    if any(key in properties for key in _TIMER_KEYS):
        return schema
    merged = dict(properties)
    merged.update(_TIMER_PROPERTIES)
    out = dict(schema)
    out["properties"] = merged
    return out


def build_openai_tools(registry: Any) -> List[Dict[str, Any]]:
    """从 ToolRegistry 构建 OpenAI tools 数组。"""
    tools = []
    for tool in registry.tools.values():
        parameters = getattr(tool, "parameters", None) or {
            "type": "object",
            "properties": {},
        }
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": getattr(tool, "description", "") or "",
                    "parameters": with_timer_params(parameters),
                },
            }
        )
    return tools


def build_anthropic_tools(registry: Any) -> List[Dict[str, Any]]:
    """从 ToolRegistry 构建 Anthropic tools 数组。"""
    tools = []
    for tool in registry.tools.values():
        parameters = getattr(tool, "parameters", None) or {
            "type": "object",
            "properties": {},
        }
        tools.append(
            {
                "name": tool.name,
                "description": getattr(tool, "description", "") or "",
                "input_schema": with_timer_params(parameters),
            }
        )
    return tools
