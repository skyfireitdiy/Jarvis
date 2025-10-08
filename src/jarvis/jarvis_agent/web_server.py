# -*- coding: utf-8 -*-
"""
基于 FastAPI 的 Web 服务：
- GET /         返回简易网页（含JS，连接 WebSocket，展示输出，处理输入/确认）
- WS  /ws       建立双向通信：服务端通过 WebBridge 广播输出与输入请求；客户端上行提交 user_input/confirm_response 或 run_task
- WS  /stdio    独立通道：专门接收标准输出/错误（sys.stdout/sys.stderr）重定向的流式文本

集成方式（在 --web 模式下）：
- 注册 WebSocketOutputSink，将 PrettyOutput 事件广播到前端
- 注入 web_multiline_input 与 web_user_confirm 到 Agent，使输入与确认经由浏览器完成
- 启动本服务，前端通过页面与 Agent 交互
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import atexit
from pathlib import Path
from typing import Any, Dict, Callable, Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from jarvis.jarvis_agent.web_bridge import WebBridge
from jarvis.jarvis_utils.globals import set_interrupt, console
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
        # 上下布局 + xterm.js 终端显示输出；底部输入面板
        return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Jarvis Web</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link rel="stylesheet" href="https://unpkg.com/xterm@5.3.0/css/xterm.css" />
  <style>
    html, body { height: 100%; }
    body {
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column; /* 上下布局：上输出，下输入 */
      background: #000;
      color: #eee;
    }
    /* 顶部：终端输出区域（占满剩余空间） */
    #terminal {
      flex: 1;
      background: #000; /* 终端背景 */
      overflow: hidden;
    }
    /* 底部：输入区域（固定高度） */
    #input-panel {
      display: flex;
      flex-direction: column;
      gap: 8px;
      padding: 10px;
      background: #0b0b0b;
      border-top: 1px solid #222;
    }
    #tip { color: #9aa0a6; font-size: 13px; }
    textarea#input {
      width: 100%;
      height: 140px;
      background: #0f0f0f;
      color: #e5e7eb;
      border: 1px solid #333;
      border-radius: 6px;
      padding: 8px;
      resize: vertical;
      outline: none;
    }
    #actions {
      display: flex;
      gap: 10px;
      align-items: center;
    }
    button {
      padding: 8px 12px;
      background: #1f2937;
      color: #e5e7eb;
      border: 1px solid #374151;
      border-radius: 6px;
      cursor: pointer;
    }
    button:hover { background: #374151; }
  </style>
</head>
<body>
  <div id="terminal"></div>

  <div id="input-panel">
    <div id="tip">输入任务或在请求时回复（Ctrl+Enter 提交）</div>
    <textarea id="input" placeholder="在此输入..."></textarea>
    <div id="actions">
      <button id="send">发送为新任务</button>
      <button id="clear">清空输出</button>
      <button id="interrupt">干预</button>
    </div>
  </div>

  <!-- xterm.js 与 fit 插件 -->
  <script src="https://unpkg.com/xterm@5.3.0/lib/xterm.js"></script>
  <script src="https://unpkg.com/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.js"></script>

  <script>
    // 初始化 xterm 终端
    const term = new Terminal({
      convertEol: true,
      fontSize: 13,
      fontFamily: '"FiraCode Nerd Font", "JetBrainsMono NF", "Fira Code", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
      theme: {
        background: '#000000',
        foreground: '#e5e7eb',
        cursor: '#e5e7eb',
      }
    });
    const fitAddon = new FitAddon.FitAddon();
    term.loadAddon(fitAddon);
    term.open(document.getElementById('terminal'));
    // 捕获前端键入并透传到后端作为 STDIN（与后端 sys.stdin 对接）
    try {
      term.onData((data) => {
        try {
          if (wsStd && wsStd.readyState === WebSocket.OPEN) {
            wsStd.send(JSON.stringify({ type: 'stdin', data }));
          }
        } catch (e) {}
      });
    } catch (e) {}

    function fitTerminal() {
      try { 
        fitAddon.fit();
        // 将终端尺寸通知后端（用于动态调整TTY宽度/高度）
        if (typeof wsCtl !== 'undefined' && wsCtl && wsCtl.readyState === WebSocket.OPEN) {
          try {
            wsCtl.send(JSON.stringify({ type: 'resize', cols: term.cols || 200, rows: term.rows || 24 }));
          } catch (e) {}
        }
      } catch (e) {}
    }
    fitTerminal();
    window.addEventListener('resize', fitTerminal);

    // 输出辅助
    function writeLine(text) {
      const lines = (text ?? '').toString().split('\\n');
      for (const ln of lines) term.writeln(ln);
    }
    function write(text) {
      term.write((text ?? '').toString());
    }

    // 元素引用
    const tip = document.getElementById('tip');
    const input = document.getElementById('input');
    const btnSend = document.getElementById('send');
    const btnClear = document.getElementById('clear');
    const btnInterrupt = document.getElementById('interrupt');
    // 输入可用性开关：Agent 未请求输入时禁用输入框（但允许通过按钮发送空任务）
    let inputEnabled = false;
    function setInputEnabled(flag) {
      inputEnabled = !!flag;
      try {
        input.disabled = !inputEnabled;
        // 根据可用状态更新占位提示
        input.placeholder = inputEnabled ? '在此输入...' : 'Agent正在运行';
      } catch (e) {}
    }
    // 初始化（未请求输入时禁用输入框）
    setInputEnabled(false);
    try { btnSend.textContent = '发送为新任务'; } catch (e) {}

    // WebSocket 通道：主通道与 STDIO 通道
    const wsProto = (location.protocol === 'https:') ? 'wss' : 'ws';
    const ws = new WebSocket(wsProto + '://' + location.host + '/ws');
    const wsStd = new WebSocket(wsProto + '://' + location.host + '/stdio');
    const wsCtl = new WebSocket(wsProto + '://' + location.host + '/control');
    let ctlReady = false;

    ws.onopen = () => {
      writeLine('WebSocket 已连接');
      // 连接成功后，允许直接输入首条任务
      try { 
        setInputEnabled(true); 
        // 连接成功后，优先聚焦终端以便直接通过 xterm 进行交互
        if (typeof term !== 'undefined' && term) {
          try { term.focus(); } catch (e) {}
        }
      } catch (e) {}
      fitTerminal();
    };
    ws.onclose = () => { writeLine('WebSocket 已关闭'); };
    ws.onerror = (e) => { writeLine('WebSocket 错误: ' + e); };

    wsStd.onopen = () => { writeLine('STDIO 通道已连接'); };
    wsStd.onclose = () => { writeLine('STDIO 通道已关闭'); };
    wsStd.onerror = (e) => { writeLine('STDIO 通道错误: ' + e); };
    wsCtl.onopen = () => { 
      writeLine('控制通道已连接'); 
      ctlReady = true;
      // 初次连接时立即上报当前终端尺寸
      try {
        wsCtl.send(JSON.stringify({ type: 'resize', cols: term.cols || 200, rows: term.rows || 24 }));
      } catch (e) {}
    };
    wsCtl.onclose = () => { 
      writeLine('控制通道已关闭'); 
      ctlReady = false;
    };
    wsCtl.onerror = (e) => { writeLine('控制通道错误: ' + e); };

    let pendingInputRequest = null; // {request_id, tip, print_on_empty}
    let pendingConfirmRequest = null; // {request_id, tip, default}

    // 主通道消息
    ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data || '{}');
        if (data.type === 'output') {
          // 忽略通过 Sink 推送的output事件，避免与STDIO通道的输出重复显示
        } else if (data.type === 'input_request') {
          pendingInputRequest = data;
          tip.textContent = '请求输入: ' + (data.tip || '');
          setInputEnabled(true);
          try { btnSend.textContent = '提交输入'; } catch (e) {}
          input.focus();
        } else if (data.type === 'confirm_request') {
          pendingConfirmRequest = data;
          // 确认请求期间不需要文本输入，禁用输入框并更新按钮文字
          setInputEnabled(false);
          try { btnSend.textContent = '确认中…'; } catch (e) {}
          const ok = window.confirm((data.tip || '') + (data.default ? " [Y/n]" : " [y/N]"));
          ws.send(JSON.stringify({
            type: 'confirm_response',
            request_id: data.request_id,
            value: !!ok
          }));
          // 确认已提交，恢复按钮文字为“发送为新任务”
          try { btnSend.textContent = '发送为新任务'; } catch (e) {}
          pendingConfirmRequest = null;
        } else if (data.type === 'agent_idle') {
          // 任务结束提示，并恢复输入状态
          try { writeLine('当前任务已结束'); } catch (e) {}
          try { setInputEnabled(true); btnSend.textContent = '发送为新任务'; input.focus(); } catch (e) {}
        } else if (data.type === 'stdio') {
          // 忽略主通道的 stdio 以避免与独立 STDIO 通道重复显示
        }
      } catch (e) {
writeLine('消息解析失败: ' + e);
      }
    };

    // STDIO 通道消息（原样写入，保留流式体验）
    wsStd.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data || '{}');
        if (data.type === 'stdio') {
          const text = data.text || '';
          write(text);
        }
      } catch (e) {
writeLine('消息解析失败: ' + e);
      }
    };

    // 操作区
    btnSend.onclick = () => {
      const text = input.value || '';
      // 若当前处于输入请求阶段，则按钮行为为“提交输入”（允许空输入）
      if (pendingInputRequest) {
        // 发送前在终端回显用户输入
        try { writeLine('> ' + text); } catch (e) {}
        ws.send(JSON.stringify({
          type: 'user_input',
          request_id: pendingInputRequest.request_id,
          text
        }));
        tip.textContent = '输入已提交';
        pendingInputRequest = null;
        input.value = '';
        // 提交输入后禁用输入区，等待下一次请求或任务结束通知
        setInputEnabled(false);
        try { btnSend.textContent = '发送为新任务'; } catch (e) {}
        fitTerminal();
        return;
      }
      // 否则行为为“发送为新任务”（允许空输入）
      // 发送前在终端回显用户输入
      try { writeLine('> ' + text); } catch (e) {}
      ws.send(JSON.stringify({ type: 'run_task', text }));
      input.value = '';
      // 发送新任务后，直到Agent请求输入前禁用输入区
      setInputEnabled(false);
      try { btnSend.textContent = '发送为新任务'; } catch (e) {}
      fitTerminal();
    };

    btnClear.onclick = () => {
      try {
        if (typeof term.clear === 'function') term.clear();
        else term.write('\\x1bc'); // 清屏/重置
      } catch (e) {
        term.write('\\x1bc');
      }
    };
    // 干预（发送中断信号）
    btnInterrupt.onclick = () => {
      try {
        wsCtl.send(JSON.stringify({ type: 'interrupt' }));
        writeLine('已发送干预（中断）信号');
      } catch (e) {
        writeLine('发送干预失败: ' + e);
      }
    };

    // Ctrl+Enter 提交输入或作为新任务
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && e.ctrlKey) {
        e.preventDefault();
        const text = input.value || '';
        if (pendingInputRequest) {
          // 发送前在终端回显用户输入
          try { writeLine('> ' + text); } catch (e) {}
          ws.send(JSON.stringify({
            type: 'user_input',
            request_id: pendingInputRequest.request_id,
            text
          }));
          tip.textContent = '输入已提交';
          pendingInputRequest = null;
          input.value = '';
          // 提交输入后，直到下一次请求前禁用输入区
          setInputEnabled(false);
          try { btnSend.textContent = '发送为新任务'; } catch (e) {}
        } else {
          // 仅在输入区启用时允许通过 Ctrl+Enter 发送新任务
          if (inputEnabled) {
            // 发送前在终端回显用户输入
            try { writeLine('> ' + text); } catch (e) {}
            ws.send(JSON.stringify({ type: 'run_task', text }));
            input.value = '';
            setInputEnabled(false);
            try { btnSend.textContent = '发送为新任务'; } catch (e) {}
          }
        }
        fitTerminal();
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

def _run_and_notify(agent: Any, text: str) -> None:
    try:
        agent.run(text)
    finally:
        try:
            WebBridge.instance().broadcast({"type": "agent_idle"})
        except Exception:
            pass

def start_web_server(agent: Any, host: str = "127.0.0.1", port: int = 8765) -> None:
    """
    启动Web服务，并将Agent绑定到应用上下文。
    - agent: 现有的 Agent 实例（已完成初始化）
    """
    app = _build_app()
    app.state.agent = agent  # 供 WS 端点调用
    # 兼容传入 Agent 或 AgentManager：
    # - 若传入的是 AgentManager，则在每个任务开始前通过 initialize() 创建全新 Agent
    # - 若传入的是 Agent 实例，则复用该 Agent（旧行为）
    try:
        app.state.agent_manager = agent if hasattr(agent, "initialize") else None
    except Exception:
        app.state.agent_manager = None

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        sender = _make_sender_filtered(queue, allowed_types=["input_request", "confirm_request", "agent_idle"])
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
                    # 允许空输入（空输入也具有语义）
                    text = data.get("text", "")
                    # 在后台线程运行，以避免阻塞事件循环
                    loop = asyncio.get_running_loop()
                    # 若提供了 AgentManager，则为每个任务创建新的 Agent 实例；否则复用现有 Agent
                    try:
                        if getattr(app.state, "agent_manager", None) and hasattr(app.state.agent_manager, "initialize"):
                            new_agent = app.state.agent_manager.initialize()
                            loop.run_in_executor(None, _run_and_notify, new_agent, text)
                        else:
                            loop.run_in_executor(None, _run_and_notify, app.state.agent, text)
                    except Exception:
                        # 回退到旧行为，避免因异常导致无法执行任务
                        try:
                            loop.run_in_executor(None, _run_and_notify, app.state.agent, text)
                        except Exception:
                            pass
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
                # 接收来自前端 STDIN 数据并注入到后端
                msg = await ws.receive_text()
                try:
                    data = json.loads(msg)
                except Exception:
                    continue
                mtype = data.get("type")
                if mtype == "stdin":
                    try:
                        from jarvis.jarvis_agent.stdio_redirect import feed_web_stdin
                        text = data.get("data", "")
                        if isinstance(text, str) and text:
                            feed_web_stdin(text)
                    except Exception:
                        pass
                else:
                    # 忽略未知类型
                    pass
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
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

    @app.websocket("/control")
    async def websocket_control(ws: WebSocket) -> None:
        await ws.accept()
        try:
            while True:
                msg = await ws.receive_text()
                try:
                    data = json.loads(msg)
                except Exception:
                    continue
                mtype = data.get("type")
                if mtype == "interrupt":
                    try:
                        set_interrupt(True)
                        # 可选：发送回执
                        await ws.send_text(json.dumps({"type": "ack", "cmd": "interrupt"}))
                    except Exception:
                        pass
                elif mtype == "resize":
                    # 动态调整后端TTY宽度（影响 PrettyOutput 和基于终端宽度的逻辑）
                    try:
                        cols = int(data.get("cols") or 0)
                        rows = int(data.get("rows") or 0)
                    except Exception:
                        cols = 0
                        rows = 0
                    try:
                        if cols > 0:
                            os.environ["COLUMNS"] = str(cols)
                            try:
                                # 覆盖全局 rich Console 的宽度，便于 PrettyOutput 按照前端列数换行
                                console._width = cols  # type: ignore[attr-defined]
                            except Exception:
                                pass
                        if rows > 0:
                            os.environ["LINES"] = str(rows)
                    except Exception:
                        pass
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            try:
                await ws.close()
            except Exception:
                pass

    PrettyOutput.print(f"启动 Jarvis Web 服务: http://{host}:{port}", OutputType.SUCCESS)
    # 在服务端进程内也写入并维护 PID 文件，增强可检测性与可清理性
    try:
        pidfile = Path(os.path.expanduser("~/.jarvis")) / f"jarvis_web_{port}.pid"
        try:
            pidfile.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        try:
            pidfile.write_text(str(os.getpid()), encoding="utf-8")
        except Exception:
            pass
        # 退出时清理 PID 文件
        def _cleanup_pidfile() -> None:
            try:
                pidfile.unlink(missing_ok=True)  # type: ignore[call-arg]
            except Exception:
                pass
        try:
            atexit.register(_cleanup_pidfile)
        except Exception:
            pass
        # 处理 SIGTERM/SIGINT，清理后退出
        def _signal_handler(signum, frame):  # type: ignore[no-untyped-def]
            try:
                _cleanup_pidfile()
            finally:
                try:
                    os._exit(0)
                except Exception:
                    pass
        try:
            signal.signal(signal.SIGTERM, _signal_handler)
        except Exception:
            pass
        try:
            signal.signal(signal.SIGINT, _signal_handler)
        except Exception:
            pass
    except Exception:
        pass
    uvicorn.run(app, host=host, port=port)
