# -*- coding: utf-8 -*-
"""Web Gateway FastAPI 应用。

独立服务：通过 WebSocket 对接 Gateway 输入/输出/执行事件。
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from typing import Callable
from typing import Dict
from typing import Optional
from typing import Tuple

from fastapi import FastAPI
from fastapi import WebSocket
from fastapi import WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from jarvis.jarvis_gateway.events import GatewayConfirmRequest
from jarvis.jarvis_gateway.events import GatewayConfirmResult
from jarvis.jarvis_gateway.events import GatewayExecutionEvent
from jarvis.jarvis_gateway.events import GatewayInputRequest
from jarvis.jarvis_gateway.events import GatewayInputResult
from jarvis.jarvis_gateway.events import GatewayOutputEvent
from jarvis.jarvis_gateway.gateway import BaseGateway
from jarvis.jarvis_gateway.input_bridge import InputSessionRegistry
from jarvis.jarvis_gateway.manager import set_current_gateway
from jarvis.jarvis_gateway.output_bridge import SessionOutputRouter
from jarvis.jarvis_web_gateway.agent_manager import AgentManager
from jarvis.jarvis_web_gateway.terminal_input_registry import TerminalInputRegistry
from jarvis.jarvis_utils.globals import set_interrupt


# 全局 AgentManager，用于状态变更回调
_global_agent_manager: Optional[AgentManager] = None

# 状态更新回调函数
_status_update_callback: Optional[Callable[[str], None]] = None

# 全局 SessionOutputRouter，用于推送状态更新
_router: Optional[SessionOutputRouter] = None


def set_status_update_callback(callback: Optional[Callable[[str], None]]) -> None:
    """设置状态更新回调函数。

    Args:
        callback: 回调函数，接收状态字符串 ("running"/"waiting_multi"/"waiting_single")
    """
    global _status_update_callback
    _status_update_callback = callback


def _update_status(status: str) -> None:
    """更新状态。

    Args:
        status: 状态字符串
    """

    global _status_update_callback, _router  # 添加 _router 到全局

    # 1. 调用回调函数更新本地状态
    if _status_update_callback:
        try:
            _status_update_callback(status)
        except Exception:
            # 静默忽略状态更新失败，不影响主流程
            pass

    # 2. 通过 WebSocket 推送状态变化给前端
    if _router:
        try:
            # 单连接模式，固定使用 default session_id
            session_id = "default"
            # 推送状态变化消息
            message = {"type": "status_update", "payload": {"execution_status": status}}
            _router.publish(message, session_id=session_id)
        except Exception:
            pass


def _on_agent_status_change(agent_id: str, status: str, data: Any) -> None:
    """Agent 状态变更回调，发送 WebSocket 通知。

    Args:
        agent_id: Agent ID
        status: 新状态 ("running", "stopped", "error")
        data: 额外数据
    """
    # TODO: 实现 WebSocket 广播，向所有连接的前端发送状态变更通知
    # 这里需要修改 WebSocketConnectionManager 来支持广播
    pass


class WebGateway(BaseGateway):
    """Web Gateway 实现：桥接输出、输入与执行事件到 WebSocket。"""

    def __init__(
        self,
        router: SessionOutputRouter,
        input_registry: InputSessionRegistry,
        auth_store: Dict[str, Optional[Dict[str, Any]]],
        terminal_input_registry: TerminalInputRegistry,
    ) -> None:
        self._router = router
        self._input_registry = input_registry
        self._auth_store = auth_store
        self._terminal_input_registry = terminal_input_registry

    def emit_output(self, event: GatewayOutputEvent) -> None:
        # 单连接模式，固定使用 default session_id
        session_id = "default"
        auth_payload = self._auth_store.get(session_id)
        authorized, _ = self._check_auth(auth_payload)
        if not authorized:
            return
        payload = {
            "text": event.text,
            "output_type": event.output_type,
            "timestamp": event.timestamp,
            "lang": event.lang,
            "traceback": event.traceback,
            "section": event.section,
            "context": dict(event.context) if event.context else {},
        }
        message = {"type": "output", "payload": payload}
        self._router.publish(message, session_id=session_id)

    def request_input(self, request: GatewayInputRequest) -> GatewayInputResult:
        # 单连接模式，固定使用 default session_id
        session_id = "default"
        metadata = dict(request.metadata) if request.metadata else {}
        metadata["session_id"] = session_id
        auth_payload = metadata.get("auth") or self._auth_store.get(session_id)
        authorized, reason = self._check_auth(auth_payload)
        if not authorized:
            return GatewayInputResult(text="", metadata={"error": reason})
        payload = {
            "tip": request.tip,
            "mode": request.mode or "multi",  # 默认多行模式
            "preset": request.preset,
            "preset_cursor": request.preset_cursor,
            "metadata": metadata,
        }
        message = {"type": "input_request", "payload": payload}
        self._router.publish(message, session_id=session_id)
        # 保存输入请求，用于重连后恢复
        self._input_registry.save_input_request(session_id, message)

        # 更新状态为等待输入
        if request.mode == "single":
            _update_status("waiting_single")
        else:
            _update_status("waiting_multi")

        session = self._input_registry.get_or_create(session_id)
        text = session.wait_for_input()

        # 输入完成，恢复为运行状态
        _update_status("running")

        return GatewayInputResult(text=text, metadata=metadata)

    def request_confirm(self, request: GatewayConfirmRequest) -> GatewayConfirmResult:
        # 单连接模式，固定使用 default session_id
        session_id = "default"
        metadata = dict(request.metadata) if request.metadata else {}
        metadata["session_id"] = session_id
        auth_payload = metadata.get("auth") or self._auth_store.get(session_id)
        authorized, reason = self._check_auth(auth_payload)
        if not authorized:
            return GatewayConfirmResult(
                confirmed=request.default if request.default is not None else False,
                metadata={"error": reason},
            )
        payload = {
            "message": request.message,
            "default": request.default,
            "metadata": metadata,
        }
        message = {"type": "confirm", "payload": payload}
        self._router.publish(message, session_id=session_id)
        # 保存确认请求，用于重连后恢复
        self._input_registry.save_confirm_request(session_id, message)

        # 更新状态为等待单行输入（确认）
        _update_status("waiting_single")

        session = self._input_registry.get_or_create_confirm_session(session_id)
        confirmed = session.wait_for_confirm()

        # 确认完成，恢复为运行状态
        _update_status("running")

        return GatewayConfirmResult(confirmed=confirmed, metadata=metadata)

    def publish_execution_event(
        self,
        event: GatewayExecutionEvent,
        session_id: Optional[str] = None,
    ) -> None:
        # 单连接模式，固定使用 default session_id
        session_id = "default"
        payload = dict(event.payload) if event.payload else {}
        auth_payload = payload.get("auth") or (
            self._auth_store.get(session_id) if session_id else None
        )
        authorized, _ = self._check_auth(auth_payload)
        if not authorized:
            return

        # 🔧 适配前端期望的消息结构
        # 前端期望: { event_type: 'stdout'|'stderr', data: '...', encoded: true/false }
        # 后端原始: { stream: 'stdout', chunk: '...', encoded: true }
        stream = payload.get("stream", "stdout")  # "stdout" 或 "stderr" 或 "tty"
        chunk = payload.get("chunk", "")  # 实际输出内容（可能是 base64 编码的字符串）
        encoded = payload.get("encoded", False)  # 是否经过 base64 编码
        # 🔧 将 'tty' 映射为 'stdout'，以便前端能正确处理
        if stream == "tty":
            stream = "stdout"

        message_payload = {
            "event_type": stream,  # 使用 stream 作为 event_type
            "data": chunk,  # 使用 chunk 作为 data（可能是 base64）
            "encoded": encoded,  # 传递编码标记
            "tool": payload.get("tool"),
            "sequence": payload.get("sequence"),
            "execution_id": payload.get("execution_id"),
        }
        if event.timestamp:
            message_payload["timestamp"] = event.timestamp
        if "message_type" in payload:
            message_payload["message_type"] = payload["message_type"]

        message = {"type": "execution", "payload": message_payload}
        self._router.publish(message, session_id=session_id)

    def get_execution_input_callback(
        self,
        execution_id: str,
    ) -> Optional[Callable[[Optional[float]], Optional[str]]]:
        return self._terminal_input_registry.get_input_callback(execution_id)

    def get_execution_resize_callback(
        self,
        execution_id: str,
    ) -> Optional[Callable[[], Optional[Tuple[int, int]]]]:
        return self._terminal_input_registry.get_resize_callback(execution_id)


class WebSocketConnectionManager:
    """WebSocket 连接管理。"""

    def __init__(
        self,
        router: SessionOutputRouter,
        input_registry: InputSessionRegistry,
        terminal_input_registry: TerminalInputRegistry,
        gateway: WebGateway,
        auth_store: Dict[str, Optional[Dict[str, Any]]],
    ) -> None:
        self._router = router
        self._input_registry = input_registry
        self._terminal_input_registry = terminal_input_registry
        self._gateway = gateway
        self._auth_store = auth_store

    async def handle(self, websocket: WebSocket) -> None:
        await websocket.accept()
        session_id = "default"  # 固定使用 default session，简化重连逻辑
        connection_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        auth_payload = _extract_auth_from_headers(websocket)
        authorized, reason = self._gateway._check_auth(auth_payload)
        if not authorized:
            auth_payload, authorized, reason = await _await_auth_message(
                websocket, self._gateway
            )
        if not authorized:
            await _send_error(websocket, "AUTH_FAILED", reason or "auth failed")
            await websocket.close()
            return

        # 检查是否已有活跃连接，如果有则拒绝新连接（在认证后、注册前检查）
        if self._router.has_active_subscribers():
            await _send_error(
                websocket, "CONNECTION_REJECTED", "Already have an active connection"
            )
            await websocket.close()
            return

        self._auth_store[session_id] = auth_payload
        self._router.register(
            connection_id,
            _build_sender(websocket, loop),
            session_id=session_id,
        )
        self._input_registry.register_provider(session_id)
        await websocket.send_json(
            {"type": "ready", "payload": {"session_id": session_id}}
        )
        # 恢复待处理的输入请求
        pending_request = self._input_registry.get_input_request(session_id)
        print(
            f"[RECONNECT] session_id={session_id}, pending_request={pending_request is not None}"
        )
        if pending_request:
            session = self._input_registry.get_or_create(session_id)
            print("[RECONNECT] Got session, reconnecting...")
            session.reconnect()
            print(f"[RECONNECT] Sending input_request: {pending_request}")
            await websocket.send_json(pending_request)
        # 恢复待处理的确认请求
        pending_confirm = self._input_registry.get_confirm_request(session_id)
        print(
            f"[RECONNECT] session_id={session_id}, pending_confirm={pending_confirm is not None}"
        )
        if pending_confirm:
            confirm_session = self._input_registry.get_or_create_confirm_session(
                session_id
            )
            print("[RECONNECT] Got confirm session, reconnecting...")
            confirm_session.reconnect()
            print(f"[RECONNECT] Sending confirm_request: {pending_confirm}")
            await websocket.send_json(pending_confirm)
        try:
            while True:
                message = await websocket.receive_json()
                await self._handle_message(session_id, message)
        except WebSocketDisconnect:
            pass
        finally:
            self._router.unregister(connection_id, session_id=session_id)
            self._input_registry.unregister_provider(session_id)
            self._input_registry.disconnect_confirm_session(session_id)
            self._auth_store.pop(session_id, None)

    async def _handle_message(self, session_id: str, message: Any) -> None:
        if not isinstance(message, dict):
            return
        message_type = message.get("type")
        payload = message.get("payload") or {}
        if message_type == "auth":
            auth_payload = _normalize_auth_payload(payload)
            authorized, _ = self._gateway._check_auth(auth_payload)
            if not authorized:
                return
            self._auth_store[session_id] = auth_payload
            return
        if message_type == "input_result":
            text = payload.get("text", "")
            self._input_registry.submit_input(session_id, text)
            return
        if message_type == "confirm_result":
            confirmed = payload.get("confirmed", False)
            self._input_registry.submit_confirm(session_id, confirmed)
            return
        if message_type == "terminal_input":
            execution_id = payload.get("execution_id")
            data = payload.get("data", "")
            if not execution_id:
                return
            self._terminal_input_registry.submit_terminal_input(execution_id, data)
            return
        if message_type == "terminal_resize":
            execution_id = payload.get("execution_id")
            rows = payload.get("rows")
            cols = payload.get("cols")
            if not execution_id:
                return
            try:
                rows_int = int(rows)
                cols_int = int(cols)
            except (TypeError, ValueError):
                return
            self._terminal_input_registry.submit_terminal_resize(
                execution_id, rows_int, cols_int
            )
            return
        if message_type == "manual_interrupt":
            set_interrupt(True)
            return


def create_app(custom_app: Optional[FastAPI] = None) -> FastAPI:
    """创建 FastAPI 应用。

    Args:
        custom_app: 自定义 FastAPI app，用于添加额外的路由（如状态查询）

    Returns:
        FastAPI 应用实例
    """

    # 创建 AgentManager，并设置状态变更回调
    agent_manager = AgentManager(on_status_change=_on_agent_status_change)
    # 保存 agent_manager 到全局，以便回调访问
    global _global_agent_manager
    _global_agent_manager = agent_manager

    router = SessionOutputRouter()
    input_registry = InputSessionRegistry()
    terminal_input_registry = TerminalInputRegistry()

    # 保存 router 到全局，用于状态更新时推送消息
    global _router
    _router = router
    auth_store: Dict[str, Optional[Dict[str, Any]]] = {}
    gateway = WebGateway(router, input_registry, auth_store, terminal_input_registry)
    manager = WebSocketConnectionManager(
        router, input_registry, terminal_input_registry, gateway, auth_store
    )

    set_current_gateway(gateway)

    # 使用自定义 app 或创建新 app
    app = custom_app if custom_app is not None else FastAPI()

    # 添加 CORS 中间件，允许前端跨域访问
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 生产环境应该指定具体域名
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def _startup() -> None:
        # 为运行中的 Agent 启动监控任务
        await agent_manager.start_monitoring_for_running_agents()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        # 清理所有 Agent
        await agent_manager.cleanup()
        set_current_gateway(None)

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await manager.handle(websocket)

    # HTTP API：创建 Agent
    @app.post("/api/agents")
    async def create_agent(request: Dict[str, Any]) -> Dict[str, Any]:
        """创建 Agent。"""
        try:
            agent_type = request.get("agent_type")
            working_dir = request.get("working_dir")
            name = request.get("name")
            llm_group = request.get("llm_group", "default")
            tool_group = request.get("tool_group", "default")
            config_file = request.get("config_file")
            task = request.get("task")
            additional_args = request.get("additional_args")

            if not agent_type:
                return {
                    "success": False,
                    "error": {
                        "code": "MISSING_AGENT_TYPE",
                        "message": "agent_type is required",
                    },
                }
            if not working_dir:
                return {
                    "success": False,
                    "error": {
                        "code": "MISSING_WORKING_DIR",
                        "message": "working_dir is required",
                    },
                }

            agent_info = agent_manager.create_agent(
                agent_type=agent_type,
                working_dir=working_dir,
                name=name,
                llm_group=llm_group,
                tool_group=tool_group,
                config_file=config_file,
                task=task,
                additional_args=additional_args,
            )

            return {"success": True, "data": agent_info}
        except ValueError as e:
            return {
                "success": False,
                "error": {"code": "INVALID_ARGUMENT", "message": str(e)},
            }
        except RuntimeError as e:
            return {
                "success": False,
                "error": {"code": "START_FAILED", "message": str(e)},
            }
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    # HTTP API：获取 Agent 列表
    @app.get("/api/agents")
    async def get_agents() -> Dict[str, Any]:
        """获取 Agent 列表。"""
        try:
            agents = agent_manager.get_agent_list()
            return {"success": True, "data": agents}
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    # HTTP API：停止 Agent
    @app.delete("/api/agents/{agent_id}/stop")
    async def stop_agent(agent_id: str) -> Dict[str, Any]:
        """停止 Agent。"""
        try:
            result = agent_manager.stop_agent(agent_id)
            return {"success": True, "data": result}
        except KeyError as e:
            return {
                "success": False,
                "error": {"code": "AGENT_NOT_FOUND", "message": str(e)},
            }
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    # HTTP API：删除 Agent
    @app.delete("/api/agents/{agent_id}")
    async def delete_agent(agent_id: str) -> Dict[str, Any]:
        """删除 Agent。"""
        try:
            result = agent_manager.delete_agent(agent_id)
            return {"success": True, "data": result}
        except KeyError as e:
            return {
                "success": False,
                "error": {"code": "AGENT_NOT_FOUND", "message": str(e)},
            }
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    # HTTP API：获取可恢复的 session 列表
    @app.get("/api/agents/{agent_id}/sessions")
    async def list_agent_sessions(agent_id: str) -> Dict[str, Any]:
        """获取可恢复的 session 列表。"""
        try:
            agent_info = agent_manager.get_agent_info(agent_id)
            if agent_info is None:
                return {
                    "success": False,
                    "error": {"code": "AGENT_NOT_FOUND", "message": "Agent not found"},
                }

            # 代理到 Agent 进程的 /sessions 接口
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"http://127.0.0.1:{agent_info.port}/sessions"
                )
                return response.json()
        except KeyError as e:
            return {
                "success": False,
                "error": {"code": "AGENT_NOT_FOUND", "message": str(e)},
            }
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    # HTTP API：恢复指定的 session
    @app.post("/api/agents/{agent_id}/sessions")
    async def restore_agent_session(
        agent_id: str, request: Dict[str, Any]
    ) -> Dict[str, Any]:
        """恢复指定的 session。"""
        try:
            agent_info = agent_manager.get_agent_info(agent_id)
            if agent_info is None:
                return {
                    "success": False,
                    "error": {"code": "AGENT_NOT_FOUND", "message": "Agent not found"},
                }

            # 代理到 Agent 进程的 /sessions 接口
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"http://127.0.0.1:{agent_info.port}/sessions", json=request
                )
                return response.json()
        except KeyError as e:
            return {
                "success": False,
                "error": {"code": "AGENT_NOT_FOUND", "message": str(e)},
            }
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    # HTTP API：获取补全列表
    @app.get("/api/completions/{agent_id}")
    async def get_completions(agent_id: str) -> Dict[str, Any]:
        """获取所有可用补全项（不包括文件）。"""
        try:
            from jarvis.jarvis_utils.config import get_replace_map
            from jarvis.jarvis_utils.tag import ot
            from jarvis.jarvis_utils.input import BUILTIN_COMMANDS
            import os

            # 获取 Agent 的工作目录
            agent = agent_manager.get_agent(agent_id)
            if not agent:
                return {
                    "success": False,
                    "error": {"code": "AGENT_NOT_FOUND", "message": "Agent not found"},
                }
            working_dir = agent.working_dir
            os.chdir(working_dir)

            all_completions = []

            # 添加 replace_map
            try:
                replace_map = get_replace_map()
                for tag, info in replace_map.items():
                    desc = (
                        info.get("description", tag) + "(Append)"
                        if info.get("append")
                        else "(Replace)"
                    )
                    all_completions.append(
                        {
                            "type": "replace",
                            "value": ot(tag),
                            "display": tag,
                            "description": desc,
                        }
                    )
            except Exception as e:
                print(f"[COMPLETIONS] Failed to load replace_map: {e}")

            # 添加内置命令
            for cmd, desc in BUILTIN_COMMANDS:
                all_completions.append(
                    {
                        "type": "command",
                        "value": ot(cmd),
                        "display": cmd,
                        "description": desc,
                    }
                )

            # 添加规则
            try:
                from jarvis.jarvis_agent.rules_manager import RulesManager

                rules_manager = RulesManager(working_dir)
                available_rules = rules_manager.get_all_available_rule_names()

                # 内置规则
                if available_rules.get("builtin"):
                    for rule_name in available_rules["builtin"]:
                        all_completions.append(
                            {
                                "type": "rule",
                                "value": f"<rule:{rule_name}>",
                                "display": rule_name,
                                "description": "📚 内置规则",
                            }
                        )

                # 文件规则
                if available_rules.get("files"):
                    for rule_name in available_rules["files"]:
                        all_completions.append(
                            {
                                "type": "rule",
                                "value": f"<rule:{rule_name}>",
                                "display": rule_name,
                                "description": "📄 文件规则",
                            }
                        )

                # YAML 规则
                if available_rules.get("yaml"):
                    for rule_name in available_rules["yaml"]:
                        all_completions.append(
                            {
                                "type": "rule",
                                "value": f"<rule:{rule_name}>",
                                "display": rule_name,
                                "description": "📝 YAML 规则",
                            }
                        )
            except Exception as e:
                print(f"[COMPLETIONS] Failed to load rules: {e}")

            return {"success": True, "data": all_completions}
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    @app.get("/api/directories")
    async def list_directories(path: str = "") -> Dict[str, Any]:
        """获取指定路径下的目录列表。

        Args:
            path: 目录路径，默认为用户主目录

        Returns:
            {
                "success": True,
                "data": {
                    "current_path": "/path/to/dir",
                    "parent_path": "/path/to",  # 如果存在
                    "directories": [
                        {"name": "dir1", "path": "/path/to/dir/dir1"},
                        ...
                    ]
                }
            }
        """
        import pathlib

        try:
            # 解析路径，如果为空则使用用户主目录
            if not path or path == "~":
                target_path = pathlib.Path.home()
            else:
                target_path = pathlib.Path(path).expanduser()

            # 规范化为绝对路径
            target_path = target_path.resolve()

            # 检查路径是否存在且是目录
            if not target_path.exists():
                return {
                    "success": False,
                    "error": {
                        "code": "NOT_FOUND",
                        "message": f"Path does not exist: {path}",
                    },
                }

            if not target_path.is_dir():
                return {
                    "success": False,
                    "error": {
                        "code": "NOT_A_DIRECTORY",
                        "message": f"Path is not a directory: {path}",
                    },
                }

            # 获取父目录路径（如果存在）
            parent_path = None
            if target_path.parent != target_path:  # 不是根目录
                parent_path = str(target_path.parent)

            # 获取子目录列表
            directories = []
            try:
                for entry in target_path.iterdir():
                    # 只返回目录
                    if entry.is_dir():
                        # 过滤隐藏文件（以 . 开头）
                        if not entry.name.startswith("."):
                            directories.append(
                                {
                                    "name": entry.name,
                                    "path": str(entry),
                                }
                            )
                # 按名称排序
                directories.sort(key=lambda x: x["name"])
            except PermissionError:
                # 忽略权限错误，返回空列表
                pass

            return {
                "success": True,
                "data": {
                    "current_path": str(target_path),
                    "parent_path": parent_path,
                    "directories": directories,
                },
            }
        except PermissionError:
            return {
                "success": False,
                "error": {"code": "PERMISSION_DENIED", "message": "Permission denied"},
            }
        except Exception as e:
            return {
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    return app


def run(
    host: str = "127.0.0.1", port: int = 8000, password: Optional[str] = None
) -> None:
    """本地启动入口。"""

    import uvicorn

    from jarvis.jarvis_utils.config import GLOBAL_CONFIG_DATA

    # 如果提供了密码参数，更新 gateway_auth 配置
    if password:
        if "gateway_auth" not in GLOBAL_CONFIG_DATA:
            GLOBAL_CONFIG_DATA["gateway_auth"] = {}
        GLOBAL_CONFIG_DATA["gateway_auth"]["password"] = password
        GLOBAL_CONFIG_DATA["gateway_auth"]["enable"] = True
        GLOBAL_CONFIG_DATA["gateway_auth"]["allow_unset"] = False

    uvicorn.run(create_app(), host=host, port=port)



def _normalize_auth_payload(payload: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None
    return {
        "password": payload.get("password"),
    }


def _extract_auth_from_headers(websocket: WebSocket) -> Optional[Dict[str, Any]]:
    password = websocket.headers.get("x-jarvis-password")
    if not password:
        return None
    return {"password": password}


def _build_sender(websocket: WebSocket, loop: asyncio.AbstractEventLoop):
    def _sender(message: Dict[str, Any]) -> None:
        asyncio.run_coroutine_threadsafe(websocket.send_json(message), loop)

    return _sender


async def _await_auth_message(
    websocket: WebSocket, gateway: WebGateway
) -> Tuple[Optional[Dict[str, Any]], bool, Optional[str]]:
    try:
        message = await asyncio.wait_for(websocket.receive_json(), timeout=10)
    except Exception:
        return None, False, "gateway auth missing"
    if not isinstance(message, dict) or message.get("type") != "auth":
        return None, False, "gateway auth missing"
    payload = _normalize_auth_payload(message.get("payload") or {})
    authorized, reason = gateway._check_auth(payload)
    return payload, authorized, reason


async def _send_error(websocket: WebSocket, code: str, message: str) -> None:
    error_msg = {"type": "error", "payload": {"code": code, "message": message}}
    await websocket.send_json(error_msg)
