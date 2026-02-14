# -*- coding: utf-8 -*-
import asyncio
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Dict
from typing import List
from typing import cast

from jarvis.jarvis_utils.output import PrettyOutput

# 为了类型检查，总是导入这些模块
if TYPE_CHECKING:
    pass


class PlaywrightBrowserTool:
    name = "playwright_browser"
    description = "控制浏览器执行自动化操作（如导航、点击、输入等）。与execute_script不同，此工具创建持久会话，保持浏览器状态。"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "要执行的浏览器操作类型",
                "enum": [
                    "launch",
                    "navigate",
                    "click",
                    "type",
                    "screenshot",
                    "close",
                    "list",
                    "console",
                    "eval",
                    "fill_form",
                    "submit_form",
                    "clear_form",
                    "get_cookies",
                    "set_cookies",
                    "clear_cookies",
                    "wait_for_selector",
                    "wait_for_text",
                    "scroll_to",
                    "scroll_down",
                    "scroll_up",
                    "get_element_info",
                    "get_text",
                    "get_attribute",
                    "hover",
                    "drag",
                    "double_click",
                    "press_key",
                    "upload_file",
                    "download_file",
                    "new_tab",
                    "switch_tab",
                    "close_tab",
                    "go_back",
                    "go_forward",
                    "get_local_storage",
                    "set_local_storage",
                    "start_network_monitor",
                    "get_network_requests",
                    "element_screenshot",
                    "export_pdf",
                    "get_performance_metrics",
                ],
            },
            "browser_id": {
                "type": "string",
                "description": "浏览器的唯一标识符（默认'default'）",
            },
            "url": {
                "type": "string",
                "description": "要导航的 URL（仅 action=navigate 时有效）",
            },
            "selector": {
                "type": "string",
                "description": "元素选择器（仅 action=click 或 action=type 时有效）",
            },
            "text": {
                "type": "string",
                "description": "要输入的文本（仅 action=type 时有效）",
            },
            "wait_condition": {
                "type": "string",
                "description": "等待条件（默认'network_idle'），可选: 'network_idle', 'timeout'",
            },
            "timeout": {
                "type": "number",
                "description": "超时时间（秒，默认30.0），当 wait_condition=timeout 时使用",
            },
            "content_mode": {
                "type": "string",
                "description": "内容保存模式（默认'abstract'），可选: 'html', 'abstract'",
            },
            "headless": {
                "type": "boolean",
                "description": "是否以无头模式启动浏览器（仅 action=launch 时有效，默认true）",
            },
            "code": {
                "type": "string",
                "description": "要执行的 JavaScript 代码（仅 action=eval 时有效）",
            },
            "save_result": {
                "type": "boolean",
                "description": "是否保存 eval 结果到文件（仅 action=eval 时有效，默认false）",
            },
            "clear_logs": {
                "type": "boolean",
                "description": "是否清空已读取的 console 日志（仅 action=console 时有效，默认false）",
            },
            "fields": {
                "type": "object",
                "description": "表单字段映射，字段名到值的字典（仅 action=fill_form 时有效）",
            },
            "form_selector": {
                "type": "string",
                "description": "表单选择器（仅 action=submit_form、action=clear_form 时有效）",
            },
            "cookies": {
                "type": "array",
                "description": "Cookies 数组（仅 action=set_cookies 时有效），每个 cookie 包含 name、value 等字段",
            },
            "wait_state": {
                "type": "string",
                "description": "等待状态（仅 action=wait_for_selector 时有效），可选: 'visible', 'hidden', 'attached', 'detached'，默认 'visible'",
            },
            "wait_text": {
                "type": "string",
                "description": "等待文本内容（仅 action=wait_for_text 时有效）",
            },
            "scroll_x": {
                "type": "number",
                "description": "水平滚动位置（像素），仅scroll_to时有效",
            },
            "scroll_y": {
                "type": "number",
                "description": "垂直滚动位置（像素），仅scroll_to时有效",
            },
            "scroll_amount": {
                "type": "number",
                "description": "滚动距离（像素），scroll_up时为负值，scroll_down时为正值",
            },
            "attribute": {
                "type": "string",
                "description": "属性名（仅action=get_attribute时有效）",
            },
            "target_selector": {
                "type": "string",
                "description": "目标元素选择器（仅action=drag时有效）",
            },
            "key": {
                "type": "string",
                "description": "按键名称（仅action=press_key时有效）",
            },
            "file_path": {
                "type": "string",
                "description": "文件路径（仅action=upload_file时有效）",
            },
            "tab_id": {
                "type": "string",
                "description": "标签页ID（仅action=switch_tab时有效）",
            },
        },
        "required": ["action"],
    }

    @staticmethod
    def check() -> bool:
        """检查工具是否可用（Playwright 是否已安装）"""
        try:
            import playwright  # noqa: F401  # pylint: disable=import-outside-toplevel

            return True
        except ImportError:
            return False

    def _run_async(self, coro: Any) -> Dict[str, Any]:
        """在现有事件循环中运行异步操作

        使用 nest_asyncio 支持嵌套事件循环

        返回:
            Dict[str, Any]: 异步操作的执行结果
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 使用 nest_asyncio 在运行中的循环中执行
                try:
                    return cast(
                        Dict[str, Any],
                        asyncio.run_coroutine_threadsafe(coro, loop).result(),
                    )
                except KeyboardInterrupt:
                    # 用户中断操作，返回友好的错误信息
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "操作被用户中断",
                    }
            else:
                return cast(Dict[str, Any], loop.run_until_complete(coro))
        except RuntimeError:
            return cast(Dict[str, Any], asyncio.run(coro))

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行浏览器操作

        参数:
            args: 包含操作参数的字典，包括agent属性

        返回:
            字典，包含以下内容：
                - success: 布尔值，表示操作状态
                - stdout: 成功消息或操作结果
                - stderr: 错误消息或空字符串
                - output_files: 保存的临时文件路径列表
        """
        # 获取agent对象
        agent = args.get("agent")
        if agent is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": "未提供agent对象",
            }

        # 获取参数
        action = args.get("action", "").strip().lower()
        browser_id = args.get("browser_id", "default")

        # 确保agent有browser_sessions字典
        if not hasattr(agent, "browser_sessions"):
            agent.browser_sessions = {}
        elif agent.browser_sessions is None:
            agent.browser_sessions = {}

        # 验证操作类型
        valid_actions = [
            "launch",
            "navigate",
            "click",
            "type",
            "screenshot",
            "close",
            "list",
            "console",
            "eval",
            "fill_form",
            "submit_form",
            "clear_form",
            "get_cookies",
            "set_cookies",
            "clear_cookies",
            "wait_for_selector",
            "wait_for_text",
            "scroll_to",
            "scroll_down",
            "scroll_up",
            "get_element_info",
            "get_text",
            "get_attribute",
            "hover",
            "drag",
            "double_click",
            "press_key",
            "upload_file",
            "download_file",
            "new_tab",
            "switch_tab",
            "close_tab",
            "go_back",
            "go_forward",
            "get_local_storage",
            "set_local_storage",
            "start_network_monitor",
            "get_network_requests",
            "element_screenshot",
            "export_pdf",
            "get_performance_metrics",
        ]
        if action not in valid_actions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"不支持的操作: {action}。有效操作: {', '.join(valid_actions)}",
            }

        try:
            if action == "launch":
                result = self._run_async(self._launch_browser(agent, browser_id, args))
                if not result["success"]:
                    PrettyOutput.auto_print(f"❌ 启动浏览器 [{browser_id}] 失败")
                return result
            elif action == "navigate":
                result = self._run_async(self._navigate(agent, browser_id, args))
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 导航到 URL 失败")
                return result
            elif action == "click":
                result = self._run_async(self._click(agent, browser_id, args))
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 点击元素失败")
                return result
            elif action == "type":
                result = self._run_async(self._type_text(agent, browser_id, args))
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 输入文本失败")
                return result
            elif action == "screenshot":
                result = self._run_async(self._screenshot(agent, browser_id, args))
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 截图失败")
                return result
            elif action == "close":
                result = self._run_async(self._close_browser(agent, browser_id))
                if not result["success"]:
                    PrettyOutput.auto_print(f"❌ 关闭浏览器 [{browser_id}] 失败")
                return result
            elif action == "list":
                result = self._run_async(self._list_browsers(agent))
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 获取浏览器列表失败")
                return result
            elif action == "console":
                result = self._run_async(
                    self._get_console_logs(agent, browser_id, args)
                )
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 获取 console 日志失败")
                return result
            elif action == "eval":
                result = self._run_async(
                    self._evaluate_javascript(agent, browser_id, args)
                )
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 执行 JavaScript 代码失败")
                return result
            elif action == "fill_form":
                result = self._run_async(self._fill_form(agent, browser_id, args))
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 填写表单失败")
                return result
            elif action == "submit_form":
                result = self._run_async(self._submit_form(agent, browser_id, args))
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 提交表单失败")
                return result
            elif action == "clear_form":
                result = self._run_async(self._clear_form(agent, browser_id, args))
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 清空表单失败")
                return result
            elif action == "get_cookies":
                result = self._run_async(self._get_cookies(agent, browser_id))
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 获取 Cookies 失败")
                return result
            elif action == "set_cookies":
                result = self._run_async(self._set_cookies(agent, browser_id, args))
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 设置 Cookies 失败")
                return result
            elif action == "clear_cookies":
                result = self._run_async(self._clear_cookies(agent, browser_id))
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 清空 Cookies 失败")
                return result
            elif action == "wait_for_selector":
                result = self._run_async(
                    self._wait_for_selector(agent, browser_id, args)
                )
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 等待元素失败")
                return result
            elif action == "wait_for_text":
                result = self._run_async(self._wait_for_text(agent, browser_id, args))
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 等待文本失败")
                return result
            elif action == "scroll_to":
                result = self._run_async(self._scroll_to(agent, browser_id, args))
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 滚动到指定位置失败")
                return result
            elif action == "scroll_down":
                result = self._run_async(self._scroll_down(agent, browser_id, args))
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 向下滚动失败")
                return result
            elif action == "scroll_up":
                result = self._run_async(self._scroll_up(agent, browser_id, args))
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 向上滚动失败")
                return result
            elif action == "get_element_info":
                result = self._run_async(
                    self._get_element_info(agent, browser_id, args)
                )
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 获取元素信息失败")
                return result
            elif action == "get_text":
                result = self._run_async(self._get_text(agent, browser_id, args))
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 获取文本失败")
                return result
            elif action == "get_attribute":
                result = self._run_async(self._get_attribute(agent, browser_id, args))
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 获取属性失败")
                return result
            elif action == "hover":
                result = self._run_async(self._hover(agent, browser_id, args))
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 悬停失败")
                return result
            elif action == "drag":
                result = self._run_async(self._drag(agent, browser_id, args))
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 拖拽失败")
                return result
            elif action == "double_click":
                result = self._run_async(self._double_click(agent, browser_id, args))
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 双击失败")
                return result
            elif action == "press_key":
                result = self._run_async(self._press_key(agent, browser_id, args))
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 按键失败")
                return result
            elif action == "upload_file":
                result = self._run_async(self._upload_file(agent, browser_id, args))
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 上传文件失败")
                return result
            elif action == "download_file":
                result = self._run_async(self._download_file(agent, browser_id, args))
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 下载文件失败")
                return result
            elif action == "new_tab":
                result = self._run_async(self._new_tab(agent, browser_id, args))
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 新建标签页失败")
                return result
            elif action == "switch_tab":
                result = self._run_async(self._switch_tab(agent, browser_id, args))
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 切换标签页失败")
                return result
            elif action == "close_tab":
                result = self._run_async(self._close_tab(agent, browser_id, args))
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 关闭标签页失败")
                return result
            elif action == "go_back":
                result = self._run_async(self._go_back(agent, browser_id, args))
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 后退失败")
                return result
            elif action == "go_forward":
                result = self._run_async(self._go_forward(agent, browser_id, args))
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 前进失败")
                return result
            elif action == "get_local_storage":
                result = self._run_async(
                    self._get_local_storage(agent, browser_id, args)
                )
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 获取本地存储失败")
                return result
            elif action == "set_local_storage":
                result = self._run_async(
                    self._set_local_storage(agent, browser_id, args)
                )
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 设置本地存储失败")
                return result
            elif action == "start_network_monitor":
                result = self._run_async(
                    self._start_network_monitor(agent, browser_id, args)
                )
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 启动网络监听失败")
                return result
            elif action == "get_network_requests":
                result = self._run_async(
                    self._get_network_requests(agent, browser_id, args)
                )
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 获取网络请求失败")
                return result
            elif action == "element_screenshot":
                result = self._run_async(
                    self._element_screenshot(agent, browser_id, args)
                )
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 元素截图失败")
                return result
            elif action == "export_pdf":
                result = self._run_async(self._export_pdf(agent, browser_id, args))
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 导出PDF失败")
                return result
            elif action == "get_performance_metrics":
                result = self._run_async(
                    self._get_performance_metrics(agent, browser_id, args)
                )
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 获取性能指标失败")
                return result
            return {
                "success": False,
                "stdout": "",
                "stderr": "不支持的操作",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"执行浏览器操作出错: {str(e)}",
            }

    async def _launch_browser(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """启动浏览器（异步）"""
        try:
            # 尝试导入 playwright
            try:
                from playwright.async_api import async_playwright  # pylint: disable=import-outside-toplevel
            except ImportError:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "Playwright 未安装，请运行: pip install playwright",
                }

            # 获取参数
            headless = args.get("headless", True)

            # 如果该ID的浏览器已经启动，先关闭它
            if browser_id in agent.browser_sessions:
                await self._close_browser(agent, browser_id)

            # 创建浏览器会话（异步）- 不使用 async with 以保持会话活跃
            from playwright.async_api import async_playwright  # noqa: F401

            playwright_manager = await async_playwright().start()
            browser = await playwright_manager.chromium.launch(headless=headless)
            context = await browser.new_context()
            page = await context.new_page()

            # 添加 console 事件监听器
            async def handle_console_message(msg):
                # 限制日志条数，最多保存 1000 条
                session = agent.browser_sessions[browser_id]
                if len(session["console_logs"]) >= 1000:
                    session["console_logs"].pop(0)  # 移除最早的日志
                session["console_logs"].append(
                    {
                        "type": msg.type,
                        "text": msg.text,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )

            page.on("console", handle_console_message)

            # 保存会话
            agent.browser_sessions[browser_id] = {
                "playwright_manager": playwright_manager,
                "browser": browser,
                "context": context,
                "page": page,
                "console_logs": [],
            }

            # 保存初始页面内容
            content_mode = args.get("content_mode", "abstract")
            file_paths = await self._save_page_content(
                page, browser_id, "launch", content_mode
            )

            stdout_msg = f"浏览器 [{browser_id}] 已启动"
            if file_paths:
                stdout_msg += f"。文件路径: {', '.join(file_paths)}"
                PrettyOutput.auto_print(
                    f"📥 启动浏览器 [{browser_id}] 时的内容已保存到: {', '.join(file_paths)}"
                )

            return {
                "success": True,
                "stdout": stdout_msg,
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"启动浏览器 [{browser_id}] 失败: {str(e)}",
            }

    async def _navigate(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """导航到 URL（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        # 获取参数
        url = args.get("url", "").strip()
        wait_condition = args.get("wait_condition", "network_idle")
        timeout = args.get("timeout", 30.0)
        content_mode = args.get("content_mode", "abstract")

        # 验证 URL
        if not url.startswith(("http://", "https://")):
            return {
                "success": False,
                "stdout": "",
                "stderr": f"无效的 URL: {url}，必须以 http:// 或 https:// 开头",
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]

            # 导航到 URL
            await page.goto(url)

            # 等待条件满足
            await self._wait_for_condition(page, wait_condition, timeout)

            # 保存页面内容
            output_files = await self._save_page_content(
                page, browser_id, "navigate", content_mode
            )

            stdout_msg = f"已导航到: {url}"
            if output_files:
                PrettyOutput.auto_print(
                    f"📥 导航到 [{url}] 后的内容已保存到: {', '.join(output_files)}"
                )
                stdout_msg += f"。页面内容已保存到: {', '.join(output_files)}"

            return {
                "success": True,
                "stdout": stdout_msg,
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"导航到 URL 失败: {str(e)}",
            }

    async def _click(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """点击元素（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        # 获取参数
        selector = args.get("selector", "").strip()
        wait_condition = args.get("wait_condition", "network_idle")
        timeout = args.get("timeout", 30.0)
        content_mode = args.get("content_mode", "abstract")

        if not selector:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少选择器参数",
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]

            # 点击元素
            await page.click(selector)

            # 等待条件满足
            await self._wait_for_condition(page, wait_condition, timeout)

            # 保存页面内容
            output_files = await self._save_page_content(
                page, browser_id, "click", content_mode
            )

            stdout_msg = f"已点击元素: {selector}"
            if output_files:
                PrettyOutput.auto_print(
                    f"📥 点击元素 [{selector}] 后的内容已保存到: {', '.join(output_files)}"
                )
                stdout_msg += f"。页面内容已保存到: {', '.join(output_files)}"

            return {
                "success": True,
                "stdout": stdout_msg,
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"点击元素失败: {str(e)}",
            }

    async def _type_text(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """输入文本（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        # 获取参数
        selector = args.get("selector", "").strip()
        text = args.get("text", "")
        wait_condition = args.get("wait_condition", "network_idle")
        timeout = args.get("timeout", 30.0)
        content_mode = args.get("content_mode", "abstract")

        if not selector:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少选择器参数",
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]

            # 清空并输入文本
            await page.fill(selector, text)

            # 等待条件满足
            await self._wait_for_condition(page, wait_condition, timeout)

            # 保存页面内容
            output_files = await self._save_page_content(
                page, browser_id, "type", content_mode
            )

            stdout_msg = f"已在元素 [{selector}] 中输入文本"
            if output_files:
                PrettyOutput.auto_print(
                    f"📥 输入文本后 [{selector}] 的内容已保存到: {', '.join(output_files)}"
                )
                stdout_msg += f"。页面内容已保存到: {', '.join(output_files)}"

            return {
                "success": True,
                "stdout": stdout_msg,
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"输入文本失败: {str(e)}",
            }

    async def _screenshot(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """截图（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]

            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            temp_dir = Path("/tmp/playwright_browser")
            temp_dir.mkdir(parents=True, exist_ok=True)
            filename = temp_dir / f"{browser_id}_screenshot_{timestamp}.png"

            # 截图
            await page.screenshot(path=str(filename))

            output_files = [str(filename)]
            PrettyOutput.auto_print(f"📥 截图已保存到: {', '.join(output_files)}")

            return {
                "success": True,
                "stdout": f"截图已保存。文件路径: {filename}",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"截图失败: {str(e)}",
            }

    async def _close_browser(self, agent: Any, browser_id: str) -> Dict[str, Any]:
        """关闭浏览器（异步）"""
        # 检查浏览器是否存在
        if browser_id not in agent.browser_sessions:
            return {
                "success": True,
                "stdout": f"浏览器 [{browser_id}] 未启动或已关闭",
                "stderr": "",
            }

        try:
            session = agent.browser_sessions[browser_id]

            # 关闭浏览器
            await session["context"].close()
            await session["browser"].close()
            await session["playwright_manager"].stop()

            # 删除会话
            del agent.browser_sessions[browser_id]

            return {
                "success": True,
                "stdout": f"浏览器 [{browser_id}] 已关闭",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"关闭浏览器 [{browser_id}] 失败: {str(e)}",
            }

    async def _list_browsers(self, agent: Any) -> Dict[str, Any]:
        """列出所有浏览器会话（异步）"""
        try:
            browser_list = []

            for browser_id, session in agent.browser_sessions.items():
                try:
                    page = session["page"]
                    browser_list.append(
                        {
                            "id": browser_id,
                            "status": "活跃",
                            "title": await page.title(),
                            "url": page.url,
                        }
                    )
                except Exception:
                    browser_list.append(
                        {"id": browser_id, "status": "错误", "title": "", "url": ""}
                    )

            # 格式化输出
            output = "浏览器列表:\n"
            for browser in browser_list:
                output += f"ID: {browser['id']}, 状态: {browser['status']}, 标题: {browser['title']}, URL: {browser['url']}\n"

            return {
                "success": True,
                "stdout": output,
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"获取浏览器列表失败: {str(e)}",
            }

    async def _save_page_content(
        self, page: Any, browser_id: str, action: str, content_mode: str
    ) -> List[str]:
        """保存页面内容到临时文件（异步）

        参数:
            page: Playwright 页面对象
            browser_id: 浏览器ID
            action: 操作名称
            content_mode: 内容模式 ('html' 或 'abstract')

        返回:
            List[str]: 保存的文件路径列表
        """
        output_files = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = Path("/tmp/playwright_browser")
        temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            if content_mode == "html":
                # 保存完整 HTML
                filename = temp_dir / f"{browser_id}_{action}_{timestamp}.html"
                content = await page.content()
                filename.write_text(content, encoding="utf-8")
                output_files.append(str(filename))
            else:
                # 保存抽象模式（可交互控件）
                filename = temp_dir / f"{browser_id}_{action}_{timestamp}.txt"
                content = await self._extract_interactive_elements(
                    page, action, timestamp
                )
                filename.write_text(content, encoding="utf-8")
                output_files.append(str(filename))
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 保存页面内容时出错: {str(e)}")

        return output_files

    async def _extract_interactive_elements(
        self, page: Any, action: str, timestamp: str
    ) -> str:
        """提取页面的可交互控件（异步）

        参数:
            page: Playwright 页面对象
            action: 操作名称
            timestamp: 时间戳

        返回:
            str: 格式化的元素文本
        """
        content = f"操作: {action}\n"
        content += f"时间: {timestamp}\n"
        content += f"URL: {page.url}\n\n"
        content += "=== 可交互控件 ===\n\n"

        try:
            # 提取链接
            links = await page.query_selector_all("a[href]")
            if links:
                content += "[链接]\n"
                for link in links[:50]:  # 限制数量
                    try:
                        text = await link.inner_text() or ""
                        href = await link.get_attribute("href") or ""
                        if text.strip():
                            content += f"  文本: {text.strip()}\n"
                            content += f'  链接: a[href="{href}"]\n\n'
                    except Exception:
                        pass

            # 提取按钮
            buttons = await page.query_selector_all(
                "button, input[type='button'], input[type='submit']"
            )
            if buttons:
                content += "[按钮]\n"
                for button in buttons[:50]:
                    try:
                        text = (
                            await button.inner_text()
                            or await button.get_attribute("value")
                            or ""
                        )
                        tag_name = await button.evaluate(
                            "el => el.tagName.toLowerCase()"
                        )
                        selector = (
                            f"{tag_name}[{'text="' + text + '"' if text else ''}]"
                        )
                        if text.strip():
                            content += f"  文本: {text.strip()}\n"
                            content += f"  选择器: {selector}\n\n"
                    except Exception:
                        pass

            # 提取输入框
            inputs = await page.query_selector_all(
                "input[type='text'], input[type='email'], input[type='password'], textarea"
            )
            if inputs:
                content += "[输入框]\n"
                for inp in inputs[:50]:
                    try:
                        tag_name = await inp.evaluate("el => el.tagName.toLowerCase()")
                        input_type = await inp.get_attribute("type") or "text"
                        name = (
                            await inp.get_attribute("name")
                            or await inp.get_attribute("id")
                            or ""
                        )
                        selector = f"{tag_name}[type='{input_type}'{'[name="' + name + '"]' if name else ''}]"
                        content += f"  类型: {input_type}\n"
                        content += f"  名称: {name or '未知'}\n"
                        content += f"  选择器: {selector}\n\n"
                    except Exception:
                        pass

            # 提取选择框
            selects = await page.query_selector_all("select")
            if selects:
                content += "[选择框]\n"
                for select in selects[:50]:
                    try:
                        name = (
                            await select.get_attribute("name")
                            or await select.get_attribute("id")
                            or ""
                        )
                        options = await select.query_selector_all("option")
                        option_texts = [
                            text for opt in options if (text := await opt.inner_text())
                        ]
                        content += f"  名称: {name or '未知'}\n"
                        content += f"  选项: {', '.join(option_texts[:10])}\n"
                        content += f"  选择器: select[{'[name="' + name + '"]' if name else ''}]\n\n"
                    except Exception:
                        pass

        except Exception as e:
            content += f"\n错误: 提取元素时出错: {str(e)}\n"

        return content

    async def _wait_for_condition(
        self, page: Any, wait_condition: str, timeout: float
    ) -> None:
        """等待条件满足（异步）

        参数:
            page: Playwright 页面对象
            wait_condition: 等待条件 ('network_idle' 或 'timeout')
            timeout: 超时时间（秒）
        """
        try:
            if wait_condition == "network_idle":
                # 等待网络空闲
                await page.wait_for_load_state("networkidle", timeout=timeout * 1000)
            else:
                # 固定等待
                await page.wait_for_timeout(timeout * 1000)
        except Exception:
            # 超时或其他错误，继续执行
            pass

    async def _get_console_logs(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """获取 console 日志（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        try:
            session = agent.browser_sessions[browser_id]
            console_logs = session.get("console_logs", [])
            clear_logs = args.get("clear_logs", False)

            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            temp_dir = Path("/tmp/playwright_browser")
            temp_dir.mkdir(parents=True, exist_ok=True)
            filename = temp_dir / f"{browser_id}_console_{timestamp}.txt"

            # 格式化日志内容
            content = f"浏览器 ID: {browser_id}\n"
            content += f"时间: {timestamp}\n"
            content += f"日志数量: {len(console_logs)}\n"
            content += "=" * 50 + "\n\n"

            for log in console_logs:
                content += (
                    f"[{log['timestamp']}] [{log['type'].upper()}] {log['text']}\n"
                )

            # 保存到文件
            filename.write_text(content, encoding="utf-8")
            file_path = str(filename)
            PrettyOutput.auto_print(f"📥 Console 日志已保存到: {file_path}")

            # 清空日志
            if clear_logs:
                session["console_logs"] = []

            return {
                "success": True,
                "stdout": f"已获取 {len(console_logs)} 条 console 日志。文件路径: {file_path}",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"获取 console 日志失败: {str(e)}",
            }

    async def _evaluate_javascript(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行 JavaScript 代码（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        # 获取参数
        code = args.get("code", "").strip()
        save_result = args.get("save_result", False)

        if not code:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少 JavaScript 代码参数",
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]

            # 执行 JavaScript 代码
            result = await page.evaluate(code)

            # 格式化结果为字符串
            result_str = str(result)
            if len(result_str) > 10000:
                result_str = result_str[:10000] + "... (已截断)"

            stdout_msg = f"JavaScript 执行成功: {result_str}"
            file_path_msg = ""

            # 可选保存结果到文件
            if save_result:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                temp_dir = Path("/tmp/playwright_browser")
                temp_dir.mkdir(parents=True, exist_ok=True)
                filename = temp_dir / f"{browser_id}_eval_{timestamp}.txt"

                content = f"浏览器 ID: {browser_id}\n"
                content += f"时间: {timestamp}\n"
                content += f"代码:\n{code}\n\n"
                content += f"结果:\n{result_str}\n"

                file_path = str(filename)
                filename.write_text(content, encoding="utf-8")
                file_path_msg = f" 文件路径: {file_path}"
                PrettyOutput.auto_print(f"📥 Eval 结果已保存到: {file_path}")

            return {
                "success": True,
                "stdout": f"{stdout_msg}{file_path_msg}",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"执行 JavaScript 代码失败: {str(e)}",
            }

    async def _fill_form(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """填写表单（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        # 获取参数
        fields = args.get("fields", {})

        if not fields:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少表单字段参数",
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]
            filled_fields = []
            errors = []

            # 遍历所有字段
            for field_name, field_value in fields.items():
                try:
                    # 尝试多种选择器
                    selectors = [
                        f"input[name='{field_name}']",
                        f"input[id='{field_name}']",
                        f"textarea[name='{field_name}']",
                        f"textarea[id='{field_name}']",
                        f"select[name='{field_name}']",
                        f"select[id='{field_name}']",
                    ]

                    element = None
                    for selector in selectors:
                        try:
                            element = await page.query_selector(selector)
                            if element:
                                break
                        except Exception:
                            continue

                    if element:
                        await element.fill(str(field_value))
                        filled_fields.append(field_name)
                    else:
                        errors.append(f"未找到字段: {field_name}")

                except Exception as e:
                    errors.append(f"填写字段 {field_name} 失败: {str(e)}")

            # 保存操作结果
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            temp_dir = Path("/tmp/playwright_browser")
            temp_dir.mkdir(parents=True, exist_ok=True)
            filename = temp_dir / f"{browser_id}_fill_form_{timestamp}.txt"

            content = f"浏览器 ID: {browser_id}\n"
            content += f"时间: {timestamp}\n"
            content += f"成功填写: {len(filled_fields)} 个字段\n"
            content += f"失败: {len(errors)} 个字段\n\n"

            if filled_fields:
                content += "=== 成功填写的字段 ===\n"
                for field in filled_fields:
                    content += f"  - {field}: {fields[field]}\n"
                content += "\n"

            if errors:
                content += "=== 错误信息 ===\n"
                for error in errors:
                    content += f"  - {error}\n"

            filename.write_text(content, encoding="utf-8")
            output_files = [str(filename)]
            PrettyOutput.auto_print(
                f"📥 表单填写结果已保存到: {', '.join(output_files)}"
            )

            return {
                "success": len(errors) == 0,
                "stdout": f"成功填写 {len(filled_fields)} 个字段。表单结果已保存到: {filename}",
                "stderr": "; ".join(errors) if errors else "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"填写表单失败: {str(e)}",
            }

    async def _submit_form(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """提交表单（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]
            form_selector = args.get("form_selector", "form")
            wait_condition = args.get("wait_condition", "network_idle")
            timeout = args.get("timeout", 30.0)

            # 尝试提交表单
            try:
                await page.click(f"{form_selector} button[type='submit']")
            except Exception:
                try:
                    await page.click(f"{form_selector} input[type='submit']")
                except Exception:
                    # 尝试直接提交表单
                    form = await page.query_selector(form_selector)
                    if form:
                        await form.evaluate("el => el.submit()")
                    else:
                        return {
                            "success": False,
                            "stdout": "",
                            "stderr": f"未找到表单: {form_selector}",
                        }

            # 等待条件满足
            await self._wait_for_condition(page, wait_condition, timeout)

            return {
                "success": True,
                "stdout": "表单已提交",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"提交表单失败: {str(e)}",
            }

    async def _clear_form(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """清空表单（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]
            form_selector = args.get("form_selector", "form")

            # 获取表单内的所有输入元素
            inputs = await page.query_selector_all(f"{form_selector} input")
            textareas = await page.query_selector_all(f"{form_selector} textarea")
            selects = await page.query_selector_all(f"{form_selector} select")

            cleared_count = 0

            # 清空 input 元素
            for input_elem in inputs:
                try:
                    await input_elem.fill("")
                    cleared_count += 1
                except Exception:
                    pass

            # 清空 textarea 元素
            for textarea in textareas:
                try:
                    await textarea.fill("")
                    cleared_count += 1
                except Exception:
                    pass

            # 重置 select 元素到第一个选项
            for select in selects:
                try:
                    await select.select_option(index=0)
                    cleared_count += 1
                except Exception:
                    pass

            return {
                "success": True,
                "stdout": f"已清空 {cleared_count} 个表单字段",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"清空表单失败: {str(e)}",
            }

    async def _get_cookies(self, agent: Any, browser_id: str) -> Dict[str, Any]:
        """获取所有 Cookies（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        try:
            context = agent.browser_sessions[browser_id]["context"]

            # 获取所有 cookies
            cookies = await context.cookies()

            # 保存到文件
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            temp_dir = Path("/tmp/playwright_browser")
            temp_dir.mkdir(parents=True, exist_ok=True)
            filename = temp_dir / f"{browser_id}_cookies_{timestamp}.json"

            # 格式化输出
            content = f"浏览器 ID: {browser_id}\n"
            content += f"时间: {timestamp}\n"
            content += f"Cookies 数量: {len(cookies)}\n\n"

            for i, cookie in enumerate(cookies, 1):
                content += f"=== Cookie {i} ===\n"
                content += f"  Name: {cookie.get('name', '')}\n"
                content += f"  Value: {cookie.get('value', '')}\n"
                content += f"  Domain: {cookie.get('domain', '')}\n"
                content += f"  Path: {cookie.get('path', '')}\n"
                content += f"  Expires: {cookie.get('expires', 'Session')}\n"
                content += f"  Secure: {cookie.get('secure', False)}\n"
                content += f"  HttpOnly: {cookie.get('httpOnly', False)}\n"
                content += "\n"

            filename.write_text(content, encoding="utf-8")
            output_files = [str(filename)]
            PrettyOutput.auto_print(f"📥 Cookies 已保存到: {', '.join(output_files)}")

            return {
                "success": True,
                "stdout": f"已获取 {len(cookies)} 个 Cookies。Cookies 已保存到: {filename}",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"获取 Cookies 失败: {str(e)}",
            }

    async def _set_cookies(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """设置 Cookies（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        # 获取参数
        cookies = args.get("cookies", [])

        if not cookies:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少 cookies 参数",
            }

        try:
            context = agent.browser_sessions[browser_id]["context"]

            # 设置 cookies
            await context.add_cookies(cookies)

            return {
                "success": True,
                "stdout": f"已设置 {len(cookies)} 个 Cookies",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"设置 Cookies 失败: {str(e)}",
            }

    async def _clear_cookies(self, agent: Any, browser_id: str) -> Dict[str, Any]:
        """清空所有 Cookies（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        try:
            context = agent.browser_sessions[browser_id]["context"]

            # 清空 cookies
            await context.clear_cookies()

            return {
                "success": True,
                "stdout": "已清空所有 Cookies",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"清空 Cookies 失败: {str(e)}",
            }

    async def _wait_for_selector(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """等待元素达到指定状态（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        # 获取参数
        selector = args.get("selector", "").strip()
        wait_state = args.get("wait_state", "visible")
        timeout = args.get("timeout", 30.0)

        if not selector:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少选择器参数",
            }

        # 验证状态参数
        valid_states = ["visible", "hidden", "attached", "detached"]
        if wait_state not in valid_states:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"无效的等待状态: {wait_state}，有效状态: {', '.join(valid_states)}",
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]

            # 等待元素达到指定状态
            await page.wait_for_selector(
                selector, state=wait_state, timeout=timeout * 1000
            )

            return {
                "success": True,
                "stdout": f"元素 [{selector}] 已达到状态 [{wait_state}]",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"等待元素失败: {str(e)}",
            }

    async def _wait_for_text(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """等待文本出现（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        # 获取参数
        text = args.get("wait_text", "").strip()
        selector = args.get("selector", "*")
        timeout = args.get("timeout", 30.0)

        if not text:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少 wait_text 参数",
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]

            # 等待文本出现
            await page.wait_for_function(
                """
                (text, selector) => {{
                    const elements = document.querySelectorAll(selector);
                    for (const el of elements) {{
                        if (el.textContent && el.textContent.includes(text)) {{
                            return true;
                        }}
                    }}
                    return false;
                }}
                """,
                text=text,
                selector=selector,
                timeout=timeout * 1000,
            )

            return {
                "success": True,
                "stdout": f"文本 [{text}] 已出现",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"等待文本失败: {str(e)}",
            }

    async def _scroll_to(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """滚动到指定位置（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        # 获取参数
        scroll_x = args.get("scroll_x", 0)
        scroll_y = args.get("scroll_y", 0)

        try:
            page = agent.browser_sessions[browser_id]["page"]

            # 滚动到指定位置
            await page.evaluate(f"window.scrollTo({scroll_x}, {scroll_y})")

            return {
                "success": True,
                "stdout": f"已滚动到位置 ({scroll_x}, {scroll_y})",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"滚动失败: {str(e)}",
            }

    async def _scroll_down(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """向下滚动页面（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        # 获取参数
        scroll_amount = args.get("scroll_amount", 300)

        try:
            page = agent.browser_sessions[browser_id]["page"]

            # 获取当前滚动位置
            current_scroll = await page.evaluate("window.scrollY")
            new_scroll = current_scroll + scroll_amount

            # 向下滚动
            await page.evaluate(f"window.scrollTo(0, {new_scroll})")

            return {
                "success": True,
                "stdout": f"已向下滚动 {scroll_amount} 像素",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"向下滚动失败: {str(e)}",
            }

    async def _scroll_up(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """向上滚动页面（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        # 获取参数
        scroll_amount = args.get("scroll_amount", -300)  # 默认向上300像素

        try:
            page = agent.browser_sessions[browser_id]["page"]

            # 获取当前滚动位置
            current_scroll = await page.evaluate("window.scrollY")
            new_scroll = current_scroll + scroll_amount

            # 确保 new_scroll 不小于0
            if new_scroll < 0:
                new_scroll = 0

            # 向上滚动
            await page.evaluate(f"window.scrollTo(0, {new_scroll})")

            return {
                "success": True,
                "stdout": f"已向上滚动 {abs(scroll_amount)} 像素",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"向上滚动失败: {str(e)}",
            }

    async def _get_element_info(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """获取元素的详细信息（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        # 获取参数
        selector = args.get("selector", "").strip()

        if not selector:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少选择器参数",
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]
            element = await page.query_selector(selector)

            if not element:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"未找到元素 [{selector}]",
                }

            # 获取元素信息
            info = {
                "selector": selector,
                "tag_name": await element.evaluate("el => el.tagName"),
                "text": await element.evaluate("el => el.textContent"),
                "visible": await element.is_visible(),
                "enabled": await element.is_enabled(),
                "id": await element.evaluate("el => el.id"),
                "class": await element.evaluate("el => el.className"),
            }

            # 将信息转换为 JSON 字符串
            import json

            info_str = json.dumps(info, indent=2, ensure_ascii=False)

            return {
                "success": True,
                "stdout": f"元素信息:\n{info_str}",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"获取元素信息失败: {str(e)}",
            }

    async def _get_text(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """获取元素的文本内容（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        # 获取参数
        selector = args.get("selector", "").strip()

        if not selector:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少选择器参数",
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]
            element = await page.query_selector(selector)

            if not element:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"未找到元素 [{selector}]",
                }

            # 获取文本内容
            text = await element.text_content()

            return {
                "success": True,
                "stdout": text if text else "",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"获取文本失败: {str(e)}",
            }

    async def _get_attribute(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """获取元素的属性值（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        # 获取参数
        selector = args.get("selector", "").strip()
        attribute = args.get("attribute", "").strip()

        if not selector:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少选择器参数",
            }

        if not attribute:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少属性名参数",
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]
            element = await page.query_selector(selector)

            if not element:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"未找到元素 [{selector}]",
                }

            # 获取属性值
            attr_value = await element.get_attribute(attribute)

            if attr_value is None:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"元素 [{selector}] 没有属性 [{attribute}]",
                }

            return {
                "success": True,
                "stdout": attr_value,
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"获取属性失败: {str(e)}",
            }

    async def _hover(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """鼠标悬停到元素上（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        # 获取参数
        selector = args.get("selector", "").strip()

        if not selector:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少选择器参数",
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]
            element = await page.query_selector(selector)

            if not element:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"未找到元素 [{selector}]",
                }

            # 鼠标悬停
            await element.hover()

            return {
                "success": True,
                "stdout": f"已悬停到元素 [{selector}]",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"悬停失败: {str(e)}",
            }

    async def _drag(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """拖拽元素（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        # 获取参数
        selector = args.get("selector", "").strip()
        target_selector = args.get("target_selector", "").strip()

        if not selector:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少选择器参数",
            }

        if not target_selector:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少目标选择器参数",
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]

            # 获取源元素和目标元素
            source_element = await page.query_selector(selector)
            target_element = await page.query_selector(target_selector)

            if not source_element:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"未找到源元素 [{selector}]",
                }

            if not target_element:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"未找到目标元素 [{target_selector}]",
                }

            # 执行拖拽操作
            await source_element.drag_to(target_element)

            return {
                "success": True,
                "stdout": f"已将元素 [{selector}] 拖拽到 [{target_selector}]",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"拖拽失败: {str(e)}",
            }

    async def _double_click(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """双击元素（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        # 获取参数
        selector = args.get("selector", "").strip()

        if not selector:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少选择器参数",
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]
            element = await page.query_selector(selector)

            if not element:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"未找到元素 [{selector}]",
                }

            # 双击元素
            await element.dblclick()

            return {
                "success": True,
                "stdout": f"已双击元素 [{selector}]",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"双击失败: {str(e)}",
            }

    async def _press_key(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """按下键盘按键（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        # 获取参数
        key = args.get("key", "").strip()

        if not key:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少按键参数",
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]

            # 按下按键
            await page.keyboard.press(key)

            return {
                "success": True,
                "stdout": f"已按下按键 [{key}]",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"按键失败: {str(e)}",
            }

    async def _upload_file(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """上传文件（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        # 获取参数
        selector = args.get("selector", "").strip()
        file_path = args.get("file_path", "").strip()

        if not selector:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少选择器参数",
            }

        if not file_path:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少文件路径参数",
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]
            element = await page.query_selector(selector)

            if not element:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"未找到元素 [{selector}]",
                }

            # 上传文件
            await element.set_input_files(file_path)

            return {
                "success": True,
                "stdout": f"已上传文件 [{file_path}]",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"上传文件失败: {str(e)}",
            }

    async def _new_tab(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """新建标签页（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        try:
            browser = agent.browser_sessions[browser_id]["browser"]
            pages = agent.browser_sessions[browser_id].get("pages", {})

            # 创建新页面
            new_page = await browser.new_page()
            page_id = f"page_{len(pages) + 1}"
            pages[page_id] = new_page

            # 更新会话
            agent.browser_sessions[browser_id]["pages"] = pages
            agent.browser_sessions[browser_id]["current_page_id"] = page_id
            agent.browser_sessions[browser_id]["page"] = new_page

            PrettyOutput.auto_print(
                f"✅ 新建标签页 [{page_id}] 成功，当前标签页总数: {len(pages)}"
            )

            return {
                "success": True,
                "stdout": f"已新建标签页 [{page_id}]",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"新建标签页失败: {str(e)}",
            }

    async def _switch_tab(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """切换标签页（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        # 获取参数
        page_id = args.get("page_id", "").strip()

        if not page_id:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少 page_id 参数",
            }

        try:
            pages = agent.browser_sessions[browser_id].get("pages", {})

            if page_id not in pages:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"标签页 [{page_id}] 不存在，可用标签页: {', '.join(pages.keys())}",
                }

            # 切换到指定标签页
            agent.browser_sessions[browser_id]["current_page_id"] = page_id
            agent.browser_sessions[browser_id]["page"] = pages[page_id]

            PrettyOutput.auto_print(f"✅ 已切换到标签页 [{page_id}]")

            return {
                "success": True,
                "stdout": f"已切换到标签页 [{page_id}]",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"切换标签页失败: {str(e)}",
            }

    async def _close_tab(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """关闭标签页（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        # 获取参数
        page_id = args.get("page_id", "").strip()

        if not page_id:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少 page_id 参数",
            }

        try:
            pages = agent.browser_sessions[browser_id].get("pages", {})

            if page_id not in pages:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"标签页 [{page_id}] 不存在，可用标签页: {', '.join(pages.keys())}",
                }

            # 关闭标签页
            await pages[page_id].close()
            del pages[page_id]

            # 如果关闭的是当前标签页，切换到另一个
            if (
                "current_page_id" in agent.browser_sessions[browser_id]
                and agent.browser_sessions[browser_id]["current_page_id"] == page_id
            ):
                if pages:
                    # 切换到第一个可用标签页
                    new_current_id = list(pages.keys())[0]
                    agent.browser_sessions[browser_id]["current_page_id"] = (
                        new_current_id
                    )
                    agent.browser_sessions[browser_id]["page"] = pages[new_current_id]
                else:
                    # 没有其他标签页了，清空
                    agent.browser_sessions[browser_id]["current_page_id"] = None
                    agent.browser_sessions[browser_id]["page"] = None

            agent.browser_sessions[browser_id]["pages"] = pages

            PrettyOutput.auto_print(
                f"✅ 已关闭标签页 [{page_id}]，剩余标签页: {len(pages)}"
            )

            return {
                "success": True,
                "stdout": f"已关闭标签页 [{page_id}]",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"关闭标签页失败: {str(e)}",
            }

    async def _go_back(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """后退到上一个页面（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]

            # 检查是否有页面可以后退
            can_go_back = await page.evaluate("() => window.history.length > 1")

            if not can_go_back:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "没有可以后退的页面",
                }

            # 后退到上一个页面
            await page.go_back()

            PrettyOutput.auto_print("✅ 已后退到上一个页面")

            return {
                "success": True,
                "stdout": "已后退到上一个页面",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"后退失败: {str(e)}",
            }

    async def _go_forward(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """前进到下一个页面（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]

            # 前进到下一个页面
            await page.go_forward()

            PrettyOutput.auto_print("✅ 已前进到下一个页面")

            return {
                "success": True,
                "stdout": "已前进到下一个页面",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"前进失败: {str(e)}",
            }

    async def _get_local_storage(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """获取本地存储（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]

            # 获取所有 localStorage 数据
            local_storage = await page.evaluate("""() => {
                const items = {};
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    items[key] = localStorage.getItem(key);
                }
                return items;
            }""")

            # 保存到文件
            import json
            import tempfile

            output_file = tempfile.mktemp(
                suffix="_local_storage.json",
                prefix=f"{browser_id}_",
            )
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(local_storage, f, ensure_ascii=False, indent=2)

            PrettyOutput.auto_print(
                f"✅ 已获取本地存储数据，共 {len(local_storage)} 项，已保存到: {output_file}"
            )

            return {
                "success": True,
                "stdout": f"已获取本地存储数据，共 {len(local_storage)} 项\n保存路径: {output_file}",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"获取本地存储失败: {str(e)}",
            }

    async def _set_local_storage(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """设置本地存储（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        # 获取参数
        data = args.get("data", {})
        clear = args.get("clear", False)

        if not isinstance(data, dict):
            return {
                "success": False,
                "stdout": "",
                "stderr": "data 参数必须是字典类型",
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]

            if clear:
                # 清空所有 localStorage
                await page.evaluate("() => localStorage.clear()")

            # 设置 localStorage 数据
            if data:
                await page.evaluate(
                    """(data) => {
                        for (const [key, value] of Object.entries(data)) {
                            localStorage.setItem(key, value);
                        }
                    }""",
                    data,
                )

            action_desc = "清空并设置" if clear else "设置"
            PrettyOutput.auto_print(
                f"✅ 已{action_desc}本地存储数据，共 {len(data)} 项"
            )

            return {
                "success": True,
                "stdout": f"已{action_desc}本地存储数据，共 {len(data)} 项",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"设置本地存储失败: {str(e)}",
            }

    async def _start_network_monitor(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """启动网络监听（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]

            # 初始化网络请求列表
            if "network_requests" not in agent.browser_sessions[browser_id]:
                agent.browser_sessions[browser_id]["network_requests"] = []

            # 设置请求和响应监听器
            def handle_request(request):
                request_info = {
                    "type": "request",
                    "url": request.url,
                    "method": request.method,
                    "headers": dict(request.headers),
                    "timestamp": self._get_timestamp(),
                }
                agent.browser_sessions[browser_id]["network_requests"].append(
                    request_info
                )

            def handle_response(response):
                response_info = {
                    "type": "response",
                    "url": response.url,
                    "status": response.status,
                    "headers": dict(response.headers),
                    "timestamp": self._get_timestamp(),
                }
                agent.browser_sessions[browser_id]["network_requests"].append(
                    response_info
                )

            # 添加监听器
            page.on("request", handle_request)
            page.on("response", handle_response)

            PrettyOutput.auto_print("✅ 已启动网络监听")

            return {
                "success": True,
                "stdout": "已启动网络监听",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"启动网络监听失败: {str(e)}",
            }

    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime

        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async def _get_network_requests(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """获取网络请求（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        try:
            network_requests = agent.browser_sessions[browser_id].get(
                "network_requests", []
            )

            if not network_requests:
                return {
                    "success": True,
                    "stdout": "暂无网络请求记录",
                    "stderr": "",
                }

            # 保存到文件
            import json
            import tempfile

            output_file = tempfile.mktemp(
                suffix="_network_requests.json",
                prefix=f"{browser_id}_",
            )
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(network_requests, f, ensure_ascii=False, indent=2)

            PrettyOutput.auto_print(
                f"✅ 已获取网络请求记录，共 {len(network_requests)} 条，已保存到: {output_file}"
            )

            return {
                "success": True,
                "stdout": f"已获取网络请求记录，共 {len(network_requests)} 条\n保存路径: {output_file}",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"获取网络请求失败: {str(e)}",
            }

    async def _element_screenshot(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """元素截图（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        # 获取参数
        selector = args.get("selector", "").strip()

        if not selector:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少 selector 参数",
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]

            # 查找元素
            element = await page.wait_for_selector(selector, timeout=30000)

            if not element:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"未找到选择器: {selector}",
                }

            # 截图
            import tempfile

            screenshot_path = tempfile.mktemp(
                suffix="_element_screenshot.png",
                prefix=f"{browser_id}_",
            )
            await element.screenshot(path=screenshot_path)

            PrettyOutput.auto_print(
                f"✅ 已对元素 [{selector}] 截图，保存到: {screenshot_path}"
            )

            return {
                "success": True,
                "stdout": f"已对元素 [{selector}] 截图\n保存路径: {screenshot_path}",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"元素截图失败: {str(e)}",
            }

    async def _export_pdf(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """导出PDF（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]

            # 导出PDF
            import tempfile

            pdf_path = tempfile.mktemp(
                suffix="_page.pdf",
                prefix=f"{browser_id}_",
            )
            await page.pdf(path=pdf_path)

            PrettyOutput.auto_print(f"✅ 已导出PDF，保存到: {pdf_path}")

            return {
                "success": True,
                "stdout": f"已导出PDF\n保存路径: {pdf_path}",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"导出PDF失败: {str(e)}",
            }

    async def _get_performance_metrics(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """获取页面性能指标（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]

            # 获取性能指标
            metrics = await page.evaluate("""() => {
                const perfData = performance.timing;
                const metrics = {
                    "页面加载时间": perfData.loadEventEnd - perfData.navigationStart,
                    "DOM 解析时间": perfData.domComplete - perfData.domInteractive,
                    "资源加载时间": perfData.loadEventEnd - perfData.domContentLoadedEventEnd,
                    "DNS 查询时间": perfData.domainLookupEnd - perfData.domainLookupStart,
                    "TCP 连接时间": perfData.connectEnd - perfData.connectStart,
                    "请求响应时间": perfData.responseStart - perfData.requestStart,
                    "文档下载时间": perfData.responseEnd - perfData.responseStart,
                    "DOM 内容加载时间": perfData.domContentLoadedEventEnd - perfData.navigationStart,
                };
                return metrics;
            }""")

            # 保存到文件
            import json
            import tempfile

            output_file = tempfile.mktemp(
                suffix="_performance_metrics.json",
                prefix=f"{browser_id}_",
            )
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(metrics, f, ensure_ascii=False, indent=2)

            PrettyOutput.auto_print(f"✅ 已获取页面性能指标，已保存到: {output_file}")

            return {
                "success": True,
                "stdout": f"已获取页面性能指标\n保存路径: {output_file}",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"获取性能指标失败: {str(e)}",
            }

    async def _download_file(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """下载文件（异步）"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]

            # 设置下载路径
            import os
            from datetime import datetime

            download_dir = "/tmp/playwright_downloads"
            os.makedirs(download_dir, exist_ok=True)

            # 开始下载，等待下载完成
            async with page.expect_download() as download_info:
                # 点击下载链接或按钮
                selector = args.get("selector", "").strip()
                if selector:
                    element = await page.query_selector(selector)
                    if element:
                        await element.click()
                else:
                    # 如果没有 selector，假设页面已经开始下载
                    pass

            download = await download_info.value
            file_name = (
                download.suggested_filename
                or f"download_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            save_path = os.path.join(download_dir, file_name)

            # 保存文件
            await download.save_as(save_path)

            return {
                "success": True,
                "stdout": f"文件已下载到 [{save_path}]",
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"下载文件失败: {str(e)}",
            }
