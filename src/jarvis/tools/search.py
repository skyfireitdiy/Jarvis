from typing import Dict, Any, List
from jarvis.models.registry import PlatformRegistry
from jarvis.utils import PrettyOutput, OutputType
from jarvis.tools.webpage import WebpageTool
from playwright.sync_api import sync_playwright
from urllib.parse import quote

def bing_search(query):
    try:
        with sync_playwright() as p:
            # 启动浏览器时设置参数
            browser = p.chromium.launch(
                headless=True,  # 无头模式
                args=['--disable-gpu', '--no-sandbox', '--disable-dev-shm-usage']
            )
            
            # 创建新页面并设置超时
            page = browser.new_page(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            
            # 设置页面超时
            page.set_default_timeout(60000)
            
            # 访问搜索页面
            url = f"https://www.bing.com/search?q={quote(query)}&form=QBLH&sp=-1"
            page.goto(url, wait_until="networkidle")
            
            # 等待搜索结果加载
            page.wait_for_selector("#b_results", state="visible", timeout=30000)
            
            # 等待一下以确保结果完全加载
            page.wait_for_timeout(1000)
            
            # 提取搜索结果
            summaries = page.evaluate("""() => {
                const results = [];
                const elements = document.querySelectorAll("#b_results > .b_algo");
                
                for (const el of elements) {
                    const titleEl = el.querySelector("h2");
                    const linkEl = titleEl ? titleEl.querySelector("a") : null;
                    const abstractEl = el.querySelector(".b_caption p");
                    
                    if (linkEl) {
                        results.push({
                            title: titleEl.innerText.trim(),
                            href: linkEl.href,
                            abstract: abstractEl ? abstractEl.innerText.trim() : ""
                        });
                    }
                }
                return results;
            }""")
            
            browser.close()
            return summaries
            
    except Exception as error:
        PrettyOutput.print(f"搜索出错: {str(error)}", OutputType.ERROR)
        return None

class SearchTool:
    name = "search"
    description = "使用Bing搜索引擎搜索信息，并根据问题提取关键信息"
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词"
            },
            "question": {
                "type": "string",
                "description": "需要回答的具体问题，用于从搜索结果中提取相关信息"
            },
            "max_results": {
                "type": "integer",
                "description": "最大搜索结果数量",
                "default": 3
            }
        },
        "required": ["query", "question"]
    }

    def __init__(self):
        """初始化搜索工具，需要传入语言模型用于信息提取"""
        self.model = PlatformRegistry.get_global_platform_registry().get_normal_platform()
        self.webpage_tool = WebpageTool()

    def _search(self, query: str, max_results: int) -> List[Dict]:
        """执行搜索请求"""
        try:
            results = bing_search(query)
            if not results:
                return []
            
            # 格式化搜索结果
            formatted_results = []
            for result in results[:max_results]:
                formatted_results.append({
                    "title": result.get("title", ""),
                    "href": result.get("href", ""),
                    "body": result.get("abstract", "")
                })
            return formatted_results
        except Exception as e:
            PrettyOutput.print(f"搜索请求失败: {str(e)}", OutputType.ERROR)
            return []

    def _extract_info(self, contents: List[str], question: str) -> str:
        """使用语言模型从网页内容中提取关键信息"""
        prompt = f"""请根据以下搜索结果内容，回答问题：{question}

搜索结果内容：
{'-' * 40}
{''.join(contents)}
{'-' * 40}

请提供一个简洁、准确的答案，重点关注与问题直接相关的信息。如果搜索结果中没有相关信息，请明确说明。
回答时注意：
1. 保持客观性，只基于搜索结果提供信息
2. 如果不同来源有冲突，请指出差异
3. 适当引用信息来源
4. 如果信息不完整或不确定，请说明"""

        try:
            response = self.model.chat(prompt)
            return response
        except Exception as e:
            return f"信息提取失败: {str(e)}"

    def execute(self, args: Dict) -> Dict[str, Any]:
        """执行搜索并提取信息"""
        try:
            query = args["query"]
            question = args["question"]
            max_results = args.get("max_results", 3)
            
            # 打印搜索信息
            PrettyOutput.print(f"搜索查询: {query}", OutputType.INFO)
            PrettyOutput.print(f"相关问题: {question}", OutputType.INFO)
            
            # 获取搜索结果
            results = self._search(query, max_results)
            if not results:
                return {
                    "success": False,
                    "error": "未能获取任何搜索结果"
                }
            
            # 收集网页内容
            contents = []
            for i, result in enumerate(results, 1):
                try:
                    PrettyOutput.print(f"正在读取第 {i}/{len(results)} 个结果... {result['title']} - {result['href']}", OutputType.PROGRESS)
                    webpage_result = self.webpage_tool.execute({"url": result["href"]})
                    if webpage_result["success"]:
                        contents.append(f"\n来源 {i}：{result['href']}\n")
                        contents.append(webpage_result["stdout"])
                except Exception as e:
                    PrettyOutput.print(f"读取结果 {i} 失败: {str(e)}", OutputType.WARNING)
                    continue
            
            if not contents:
                return {
                    "success": False,
                    "error": "未能获取任何有效的搜索结果"
                }
            
            # 提取信息
            PrettyOutput.print("正在分析搜索结果...", OutputType.PROGRESS)
            analysis = self._extract_info(contents, question)
            
            return {
                "success": True,
                "stdout": f"搜索分析结果：\n\n{analysis}",
                "stderr": ""
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"搜索失败: {str(e)}"
            }

def main():
    """命令行直接运行搜索工具"""
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description='Bing搜索工具')
    parser.add_argument('query', help='搜索关键词')
    parser.add_argument('--max', type=int, default=5, help='最大结果数量(默认5)')
    parser.add_argument('--url-only', action='store_true', help='只显示URL')
    args = parser.parse_args()
    
    try:
        PrettyOutput.print(f"正在搜索: {args.query}", OutputType.INFO)
        
        results = bing_search(args.query)
        
        if not results:
            PrettyOutput.print("未找到搜索结果", OutputType.WARNING)
            sys.exit(1)
            
        PrettyOutput.print(f"\n找到 {len(results)} 条结果:", OutputType.INFO)
        
        for i, result in enumerate(results[:args.max], 1):
            PrettyOutput.print(f"\n{'-'*50}", OutputType.INFO)
            if args.url_only:
                PrettyOutput.print(f"{i}. {result['href']}", OutputType.INFO)
            else:
                PrettyOutput.print(f"{i}. {result['title']}", OutputType.INFO)
                PrettyOutput.print(f"链接: {result['href']}", OutputType.INFO)
                if result['abstract']:
                    PrettyOutput.print(f"摘要: {result['abstract']}", OutputType.INFO)
                    
    except KeyboardInterrupt:
        PrettyOutput.print("\n搜索已取消", OutputType.WARNING)
        sys.exit(1)
    except Exception as e:
        PrettyOutput.print(f"执行出错: {str(e)}", OutputType.ERROR)
        sys.exit(1)

if __name__ == "__main__":
    main() 