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
class HoverInfo:
    """符号悬停信息

    包含符号的注释、类型、参数说明、文档字符串等语义信息。
    用于为 LLM 补充代码的语义信息，避免解析原始代码。

    Attributes:
        contents: 悬停内容（Markdown 或纯文本格式）
        range: 符号的位置范围（可选）
        file_path: 文件路径
        line: 符号所在行号（0-based）
        character: 符号所在列号（0-based）
    """

    contents: str
    range: Optional[tuple[int, int, int, int]]  # (start_line, start_char, end_line, end_char)
    file_path: str
    line: int
    character: int


@dataclass
class FoldingRangeInfo:
    """代码折叠范围信息

    用于表示代码中可折叠的区域，如函数、类、if 语句等。
    这可以帮助 LLM 识别代码块的边界。

    Attributes:
        start_line: 起始行号（0-based）
        start_character: 起始列号（0-based）
        end_line: 结束行号（0-based，包含）
        end_character: 结束列号（0-based，包含）
        kind: 折叠范围类型（如 comment, region, imports 等）
        collapsed_text: 折叠时显示的文本（可选）
    """

    start_line: int
    start_character: int
    end_line: int
    end_character: int
    kind: Optional[str] = None
    collapsed_text: Optional[str] = None


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


@dataclass
class DiagnosticInfo:
    """代码诊断信息

    包含语法错误、lint 警告、类型错误、代码规范问题等。
    用于为 LLM 提供代码质量检查信息。

    Attributes:
        range: 问题位置范围 (start_line, start_char, end_line, end_char)
        severity: 严重级别 (Error=1, Warning=2, Info=3, Hint=4)
        code: 错误代码（可选）
        source: 诊断来源（pylint、mypy、pyflakes 等）
        message: 错误信息
    """

    range: tuple[int, int, int, int]  # (start_line, start_char, end_line, end_char)
    severity: int  # 1=Error, 2=Warning, 3=Info, 4=Hint
    code: Optional[str]
    source: str
    message: str


@dataclass
class CodeActionInfo:
    """代码动作信息

    包含可执行的修复动作，如修复错误、重构、优化等。
    用于为 LLM 提供代码修复建议。

    Attributes:
        title: 操作标题
        kind: 操作类型（quickfix/refactor/rename/source.organizeImports 等）
        is_preferred: 是否为首选操作
    """

    title: str
    kind: str
    is_preferred: bool
