"""LSP 客户端模块

该模块提供 LSP 客户端核心功能，包括与 LSP 服务器的
异步通信、初始化、符号查询等。
"""

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

from jarvis.jarvis_lsp.protocol import (
    LSPMessageCodec,
    LSPNotification,
    LSPRequest,
    LSPResponse,
)


@dataclass
class SymbolInfo:
    """符号信息数据类

    Attributes:
        name: 符号名称
        kind: 符号类型（function, class, variable 等）
        line: 行号
        column: 列号
        description: 描述信息
    """

    name: str
    kind: str
    line: int
    column: int
    description: Optional[str] = None


class LSPClient:
    """LSP 客户端类

    负责与 LSP 服务器通信，提供初始化、文档打开、符号查询等功能。
    """

    def __init__(self, command: str, args: List[str]) -> None:
        """初始化 LSP 客户端

        Args:
            command: LSP 服务器可执行文件命令
            args: 启动参数列表
        """
        self.command = command
        self.args = args
        self.process: Optional[asyncio.subprocess.Process] = None
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.request_id: int = 0
        self.root_uri: Optional[str] = None
        self._initialized: bool = False

    async def initialize(self) -> None:
        """初始化 LSP 服务器

        启动 LSP 服务器进程并发送 initialize 请求。

        Raises:
            RuntimeError: 服务器启动失败或初始化失败
        """
        # 启动 LSP 服务器进程
        # 将 stderr 重定向到 PIPE 以捕获错误信息
        self.process = await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        if not self.process or not self.process.stdout or not self.process.stdin or not self.process.stderr:
            raise RuntimeError("Failed to start LSP server process")

        # 类型断言：self.process 已经在上面检查过不为 None
        assert self.process is not None
        assert self.process.stdout is not None
        assert self.process.stdin is not None
        assert self.process.stderr is not None

        # 等待一小段时间确保进程启动
        await asyncio.sleep(0.2)

        # 检查进程是否立即退出
        if self.process.returncode is not None:
            # 进程已退出，读取 stderr 错误信息
            if self.process.stderr:
                stderr_output = await self.process.stderr.read()
                error_msg = stderr_output.decode("utf-8", errors="ignore")
                raise RuntimeError(
                    f"LSP server '{' '.join([self.command] + self.args)}' failed to start\n"
                    f"Exit code: {self.process.returncode}\n"
                    f"Error: {error_msg}\n\n"
                    f"To install Python LSP server: pip install python-lsp-server\n"
                    f"To install Rust LSP server: rustup component add rust-analyzer\n"
                    f"To install Go LSP server: go install golang.org/x/tools/gopls@latest\n"
                    f"For other languages, see: https://microsoft.github.io/language-server-protocol/implementors/tools/"
                )
            else:
                raise RuntimeError(
                    f"LSP server '{self.command}' exited with code {self.process.returncode}"
                )

        self.reader = self.process.stdout
        self.writer = self.process.stdin

        # 发送 initialize 请求
        request = LSPRequest(
            jsonrpc="2.0",
            id=self._next_id(),
            method="initialize",
            params={
                "processId": self.process.pid if self.process.pid else None,
                "rootUri": self.root_uri,
                "capabilities": {
                    "textDocument": {
                        "documentSymbol": {
                            "hierarchicalDocumentSymbolSupport": True
                        }
                    }
                },
            },
        )

        await self._send_request(request)
        
        try:
            response = await self._read_response(timeout=30.0)
        except asyncio.TimeoutError:
            raise RuntimeError(
                "LSP server initialization timed out after 30 seconds. "
                "The server may be unresponsive or slow to start."
            )

        if response.error:
            raise RuntimeError(
                f"LSP initialization failed: {response.error}"
            )

        # 发送 initialized 通知
        notification = LSPNotification(
            jsonrpc="2.0",
            method="initialized",
            params={},
        )
        await self._send_notification(notification)

        self._initialized = True

    async def open_document(self, file_path: str) -> None:
        """打开文档

        Args:
            file_path: 文件路径

        Raises:
            RuntimeError: 客户端未初始化
        """
        if not self._initialized:
            raise RuntimeError("LSP client not initialized")

        path = Path(file_path).resolve()
        uri = f"file://{path}"

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        notification = LSPNotification(
            jsonrpc="2.0",
            method="textDocument/didOpen",
            params={
                "textDocument": {
                    "uri": uri,
                    "languageId": "python",  # 可以自动检测
                    "version": 1,
                    "text": content,
                }
            },
        )

        await self._send_notification(notification)

    async def document_symbol(self, file_path: str) -> List[SymbolInfo]:
        """获取文档符号

        Args:
            file_path: 文件路径

        Returns:
            符号信息列表

        Raises:
            RuntimeError: 客户端未初始化或查询失败
        """
        if not self._initialized:
            raise RuntimeError("LSP client not initialized")

        # 先打开文档
        await self.open_document(file_path)

        # 类型断言：open_document 确保了 process 已初始化
        if self.process is None:
            raise RuntimeError("LSP server process is not initialized")

        path = Path(file_path).resolve()
        uri = f"file://{path}"

        # 发送 documentSymbol 请求
        request = LSPRequest(
            jsonrpc="2.0",
            id=self._next_id(),
            method="textDocument/documentSymbol",
            params={
                "textDocument": {
                    "uri": uri,
                }
            },
        )

        await self._send_request(request)
        
        # 检查进程是否还在运行
        await asyncio.sleep(0.5)
        if self.process.returncode is not None:
            # 进程已退出，读取 stderr 错误信息
            if self.process.stderr:
                stderr_output = await self.process.stderr.read()
                error_msg = stderr_output.decode("utf-8", errors="ignore")
            else:
                error_msg = "No stderr output available"
            raise RuntimeError(
                f"LSP server '{' '.join([self.command] + self.args)}' crashed after sending initialize request\n"
                f"Exit code: {self.process.returncode}\n"
                f"Error: {error_msg}"
            )
        
        try:
            response = await self._read_response(timeout=30.0)
        except asyncio.TimeoutError:
            raise RuntimeError(
                "LSP server initialization timed out after 30 seconds. "
                "The server may be unresponsive or slow to start."
            )

        if response.error:
            raise RuntimeError(
                f"Document symbol request failed: {response.error}"
            )


        # 解析符号
        symbols = self._parse_symbols(response.result)
        return symbols

    async def close_document(self, file_path: str) -> None:
        """关闭文档

        Args:
            file_path: 文件路径

        Raises:
            RuntimeError: 客户端未初始化
        """
        if not self._initialized:
            raise RuntimeError("LSP client not initialized")

        path = Path(file_path).resolve()
        uri = f"file://{path}"

        notification = LSPNotification(
            jsonrpc="2.0",
            method="textDocument/didClose",
            params={
                "textDocument": {
                    "uri": uri,
                }
            },
        )

        await self._send_notification(notification)

    async def shutdown(self) -> None:
        """关闭 LSP 客户端

        发送 shutdown 和 exit 请求，并关闭进程。
        """
        if self._initialized:
            try:
                # 发送 shutdown 请求
                request = LSPRequest(
                    jsonrpc="2.0",
                    id=self._next_id(),
                    method="shutdown",
                    params={},
                )
                await self._send_request(request)
                try:
                    await asyncio.wait_for(
                        self._read_response(),
                        timeout=5.0
                    )
                except (asyncio.TimeoutError, Exception):
                    # 忽略 shutdown 响应超时或错误，继续关闭
                    pass

                # 发送 exit 通知
                notification = LSPNotification(
                    jsonrpc="2.0",
                    method="exit",
                    params={},
                )
                await self._send_notification(notification)
            except Exception:  # nosec: B110
                # 忽略关闭时的错误
                pass

        # 关闭进程
        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except Exception:
                try:
                    self.process.kill()
                    await asyncio.wait_for(self.process.wait(), timeout=5.0)
                except Exception:  # nosec: B110
                    pass

        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:  # nosec: B110
                pass

        self._initialized = False

    def _next_id(self) -> int:
        """获取下一个请求 ID"""
        self.request_id += 1
        return self.request_id

    async def _send_request(self, request: LSPRequest) -> None:
        """发送请求

        Args:
            request: LSP 请求对象

        Raises:
            RuntimeError: 写入失败
        """
        if not self.writer:
            raise RuntimeError("Writer not initialized")

        data = LSPMessageCodec.encode_request(request)
        self.writer.write(data)
        await self.writer.drain()

    async def _send_notification(self, notification: LSPNotification) -> None:
        """发送通知

        Args:
            notification: LSP 通知对象

        Raises:
            RuntimeError: 写入失败
        """
        if not self.writer:
            raise RuntimeError("Writer not initialized")

        data = LSPMessageCodec.encode_notification(notification)
        self.writer.write(data)
        await self.writer.drain()

    async def _read_response(self, timeout: float = 30.0) -> LSPResponse:
        """读取响应

        Args:
            timeout: 超时时间（秒）

        Returns:
            LSP 响应对象

        Raises:
            RuntimeError: 读取失败或超时
        """
        if not self.reader:
            raise RuntimeError("Reader not initialized")
        
        while True:
            # 读取 Content-Length 头
            header_line = await asyncio.wait_for(
                self.reader.readline(),
                timeout=timeout
            )
            if not header_line:
                raise RuntimeError("Failed to read response header")

            content_length = int(header_line.decode("utf-8").split(":", 1)[1].strip())

            # 跳过所有剩余的头行，直到遇到空行（\r\n）
            while True:
                line = await asyncio.wait_for(
                    self.reader.readline(),
                    timeout=timeout
                )
                if line == b"\r\n":  # 空行表示头结束
                    break

            # 读取 JSON 内容
            content_bytes = await asyncio.wait_for(
                self.reader.readexactly(content_length),
                timeout=timeout
            )
            
            # 直接解析 JSON
            content_str = content_bytes.decode("utf-8")
            message_dict = json.loads(content_str)
            
            # 检查是否是响应（有 id）而不是通知（没有 id）
            if "id" in message_dict:
                response = LSPResponse(
                    jsonrpc=message_dict.get("jsonrpc", "2.0"),
                    id=message_dict.get("id"),
                    result=message_dict.get("result"),
                    error=message_dict.get("error")
                )
                return response

    def _parse_symbols(self, result: Any) -> List[SymbolInfo]:
        """解析符号

        Args:
            result: documentSymbol 响应结果

        Returns:
            符号信息列表
        """
        symbols: List[SymbolInfo] = []

        if not isinstance(result, list):
            return symbols

        def _parse_symbol_item(item: Any) -> Optional[SymbolInfo]:
            if not isinstance(item, dict):
                return None

            name = item.get("name")
            kind = item.get("kind")
            
            # 位置信息可能在 location.range 或直接在 range
            location = item.get("location", {})
            if "range" in location:
                range_info = location["range"]
            else:
                range_info = item.get("range", {})
            
            start = range_info.get("start", {})
            line = start.get("line", 0)
            column = start.get("character", 0)

            # LSP SymbolKind 映射
            kind_map: dict[int, str] = {
                1: "file",
                2: "module",
                3: "namespace",
                4: "package",
                5: "class",
                6: "method",
                7: "property",
                8: "field",
                9: "constructor",
                10: "enum",
                11: "interface",
                12: "function",
                13: "variable",
                14: "constant",
                15: "string",
                16: "number",
                17: "boolean",
                18: "array",
                19: "object",
                20: "key",
                21: "null",
                22: "enumMember",
                23: "struct",
                24: "event",
                25: "operator",
                26: "typeParameter",
            }

            if isinstance(kind, int):
                kind_name = kind_map.get(kind, "unknown")
            else:
                kind_name = "unknown"

            return SymbolInfo(
                name=name or "",
                kind=kind_name,
                line=line,
                column=column,
                description=item.get("detail"),
            )

        for item in result:
            symbol = _parse_symbol_item(item)
            if symbol:
                symbols.append(symbol)

            # 递归处理子符号
            children = item.get("children") if isinstance(item, dict) else None
            if isinstance(children, list):
                for child in children:
                    child_symbol = _parse_symbol_item(child)
                    if child_symbol:
                        symbols.append(child_symbol)

        return symbols

    async def __aenter__(self) -> "LSPClient":
        """异步上下文管理器入口"""
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: Any,
        exc_val: Any,
        exc_tb: Any,
    ) -> None:
        """异步上下文管理器出口"""
        await self.shutdown()
