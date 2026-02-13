"""LSP 守护进程客户端模块

该模块提供与 LSP 守护进程通信的客户端接口。
通过 Unix domain socket 发送请求并接收响应。
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from jarvis.jarvis_lsp.client import LocationInfo, SymbolInfo
from jarvis.jarvis_lsp.protocol import (
    CodeActionInfo,
    DiagnosticInfo,
    FoldingRangeInfo,
    HoverInfo,
)


class LSPDaemonClient:
    """LSP 守护进程客户端

    通过 Unix domain socket 与守护进程通信。
    """

    def __init__(self, socket_path: str | None = None):
        if socket_path is None:
            socket_path = str(Path.home() / ".jarvis" / "lsp_daemon.sock")

        self.socket_path = socket_path

    async def _ensure_daemon_running(self) -> None:
        """确保守护进程正在运行"""
        # 检查 socket 文件是否存在
        if os.path.exists(self.socket_path):
            # 尝试连接守护进程，验证是否真的在运行
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_unix_connection(self.socket_path), timeout=2.0
                )
                writer.close()
                await writer.wait_closed()
                return  # 守护进程正在运行
            except (ConnectionRefusedError, FileNotFoundError, asyncio.TimeoutError):
                # Socket 文件存在但守护进程已崩溃，继续启动
                pass

        # 启动守护进程
        daemon_script = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "jarvis_lsp", "daemon.py"
        )

        # 检查 daemon.py 是否存在
        if not os.path.exists(daemon_script):
            raise FileNotFoundError(f"守护进程脚本不存在: {daemon_script}")

        # 启动守护进程（后台运行）
        _ = await asyncio.create_subprocess_exec(
            sys.executable,
            daemon_script,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

        # 等待 socket 文件创建（最多等待 5 秒）
        for i in range(50):  # 5 秒，每次 0.1 秒
            await asyncio.sleep(0.1)
            if os.path.exists(self.socket_path):
                # 再等待 0.5 秒，确保守护进程完全启动
                await asyncio.sleep(0.5)
                return

        raise RuntimeError(f"守护进程启动失败。socket 文件未创建: {self.socket_path}")

    async def _send_request(
        self, method: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """发送请求到守护进程"""

        # 自动启动守护进程（如果未运行）
        await self._ensure_daemon_running()

        if not os.path.exists(self.socket_path):
            raise RuntimeError(
                f"守护进程启动失败。socket 文件不存在: {self.socket_path}"
            )

        request = {"method": method, "params": params}
        request_json = json.dumps(request, ensure_ascii=False)
        request_data = (
            f"Content-Length: {len(request_json)}\r\n\r\n{request_json}".encode()
        )

        try:
            reader, writer = await asyncio.open_unix_connection(self.socket_path)

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
            raise RuntimeError("无法连接到守护进程。请先运行: jlsp daemon start")
        except Exception as e:
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
        )
