from typing import Dict, Any
import os
from jarvis.jarvis_platform.registry import PlatformRegistry
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
            },
            "want": {
                "type": "string",
                "description": "具体想要从网页获取的信息或回答的问题",
                "default": "请总结这个网页的主要内容"
            }
        },
        "required": ["url"]
    }


    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Read webpage content using Yuanbao model"""
        try:
            url = args["url"].strip()
            want = args.get("want", "请总结这个网页的主要内容")
            
            # Create Yuanbao model instance
            model = PlatformRegistry().get_normal_platform()
            model.set_web(True)
            model.set_suppress_output(False)  # type: ignore

            # Construct prompt based on want parameter
            prompt = f"""请帮我处理这个网页：{url}
用户的具体需求是：{want}
请按照以下要求输出结果：
1. 使用Markdown格式
2. 包含网页标题
3. 根据用户需求提供准确、完整的信息"""

            # Get response from Yuanbao model
            response = model.chat_until_success(prompt)  # type: ignore

            return {
                "success": True,
                "stdout": response,
                "stderr": ""
            }

        except Exception as e:
            PrettyOutput.print(f"读取网页失败: {str(e)}", OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Failed to parse webpage: {str(e)}"
            }
