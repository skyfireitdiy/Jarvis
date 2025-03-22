from typing import Dict, Any
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup, Tag
from urllib.parse import urlparse, urljoin
import re

from jarvis.jarvis_utils.output import OutputType, PrettyOutput

class WebpageTool:
    name = "read_webpage"
    description = "读取网页内容，提取标题、文本和超链接"
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

    def execute(self, args: Dict) -> Dict[str, Any]:
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
                markdown_content = self._html_to_markdown(html_content, url)
                
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
    
    def _create_soup_element(self, content):
        """Safely create a BeautifulSoup element, ensuring it's treated as markup"""
        if isinstance(content, str):
            # Create a wrapper tag to ensure proper parsing
            soup_div = BeautifulSoup(f"<div>{content}</div>", 'html.parser').div
            if soup_div is not None:
                return soup_div.contents
            # Return an empty list if the div is None
            return []
        return content
    
    def _html_to_markdown(self, html_content: str, base_url: str) -> str:
        """Convert HTML to Markdown format preserving the content structure"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove unwanted elements
        for element in soup(['script', 'style', 'meta', 'noscript', 'head']):
            element.decompose()
        
        # Process headings
        for level in range(1, 7):
            for heading in soup.find_all(f'h{level}'):
                text = heading.get_text().strip()
                heading_md = "\n\n" + "#" * level + " " + text + "\n\n"
                new_element = self._create_soup_element(heading_md)
                heading.replace_with(*new_element)
        
        # Process paragraphs
        for p in soup.find_all('p'):
            text = p.get_text().strip()
            if text:
                new_element = self._create_soup_element("\n\n" + text + "\n\n")
                p.replace_with(*new_element)
        
        # Process unordered lists
        for ul in soup.find_all('ul'):
            items = []
            for li in ul.find_all('li', recursive=False):
                items.append("* " + li.get_text().strip())
            new_element = self._create_soup_element("\n\n" + "\n".join(items) + "\n\n")
            ul.replace_with(*new_element)
        
        # Process ordered lists
        for ol in soup.find_all('ol'):
            items = []
            for i, li in enumerate(ol.find_all('li', recursive=False), 1):
                items.append(str(i) + ". " + li.get_text().strip())
            new_element = self._create_soup_element("\n\n" + "\n".join(items) + "\n\n")
            ol.replace_with(*new_element)
        
        # Process links (first pass)
        for a in soup.find_all('a', href=True):
            try:
                href = a['href']
                text = a.get_text().strip()
                if text and href:
                    # Convert relative URLs to absolute
                    if href.startswith('/') and not href.startswith('//'):
                        href = urljoin(base_url, href)
                    link_md = "[" + text + "](" + href + ")"
                    new_element = self._create_soup_element(link_md)
                    a.replace_with(*new_element)
            except (KeyError, AttributeError):
                continue
        
        # Process images
        for img in soup.find_all('img', src=True):
            try:
                src = img['src']
                alt = img.get('alt', 'Image').strip()
                # Convert relative URLs to absolute
                if src.startswith('/') and not src.startswith('//'):
                    src = urljoin(base_url, src)
                img_md = "![" + alt + "](" + src + ")"
                new_element = self._create_soup_element(img_md)
                img.replace_with(*new_element)
            except (KeyError, AttributeError, UnboundLocalError):
                continue
        
        # Process code blocks
        for pre in soup.find_all('pre'):
            code = pre.get_text().strip()
            pre_md = "\n\n```\n" + code + "\n```\n\n"
            new_element = self._create_soup_element(pre_md)
            pre.replace_with(*new_element)
        
        # Process inline code
        for code in soup.find_all('code'):
            text = code.get_text().strip()
            code_md = "`" + text + "`"
            new_element = self._create_soup_element(code_md)
            code.replace_with(*new_element)
        
        # Process line breaks
        for br in soup.find_all('br'):
            new_element = self._create_soup_element('\n')
            br.replace_with(*new_element)
        
        # Get the full text
        markdown_text = soup.get_text()
        
        # Clean up extra whitespace and line breaks
        markdown_text = re.sub(r'\n{3,}', '\n\n', markdown_text)
        markdown_text = re.sub(r'\s{2,}', ' ', markdown_text)
        
        # Process links again (for any that might have been missed)
        link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
        all_links = re.findall(link_pattern, markdown_text)
        
        # Add a section with all links at the end
        if all_links:
            link_section = ["", "## Links", ""]
            seen_links = set()
            for text, href in all_links:
                link_entry = "[" + text + "](" + href + ")"
                if link_entry not in seen_links:
                    link_section.append(link_entry)
                    seen_links.add(link_entry)
            
            markdown_text += "\n\n" + "\n".join(link_section)
        
        return markdown_text.strip() 