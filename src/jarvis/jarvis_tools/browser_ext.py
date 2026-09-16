# -*- coding: utf-8 -*-
"""浏览器扩展工具 - 通过用户本地浏览器扩展操作用户真实浏览器中的网页。

与 jarvis-browser(jb) 的区别：jb 在服务端用 Playwright 启动独立浏览器，
本工具驱动的是**用户自己浏览器**中已登录的真实标签页。

依赖用户浏览器安装 Jarvis Browser Bridge 扩展并连接到网关。
"""

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

import jarvis.jarvis_utils.globals as jglobals

logger = logging.getLogger(__name__)


class BrowserExtTool:
    """浏览器扩展工具，操作用户真实浏览器。

    支持的操作（action）：
    1. **list_sessions**: 列出当前在线的浏览器扩展会话
    2. **list_tabs**: 列出指定会话的标签页
    3. **navigate**: 导航到指定 URL
    4. **get_text**: 读取元素文本
    5. **click**: 点击元素
    6. **type**: 向输入框输入文本
    7. **screenshot**: 截图
    8. **activate_tab**: 激活（切换到）指定标签页
    9. **close_tab**: 关闭指定标签页
    10. **new_tab**: 新建标签页
    11. **reload**: 重新加载标签页
    12. **back**: 页面前进后退中的「后退」
    13. **forward**: 页面前进后退中的「前进」
    14. **query**: 查询元素信息（tag/text/value/id/class）
    15. **get_html**: 读取元素 innerHTML
    16. **hover**: 悬停元素
    17. **select**: 选择下拉框选项
    18. **wait_for**: 等待元素出现/消失
    19. **press_key**: 按下键盘按键（可选聚焦指定元素）
    20. **scroll**: 滚动页面或滚动到指定元素
    21. **execute_script**: 在页面中执行任意 JS 代码（高危）
    22. **upload_file**: 上传本地文件到 file input（需 debugger 权限）

    典型流程：先 list_sessions 拿到 session_id，再 list_tabs 拿到 tab_id，
    然后执行 navigate/get_text/click/type/screenshot 等操作。

    **重要提示**：
    - 每次调用只能执行一种操作
    - 操作的是用户真实浏览器，请谨慎执行可能造成不可逆后果的动作
    """

    name = "browser_ext"

    @staticmethod
    def check() -> bool:
        """检查工具是否可用，仅当 Gateway 存在时启用（通过 agent_id 是否设置判断）。"""
        return jglobals.agent_id is not None

    description = """操作用户本地真实浏览器中的网页（通过用户安装的浏览器扩展）。
与 read_webpage 等工具不同：本工具操作的是**用户自己浏览器**里已登录的标签页，可复用登录态与 Cookie。
每次调用只能执行一个 action：
- list_sessions: 列出当前在线的浏览器会话（返回 session_id 列表）。**应先调用此操作获取 session_id**
- list_tabs: 列出指定会话的标签页（返回 tab_id/url/title）。需 session_id
- navigate: 导航到指定 URL。需 session_id、url；可选 tab_id（不传则新建标签页）
- get_text: 读取元素文本。需 session_id、selector；可选 tab_id
- click: 点击元素。需 session_id、selector；可选 tab_id
- type: 向输入框输入文本。需 session_id、selector、text；可选 tab_id
- screenshot: 截图。需 session_id；可选 tab_id
- activate_tab: 激活（切换到）指定标签页。需 session_id、tab_id
- close_tab: 关闭指定标签页。需 session_id、tab_id
- new_tab: 新建标签页。需 session_id；可选 url（不传则 about:blank）
- reload: 重新加载标签页。需 session_id；可选 tab_id（不传则当前活动页）
- back: 后退。需 session_id；可选 tab_id（不传则当前活动页）
- forward: 前进。需 session_id；可选 tab_id（不传则当前活动页）
- query: 查询元素信息。需 session_id、selector；可选 tab_id、all（true 返回全部匹配）
- get_html: 读取元素 innerHTML。需 session_id、selector；可选 tab_id
- hover: 悬停元素。需 session_id、selector；可选 tab_id
- select: 选择下拉框选项。需 session_id、selector、value；可选 tab_id
- wait_for: 等待元素出现/消失。需 session_id、selector；可选 tab_id、state（visible/hidden/attached，默认 visible）、timeout_ms（默认 15000）
- press_key: 按下键盘按键。需 session_id、key（如 Enter/Escape/Tab/ArrowDown）；可选 tab_id、selector（不传则作用于当前焦点元素）
- scroll: 滚动页面。需 session_id；可选 tab_id、selector（滚动到该元素）、x/y（像素偏移，正数向右/向下）、behavior（auto/smooth）
- execute_script: 在页面中执行任意 JS 代码（高危）。需 session_id、code；可选 tab_id、world（ISOLATED/MAIN，默认 ISOLATED）
- upload_file: 上传本地文件到 file input。需 session_id、selector、file_path（本地绝对路径）；可选 tab_id。依赖 chrome.debugger，扩展需具备 debugger 权限
若用户未安装扩展或扩展未连接，list_sessions 会返回空列表。"""

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "list_sessions",
                    "list_tabs",
                    "navigate",
                    "get_text",
                    "click",
                    "type",
                    "screenshot",
                    "activate_tab",
                    "close_tab",
                    "new_tab",
                    "reload",
                    "back",
                    "forward",
                    "query",
                    "get_html",
                    "hover",
                    "select",
                    "wait_for",
                    "press_key",
                    "scroll",
                    "execute_script",
                    "upload_file",
                ],
                "description": "要执行的操作类型，每次只能选一个",
            },
            "session_id": {
                "type": "string",
                "description": "浏览器扩展会话 ID（由 list_sessions 获取；除 list_sessions 外均必填）",
            },
            "tab_id": {
                "type": "integer",
                "description": "目标标签页 ID（由 list_tabs 获取；navigate 不传则新建标签页）",
            },
            "url": {
                "type": "string",
                "description": "要导航到的 URL（navigate 操作必填）",
            },
            "selector": {
                "type": "string",
                "description": "CSS 选择器（get_text/click/type 操作必填）",
            },
            "text": {
                "type": "string",
                "description": "要输入的文本（type 操作必填）",
            },
            "value": {
                "type": "string",
                "description": "下拉框选项的值（select 操作必填）",
            },
            "state": {
                "type": "string",
                "enum": ["visible", "hidden", "attached"],
                "description": "等待的目标状态（wait_for 可选，默认 visible）",
            },
            "all": {
                "type": "boolean",
                "description": "是否返回全部匹配元素（query 可选，默认 false 只返回首个）",
            },
            "key": {
                "type": "string",
                "description": "要按下的键，如 Enter/Escape/Tab/ArrowDown（press_key 必填）",
            },
            "x": {
                "type": "integer",
                "description": "水平滚动像素（scroll 可选，正数向右）",
            },
            "y": {
                "type": "integer",
                "description": "垂直滚动像素（scroll 可选，正数向下）",
            },
            "behavior": {
                "type": "string",
                "enum": ["auto", "smooth"],
                "description": "滚动行为（scroll 可选，默认 auto）",
            },
            "code": {
                "type": "string",
                "description": "要执行的 JavaScript 代码（execute_script 必填，高危）",
            },
            "world": {
                "type": "string",
                "enum": ["ISOLATED", "MAIN"],
                "description": "脚本执行环境（execute_script 可选，默认 ISOLATED）",
            },
            "file_path": {
                "type": "string",
                "description": "要上传的本地文件绝对路径（upload_file 必填）",
            },
            "full_page": {
                "type": "boolean",
                "description": "是否整页截图（screenshot 可选，默认 false 仅当前视口）",
            },
            "timeout": {
                "type": "number",
                "description": "等待指令执行结果的超时秒数（默认 15）",
            },
        },
        "required": ["action"],
    }

    def _get_master_url(self, action_name: str = "") -> Optional[Dict[str, Any]]:
        """获取 master_url，未设置时返回错误字典。"""
        if not jglobals.master_url:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"master_url is not set, cannot {action_name}. "
                "Please ensure the agent is started with --master-url option.",
            }
        return None

    def _build_auth_headers(self) -> Dict[str, str]:
        """构建带认证信息的请求头。"""
        headers: Dict[str, str] = {}
        auth_token = os.environ.get("JARVIS_AUTH_TOKEN")
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        return headers

    def _request_gateway(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None,
        error_prefix: str = "Request failed",
        timeout: float = 20.0,
    ) -> Dict[str, Any]:
        """向 Gateway 发送 HTTP 请求。"""
        url = f"{jglobals.master_url}{path}"
        headers = self._build_auth_headers()
        try:
            with httpx.Client(timeout=timeout) as client:
                if method.upper() == "POST":
                    response = client.post(url, json=json_data, headers=headers)
                elif method.upper() == "DELETE":
                    response = client.delete(url, headers=headers, params=params)
                else:
                    response = client.get(url, headers=headers, params=params)
            if response.status_code == 200:
                return {
                    "success": True,
                    "status_code": response.status_code,
                    "data": response.json(),
                }
            return {
                "success": False,
                "status_code": response.status_code,
                "data": None,
                "error": f"{error_prefix}: HTTP {response.status_code} - {response.text}",
            }
        except httpx.ConnectError:
            return {
                "success": False,
                "status_code": None,
                "data": None,
                "error": f"Cannot connect to gateway at {jglobals.master_url}. "
                "Please ensure the gateway is running.",
            }
        except Exception as e:
            return {
                "success": False,
                "status_code": None,
                "data": None,
                "error": f"{error_prefix}: {str(e)}",
            }

    def _send_command(
        self,
        session_id: str,
        action: str,
        params: Dict[str, Any],
        timeout: float = 15.0,
    ) -> Dict[str, Any]:
        """通过网关向浏览器扩展会话下发指令。"""
        result = self._request_gateway(
            "POST",
            "/api/browser-ext/command",
            json_data={
                "session_id": session_id,
                "action": action,
                "params": params,
                "timeout": timeout,
            },
            error_prefix=f"Failed to send {action}",
            timeout=timeout + 5.0,
        )
        if not result.get("success"):
            return {
                "success": False,
                "stdout": "",
                "stderr": result.get("error") or "unknown error",
            }
        data = result.get("data") or {}
        if not data.get("success"):
            return {
                "success": False,
                "stdout": "",
                "stderr": data.get("error") or "command failed",
            }
        # 扩展返回的结果信封：{id, type:"result", success, data, error}
        envelope = data.get("result") or {}
        if not envelope.get("success", False):
            return {
                "success": False,
                "stdout": "",
                "stderr": envelope.get("error") or "extension reported failure",
            }
        return {
            "success": True,
            "stdout": self._format_result(action, envelope.get("data")),
            "stderr": "",
        }

    @staticmethod
    def _format_result(action: str, data: Any) -> str:
        """把扩展返回的数据格式化为可读文本。"""
        import json

        if data is None:
            return f"{action} 执行成功"
        if isinstance(data, str):
            return data
        try:
            return json.dumps(data, ensure_ascii=False, indent=2)
        except Exception:
            return str(data)

    def _screenshot_to_file(
        self,
        session_id: str,
        params: Dict[str, Any],
        timeout: float,
    ) -> Dict[str, Any]:
        """截图并把 base64 落盘为临时 PNG 文件，stdout 只返回路径与尺寸。"""
        import base64
        import os
        import tempfile
        import time

        result = self._send_command(session_id, "capture.screenshot", params, timeout)
        if not result.get("success"):
            return result

        # _send_command 已把扩展返回的 data 格式化为文本，这里需要原始 data，
        # 因此重新解析 stdout（扩展返回的是 JSON 文本）。
        import json

        try:
            data = json.loads(result.get("stdout") or "{}")
        except Exception:
            return {
                "success": False,
                "stdout": "",
                "stderr": "failed to parse screenshot result",
            }

        image = data.get("image") or data.get("data_url") or data.get("dataUrl") or ""
        if not image:
            return {
                "success": False,
                "stdout": "",
                "stderr": "screenshot result contains no image data",
            }

        if "," in image and image.strip().startswith("data:"):
            image = image.split(",", 1)[1]

        try:
            raw = base64.b64decode(image)
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"failed to decode screenshot base64: {e}",
            }

        path = os.path.join(
            tempfile.gettempdir(),
            f"jarvis_browser_ext_{int(time.time() * 1000)}.png",
        )
        try:
            with open(path, "wb") as f:
                f.write(raw)
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"failed to write screenshot file: {e}",
            }

        info = {
            "path": path,
            "width": data.get("width"),
            "height": data.get("height"),
            "full_page": bool(params.get("full_page")),
            "bytes": len(raw),
        }
        return {
            "success": True,
            "stdout": json.dumps(info, ensure_ascii=False, indent=2),
            "stderr": "",
        }

    def execute(
        self,
        action: str,
        session_id: Optional[str] = None,
        tab_id: Optional[int] = None,
        url: str = "",
        selector: str = "",
        text: str = "",
        value: str = "",
        state: str = "",
        all: bool = False,
        key: str = "",
        x: Optional[int] = None,
        y: Optional[int] = None,
        behavior: str = "",
        code: str = "",
        world: str = "",
        file_path: str = "",
        full_page: bool = False,
        timeout: float = 15.0,
        **kwargs,
    ) -> Dict[str, Any]:
        """执行浏览器扩展操作。

        参数:
            action: 操作类型（见 parameters.enum）
            session_id: 浏览器扩展会话 ID（除 list_sessions 外必填）
            tab_id: 目标标签页 ID
            url: 要导航到的 URL（navigate/new_tab）
            selector: CSS 选择器（get_text/click/type/query/get_html/hover/select/wait_for）
            text: 要输入的文本（type）
            value: 下拉框选项的值（select）
            state: 等待的目标状态（wait_for，visible/hidden/attached）
            all: 是否返回全部匹配元素（query）
            timeout: 等待结果的超时秒数
            **kwargs: 其他参数

        返回:
            Dict[str, Any]: {"success": bool, "stdout": str, "stderr": str}
        """
        # 兼容 v1.0 协议：registry 可能将整个参数字典作为 action 传入
        if isinstance(action, dict):
            args = action
            action = args.get("action", "")
            session_id = args.get("session_id")
            tab_id = args.get("tab_id")
            url = args.get("url", "")
            selector = args.get("selector", "")
            text = args.get("text", "")
            value = args.get("value", "")
            state = args.get("state", "")
            all = args.get("all", False)
            key = args.get("key", "")
            x = args.get("x")
            y = args.get("y")
            behavior = args.get("behavior", "")
            code = args.get("code", "")
            world = args.get("world", "")
            file_path = args.get("file_path", "")
            full_page = args.get("full_page", False)
            timeout = args.get("timeout", 15.0)

        action = str(action or "").strip()
        if not action:
            return {
                "success": False,
                "stdout": "",
                "stderr": "action is required",
            }

        err = self._get_master_url(f"execute {action}")
        if err is not None:
            return err

        try:
            timeout = float(timeout)
        except (TypeError, ValueError):
            timeout = 15.0

        # ---------------- list_sessions ----------------
        if action == "list_sessions":
            result = self._request_gateway(
                "GET",
                "/api/browser-ext/sessions",
                error_prefix="Failed to list browser sessions",
            )
            if not result.get("success"):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": result.get("error") or "unknown error",
                }
            data = result.get("data") or {}
            sessions: List[Dict[str, Any]] = data.get("sessions") or []
            if not sessions:
                return {
                    "success": True,
                    "stdout": "当前没有在线的浏览器扩展会话。"
                    "请确认用户已在浏览器中安装并连接 Jarvis Browser Bridge 扩展。",
                    "stderr": "",
                }
            return {
                "success": True,
                "stdout": self._format_result("list_sessions", sessions),
                "stderr": "",
            }

        # ---------------- 其余操作均需 session_id ----------------
        known_actions = {
            "list_tabs",
            "navigate",
            "get_text",
            "click",
            "type",
            "screenshot",
            "activate_tab",
            "close_tab",
            "new_tab",
            "reload",
            "back",
            "forward",
            "query",
            "get_html",
            "hover",
            "select",
            "wait_for",
            "press_key",
            "scroll",
            "execute_script",
            "upload_file",
        }
        if action not in known_actions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"unknown action: {action}",
            }

        session_id = str(session_id or "").strip()
        if not session_id:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"session_id is required for action '{action}'. "
                "请先调用 list_sessions 获取。",
            }

        params: Dict[str, Any] = {}
        if tab_id is not None:
            params["tab_id"] = tab_id

        # ---------------- list_tabs ----------------
        if action == "list_tabs":
            return self._send_command(session_id, "tab.list", params, timeout)

        # ---------------- navigate ----------------
        if action == "navigate":
            if not url:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "url is required for action 'navigate'",
                }
            params["url"] = url
            return self._send_command(session_id, "page.navigate", params, timeout)

        # ---------------- get_text ----------------
        if action == "get_text":
            if not selector:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "selector is required for action 'get_text'",
                }
            params["selector"] = selector
            return self._send_command(session_id, "dom.get_text", params, timeout)

        # ---------------- click ----------------
        if action == "click":
            if not selector:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "selector is required for action 'click'",
                }
            params["selector"] = selector
            return self._send_command(session_id, "dom.click", params, timeout)

        # ---------------- type ----------------
        if action == "type":
            if not selector:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "selector is required for action 'type'",
                }
            params["selector"] = selector
            params["text"] = text
            return self._send_command(session_id, "dom.type", params, timeout)

        # ---------------- screenshot ----------------
        if action == "screenshot":
            if full_page:
                params["full_page"] = True
            return self._screenshot_to_file(session_id, params, timeout)

        # ---------------- activate_tab ----------------
        if action == "activate_tab":
            if tab_id is None:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "tab_id is required for action 'activate_tab'",
                }
            return self._send_command(session_id, "tab.activate", params, timeout)

        # ---------------- close_tab ----------------
        if action == "close_tab":
            if tab_id is None:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "tab_id is required for action 'close_tab'",
                }
            return self._send_command(session_id, "tab.close", params, timeout)

        # ---------------- new_tab ----------------
        if action == "new_tab":
            if url:
                params["url"] = url
            return self._send_command(session_id, "tab.create", params, timeout)

        # ---------------- reload ----------------
        if action == "reload":
            return self._send_command(session_id, "page.reload", params, timeout)

        # ---------------- back ----------------
        if action == "back":
            return self._send_command(session_id, "page.back", params, timeout)

        # ---------------- forward ----------------
        if action == "forward":
            return self._send_command(session_id, "page.forward", params, timeout)

        # ---------------- query ----------------
        if action == "query":
            if not selector:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "selector is required for action 'query'",
                }
            params["selector"] = selector
            if all:
                params["all"] = True
            return self._send_command(session_id, "dom.query", params, timeout)

        # ---------------- get_html ----------------
        if action == "get_html":
            if not selector:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "selector is required for action 'get_html'",
                }
            params["selector"] = selector
            return self._send_command(session_id, "dom.get_html", params, timeout)

        # ---------------- hover ----------------
        if action == "hover":
            if not selector:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "selector is required for action 'hover'",
                }
            params["selector"] = selector
            return self._send_command(session_id, "dom.hover", params, timeout)

        # ---------------- select ----------------
        if action == "select":
            if not selector:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "selector is required for action 'select'",
                }
            if value == "":
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "value is required for action 'select'",
                }
            params["selector"] = selector
            params["value"] = value
            return self._send_command(session_id, "dom.select", params, timeout)

        # ---------------- wait_for ----------------
        if action == "wait_for":
            if not selector:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "selector is required for action 'wait_for'",
                }
            params["selector"] = selector
            if state:
                params["state"] = state
            # wait_for 的等待时长以 timeout 参数为准（秒 → 毫秒）
            params["timeout_ms"] = int(timeout * 1000)
            return self._send_command(session_id, "dom.wait_for", params, timeout)

        # ---------------- press_key ----------------
        if action == "press_key":
            if not key:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "key is required for action 'press_key'",
                }
            params["key"] = key
            if selector:
                params["selector"] = selector
            return self._send_command(session_id, "dom.press_key", params, timeout)

        # ---------------- scroll ----------------
        if action == "scroll":
            if not selector and x is None and y is None:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "either selector or x/y is required for action 'scroll'",
                }
            if selector:
                params["selector"] = selector
            if x is not None:
                params["x"] = x
            if y is not None:
                params["y"] = y
            if behavior:
                params["behavior"] = behavior
            return self._send_command(session_id, "dom.scroll", params, timeout)

        # ---------------- execute_script ----------------
        if action == "execute_script":
            if not code:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "code is required for action 'execute_script'",
                }
            params["code"] = code
            if world:
                params["world"] = world
            return self._send_command(session_id, "script.execute", params, timeout)

        # ---------------- upload_file ----------------
        if action == "upload_file":
            if not selector:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "selector is required for action 'upload_file'",
                }
            if not file_path:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "file_path is required for action 'upload_file'",
                }
            params["selector"] = selector
            params["file_path"] = file_path
            return self._send_command(session_id, "dom.upload_file", params, timeout)

        return {
            "success": False,
            "stdout": "",
            "stderr": f"unknown action: {action}",
        }
