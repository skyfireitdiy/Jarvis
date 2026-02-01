# -*- coding: utf-8 -*-
from typing import Any
from typing import Dict

from playwright.sync_api import sync_playwright
from markdownify import markdownify as md

# 降级方案依赖
try:
    import requests

    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

from jarvis.jarvis_utils.config import calculate_content_token_limit
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.output import PrettyOutput


class WebpageTool:
    name = "read_webpage"
    description = "使用无头浏览器读取网页内容，支持JavaScript动态渲染，将HTML转换为Markdown格式返回"
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "要读取的网页URL"},
        },
        "required": ["url"],
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        使用无头浏览器读取网页内容，将HTML转换为Markdown格式返回。
        支持JavaScript动态渲染的内容。
        """
        try:
            url = str(args.get("url", "")).strip()

            if not url:
                return {"success": False, "stdout": "", "stderr": "缺少必需参数：url"}

            # 使用 Playwright 无头浏览器抓取网页内容
            try:
                with sync_playwright() as p:
                    # 启动无头浏览器
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()

                    # 设置超时时间为30秒
                    page.set_default_timeout(30000)

                    PrettyOutput.auto_print(f"🌐 正在使用无头浏览器访问: {url}")

                    # 访问页面并等待加载
                    page.goto(url, wait_until="networkidle")

                    # 获取渲染后的HTML内容
                    html_content = page.content()

                    # 关闭浏览器
                    browser.close()

                # 将HTML转换为Markdown
                content_md = md(html_content, strip=["script", "style"])

            except ImportError:
                # Playwright 未安装，尝试降级到 requests
                PrettyOutput.auto_print(
                    "⚠️ Playwright 未安装，正在降级使用 requests 方案..."
                )
                if not REQUESTS_AVAILABLE:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "Playwright 和 requests 库均不可用。请安装至少一个：pip install playwright 或 pip install requests beautifulsoup4",
                    }

                try:
                    PrettyOutput.auto_print(f"📡 正在使用 requests 访问: {url}")
                    PrettyOutput.auto_print(
                        "💡 注意：requests 方案无法获取 JavaScript 动态渲染的内容"
                    )

                    response = requests.get(
                        url,
                        timeout=30,
                        headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                        },
                    )
                    response.raise_for_status()

                    # 直接使用 markdownify 转换，strip 参数会移除 script 和 style
                    content_md = md(response.text, strip=["script", "style"])

                except Exception as req_error:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": f"requests 方案也失败：{req_error}",
                    }

            except Exception as e:
                # Playwright 运行时错误，尝试降级到 requests
                PrettyOutput.auto_print(
                    f"⚠️ 无头浏览器错误: {e}，正在降级使用 requests 方案..."
                )

                if not REQUESTS_AVAILABLE:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": f"无头浏览器错误：{e}\n注意：requests 库也不可用，无法降级。请安装: pip install requests beautifulsoup4",
                    }

                try:
                    PrettyOutput.auto_print(f"📡 正在使用 requests 访问: {url}")
                    PrettyOutput.auto_print(
                        "💡 注意：requests 方案无法获取 JavaScript 动态渲染的内容"
                    )

                    response = requests.get(
                        url,
                        timeout=30,
                        headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                        },
                    )
                    response.raise_for_status()

                    # 直接使用 markdownify 转换，strip 参数会移除 script 和 style
                    content_md = md(response.text, strip=["script", "style"])

                except Exception as req_error:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": f"requests 方案也失败：{req_error}",
                    }

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

            # 使用print_markdown打印网页内容
            PrettyOutput.print_markdown(
                content_md_truncated,
                title=f"📄 网页内容: {url}",
                border_style="bright_blue",
                theme="monokai",
            )

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
        """工具可用性检查：检查Playwright或requests降级方案是否可用。

        优先检查Playwright，如果不可用则检查requests降级方案。
        如果浏览器驱动未安装，会自动尝试安装。

        Returns:
            bool: 工具是否可用（Playwright或requests至少一个可用）
        """
        # 首先尝试 Playwright
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch()
                browser.close()
            PrettyOutput.auto_print(
                "✅ Playwright 可用（完整功能，支持JavaScript渲染）"
            )
            return True
        except ImportError:
            PrettyOutput.auto_print("⚠️ Playwright Python包未安装")
        except Exception as e:
            error_msg = str(e)
            # 检测是否是浏览器驱动未安装
            if "executable doesn't exist" in error_msg or "driver" in error_msg.lower():
                PrettyOutput.auto_print("🔧 检测到浏览器驱动未安装，正在自动安装...")
                try:
                    from jarvis.scripts.install_playwright import install_chromium

                    install_chromium()
                    PrettyOutput.auto_print("✅ 浏览器驱动安装成功，正在重试...")
                    # 重试检查
                    return WebpageTool.check()
                except Exception as install_error:
                    PrettyOutput.auto_print(f"❌ 自动安装失败: {install_error}")
            else:
                PrettyOutput.auto_print(f"⚠️ Playwright 运行时错误: {e}")

        # Playwright 不可用，检查降级方案
        if REQUESTS_AVAILABLE:
            PrettyOutput.auto_print(
                "✅ requests 降级方案可用（不支持JavaScript动态渲染）"
            )
            return True
        else:
            PrettyOutput.auto_print("❌ Playwright 和 requests 均不可用")
            PrettyOutput.auto_print("💡 请安装至少一个方案：")
            PrettyOutput.auto_print("   - pip install playwright")
            PrettyOutput.auto_print("   - pip install requests beautifulsoup4")
            return False
