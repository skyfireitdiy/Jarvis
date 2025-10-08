# -*- coding: utf-8 -*-
"""
基于 FastAPI 的 Web 服务：
- GET /         返回简易网页（含JS，连接 WebSocket，展示输出，处理输入/确认）
- WS  /ws       建立双向通信：服务端通过 WebBridge 广播输出与输入请求；客户端上行提交 user_input/confirm_response 或 run_task

集成方式（在 --web 模式下）：
- 注册 WebSocketOutputSink，将 PrettyOutput 事件广播到前端
- 注入 web_multiline_input 与 web_user_confirm 到 Agent，使输入与确认经由浏览器完成
- 启动本服务，前端通过页面与 Agent 交互
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Callable, Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from jarvis.jarvis_agent.web_bridge import WebBridge
from jarvis.jarvis_utils.output import PrettyOutput, OutputType

# ---------------------------
# 应用与页面
# ---------------------------
def _build_app() -> FastAPI:
    app = FastAPI(title="Jarvis Web")

    # 允许本地简单跨域调试
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        # 简单HTML：左侧输出区，右侧输入区；WS连接与事件处理
        return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Jarvis Web</title>
  <style>
    body { font-family: sans-serif; margin: 0; padding: 0; display: flex; height: 100vh; }
    #left { flex: 2; background: #111; color: #eee; padding: 10px; overflow-y: auto; }
    #right { flex: 1; display: flex; flex-direction: column; padding: 10px; gap: 8px; }
    .msg { white-space: pre-wrap; border-bottom: 1px solid #333; padding: 6px 0; }
    .system { color: #83c5be; }
    .error { color: #ef4444; }
    .info { color: #60a5fa; }
    .user { color: #34d399; }
    .tool { color: #f59e0b; }
    .success { color: #22c55e; }
    .warning { color: #fbbf24; }
    textarea { width: 100%; height: 160px; }
    button { padding: 8px 12px; }
    #tip { color: #999; }
  </style>
</head>
<body>
  <div id="left"></div>
  <div id="right">
    <div id="tip">输入任务或在请求时回复</div>
    <textarea id="input"></textarea>
    <div>
      <button id="send">发送为新任务</button>
      <button id="clear">清空输出</button>
    </div>
  </div>

  <script>
    const left = document.getElementById('left');
    const tip = document.getElementById('tip');
    const input = document.getElementById('input');
    const btnSend = document.getElementById('send');
    const btnClear = document.getElementById('clear');

    function appendMsg(text, cls='') {
      const div = document.createElement('div');
      div.className = 'msg ' + cls;
      div.textContent = text;
      left.appendChild(div);
      left.scrollTop = left.scrollHeight;
    }

    let pendingInputRequest = null; // {request_id, tip, print_on_empty}
    let pendingConfirmRequest = null; // {request_id, tip, default}

    const wsProto = (location.protocol === 'https:') ? 'wss' : 'ws';
    const ws = new WebSocket(wsProto + '://' + location.host + '/ws');
    const wsStd = new WebSocket(wsProto + '://' + location.host + '/stdio');

    ws.onopen = () => {
      appendMsg('WebSocket 已连接', 'info');
    };
    ws.onclose = () => {
      appendMsg('WebSocket 已关闭', 'warning');
    };
    ws.onerror = (e) => {
      appendMsg('WebSocket 错误: ' + e, 'error');
    };
    wsStd.onopen = () => {
      appendMsg('STDIO 通道已连接', 'info');
    };
    wsStd.onclose = () => {
      appendMsg('STDIO 通道已关闭', 'warning');
    };
    wsStd.onerror = (e) => {
      appendMsg('STDIO 通道错误: ' + e, 'error');
    };

    ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data);
        if (data.type === 'output') {
          const p = data.payload || {};
          const ot = (p.output_type || '').toLowerCase();
          let cls = '';
          if (ot === 'error') cls = 'error';
          else if (ot === 'info') cls = 'info';
          else if (ot === 'user') cls = 'user';
          else if (ot === 'tool') cls = 'tool';
          else if (ot === 'success') cls = 'success';
          else if (ot === 'warning') cls = 'warning';
          else cls = 'system';
          const header = `[${p.output_type||'SYSTEM'}]`;
          const section = p.section ? ('[SECTION] ' + p.section + '\\n') : '';
          appendMsg(section + header + ' ' + (p.text || ''), cls);
        } else if (data.type === 'input_request') {
          pendingInputRequest = data;
          tip.textContent = '请求输入: ' + (data.tip || '');
          // 聚焦输入框
          input.focus();
        } else if (data.type === 'confirm_request') {
          pendingConfirmRequest = data;
          const ok = window.confirm(data.tip + (data.default ? " [Y/n]" : " [y/N]"));
          ws.send(JSON.stringify({
            type: 'confirm_response',
            request_id: data.request_id,
            value: !!ok
          }));
          pendingConfirmRequest = null;
        } else if (data.type === 'stdio') {
          const stream = (data.stream || '').toLowerCase();
          const text = data.text || '';
          const cls = stream === 'stderr' ? 'error' : 'info';
          appendMsg(`[STDIO:${stream||'stdout'}] ` + text, cls);
        }
      } catch (e) {
        appendMsg('消息解析失败: ' + e, 'error');
      }
    };
    wsStd.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data);
        if (data.type === 'stdio') {
          const stream = (data.stream || '').toLowerCase();
          const text = data.text || '';
          const cls = stream === 'stderr' ? 'error' : 'info';
          appendMsg(`[STDIO:${stream||'stdout'}] ` + text, cls);
        }
      } catch (e) {
        appendMsg('消息解析失败: ' + e, 'error');
      }
    };

    btnSend.onclick = () => {
      const text = input.value || '';
      if (!text) return;
      // 发送为新任务
      ws.send(JSON.stringify({ type: 'run_task', text }));
      input.value = '';
    };

    btnClear.onclick = () => {
      left.innerHTML = '';
    };

    // 回车+Ctrl 直接作为用户输入响应（当处于等待输入状态）
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && e.ctrlKey) {
        e.preventDefault();
        const text = input.value || '';
        if (pendingInputRequest) {
          ws.send(JSON.stringify({
            type: 'user_input',
            request_id: pendingInputRequest.request_id,
            text
          }));
          tip.textContent = '输入已提交';
          pendingInputRequest = null;
          input.value = '';
        } else {
          // 未处于输入请求时，作为新任务发送
          ws.send(JSON.stringify({ type: 'run_task', text }));
          input.value = '';
        }
      }
    });
  </script>
</body>
</html>
        """

    return app

