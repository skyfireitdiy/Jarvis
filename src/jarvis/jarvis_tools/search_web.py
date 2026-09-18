"""网络搜索工具。"""

from typing import Any
from typing import Dict
from typing import Optional
from jarvis.jarvis_utils.output import PrettyOutput

# -*- coding: utf-8 -*-

import json
import re
import urllib.request
from urllib.parse import quote_plus

try:
    from bs4 import BeautifulSoup
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
import shutil
import subprocess
import sys

# pylint: disable=import-error,missing-module-docstring

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_utils.exception_utils import save_exception

# fmt: on

_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_CHINESE_PATTERN = re.compile(r"[\u4e00-\u9fff]")


def _contains_chinese(text: str) -> bool:
    """判断文本是否包含中文字符。"""
    return bool(_CHINESE_PATTERN.search(text))


class SearchWebTool:
    """处理网络搜索的类。"""

    name = "search_web"
    description = "搜索互联网并返回结果；需要外部/最新信息或查证时使用，可配合 read_webpage 打开结果详情。"
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

    def _get_ddgr_command(self) -> list[str]:
        """获取 ddgr 命令，支持多种调用方式

        返回:
            list[str]: ddgr 命令列表
        """
        # 方法1: 尝试直接使用 ddgr 命令（如果它在 PATH 中）
        ddgr_path = shutil.which("ddgr")
        if ddgr_path:
            return [ddgr_path]

        # 方法2: 尝试使用 python -m ddgr（适用于 uv tool install 等安装方式）
        try:
            # 检查 ddgr 模块是否可用
            import importlib.util

            spec = importlib.util.find_spec("ddgr")
            if spec is not None:
                return [sys.executable, "-m", "ddgr"]
        except Exception as e:
            save_exception(
                e, module="jarvis_tools.search_web", function="_get_ddgr_command"
            )
            pass

        # 方法3: 回退到直接使用 ddgr（让 subprocess 处理错误）
        return ["ddgr"]

    def _search_with_ddgr(
        self,
        query: str,
        agent: Agent,
        site: Optional[str] = None,
    ) -> Dict[str, Any]:
        # pylint: disable=too-many-locals, broad-except
        """使用ddgr命令执行网络搜索、抓取内容并总结结果。"""
        try:
            # 获取 ddgr 命令
            ddgr_cmd = self._get_ddgr_command()

            # 构建ddgr命令
            cmd = ddgr_cmd + [
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
                PrettyOutput.auto_print(f"⚠️ ddgr 命令执行失败: {result.stderr}")
                # 降级到 Playwright 方案
                return self._search_with_playwright(query=query, agent=agent, site=site)

            try:
                results = json.loads(result.stdout)
            except json.JSONDecodeError as e:
                PrettyOutput.auto_print(f"⚠️ 解析ddgr JSON输出失败: {e}")
                # 降级到 Playwright 方案
                return self._search_with_playwright(query=query, agent=agent, site=site)

            if not results:
                PrettyOutput.auto_print("⚠️ ddgr 未找到搜索结果")
                # 降级到 Playwright 方案
                return self._search_with_playwright(query=query, agent=agent, site=site)

            # 先打印搜索结果
            PrettyOutput.auto_print("🔍 网络搜索结果")
            PrettyOutput.auto_print(f"📝 查询关键词: {query}")
            PrettyOutput.auto_print(f"📊 搜索结果数: {len(results)}")
            PrettyOutput.auto_print("📄 搜索摘要:")

            # 收集搜索结果并格式化输出
            results_text = ""
            visited_urls = []

            for idx, r in enumerate(results[:10], 1):
                title = r.get("title", "")
                url = r.get("url", "")
                abstract = r.get("abstract", "")

                if title:
                    PrettyOutput.auto_print(f"  {idx}. {title}")
                    if url:
                        PrettyOutput.auto_print(f"     URL: {url}")
                        visited_urls.append(url)
                    if abstract:
                        PrettyOutput.auto_print(
                            f"     摘要: {abstract[:150]}..."
                            if len(abstract) > 150
                            else f"     摘要: {abstract}"
                        )

                    # 添加到返回文本
                    results_text += f"{idx}. {title}\n"
                    if url:
                        results_text += f"   URL: {url}\n"
                    if abstract:
                        results_text += f"   摘要: {abstract}\n"
                    results_text += "\n"

            # 添加提示信息
            results_text += "💡 提示：如果想要获取详细信息，可以调用read_webpage工具\n"

            return {
                "stdout": results_text,
                "stderr": "",
                "success": True,
            }

        except subprocess.TimeoutExpired:
            PrettyOutput.auto_print("⚠️ ddgr 命令执行超时")
            # 降级到 Playwright 方案
            return self._search_with_playwright(query=query, agent=agent, site=site)
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 网页搜索过程中发生错误: {e}")
            # 降级到 Playwright 方案
            return self._search_with_playwright(query=query, agent=agent, site=site)

    def _build_bing_url(self, query: str, site: Optional[str] = None) -> str:
        """构建 Bing 搜索 URL。

        Bing 对无登录态访问会按查询语言降级，故按语言选择对应市场：
        中文查询走默认 zh-CN 市场，其他查询强制 en-US 市场，避免只匹配首个实体词。
        """
        full_query = f"{query} site:{site}" if site else query
        encoded_query = quote_plus(full_query)
        if _contains_chinese(query):
            return f"https://cn.bing.com/search?q={encoded_query}"
        return f"https://cn.bing.com/search?q={encoded_query}&mkt=en-US&setlang=en"

    def _fetch_bing_html(self, url: str, query: str) -> str:
        """用 urllib 抓取 Bing 搜索页 HTML，避免启动无头浏览器。"""
        accept_language = (
            "zh-CN,zh;q=0.9,en;q=0.8" if _contains_chinese(query) else "en-US,en;q=0.9"
        )
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": _BROWSER_USER_AGENT,
                "Accept-Language": accept_language,
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                ),
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", "ignore")

    @staticmethod
    def _parse_bing_results(html_content: str) -> list[Dict[str, str]]:
        """从 Bing 搜索页 HTML 中解析搜索结果。"""
        soup = BeautifulSoup(html_content, "lxml")
        results: list[Dict[str, str]] = []
        for item in soup.select("li.b_algo")[:10]:
            title_elem = item.select_one("h2 a")
            if not title_elem:
                continue
            title = title_elem.get_text(strip=True)
            url = title_elem.get("href", "")
            if not title or not url:
                continue
            abstract_elem = item.select_one("p")
            abstract = abstract_elem.get_text(strip=True) if abstract_elem else ""
            results.append(
                {
                    "title": str(title),
                    "url": str(url),
                    "abstract": str(abstract),
                }
            )
        return results

    def _format_search_results(
        self,
        results: list[Dict[str, str]],
        query: str,
        site: Optional[str],
    ) -> Dict[str, Any]:
        """格式化搜索结果输出（与 ddgr 保持一致）。"""
        PrettyOutput.auto_print("🔍 网络搜索结果（降级方案: Bing）")
        PrettyOutput.auto_print(f"📝 查询关键词: {query}")
        if site:
            PrettyOutput.auto_print(f"🌐 站点过滤: {site}")
        PrettyOutput.auto_print(f"📊 搜索结果数: {len(results)}")
        PrettyOutput.auto_print("📄 搜索摘要:")

        results_text = ""
        for idx, r in enumerate(results, 1):
            title = r.get("title", "")
            url = r.get("url", "")
            abstract = r.get("abstract", "")

            PrettyOutput.auto_print(f"  {idx}. {title}")
            if url:
                PrettyOutput.auto_print(f"     URL: {url}")
            if abstract:
                PrettyOutput.auto_print(
                    f"     摘要: {abstract[:150]}..."
                    if len(abstract) > 150
                    else f"     摘要: {abstract}"
                )

            results_text += f"{idx}. {title}\n"
            if url:
                results_text += f"   URL: {url}\n"
            if abstract:
                results_text += f"   摘要: {abstract}\n"
            results_text += "\n"

        results_text += "💡 提示：如果想要获取详细信息，可以调用read_webpage工具\n"
        return {
            "stdout": results_text,
            "stderr": "",
            "success": True,
        }

    def _search_with_playwright(
        self,
        query: str,
        agent: Agent,
        site: Optional[str] = None,
    ) -> Dict[str, Any]:
        # pylint: disable=too-many-locals, broad-except
        """使用 Bing 搜索作为 ddgr 的降级方案。"""
        search_url = self._build_bing_url(query, site)
        PrettyOutput.auto_print("⚠️ ddgr 搜索失败，正在降级使用 Bing 搜索...")
        PrettyOutput.auto_print(f"🌐 访问搜索页面: {search_url}")

        try:
            html_content = self._fetch_bing_html(search_url, query)
            results = self._parse_bing_results(html_content)
        except Exception as e:
            save_exception(
                e,
                module="jarvis_tools.search_web",
                function="_search_with_playwright",
            )
            PrettyOutput.auto_print(f"⚠️ 直接抓取失败，回退到 Playwright: {e}")
            results = self._search_bing_with_playwright(search_url)

        if not results:
            return {
                "stdout": "未找到搜索结果。",
                "stderr": "未找到搜索结果。",
                "success": False,
            }

        return self._format_search_results(results, query, site)

    def _search_bing_with_playwright(self, search_url: str) -> list[Dict[str, str]]:
        """用无头浏览器访问 Bing 并解析结果，作为直接抓取失败时的兜底。"""
        if not PLAYWRIGHT_AVAILABLE:
            return []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_default_timeout(30000)
                page.goto(search_url, wait_until="networkidle")
                page.wait_for_selector("li.b_algo", timeout=10000)
                html_content = page.content()
                browser.close()
            return self._parse_bing_results(html_content)
        except Exception as e:
            save_exception(
                e,
                module="jarvis_tools.search_web",
                function="_search_bing_with_playwright",
            )
            PrettyOutput.auto_print(f"❌ Playwright 搜索失败: {e}")
            return []

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
