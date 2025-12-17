# -*- coding: utf-8 -*-
"""
WebSocketOutputSink: 将 PrettyOutput 的输出事件通过 WebBridge 广播给前端（WebSocket 客户端）

用法：
- 在 Web 模式启动时，注册该 Sink：
    from jarvis.jarvis_utils.output import PrettyOutput
    from jarvis.jarvis_agent.web_output_sink import WebSocketOutputSink
    PrettyOutput.add_sink(WebSocketOutputSink())

- Web 端收到的消息结构：
    {
      "type": "output",
      "payload": {
        "text": "...",
        "output_type": "INFO" | "ERROR" | ...,
        "timestamp": true/false,
        "lang": "markdown" | "python" | ... | null,
        "traceback": false,
        "section": null | "标题",
        "context": { ... } | null
      }
    }
"""

from __future__ import annotations

from typing import Any


from jarvis.jarvis_agent.web_bridge import WebBridge
from jarvis.jarvis_utils.output import OutputEvent
from jarvis.jarvis_utils.output import OutputSink


class WebSocketOutputSink(OutputSink):
    """将输出事件广播到 WebSocket 前端的 OutputSink 实现。"""

    def emit(self, event: OutputEvent) -> None:
        try:
            payload: dict[str, Any] = {
                "type": "output",
                "payload": {
                    "text": event.text,
                    "output_type": event.output_type.value,
                    "timestamp": bool(event.timestamp),
                    "lang": event.lang,
                    "traceback": bool(event.traceback),
                    "section": event.section,
                    "context": event.context,
                },
            }
            WebBridge.instance().broadcast(payload)
        except Exception:
            # 广播过程中的异常不应影响其他输出后端
            pass
