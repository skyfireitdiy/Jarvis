"""网络搜索工具。"""

from typing import Any
from typing import Dict
from typing import Optional
from jarvis.jarvis_utils.output import PrettyOutput

# -*- coding: utf-8 -*-

import json
import subprocess
import requests  # 导入第三方库requests

# pylint: disable=import-error,missing-module-docstring
# fmt: off
from markdownify import markdownify as md

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.config import calculate_content_token_limit
from jarvis.jarvis_utils.config import get_llm_config
from jarvis.jarvis_utils.config import get_normal_model_name
from jarvis.jarvis_utils.config import get_normal_platform_name
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.http import get as http_get

# fmt: on


class SearchWebTool:
    """处理网络搜索的类。"""

    name = "search_web"
    description = "搜索互联网上的信息"
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词或问题",
            },
            "site": {
                "type": "string",
                "description": "在特定网站内搜索，如 'wikipedia.org', 'github.com'",
            },
        },
        "required": ["query"],
    }

    def _search_with_ddgr(
        self,
        query: str,
        agent: Agent,
        site: Optional[str] = None,
    ) -> Dict[str, Any]:
        # pylint: disable=too-many-locals, broad-except
        """使用ddgr命令执行网络搜索、抓取内容并总结结果。"""
        try:
            # 构建ddgr命令
            cmd = [
                "ddgr",
                "--json",
                "--np",
                "-x",
            ]  # --np 表示不提示，直接执行；-x 显示完整URL

            # 添加网站特定搜索参数
            if site:
                cmd.extend(["-w", site])

            # 添加搜索关键词
            cmd.append(query)

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, check=False
            )

            if result.returncode != 0:
                return {
                    "stdout": "",
                    "stderr": f"ddgr命令执行失败: {result.stderr}",
                    "success": False,
                }

            try:
                results = json.loads(result.stdout)
            except json.JSONDecodeError as e:
                return {
                    "stdout": "",
                    "stderr": f"解析ddgr JSON输出失败: {e}",
                    "success": False,
                }

            if not results:
                return {
                    "stdout": "未找到搜索结果。",
                    "stderr": "未找到搜索结果。",
                    "success": False,
                }

            # 先打印搜索结果
            PrettyOutput.auto_print("\n🔍 网络搜索结果")
            PrettyOutput.auto_print(f"📝 查询关键词: {query}")
            PrettyOutput.auto_print(f"📊 搜索结果数: {len(results)}")
            PrettyOutput.auto_print("\n📄 搜索摘要:")
            for idx, r in enumerate(results[:10], 1):
                title = r.get("title", "")
                url = r.get("url", "")
                abstract = r.get("abstract", "")
                if title:
                    PrettyOutput.auto_print(f"  {idx}. {title}")
                    if url:
                        PrettyOutput.auto_print(f"     URL: {url}")
                    if abstract:
                        PrettyOutput.auto_print(
                            f"     摘要: {abstract[:150]}..."
                            if len(abstract) > 150
                            else f"     摘要: {abstract}"
                        )

            full_content = ""
            visited_urls = []
            visited_count = 0

            # 首先收集所有abstract作为基础内容
            for r in results:
                url = r.get("url", "")
                title = r.get("title", "")
                abstract = r.get("abstract", "")

                # 添加abstract到内容中
                if abstract:
                    full_content += f"标题: {title}\n摘要: {abstract}\n\n"

            # 首先计算一次内容长度限制（基于剩余token）
            content_token_limit = calculate_content_token_limit(agent)

            # 然后抓取前10个URL的详细内容
            for r in results:
                if visited_count >= 10:
                    break

                url = r.get("url", "")
                if url:
                    PrettyOutput.auto_print(
                        f"\n⏳ 正在访问 ({visited_count + 1}/{min(10, len(results))}): {url}"
                    )
                    try:
                        response = http_get(url, timeout=10.0, allow_redirects=True)
                        content = md(response.text, strip=["script", "style"])
                        if content:
                            # 计算剩余可用的内容长度限制（token数）
                            remaining_limit = (
                                content_token_limit
                                - get_context_token_count(full_content)
                            )
                            # 如果剩余限制不足，跳过此URL
                            if remaining_limit <= 0:
                                PrettyOutput.auto_print(
                                    f"⚠️ 内容长度已达限制，跳过: {url}"
                                )
                                continue
                            # 基于token限制截取内容（保守估计：1 token ≈ 4 字符，用字符数保守截取）
                            content_preview = content[: remaining_limit * 4]
                            full_content += (
                                f"URL: {url}\n内容预览: {content_preview}\n\n"
                            )
                            visited_urls.append(url)
                            visited_count += 1
                            PrettyOutput.auto_print(
                                f"✅ 已抓取内容 ({len(content_preview)} 字符)"
                            )
                    except requests.exceptions.HTTPError as e:
                        PrettyOutput.auto_print(
                            f"⚠️ HTTP错误 {e.response.status_code} 访问 {url}"
                        )
                    except requests.exceptions.RequestException as e:
                        PrettyOutput.auto_print(f"⚠️ 请求错误: {e}")

            if not full_content.strip():
                return {
                    "stdout": "无法从任何URL抓取有效内容。",
                    "stderr": "抓取内容失败。",
                    "success": False,
                }

            urls_list = "\n".join(f"  - {u}" for u in visited_urls)
            if urls_list:
                full_content = f"参考URL:\n{urls_list}\n\n{full_content}"

            summary_prompt = f'请为查询"{query}"总结以下内容：\n\n{full_content}'

            # 使用normal模型进行总结
            platform_name = get_normal_platform_name(None)
            model_name = get_normal_model_name(None)
            # 获取 normal_llm 的 llm_config，确保使用正确的 API base 和 API key
            llm_config = get_llm_config("normal", None)

            model = PlatformRegistry().create_platform(platform_name, llm_config)
            if not model:
                return {
                    "stdout": "",
                    "stderr": "无法创建用于总结的模型。",
                    "success": False,
                }

            model.set_model_name(model_name)
            model.set_suppress_output(False)
            summary = model.chat_until_success(summary_prompt)

            PrettyOutput.auto_print("\n💡 总结结果:")
            PrettyOutput.auto_print(summary)

            # 添加来源信息到总结文本中，便于LLM使用read_webpage验证
            if visited_urls:
                sources_text = "\n\n参考来源:\n" + "\n".join(
                    f"- {url}" for url in visited_urls
                )
                summary_with_sources = summary + sources_text
                PrettyOutput.auto_print("\n📚 参考来源:")
                for url in visited_urls:
                    PrettyOutput.auto_print(f"  - {url}")
            else:
                summary_with_sources = summary
                visited_urls = []

            return {
                "stdout": summary_with_sources,
                "stderr": "",
                "success": True,
                "sources": visited_urls,
            }

        except subprocess.TimeoutExpired:
            return {
                "stdout": "",
                "stderr": "ddgr命令执行超时。",
                "success": False,
            }
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 网页搜索过程中发生错误: {e}")
            return {
                "stdout": "",
                "stderr": f"网页搜索过程中发生错误: {e}",
                "success": False,
            }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes the web search.

        Uses ddgr command to search the web and scrape pages for content.
        Supports site-specific search.
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

        # 提取可选参数
        site = args.get("site")

        return self._search_with_ddgr(query=query, agent=agent, site=site)

    @staticmethod
    def check() -> bool:
        """Check if the tool is available."""
        return True
