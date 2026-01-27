# -*- coding: utf-8 -*-
from typing import Any
from typing import Dict

import requests  # 导入第三方库requests
from markdownify import markdownify as md

from jarvis.jarvis_utils.config import calculate_content_token_limit
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.http import get as http_get
from jarvis.jarvis_utils.output import PrettyOutput


class WebpageTool:
    name = "read_webpage"
    description = "读取网页内容，将HTML转换为Markdown格式返回"
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "要读取的网页URL"},
        },
        "required": ["url"],
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        读取网页内容，将HTML转换为Markdown格式返回。
        """
        try:
            url = str(args.get("url", "")).strip()

            if not url:
                return {"success": False, "stdout": "", "stderr": "缺少必需参数：url"}

            # 使用 requests 抓取网页内容并转换为 Markdown

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

            # 根据剩余token动态计算内容长度限制，避免内容过长
            token_limit = calculate_content_token_limit()

            # 基于 token 数进行截断
            content_token_count = get_context_token_count(content_md)
            if content_token_count > token_limit:
                # 使用固定的小块大小进行逐块累加，确保充分利用token限制
                # 块大小设为100字符，既避免频繁计算，又能保证精细控制
                chunk_size = 100
                truncated_text = ""
                truncated_tokens = 0

                for i in range(0, len(content_md), chunk_size):
                    chunk = content_md[i : i + chunk_size]
                    chunk_tokens = get_context_token_count(chunk)

                    # 如果当前chunk超过剩余限制，跳过当前chunk继续处理后续chunks
                    if chunk_tokens > token_limit - truncated_tokens:
                        continue

                    truncated_text += chunk
                    truncated_tokens += chunk_tokens

                content_md_truncated = truncated_text
                PrettyOutput.auto_print(
                    f"⚠️ 网页内容过长（{content_token_count} token），已截断至 {truncated_tokens} token"
                )
            else:
                content_md_truncated = content_md

            # 直接返回Markdown格式的网页内容
            return {"success": True, "stdout": content_md_truncated, "stderr": ""}

        except Exception as e:
            PrettyOutput.auto_print(f"❌ 读取网页失败: {str(e)}")
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Failed to parse webpage: {str(e)}",
            }

    @staticmethod
    def check() -> bool:
        """工具可用性检查：始终可用。"""
        return True
