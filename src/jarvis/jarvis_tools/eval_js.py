# -*- coding: utf-8 -*-
"""在前端浏览器中执行 JavaScript 并取回结果的工具。"""

from __future__ import annotations

import json
from typing import Any
from typing import Dict


class eval_js:
    """将一段 JavaScript 下发到前端浏览器执行，并返回执行结果。

    仅在 Web 网关模式下可用；CLI 模式下会返回明确的错误提示。
    """

    name = "eval_js"
    description = """将一段 JavaScript 发送到前端浏览器执行，并返回执行结果。

**用途**：
- 读取/操作前端页面状态（document、window、Vue 实例、DOM 等）
- 调试前端行为、验证前端逻辑
- 自动控制目标前端

**用法**：
- code 中可直接写 JS，支持 async/await；返回值会被回传
- 例：`return document.title`、`return window.location.href`
- 例：`const el = document.querySelector('#app'); return el.innerHTML.length`

**限制**：
- 仅在 Web 网关模式下可用
- 默认超时 30 秒，结果大小限制 1MB
- 返回值需可序列化（DOM/函数/循环引用会降级为字符串）"""

    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "要执行的 JavaScript 代码，支持 async/await，返回值会被回传",
            },
            "timeout": {
                "type": "number",
                "description": "等待前端执行结果的超时时间（秒），默认 30",
            },
            "target": {
                "type": "string",
                "description": (
                    "目标前端：默认 current（当前活跃前端）；"
                    "也可指定具体 session_id 或 all（广播到所有前端）"
                ),
            },
        },
        "required": ["code"],
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具。"""
        try:
            code = args.get("code")
            if not code or not str(code).strip():
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "缺少或为空：code（要执行的 JavaScript 代码）",
                }

            timeout = args.get("timeout", 30)
            try:
                timeout = float(timeout)
            except (TypeError, ValueError):
                timeout = 30.0

            target = args.get("target") or "current"

            from jarvis.jarvis_gateway.manager import get_current_gateway

            gateway = get_current_gateway()
            request_frontend_js = getattr(gateway, "request_frontend_js", None)
            if not callable(request_frontend_js):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "eval_js 仅在 Web 网关模式下可用",
                }

            result = request_frontend_js(
                str(code), timeout=timeout, target=str(target)
            )

            if not isinstance(result, dict):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"前端返回了非预期结果: {result!r}",
                }

            if not result.get("success"):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": str(result.get("error") or "前端执行失败"),
                }

            value = result.get("result")
            if isinstance(value, str):
                stdout = value
            else:
                stdout = json.dumps(value, ensure_ascii=False, indent=2)
            return {"success": True, "stdout": stdout, "stderr": ""}

        except Exception as e:
            return {"success": False, "stdout": "", "stderr": str(e)}
