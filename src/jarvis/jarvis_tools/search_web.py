from typing import Dict, Any, List
import concurrent.futures
from regex import W
from yaspin import yaspin
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.read_webpage import WebpageTool
from playwright.sync_api import sync_playwright
from urllib.parse import quote

from jarvis.jarvis_utils.config import get_max_token_count, get_thread_count
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.output import OutputType, PrettyOutput

def bing_search(query):
    try:
        with sync_playwright() as p:
            # Set parameters when starting the browser
            with yaspin(text="正在启动浏览器...", color="cyan") as spinner:
                browser = p.chromium.launch(
                    headless=True,  # Headless mode
                    args=['--disable-gpu', '--no-sandbox', '--disable-dev-shm-usage']
                )
                spinner.text = "浏览器启动完成"
                spinner.ok("✅")
            
            # Create a new page and set timeout
            with yaspin(text="正在创建新页面...", color="cyan") as spinner:
                page = browser.new_page(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080}
                )
                spinner.text = "新页面创建完成"
                spinner.ok("✅")
            
            # Set page timeout
            with yaspin(text="正在设置页面超时...", color="cyan") as spinner:
                page.set_default_timeout(60000)
                spinner.text = "页面超时设置完成"
                spinner.ok("✅")
            
            # Visit search page
            with yaspin(text=f"正在搜索 {query}...", color="cyan") as spinner:
                url = f"https://www.bing.com/search?q={quote(query)}&form=QBLH&sp=-1"
                page.goto(url, wait_until="networkidle")
                spinner.text = "搜索完成"
                spinner.ok("✅")
            
            # Wait for search results to load
            with yaspin(text="正在等待搜索结果加载...", color="cyan") as spinner:
                page.wait_for_selector("#b_results", state="visible", timeout=30000)
                # Wait for a moment to ensure the results are fully loaded
                page.wait_for_timeout(1000)
                spinner.text = "搜索结果加载完成"
                spinner.ok("✅")
            
            # Extract search results
            with yaspin(text="正在提取搜索结果...", color="cyan") as spinner:
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
                spinner.text = "搜索结果提取完成"
                spinner.ok("✅")

            with yaspin(text="正在关闭浏览器...", color="cyan") as spinner:
                browser.close()
                spinner.text = "浏览器关闭完成"
                spinner.ok("✅")
            return summaries
            
    except Exception as error:
        PrettyOutput.print(f"搜索错误：{str(error)}", OutputType.ERROR)
        return None

