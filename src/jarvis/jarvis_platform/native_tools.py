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


def _sanitize_surrogates(text: str) -> str:
    """把孤立 UTF-16 代理字符替换为 U+FFFD，保证文本可被 UTF-8 编码。

    背景：消息历史中可能混入孤立代理字符（U+D800-U+DFFF 单独出现，属非法
    Unicode）。常见来源：
    - 以 ``errors="surrogateescape"`` 解码非法字节（Python 文件系统编码默认
      即为 ``utf-8/surrogateescape``）；
    - 前端 JS ``JSON.stringify`` 把孤立代理转义为 ``\\udXXX``，经 Python
      ``json.loads`` 还原为真正的代理字符。

    ``json.dumps`` 能正常处理这类字符，但发送请求时 httpx 会执行
    ``json_dumps(..., ensure_ascii=False).encode("utf-8")``，此时抛
    ``UnicodeEncodeError: surrogates not allowed``，导致原生工具调用失败并
    降级为纯文本协议。故在序列化出口统一清理。

    注意：Python 中合法的 BMP 外字符（如 ``😀`` U+1F600）是单个码点，不落在
    代理区，天然不受影响，会被原样保留。
    """
    if not text:
        return text
    # 快速路径：绝大多数文本不含代理字符，避免逐字符扫描开销
    if not any(0xD800 <= ord(ch) <= 0xDFFF for ch in text):
        return text
    return "".join(
        "\ufffd" if 0xD800 <= ord(ch) <= 0xDFFF else ch for ch in text
    )


def _sanitize_value(value: Any) -> Any:
    """递归清理任意嵌套结构中的孤立代理字符，返回新对象（不修改入参）。"""
    if isinstance(value, str):
        return _sanitize_surrogates(value)
    if isinstance(value, dict):
        return {k: _sanitize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_value(v) for v in value)
    return value


def sanitize_message(msg: Dict[str, Any]) -> Dict[str, Any]:
    """清理一条规范消息中所有字符串字段的孤立代理字符。

    覆盖 content、tool_calls 的 name/arguments、tool_call_id、name 等字段，
    返回新对象，不原地修改入参。
    """
    if not isinstance(msg, dict):
        return msg
    return {k: _sanitize_value(v) for k, v in msg.items()}


def make_tool_call_msg(
    content: Optional[str], tool_calls: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """构造 assistant 含工具调用的规范消息。"""
    return {
        "role": "assistant",
        "content": content,
        "tool_calls": list(tool_calls),
    }


def make_tool_call(
    call_id: str, name: str, arguments: Dict[str, Any]
) -> Dict[str, Any]:
    """构造单个工具调用项。"""
    return {"id": call_id, "name": name, "arguments": dict(arguments)}


def make_tool_result_msg(tool_call_id: str, name: str, content: str) -> Dict[str, Any]:
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
    # 当前未闭合 assistant(tool_calls) 下已保留的 tool 结果在 out 中的索引。
    # 一旦该 assistant 因配对不完整被删除，这些结果也必须一并删除，
    # 否则会残留孤立 tool 消息，导致 API 400。
    matched_result_idx: List[int] = []

    def _drop_open_assistant() -> None:
        """删除未闭合的 assistant(tool_calls) 及其已保留的 tool 结果。"""
        nonlocal open_idx
        if open_idx is None:
            return
        # 先删索引更大的结果，避免删除后索引错位
        for idx in sorted(matched_result_idx, reverse=True):
            del out[idx]
        del out[open_idx]
        open_idx = None
        matched_result_idx.clear()

    for msg in messages:
        if is_tool_call_msg(msg):
            _drop_open_assistant()
            ids = {(tc.get("id") or "") for tc in msg.get("tool_calls") or []}
            ids.discard("")
            if not ids:
                out.append(msg)
            else:
                out.append(msg)
                pending_ids = set(ids)
                open_idx = len(out) - 1
                matched_result_idx = []
        elif is_tool_result_msg(msg):
            tid = msg.get("tool_call_id") or ""
            if tid and tid in pending_ids:
                pending_ids.discard(tid)
                out.append(msg)
                matched_result_idx.append(len(out) - 1)
                if not pending_ids:
                    open_idx = None
                    matched_result_idx = []
            # 孤立 tool 结果：丢弃
        else:
            _drop_open_assistant()
            pending_ids = set()
            out.append(msg)

    _drop_open_assistant()
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
    # 出口统一清理孤立代理字符，避免 httpx 以 UTF-8 编码请求体时抛
    # UnicodeEncodeError（详见 _sanitize_surrogates 说明）。
    return [
        to_openai_message(sanitize_message(m))
        for m in ensure_tool_pairing(messages)
    ]


def to_anthropic_messages(
    messages: List[Dict[str, Any]],
) -> tuple[Optional[str], List[Dict[str, Any]]]:
    """规范消息列表 -> (system_text, anthropic 消息列表)。

    - system 消息拼接为顶层 system 文本；
    - assistant 工具调用转成 content 块（text + tool_use）；
    - 连续的 role=tool 结果合并进紧随其后的 user 消息的 tool_result 内容块。

    出口统一清理孤立代理字符，避免 Anthropic SDK 以 UTF-8 编码请求体时抛
    UnicodeEncodeError（详见 _sanitize_surrogates 说明）。
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

    for raw_msg in ensure_tool_pairing(messages):
        msg = sanitize_message(raw_msg)
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
        out.append({"role": role, "content": content if content is not None else ""})
    flush_results()
    return ("\n".join(system_parts) if system_parts else None, out)


# 与文本协议一致的定时/延迟调用参数：可附加到任意工具参数 schema，
# 供模型以原生方式声明 after/at/loop。
_TIMER_PROPERTIES: Dict[str, Any] = {
    "after": {
        "type": "integer",
        "description": "延迟 N 秒后再执行本工具（与其它实参同用，勿单用）",
    },
    "at": {
        "type": "string",
        "description": "到该 ISO8601 时间点执行本工具（与其它实参同用，勿单用）",
    },
    "loop": {
        "type": "integer",
        "description": "每 N 秒重复执行本工具（与其它实参同用，勿单用）",
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
        parameters = with_timer_params(ensure_object_schema(parameters))
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": getattr(tool, "description", "") or "",
                    "parameters": parameters,
                },
            }
        )
    return tools


def build_anthropic_tools(registry: Any) -> List[Dict[str, Any]]:
    """从 ToolRegistry 构建 Anthropic tools 数组。"""
    tools = []
    for tool in registry.tools.values():
        parameters = getattr(tool, "parameters", None) or {}
        parameters = with_timer_params(ensure_object_schema(parameters))
        tools.append(
            {
                "name": tool.name,
                "description": getattr(tool, "description", "") or "",
                "input_schema": parameters,
            }
        )
    return tools
