from multiprocessing import get_context
from typing import Dict, Any, Optional, List
import os
import time
from datetime import datetime
from pathlib import Path
import scipy as sp
from yaspin import yaspin
from yaspin.spinners import Spinners
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.config import get_max_token_count
from jarvis.jarvis_utils.embedding import get_context_token_count

class BrowserTool:
    name = "browser"
    description = "控制无头浏览器执行各种操作，如导航、截图和获取内容"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "要执行的浏览器操作，可选值: 'launch', 'goto', 'screenshot', 'extract', 'click', 'type', 'close'"
            },
            "url": {
                "type": "string",
                "description": "目标URL（用于goto操作）"
            },
            "selector": {
                "type": "string",
                "description": "元素选择器（用于click, type等操作）"
            },
            "text": {
                "type": "string", 
                "description": "要输入的文本（用于type操作）"
            },
            "path": {
                "type": "string",
                "description": "保存文件的路径（用于screenshot操作）"
            },
            "query": {
                "type": "string",
                "description": "从页面内容中提取的信息描述（用于extract操作）"
            }
        },
        "required": ["action"]
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行浏览器操作

        参数:
            args: 包含操作参数的字典，包括agent属性

        返回:
            字典，包含以下内容：
                - success: 布尔值，表示操作状态
                - stdout: 成功消息或操作结果
                - stderr: 错误消息或空字符串
        """
        # 获取agent对象
        agent = args.get("agent")
        if agent is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": "未提供agent对象"
            }
            
        # 确保agent有browser属性字典
        if not hasattr(agent, "browser_data"):
            agent.browser_data = {
                "browser": None,
                "context": None,
                "page": None,
                "playwright": None
            }
            
        action = args.get("action", "").strip().lower()
        
        # 验证操作类型
        valid_actions = ['launch', 'goto', 'screenshot', 'extract', 'click', 'type', 'close']
        if action not in valid_actions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"不支持的操作: {action}。有效操作: {', '.join(valid_actions)}"
            }
            
        try:
            if agent.browser_data["browser"] is None or agent.browser_data["page"] is None:
                with yaspin(Spinners.dots, text="正在启动浏览器...") as spinner:
                    if not self._launch_browser(agent):
                        spinner.text = "启动浏览器失败"
                        spinner.fail("❌")
                        return {
                            "success": False,
                            "stdout": "",
                            "stderr": "启动浏览器失败"
                        }
                    spinner.text = "启动浏览器成功"
                    spinner.ok("✅")
            
            # 在操作前先截图（对于非launch和close操作）
            if action not in ['launch', 'close'] and agent.browser_data["page"] is not None:
                self._auto_screenshot(agent, action)
                    
            if action == "close":
                with yaspin(Spinners.dots, text="正在关闭浏览器...") as spinner:
                    result = self._close_browser(agent)
                    if result["success"]:
                        spinner.text = "关闭浏览器成功"
                        spinner.ok("✅")
                    else:
                        spinner.text = "关闭浏览器失败"
                        spinner.fail("❌")
                    return result
            elif action == "goto":
                url = args.get("url", "").strip()
                with yaspin(Spinners.dots, text=f"正在导航到 {url}...") as spinner:
                    result = self._goto_url(agent, args)
                    if result["success"]:
                        spinner.text = f"导航到 {url} 成功"
                        spinner.ok("✅")
                    else:
                        spinner.text = f"导航到 {url} 失败"
                        spinner.fail("❌")
                    return result
            elif action == "screenshot":
                path = args.get("path", "screenshot.png").strip()
                with yaspin(Spinners.dots, text=f"正在截取页面截图...") as spinner:
                    result = self._take_screenshot(agent, args)
                    if result["success"]:
                        spinner.text = f"截取页面截图成功"
                        spinner.ok("✅")
                    else:
                        spinner.text = f"截取页面截图失败"
                        spinner.fail("❌")
                    return result
            elif action == "extract":
                query = args.get("query", "").strip()
                with yaspin(Spinners.dots, text=f"正在提取信息: {query}...") as spinner:
                    result = self._extract_information(agent, args)
                    if result["success"]:
                        spinner.text = f"提取信息成功"
                        spinner.ok("✅")
                    else:
                        spinner.text = f"提取信息失败"
                        spinner.fail("❌")
                    return result
            elif action == "click":
                selector = args.get("selector", "").strip()
                with yaspin(Spinners.dots, text=f"正在点击元素: {selector}...") as spinner:
                    result = self._click_element(agent, args)
                    if result["success"]:
                        spinner.text = f"点击元素 {selector} 成功"
                        spinner.ok("✅")
                    else:
                        spinner.text = f"点击元素 {selector} 失败"
                        spinner.fail("❌")
                    return result
            elif action == "type":
                selector = args.get("selector", "").strip()
                with yaspin(Spinners.dots, text=f"正在输入文本到元素: {selector}...") as spinner:
                    result = self._type_text(agent, args)
                    if result["success"]:
                        spinner.text = f"输入文本到元素 {selector} 成功"
                        spinner.ok("✅")
                    else:
                        spinner.text = f"输入文本到元素 {selector} 失败"
                        spinner.fail("❌")
                    return result
            return {
                "success": False,
                "stdout": "",
                "stderr": "不支持的操作"
            }
            
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"执行浏览器操作出错: {str(e)}"
            }
    
    def _auto_screenshot(self, agent: Any, action: str) -> None:
        """在执行操作前自动截图"""
        try:
            # 获取agent名称，默认为"unknown"
            agent_name = getattr(agent, "name", "unknown")
            
            # 创建截图保存目录
            screenshot_dir = Path.home() / ".jarvis" / f"{agent_name}-browser"
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            
            # 生成带时间戳的文件名
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            screenshot_path = screenshot_dir / f"{timestamp}-{action}.png"
            
            # 尝试截图
            agent.browser_data["page"].screenshot(path=str(screenshot_path))
        except Exception:
            # 自动截图失败不应影响主要操作，所以捕获异常但不报错
            pass
    
    def _launch_browser(self, agent: Any) -> bool:
        browser_type = "chromium"
        headless = True
        
        # 固定视口大小为1920x1080
        viewport_width = 1920
        viewport_height = 1080
        
        try:
            playwright = sync_playwright().start()
            agent.browser_data["playwright"] = playwright
            
            browser = playwright.chromium.launch(headless=headless)
            
            # 创建具有固定1920x1080视口大小的上下文
            context = browser.new_context(
                viewport={'width': viewport_width, 'height': viewport_height}
            )
            page = context.new_page()
            
            # 存储浏览器实例到agent属性中
            agent.browser_data["browser"] = browser
            agent.browser_data["context"] = context
            agent.browser_data["page"] = page
            
            return True
        except Exception as e:
            return False
    
    def _close_browser(self, agent: Any) -> Dict[str, Any]:
        """关闭浏览器"""
        if agent.browser_data["browser"] is None:
            return {
                "success": True,
                "stdout": "没有正在运行的浏览器",
                "stderr": ""
            }
        
        try:
            # 在关闭前截一张最终状态的截图
            if agent.browser_data["page"] is not None:
                self._auto_screenshot(agent, "final")
                
            agent.browser_data["browser"].close()
            
            # 如果playwright存在，关闭它
            if agent.browser_data["playwright"] is not None:
                agent.browser_data["playwright"].stop()
                
            # 清除浏览器实例
            agent.browser_data = {
                "browser": None,
                "context": None,
                "page": None,
                "playwright": None
            }
            
            return {
                "success": True,
                "stdout": "浏览器已关闭",
                "stderr": ""
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"关闭浏览器失败: {str(e)}"
            }
    
    def _goto_url(self, agent: Any, args: Dict[str, Any]) -> Dict[str, Any]:
        """导航到指定URL"""
        url = args.get("url", "").strip()
        if not url:
            return {
                "success": False,
                "stdout": "",
                "stderr": "未提供URL"
            }
            
        try:
            agent.browser_data["page"].goto(url)
            return {
                "success": True,
                "stdout": f"成功导航到 {url}",
                "stderr": ""
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"导航到 {url} 失败: {str(e)}"
            }
    
    def _take_screenshot(self, agent: Any, args: Dict[str, Any]) -> Dict[str, Any]:
        """截取页面截图"""
        path = args.get("path", "screenshot.png").strip()
        
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            
            agent.browser_data["page"].screenshot(path=path)
            abs_path = os.path.abspath(path)
            
            return {
                "success": True,
                "stdout": f"已保存截图到 {abs_path}",
                "stderr": ""
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"截图失败: {str(e)}"
            }
    
    def _extract_information(self, agent: Any, args: Dict[str, Any]) -> Dict[str, Any]:
        """从页面提取特定信息"""
        query = args.get("query", "").strip()
        if not query:
            return {
                "success": False,
                "stdout": "",
                "stderr": "未提供提取信息的查询"
            }
            
        try:
            # 获取页面内容
            content = agent.browser_data["page"].content()
            page_title = agent.browser_data["page"].title()
            page_url = agent.browser_data["page"].url
            
            # 页面基本信息
            context_info = f"页面标题: {page_title}\n页面URL: {page_url}\n\n"
            
            prompt = f"""
            从以下网页内容中提取有关"{query}"的信息。
            如果找不到相关信息，请回答"在页面中未找到关于'{query}'的信息"。
            提取的信息应该简洁、准确，并直接回答查询，不要包含额外的解释。

            网页内容:
            {content}"""

            if get_context_token_count(prompt) > get_max_token_count() - 2048:
                pass

            model = PlatformRegistry().get_thinking_platform()
            result = model.chat_until_success(prompt)
            return {
                "success": True,
                "stdout": f"{context_info}提取结果: \n\n{result}",
                "stderr": ""
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"提取信息失败: {str(e)}"
            }
    
    def _click_element(self, agent: Any, args: Dict[str, Any]) -> Dict[str, Any]:
        """点击页面元素"""
        selector = args.get("selector", "").strip()
        if not selector:
            return {
                "success": False,
                "stdout": "",
                "stderr": "未提供元素选择器"
            }
            
        try:
            agent.browser_data["page"].click(selector)
            return {
                "success": True,
                "stdout": f"成功点击元素: {selector}",
                "stderr": ""
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"点击元素 {selector} 失败: {str(e)}"
            }
    
    def _type_text(self, agent: Any, args: Dict[str, Any]) -> Dict[str, Any]:
        """在元素中输入文本"""
        selector = args.get("selector", "").strip()
        text = args.get("text", "")
        
        if not selector:
            return {
                "success": False,
                "stdout": "",
                "stderr": "未提供元素选择器"
            }
            
        try:
            agent.browser_data["page"].fill(selector, text)
            return {
                "success": True,
                "stdout": f"成功在元素 {selector} 中输入文本",
                "stderr": ""
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"在元素 {selector} 中输入文本失败: {str(e)}"
            }
