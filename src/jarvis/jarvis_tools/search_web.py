# -*- coding: utf-8 -*-
"""网络搜索工具。"""
from typing import Any, Dict

import requests
from markdownify import markdownify as md  # type: ignore

# pylint: disable=import-error,missing-module-docstring
# fmt: off
from ddgs import DDGS  # type: ignore[import-not-found]
# fmt: on

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.config import (
    get_web_search_platform_name,
    get_web_search_model_name,
)
from jarvis.jarvis_utils.http import get as http_get
from jarvis.jarvis_utils.output import OutputType, PrettyOutput


class SearchWebTool:
    """处理网络搜索的类。"""

    name = "search_web"
    description = "搜索互联网上的信息"
    parameters = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "具体的问题"}},
    }

    def _search_with_ddgs(self, query: str, agent: Agent) -> Dict[str, Any]:
        # pylint: disable=too-many-locals, broad-except
        """执行网络搜索、抓取内容并总结结果。"""
        try:

            results = list(DDGS().text(query, max_results=50, page=3))

            if not results:
                return {
                    "stdout": "未找到搜索结果。",
                    "stderr": "未找到搜索结果。",
                    "success": False,
                }

            full_content = ""
            visited_urls = []
            visited_count = 0

            for r in results:
                if visited_count >= 10:

                    break

                url = r["href"]
                r.get("title", url)

                try:

                    response = http_get(url, timeout=10.0, allow_redirects=True)
                    content = md(response.text, strip=["script", "style"])
                    if content:
                        full_content += content + "\n\n"
                        visited_urls.append(url)
                        visited_count += 1
                except requests.exceptions.HTTPError as e:
                    PrettyOutput.print(
                        f"⚠️ HTTP错误 {e.response.status_code} 访问 {url}",
                        OutputType.WARNING,
                    )
                except requests.exceptions.RequestException as e:
                    PrettyOutput.print(f"⚠️ 请求错误: {e}", OutputType.WARNING)

            if not full_content.strip():
                return {
                    "stdout": "无法从任何URL抓取有效内容。",
                    "stderr": "抓取内容失败。",
                    "success": False,
                }

            "\n".join(f"  - {u}" for u in visited_urls)

            summary_prompt = f"请为查询“{query}”总结以下内容：\n\n{full_content}"

            if not agent.model:
                return {
                    "stdout": "",
                    "stderr": "用于总结的Agent模型未找到。",
                    "success": False,
                }

            platform_name = agent.model.platform_name()
            model_name = agent.model.name()

            model = PlatformRegistry().create_platform(platform_name)
            if not model:
                return {
                    "stdout": "",
                    "stderr": "无法创建用于总结的模型。",
                    "success": False,
                }

            model.set_model_name(model_name)
            model.set_suppress_output(False)
            summary = model.chat_until_success(summary_prompt)

            return {"stdout": summary, "stderr": "", "success": True}

        except Exception as e:
            PrettyOutput.print(f"❌ 网页搜索过程中发生错误: {e}", OutputType.ERROR)
            return {
                "stdout": "",
                "stderr": f"网页搜索过程中发生错误: {e}",
                "success": False,
            }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes the web search.

        If the agent's model supports a native web search, it uses it.
        Otherwise, it falls back to using DuckDuckGo Search and scraping pages.
        """
        query = args.get("query")
        agent = args.get("agent")

        if not query:
            return {"stdout": "", "stderr": "缺少查询参数。", "success": False}

        if not isinstance(agent, Agent) or not agent.model:
            return {
                "stdout": "",
                "stderr": "Agent或Agent模型未找到。",
                "success": False,
            }

        # 检查是否配置了专门的 Web 搜索平台和模型
        web_search_platform = get_web_search_platform_name()
        web_search_model = get_web_search_model_name()

        # 如果配置了专门的 Web 搜索平台和模型，优先使用
        if web_search_platform and web_search_model:
            model = PlatformRegistry().create_platform(web_search_platform)
            if model:
                model.set_model_name(web_search_model)
                if model.support_web():
                    model.set_web(True)
                    model.set_suppress_output(False)
                    return {
                        "stdout": model.chat_until_success(query),
                        "stderr": "",
                        "success": True,
                    }

        # 否则使用现有的模型选择流程
        if agent.model.support_web():
            model = PlatformRegistry().create_platform(agent.model.platform_name())
            if not model:
                return {"stdout": "", "stderr": "无法创建模型。", "success": False}
            model.set_model_name(agent.model.name())
            model.set_web(True)
            model.set_suppress_output(False)
            return {
                "stdout": model.chat_until_success(query),
                "stderr": "",
                "success": True,
            }

        return self._search_with_ddgs(query, agent)

    @staticmethod
    def check() -> bool:
        """Check if the tool is available."""
        return True
