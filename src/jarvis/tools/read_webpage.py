from typing import Dict, Any
import requests
from bs4 import BeautifulSoup
from jarvis.utils import PrettyOutput, OutputType

class WebpageTool:
    name = "read_webpage"
    description = "Read webpage content, extract title and text"
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL of the webpage to read"
            }
        },
        "required": ["url"]
    }

    def execute(self, args: Dict) -> Dict[str, Any]:
        """Read webpage content"""
        try:
            url = args["url"]
            
            # Set request headers
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            # Send request
            PrettyOutput.print(f"Reading webpage: {url}", OutputType.INFO)
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
            
            # Extract text
            text = soup.get_text(separator='\n', strip=True)
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            
            # Build output
            output = [
                f"Title: {title}",
                "",
                "Text content:",
                "\n".join(lines)
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