# ---------------------------
# WebSocket 端点
# ---------------------------
async def _ws_sender_loop(ws: WebSocket, queue: "asyncio.Queue[Dict[str, Any]]") -> None:
    try:
        while True:
            payload = await queue.get()
            await ws.send_text(json.dumps(payload))
    except Exception:
        # 发送循环异常即退出
        pass

def _make_sender(queue: "asyncio.Queue[Dict[str, Any]]") -> Callable[[Dict[str, Any]], None]:
    # 同步函数，供 WebBridge 注册；将消息放入异步队列，由协程发送
    def _sender(payload: Dict[str, Any]) -> None:
        try:
            queue.put_nowait(payload)
        except Exception:
            pass
    return _sender

def _make_sender_filtered(queue: "asyncio.Queue[Dict[str, Any]]", allowed_types: Optional[list[str]] = None) -> Callable[[Dict[str, Any]], None]:
    """
    过滤版 sender：仅将指定类型的payload放入队列（用于单独的STDIO通道）。
    """
    allowed = set(allowed_types or [])
    def _sender(payload: Dict[str, Any]) -> None:
        try:
            ptype = payload.get("type")
            if ptype in allowed:
                queue.put_nowait(payload)
        except Exception:
            pass
    return _sender

def start_web_server(agent: Any, host: str = "127.0.0.1", port: int = 8765) -> None:
    """
    启动Web服务，并将Agent绑定到应用上下文。
    - agent: 现有的 Agent 实例（已完成初始化）
    """
    app = _build_app()
    app.state.agent = agent  # 供 WS 端点调用

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        sender = _make_sender(queue)
        bridge = WebBridge.instance()
        bridge.add_client(sender)

        # 后台发送任务
        send_task = asyncio.create_task(_ws_sender_loop(ws, queue))

        # 初始欢迎
        try:
            await ws.send_text(json.dumps({"type": "output", "payload": {"text": "欢迎使用 Jarvis Web", "output_type": "INFO"}}))
        except Exception:
            pass

        try:
            while True:
                msg = await ws.receive_text()
                try:
                    data = json.loads(msg)
                except Exception:
                    continue

                mtype = data.get("type")
                if mtype == "user_input":
                    req_id = data.get("request_id")
                    text = data.get("text", "") or ""
                    if isinstance(req_id, str):
                        bridge.post_user_input(req_id, str(text))
                elif mtype == "confirm_response":
                    req_id = data.get("request_id")
                    val = bool(data.get("value", False))
                    if isinstance(req_id, str):
                        bridge.post_confirm(req_id, val)
                elif mtype == "run_task":
                    text = data.get("text", "") or ""
                    if text.strip():
                        # 在后台线程运行，以避免阻塞事件循环
                        loop = asyncio.get_running_loop()
                        loop.run_in_executor(None, app.state.agent.run, text)
                else:
                    # 兼容未知消息类型
                    pass
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            try:
                bridge.remove_client(sender)
            except Exception:
                pass
            try:
                send_task.cancel()
            except Exception:
                pass

    @app.websocket("/stdio")
    async def websocket_stdio(ws: WebSocket) -> None:
        await ws.accept()
        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        sender = _make_sender_filtered(queue, allowed_types=["stdio"])
        bridge = WebBridge.instance()
        bridge.add_client(sender)
        send_task = asyncio.create_task(_ws_sender_loop(ws, queue))
        try:
            await ws.send_text(json.dumps({"type": "output", "payload": {"text": "STDIO 通道已就绪", "output_type": "INFO"}}))
        except Exception:
            pass
        try:
            while True:
                await asyncio.sleep(60)
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            try:
                bridge.remove_client(sender)
            except Exception:
                pass
            try:
                send_task.cancel()
            except Exception:
                pass

    PrettyOutput.print(f"启动 Jarvis Web 服务: http://{host}:{port}", OutputType.SUCCESS)
    uvicorn.run(app, host=host, port=port)
