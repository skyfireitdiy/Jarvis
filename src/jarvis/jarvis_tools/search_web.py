from typing import Dict, Any, List
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.read_webpage import WebpageTool
from playwright.sync_api import sync_playwright
from urllib.parse import quote

from jarvis.jarvis_utils.config import get_max_token_count
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.output import OutputType, PrettyOutput

def bing_search(query):
    try:
        with sync_playwright() as p:
            # Set parameters when starting the browser
            browser = p.chromium.launch(
                headless=True,  # Headless mode
                args=['--disable-gpu', '--no-sandbox', '--disable-dev-shm-usage']
            )
            
            # Create a new page and set timeout
            page = browser.new_page(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            
            # Set page timeout
            page.set_default_timeout(60000)
            
            # Visit search page
            url = f"https://www.bing.com/search?q={quote(query)}&form=QBLH&sp=-1"
            page.goto(url, wait_until="networkidle")
            
            # Wait for search results to load
            page.wait_for_selector("#b_results", state="visible", timeout=30000)
            
            # Wait for a moment to ensure the results are fully loaded
            page.wait_for_timeout(1000)
            
            # Extract search results
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
                PrettyOutput.print(f"正在处理批次 {i}/{len(batches)}...", OutputType.PROGRESS)
                
                prompt = f"""Please analyze these search results to answer the question: {question}

Search results content (Batch {i}/{len(batches)}):
{'-' * 40}
{''.join(batch)}
{'-' * 40}

Please extract key information related to the question. Focus on:
1. Relevant facts and details
2. Maintaining objectivity
3. Citing sources when appropriate
4. Noting any uncertainties

Format your response as a clear summary of findings from this batch."""

                response = self.model.chat_until_success(prompt)
                batch_results.append(response)

            # If only one batch, return its result directly
            if len(batch_results) == 1:
                return batch_results[0]

            # Synthesize results from all batches
            batch_findings = '\n\n'.join(f'Batch {i+1}:\n{result}' for i, result in enumerate(batch_results))
            separator = '-' * 40
            
            synthesis_prompt = f"""Please provide a comprehensive answer to the original question by synthesizing the findings from multiple batches of search results.

Original Question: {question}

Findings from each batch:
{separator}
{batch_findings}
{separator}

Please synthesize a final answer that:
1. Combines key insights from all batches
2. Resolves any contradictions between sources
3. Maintains clear source attribution
4. Acknowledges any remaining uncertainties
5. Provides a coherent and complete response to the original question"""

            final_response = self.model.chat_until_success(synthesis_prompt)
            return final_response

        except Exception as e:
            return f"Information extraction failed: {str(e)}"

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
            
            contents = []
            for i, result in enumerate(results, 1):
                try:
                    PrettyOutput.print(f"正在读取结果 {i}/{len(results)}... {result['title']} - {result['href']}", OutputType.PROGRESS)
                    webpage_result = self.webpage_tool.execute({"url": result["href"]})
                    if webpage_result["success"]:
                        contents.append(f"\nSource {i}: {result['href']}\n")
                        contents.append(webpage_result["stdout"])
                except Exception as e:
                    PrettyOutput.print(f"读取结果失败 {i}: {str(e)}", OutputType.WARNING)
                    continue
            
            if not contents:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "No valid search results found"
                }
            
            # Extract information
            PrettyOutput.print("正在分析搜索结果...", OutputType.PROGRESS)
            analysis = self._extract_info(contents, question)
            
            return {
                "success": True,
                "stdout": f"Search analysis results:\n\n{analysis}",
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