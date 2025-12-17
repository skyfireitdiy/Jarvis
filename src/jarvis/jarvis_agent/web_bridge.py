# -*- coding: utf-8 -*-
"""
WebBridge: WebSocket 交互桥
- 提供线程安全的广播能力（后续由 WebSocket 服务注册发送函数）
- 提供阻塞式的多行输入与确认请求（通过 request_* 发起请求，等待浏览器端响应）
- 适配 Agent 的输入注入接口：web_multiline_input / web_user_confirm
- 事件约定（发往前端，均为 JSON 对象）:
  * {"type":"input_request","mode":"multiline","tip": "...","print_on_empty": true/false,"request_id":"..."}
  * {"type":"confirm_request","tip":"...","default": true/false,"request_id":"..."}
  后续输出事件由输出Sink负责（使用 PrettyOutput.add_sink 接入），不在本桥内实现。
- 事件约定（来自前端）:
  * {"type":"user_input","request_id":"...","text":"..."}
  * {"type":"confirm_response","request_id":"...","value": true/false}
"""

from __future__ import annotations

import threading
import uuid
from queue import Empty, Queue
from typing import Any
from typing import Callable
from typing import Dict
from typing import Optional
from typing import Set

DEFAULT_WAIT_TIMEOUT = None  # 阻塞等待直到收到响应（可按需改为秒数）


class WebBridge:
    """
    线程安全的 WebSocket 交互桥。
    - 维护一组客户端发送函数（由Web服务注册），用于广播事件
    - 维护挂起的输入/确认请求队列，按 request_id 匹配响应
    """

    _instance_lock = threading.Lock()
    _instance: Optional["WebBridge"] = None

    def __init__(self) -> None:
        self._clients: Set[Callable[[Dict[str, Any]], None]] = set()
        self._clients_lock = threading.Lock()

        # 按 request_id 等待的阻塞队列
        self._pending_inputs: Dict[str, Queue[Any]] = {}
        self._pending_confirms: Dict[str, Queue[Any]] = {}
        self._pending_lock = threading.Lock()

    @classmethod
    def instance(cls) -> "WebBridge":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = WebBridge()
            return cls._instance

    # ---------------------------
    # 客户端管理与广播
    # ---------------------------
    def add_client(self, sender: Callable[[Dict[str, Any]], None]) -> None:
        """
        注册一个客户端发送函数。发送函数需接受一个 dict，并自行完成异步发送。
        例如在 FastAPI/WS 中包装成 enqueue 到事件循环的任务。
        """
        with self._clients_lock:
            self._clients.add(sender)

    def remove_client(self, sender: Callable[[Dict[str, Any]], None]) -> None:
        with self._clients_lock:
            if sender in self._clients:
                self._clients.remove(sender)

    def broadcast(self, payload: Dict[str, Any]) -> None:
        """
        广播一条消息给所有客户端。失败的客户端不影响其他客户端。
        """
        with self._clients_lock:
            targets = list(self._clients)
        for send in targets:
            try:
                send(payload)
            except Exception:
                # 静默忽略单个客户端的发送异常
                pass

    # ---------------------------
    # 输入/确认 请求-响应 管理
    # ---------------------------
    def request_multiline_input(
        self,
        tip: str,
        print_on_empty: bool = True,
        timeout: Optional[float] = DEFAULT_WAIT_TIMEOUT,
    ) -> str:
        """
        发起一个多行输入请求并阻塞等待浏览器返回。
        返回用户输入的文本（可能为空字符串，表示取消）。
        """
        req_id = uuid.uuid4().hex
        q: Queue[Any] = Queue(maxsize=1)
        with self._pending_lock:
            self._pending_inputs[req_id] = q

        self.broadcast(
            {
                "type": "input_request",
                "mode": "multiline",
                "tip": tip,
                "print_on_empty": bool(print_on_empty),
                "request_id": req_id,
            }
        )

        try:
            if timeout is None:
                result = q.get()  # 阻塞直到有结果
            else:
                result = q.get(timeout=timeout)
        except Empty:
            result = ""  # 超时回退为空
        finally:
            with self._pending_lock:
                self._pending_inputs.pop(req_id, None)

        # 规范化为字符串
        return str(result or "")

    def request_confirm(
        self,
        tip: str,
        default: bool = True,
        timeout: Optional[float] = DEFAULT_WAIT_TIMEOUT,
    ) -> bool:
        """
        发起一个确认请求并阻塞等待浏览器返回。
        返回 True/False，若超时则回退为 default。
        """
        req_id = uuid.uuid4().hex
        q: Queue[Any] = Queue(maxsize=1)
        with self._pending_lock:
            self._pending_confirms[req_id] = q

        self.broadcast(
            {
                "type": "confirm_request",
                "tip": tip,
                "default": bool(default),
                "request_id": req_id,
            }
        )

        try:
            if timeout is None:
                result = q.get()
            else:
                result = q.get(timeout=timeout)
        except Empty:
            result = default
        finally:
            with self._pending_lock:
                self._pending_confirms.pop(req_id, None)

        return bool(result)

    # ---------------------------
    # 由 Web 服务回调：注入用户响应
    # ---------------------------
    def post_user_input(self, request_id: str, text: str) -> None:
        """
        注入浏览器端的多行输入响应。
        """
        with self._pending_lock:
            q = self._pending_inputs.get(request_id)
        if q:
            try:
                q.put_nowait(text)
            except Exception:
                pass

    def post_confirm(self, request_id: str, value: bool) -> None:
        """
        注入浏览器端的确认响应。
        """
        with self._pending_lock:
            q = self._pending_confirms.get(request_id)
        if q:
            try:
                q.put_nowait(bool(value))
            except Exception:
                pass


# ---------------------------
# 供 Agent 注入的输入函数
# ---------------------------
def web_multiline_input(tip: str, print_on_empty: bool = True) -> str:
    """
    适配 Agent.multiline_inputer 签名的多行输入函数。
    在 Web 模式下被注入到 Agent，转由浏览器端输入。
    """
    return WebBridge.instance().request_multiline_input(tip, print_on_empty)


def web_user_confirm(tip: str, default: bool = True) -> bool:
    """
    适配 Agent.confirm_callback 签名的确认函数。
    在 Web 模式下被注入到 Agent，转由浏览器端确认。
    """
    return WebBridge.instance().request_confirm(tip, default)
