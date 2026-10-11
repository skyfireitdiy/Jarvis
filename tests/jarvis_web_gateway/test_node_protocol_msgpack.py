# -*- coding: utf-8 -*-
"""跨节点消息二进制（msgpack）编解码单元测试。

覆盖 node_protocol.encode_node_message / decode_node_message：
1. msgpack roundtrip（含中文、嵌套 dict/list、None、bytes、非 ASCII key）
2. 无魔数前缀的 JSON 字节回退解析（兼容旧版）
3. 魔数帧头正确性
4. encode 后为 bytes 类型且带魔数前缀
"""
import os

# 必须在导入 jarvis 模块之前设置环境变量，避免触发交互式配置
os.environ["JARVIS_SKIP_INTERACTIVE_CONFIG"] = "1"

import json

from jarvis.jarvis_web_gateway.node_protocol import (
    MAGIC,
    build_node_message,
    decode_node_message,
    encode_node_message,
)


def _sample_message() -> dict:
    """构造一个覆盖常见负载类型的节点消息。"""
    return build_node_message(
        "test_type",
        {
            "node_id": "sf-pc",
            "中文键": "中文值",
            "nested": {"a": [1, 2, 3], "b": None},
            "body": b"\x00\x01binary",
        },
        request_id="req-1",
    )


def test_encode_decode_roundtrip():
    """msgpack 编解码 roundtrip 应完整还原消息。"""
    msg = _sample_message()
    encoded = encode_node_message(msg)
    assert decode_node_message(encoded) == msg


def test_encode_result_is_bytes_with_magic():
    """encode 结果应为 bytes 且带魔数前缀。"""
    encoded = encode_node_message(_sample_message())
    assert isinstance(encoded, bytes)
    assert encoded.startswith(MAGIC)


def test_magic_header():
    """魔数帧头应正确。"""
    assert MAGIC == b"\x93JAR"


def test_decode_json_bytes_fallback():
    """无魔数前缀的 JSON 字节应回退解析（兼容旧版）。"""
    msg = build_node_message(
        "test_type",
        {"node_id": "sf-pc", "nested": {"a": [1, 2, 3], "b": None}},
        request_id="req-1",
    )
    json_bytes = json.dumps(msg).encode("utf-8")
    assert decode_node_message(json_bytes) == msg


def test_decode_json_str_fallback():
    """str 形式的 JSON 文本也应回退解析。"""
    msg = build_node_message("test_type", {"node_id": "sf-pc"}, request_id="req-1")
    assert decode_node_message(json.dumps(msg)) == msg


def test_decode_plain_json_bytes_without_magic():
    """不带魔数且为纯 JSON 可序列化数据的字节应正确回退。"""
    payload = {"success": True, "status_code": 200, "headers": {}, "body": "ok"}
    msg = build_node_message("agent_http_response", payload, request_id="req-2")
    json_bytes = json.dumps(msg).encode("utf-8")
    assert decode_node_message(json_bytes) == msg
