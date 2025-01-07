from typing import Dict, Any, List, Optional, Callable
import json
from ..utils import PrettyOutput, OutputType

class Tool:
    def __init__(self, name: str, description: str, parameters: Dict, func: Callable):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.func = func

    def to_dict(self) -> Dict:
        """转换为Ollama工具格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }

    def execute(self, arguments: Dict) -> Dict[str, Any]:
        """执行工具函数"""
        return self.func(arguments)

class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, Tool] = {}
        self._register_default_tools()

    def _register_default_tools(self):
        """注册所有默认工具"""
        from .search import SearchTool
        from .shell import ShellTool
        from .user_interaction import UserInteractionTool
        from .user_confirmation import UserConfirmationTool
        from .python_script import PythonScriptTool
        from .file_ops import FileOperationTool
        from .rag import RAGTool
        from .webpage import WebpageTool

        tools = [
            SearchTool(),
            ShellTool(),
            UserInteractionTool(),
            UserConfirmationTool(),
            PythonScriptTool(),
            FileOperationTool(),
            RAGTool(),
            WebpageTool(),
        ]

        for tool in tools:
            self.register_tool(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters,
                func=tool.execute
            )

    def register_tool(self, name: str, description: str, parameters: Dict, func: Callable):
        """注册新工具"""
        self.tools[name] = Tool(name, description, parameters, func)

    def get_tool(self, name: str) -> Optional[Tool]:
        """获取工具"""
        return self.tools.get(name)

    def get_all_tools(self) -> List[Dict]:
        """获取所有工具的Ollama格式定义"""
        return [tool.to_dict() for tool in self.tools.values()]

    def execute_tool(self, name: str, arguments: Dict) -> Dict[str, Any]:
        """执行指定工具"""
        tool = self.get_tool(name)
        if tool is None:
            return {"success": False, "error": f"Tool {name} does not exist"}
        return tool.execute(arguments)

    def handle_tool_calls(self, tool_calls: List[Dict]) -> str:
        """处理工具调用"""
        results = []
        for tool_call in tool_calls:
            name = tool_call["function"]["name"]
            args = tool_call["function"]["arguments"]
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    return f"Invalid JSON in arguments for tool {name}"

            PrettyOutput.print(f"Calling tool: {name}", OutputType.INFO)
            if isinstance(args, dict):
                for key, value in args.items():
                    PrettyOutput.print(f"  - {key}: {value}", OutputType.INFO)
            else:
                PrettyOutput.print(f"  Arguments: {args}", OutputType.INFO)
            PrettyOutput.print("", OutputType.INFO)
            
            result = self.execute_tool(name, args)
            if result["success"]:
                stdout = result["stdout"]
                stderr = result.get("stderr", "")
                output_parts = []
                output_parts.append(f"Result:\n{stdout}")
                if stderr:
                    output_parts.append(f"Errors:\n{stderr}")
                output = "\n\n".join(output_parts)
            else:
                error_msg = result["error"]
                output = f"Execution failed: {error_msg}"
                    
            results.append(output)
        return "\n".join(results)

    def tool_help_text(self) -> str:
        """返回所有工具的帮助文本"""
        return """Available Tools:

1. search: Search for information using DuckDuckGo
2. read_webpage: Extract content from webpages
3. execute_python: Run Python code with dependency management
4. execute_shell: Execute shell commands
5. ask_user: Get input from user with options support
6. ask_user_confirmation: Get yes/no confirmation from user
7. file_operation: Read/write files in workspace directory
8. rag_query: Query documents using RAG

Output Guidelines:
1. Focus on Essential Information
   - Filter out irrelevant or redundant information
   - Only output the most relevant search results
   - Summarize long content when possible

2. Context Management
   - Avoid repeating information that's already known
   - Don't echo back the entire content of files
   - Use snippets instead of full documents

3. Error Handling
   - Only show relevant parts of error messages
   - Include troubleshooting steps when appropriate
   - Omit stack traces unless specifically requested

4. Search Results
   - Focus on the most relevant 2-3 results
   - Extract key information instead of full articles
   - Skip duplicate or similar content

5. RAG Queries
   - Return only the most relevant passages
   - Combine similar information
   - Skip redundant context

Tool Call Format Requirements:
1. MUST use exact format:
<tool_call>
{
    "name": "tool_name",
    "arguments": {
        "param1": "value1"
    }
}
</tool_call>

2. Format Rules:
   - NO comments or explanations inside tool_call blocks
   - NO additional text or formatting within JSON
   - NO markdown or other markup inside tool_call
   - ONLY valid JSON allowed in arguments
   - ALL arguments must match tool parameters exactly

3. Invalid Examples (DO NOT USE):
   ❌ <tool_call>
   {
       "name": "search",  # Search tool
       "arguments": {
           "query": "Python GIL"  // Search query
       }
   }
   </tool_call>

   ❌ <tool_call>
   ```json
   {
       "name": "search",
       "arguments": {
           "query": "Python GIL"
       }
   }
   ```
   </tool_call>

4. Valid Example:
   ✅ <tool_call>
   {
       "name": "search",
       "arguments": {
           "query": "Python GIL",
           "max_results": 2
       }
   }
   </tool_call>

Remember:
1. Quality over quantity
2. Relevance over completeness
3. Conciseness over verbosity
4. Context efficiency is crucial
5. STRICT adherence to tool call format"""