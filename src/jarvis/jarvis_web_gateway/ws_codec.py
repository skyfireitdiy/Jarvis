"""WebSocket 消息压缩编解码工具。

在 JSON 序列化后、发送前压缩；接收后、解析前解压。
协议兼容：首字节 0x78（zlib header）标记压缩，'{' 开头为普通 JSON。
小消息（<1KB）跳过压缩，避免无谓开销。
"""

import json
import zlib
from typing import Any, Dict

# 压缩阈值：小于此大小的消息不压缩
_COMPRESS_THRESHOLD = 1024

# zlib 压缩级别（1-9，6 为默认平衡值）
_COMPRESS_LEVEL = 6


def compress_if_needed(data: str) -> bytes:
    """若消息超过阈值则压缩，否则返回原文本字节。"""
    raw = data.encode("utf-8")
    if len(raw) >= _COMPRESS_THRESHOLD:
        return zlib.compress(raw, _COMPRESS_LEVEL)
    return raw


def decompress_if_needed(data: bytes) -> str:
    """若首字节为 0x78（zlib header）则解压，否则直接解码。"""
    if data and data[0] == 0x78:
        return zlib.decompress(data).decode("utf-8")
    return data.decode("utf-8")


async def send_json_compressed(websocket: Any, message: Dict[str, Any]) -> None:
    """序列化 JSON 并压缩后发送。

    大消息以二进制（压缩）发送，小消息以文本发送。
    """
    text = json.dumps(message, ensure_ascii=False)
    compressed = compress_if_needed(text)
    if len(compressed) < len(text.encode("utf-8")):
        await websocket.send_bytes(compressed)
    else:
        await websocket.send_text(text)


async def receive_json_compressed(websocket: Any) -> Dict[str, Any]:
    """接收消息并解压后解析 JSON。

    兼容二进制（压缩）与文本（未压缩）两种消息。
    """
    message = await websocket.receive()
    if message.get("bytes") is not None:
        # 二进制消息（可能为 zlib 压缩）
        text = decompress_if_needed(message["bytes"])
    elif message.get("text") is not None:
        # 文本消息（未压缩 JSON）
        text = message["text"]
    else:
        # 其他消息类型（如断开连接），返回空字典
        return {}
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}
