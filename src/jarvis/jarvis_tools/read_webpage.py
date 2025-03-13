from typing import Dict, Any
import requests
from bs4 import BeautifulSoup

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
            PrettyOutput.print(f"正在读取网页：{url}", OutputType.INFO)
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            # Use correct encoding
            response.encoding = response.apparent_encoding
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove script and style tags
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Extract title
            title = soup.title.string if soup.title else ""
            title = title.strip() if title else "No title"
            
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
            
            # Build output
            output = [
                f"Title: {title}",
                "",
                "Text content:",
                "\n".join(text_parts),
                "",
                "Links found:",
                "\n".join(links) if links else "No links found"
            ]
            
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