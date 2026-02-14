# -*- coding: utf-8 -*-
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Dict
from typing import List

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
                "output_files": [],
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
        ]
        if action not in valid_actions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"不支持的操作: {action}。有效操作: {', '.join(valid_actions)}",
                "output_files": [],
            }

        try:
            if action == "launch":
                result = self._launch_browser(agent, browser_id, args)
                if not result["success"]:
                    PrettyOutput.auto_print(f"❌ 启动浏览器 [{browser_id}] 失败")
                return result
            elif action == "navigate":
                result = self._navigate(agent, browser_id, args)
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 导航到 URL 失败")
                return result
            elif action == "click":
                result = self._click(agent, browser_id, args)
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 点击元素失败")
                return result
            elif action == "type":
                result = self._type_text(agent, browser_id, args)
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 输入文本失败")
                return result
            elif action == "screenshot":
                result = self._screenshot(agent, browser_id, args)
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 截图失败")
                return result
            elif action == "close":
                result = self._close_browser(agent, browser_id)
                if not result["success"]:
                    PrettyOutput.auto_print(f"❌ 关闭浏览器 [{browser_id}] 失败")
                return result
            elif action == "list":
                result = self._list_browsers(agent)
                if not result["success"]:
                    PrettyOutput.auto_print("❌ 获取浏览器列表失败")
                return result
            return {
                "success": False,
                "stdout": "",
                "stderr": "不支持的操作",
                "output_files": [],
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"执行浏览器操作出错: {str(e)}",
                "output_files": [],
            }

    def _launch_browser(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """启动浏览器"""
        try:
            # 尝试导入 playwright
            try:
                from playwright.sync_api import sync_playwright  # pylint: disable=import-outside-toplevel
            except ImportError:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "Playwright 未安装，请运行: pip install playwright",
                    "output_files": [],
                }

            # 获取参数
            headless = args.get("headless", True)

            # 如果该ID的浏览器已经启动，先关闭它
            if browser_id in agent.browser_sessions:
                self._close_browser(agent, browser_id)

            # 创建浏览器会话
            playwright_manager = sync_playwright().start()
            browser = playwright_manager.chromium.launch(headless=headless)
            context = browser.new_context()
            page = context.new_page()

            # 保存会话
            agent.browser_sessions[browser_id] = {
                "playwright_manager": playwright_manager,
                "browser": browser,
                "context": context,
                "page": page,
            }

            # 保存初始页面内容
            content_mode = args.get("content_mode", "abstract")
            output_files = self._save_page_content(
                page, browser_id, "launch", content_mode
            )

            if output_files:
                PrettyOutput.auto_print(
                    f"📥 启动浏览器 [{browser_id}] 时的内容已保存到: {', '.join(output_files)}"
                )

            return {
                "success": True,
                "stdout": f"浏览器 [{browser_id}] 已启动",
                "stderr": "",
                "output_files": output_files,
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"启动浏览器 [{browser_id}] 失败: {str(e)}",
                "output_files": [],
            }

    def _navigate(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """导航到 URL"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
                "output_files": [],
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
                "output_files": [],
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]

            # 导航到 URL
            page.goto(url)

            # 等待条件满足
            self._wait_for_condition(page, wait_condition, timeout)

            # 保存页面内容
            output_files = self._save_page_content(
                page, browser_id, "navigate", content_mode
            )

            if output_files:
                PrettyOutput.auto_print(
                    f"📥 导航到 [{url}] 后的内容已保存到: {', '.join(output_files)}"
                )

            return {
                "success": True,
                "stdout": f"已导航到: {url}",
                "stderr": "",
                "output_files": output_files,
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"导航到 URL 失败: {str(e)}",
                "output_files": [],
            }

    def _click(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """点击元素"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
                "output_files": [],
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
                "output_files": [],
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]

            # 点击元素
            page.click(selector)

            # 等待条件满足
            self._wait_for_condition(page, wait_condition, timeout)

            # 保存页面内容
            output_files = self._save_page_content(
                page, browser_id, "click", content_mode
            )

            if output_files:
                PrettyOutput.auto_print(
                    f"📥 点击元素 [{selector}] 后的内容已保存到: {', '.join(output_files)}"
                )

            return {
                "success": True,
                "stdout": f"已点击元素: {selector}",
                "stderr": "",
                "output_files": output_files,
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"点击元素失败: {str(e)}",
                "output_files": [],
            }

    def _type_text(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """输入文本"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
                "output_files": [],
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
                "output_files": [],
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]

            # 清空并输入文本
            page.fill(selector, text)

            # 等待条件满足
            self._wait_for_condition(page, wait_condition, timeout)

            # 保存页面内容
            output_files = self._save_page_content(
                page, browser_id, "type", content_mode
            )

            if output_files:
                PrettyOutput.auto_print(
                    f"📥 输入文本后 [{selector}] 的内容已保存到: {', '.join(output_files)}"
                )

            return {
                "success": True,
                "stdout": f"已在元素 [{selector}] 中输入文本",
                "stderr": "",
                "output_files": output_files,
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"输入文本失败: {str(e)}",
                "output_files": [],
            }

    def _screenshot(
        self, agent: Any, browser_id: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """截图"""
        # 检查浏览器是否启动
        if browser_id not in agent.browser_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"浏览器 [{browser_id}] 未启动",
                "output_files": [],
            }

        try:
            page = agent.browser_sessions[browser_id]["page"]

            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            temp_dir = Path("/tmp/playwright_browser")
            temp_dir.mkdir(parents=True, exist_ok=True)
            filename = temp_dir / f"{browser_id}_screenshot_{timestamp}.png"

            # 截图
            page.screenshot(path=str(filename))

            output_files = [str(filename)]
            PrettyOutput.auto_print(f"📥 截图已保存到: {', '.join(output_files)}")

            return {
                "success": True,
                "stdout": "截图已保存",
                "stderr": "",
                "output_files": output_files,
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"截图失败: {str(e)}",
                "output_files": [],
            }

    def _close_browser(self, agent: Any, browser_id: str) -> Dict[str, Any]:
        """关闭浏览器"""
        # 检查浏览器是否存在
        if browser_id not in agent.browser_sessions:
            return {
                "success": True,
                "stdout": f"浏览器 [{browser_id}] 未启动或已关闭",
                "stderr": "",
                "output_files": [],
            }

        try:
            session = agent.browser_sessions[browser_id]

            # 关闭浏览器
            session["context"].close()
            session["browser"].close()
            session["playwright_manager"].stop()

            # 删除会话
            del agent.browser_sessions[browser_id]

            return {
                "success": True,
                "stdout": f"浏览器 [{browser_id}] 已关闭",
                "stderr": "",
                "output_files": [],
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"关闭浏览器 [{browser_id}] 失败: {str(e)}",
                "output_files": [],
            }

    def _list_browsers(self, agent: Any) -> Dict[str, Any]:
        """列出所有浏览器会话"""
        try:
            browser_list = []

            for browser_id, session in agent.browser_sessions.items():
                try:
                    page = session["page"]
                    browser_list.append(
                        {
                            "id": browser_id,
                            "status": "活跃",
                            "title": page.title(),
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
                "output_files": [],
                "browser_list": browser_list,
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"获取浏览器列表失败: {str(e)}",
                "output_files": [],
            }

    def _save_page_content(
        self, page: Any, browser_id: str, action: str, content_mode: str
    ) -> List[str]:
        """保存页面内容到临时文件

        参数:
            page: Playwright 页面对象
            browser_id: 浏览器ID
            action: 操作名称
            content_mode: 内容模式 ('html' 或 'abstract')

        返回:
            保存的文件路径列表
        """
        output_files = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = Path("/tmp/playwright_browser")
        temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            if content_mode == "html":
                # 保存完整 HTML
                filename = temp_dir / f"{browser_id}_{action}_{timestamp}.html"
                content = page.content()
                filename.write_text(content, encoding="utf-8")
                output_files.append(str(filename))
            else:
                # 保存抽象模式（可交互控件）
                filename = temp_dir / f"{browser_id}_{action}_{timestamp}.txt"
                content = self._extract_interactive_elements(page, action, timestamp)
                filename.write_text(content, encoding="utf-8")
                output_files.append(str(filename))
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 保存页面内容时出错: {str(e)}")

        return output_files

    def _extract_interactive_elements(
        self, page: Any, action: str, timestamp: str
    ) -> str:
        """提取页面的可交互控件

        参数:
            page: Playwright 页面对象
            action: 操作名称
            timestamp: 时间戳

        返回:
            格式化的元素文本
        """
        content = f"操作: {action}\n"
        content += f"时间: {timestamp}\n"
        content += f"URL: {page.url}\n\n"
        content += "=== 可交互控件 ===\n\n"

        try:
            # 提取链接
            links = page.query_selector_all("a[href]")
            if links:
                content += "[链接]\n"
                for link in links[:50]:  # 限制数量
                    try:
                        text = link.inner_text() or ""
                        href = link.get_attribute("href") or ""
                        if text.strip():
                            content += f"  文本: {text.strip()}\n"
                            content += f'  链接: a[href="{href}"]\n\n'
                    except Exception:
                        pass

            # 提取按钮
            buttons = page.query_selector_all(
                "button, input[type='button'], input[type='submit']"
            )
            if buttons:
                content += "[按钮]\n"
                for button in buttons[:50]:
                    try:
                        text = (
                            button.inner_text() or button.get_attribute("value") or ""
                        )
                        tag_name = button.evaluate("el => el.tagName.toLowerCase()")
                        selector = (
                            f"{tag_name}[{'text="' + text + '"' if text else ''}]"
                        )
                        if text.strip():
                            content += f"  文本: {text.strip()}\n"
                            content += f"  选择器: {selector}\n\n"
                    except Exception:
                        pass

            # 提取输入框
            inputs = page.query_selector_all(
                "input[type='text'], input[type='email'], input[type='password'], textarea"
            )
            if inputs:
                content += "[输入框]\n"
                for inp in inputs[:50]:
                    try:
                        tag_name = inp.evaluate("el => el.tagName.toLowerCase()")
                        input_type = inp.get_attribute("type") or "text"
                        name = (
                            inp.get_attribute("name") or inp.get_attribute("id") or ""
                        )
                        selector = f"{tag_name}[type='{input_type}'{'[name="' + name + '"]' if name else ''}]"
                        content += f"  类型: {input_type}\n"
                        content += f"  名称: {name or '未知'}\n"
                        content += f"  选择器: {selector}\n\n"
                    except Exception:
                        pass

            # 提取选择框
            selects = page.query_selector_all("select")
            if selects:
                content += "[选择框]\n"
                for select in selects[:50]:
                    try:
                        name = (
                            select.get_attribute("name")
                            or select.get_attribute("id")
                            or ""
                        )
                        options = select.query_selector_all("option")
                        option_texts = [
                            opt.inner_text() for opt in options if opt.inner_text()
                        ]
                        content += f"  名称: {name or '未知'}\n"
                        content += f"  选项: {', '.join(option_texts[:10])}\n"
                        content += f"  选择器: select[{'[name="' + name + '"]' if name else ''}]\n\n"
                    except Exception:
                        pass

        except Exception as e:
            content += f"\n错误: 提取元素时出错: {str(e)}\n"

        return content

    def _wait_for_condition(
        self, page: Any, wait_condition: str, timeout: float
    ) -> None:
        """等待条件满足

        参数:
            page: Playwright 页面对象
            wait_condition: 等待条件 ('network_idle' 或 'timeout')
            timeout: 超时时间（秒）
        """
        try:
            if wait_condition == "network_idle":
                # 等待网络空闲
                page.wait_for_load_state("networkidle", timeout=timeout * 1000)
            else:
                # 固定等待
                page.wait_for_timeout(timeout * 1000)
        except Exception:
            # 超时或其他错误，继续执行
            pass
