from typing import Dict, Any
import requests
from bs4 import BeautifulSoup
from ..utils import PrettyOutput, OutputType

class WebpageTool:
    name = "read_webpage"
    description = "Read webpage content, supporting extraction of main text, title, and other information"
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL of the webpage to read"
            },
            "extract_type": {
                "type": "string",
                "description": "Type of content to extract: 'text', 'title', or 'all'",
                "enum": ["text", "title", "all"],
                "default": "all"
            }
        },
        "required": ["url"]
    }

    def execute(self, args: Dict) -> Dict[str, Any]:
        """读取网页内容"""
        try:
            url = args["url"]
            extract_type = args.get("extract_type", "all")
            
            # 设置请求头
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            # 发送请求
            PrettyOutput.print(f"正在读取网页: {url}", OutputType.INFO)
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            # 使用正确的编码
            response.encoding = response.apparent_encoding
            
            # 解析HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 移除script和style标签
            for script in soup(["script", "style"]):
                script.decompose()
            
            result = {}
            
            # 提取标题
            if extract_type in ["title", "all"]:
                title = soup.title.string if soup.title else ""
                result["title"] = title.strip() if title else "无标题"
            
            # 提取正文
            if extract_type in ["text", "all"]:
                text = soup.get_text(separator='\n', strip=True)
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                result["text"] = "\n".join(lines)
            
            # 构建输出
            output = []
            if "title" in result:
                output.append(f"标题: {result['title']}")
                output.append("")
            
            if "text" in result:
                output.append("正文内容:")
                output.append(result["text"])
            
            return {
                "success": True,
                "stdout": "\n".join(output),
                "stderr": ""
            }

        except requests.RequestException as e:
            return {
                "success": False,
                "error": f"网页请求失败: {str(e)}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"解析网页失败: {str(e)}"
            } 