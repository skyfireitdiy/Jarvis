"""LSP 守护进程模块

该模块提供一个独立的后台守护进程，管理所有 LSP server 的生命周期。
通过 Unix domain socket 提供 IPC 接口，响应客户端请求。
"""

import asyncio
import json
import os
import signal
import sys
from pathlib import Path
from typing import Any, Dict

from jarvis.jarvis_lsp.config import LSPConfigReader
from jarvis.jarvis_lsp.server_manager import LSPServerInstance


class LSPDaemon:
    """LSP 守护进程

    负责管理所有 LSP server 实例，通过 Unix domain socket 提供 IPC 接口。
    """

    def __init__(self, socket_path: str):
        self.socket_path = socket_path
        self.servers: Dict[str, LSPServerInstance] = {}
        self.config_reader = LSPConfigReader()
        self.server: asyncio.Server | None = None
        self._server_task: asyncio.Task[None] | None = None
        self.running = False

    async def start(self) -> None:
        """启动守护进程"""
        self.running = True

        # 确保 socket 文件不存在
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)

        # 创建 Unix domain socket
        self.server = await asyncio.start_unix_server(
            self.handle_client,
            path=self.socket_path,
        )

        print(f"LSP 守护进程已启动，socket: {self.socket_path}")

        # 启动服务任务
        self._server_task = asyncio.create_task(self.server.serve_forever())

        # 优雅退出处理
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

    async def _delayed_stop(self) -> None:
        """延迟停止守护进程"""
        # 等待一段时间，确保客户端收到响应
        await asyncio.sleep(0.1)
        await self.stop()

    async def stop(self) -> None:
        """停止守护进程"""
        if not self.running:
            return

        self.running = False

        # 停止所有 LSP server
        for server in list(self.servers.values()):
            await server.shutdown()
        self.servers.clear()

        # 取消服务任务
        if self._server_task:
            self._server_task.cancel()
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass

        # 关闭 socket
        if self.server:
            self.server.close()
            await self.server.wait_closed()

        # 删除 socket 文件
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)

        print("LSP 守护进程已停止")

        # 退出进程
        sys.exit(0)

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """处理客户端连接"""
        try:
            while self.running:
                # 读取请求
                line = await reader.readline()
                if not line:
                    break

                try:
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
                    request = json.loads(content.decode())

                    # 处理请求
                    response = await self.handle_request(request)

                    # 发送响应
                    response_json = json.dumps(response, ensure_ascii=False)
                    response_data = f"Content-Length: {len(response_json)}\r\n\r\n{response_json}".encode()
                    writer.write(response_data)
                    await writer.drain()

                except Exception as e:
                    # 发送错误响应
                    error_response = {
                        "success": False,
                        "error": str(e),
                    }
                    error_json = json.dumps(error_response, ensure_ascii=False)
                    error_data = f"Content-Length: {len(error_json)}\r\n\r\n{error_json}".encode()
                    writer.write(error_data)
                    await writer.drain()
                    break

        except Exception:
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """处理请求"""
        method = request.get("method")
        params = request.get("params", {})

        if method == "start_server":
            return await self.start_server(params)
        elif method == "stop_server":
            return await self.stop_server(params)
        elif method == "workspace_symbol":
            return await self.workspace_symbol(params)
        elif method == "document_symbol":
            return await self.document_symbol(params)
        elif method == "folding_range":
            return await self.folding_range(params)
        elif method == "hover":
            return await self.hover(params)
        elif method == "diagnostic":
            return await self.diagnostic(params)
        elif method == "code_action":
            return await self.code_action(params)
        elif method == "code_action_by_name":
            return await self.code_action_by_name(params)
        elif method == "definition":
            return await self.definition(params)
        elif method == "references":
            return await self.references(params)
        elif method == "implementation":
            return await self.implementation(params)
        elif method == "type_definition":
            return await self.type_definition(params)
        elif method == "definition_at_line":
            return await self.definition_at_line(params)
        elif method == "definition_by_name":
            return await self.definition_by_name(params)
        elif method == "references_by_name":
            return await self.references_by_name(params)
        elif method == "implementation_by_name":
            return await self.implementation_by_name(params)
        elif method == "type_definition_by_name":
            return await self.type_definition_by_name(params)
        elif method == "callers_by_name":
            return await self.callers_by_name(params)
        elif method == "incoming_calls_by_name":
            return await self.incoming_calls_by_name(params)
        elif method == "outgoing_calls_by_name":
            return await self.outgoing_calls_by_name(params)
        elif method == "status":
            return await self.status(params)
        elif method == "shutdown":
            # 延迟停止守护进程，先返回响应
            asyncio.create_task(self._delayed_stop())
            return {"success": True}
        else:
            return {
                "success": False,
                "error": f"Unknown method: {method}",
            }

    async def get_or_create_server(
        self, language: str, project_path: str
    ) -> LSPServerInstance:
        """获取或创建 LSP server 实例"""
        key = f"{language}:{project_path}"

        if key not in self.servers:
            server = LSPServerInstance(
                language=language,
                project_path=project_path,
            )
            await server.start(self.config_reader)
            self.servers[key] = server

        return self.servers[key]

    async def start_server(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """启动 LSP server"""
        language = params.get("language")
        project_path = params.get("project_path")

        if not language or not project_path:
            return {
                "success": False,
                "error": "Missing required parameters: language, project_path",
            }

        server = await self.get_or_create_server(language, project_path)

        return {
            "success": True,
            "pid": server.process.pid if server.process else None,
        }

    async def stop_server(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """停止 LSP server"""
        language = params.get("language")
        project_path = params.get("project_path")

        if not language or not project_path:
            return {
                "success": False,
                "error": "Missing required parameters: language, project_path",
            }

        key = f"{language}:{project_path}"

        if key in self.servers:
            server = self.servers[key]
            await server.shutdown()
            del self.servers[key]

        return {"success": True}

    async def workspace_symbol(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """在工作区中搜索符号"""
        language = params.get("language")
        project_path = params.get("project_path")
        query = params.get("query")

        if not language or not project_path or not query:
            return {
                "success": False,
                "error": "Missing required parameters: language, project_path, query",
            }

        server = await self.get_or_create_server(language, project_path)

        if server.client is None:
            return {
                "success": False,
                "error": "LSP server client not initialized",
            }

        symbols = await server.client.workspace_symbol(query)

        return {
            "success": True,
            "symbols": [
                {
                    "name": s.name,
                    "kind": s.kind,
                    "line": s.line,
                    "column": s.column,
                    "description": s.description,
                }
                for s in symbols
            ],
        }

    async def document_symbol(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """列出文件中的文档符号"""
        language = params.get("language")
        project_path = params.get("project_path")
        file_path = params.get("file_path")

        if not language or not project_path or not file_path:
            return {
                "success": False,
                "error": "Missing required parameters: language, project_path, file_path",
            }

        server = await self.get_or_create_server(language, project_path)

        if server.client is None:
            return {
                "success": False,
                "error": "LSP server client not initialized",
            }

        symbols = await server.client.document_symbol(file_path)

        return {
            "success": True,
            "symbols": [
                {
                    "name": s.name,
                    "kind": s.kind,
                    "file_path": s.file_path or file_path,
                    "line": s.line,
                    "column": s.column,
                    "description": s.description,
                }
                for s in symbols
            ],
        }

    async def folding_range(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取代码折叠范围"""
        language = params.get("language")
        project_path = params.get("project_path")
        file_path = params.get("file_path")

        if not language or not project_path or not file_path:
            return {
                "success": False,
                "error": "Missing required parameters: language, project_path, file_path",
            }

        server = await self.get_or_create_server(language, project_path)

        if server.client is None:
            return {
                "success": False,
                "error": "LSP server client not initialized",
            }

        folding_ranges = await server.client.folding_range(file_path)

        return {
            "success": True,
            "folding_ranges": [
                {
                    "start_line": fr.start_line,
                    "start_character": fr.start_character,
                    "end_line": fr.end_line,
                    "end_character": fr.end_character,
                    "kind": fr.kind,
                    "collapsed_text": fr.collapsed_text,
                }
                for fr in folding_ranges
            ],
        }

    async def hover(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取符号悬停信息"""
        language = params.get("language")
        project_path = params.get("project_path")
        file_path = params.get("file_path")
        line = params.get("line")
        character = params.get("character")

        if not language or not project_path or not file_path:
            return {
                "success": False,
                "error": "Missing required parameters: language, project_path, file_path",
            }

        if line is None or character is None:
            return {
                "success": False,
                "error": "Missing required parameters: line, character",
            }

        server = await self.get_or_create_server(language, project_path)

        if server.client is None:
            return {
                "success": False,
                "error": "LSP server client not initialized",
            }

        hover_info = await server.client.hover(file_path, line, character)

        if hover_info is None:
            return {
                "success": True,
                "hover_info": None,
            }

        return {
            "success": True,
            "hover_info": {
                "contents": hover_info.contents,
                "range": hover_info.range,
                "file_path": hover_info.file_path,
                "line": hover_info.line,
                "character": hover_info.character,
            },
        }

    async def diagnostic(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取代码诊断信息"""
        language = params.get("language")
        project_path = params.get("project_path")
        file_path = params.get("file_path")
        severity_filter = params.get("severity_filter")

        if not language or not project_path or not file_path:
            return {
                "success": False,
                "error": "Missing required parameters: language, project_path, file_path",
            }

        server = await self.get_or_create_server(language, project_path)

        if server.client is None:
            return {
                "success": False,
                "error": "LSP server client not initialized",
            }

        try:
            diagnostics = await server.client.diagnostic(file_path, severity_filter)
        except RuntimeError as e:
            # 检查是否是方法不支持的错误
            error_msg = str(e)
            if "Method Not Found" in error_msg or "-32601" in error_msg:
                return {
                    "success": False,
                    "error": f"LSP server does not support textDocument/diagnostic method. {language} LSP server may not provide diagnostics.",
                    "not_supported": True,
                }
            raise

        return {
            "success": True,
            "diagnostics": [
                {
                    "range": diag.range,
                    "severity": diag.severity,
                    "code": diag.code,
                    "source": diag.source,
                    "message": diag.message,
                }
                for diag in diagnostics
            ],
        }

    async def code_action(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取代码动作信息"""
        language = params.get("language")
        project_path = params.get("project_path")
        file_path = params.get("file_path")
        line = params.get("line")
        character = params.get("character")

        if not language or not project_path or not file_path:
            return {
                "success": False,
                "error": "Missing required parameters: language, project_path, file_path",
            }

        if line is None or character is None:
            return {
                "success": False,
                "error": "Missing required parameters: line, character",
            }

        server = await self.get_or_create_server(language, project_path)

        if server.client is None:
            return {
                "success": False,
                "error": "LSP server client not initialized",
            }

        try:
            code_actions = await server.client.code_action(file_path, line, character)
        except RuntimeError as e:
            # 检查是否是方法不支持的错误
            error_msg = str(e)
            if "Method Not Found" in error_msg or "-32601" in error_msg:
                return {
                    "success": False,
                    "error": f"LSP server does not support textDocument/codeAction method. {language} LSP server may not provide code actions.",
                    "not_supported": True,
                }
            raise

        return {
            "success": True,
            "code_actions": [
                {
                    "title": action.title,
                    "kind": action.kind,
                    "is_preferred": action.is_preferred,
                }
                for action in code_actions
            ],
        }

    async def code_action_by_name(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """通过符号名获取代码动作信息"""
        language = params.get("language")
        project_path = params.get("project_path")
        file_path = params.get("file_path")
        symbol_name = params.get("symbol_name")

        if not language or not project_path or not file_path:
            return {
                "success": False,
                "error": "Missing required parameters: language, project_path, file_path",
            }

        if not symbol_name:
            return {
                "success": False,
                "error": "Missing required parameter: symbol_name",
            }

        server = await self.get_or_create_server(language, project_path)

        if server.client is None:
            return {
                "success": False,
                "error": "LSP server client not initialized",
            }

        try:
            code_actions = await server.client.code_action_by_name(
                file_path, symbol_name
            )
        except RuntimeError as e:
            # 检查是否是方法不支持的错误
            error_msg = str(e)
            if "Method Not Found" in error_msg or "-32601" in error_msg:
                return {
                    "success": False,
                    "error": f"LSP server does not support textDocument/codeAction method. {language} LSP server may not provide code actions.",
                    "not_supported": True,
                }
            raise

        return {
            "success": True,
            "code_actions": [
                {
                    "title": action.title,
                    "kind": action.kind,
                    "is_preferred": action.is_preferred,
                }
                for action in code_actions
            ],
        }

    async def status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取守护进程状态"""
        servers_dict = {}

        for key, server in self.servers.items():
            servers_dict[key] = {
                "pid": server.process.pid if server.process else None,
                "start_time": str(server.last_activity) if server.last_activity else "",
                "is_alive": server.is_alive(),
            }

        return {
            "success": True,
            **servers_dict,
        }

    async def definition(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """跳转到定义"""
        language = params.get("language")
        project_path = params.get("project_path")
        file_path = params.get("file_path")
        line = params.get("line")
        column = params.get("column", 0)

        # 类型检查
        if not isinstance(language, str) or not isinstance(project_path, str):
            return {
                "success": False,
                "error": "Missing required parameters: language, project_path",
            }
        if not isinstance(file_path, str) or not isinstance(line, int):
            return {
                "success": False,
                "error": "Missing required parameters: file_path, line",
            }

        server = await self.get_or_create_server(language, project_path)

        if server.client is None:
            return {
                "success": False,
                "error": "LSP server client not initialized",
            }

        locations = await server.client.definition(file_path, line, column)
        print(
            f"[DEBUG] daemon.definition: file_path={file_path}, line={line}, column={column}, locations={locations}"
        )

        if not locations:
            return {"success": True, "location": None}

        # 返回第一个位置（不包含 code_snippet 和 context 以避免 JSON 序列化问题）
        first_location = locations[0]
        # 检查位置的有效性：file_path 不能为空
        if not first_location.file_path:
            return {"success": True, "location": None}

        return {
            "success": True,
            "location": {
                "file_path": first_location.file_path,
                "line": first_location.line,
                "column": first_location.column,
                "uri": first_location.uri,
                "symbol_name": first_location.symbol_name,
                # "code_snippet": first_location.code_snippet,
                # "context": first_location.context,
            },
        }

    async def references(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """查找所有引用"""
        language = params.get("language")
        project_path = params.get("project_path")
        file_path = params.get("file_path")
        line = params.get("line")
        column = params.get("column", 0)

        # 类型检查
        if not isinstance(language, str) or not isinstance(project_path, str):
            return {
                "success": False,
                "error": "Missing required parameters: language, project_path",
            }
        if not isinstance(file_path, str) or not isinstance(line, int):
            return {
                "success": False,
                "error": "Missing required parameters: file_path, line",
            }

        server = await self.get_or_create_server(language, project_path)

        if server.client is None:
            return {
                "success": False,
                "error": "LSP server client not initialized",
            }

        locations = await server.client.references(file_path, line, column)

        return {
            "success": True,
            "locations": [
                {
                    "file_path": loc.file_path,
                    "line": loc.line,
                    "column": loc.column,
                }
                for loc in locations
            ],
        }

    async def implementation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """查找实现"""
        language = params.get("language")
        project_path = params.get("project_path")
        file_path = params.get("file_path")
        line = params.get("line")
        column = params.get("column", 0)

        # 类型检查
        if not isinstance(language, str) or not isinstance(project_path, str):
            return {
                "success": False,
                "error": "Missing required parameters: language, project_path",
            }
        if not isinstance(file_path, str) or not isinstance(line, int):
            return {
                "success": False,
                "error": "Missing required parameters: file_path, line",
            }

        server = await self.get_or_create_server(language, project_path)

        if server.client is None:
            return {
                "success": False,
                "error": "LSP server client not initialized",
            }

        try:
            locations = await server.client.implementation(file_path, line, column)
        except NotImplementedError:
            return {
                "success": False,
                "error": "LSP server does not support implementation",
            }
        except RuntimeError as e:
            # 检查是否是 Method Not Found 错误
            if "Method Not Found" in str(e) or "-32601" in str(e):
                return {
                    "success": False,
                    "error": "LSP server does not support implementation",
                }
            raise

        return {
            "success": True,
            "locations": [
                {
                    "file_path": loc.file_path,
                    "line": loc.line,
                    "column": loc.column,
                }
                for loc in locations
            ],
        }

    async def type_definition(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """查找类型定义"""
        language = params.get("language")
        project_path = params.get("project_path")
        file_path = params.get("file_path")
        line = params.get("line")
        column = params.get("column", 0)

        # 类型检查
        if not isinstance(language, str) or not isinstance(project_path, str):
            return {
                "success": False,
                "error": "Missing required parameters: language, project_path",
            }
        if not isinstance(file_path, str) or not isinstance(line, int):
            return {
                "success": False,
                "error": "Missing required parameters: file_path, line",
            }

        server = await self.get_or_create_server(language, project_path)

        if server.client is None:
            return {
                "success": False,
                "error": "LSP server client not initialized",
            }

        try:
            locations = await server.client.type_definition(file_path, line, column)
        except NotImplementedError:
            return {
                "success": False,
                "error": "LSP server does not support type definition",
            }
        except RuntimeError as e:
            # 检查是否是 Method Not Found 错误
            if "Method Not Found" in str(e) or "-32601" in str(e):
                return {
                    "success": False,
                    "error": "LSP server does not support type definition",
                }
            raise

        if not locations:
            return {"success": True, "location": None}

        # 返回第一个位置（不包含 code_snippet 和 context 以避免 JSON 序列化问题）
        first_location = locations[0]
        # 检查位置的有效性：file_path 不能为空
        if not first_location.file_path:
            return {"success": True, "location": None}

        return {
            "success": True,
            "location": {
                "file_path": first_location.file_path,
                "line": first_location.line,
                "column": first_location.column,
                "uri": first_location.uri,
                "symbol_name": first_location.symbol_name,
                # "code_snippet": first_location.code_snippet,
                # "context": first_location.context,
            },
        }

    def _find_symbol_by_name(
        self, symbols: list[Dict[str, Any]], symbol_name: str, file_path: str
    ) -> Dict[str, Any] | None:
        """在符号列表中查找指定名称的符号

        Args:
            symbols: 符号列表
            symbol_name: 符号名称
            file_path: 文件路径（用于错误提示）

        Returns:
            匹配的符号字典，如果找不到返回 None

        Raises:
            RuntimeError: 如果找到多个匹配的符号
        """
        # 精确匹配
        exact_matches = [s for s in symbols if s["name"] == symbol_name]

        if len(exact_matches) == 1:
            return exact_matches[0]
        elif len(exact_matches) > 1:
            # 多个精确匹配，返回第一个
            return exact_matches[0]

        # 模糊匹配（包含符号名）
        fuzzy_matches = [s for s in symbols if symbol_name.lower() in s["name"].lower()]

        if len(fuzzy_matches) == 1:
            return fuzzy_matches[0]
        elif len(fuzzy_matches) > 1:
            # 多个模糊匹配，选择最相似的（最短的）
            fuzzy_matches.sort(key=lambda s: len(s["name"]))
            return fuzzy_matches[0]

        return None

    async def definition_by_name(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """通过符号名查找定义"""
        language = params.get("language")
        project_path = params.get("project_path")
        file_path = params.get("file_path")
        symbol_name = params.get("symbol_name")

        if not language or not project_path or not file_path or not symbol_name:
            return {
                "success": False,
                "error": "Missing required parameters: language, project_path, file_path, symbol_name",
            }

        server = await self.get_or_create_server(language, project_path)

        if server.client is None:
            return {
                "success": False,
                "error": "LSP server client not initialized",
            }

        symbols_result = await self.document_symbol(
            {
                "language": language,
                "project_path": project_path,
                "file_path": file_path,
            }
        )

        if not symbols_result.get("success"):
            return symbols_result

        symbols = symbols_result.get("symbols", [])
        print(
            f"[DEBUG] daemon.definition_by_name: found {len(symbols)} symbols: {[s['name'] + ':' + s['kind'] for s in symbols]}"
        )
        print(
            f"[DEBUG] daemon.definition_by_name: looking for symbol_name={symbol_name}"
        )
        symbol = self._find_symbol_by_name(symbols, symbol_name, file_path)
        print(f"[DEBUG] daemon.definition_by_name: symbol = {symbol}")

        if symbol is None:
            return {
                "success": False,
                "error": f"Symbol '{symbol_name}' not found in file '{file_path}'",
            }

        # 直接返回符号的位置（不再调用 definition，因为在定义位置查询定义会返回空）
        result = {
            "success": True,
            "location": {
                "file_path": file_path,
                "line": symbol["line"],  # 1-based 行号
                "column": symbol["column"],  # 1-based 列号
                "uri": f"file://{file_path}",
                "symbol_name": symbol_name,
            },
        }
        return result

    async def callers_by_name(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """查询指定函数内部调用了哪些其他函数"""
        language = params.get("language")
        project_path = params.get("project_path")
        file_path = params.get("file_path")
        symbol_name = params.get("symbol_name")

        if not language or not project_path or not file_path or not symbol_name:
            return {
                "success": False,
                "error": "Missing required parameters: language, project_path, file_path, symbol_name",
            }

        # 获取符号位置
        symbols_result = await self.document_symbol(
            {
                "language": language,
                "project_path": project_path,
                "file_path": file_path,
            }
        )

        if not symbols_result.get("success"):
            return symbols_result

        symbols = symbols_result.get("symbols", [])
        symbol = self._find_symbol_by_name(symbols, symbol_name, file_path)

        if symbol is None:
            return {
                "success": False,
                "error": f"Symbol '{symbol_name}' not found in file '{file_path}'",
            }

        # 获取符号的起始和结束行号
        start_line = symbol["line"]
        end_line = symbol["end_line"]

        # 解析函数调用
        server = await self.get_or_create_server(language, project_path)

        if server.client is None:
            return {
                "success": False,
                "error": "LSP server client not initialized",
            }

        callers = await server.client.callers_in_range(
            file_path, start_line, end_line, language
        )

        return {
            "success": True,
            "callers": callers,
        }

    async def definition_at_line(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """通过行号查找定义（自动查找该行的符号列号）"""
        language = params.get("language")
        project_path = params.get("project_path")
        file_path = params.get("file_path")
        line = params.get("line")
        symbol_name = params.get("symbol_name")  # 必填，用于精确匹配

        if (
            not language
            or not project_path
            or not file_path
            or line is None
            or not symbol_name
        ):
            return {
                "success": False,
                "error": "Missing required parameters: language, project_path, file_path, line, symbol_name",
            }

        # 获取文件中的符号列表
        symbols_result = await self.document_symbol(
            {
                "language": language,
                "project_path": project_path,
                "file_path": file_path,
            }
        )

        if not symbols_result.get("success"):
            return symbols_result

        symbols = symbols_result.get("symbols", [])

        # 查找该行的符号（document_symbol 和 line 参数都是 1-based）
        line_symbols = [s for s in symbols if s["line"] == line]

        if not line_symbols:
            return {
                "success": False,
                "error": f"No symbol found at line {line}",
            }

        # 使用符号名精确匹配
        matched = [s for s in line_symbols if s["name"] == symbol_name]
        if matched:
            target_symbol = matched[0]
        else:
            return {
                "success": False,
                "error": f"Symbol '{symbol_name}' not found at line {line}",
            }

        # 如果列号为 0，自动查找符号在该行的实际位置
        column = target_symbol["column"]
        if column == 0:
            try:
                # 读取文件内容，查找符号在该行的实际列号
                import asyncio
                from pathlib import Path

                content_text = await asyncio.to_thread(Path(file_path).read_text)
                lines = content_text.splitlines()
                if line < len(lines):
                    line_content = lines[line]
                    symbol_pos = line_content.find(target_symbol["name"])
                    if symbol_pos != -1:
                        column = symbol_pos
            except Exception:
                pass  # 如果查找失败，使用原始列号

        # 调用 definition 方法查找定义
        return await self.definition(
            {
                "language": language,
                "project_path": project_path,
                "file_path": file_path,
                "line": target_symbol["line"],
                "column": column,
            }
        )

    async def references_by_name(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """通过符号名查找引用"""
        language = params.get("language")
        project_path = params.get("project_path")
        file_path = params.get("file_path")
        symbol_name = params.get("symbol_name")

        if not language or not project_path or not file_path or not symbol_name:
            return {
                "success": False,
                "error": "Missing required parameters: language, project_path, file_path, symbol_name",
            }

        server = await self.get_or_create_server(language, project_path)

        if server.client is None:
            return {
                "success": False,
                "error": "LSP server client not initialized",
            }

        symbols_result = await self.document_symbol(
            {
                "language": language,
                "project_path": project_path,
                "file_path": file_path,
            }
        )

        if not symbols_result.get("success"):
            return symbols_result

        symbols = symbols_result.get("symbols", [])
        symbol = self._find_symbol_by_name(symbols, symbol_name, file_path)

        if symbol is None:
            return {
                "success": False,
                "error": f"Symbol '{symbol_name}' not found in file '{file_path}'",
            }

        return await self.references(
            {
                "language": language,
                "project_path": project_path,
                "file_path": file_path,
                "line": symbol["line"],
                "column": symbol["column"],
            }
        )

    async def implementation_by_name(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """通过符号名查找实现"""
        language = params.get("language")
        project_path = params.get("project_path")
        file_path = params.get("file_path")
        symbol_name = params.get("symbol_name")

        if not language or not project_path or not file_path or not symbol_name:
            return {
                "success": False,
                "error": "Missing required parameters: language, project_path, file_path, symbol_name",
            }

        server = await self.get_or_create_server(language, project_path)

        if server.client is None:
            return {
                "success": False,
                "error": "LSP server client not initialized",
            }

        symbols_result = await self.document_symbol(
            {
                "language": language,
                "project_path": project_path,
                "file_path": file_path,
            }
        )

        if not symbols_result.get("success"):
            return symbols_result

        symbols = symbols_result.get("symbols", [])
        symbol = self._find_symbol_by_name(symbols, symbol_name, file_path)

        if symbol is None:
            return {
                "success": False,
                "error": f"Symbol '{symbol_name}' not found in file '{file_path}'",
            }

        return await self.definition(
            {
                "language": language,
                "project_path": project_path,
                "file_path": file_path,
                "line": symbol["line"] - 1,  # SymbolInfo 是 1-based，LSP 需要 0-based
                "column": symbol["column"]
                - 1,  # SymbolInfo 是 1-based，LSP 需要 0-based
            }
        )

    async def type_definition_by_name(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """通过符号名查找类型定义"""
        language = params.get("language")
        project_path = params.get("project_path")
        file_path = params.get("file_path")
        symbol_name = params.get("symbol_name")

        if not language or not project_path or not file_path or not symbol_name:
            return {
                "success": False,
                "error": "Missing required parameters: language, project_path, file_path, symbol_name",
            }

        server = await self.get_or_create_server(language, project_path)

        if server.client is None:
            return {
                "success": False,
                "error": "LSP server client not initialized",
            }

        symbols_result = await self.document_symbol(
            {
                "language": language,
                "project_path": project_path,
                "file_path": file_path,
            }
        )

        if not symbols_result.get("success"):
            return symbols_result

        symbols = symbols_result.get("symbols", [])
        symbol = self._find_symbol_by_name(symbols, symbol_name, file_path)

        if symbol is None:
            return {
                "success": False,
                "error": f"Symbol '{symbol_name}' not found in file '{file_path}'",
            }

        return await self.type_definition(
            {
                "language": language,
                "project_path": project_path,
                "file_path": file_path,
                "line": symbol["line"],
                "column": symbol["column"],
            }
        )

    async def callers_by_name(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """通过符号名查找被调用方（该函数内部调用的所有符号）"""
        language = params.get("language")
        project_path = params.get("project_path")
        file_path = params.get("file_path")
        symbol_name = params.get("symbol_name")

        if not language or not project_path or not file_path or not symbol_name:
            return {
                "success": False,
                "error": "Missing required parameters: language, project_path, file_path, symbol_name",
            }

        server = await self.get_or_create_server(language, project_path)

        if server.client is None:
            return {
                "success": False,
                "error": "LSP server client not initialized",
            }

        try:
            locations = await server.client.callers_by_name(file_path, symbol_name)
        except RuntimeError as e:
            error_msg = str(e)
            if "Method Not Found" in error_msg or "-32601" in error_msg:
                return {
                    "success": False,
                    "error": f"LSP server does not support the required method. {error_msg}",
                    "not_supported": True,
                }
            raise

        return {
            "success": True,
            "locations": [
                {
                    "file_path": loc.file_path,
                    "line": loc.line,
                    "column": loc.column,
                    "uri": loc.uri,
                    "symbol_name": loc.symbol_name,
                    "context": loc.context,
                    "code_snippet": loc.code_snippet,
                }
                for loc in locations
            ],
        }

    async def incoming_calls_by_name(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """通过符号名查询谁调用了这个符号（incoming calls / callers）"""
        language = params.get("language")
        project_path = params.get("project_path")
        file_path = params.get("file_path")
        symbol_name = params.get("symbol_name")

        if not language or not project_path or not file_path or not symbol_name:
            return {
                "success": False,
                "error": "Missing required parameters: language, project_path, file_path, symbol_name",
            }

        server = await self.get_or_create_server(language, project_path)

        if server.client is None:
            return {
                "success": False,
                "error": "LSP server client not initialized",
            }

        try:
            locations = await server.client.incoming_calls_by_name(
                file_path, symbol_name
            )
        except RuntimeError as e:
            error_msg = str(e)
            if "Method Not Found" in error_msg or "-32601" in error_msg:
                return {
                    "success": False,
                    "error": f"LSP server does not support callHierarchy. {error_msg}",
                    "not_supported": True,
                }
            raise

        return {
            "success": True,
            "locations": [
                {
                    "file_path": loc.file_path,
                    "line": loc.line,
                    "column": loc.column,
                    "uri": loc.uri,
                    "symbol_name": loc.symbol_name,
                    "context": loc.context,
                    "code_snippet": loc.code_snippet,
                }
                for loc in locations
            ],
        }

    async def outgoing_calls_by_name(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """通过符号名查询这个符号调用了哪些符号（outgoing calls / callees）"""
        language = params.get("language")
        project_path = params.get("project_path")
        file_path = params.get("file_path")
        symbol_name = params.get("symbol_name")

        if not language or not project_path or not file_path or not symbol_name:
            return {
                "success": False,
                "error": "Missing required parameters: language, project_path, file_path, symbol_name",
            }

        server = await self.get_or_create_server(language, project_path)

        if server.client is None:
            return {
                "success": False,
                "error": "LSP server client not initialized",
            }

        try:
            locations = await server.client.outgoing_calls_by_name(
                file_path, symbol_name
            )
        except RuntimeError as e:
            error_msg = str(e)
            if "Method Not Found" in error_msg or "-32601" in error_msg:
                return {
                    "success": False,
                    "error": f"LSP server does not support callHierarchy. {error_msg}",
                    "not_supported": True,
                }
            raise

        return {
            "success": True,
            "locations": [
                {
                    "file_path": loc.file_path,
                    "line": loc.line,
                    "column": loc.column,
                    "uri": loc.uri,
                    "symbol_name": loc.symbol_name,
                    "context": loc.context,
                    "code_snippet": loc.code_snippet,
                }
                for loc in locations
            ],
        }


async def main(socket_path: str | None = None) -> None:
    """主函数"""
    if socket_path is None:
        socket_path = str(Path.home() / ".jarvis" / "lsp_daemon.sock")

    daemon = LSPDaemon(socket_path)
    await daemon.start()

    try:
        # 等待停止信号
        while daemon.running:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        await daemon.stop()


if __name__ == "__main__":
    socket_path_arg: str | None = None
    if len(sys.argv) > 1:
        socket_path_arg = sys.argv[1]

    asyncio.run(main(socket_path_arg))
