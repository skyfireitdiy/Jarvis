"""LSP 守护进程客户端模块

该模块提供与 LSP 守护进程通信的客户端接口。
Unix: Unix domain socket；Windows: TCP 127.0.0.1。
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from jarvis.jarvis_lsp.client import LocationInfo, SymbolInfo
from jarvis.jarvis_lsp.daemon import (
    _get_lsp_daemon_addr,
)
from jarvis.jarvis_lsp.protocol import (
    CodeActionInfo,
    DiagnosticInfo,
    FoldingRangeInfo,
    HoverInfo,
)

_IS_WINDOWS = sys.platform == "win32"


class LSPDaemonClient:
    """LSP 守护进程客户端

    Unix: Unix domain socket；Windows: TCP 127.0.0.1。
    """

    def __init__(self, addr: Union[str, tuple, None] = None):
        if addr is None:
            addr = _get_lsp_daemon_addr()
        self.addr = addr
        self._is_unix = isinstance(addr, str)
        # 兼容旧代码中 client.socket_path 的引用（如 daemon_stop）
        self.socket_path = addr if self._is_unix else f"{addr[0]}:{addr[1]}"
        # 守护进程就绪标志：仅在首次请求时探测/启动，避免每次请求都额外
        # 建立一条探测连接（探测连接被立即关闭会让服务端读到 RST，干扰正常请求）
        self._daemon_ready = False

    async def _ensure_daemon_running(self) -> None:
        """确保守护进程正在运行（仅在未确认就绪时探测/启动）"""
        if self._daemon_ready:
            return

        async def _try_connect() -> bool:
            try:
                if self._is_unix:
                    # 在Unix情况下，self.addr是字符串
                    assert isinstance(self.addr, str), "Unix socket地址必须是字符串"
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_unix_connection(self.addr), timeout=2.0
                    )
                else:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(self.addr[0], self.addr[1]),
                        timeout=2.0,
                    )
                writer.close()
                await writer.wait_closed()
                return True
            except (
                ConnectionRefusedError,
                FileNotFoundError,
                asyncio.TimeoutError,
                OSError,
            ):
                return False

        if await _try_connect():
            self._daemon_ready = True
            return

        # 启动守护进程
        daemon_script = str(Path(__file__).resolve().parent / "daemon.py")
        if not os.path.exists(daemon_script):
            raise FileNotFoundError(f"守护进程脚本不存在: {daemon_script}")

        if _IS_WINDOWS:
            flags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            if hasattr(subprocess, "DETACHED_PROCESS"):
                flags |= subprocess.DETACHED_PROCESS
            subprocess.Popen(
                [sys.executable, daemon_script],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
                cwd=os.path.expanduser("~"),
            )
        else:
            # 必须用 subprocess.Popen 而非 asyncio.create_subprocess_exec：
            # 后者创建的子进程由当前事件循环托管，asyncio.run 结束/进程退出时
            # 会被一并终止，导致守护进程随客户端进程消亡（下次调用需重启，
            # 且重启窗口内容易出现 Connection reset by peer）。
            subprocess.Popen(
                [sys.executable, daemon_script],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                cwd=os.path.expanduser("~"),
            )

        # 等待守护进程就绪（最多 5 秒）
        for i in range(50):
            await asyncio.sleep(0.1)
            if await _try_connect():
                await asyncio.sleep(0.5)
                self._daemon_ready = True
                return

        raise RuntimeError(
            "守护进程启动失败。"
            + (
                f"socket 未创建: {self.addr}"
                if self._is_unix
                else f"TCP 无法连接: {self.addr[0]}:{self.addr[1]}"
            )
        )

    async def _send_request(
        self, method: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """发送请求到守护进程"""

        # 自动启动守护进程（如果未运行）
        await self._ensure_daemon_running()

        if self._is_unix:
            assert isinstance(self.addr, str), "Unix socket地址必须是字符串"
            if not os.path.exists(self.addr):
                raise RuntimeError(f"守护进程启动失败。socket 文件不存在: {self.addr}")

        request = {"method": method, "params": params}
        request_json = json.dumps(request, ensure_ascii=False)
        request_bytes = request_json.encode()
        # Content-Length 必须是 UTF-8 字节数（非字符数），否则含中文时请求被截断
        request_data = (
            f"Content-Length: {len(request_bytes)}\r\n\r\n".encode() + request_bytes
        )

        try:
            if self._is_unix:
                # 在Unix情况下，self.addr是字符串
                assert isinstance(self.addr, str), "Unix socket地址必须是字符串"
                reader, writer = await asyncio.open_unix_connection(self.addr)
            else:
                reader, writer = await asyncio.open_connection(
                    self.addr[0], self.addr[1]
                )

            # 发送请求
            writer.write(request_data)
            await writer.drain()

            # 读取响应
            line = await reader.readline()
            if not line:
                raise RuntimeError("守护进程断开连接")

            # 解析 Content-Length 头
            header = line.decode().strip()
            if header.startswith("Content-Length:"):
                content_length = int(header.split(":")[1].strip())
            else:
                content_length = int(header)

            # 读取空行
            await reader.readline()

            # 读取内容
            content = await reader.readexactly(content_length)
            response = json.loads(content.decode())

            assert isinstance(response, dict)

            writer.close()
            await writer.wait_closed()

            return response

        except ConnectionRefusedError:
            self._daemon_ready = False
            raise RuntimeError("无法连接到守护进程。请先运行: jlsp daemon start")
        except Exception as e:
            # 通信失败可能因守护进程已退出，重置标志以便下次请求重新探测/启动
            self._daemon_ready = False
            raise RuntimeError(f"守护进程通信失败: {e}")

    async def start_server(self, language: str, project_path: str) -> int:
        """启动 LSP server"""
        response = await self._send_request(
            "start_server",
            {"language": language, "project_path": project_path},
        )

        if not response.get("success"):
            raise RuntimeError(response.get("error", "未知错误"))

        pid = response.get("pid")
        if pid is None:
            raise RuntimeError("守护进程未返回 PID")

        assert isinstance(pid, int)
        return pid

    async def stop_server(self, language: str, project_path: str) -> None:
        """停止 LSP server"""
        response = await self._send_request(
            "stop_server",
            {"language": language, "project_path": project_path},
        )

        if not response.get("success"):
            raise RuntimeError(response.get("error", "未知错误"))

    async def workspace_symbol(
        self, language: str, project_path: str, query: str
    ) -> List[SymbolInfo]:
        """在工作区中搜索符号"""
        response = await self._send_request(
            "workspace_symbol",
            {"language": language, "project_path": project_path, "query": query},
        )

        if not response.get("success"):
            raise RuntimeError(response.get("error", "未知错误"))

        symbols_data = response.get("symbols", [])
        return [
            SymbolInfo(
                name=s["name"],
                kind=s["kind"],
                file_path=s.get("file_path", ""),
                line=s["line"],
                column=s["column"],
                description=s["description"],
            )
            for s in symbols_data
        ]

    async def document_symbol(
        self, language: str, project_path: str, file_path: str
    ) -> List[SymbolInfo]:
        """列出文件中的文档符号"""
        response = await self._send_request(
            "document_symbol",
            {
                "language": language,
                "project_path": project_path,
                "file_path": file_path,
            },
        )

        if not response.get("success"):
            raise RuntimeError(response.get("error", "未知错误"))

        symbols_data = response.get("symbols", [])
        return [
            SymbolInfo(
                name=s["name"],
                kind=s["kind"],
                file_path=s.get("file_path", ""),
                line=s["line"],
                column=s["column"],
                description=s["description"],
            )
            for s in symbols_data
        ]

    async def folding_range(
        self, language: str, project_path: str, file_path: str
    ) -> List[FoldingRangeInfo]:
        """获取代码折叠范围"""
        response = await self._send_request(
            "folding_range",
            {
                "language": language,
                "project_path": project_path,
                "file_path": file_path,
            },
        )

        if not response.get("success"):
            raise RuntimeError(response.get("error", "未知错误"))

        folding_ranges_data = response.get("folding_ranges", [])
        return [
            FoldingRangeInfo(
                start_line=fr["start_line"],
                start_character=fr["start_character"],
                end_line=fr["end_line"],
                end_character=fr["end_character"],
                kind=fr.get("kind"),
                collapsed_text=fr.get("collapsed_text"),
            )
            for fr in folding_ranges_data
        ]

    async def hover(
        self,
        language: str,
        project_path: str,
        file_path: str,
        line: int,
        character: int,
    ) -> Optional[HoverInfo]:
        """获取符号悬停信息"""
        response = await self._send_request(
            "hover",
            {
                "language": language,
                "project_path": project_path,
                "file_path": file_path,
                "line": line,
                "character": character,
            },
        )

        if not response.get("success"):
            raise RuntimeError(response.get("error", "未知错误"))

        hover_data = response.get("hover_info")
        if hover_data is None:
            return None

        return HoverInfo(
            contents=hover_data["contents"],
            range=hover_data["range"],
            file_path=hover_data["file_path"],
            line=hover_data["line"],
            character=hover_data["character"],
        )

    async def diagnostic(
        self,
        language: str,
        project_path: str,
        file_path: str,
        severity_filter: Optional[int] = None,
    ) -> List[DiagnosticInfo]:
        """获取代码诊断信息"""
        response = await self._send_request(
            "diagnostic",
            {
                "language": language,
                "project_path": project_path,
                "file_path": file_path,
                "severity_filter": severity_filter,
            },
        )

        if not response.get("success"):
            raise RuntimeError(response.get("error", "未知错误"))

        diagnostics_data = response.get("diagnostics", [])
        return [
            DiagnosticInfo(
                range=diag["range"],
                severity=diag["severity"],
                code=diag["code"],
                source=diag["source"],
                message=diag["message"],
            )
            for diag in diagnostics_data
        ]

    async def code_action(
        self,
        language: str,
        project_path: str,
        file_path: str,
        line: int,
        character: int,
    ) -> List[CodeActionInfo]:
        """获取代码动作信息"""
        response = await self._send_request(
            "code_action",
            {
                "language": language,
                "project_path": project_path,
                "file_path": file_path,
                "line": line,
                "character": character,
            },
        )

        if not response.get("success"):
            raise RuntimeError(response.get("error", "未知错误"))

        code_actions_data = response.get("code_actions", [])
        return [
            CodeActionInfo(
                title=action["title"],
                kind=action["kind"],
                is_preferred=action["is_preferred"],
            )
            for action in code_actions_data
        ]

    async def code_action_by_name(
        self,
        language: str,
        project_path: str,
        file_path: str,
        symbol_name: str,
    ) -> List[CodeActionInfo]:
        """通过符号名获取代码动作信息"""
        response = await self._send_request(
            "code_action_by_name",
            {
                "language": language,
                "project_path": project_path,
                "file_path": file_path,
                "symbol_name": symbol_name,
            },
        )

        if not response.get("success"):
            raise RuntimeError(response.get("error", "未知错误"))

        code_actions_data = response.get("code_actions", [])
        return [
            CodeActionInfo(
                title=action["title"],
                kind=action["kind"],
                is_preferred=action["is_preferred"],
            )
            for action in code_actions_data
        ]

    async def status(self) -> Dict[str, Any]:
        """获取守护进程状态"""
        response = await self._send_request("status", {})

        if not response.get("success"):
            raise RuntimeError(response.get("error", "未知错误"))

        return response

    async def definition(
        self,
        language: str,
        project_path: str,
        file_path: str,
        line: int,
        column: int = 0,
    ) -> LocationInfo | None:
        """跳转到定义"""
        response = await self._send_request(
            "definition",
            {
                "language": language,
                "project_path": project_path,
                "file_path": file_path,
                "line": line,
                "column": column,
            },
        )

        if not response.get("success"):
            raise RuntimeError(response.get("error", "未知错误"))

        location_data = response.get("location")
        if location_data is None:
            return None

        return LocationInfo(
            file_path=location_data["file_path"],
            line=location_data["line"],
            column=location_data["column"],
            uri=location_data.get("uri", f"file://{location_data['file_path']}"),
            code_snippet=location_data.get("code_snippet"),
            symbol_name=location_data.get("symbol_name"),
            context=location_data.get("context"),
        )

    async def references(
        self,
        language: str,
        project_path: str,
        file_path: str,
        line: int,
        column: int = 0,
    ) -> list[LocationInfo]:
        """查找所有引用"""
        response = await self._send_request(
            "references",
            {
                "language": language,
                "project_path": project_path,
                "file_path": file_path,
                "line": line,
                "column": column,
            },
        )

        if not response.get("success"):
            raise RuntimeError(response.get("error", "未知错误"))

        locations_data = response.get("locations", [])
        return [
            LocationInfo(
                file_path=loc["file_path"],
                line=loc["line"],
                column=loc["column"],
                uri=loc.get("uri", f"file://{loc['file_path']}"),
                code_snippet=loc.get("code_snippet"),
                symbol_name=loc.get("symbol_name"),
                context=loc.get("context"),
            )
            for loc in locations_data
        ]

    async def implementation(
        self,
        language: str,
        project_path: str,
        file_path: str,
        line: int,
        column: int = 0,
    ) -> list[LocationInfo]:
        """查找实现"""
        response = await self._send_request(
            "implementation",
            {
                "language": language,
                "project_path": project_path,
                "file_path": file_path,
                "line": line,
                "column": column,
            },
        )

        if not response.get("success"):
            raise RuntimeError(response.get("error", "未知错误"))

        locations_data = response.get("locations", [])
        return [
            LocationInfo(
                file_path=loc["file_path"],
                line=loc["line"],
                column=loc["column"],
                uri=loc.get("uri", f"file://{loc['file_path']}"),
                code_snippet=loc.get("code_snippet"),
                symbol_name=loc.get("symbol_name"),
                context=loc.get("context"),
            )
            for loc in locations_data
        ]

    async def type_definition(
        self,
        language: str,
        project_path: str,
        file_path: str,
        line: int,
        column: int = 0,
    ) -> LocationInfo | None:
        """查找类型定义"""
        response = await self._send_request(
            "type_definition",
            {
                "language": language,
                "project_path": project_path,
                "file_path": file_path,
                "line": line,
                "column": column,
            },
        )

        if not response.get("success"):
            raise RuntimeError(response.get("error", "未知错误"))

        location_data = response.get("location")
        if location_data is None:
            return None

        return LocationInfo(
            file_path=location_data["file_path"],
            line=location_data["line"],
            column=location_data["column"],
            uri=f"file://{location_data['file_path']}",
            symbol_name=location_data.get("symbol_name"),
        )

    async def definition_at_line(
        self,
        language: str,
        project_path: str,
        file_path: str,
        line: int,
        symbol_name: str,
    ) -> LocationInfo | None:
        """通过行号查找定义（自动查找该行的符号列号）

        Args:
            language: 语言
            project_path: 项目路径
            file_path: 文件路径
            line: 行号（从 0 开始）
            symbol_name: 符号名称（必填，用于精确匹配）

        Returns:
            定义位置信息，如果找不到返回 None
        """
        response = await self._send_request(
            "definition_at_line",
            {
                "language": language,
                "project_path": project_path,
                "file_path": file_path,
                "line": line,
                "symbol_name": symbol_name,
            },
        )

        if not response.get("success"):
            raise RuntimeError(response.get("error", "未知错误"))

        location_data = response.get("location")
        if location_data is None:
            return None

        return LocationInfo(
            file_path=location_data["file_path"],
            line=location_data["line"],
            column=location_data["column"],
            uri=f"file://{location_data['file_path']}",
            symbol_name=location_data.get("symbol_name"),
        )

    async def definition_by_name(
        self, language: str, project_path: str, file_path: str, symbol_name: str
    ) -> LocationInfo | None:
        """通过符号名查找定义"""
        response = await self._send_request(
            "definition_by_name",
            {
                "language": language,
                "project_path": project_path,
                "file_path": file_path,
                "symbol_name": symbol_name,
            },
        )

        if not response.get("success"):
            raise RuntimeError(response.get("error", "未知错误"))

        location_data = response.get("location")
        if location_data is None:
            return None

        return LocationInfo(
            file_path=location_data["file_path"],
            line=location_data["line"],
            column=location_data["column"],
            uri=f"file://{location_data['file_path']}",
            symbol_name=location_data.get("symbol_name"),
        )

    async def references_by_name(
        self, language: str, project_path: str, file_path: str, symbol_name: str
    ) -> list[LocationInfo]:
        """通过符号名查找引用"""
        response = await self._send_request(
            "references_by_name",
            {
                "language": language,
                "project_path": project_path,
                "file_path": file_path,
                "symbol_name": symbol_name,
            },
        )

        if not response.get("success"):
            raise RuntimeError(response.get("error", "未知错误"))

        locations_data = response.get("locations", [])
        return [
            LocationInfo(
                file_path=loc["file_path"],
                line=loc["line"],
                column=loc["column"],
                uri=loc.get("uri", f"file://{loc['file_path']}"),
                code_snippet=loc.get("code_snippet"),
                symbol_name=loc.get("symbol_name"),
                context=loc.get("context"),
            )
            for loc in locations_data
        ]

    async def callees_by_name(
        self, language: str, project_path: str, file_path: str, symbol_name: str
    ) -> list[Dict[str, Any]]:
        """查询指定函数内部调用了哪些其他函数（outgoing calls）"""
        response = await self._send_request(
            "callers_by_name",
            {
                "language": language,
                "project_path": project_path,
                "file_path": file_path,
                "symbol_name": symbol_name,
            },
        )

        if not response.get("success"):
            raise RuntimeError(response.get("error", "未知错误"))

        return response.get("callers", [])  # type: ignore[no-any-return]

    async def implementation_by_name(
        self, language: str, project_path: str, file_path: str, symbol_name: str
    ) -> list[LocationInfo]:
        """通过符号名查找实现"""
        response = await self._send_request(
            "implementation_by_name",
            {
                "language": language,
                "project_path": project_path,
                "file_path": file_path,
                "symbol_name": symbol_name,
            },
        )

        if not response.get("success"):
            raise RuntimeError(response.get("error", "未知错误"))

        locations_data = response.get("locations", [])
        return [
            LocationInfo(
                file_path=loc["file_path"],
                line=loc["line"],
                column=loc["column"],
                uri=loc.get("uri", f"file://{loc['file_path']}"),
                code_snippet=loc.get("code_snippet"),
                symbol_name=loc.get("symbol_name"),
                context=loc.get("context"),
            )
            for loc in locations_data
        ]

    async def type_definition_by_name(
        self, language: str, project_path: str, file_path: str, symbol_name: str
    ) -> LocationInfo | None:
        """通过符号名查找类型定义"""
        response = await self._send_request(
            "type_definition_by_name",
            {
                "language": language,
                "project_path": project_path,
                "file_path": file_path,
                "symbol_name": symbol_name,
            },
        )

        if not response.get("success"):
            raise RuntimeError(response.get("error", "未知错误"))

        location_data = response.get("location")
        if location_data is None:
            return None

        return LocationInfo(
            file_path=location_data["file_path"],
            line=location_data["line"],
            column=location_data["column"],
            uri=f"file://{location_data['file_path']}",
            symbol_name=location_data.get("symbol_name"),
        )

    async def callers_by_name(
        self, language: str, project_path: str, file_path: str, symbol_name: str
    ) -> list[LocationInfo]:
        """通过符号名查找被调用方（该函数内部调用的所有符号）

        Args:
            language: 语言
            project_path: 项目路径
            file_path: 文件路径
            symbol_name: 符号名称

        Returns:
            被调用符号的定义位置列表
        """
        response = await self._send_request(
            "callers_by_name",
            {
                "language": language,
                "project_path": project_path,
                "file_path": file_path,
                "symbol_name": symbol_name,
            },
        )

        if not response.get("success"):
            raise RuntimeError(response.get("error", "Unknown error"))

        locations_data = response.get("locations", [])
        return [
            LocationInfo(
                file_path=loc["file_path"],
                line=loc["line"],
                column=loc["column"],
                uri=loc.get("uri", f"file://{loc['file_path']}"),
                code_snippet=loc.get("code_snippet"),
                symbol_name=loc.get("symbol_name"),
                context=loc.get("context"),
            )
            for loc in locations_data
        ]

    async def incoming_calls_by_name(
        self, language: str, project_path: str, file_path: str, symbol_name: str
    ) -> list[LocationInfo]:
        """通过符号名查询谁调用了这个符号（incoming calls / callers）

        Args:
            language: 语言
            project_path: 项目路径
            file_path: 文件路径
            symbol_name: 符号名称

        Returns:
            调用者位置列表
        """
        response = await self._send_request(
            "incoming_calls_by_name",
            {
                "language": language,
                "project_path": project_path,
                "file_path": file_path,
                "symbol_name": symbol_name,
            },
        )

        if not response.get("success"):
            raise RuntimeError(response.get("error", "Unknown error"))

        locations_data = response.get("locations", [])
        return [
            LocationInfo(
                file_path=loc["file_path"],
                line=loc["line"],
                column=loc["column"],
                uri=loc.get("uri", f"file://{loc['file_path']}"),
                code_snippet=loc.get("code_snippet"),
                symbol_name=loc.get("symbol_name"),
                context=loc.get("context"),
            )
            for loc in locations_data
        ]

    async def outgoing_calls_by_name(
        self, language: str, project_path: str, file_path: str, symbol_name: str
    ) -> list[LocationInfo]:
        """通过符号名查询这个符号调用了哪些符号（outgoing calls / callees）

        Args:
            language: 语言
            project_path: 项目路径
            file_path: 文件路径
            symbol_name: 符号名称

        Returns:
            被调用者位置列表
        """
        response = await self._send_request(
            "outgoing_calls_by_name",
            {
                "language": language,
                "project_path": project_path,
                "file_path": file_path,
                "symbol_name": symbol_name,
            },
        )

        if not response.get("success"):
            raise RuntimeError(response.get("error", "Unknown error"))

        locations_data = response.get("locations", [])
        return [
            LocationInfo(
                file_path=loc["file_path"],
                line=loc["line"],
                column=loc["column"],
                uri=loc.get("uri", f"file://{loc['file_path']}"),
                code_snippet=loc.get("code_snippet"),
                symbol_name=loc.get("symbol_name"),
                context=loc.get("context"),
            )
            for loc in locations_data
        ]
