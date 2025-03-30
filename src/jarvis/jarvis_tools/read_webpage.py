from typing import Dict, Any, List, Union, Sequence, cast
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString  # 正确导入NavigableString
from urllib.parse import urlparse, urljoin
import re

from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import html_to_markdown

class WebpageTool:
    name = "read_webpage"
    description = "读取网页内容，提取标题、文本和超链接"
    labels = ['web', 'scraping']
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "要读取的网页URL"
            }
        },
        "required": ["url"]
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Read webpage content using Playwright to handle JavaScript-rendered pages"""
        try:
            url = args["url"].strip()

            with sync_playwright() as p:
                # Launch browser
                browser = p.chromium.launch(
                    headless=True,
                    args=['--disable-gpu', '--no-sandbox', '--disable-dev-shm-usage']
                )

                # Create a new page with appropriate settings
                page = browser.new_page(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080}
                )

                # Set timeout to avoid long waits
                page.set_default_timeout(30000)  # 30 seconds

                try:
                    # Navigate to URL and wait for page to load
                    response = page.goto(url, wait_until="domcontentloaded")

                    # Additional wait for network to be idle (with a timeout)
                    try:
                        page.wait_for_load_state("networkidle", timeout=10000)
                    except PlaywrightTimeoutError:
                        # Continue even if network doesn't become completely idle
                        pass

                    # Make sure we got a valid response
                    if not response or response.status >= 400:
                        raise Exception(f"Failed to load page: HTTP {response.status if response else 'No response'}")

                    # Get page title safely
                    title = "No title"
                    try:
                        title = page.title()
                    except Exception:
                        # Try to extract title from content if direct method fails
                        try:
                            title_element = page.query_selector("title")
                            if title_element:
                                title = title_element.text_content() or "No title"
                        except Exception:
                            pass

                    # Get the HTML content after JavaScript execution
                    html_content = page.content()

                except Exception as e:
                    raise Exception(f"Error navigating to page: {str(e)}")
                finally:
                    # Always close browser
                    browser.close()

                # Parse with BeautifulSoup and convert to markdown
                markdown_content = html_to_markdown(html_content, url)

                # Build output in markdown format
                output = [
                    f"# {title}",
                    f"Url: {url}",
                    markdown_content
                ]

                return {
                    "success": True,
                    "stdout": "\n".join(output),
                    "stderr": ""
                }

        except Exception as e:
            PrettyOutput.print(f"读取网页失败: {str(e)}", OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Failed to parse webpage: {str(e)}"
            }

    def _create_soup_element(self, content: Union[str, Tag, NavigableString]) -> List[Union[Tag, NavigableString]]:
        """Safely create a BeautifulSoup element, ensuring it's treated as markup"""
        if isinstance(content, str):
            # Create a wrapper tag to ensure proper parsing
            soup_div = BeautifulSoup(f"<div>{content}</div>", 'html.parser').div
            if soup_div is not None:
                return [child for child in soup_div.contents if isinstance(child, (Tag, NavigableString))]
            return []
        elif isinstance(content, (Tag, NavigableString)):
            return [content]
        return []

    def _html_to_markdown(self, html_content: str, base_url: str) -> str:
        """Convert HTML to Markdown format preserving the content structure"""
        from bs4 import BeautifulSoup, Tag
        from typing import List
        import re
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 类型安全的元素处理函数
        def process_element(element: Tag) -> None:
            # 处理标题
            if element.name and element.name.startswith('h') and len(element.name) == 2:
                level = int(element.name[1])
                text = str(element.get_text()).strip()
                element.replace_with(soup.new_string(f"\n\n{'#' * level} {text}\n\n"))
                return
                
            # 处理段落
            if element.name == 'p':
                text = str(element.get_text()).strip()
                if text:
                    element.replace_with(soup.new_string(f"\n\n{text}\n\n"))
                return
                
            # 处理列表
            if element.name in ('ul', 'ol'):
                items: List[str] = []
                for li in element.find_all('li', recursive=False):
                    if isinstance(li, Tag):
                        prefix = "* " if element.name == 'ul' else f"{len(items)+1}. "
                        items.append(prefix + str(li.get_text()).strip())
                element.replace_with(soup.new_string("\n\n" + "\n".join(items) + "\n\n"))
                return
                
            # 递归处理子元素
            for child in list(element.children):
                if isinstance(child, Tag):
                    process_element(child)
        
        # 处理整个文档
        if len(soup.contents) > 0 and isinstance(soup.contents[0], Tag):
            process_element(soup.contents[0])
        
        # 获取最终文本并清理格式
        markdown_text = str(soup)
        markdown_text = re.sub(r'<[^>]+>', '', markdown_text)  # 移除残留标签
        markdown_text = re.sub(r'\n{3,}', '\n\n', markdown_text)
        markdown_text = re.sub(r'\s{2,}', ' ', markdown_text)
        
        return markdown_text.strip()