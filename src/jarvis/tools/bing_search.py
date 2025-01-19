from playwright.sync_api import sync_playwright
from urllib.parse import quote

def bing_search(query):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(
                f"https://www.bing.com/search?form=QBRE&q={quote(query)}&cc=US"
            )

            page.wait_for_selector("#b_results", timeout=10000)
            
            summaries = page.evaluate("""() => {
                const liElements = Array.from(
                    document.querySelectorAll("#b_results > .b_algo")
                );
                return liElements.map((li) => {
                    const abstractElement = li.querySelector(".b_caption > p");
                    const linkElement = li.querySelector("a");
                    const href = linkElement.getAttribute("href");
                    const title = linkElement.textContent;
                    const abstract = abstractElement ? abstractElement.textContent : "";
                    return { href, title, abstract };
                });
            }""")
            
            browser.close()
            print(summaries)
            return summaries
    except Exception as error:
        print("An error occurred:", error)

if __name__ == "__main__":
    # results = bing_search("北京到西雅图的距离")
    results = bing_search("北京到西雅图的距离")
    print(results)
