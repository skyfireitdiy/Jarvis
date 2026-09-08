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


def ensure_tool_pairing(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """清洗规范消息历史，保证 tool_calls 与 role=tool 回包配对完整。

    历史被裁剪/压缩切断配对时，OpenAI/Anthropic 会 400（assistant tool_calls 后
    缺对应 tool 消息）。此函数：
    - 丢弃"带 tool_calls 但后续无任何匹配 tool 回包"的 assistant 消息；
    - 丢弃没有对应前置 tool_calls 的孤立 tool 结果；
    - 保留正常配对。
    """
    out: List[Dict[str, Any]] = []
    pending_ids = set()
    open_idx: Optional[int] = None

    for msg in messages:
        if is_tool_call_msg(msg):
            if open_idx is not None:
                del out[open_idx]
            ids = {(tc.get("id") or "") for tc in msg.get("tool_calls") or []}
            ids.discard("")
            if not ids:
                out.append(msg)
            else:
                out.append(msg)
                pending_ids = set(ids)
                open_idx = len(out) - 1
        elif is_tool_result_msg(msg):
            tid = msg.get("tool_call_id") or ""
            if tid and tid in pending_ids:
                pending_ids.discard(tid)
                out.append(msg)
                if not pending_ids:
                    open_idx = None
            # 孤立 tool 结果：丢弃
        else:
            if open_idx is not None:
                del out[open_idx]
            open_idx = None
            pending_ids = set()
            out.append(msg)

    if open_idx is not None:
        del out[open_idx]
    return out


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
    return [to_openai_message(m) for m in ensure_tool_pairing(messages)]


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

    for msg in ensure_tool_pairing(messages):
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


def ensure_object_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """把工具参数 schema 归一为函数所需的 object 型 JSON Schema。

    不少内置/自定义工具的 parameters 只写 properties/required 而缺顶层 type，
    被 OpenAI/Anthropic 拒绝（"schema must be a JSON Schema of type object"）。
    这里补上顶层 type=object，并保证 properties 存在。
    """
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}
    out = dict(schema)
    if not out.get("type"):
        out["type"] = "object"
    if not isinstance(out.get("properties"), dict):
        out["properties"] = {}
    return out


def build_openai_tools(registry: Any) -> List[Dict[str, Any]]:
    """从 ToolRegistry 构建 OpenAI tools 数组。"""
    tools = []
    for tool in registry.tools.values():
        parameters = getattr(tool, "parameters", None) or {}
        parameters = ensure_object_schema(parameters)
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
        parameters = getattr(tool, "parameters", None) or {}
        parameters = ensure_object_schema(parameters)
        tools.append(
            {
                "name": tool.name,
                "description": getattr(tool, "description", "") or "",
                "input_schema": with_timer_params(parameters),
            }
        )
    return tools
