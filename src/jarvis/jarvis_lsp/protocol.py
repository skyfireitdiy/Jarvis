"""LSP 协议模块

该模块提供 LSP（Language Server Protocol）的协议定义和
JSON-RPC 消息编解码功能。
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class LSPRequest:
    """LSP 请求数据类

    Attributes:
        jsonrpc: JSON-RPC 版本，固定为 "2.0"
        id: 请求 ID
        method: 方法名
        params: 请求参数
    """

    jsonrpc: str
    id: int
    method: str
    params: Optional[Dict[str, Any]]


@dataclass
class LSPResponse:
    """LSP 响应数据类

    Attributes:
        jsonrpc: JSON-RPC 版本，固定为 "2.0"
        id: 请求 ID
        result: 响应结果
        error: 错误信息
    """

    jsonrpc: str
    id: Optional[int]
    result: Optional[Any]
    error: Optional[Dict[str, Any]]


@dataclass
class LSPNotification:
    """LSP 通知数据类

    Attributes:
        jsonrpc: JSON-RPC 版本，固定为 "2.0"
        method: 方法名
        params: 通知参数
    """

    jsonrpc: str
    method: str
    params: Optional[Dict[str, Any]]


class LSPMessageCodec:
    """LSP 消息编解码器

    处理 LSP 协议的 JSON-RPC 消息编解码，包括
    Content-Length 头的处理。
    """

    CONTENT_LENGTH_HEADER = "Content-Length"

    @staticmethod
    def encode_request(request: LSPRequest) -> bytes:
        """编码 LSP 请求

        Args:
            request: LSP 请求对象

        Returns:
            编码后的字节数据
        """
        content = json.dumps(
            {
                "jsonrpc": request.jsonrpc,
                "id": request.id,
                "method": request.method,
                "params": request.params,
            },
            ensure_ascii=False,
        )
        return LSPMessageCodec._encode_content(content)

    @staticmethod
    def encode_response(response: LSPResponse) -> bytes:
        """编码 LSP 响应

        Args:
            response: LSP 响应对象

        Returns:
            编码后的字节数据
        """
        content = json.dumps(
            {
                "jsonrpc": response.jsonrpc,
                "id": response.id,
                "result": response.result,
                "error": response.error,
            },
            ensure_ascii=False,
        )
        return LSPMessageCodec._encode_content(content)

    @staticmethod
    def encode_notification(notification: LSPNotification) -> bytes:
        """编码 LSP 通知

        Args:
            notification: LSP 通知对象

        Returns:
            编码后的字节数据
        """
        content = json.dumps(
            {
                "jsonrpc": notification.jsonrpc,
                "method": notification.method,
                "params": notification.params,
            },
            ensure_ascii=False,
        )
        return LSPMessageCodec._encode_content(content)

    @staticmethod
    def _encode_content(content: str) -> bytes:
        """编码消息内容

        Args:
            content: JSON 字符串

        Returns:
            包含 Content-Length 头和内容的字节数据
        """
        content_bytes = content.encode("utf-8")
        header = (
            f"{LSPMessageCodec.CONTENT_LENGTH_HEADER}: {len(content_bytes)}\r\n"
            f"Content-Type: application/vscode-jsonrpc; charset=utf8\r\n\r\n"
        )
        return header.encode("utf-8") + content_bytes

    @staticmethod
    def decode_message(data: bytes) -> LSPResponse:
        """解码 LSP 消息

        Args:
            data: 接收到的字节数据

        Returns:
            LSP 响应对象

        Raises:
            ValueError: 消息格式错误
        """
        # 去除前面可能的空行
        data = data.lstrip(b"\r\n")
        
        # 解析 Content-Length 头
        try:
            headers, content = data.split(b"\r\n\r\n", 1)
            header_lines = headers.decode("utf-8").split("\r\n")
            content_length = None
            for line in header_lines:
                if line.startswith(f"{LSPMessageCodec.CONTENT_LENGTH_HEADER}:"):
                    content_length = int(line.split(":", 1)[1].strip())
                    break

            if content_length is None:
                raise ValueError("Missing Content-Length header")

            content_str = content.decode("utf-8")
            message_dict = json.loads(content_str)

            # 区分响应和通知
            if "id" in message_dict:
                return LSPResponse(
                    jsonrpc=message_dict.get("jsonrpc", "2.0"),
                    id=message_dict["id"],
                    result=message_dict.get("result"),
                    error=message_dict.get("error"),
                )
            else:
                # 通知，这里简化处理，返回响应对象
                return LSPResponse(
                    jsonrpc=message_dict.get("jsonrpc", "2.0"),
                    id=None,
                    result=message_dict.get("params"),
                    error=None,
                )

        except (ValueError, json.JSONDecodeError) as e:
            raise ValueError(f"Failed to decode LSP message: {e}") from e
