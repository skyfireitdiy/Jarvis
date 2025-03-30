from typing import Dict, Any, List
import os
from datetime import datetime
from pathlib import Path
from yaspin import yaspin
from yaspin.spinners import Spinners
from playwright.sync_api import sync_playwright

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.config import get_max_token_count
from jarvis.jarvis_utils.embedding import get_context_token_count

class BrowserTool:
    name = "browser"
    description = "控制无头浏览器执行各种操作，如导航、截图和获取内容。（如果需要搜索信息，优先使用Bing搜索引擎）"
    labels = ['web', 'automation']
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "要执行的浏览器操作，可选值: 'launch', 'goto', 'screenshot', 'extract', 'click', 'type', 'close', 'wait', 'scroll', 'hover', 'select', 'check', 'uncheck', 'press', 'evaluate', 'reload', 'back', 'forward'"
            },
            "url": {
                "type": "string",
                "description": "目标URL（用于goto操作）"
            },
            "selector": {
                "type": "string",
                "description": "元素选择器，支持CSS选择器或XPath。XPath以'/'或'//'开头，例如：'/html/body/div[2]/form/input[1]'或'//input[@type=\"text\"]'（用于click, type等操作）"
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
            },
            "use_xpath": {
                "type": "boolean",
                "description": "是否使用XPath选择器（默认为false，使用CSS选择器）",
                "default": False
            },
            "wait_time": {
                "type": "number",
                "description": "等待时间（毫秒），用于wait操作",
                "default": 5000
            },
            "wait_for": {
                "type": "string",
                "description": "等待条件，可选值：'load', 'networkidle', 'domcontentloaded'",
                "enum": ["load", "networkidle", "domcontentloaded"]
            },
            "scroll_amount": {
                "type": "number",
                "description": "滚动距离（像素），用于scroll操作"
            },
            "key": {
                "type": "string",
                "description": "要按下的按键，用于press操作"
            },
            "value": {
                "type": "string",
                "description": "选择的值，用于select操作"
            },
            "script": {
                "type": "string",
                "description": "要执行的JavaScript代码，用于evaluate操作"
            },
            "timeout": {
                "type": "number",
                "description": "操作超时时间（毫秒）",
                "default": 30000
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
        valid_actions = ['launch', 'goto', 'screenshot', 'extract', 'click', 'type', 'close', 'wait', 'scroll', 'hover', 'select', 'check', 'uncheck', 'press', 'evaluate', 'reload', 'back', 'forward']
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
            elif action == "wait":
                with yaspin(Spinners.dots, text="等待页面加载...") as spinner:
                    result = self._wait_for(agent, args)
                    if result["success"]:
                        spinner.text = "等待完成"
                        spinner.ok("✅")
                    else:
                        spinner.text = "等待失败"
                        spinner.fail("❌")
                    return result
            elif action == "scroll":
                with yaspin(Spinners.dots, text="滚动页面...") as spinner:
                    result = self._scroll_page(agent, args)
                    if result["success"]:
                        spinner.text = "滚动完成"
                        spinner.ok("✅")
                    else:
                        spinner.text = "滚动失败"
                        spinner.fail("❌")
                    return result
            elif action == "hover":
                with yaspin(Spinners.dots, text="悬停在元素上...") as spinner:
                    result = self._hover_element(agent, args)
                    if result["success"]:
                        spinner.text = "悬停完成"
                        spinner.ok("✅")
                    else:
                        spinner.text = "悬停失败"
                        spinner.fail("❌")
                    return result
            elif action == "select":
                with yaspin(Spinners.dots, text="选择选项...") as spinner:
                    result = self._select_option(agent, args)
                    if result["success"]:
                        spinner.text = "选择完成"
                        spinner.ok("✅")
                    else:
                        spinner.text = "选择失败"
                        spinner.fail("❌")
                    return result
            elif action == "check":
                with yaspin(Spinners.dots, text="勾选元素...") as spinner:
                    result = self._check_element(agent, args)
                    if result["success"]:
                        spinner.text = "勾选完成"
                        spinner.ok("✅")
                    else:
                        spinner.text = "勾选失败"
                        spinner.fail("❌")
                    return result
            elif action == "uncheck":
                with yaspin(Spinners.dots, text="取消勾选元素...") as spinner:
                    result = self._uncheck_element(agent, args)
                    if result["success"]:
                        spinner.text = "取消勾选完成"
                        spinner.ok("✅")
                    else:
                        spinner.text = "取消勾选失败"
                        spinner.fail("❌")
                    return result
            elif action == "press":
                with yaspin(Spinners.dots, text="按下按键...") as spinner:
                    result = self._press_key(agent, args)
                    if result["success"]:
                        spinner.text = "按键完成"
                        spinner.ok("✅")
                    else:
                        spinner.text = "按键失败"
                        spinner.fail("❌")
                    return result
            elif action == "evaluate":
                with yaspin(Spinners.dots, text="执行JavaScript...") as spinner:
                    result = self._evaluate_script(agent, args)
                    if result["success"]:
                        spinner.text = "执行完成"
                        spinner.ok("✅")
                    else:
                        spinner.text = "执行失败"
                        spinner.fail("❌")
                    return result
            elif action == "reload":
                with yaspin(Spinners.dots, text="重新加载页面...") as spinner:
                    result = self._reload_page(agent)
                    if result["success"]:
                        spinner.text = "重新加载完成"
                        spinner.ok("✅")
                    else:
                        spinner.text = "重新加载失败"
                        spinner.fail("❌")
                    return result
            elif action == "back":
                with yaspin(Spinners.dots, text="返回上一页...") as spinner:
                    result = self._go_back(agent)
                    if result["success"]:
                        spinner.text = "返回完成"
                        spinner.ok("✅")
                    else:
                        spinner.text = "返回失败"
                        spinner.fail("❌")
                    return result
            elif action == "forward":
                with yaspin(Spinners.dots, text="前进到下一页...") as spinner:
                    result = self._go_forward(agent)
                    if result["success"]:
                        spinner.text = "前进完成"
                        spinner.ok("✅")
                    else:
                        spinner.text = "前进失败"
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
            
            # 提取交互元素和展示元素
            from jarvis.jarvis_utils.utils import extract_interactive_elements, extract_display_elements
            interactive_elements = extract_interactive_elements(content)
            display_elements = extract_display_elements(content)
            
            # 构建结构化信息
            structured_info = {
                "page_info": {
                    "title": page_title,
                    "url": page_url
                },
                "interactive_elements": interactive_elements,
                "display_elements": display_elements
            }
            
            # 页面基本信息
            context_info = f"页面标题: {page_title}\n页面URL: {page_url}\n\n"
            
            # 构建提示信息
            prompt = f"""
            从以下网页内容中提取有关"{query}"的信息。
            如果找不到相关信息，请回答"在页面中未找到关于'{query}'的信息"，并给出下一步推荐的操作。
            提取的信息应该简洁、准确，并直接回答查询，不要包含额外的解释。

            页面结构信息:
            - 可交互元素数量: {len(interactive_elements)}
            - 展示元素数量: {len(display_elements)}
            
            可交互元素:
            {self._format_elements(interactive_elements)}
            
            展示元素:
            {self._format_elements(display_elements)}
            """

            # 检查token限制
            if get_context_token_count(prompt) > get_max_token_count() - 2048:
                # 尝试转换为markdown格式
                from jarvis.jarvis_utils.utils import html_to_markdown
                markdown_content = html_to_markdown(content, page_url)
                markdown_prompt = f"""
                从以下网页内容中提取有关"{query}"的信息。
                如果找不到相关信息，请回答"在页面中未找到关于'{query}'的信息"，并给出下一步推荐的操作。
                提取的信息应该简洁、准确，并直接回答查询，不要包含额外的解释。

                页面结构信息:
                - 可交互元素数量: {len(interactive_elements)}
                - 展示元素数量: {len(display_elements)}
                
                可交互元素:
                {self._format_elements(interactive_elements)}
                
                展示元素:
                {self._format_elements(display_elements)}
                
                网页内容(已转换为Markdown):
                {markdown_content}"""
                
                # 再次检查token限制
                if get_context_token_count(markdown_prompt) > get_max_token_count() - 2048:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "网页内容过大，无法处理"
                    }
                prompt = markdown_prompt

            model = PlatformRegistry().get_thinking_platform()
            result = model.chat_until_success(prompt)
            return {
                "success": True,
                "stdout": f"{context_info}提取结果: \n\n{result}",
                "stderr": "",
                "structured_data": structured_info  # 添加结构化数据到返回结果
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"提取信息失败: {str(e)}"
            }
            
    def _format_elements(self, elements: List[Dict[str, Any]]) -> str:
        """格式化元素列表为易读的字符串"""
        if not elements:
            return "无"
            
        formatted = []
        for i, element in enumerate(elements, 1):
            element_info = []
            
            # 基本属性
            element_info.append(f"元素 {i}:")
            element_info.append(f"- 标签: {element['tag']}")
            element_info.append(f"- 文本: {element['text']}")
            element_info.append(f"- XPath: {element['xpath']}")
            
            # 特殊属性
            if 'heading_level' in element:
                element_info.append(f"- 标题级别: {element['heading_level']}")
            if 'is_clickable' in element:
                element_info.append(f"- 可点击: {element['is_clickable']}")
            if 'is_input' in element:
                element_info.append(f"- 输入类型: {element.get('input_type', 'text')}")
                element_info.append(f"- 名称: {element.get('name', '')}")
                element_info.append(f"- 值: {element.get('value', '')}")
            if 'is_select' in element:
                element_info.append(f"- 选项: {len(element.get('options', []))}个")
            if 'is_list' in element:
                element_info.append(f"- 列表项: {len(element.get('list_items', []))}个")
            if 'is_table' in element:
                element_info.append(f"- 表格行: {len(element.get('table_rows', []))}行")
            
            formatted.append("\n".join(element_info))
            
        return "\n\n".join(formatted)
    
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
            # 判断是否使用XPath选择器
            use_xpath = args.get("use_xpath", False) or selector.startswith('/') or selector.startswith('//')
            if use_xpath:
                agent.browser_data["page"].locator(f"xpath={selector}").click()
            else:
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
            # 判断是否使用XPath选择器
            use_xpath = args.get("use_xpath", False) or selector.startswith('/') or selector.startswith('//')
            if use_xpath:
                agent.browser_data["page"].locator(f"xpath={selector}").fill(text)
            else:
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

    def _wait_for(self, agent: Any, args: Dict[str, Any]) -> Dict[str, Any]:
        """等待页面加载或元素出现"""
        wait_for = args.get("wait_for", "load")
        wait_time = args.get("wait_time", 5000)
        selector = args.get("selector", "")
        
        try:
            if selector:
                # 等待元素出现
                use_xpath = args.get("use_xpath", False) or selector.startswith('/') or selector.startswith('//')
                if use_xpath:
                    agent.browser_data["page"].wait_for_selector(f"xpath={selector}", timeout=wait_time)
                else:
                    agent.browser_data["page"].wait_for_selector(selector, timeout=wait_time)
            else:
                # 等待页面状态
                if wait_for == "load":
                    agent.browser_data["page"].wait_for_load_state("load", timeout=wait_time)
                elif wait_for == "networkidle":
                    agent.browser_data["page"].wait_for_load_state("networkidle", timeout=wait_time)
                elif wait_for == "domcontentloaded":
                    agent.browser_data["page"].wait_for_load_state("domcontentloaded", timeout=wait_time)
                    
            return {
                "success": True,
                "stdout": f"等待完成: {wait_for if not selector else f'元素 {selector}'}",
                "stderr": ""
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"等待失败: {str(e)}"
            }

    def _scroll_page(self, agent: Any, args: Dict[str, Any]) -> Dict[str, Any]:
        """滚动页面"""
        scroll_amount = args.get("scroll_amount", 0)
        
        try:
            agent.browser_data["page"].evaluate(f"window.scrollBy(0, {scroll_amount})")
            return {
                "success": True,
                "stdout": f"页面已滚动 {scroll_amount} 像素",
                "stderr": ""
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"滚动失败: {str(e)}"
            }

    def _hover_element(self, agent: Any, args: Dict[str, Any]) -> Dict[str, Any]:
        """悬停在元素上"""
        selector = args.get("selector", "").strip()
        if not selector:
            return {
                "success": False,
                "stdout": "",
                "stderr": "未提供元素选择器"
            }
            
        try:
            use_xpath = args.get("use_xpath", False) or selector.startswith('/') or selector.startswith('//')
            if use_xpath:
                agent.browser_data["page"].locator(f"xpath={selector}").hover()
            else:
                agent.browser_data["page"].hover(selector)
                
            return {
                "success": True,
                "stdout": f"成功悬停在元素上: {selector}",
                "stderr": ""
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"悬停失败: {str(e)}"
            }

    def _select_option(self, agent: Any, args: Dict[str, Any]) -> Dict[str, Any]:
        """选择下拉选项"""
        selector = args.get("selector", "").strip()
        value = args.get("value", "")
        
        if not selector or not value:
            return {
                "success": False,
                "stdout": "",
                "stderr": "未提供选择器或值"
            }
            
        try:
            use_xpath = args.get("use_xpath", False) or selector.startswith('/') or selector.startswith('//')
            if use_xpath:
                agent.browser_data["page"].locator(f"xpath={selector}").select_option(value=value)
            else:
                agent.browser_data["page"].select_option(selector, value=value)
                
            return {
                "success": True,
                "stdout": f"成功选择选项: {value}",
                "stderr": ""
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"选择选项失败: {str(e)}"
            }

    def _check_element(self, agent: Any, args: Dict[str, Any]) -> Dict[str, Any]:
        """勾选复选框"""
        selector = args.get("selector", "").strip()
        if not selector:
            return {
                "success": False,
                "stdout": "",
                "stderr": "未提供元素选择器"
            }
            
        try:
            use_xpath = args.get("use_xpath", False) or selector.startswith('/') or selector.startswith('//')
            if use_xpath:
                agent.browser_data["page"].locator(f"xpath={selector}").check()
            else:
                agent.browser_data["page"].check(selector)
                
            return {
                "success": True,
                "stdout": f"成功勾选元素: {selector}",
                "stderr": ""
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"勾选失败: {str(e)}"
            }

    def _uncheck_element(self, agent: Any, args: Dict[str, Any]) -> Dict[str, Any]:
        """取消勾选复选框"""
        selector = args.get("selector", "").strip()
        if not selector:
            return {
                "success": False,
                "stdout": "",
                "stderr": "未提供元素选择器"
            }
            
        try:
            use_xpath = args.get("use_xpath", False) or selector.startswith('/') or selector.startswith('//')
            if use_xpath:
                agent.browser_data["page"].locator(f"xpath={selector}").uncheck()
            else:
                agent.browser_data["page"].uncheck(selector)
                
            return {
                "success": True,
                "stdout": f"成功取消勾选元素: {selector}",
                "stderr": ""
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"取消勾选失败: {str(e)}"
            }

    def _press_key(self, agent: Any, args: Dict[str, Any]) -> Dict[str, Any]:
        """按下按键"""
        key = args.get("key", "")
        if not key:
            return {
                "success": False,
                "stdout": "",
                "stderr": "未提供按键"
            }
            
        try:
            agent.browser_data["page"].keyboard.press(key)
            return {
                "success": True,
                "stdout": f"成功按下按键: {key}",
                "stderr": ""
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"按键失败: {str(e)}"
            }

    def _evaluate_script(self, agent: Any, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行JavaScript代码"""
        script = args.get("script", "")
        if not script:
            return {
                "success": False,
                "stdout": "",
                "stderr": "未提供JavaScript代码"
            }
            
        try:
            result = agent.browser_data["page"].evaluate(script)
            return {
                "success": True,
                "stdout": f"执行结果: {result}",
                "stderr": ""
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"执行失败: {str(e)}"
            }

    def _reload_page(self, agent: Any) -> Dict[str, Any]:
        """重新加载页面"""
        try:
            agent.browser_data["page"].reload()
            return {
                "success": True,
                "stdout": "页面已重新加载",
                "stderr": ""
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"重新加载失败: {str(e)}"
            }

    def _go_back(self, agent: Any) -> Dict[str, Any]:
        """返回上一页"""
        try:
            agent.browser_data["page"].go_back()
            return {
                "success": True,
                "stdout": "已返回上一页",
                "stderr": ""
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"返回失败: {str(e)}"
            }

    def _go_forward(self, agent: Any) -> Dict[str, Any]:
        """前进到下一页"""
        try:
            agent.browser_data["page"].go_forward()
            return {
                "success": True,
                "stdout": "已前进到下一页",
                "stderr": ""
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"前进失败: {str(e)}"
            }
