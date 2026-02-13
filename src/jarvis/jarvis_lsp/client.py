"""LSP 客户端模块

该模块提供 LSP 客户端核心功能，包括与 LSP 服务器的
异步通信、初始化、符号查询等。
"""

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Dict

from jarvis.jarvis_lsp.protocol import (
    CodeActionInfo,
    DiagnosticInfo,
    FoldingRangeInfo,
    HoverInfo,
    LSPMessageCodec,
    LSPNotification,
    LSPRequest,
    LSPResponse,
)


@dataclass
class LocationInfo:
    """位置信息数据类（LLM 友好格式）

    这个数据类提供对 LLM/Agent 更友好的位置信息，
    不仅仅是行列号，还包括代码内容和上下文。

    Attributes:
        file_path: 文件路径（绝对路径）
        line: 行号（0-based）
        column: 列号（0-based）
        uri: 原始 LSP URI
        code_snippet: 目标位置的代码片段（几行上下文）
        symbol_name: 符号名称（函数名、类名等，如果可提取）
        context: 完整的上下文描述
    """

    file_path: str
    line: int
    column: int
    uri: str
    code_snippet: Optional[str] = None
    symbol_name: Optional[str] = None
    context: Optional[str] = None


@dataclass
class SymbolInfo:
    """符号信息数据类

    Attributes:
        name: 符号名称
        kind: 符号类型（function, class, variable 等）
        file_path: 符号所在文件路径
        line: 行号（1-based）
        column: 列号（1-based）
        description: 描述信息
    """

    name: str
    kind: str
    line: int
    column: int
    file_path: str = ""
    description: Optional[str] = None


