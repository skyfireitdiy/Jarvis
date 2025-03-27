from typing import Dict, Any, Optional, List
import os
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
from typing import Dict, Any, Optional, List

class BrowserTool:
    name = "browser"
    description = "控制无头浏览器执行各种操作，如导航、截图和获取内容"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "要执行的浏览器操作，可选值: 'launch', 'goto', 'screenshot', 'content', 'click', 'type', 'close'"
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
            "browser_type": {
                "type": "string",
                "description": "浏览器类型: 'chromium', 'firefox', 或 'webkit'",
                "default": "chromium"
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
        valid_actions = ['launch', 'goto', 'screenshot', 'content', 'click', 'type', 'close']
        if action not in valid_actions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"不支持的操作: {action}。有效操作: {', '.join(valid_actions)}"
            }
            
        try:
            # 根据操作类型执行相应的方法
            if action == "launch":
                return self._launch_browser(agent, args)
            elif action == "close":
                return self._close_browser(agent)
            elif agent.browser_data["browser"] is None or agent.browser_data["page"] is None:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "浏览器未启动。请先使用 'launch' 操作启动浏览器。"
                }
            elif action == "goto":
                return self._goto_url(agent, args)
            elif action == "screenshot":
                return self._take_screenshot(agent, args)
            elif action == "content":
                return self._get_content(agent)
            elif action == "click":
                return self._click_element(agent, args)
            elif action == "type":
                return self._type_text(agent, args)
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
    
    def _launch_browser(self, agent: Any, args: Dict[str, Any]) -> Dict[str, Any]:
        """启动浏览器"""
        if agent.browser_data["browser"] is not None:
            return {
                "success": True,
                "stdout": "浏览器已经在运行",
                "stderr": ""
            }
            
        browser_type = args.get("browser_type", "chromium").lower()
        headless = True
        
        # 固定视口大小为1920x1080
        viewport_width = 1920
        viewport_height = 1080
        
        try:
            playwright = sync_playwright().start()
            agent.browser_data["playwright"] = playwright
            
            if browser_type == "chromium":
                browser = playwright.chromium.launch(headless=headless)
            elif browser_type == "firefox":
                browser = playwright.firefox.launch(headless=headless)
            elif browser_type == "webkit":
                browser = playwright.webkit.launch(headless=headless)
            else:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"不支持的浏览器类型: {browser_type}。支持的类型: chromium, firefox, webkit"
                }
            
            # 创建具有固定1920x1080视口大小的上下文
            context = browser.new_context(
                viewport={'width': viewport_width, 'height': viewport_height}
            )
            page = context.new_page()
            
            # 存储浏览器实例到agent属性中
            agent.browser_data["browser"] = browser
            agent.browser_data["context"] = context
            agent.browser_data["page"] = page
            
            return {
                "success": True,
                "stdout": f"成功启动 {browser_type} 浏览器，视口大小: 1920x1080",
                "stderr": ""
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"启动浏览器失败: {str(e)}"
            }
    
    def _close_browser(self, agent: Any) -> Dict[str, Any]:
        """关闭浏览器"""
        if agent.browser_data["browser"] is None:
            return {
                "success": True,
                "stdout": "没有正在运行的浏览器",
                "stderr": ""
            }
        
        try:
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
    
    def _get_content(self, agent: Any) -> Dict[str, Any]:
        """获取页面内容"""
        try:
            content = agent.browser_data["page"].content()
            return {
                "success": True,
                "stdout": content,
                "stderr": ""
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"获取页面内容失败: {str(e)}"
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
