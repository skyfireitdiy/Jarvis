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

from jarvis.jarvis_utils.output import PrettyOutput

import asyncio
import atexit
import json
import os
import signal
from pathlib import Path
from typing import Any, Callable, Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from jarvis.jarvis_agent.web_bridge import WebBridge
from jarvis.jarvis_utils.globals import console, set_interrupt


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
          // 优先将键入数据发送到交互式终端（PTY）通道；若未就绪则回退到 STDIN 重定向通道
          if (typeof wsTerm !== 'undefined' && wsTerm && wsTerm.readyState === WebSocket.OPEN) {
            wsTerm.send(JSON.stringify({ type: 'stdin', data }));
          } else if (wsStd && wsStd.readyState === WebSocket.OPEN) {
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
        // 同步调整交互式终端（PTY）窗口大小
        if (typeof wsTerm !== 'undefined' && wsTerm && wsTerm.readyState === WebSocket.OPEN) {
          try {
            wsTerm.send(JSON.stringify({ type: 'resize', cols: term.cols || 200, rows: term.rows || 24 }));
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

    // WebSocket 通道：STDIO、控制与交互式终端
    const wsProto = (location.protocol === 'https:') ? 'wss' : 'ws';
    const wsStd = new WebSocket(wsProto + '://' + location.host + '/stdio');
    const wsCtl = new WebSocket(wsProto + '://' + location.host + '/control');
    // 交互式终端（PTY）通道：用于真正的交互式命令
    const wsTerm = new WebSocket(wsProto + '://' + location.host + '/terminal');
    let ctlReady = false;


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
    
    // 终端（PTY）通道
    wsTerm.onopen = () => { 
      writeLine('终端通道已连接'); 
      // 初次连接时上报当前终端尺寸
      try {
        wsTerm.send(JSON.stringify({ type: 'resize', cols: term.cols || 200, rows: term.rows || 24 }));
      } catch (e) {}
    };
    wsTerm.onclose = () => { writeLine('终端通道已关闭'); };
    wsTerm.onerror = (e) => { writeLine('终端通道错误: ' + e); };
    wsTerm.onmessage = (evt) => {
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



  </script>
</body>
</html>
        """

    return app


# ---------------------------
# WebSocket 端点
# ---------------------------
async def _ws_sender_loop(
    ws: WebSocket, queue: "asyncio.Queue[dict[str, Any]]"
) -> None:
    try:
        while True:
            payload = await queue.get()
            await ws.send_text(json.dumps(payload))
    except Exception:
        # 发送循环异常即退出
        pass


def _make_sender(
    queue: "asyncio.Queue[dict[str, Any]]",
) -> Callable[[dict[str, Any]], None]:
    # 同步函数，供 WebBridge 注册；将消息放入异步队列，由协程发送
    def _sender(payload: dict[str, Any]) -> None:
        try:
            queue.put_nowait(payload)
        except Exception:
            pass

    return _sender


def _make_sender_filtered(
    queue: "asyncio.Queue[dict[str, Any]]", allowed_types: Optional[list[str]] = None
) -> Callable[[dict[str, Any]], None]:
    """
    过滤版 sender：仅将指定类型的payload放入队列（用于单独的STDIO通道）。
    """
    allowed = set(allowed_types or [])

    def _sender(payload: dict[str, Any]) -> None:
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


def start_web_server(
    agent: Any,
    host: str = "127.0.0.1",
    port: int = 8765,
    launch_command: Optional[list[str]] = None,
) -> None:
    """
    启动Web服务，并将Agent绑定到应用上下文。
    - agent: 现有的 Agent 实例（已完成初始化）
    - host: Web 服务主机地址
    - port: Web 服务端口
    - launch_command: 交互式终端启动命令（列表格式，如 ["jvs", "--task", "xxx"]），
                      如果为 None，则从环境变量 web_launch_json 读取
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
    # 存储启动命令到应用状态
    app.state.launch_command = launch_command

    @app.websocket("/stdio")
    async def websocket_stdio(ws: WebSocket) -> None:
        await ws.accept()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        sender = _make_sender_filtered(queue, allowed_types=["stdio"])
        bridge = WebBridge.instance()
        bridge.add_client(sender)
        send_task = asyncio.create_task(_ws_sender_loop(ws, queue))
        try:
            await ws.send_text(
                json.dumps(
                    {
                        "type": "output",
                        "payload": {"text": "STDIO 通道已就绪", "output_type": "INFO"},
                    }
                )
            )
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
                        await ws.send_text(
                            json.dumps({"type": "ack", "cmd": "interrupt"})
                        )
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
                                console._width = cols
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

    # 交互式终端通道：为前端 xterm 提供真实的 PTY 会话，以支持交互式命令
    @app.websocket("/terminal")
    async def websocket_terminal(ws: WebSocket) -> None:
        await ws.accept()
        # 仅在非 Windows 平台提供 PTY 功能
        import sys as _sys

        if _sys.platform == "win32":
            try:
                await ws.send_text(
                    json.dumps(
                        {
                            "type": "output",
                            "payload": {
                                "text": "当前平台不支持交互式终端（PTY）",
                                "output_type": "ERROR",
                            },
                        }
                    )
                )
            except Exception:
                pass
            try:
                await ws.close()
            except Exception:
                pass
            return

        import os as _os

        try:
            import fcntl as _fcntl
            import pty as _pty
            import select as _select
            import struct as _struct
            import termios as _termios
        except Exception:
            try:
                await ws.send_text(
                    json.dumps(
                        {
                            "type": "output",
                            "payload": {
                                "text": "服务端缺少 PTY 相关依赖，无法启动交互式终端",
                                "output_type": "ERROR",
                            },
                        }
                    )
                )
            except Exception:
                pass
            try:
                await ws.close()
            except Exception:
                pass
            return

        def _set_winsize(fd: int, cols: int, rows: int) -> None:
            try:
                if cols > 0 and rows > 0:
                    winsz = _struct.pack("HHHH", rows, cols, 0, 0)
                    _fcntl.ioctl(fd, _termios.TIOCSWINSZ, winsz)
            except Exception:
                # 调整失败不影响主流程
                pass

        # 交互式会话状态与启动函数（优先执行 jvs 命令，失败回退到系统 shell）
        session: dict[str, Optional[int]] = {"pid": None, "master_fd": None}
        last_cols = 0
        last_rows = 0
        # 会话结束后等待用户按回车再重启
        waiting_for_ack = False
        ack_event = asyncio.Event()

        # 在 fork 前获取启动命令（避免在子进程中访问 app.state）
        _launch_cmd = None
        try:
            if hasattr(app.state, "launch_command") and app.state.launch_command:
                _launch_cmd = app.state.launch_command
                # 调试输出
                if _os.environ.get("debug_web_launch_cmd") == "1":
                    PrettyOutput.auto_print(
                        f"🔍 Web服务器: 使用传入的启动命令: {_launch_cmd}"
                    )
            else:
                # 回退到环境变量
                import json as _json

                _cmd_json = _os.environ.get("web_launch_json", "")
                if _cmd_json:
                    try:
                        _launch_cmd = _json.loads(_cmd_json)
                        if _os.environ.get("debug_web_launch_cmd") == "1":
                            PrettyOutput.auto_print(
                                f"🔍 Web服务器: 从环境变量读取启动命令: {_launch_cmd}"
                            )
                    except Exception:
                        _launch_cmd = None
        except Exception:
            _launch_cmd = None

        def _spawn_jvs_session() -> bool:
            nonlocal session, _launch_cmd
            try:
                pid, master_fd = _pty.fork()
                if pid == 0:
                    # 子进程：执行启动命令，失败时回退到系统 shell
                    # 使用在 fork 前获取的命令
                    _argv = _launch_cmd

                    # 如果获取到有效命令，执行它
                    if (
                        _argv
                        and isinstance(_argv, list)
                        and len(_argv) > 0
                        and isinstance(_argv[0], str)
                    ):
                        try:
                            if _os.environ.get("debug_web_launch_cmd") == "1":
                                PrettyOutput.auto_print(f"🔍 子进程: 执行命令: {_argv}")
                            _os.execvp(_argv[0], _argv)
                        except Exception as e:
                            if _os.environ.get("debug_web_launch_cmd") == "1":
                                PrettyOutput.auto_print(f"⚠️ 子进程: 执行命令失败: {e}")
                            pass
                    # 若未配置或执行失败，回退到 /bin/bash 或 /bin/sh
                    try:
                        _os.execvp("/bin/bash", ["/bin/bash"])
                    except Exception:
                        try:
                            _os.execvp("/bin/sh", ["/bin/sh"])
                        except Exception:
                            _os._exit(1)
                else:
                    # 父进程：设置非阻塞模式并记录状态
                    try:
                        _fcntl.fcntl(master_fd, _fcntl.F_SETFL, _os.O_NONBLOCK)
                    except Exception:
                        pass
                    session["pid"] = pid
                    session["master_fd"] = master_fd
                    # 如果已有窗口大小设置，应用到新会话
                    try:
                        if last_cols > 0 and last_rows > 0:
                            winsz = _struct.pack("HHHH", last_rows, last_cols, 0, 0)
                            _fcntl.ioctl(master_fd, _termios.TIOCSWINSZ, winsz)
                    except Exception:
                        pass
                    return True
            except Exception:
                return False

        # 启动首个会话
        ok = _spawn_jvs_session()
        if not ok:
            try:
                await ws.send_text(
                    json.dumps(
                        {
                            "type": "output",
                            "payload": {
                                "text": "启动交互式终端失败",
                                "output_type": "ERROR",
                            },
                        }
                    )
                )
            except Exception:
                pass
            try:
                await ws.close()
            except Exception:
                pass
            return

        async def _tty_read_loop() -> None:
            nonlocal waiting_for_ack
            try:
                while True:
                    fd = session.get("master_fd")
                    if fd is None:
                        # 若正在等待用户按回车确认，则暂不重启
                        if waiting_for_ack:
                            if ack_event.is_set():
                                try:
                                    ack_event.clear()
                                except Exception:
                                    pass
                                waiting_for_ack = False
                                if _spawn_jvs_session():
                                    try:
                                        await ws.send_text(
                                            json.dumps(
                                                {
                                                    "type": "stdio",
                                                    "text": "\r\njvs 会话已重启\r\n",
                                                }
                                            )
                                        )
                                    except Exception:
                                        pass
                                    fd = session.get("master_fd")
                                else:
                                    await asyncio.sleep(0.5)
                                    continue
                            # 等待用户按回车
                            await asyncio.sleep(0.1)
                            continue
                        # 非确认流程：自动重启
                        if _spawn_jvs_session():
                            try:
                                await ws.send_text(
                                    json.dumps(
                                        {
                                            "type": "stdio",
                                            "text": "\r\njvs 会话已重启\r\n",
                                        }
                                    )
                                )
                            except Exception:
                                pass
                            fd = session.get("master_fd")
                        else:
                            await asyncio.sleep(0.5)
                            continue
                    if not isinstance(fd, int):
                        await asyncio.sleep(0.1)
                        continue
                    try:
                        r, _, _ = _select.select([fd], [], [], 0.1)
                    except Exception:
                        r = []
                    if r:
                        try:
                            data = _os.read(fd, 4096)
                        except BlockingIOError:
                            data = b""
                        except Exception:
                            data = b""
                        if data:
                            try:
                                await ws.send_text(
                                    json.dumps(
                                        {
                                            "type": "stdio",
                                            "text": data.decode(errors="ignore"),
                                        }
                                    )
                                )
                            except Exception:
                                break
                        else:
                            # 读取到 EOF，说明子进程已退出；提示后等待用户按回车再重启
                            try:
                                # 关闭旧 master
                                try:
                                    fd2 = session.get("master_fd")
                                    if isinstance(fd2, int):
                                        _os.close(fd2)
                                except Exception:
                                    pass
                                session["master_fd"] = None
                                session["pid"] = None
                                # 标记等待用户回车，并提示
                                waiting_for_ack = True
                                try:
                                    await ws.send_text(
                                        json.dumps(
                                            {
                                                "type": "stdio",
                                                "text": "\r\nAgent 已结束。按回车继续，系统将重启新的 Agent。\r\n> ",
                                            }
                                        )
                                    )
                                except Exception:
                                    pass
                                # 不立即重启，等待顶部 fd None 分支在收到回车后处理
                                await asyncio.sleep(0.1)
                            except Exception:
                                pass
                    # 让出事件循环
                    try:
                        await asyncio.sleep(0)
                    except Exception:
                        pass
            except Exception:
                pass

        # 后台读取任务
        read_task = asyncio.create_task(_tty_read_loop())

        # 初次连接：尝试根据控制通道设定的列数调整终端大小
        try:
            cols = int(_os.environ.get("COLUMNS", "0"))
        except Exception:
            cols = 0
        try:
            rows = int(_os.environ.get("LINES", "0"))
        except Exception:
            rows = 0
        try:
            if cols > 0 and rows > 0:
                _set_winsize(session.get("master_fd") or -1, cols, rows)
                last_cols = cols
                last_rows = rows
        except Exception:
            pass
        # 发送就绪提示
        try:
            await ws.send_text(
                json.dumps(
                    {
                        "type": "output",
                        "payload": {
                            "text": "交互式终端已就绪（PTY）",
                            "output_type": "INFO",
                        },
                    }
                )
            )
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
                if mtype == "stdin":
                    # 前端键入数据：若等待回车，则捕获回车；否则透传到 PTY
                    try:
                        text = data.get("data", "")
                        if isinstance(text, str) and text:
                            if waiting_for_ack:
                                # Enter 键触发继续
                                if "\r" in text or "\n" in text:
                                    try:
                                        ack_event.set()
                                    except Exception:
                                        pass
                                else:
                                    # 非回车输入时轻提示
                                    try:
                                        await ws.send_text(
                                            json.dumps(
                                                {
                                                    "type": "stdio",
                                                    "text": "\r\n按回车继续。\r\n> ",
                                                }
                                            )
                                        )
                                    except Exception:
                                        pass
                            else:
                                # 原样写入（保留控制字符）；前端可按需发送回车
                                _os.write(
                                    session.get("master_fd") or -1,
                                    text.encode(errors="ignore"),
                                )
                    except Exception:
                        pass
                elif mtype == "resize":
                    # 终端窗口大小调整（与控制通道一致，但作用于 PTY）
                    try:
                        cols = int(data.get("cols") or 0)
                    except Exception:
                        cols = 0
                    try:
                        rows = int(data.get("rows") or 0)
                    except Exception:
                        rows = 0
                    try:
                        if cols > 0 and rows > 0:
                            _set_winsize(session.get("master_fd") or -1, cols, rows)
                            last_cols = cols
                            last_rows = rows
                    except Exception:
                        pass
                else:
                    # 忽略未知类型
                    pass
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            # 清理资源
            try:
                read_task.cancel()
            except Exception:
                pass
            try:
                fd3 = session.get("master_fd")
                if isinstance(fd3, int):
                    try:
                        _os.close(fd3)
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                pid_val = session.get("pid")
                if isinstance(pid_val, int):
                    import signal as _signal

                    try:
                        _os.kill(pid_val, _signal.SIGTERM)
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                await ws.close()
            except Exception:
                pass

    PrettyOutput.auto_print(f"✅ 启动 Jarvis Web 服务: http://{host}:{port}")
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
                pidfile.unlink(missing_ok=True)
            except Exception:
                pass

        try:
            atexit.register(_cleanup_pidfile)
        except Exception:
            pass

        # 处理 SIGTERM/SIGINT，清理后退出
        def _signal_handler(signum: int, frame: Any) -> None:
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
    # 配置 uvicorn 日志级别，隐藏连接信息和访问日志
    import logging

    # 禁用 uvicorn 的访问日志
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # 禁用 uvicorn 的常规日志（连接信息等）
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    # 禁用 uvicorn.error 的 INFO 级别日志
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    uvicorn.run(app, host=host, port=port, log_level="warning", access_log=False)
