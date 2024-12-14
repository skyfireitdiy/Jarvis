from langchain.tools import Tool
from langchain_community.utilities import WikipediaAPIWrapper
from langchain_community.tools import TavilySearchResults
from langchain_experimental.tools import PythonREPLTool

def get_tools():
    """获取所有可用工具"""
    tools = [
        Tool(
            name="Calculator",
            func=PythonREPLTool().run,
            description="用于执行数学计算的Python计算器。当需要进行数学运算、计算幂次方等数学任务时使用此工具。输入应该是可执行的Python代码。"
        ),
        Tool(
            name="Search",
            func=TavilySearchResults().run,
            description="用于搜索实时信息的工具。当需要查询最新信息、新闻、天气等信息时使用此工具。"
        ),
        Tool(
            name="Wikipedia",
            func=WikipediaAPIWrapper(lang="zh").run,
            description="用于查询百科知识的工具。当需要了解某个概念或主题的详细信息时使用此工具。"
        )
    ]
    
    return tools 