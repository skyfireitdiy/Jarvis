# -*- coding: utf-8 -*-
from typing import Any
from typing import Dict

import requests
from markdownify import markdownify as md

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.config import get_web_search_model_name
from jarvis.jarvis_utils.config import get_web_search_platform_name
from jarvis.jarvis_utils.http import get as http_get
from jarvis.jarvis_utils.output import PrettyOutput


class WebpageTool:
    name = "read_webpage"
    description = "读取网页内容，提取标题、文本和超链接"
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "要读取的网页URL"},
            "want": {
                "type": "string",
                "description": "具体想要从网页获取的信息或回答的问题",
                "default": "请总结这个网页的主要内容",
            },
        },
        "required": ["url"],
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        读取网页内容。
        优先使用配置的 web_search_platform 与模型的原生web能力；若不支持，则使用requests抓取页面并调用模型进行分析。
        """
        try:
            url = str(args.get("url", "")).strip()
            want = str(args.get("want", "请总结这个网页的主要内容"))

            if not url:
                return {"success": False, "stdout": "", "stderr": "缺少必需参数：url"}

            # 1) 优先使用配置的 Web 搜索平台与模型（若支持web）
            web_search_platform = get_web_search_platform_name()
            web_search_model = get_web_search_model_name()
            if web_search_platform and web_search_model:
                model = PlatformRegistry().create_platform(web_search_platform)
                if model:
                    model.set_model_name(web_search_model)
                    if model.support_web():
                        model.set_web(True)
                        model.set_suppress_output(False)
                        prompt = f"""请帮我处理这个网页：{url}
用户的具体需求是：{want}
请按照以下要求输出结果：
1. 使用Markdown格式
2. 包含网页标题
3. 根据用户需求提供准确、完整的信息"""
                        response = model.chat_until_success(prompt)
                        if response and response.strip():
                            return {"success": True, "stdout": response, "stderr": ""}

            # 2) 然后尝试使用cheap平台的 web 能力（适用于网页读取等简单任务）
            model = PlatformRegistry().get_cheap_platform()
            if model.support_web():
                model.set_web(True)
                model.set_suppress_output(False)
                prompt = f"""请帮我处理这个网页：{url}
用户的具体需求是：{want}
请按照以下要求输出结果：
1. 使用Markdown格式
2. 包含网页标题
3. 根据用户需求提供准确、完整的信息"""
                response = model.chat_until_success(prompt)
                if response and response.strip():
                    return {"success": True, "stdout": response, "stderr": ""}

            # 3) 回退：使用 requests 抓取网页，再用模型分析

            try:
                resp = http_get(url, timeout=10.0, allow_redirects=True)
                content_md = md(resp.text, strip=["script", "style"])
            except requests.exceptions.HTTPError as e:
                PrettyOutput.auto_print(
                    f"⚠️ HTTP错误 {e.response.status_code} 访问 {url}"
                )
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"HTTP错误：{e.response.status_code}",
                }
            except requests.exceptions.RequestException as e:
                PrettyOutput.auto_print(f"⚠️ 请求错误: {e}")
                return {"success": False, "stdout": "", "stderr": f"请求错误：{e}"}

            if not content_md or not content_md.strip():
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "无法从网页抓取有效内容。",
                }

            summary_prompt = f"""以下是网页 {url} 的内容（已转换为Markdown）：
----------------
{content_md}
----------------
请根据用户的具体需求“{want}”进行总结与回答：
- 使用Markdown格式
- 包含网页标题（若可推断）
- 提供准确、完整的信息"""

            # 使用cheap平台进行网页内容总结（简单任务）
            model = PlatformRegistry().get_cheap_platform()
            model.set_suppress_output(False)
            summary = model.chat_until_success(summary_prompt)

            return {"success": True, "stdout": summary, "stderr": ""}

        except Exception as e:
            PrettyOutput.auto_print(f"❌ 读取网页失败: {str(e)}")
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Failed to parse webpage: {str(e)}",
            }

    @staticmethod
    def check() -> bool:
        """工具可用性检查：始终可用；若模型不支持web将回退到requests抓取。"""
        return True