class LSPClient:
    """LSP 客户端类

    负责与 LSP 服务器通信，提供初始化、文档打开、符号查询等功能。

    支持两种模式：
    - short（短连接）：每次启动新进程，使用后关闭
    - persistent（持久化）：复用已有进程，不关闭
    """

    def __init__(self, command: str, args: List[str], mode: str = "short") -> None:
        """初始化 LSP 客户端

        Args:
            command: LSP 服务器可执行文件命令
            args: 启动参数列表
            mode: 客户端模式，"short"（短连接）或 "persistent"（持久化）
        """
        if mode not in ("short", "persistent"):
            raise ValueError(f"Invalid mode: {mode}, must be 'short' or 'persistent'")

        self.command = command
        self.args = args
        self.mode = mode
        self.process: Optional[asyncio.subprocess.Process] = None
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.request_id: int = 0
        self.root_uri: Optional[str] = None
        self._initialized: bool = False

    async def initialize(self) -> None:
        """初始化 LSP 服务器

        启动 LSP 服务器进程并发送 initialize 请求。

        在持久化模式下，如果进程已存在，则直接复用。

        Raises:
            RuntimeError: 服务器启动失败或初始化失败
        """
        # 在持久化模式下，如果进程已存在，直接复用
        if self.mode == "persistent" and self.process is not None:
            if not self.process.stdout or not self.process.stdin:
                raise RuntimeError(
                    "Persistent mode: process exists but has no stdout/stdin"
                )
            self.reader = self.process.stdout
            self.writer = self.process.stdin
        else:
            # 启动 LSP 服务器进程（短连接模式或持久化模式首次启动）
            # 将 stderr 重定向到 PIPE 以捕获错误信息
            self.process = await asyncio.create_subprocess_exec(
                self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            if (
                not self.process
                or not self.process.stdout
                or not self.process.stdin
                or not self.process.stderr
            ):
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
                        "documentSymbol": {"hierarchicalDocumentSymbolSupport": True},
                        "definition": {
                            "dynamicRegistration": True,
                            "linkSupport": True,
                        },
                        "references": {"dynamicRegistration": True},
                        "implementation": {
                            "dynamicRegistration": True,
                            "linkSupport": True,
                        },
                        "typeDefinition": {
                            "dynamicRegistration": True,
                            "linkSupport": True,
                        },
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
            raise RuntimeError(f"LSP initialization failed: {response.error}")

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

        # 根据 file extension 检测 languageId
        ext = path.suffix.lower()
        language_map = {
            ".py": "python",
            ".pyi": "python",
            ".rs": "rust",
            ".go": "go",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".c": "c",
            ".cpp": "cpp",
            ".hpp": "cpp",
            ".h": "c",
            ".cc": "cpp",
            ".cxx": "cpp",
            ".lua": "lua",
            ".sh": "shell",
            ".bash": "shell",
            ".zsh": "shell",
            ".rb": "ruby",
            ".php": "php",
            ".html": "html",
            ".htm": "html",
            ".css": "css",
            ".scss": "css",
            ".less": "css",
        }
        language_id = language_map.get(ext, "plaintext")

        notification = LSPNotification(
            jsonrpc="2.0",
            method="textDocument/didOpen",
            params={
                "textDocument": {
                    "uri": uri,
                    "languageId": language_id,
                    "version": 1,
                    "text": content,
                }
            },
        )

        await self._send_notification(notification)

    async def folding_range(self, file_path: str) -> List[FoldingRangeInfo]:
        """获取代码折叠范围

        Args:
            file_path: 文件路径

        Returns:
            折叠范围信息列表

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

        # 发送 foldingRange 请求
        request = LSPRequest(
            jsonrpc="2.0",
            id=self._next_id(),
            method="textDocument/foldingRange",
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
            raise RuntimeError(f"Folding range request failed: {response.error}")

        # 解析折叠范围
        folding_ranges = self._parse_folding_ranges(response.result)
        return folding_ranges

    async def hover(
        self, file_path: str, line: int, character: int
    ) -> Optional[HoverInfo]:
        """获取符号悬停信息

        Args:
            file_path: 文件路径
            line: 行号（0-based）
            character: 列号（0-based）

        Returns:
            悬停信息，如果位置没有符号则返回 None

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

        # 发送 hover 请求
        request = LSPRequest(
            jsonrpc="2.0",
            id=self._next_id(),
            method="textDocument/hover",
            params={
                "textDocument": {
                    "uri": uri,
                },
                "position": {
                    "line": line,
                    "character": character,
                },
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
                f"LSP server '{' '.join([self.command] + self.args)}' crashed after sending hover request\n"
                f"Exit code: {self.process.returncode}\n"
                f"Error: {error_msg}"
            )

        try:
            response = await self._read_response(timeout=30.0)
        except asyncio.TimeoutError:
            raise RuntimeError(
                "LSP server hover request timed out after 30 seconds. "
                "The server may be unresponsive or slow to start."
            )

        if response.error:
            raise RuntimeError(f"Hover request failed: {response.error}")

        # 解析悬停信息
        hover_info = self._parse_hover(response.result, file_path, line, character)
        return hover_info

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
            raise RuntimeError(f"Document symbol request failed: {response.error}")

        # 解析符号
        symbols = self._parse_symbols(response.result)
        return symbols

    async def workspace_symbol(self, query: str) -> List[SymbolInfo]:
        """在工作区中搜索符号

        Args:
            query: 搜索查询字符串

        Returns:
            符号信息列表

        Raises:
            RuntimeError: 客户端未初始化或查询失败
        """
        if not self._initialized:
            raise RuntimeError("LSP client not initialized")

        # 类型断言：initialize 确保了 process 已初始化
        if self.process is None:
            raise RuntimeError("LSP server process is not initialized")

        # 发送 workspace/symbol 请求
        request = LSPRequest(
            jsonrpc="2.0",
            id=self._next_id(),
            method="workspace/symbol",
            params={
                "query": query,
            },
        )

        await self._send_request(request)

        try:
            response = await self._read_response(timeout=30.0)
        except asyncio.TimeoutError:
            raise RuntimeError(
                "LSP server workspace/symbol request timed out after 30 seconds. "
                "The server may be unresponsive or slow."
            )

        # 检查是否有错误
        if response.error:
            error = response.error
            error_msg = error.get("message", "Unknown error")
            error_code = error.get("code", "unknown")

            # 如果是 pylsp 不支持 workspace/symbol 的情况，提供友好的提示
            if "workspace/symbol" in error_msg and "Not Found" in error_msg:
                raise RuntimeError(
                    f"The configured LSP server does not support workspace/symbol. "
                    f"pylsp does not implement this method. "
                    f"Please use a different LSP server that supports workspace/symbol, "
                    f"such as pyright (python-lsp-server) or ruff-lsp. "
                    f"Error: {error_msg} (code: {error_code})"
                )

            raise RuntimeError(
                f"workspace/symbol request failed: {error_msg} (code: {error_code})"
            )

        # 解析符号列表
        return self._parse_symbols(response.result or [])

    async def definition(
        self, file_path: str, line: int, column: int
    ) -> List[LocationInfo]:
        """跳转到定义

        Args:
            file_path: 文件路径
            line: 行号（0-based）
            column: 列号（0-based）

        Returns:
            定义位置列表

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

        # 发送 textDocument/definition 请求
        request = LSPRequest(
            jsonrpc="2.0",
            id=self._next_id(),
            method="textDocument/definition",
            params={
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": column},
            },
        )

        await self._send_request(request)

        try:
            response = await self._read_response(timeout=30.0)
        except asyncio.TimeoutError:
            raise RuntimeError(
                "textDocument/definition request timed out after 30 seconds. "
                "The server may be unresponsive or slow."
            )

        # 检查是否有错误
        if response.error:
            error = response.error
            raise RuntimeError(
                f"definition request failed: "
                f"{error.get('message', 'Unknown error')} (code: {error.get('code', 'unknown')})"
            )

        print(f"[DEBUG] definition: response.result = {response.result}")
        return self._parse_locations(response.result or [])

    async def callers_in_range(
        self, file_path: str, start_line: int, end_line: int, language: str = "python"
    ) -> List[Dict[str, Any]]:
        """解析指定行号范围内的函数调用

        Args:
            file_path: 文件路径
            start_line: 起始行号（1-based）
            end_line: 结束行号（1-based）
            language: 语言（用于选择解析器，目前仅支持 python）

        Returns:
            函数调用列表，每个调用包含 name, line, column 信息
        """
        callers = []

        try:
            # 读取文件内容
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 使用 AST 解析函数体
            import ast

            tree = ast.parse(content)

            # 找到指定行号范围内的所有函数调用
            class CallVisitor(ast.NodeVisitor):
                def __init__(self, start_line, end_line):
                    self.start_line = start_line
                    self.end_line = end_line
                    self.calls = []

                def visit_Call(self, node):
                    # 检查调用是否在指定行号范围内
                    if self.start_line <= node.lineno <= self.end_line:
                        # 获取函数名
                        if isinstance(node.func, ast.Name):
                            func_name = node.func.id
                        elif isinstance(node.func, ast.Attribute):
                            func_name = node.func.attr
                        else:
                            func_name = "<unknown>"

                        self.calls.append(
                            {
                                "name": func_name,
                                "line": node.lineno,  # 1-based
                                "column": node.col_offset,  # 0-based
                            }
                        )

                    # 继续遍历子节点
                    self.generic_visit(node)

            visitor = CallVisitor(start_line, end_line)
            visitor.visit(tree)
            callers = visitor.calls

        except Exception as e:
            print(f"[ERROR] Failed to parse callers: {e}")

        return callers

    async def references(
        self, file_path: str, line: int, column: int
    ) -> List[LocationInfo]:
        """查找所有引用

        Args:
            file_path: 文件路径
            line: 行号（0-based）
            column: 列号（0-based）

        Returns:
            引用位置列表

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

        # 发送 textDocument/references 请求
        request = LSPRequest(
            jsonrpc="2.0",
            id=self._next_id(),
            method="textDocument/references",
            params={
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": column},
                "context": {"includeDeclaration": True},
            },
        )

        await self._send_request(request)

        try:
            response = await self._read_response(timeout=30.0)
        except asyncio.TimeoutError:
            raise RuntimeError(
                "textDocument/references request timed out after 30 seconds. "
                "The server may be unresponsive or slow."
            )

        # 检查是否有错误
        if response.error:
            error = response.error
            raise RuntimeError(
                f"references request failed: "
                f"{error.get('message', 'Unknown error')} (code: {error.get('code', 'unknown')})"
            )

        return self._parse_locations(response.result or [])

    async def implementation(
        self, file_path: str, line: int, column: int
    ) -> List[LocationInfo]:
        """查找实现

        Args:
            file_path: 文件路径
            line: 行号（0-based）
            column: 列号（0-based）

        Returns:
            实现位置列表

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

        # 发送 textDocument/implementation 请求
        request = LSPRequest(
            jsonrpc="2.0",
            id=self._next_id(),
            method="textDocument/implementation",
            params={
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": column},
            },
        )

        await self._send_request(request)

        try:
            response = await self._read_response(timeout=30.0)
        except asyncio.TimeoutError:
            raise RuntimeError(
                "textDocument/implementation request timed out after 30 seconds. "
                "The server may be unresponsive or slow."
            )

        # 检查是否有错误
        if response.error:
            error = response.error
            raise RuntimeError(
                f"implementation request failed: "
                f"{error.get('message', 'Unknown error')} (code: {error.get('code', 'unknown')})"
            )

        return self._parse_locations(response.result or [])

    async def type_definition(
        self, file_path: str, line: int, column: int
    ) -> List[LocationInfo]:
        """查找类型定义

        Args:
            file_path: 文件路径
            line: 行号（0-based）
            column: 列号（0-based）

        Returns:
            类型定义位置列表

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

        # 发送 textDocument/typeDefinition 请求
        request = LSPRequest(
            jsonrpc="2.0",
            id=self._next_id(),
            method="textDocument/typeDefinition",
            params={
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": column},
            },
        )

        await self._send_request(request)

        try:
            response = await self._read_response(timeout=30.0)
        except asyncio.TimeoutError:
            raise RuntimeError(
                "textDocument/typeDefinition request timed out after 30 seconds. "
                "The server may be unresponsive or slow."
            )

        # 检查是否有错误
        if response.error:
            error = response.error
            raise RuntimeError(
                f"typeDefinition request failed: "
                f"{error.get('message', 'Unknown error')} (code: {error.get('code', 'unknown')})"
            )

        return self._parse_locations(response.result or [])

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

        在持久化模式下，不关闭进程，只清理本地资源。
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
                    await asyncio.wait_for(self._read_response(), timeout=5.0)
                except (asyncio.TimeoutError, Exception):
                    # 忽略 shutdown 响应超时或错误，继续关闭
                    pass

                # 发送 exit 通知（仅在短连接模式下）
                if self.mode == "short":
                    notification = LSPNotification(
                        jsonrpc="2.0",
                        method="exit",
                        params={},
                    )
                    await self._send_notification(notification)
            except Exception:  # nosec: B110
                # 忽略关闭时的错误
                pass

        # 关闭进程（仅在短连接模式下）
        if self.mode == "short":
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

        # 清理读写器和状态（仅在短连接模式下）
        # 持久化模式下需要保持连接，不清理 writer 和 reader
        if self.mode == "short":
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
                self.reader.readline(), timeout=timeout
            )
            if not header_line:
                raise RuntimeError("Failed to read response header")

            content_length = int(header_line.decode("utf-8").split(":", 1)[1].strip())

            # 跳过所有剩余的头行，直到遇到空行（\r\n）
            while True:
                line = await asyncio.wait_for(self.reader.readline(), timeout=timeout)
                if line == b"\r\n":  # 空行表示头结束
                    break

            # 读取 JSON 内容
            content_bytes = await asyncio.wait_for(
                self.reader.readexactly(content_length), timeout=timeout
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
                    error=message_dict.get("error"),
                )
                return response

    def _uri_to_path(self, uri: str) -> str:
        """将 LSP URI 转换为文件路径

        Args:
            uri: LSP URI (如 file:///path/to/file)

        Returns:
            文件绝对路径
        """
        if uri.startswith("file://"):
            return uri[7:]  # 移除 file:// 前缀
        return uri

    def _parse_location(self, location: Any) -> LocationInfo:
        """解析 LSP Location 为 LLM 友好的 LocationInfo

        Args:
            location: LSP Location 对象

        Returns:
            LocationInfo 对象（包含代码片段和上下文）
        """
        # LSP Location 格式: {uri: str, range: {start: {line, character}, end: {line, character}}}
        print(f"[DEBUG] _parse_location: raw location = {location}")
        uri = location.get("uri", "")
        print(f"[DEBUG] _parse_location: uri = {uri}")
        range_info = location.get("range", {})
        start = range_info.get("start", {})

        file_path = self._uri_to_path(uri)
        print(f"[DEBUG] _parse_location: file_path = {file_path}")
        line = start.get("line", 0)
        column = start.get("character", 0)

        # 读取代码片段（包含前后几行上下文）
        code_snippet = self._extract_code_snippet(file_path, line)

        # 生成上下文描述（不尝试提取符号名，符合 LSP 原则）
        context = f"File: {file_path}, Line: {line + 1}, Column: {column}"
        symbol_name = None  # LSP 协议层不应该假设目标语言的语法结构

        return LocationInfo(
            file_path=file_path,
            line=line,
            column=column,
            uri=uri,
            code_snippet=code_snippet,
            symbol_name=symbol_name,
            context=context,
        )

    def _extract_code_snippet(self, file_path: str, target_line: int) -> Optional[str]:
        """提取目标行周围的代码片段

        Args:
            file_path: 文件路径
            target_line: 目标行号（0-based）

        Returns:
            代码片段字符串（包含前后几行）
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # 提取前后各 3 行（共 7 行）
            start_line = max(0, target_line - 3)
            end_line = min(len(lines), target_line + 4)

            snippet_lines = lines[start_line:end_line]

            # 添加行号
            snippet = ""
            for i, line_text in enumerate(snippet_lines, start=start_line):
                marker = " > " if i == target_line else "   "
                snippet += f"{marker}{i + 1:4d} | {line_text}"

            return snippet
        except Exception:
            return None

    def _parse_hover(
        self, result: Any, file_path: str, line: int, character: int
    ) -> Optional[HoverInfo]:
        """解析 LSP hover 响应

        Args:
            result: LSP 响应结果
            file_path: 文件路径
            line: 行号（0-based）
            character: 列号（0-based）

        Returns:
            HoverInfo 对象，如果结果为空则返回 None
        """
        if result is None:
            return None

        # 提取 contents
        contents = result.get("contents")
        if contents is None:
            return None

        # 处理不同格式的 contents
        # LSP 规范允许 contents 为以下格式之一：
        # 1. MarkedString: { language: str, value: str }
        # 2. MarkedString数组: [{ language: str, value: str }]
        # 3. MarkupContent: { kind: 'markdown'|'plaintext', value: str }
        # 4. string
        if isinstance(contents, str):
            contents_str = contents
        elif isinstance(contents, dict):
            # MarkupContent 或 MarkedString
            value = contents.get("value")
            if value is None:
                return None
            contents_str = value
        elif isinstance(contents, list):
            # MarkedString数组
            contents_list = []
            for item in contents:
                if isinstance(item, str):
                    contents_list.append(item)
                elif isinstance(item, dict):
                    value = item.get("value")
                    if value:
                        contents_list.append(value)
            if not contents_list:
                return None
            contents_str = "\n\n".join(contents_list)
        else:
            return None

        # 提取 range（可选）
        range_data = result.get("range")
        if range_data:
            start = range_data.get("start", {})
            end = range_data.get("end", {})
            range_info = (
                start.get("line", 0),
                start.get("character", 0),
                end.get("line", 0),
                end.get("character", 0),
            )
        else:
            range_info = None

        return HoverInfo(
            contents=contents_str,
            range=range_info,
            file_path=file_path,
            line=line,
            character=character,
        )

    def _find_symbol_in_line(
        self, file_path: str, line: int, symbol_name: str
    ) -> Optional[int]:
        """在指定行中查找符号名的位置（fallback 机制）

        注意：这是一个不完美的 fallback 机制，只做简单的字符串匹配。
        不假设任何语言的语法结构，因此可能不准确。
        正确的做法是依赖 LSP 服务器返回准确的 selectionRange。

        Args:
            file_path: 文件路径
            line: 行号（0-based）
            symbol_name: 符号名称

        Returns:
            符号名的列号（0-based），如果找不到返回 None
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            if line < 0 or line >= len(lines):
                return None

            line_text = lines[line]

            # 只做简单的字符串匹配，不假设任何语言的语法
            # 使用单词边界确保精确匹配
            import re

            match = re.search(rf"\b{re.escape(symbol_name)}\b", line_text)
            if match:
                return match.start()

            return None
        except Exception:
            return None

    def _parse_locations(self, result: Any) -> List[LocationInfo]:
        """解析 LSP Location 列表

        Args:
            result: LSP Location 列表或单个 Location

        Returns:
            LocationInfo 列表
        """
        locations: List[LocationInfo] = []

        if result is None:
            return locations

        # 如果是单个 Location，转换为列表
        if not isinstance(result, list):
            result = [result]

        for loc in result:
            if loc and isinstance(loc, dict):
                locations.append(self._parse_location(loc))

        return locations

    def _parse_folding_ranges(self, result: Any) -> List[FoldingRangeInfo]:
        """解析折叠范围

        Args:
            result: foldingRange 响应结果

        Returns:
            折叠范围信息列表
        """
        folding_ranges: List[FoldingRangeInfo] = []

        if not isinstance(result, list):
            return folding_ranges

        for item in result:
            if not isinstance(item, dict):
                continue

            # LSP FoldingRange 格式:
            # {
            #   "startLine": int,
            #   "startCharacter": int (可选),
            #   "endLine": int,
            #   "endCharacter": int (可选),
            #   "kind": string (可选),
            #   "collapsedText": string (可选)
            # }
            start_line = item.get("startLine", 0)
            start_character = item.get("startCharacter", 0)
            end_line_raw = item.get("endLine")
            end_line = end_line_raw if end_line_raw is not None else start_line
            end_character = item.get("endCharacter", 0)
            kind = item.get("kind")
            collapsed_text = item.get("collapsedText")

            folding_ranges.append(
                FoldingRangeInfo(
                    start_line=start_line,
                    start_character=start_character,
                    end_line=end_line,
                    end_character=end_character,
                    kind=kind,
                    collapsed_text=collapsed_text,
                )
            )

        return folding_ranges

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
            # 优先使用 selectionRange（符号名称的范围），如果不存在则使用 range
            location = item.get("location", {})
            if "range" in location:
                range_info = location["range"]
            else:
                range_info = item.get("range", {})

            # LSP DocumentSymbol 有 selectionRange 字段，表示符号名称的范围
            # 这比 range 更精确（range 可能包含整个定义，selectionRange 只是符号名）
            selection_range = item.get("selectionRange")
            if selection_range:
                # 使用 selectionRange 获取符号名称的精确位置
                start = selection_range.get("start", {})
            else:
                # 如果没有 selectionRange，尝试使用 range
                start = range_info.get("start", {})

            line = start.get("line", 0)
            column = start.get("character", 0)

            # 提取文件路径
            uri = location.get("uri", "")
            file_path = self._uri_to_path(uri) if uri else ""

            # 如果列号为 0，尝试在目标行中查找符号名
            # pylsp 可能不返回 selectionRange，导致列号总是 0
            if column == 0 and name:
                # 尝试从 range 中获取文件路径
                uri = location.get("uri", "")
                if uri:
                    file_path = self._uri_to_path(uri)
                    # 读取目标行内容，查找符号名
                    found_column = self._find_symbol_in_line(file_path, line, name)
                    if found_column is not None:
                        column = found_column

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
                file_path=file_path,
                line=line + 1,  # 转换为 1-based
                column=column + 1,  # 转换为 1-based
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

    async def diagnostic(
        self, file_path: str, severity_filter: Optional[int] = None
    ) -> List[DiagnosticInfo]:
        """获取代码诊断信息

        Args:
            file_path: 文件路径
            severity_filter: 严重级别过滤（1=Error, 2=Warning, 3=Info, 4=Hint），
                          None 表示不过滤，返回所有诊断

        Returns:
            诊断信息列表

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

        # 发送 diagnostic 请求
        request = LSPRequest(
            jsonrpc="2.0",
            id=self._next_id(),
            method="textDocument/diagnostic",
            params={
                "textDocument": {
                    "uri": uri,
                },
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
                f"LSP server '{' '.join([self.command] + self.args)}' crashed after sending diagnostic request\n"
                f"Exit code: {self.process.returncode}\n"
                f"Error: {error_msg}"
            )

        try:
            response = await self._read_response(timeout=30.0)
        except asyncio.TimeoutError:
            raise RuntimeError(
                "LSP server diagnostic request timed out after 30 seconds. "
                "The server may be unresponsive or slow to start."
            )

        if response.error:
            raise RuntimeError(f"Diagnostic request failed: {response.error}")

        # 解析诊断信息
        diagnostics = self._parse_diagnostic(response.result, severity_filter)
        return diagnostics

    async def code_action(
        self, file_path: str, line: int, character: int
    ) -> List[CodeActionInfo]:
        """获取代码动作信息

        Args:
            file_path: 文件路径
            line: 行号（0-based）
            character: 列号（0-based）

        Returns:
            代码动作列表

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

        # 发送 codeAction 请求
        request = LSPRequest(
            jsonrpc="2.0",
            id=self._next_id(),
            method="textDocument/codeAction",
            params={
                "textDocument": {
                    "uri": uri,
                },
                "range": {
                    "start": {
                        "line": line,
                        "character": character,
                    },
                    "end": {
                        "line": line,
                        "character": character,
                    },
                },
                "context": {
                    "diagnostics": [],
                },
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
                f"LSP server '{' '.join([self.command] + self.args)}' crashed after sending codeAction request\n"
                f"Exit code: {self.process.returncode}\n"
                f"Error: {error_msg}"
            )

        try:
            response = await self._read_response(timeout=30.0)
        except asyncio.TimeoutError:
            raise RuntimeError(
                "LSP server codeAction request timed out after 30 seconds. "
                "The server may be unresponsive or slow to start."
            )

        if response.error:
            raise RuntimeError(f"CodeAction request failed: {response.error}")

        # 解析代码动作信息
        code_actions = self._parse_code_action(response.result)
        return code_actions

    async def code_action_by_name(
        self, file_path: str, symbol_name: str
    ) -> List[CodeActionInfo]:
        """通过符号名获取代码动作信息

        Args:
            file_path: 文件路径
            symbol_name: 符号名称（函数名、类名等）

        Returns:
            代码动作列表

        Raises:
            RuntimeError: 客户端未初始化或查询失败
        """
        if not self._initialized:
            raise RuntimeError("LSP client not initialized")

        # 先打开文档
        await self.open_document(file_path)

        # 获取文档符号
        symbols = await self.document_symbol(file_path)

        # 查找匹配的符号
        for symbol in symbols:
            if symbol.name == symbol_name:
                # 找到符号，获取其位置的代码动作
                return await self.code_action(file_path, symbol.line, 0)

        # 未找到符号，返回空列表
        return []

    def _parse_diagnostic(
        self, result: Any, severity_filter: Optional[int] = None
    ) -> List[DiagnosticInfo]:
        """解析诊断信息

        Args:
            result: LSP 响应结果
            severity_filter: 严重级别过滤

        Returns:
            诊断信息列表
        """
        diagnostics: List[DiagnosticInfo] = []

        # 处理 pylsp 的响应格式
        # pylsp 可能返回一个包含 diagnostics 列表的字典
        if isinstance(result, dict):
            diagnostics_list = result.get("diagnostics", [])
        elif isinstance(result, list):
            diagnostics_list = result
        else:
            return diagnostics

        for item in diagnostics_list:
            if not isinstance(item, dict):
                continue

            # 解析 range
            range_info = item.get("range", {})
            start = range_info.get("start", {})
            end = range_info.get("end", {})
            start_line = start.get("line", 0)
            start_char = start.get("character", 0)
            end_line = end.get("line", 0)
            end_char = end.get("character", 0)

            # 解析严重级别
            severity = item.get("severity", 1)  # 默认为 Error

            # 应用严重级别过滤
            if severity_filter is not None and severity != severity_filter:
                continue

            diagnostic = DiagnosticInfo(
                range=(start_line, start_char, end_line, end_char),
                severity=severity,
                code=item.get("code"),
                source=item.get("source", "unknown"),
                message=item.get("message", ""),
            )
            diagnostics.append(diagnostic)

        return diagnostics

    def _parse_code_action(self, result: Any) -> List[CodeActionInfo]:
        """解析代码动作信息

        Args:
            result: LSP 响应结果

        Returns:
            代码动作列表
        """
        code_actions: List[CodeActionInfo] = []

        # 处理 pylsp 的响应格式
        if isinstance(result, list):
            code_actions_list = result
        elif isinstance(result, dict):
            code_actions_list = result.get("result", [])
        else:
            return code_actions

        for item in code_actions_list:
            if not isinstance(item, dict):
                continue

            code_action = CodeActionInfo(
                title=item.get("title", ""),
                kind=item.get("kind", ""),
                is_preferred=item.get("isPreferred", False),
            )
            code_actions.append(code_action)

        return code_actions

    # ==================== Call Hierarchy API ====================

    async def prepare_call_hierarchy(
        self, file_path: str, line: int, column: int
    ) -> List[dict]:
        """准备调用层次结构

        Args:
            file_path: 文件路径
            line: 行号（0-based）
            column: 列号（0-based）

        Returns:
            CallHierarchyItem 列表，每个包含:
            - uri: 文件 URI
            - range: 符号范围
            - selectionRange: 符号名称范围
            - name: 符号名称
            - kind: 符号类型
            - detail: 详细信息

        Raises:
            RuntimeError: 客户端未初始化或查询失败
        """
        if not self._initialized:
            raise RuntimeError("LSP client not initialized")

        await self.open_document(file_path)

        if self.process is None:
            raise RuntimeError("LSP server process is not initialized")

        path = Path(file_path).resolve()
        uri = f"file://{path}"

        request = LSPRequest(
            jsonrpc="2.0",
            id=self._next_id(),
            method="textDocument/prepareCallHierarchy",
            params={
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": column},
            },
        )

        await self._send_request(request)

        try:
            response = await self._read_response(timeout=30.0)
        except asyncio.TimeoutError:
            raise RuntimeError(
                "textDocument/prepareCallHierarchy request timed out after 30 seconds."
            )

        if response.error:
            raise RuntimeError(f"prepareCallHierarchy request failed: {response.error}")

        result = response.result
        if not result:
            return []

        return result if isinstance(result, list) else [result]

    async def call_hierarchy_incoming_calls(self, item: dict) -> List[dict]:
        """查询调用层次 - 谁调用了这个符号（incoming calls / callers）

        Args:
            item: CallHierarchyItem，从 prepare_call_hierarchy 获取

        Returns:
            CallHierarchyIncomingCall 列表，每个包含:
            - from: 调用者的 CallHierarchyItem
            - fromRanges: 调用位置范围列表

        Raises:
            RuntimeError: 客户端未初始化或查询失败
        """
        if not self._initialized:
            raise RuntimeError("LSP client not initialized")

        request = LSPRequest(
            jsonrpc="2.0",
            id=self._next_id(),
            method="callHierarchy/incomingCalls",
            params={"item": item},
        )

        await self._send_request(request)

        try:
            response = await self._read_response(timeout=30.0)
        except asyncio.TimeoutError:
            raise RuntimeError(
                "callHierarchy/incomingCalls request timed out after 30 seconds."
            )

        if response.error:
            raise RuntimeError(
                f"callHierarchy/incomingCalls request failed: {response.error}"
            )

        return response.result or []

    async def call_hierarchy_outgoing_calls(self, item: dict) -> List[dict]:
        """查询调用层次 - 这个符号调用了哪些符号（outgoing calls / callees）

        Args:
            item: CallHierarchyItem，从 prepare_call_hierarchy 获取

        Returns:
            CallHierarchyOutgoingCall 列表，每个包含:
            - to: 被调用者的 CallHierarchyItem
            - fromRanges: 调用位置范围列表

        Raises:
            RuntimeError: 客户端未初始化或查询失败
        """
        if not self._initialized:
            raise RuntimeError("LSP client not initialized")

        request = LSPRequest(
            jsonrpc="2.0",
            id=self._next_id(),
            method="callHierarchy/outgoingCalls",
            params={"item": item},
        )

        await self._send_request(request)

        try:
            response = await self._read_response(timeout=30.0)
        except asyncio.TimeoutError:
            raise RuntimeError(
                "callHierarchy/outgoingCalls request timed out after 30 seconds."
            )

        if response.error:
            raise RuntimeError(
                f"callHierarchy/outgoingCalls request failed: {response.error}"
            )

        return response.result or []

    # ==================== 符号名便捷方法 ====================

    async def _find_symbol_position(
        self, file_path: str, symbol_name: str
    ) -> Optional[tuple]:
        """查找符号在文件中的位置

        Args:
            file_path: 文件路径
            symbol_name: 符号名称

        Returns:
            (line, column) 元组，如果未找到则返回 None
        """
        symbols = await self.document_symbol(file_path)
        for sym in symbols:
            if sym.name == symbol_name:
                return (sym.line, sym.column)
        return None

    async def incoming_calls_by_name(
        self, file_path: str, symbol_name: str
    ) -> List[LocationInfo]:
        """通过符号名查询谁调用了这个符号（incoming calls / callers）

        Args:
            file_path: 文件路径
            symbol_name: 符号名称

        Returns:
            调用者位置列表

        Raises:
            RuntimeError: 客户端未初始化或查询失败
        """
        position = await self._find_symbol_position(file_path, symbol_name)
        if position is None:
            return []

        line, column = position
        items = await self.prepare_call_hierarchy(file_path, line, column)
        if not items:
            return []

        locations: List[LocationInfo] = []
        for item in items:
            calls = await self.call_hierarchy_incoming_calls(item)
            for call in calls:
                from_item = call.get("from", {})
                uri = from_item.get("uri", "")
                if uri.startswith("file://"):
                    caller_path = uri[7:]
                else:
                    caller_path = uri

                range_info = from_item.get("range", {})
                start = range_info.get("start", {})
                caller_line = start.get("line", 0)
                caller_col = start.get("character", 0)

                # 获取代码片段
                snippet = await self._get_code_snippet(caller_path, caller_line)

                locations.append(
                    LocationInfo(
                        file_path=caller_path,
                        line=caller_line,
                        column=caller_col,
                        uri=uri,
                        code_snippet=snippet,
                        symbol_name=from_item.get("name"),
                    )
                )

        return locations

    async def outgoing_calls_by_name(
        self, file_path: str, symbol_name: str
    ) -> List[LocationInfo]:
        """通过符号名查询这个符号调用了哪些符号（outgoing calls / callees）

        Args:
            file_path: 文件路径
            symbol_name: 符号名称

        Returns:
            被调用者位置列表

        Raises:
            RuntimeError: 客户端未初始化或查询失败
        """
        position = await self._find_symbol_position(file_path, symbol_name)
        if position is None:
            return []

        line, column = position
        items = await self.prepare_call_hierarchy(file_path, line, column)
        if not items:
            return []

        locations: List[LocationInfo] = []
        for item in items:
            calls = await self.call_hierarchy_outgoing_calls(item)
            for call in calls:
                to_item = call.get("to", {})
                uri = to_item.get("uri", "")
                if uri.startswith("file://"):
                    callee_path = uri[7:]
                else:
                    callee_path = uri

                range_info = to_item.get("range", {})
                start = range_info.get("start", {})
                callee_line = start.get("line", 0)
                callee_col = start.get("character", 0)

                # 获取代码片段
                snippet = await self._get_code_snippet(callee_path, callee_line)

                locations.append(
                    LocationInfo(
                        file_path=callee_path,
                        line=callee_line,
                        column=callee_col,
                        uri=uri,
                        code_snippet=snippet,
                        symbol_name=to_item.get("name"),
                    )
                )

        return locations

    async def _get_code_snippet(
        self, file_path: str, line: int, context_lines: int = 3
    ) -> Optional[str]:
        """获取指定位置周围的代码片段

        Args:
            file_path: 文件路径
            line: 行号（0-based）
            context_lines: 上下文行数

        Returns:
            代码片段字符串
        """
        try:
            content = await asyncio.to_thread(Path(file_path).read_text)
            lines = content.splitlines()
            start = max(0, line - context_lines)
            end = min(len(lines), line + context_lines + 1)
            return "\n".join(lines[start:end])
        except Exception:
            return None

    # 兼容旧接口名称
    async def callers_by_name(
        self, file_path: str, symbol_name: str
    ) -> List[LocationInfo]:
        """通过符号名查询这个符号调用了哪些符号（outgoing calls 的别名）

        这是 outgoing_calls_by_name 的别名，保持向后兼容。

        Args:
            file_path: 文件路径
            symbol_name: 符号名称

        Returns:
            被调用者位置列表
        """
        return await self.outgoing_calls_by_name(file_path, symbol_name)

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
