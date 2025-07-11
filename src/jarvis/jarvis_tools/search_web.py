# -*- coding: utf-8 -*-
"""A tool for searching the web."""
import time
from typing import Any, Dict

from bs4 import BeautifulSoup
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_platform.registry import PlatformRegistry


class SearchWebTool:
    """A class to handle web searches, with a fallback to Playwright."""

    name = "search_web"
    description = "搜索互联网上的信息"
    parameters = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "具体的问题"}},
    }

    def _search_with_playwright(self, query: str, agent: Agent) -> Dict[str, Any]:
        # pylint: disable=too-many-locals
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto(f"https://www.bing.com/search?q={query}")

                page.wait_for_selector("#b_results")

                links = page.query_selector_all(".b_algo h2 a")[:5]
                urls = []
                for link in links:
                    if href := link.get_attribute("href"):
                        urls.append(href)

                content = ""
                for url in urls:
                    try:
                        page.goto(url, timeout=15000)
                        time.sleep(2)
                        html = page.content()
                        soup = BeautifulSoup(html, "lxml")
                        content += soup.get_text(separator=" ", strip=True) + "\n\n"
                    except PlaywrightError as e:
                        content += f"Could not fetch content from {url}: {e}\n\n"

                browser.close()

                if not content.strip():
                    return {
                        "stdout": "No content found from search results.",
                        "stderr": "No content found.",
                        "success": False,
                    }

                summary_prompt = (
                    f"Please summarize the following content about '{query}':\n\n"
                    f"{content}"
                )
                # pylint: disable=protected-access
                summary = agent._call_model(summary_prompt)

                return {"stdout": summary, "stderr": "", "success": True}

        except Exception as e:  # pylint: disable=broad-except
            return {
                "stdout": "",
                "stderr": f"An error occurred during web search: {e}",
                "success": False,
            }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes the web search.

        If the agent's model supports web search, it uses it.
        Otherwise, it falls back to using Playwright to search Bing.
        """
        query = args.get("query")
        agent = args.get("agent")

        if not query:
            return {"stdout": "", "stderr": "Query is missing.", "success": False}

        if not isinstance(agent, Agent) or not agent.model:
            return {
                "stdout": "",
                "stderr": "Agent or agent model is not found.",
                "success": False,
            }

        if agent.model.support_web():
            model = PlatformRegistry().create_platform(agent.model.platform_name())
            if not model:
                return {
                    "stdout": "",
                    "stderr": "Model could not be created.",
                    "success": False,
                }
            model.set_model_name(agent.model.name())
            model.set_web(True)
            model.set_suppress_output(False)
            return {
                "stdout": model.chat_until_success(query),
                "stderr": "",
                "success": True,
            }

        return self._search_with_playwright(query, agent)

    @staticmethod
    def check() -> bool:
        """Check if the tool is available."""
        return True