class SearchTool:
    name = "search_web"
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
                "description": "要回答的具体问题，用于从搜索结果中提取相关信息"
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
        """Initialize the search tool, need to pass in the language model for information extraction"""
        self.model = PlatformRegistry.get_global_platform_registry().get_normal_platform()
        self.webpage_tool = WebpageTool()

    def _search(self, query: str, max_results: int) -> List[Dict]:
        """Execute search request"""
        try:
            results = bing_search(query)
            if not results:
                return []
            
            # Format search results
            formatted_results = []
            for result in results[:max_results]:
                formatted_results.append({
                    "title": result.get("title", ""),
                    "href": result.get("href", ""),
                    "body": result.get("abstract", "")
                })
            return formatted_results
        except Exception as e:
            PrettyOutput.print(f"搜索请求失败：{str(e)}", OutputType.ERROR)
            return []

    def _extract_info(self, contents: List[str], question: str) -> str:
        """Use language model to extract key information from web content"""
        try:
            # Reserve tokens for prompt and response
            max_tokens = get_max_token_count()
            reserved_tokens = 2000  # Reserve tokens for prompt template and response
            available_tokens = max_tokens - reserved_tokens
            
            # Split contents into batches
            batches = []
            current_batch = []
            current_tokens = 0
            
            for content in contents:
                content_tokens = get_context_token_count(content)
                
                # If adding this content would exceed limit, start new batch
                if current_tokens + content_tokens > available_tokens:
                    if current_batch:
                        batches.append(current_batch)
                    current_batch = [content]
                    current_tokens = content_tokens
                else:
                    current_batch.append(content)
                    current_tokens += content_tokens
            
            # Add final batch
            if current_batch:
                batches.append(current_batch)

            # Process each batch
            batch_results = []
            for i, batch in enumerate(batches, 1):
                prompt = f"""请根据以下搜索结果回答以下问题：{question}

搜索结果内容 (第 {i} 批/{len(batches)}):
{'-' * 40}
{''.join(batch)}
{'-' * 40}

请提取与问题相关的关键信息。重点关注：
1. 相关事实和细节
2. 保持客观性
3. 在适当的时候引用来源
4. 注明任何不确定性

请将您的回答格式化为对本批次搜索结果的清晰总结。"""

                response = self.model.chat_until_success(prompt)
                batch_results.append(response)

            # If only one batch, return its result directly
            if len(batch_results) == 1:
                return batch_results[0]

            # Synthesize results from all batches
            batch_findings = '\n\n'.join(f'Batch {i+1}:\n{result}' for i, result in enumerate(batch_results))
            separator = '-' * 40
            
            synthesis_prompt = f"""请通过综合多个批次的搜索结果，为原始问题提供一个全面的回答。

原始问题: {question}

各批次的发现:
{separator}
{batch_findings}
{separator}

请综合出一个最终答案，要求：
1. 整合所有批次的关键见解
2. 解决不同来源之间的矛盾
3. 保持清晰的来源归属
4. 承认任何剩余的不确定性
5. 提供对原始问题的连贯完整的回答"""

            final_response = self.model.chat_until_success(synthesis_prompt)
            return final_response

        except Exception as e:
            return f"信息提取失败：{str(e)}"

    def execute(self, args: Dict) -> Dict[str, Any]:
        """Execute search and extract information"""
        try:
            query = args["query"]
            question = args["question"]
            max_results = args.get("max_results", 3)
            
            # Print search information
            PrettyOutput.print(f"搜索关键词: {query}", OutputType.INFO)
            PrettyOutput.print(f"相关问题: {question}", OutputType.INFO)
            
            # Get search results
            results = self._search(query, max_results)
            if not results:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "No search results found"
                }
            
            # Read webpages in parallel using ThreadPoolExecutor
            contents = []
            
            # Print starting message
            PrettyOutput.print(f"开始并行读取 {len(results)} 个网页结果...", OutputType.INFO)
            
            def fetch_webpage(result_info):
                """Function to fetch a single webpage in a separate thread"""
                idx, result = result_info
                try:
                    # Removed progress print here to avoid mixed output
                    webpage_result = self.webpage_tool.execute({"url": result["href"]})
                    if webpage_result["success"]:
                        return idx, result, webpage_result["stdout"], True
                    return idx, result, None, False
                except Exception as e:
                    return idx, result, str(e), False
            
            # Use ThreadPoolExecutor for parallel processing
            processed_results = []
            with yaspin(text="正在并行读取网页内容...", color="cyan") as spinner:
                with concurrent.futures.ThreadPoolExecutor(max_workers=get_thread_count()) as executor:
                    # Submit all webpage fetch tasks
                    future_to_result = {
                        executor.submit(fetch_webpage, (i, result)): i 
                        for i, result in enumerate(results)
                    }
                    
                    # Collect results as they complete
                    for future in concurrent.futures.as_completed(future_to_result):
                        processed_results.append(future.result())
                        # Update spinner with current progress
                        spinner.text = f"正在并行读取网页内容... ({len(processed_results)}/{len(results)})"
                
                spinner.text = "网页内容读取完成"
                spinner.ok("✅")
            
            # Sort results by original index to maintain ordering
            processed_results.sort(key=lambda x: x[0])
            
            # Print results in order and add to contents
            PrettyOutput.section("搜索结果概览", OutputType.INFO)
            
            output = ""
            for idx, result, content, success in processed_results:
                if success:
                    output += f"✅ 读取结果 {idx+1}/{len(results)} 完成: {result['title']} - {result['href']}\n"
                    contents.append(f"\nSource {idx+1}: {result['href']}\n")
                    contents.append(content)
                else:
                    output += f"❌ 读取结果 {idx+1}/{len(results)} 失败: {result['title']} - {result['href']} - 错误: {content}\n"
            
            PrettyOutput.print(output, OutputType.INFO)

            if not contents:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "No valid search results found"
                }
            
            # Extract information
            with yaspin(text="正在提取信息...", color="cyan") as spinner:   
                analysis = self._extract_info(contents, question)
                spinner.text = "信息提取完成"
                spinner.ok("✅")

            output = f"分析结果:\n\n{analysis}"
            PrettyOutput.print(output, OutputType.SUCCESS)
            
            return {
                "success": True,
                "stdout": output,
                "stderr": ""
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Search failed: {str(e)}"
            }

def main():
    """Command line directly run search tool"""
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description='Bing search tool')
    parser.add_argument('query', help='Search keywords')
    parser.add_argument('--max', type=int, default=5, help='Maximum number of results (default 5)')
    parser.add_argument('--url-only', action='store_true', help='Only display URL')
    args = parser.parse_args()
    
    try:
        PrettyOutput.print(f"搜索: {args.query}", OutputType.INFO)
        
        results = bing_search(args.query)
        
        if not results:
            PrettyOutput.print("未找到搜索结果", OutputType.WARNING)
            sys.exit(1)
            
        PrettyOutput.print(f"\n找到 {len(results)} 个结果:", OutputType.INFO)
        
        for i, result in enumerate(results[:args.max], 1):
            output = []
            output.append(f"\n{'-'*50}")
            if args.url_only:
                output.append(f"{i}. {result['href']}")
            else:
                output.append(f"{i}. {result['title']}")
                output.append(f"链接: {result['href']}")
                if result['abstract']:
                    output.append(f"摘要: {result['abstract']}")
            PrettyOutput.print("\n".join(output), OutputType.INFO)
                    
    except KeyboardInterrupt:
        PrettyOutput.print("搜索已取消", OutputType.WARNING)
        sys.exit(1)
    except Exception as e:
        PrettyOutput.print(f"执行错误: {str(e)}", OutputType.ERROR)
        sys.exit(1)

if __name__ == "__main__":
    main()