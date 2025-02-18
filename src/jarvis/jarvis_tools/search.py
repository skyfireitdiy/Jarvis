from typing import Dict, Any, List
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.utils import PrettyOutput, OutputType
from jarvis.jarvis_tools.read_webpage import WebpageTool
from playwright.sync_api import sync_playwright
from urllib.parse import quote

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
        PrettyOutput.print(f"Search error: {str(error)}", OutputType.ERROR)
        return None

class SearchTool:
    name = "search"
    description = "Use Bing search engine to search for information, and extract key information based on the question"
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search keywords"
            },
            "question": {
                "type": "string",
                "description": "Specific question to answer, used to extract relevant information from search results"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of search results",
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
            PrettyOutput.print(f"Search request failed: {str(e)}", OutputType.ERROR)
            return []

    def _extract_info(self, contents: List[str], question: str) -> str:
        """Use language model to extract key information from web content"""
        prompt = f"""Please answer the question based on the following search results: {question}

Search results content:
{'-' * 40}
{''.join(contents)}
{'-' * 40}

Please provide a concise and accurate answer, focusing on information directly related to the question. If there is no relevant information in the search results, please clearly state that.
When answering, pay attention to:
1. Maintain objectivity, providing information based solely on search results
2. If there are conflicts between different sources, point out the differences
3. Appropriately cite information sources
4. If the information is incomplete or uncertain, please explain"""

        try:
            response = self.model.chat_until_success(prompt)
            return response
        except Exception as e:
            return f"Information extraction failed: {str(e)}"

    def execute(self, args: Dict) -> Dict[str, Any]:
        """Execute search and extract information"""
        try:
            query = args["query"]
            question = args["question"]
            max_results = args.get("max_results", 3)
            
            # Print search information
            PrettyOutput.print(f"Search query: {query}", OutputType.INFO)
            PrettyOutput.print(f"Related question: {question}", OutputType.INFO)
            
            # Get search results
            results = self._search(query, max_results)
            if not results:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "No search results found"
                }
            
            # Collect webpage content
            contents = []
            for i, result in enumerate(results, 1):
                try:
                    PrettyOutput.print(f"Reading result {i}/{len(results)}... {result['title']} - {result['href']}", OutputType.PROGRESS)
                    webpage_result = self.webpage_tool.execute({"url": result["href"]})
                    if webpage_result["success"]:
                        contents.append(f"\nSource {i}: {result['href']}\n")
                        contents.append(webpage_result["stdout"])
                except Exception as e:
                    PrettyOutput.print(f"Failed to read result {i}: {str(e)}", OutputType.WARNING)
                    continue
            
            if not contents:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "No valid search results found"
                }
            
            # Extract information
            PrettyOutput.print("Analyzing search results...", OutputType.PROGRESS)
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
        PrettyOutput.print(f"Searching: {args.query}", OutputType.INFO)
        
        results = bing_search(args.query)
        
        if not results:
            PrettyOutput.print("No search results found", OutputType.WARNING)
            sys.exit(1)
            
        PrettyOutput.print(f"\nFound {len(results)} results:", OutputType.INFO)
        
        for i, result in enumerate(results[:args.max], 1):
            output = []
            output.append(f"\n{'-'*50}")
            if args.url_only:
                output.append(f"{i}. {result['href']}")
            else:
                output.append(f"{i}. {result['title']}")
                output.append(f"Link: {result['href']}")
                if result['abstract']:
                    output.append(f"Abstract: {result['abstract']}")
            PrettyOutput.print("\n".join(output), OutputType.INFO)
                    
    except KeyboardInterrupt:
        PrettyOutput.print("Search cancelled", OutputType.WARNING)
        sys.exit(1)
    except Exception as e:
        PrettyOutput.print(f"Execution error: {str(e)}", OutputType.ERROR)
        sys.exit(1)

if __name__ == "__main__":
    main() 