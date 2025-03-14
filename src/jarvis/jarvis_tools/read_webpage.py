from typing import Dict, Any
import requests
from bs4 import BeautifulSoup
from yaspin import yaspin

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
        """Read webpage content"""
        try:
            url = args["url"].strip()   
            
            # Set request headers
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            # Send request
            with yaspin(text="正在读取网页...", color="cyan") as spinner:
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                spinner.text = "网页读取完成"
                spinner.ok("✅")
                
            
            # Use correct encoding

            response.encoding = response.apparent_encoding
            
            # Parse HTML
            with yaspin(text="正在解析网页...", color="cyan") as spinner:
                soup = BeautifulSoup(response.text, 'html.parser')
                spinner.text = "网页解析完成"
                spinner.ok("✅")
            
            # Remove script and style tags
            with yaspin(text="正在移除脚本和样式...", color="cyan") as spinner:
                for script in soup(["script", "style"]):
                    script.decompose()
                spinner.text = "脚本和样式移除完成"
                spinner.ok("✅")
            
            # Extract title
            with yaspin(text="正在提取标题...", color="cyan") as spinner:
                title = soup.title.string if soup.title else ""
                title = title.strip() if title else "No title"
                spinner.text = "标题提取完成"
                spinner.ok("✅")
            
            with yaspin(text="正在提取文本和链接...", color="cyan") as spinner:
                # Extract text and links
                text_parts = []
                links = []
                
                # Process content and collect links
                for element in soup.descendants:
                    if element.name == 'a' and element.get('href'): # type: ignore
                        href = element.get('href') # type: ignore
                        text = element.get_text(strip=True)
                        if text and href:
                            links.append(f"[{text}]({href})")
                    elif isinstance(element, str) and element.strip():
                        text_parts.append(element.strip())
                spinner.text = "文本和链接提取完成"
                spinner.ok("✅")
            
            # Build output
            with yaspin(text="正在构建输出...", color="cyan") as spinner:
                output = [
                    f"Title: {title}",
                    "",
                    "Text content:",
                    "\n".join(text_parts),
                    "",
                    "Links found:",
                    "\n".join(links) if links else "No links found"
                ]
                spinner.text = "输出构建完成"
                spinner.ok("✅")
            
            return {
                "success": True,
                "stdout": "\n".join(output),
                "stderr": ""
            }

        except requests.RequestException as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Webpage request failed: {str(e)}"
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Failed to parse webpage: {str(e)}"
            } 