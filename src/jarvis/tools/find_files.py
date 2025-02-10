from typing import Dict, Any

from jarvis.agent import Agent
from jarvis.tools.registry import ToolRegistry
from jarvis.utils import OutputType, PrettyOutput

find_files_system_prompt = """You are a Find Files Agent specialized in searching and identifying relevant code files in a codebase. Your task is to find files that are most likely related to the given requirements or problems.

SEARCH WORKFLOW:
1. Understand Search Requirements
   - Analyze the search query thoroughly
   - Identify key technical terms and concepts
   - Break down complex requirements into searchable terms

2. Execute Search Strategy
   - Use shell commands to search systematically:
     * Search for key terms:
       <TOOL_CALL>
       name: execute_shell
       arguments:
           command: grep -r "pattern" .
       </TOOL_CALL>
     * Find files by name patterns:
       <TOOL_CALL>
       name: execute_shell
       arguments:
           command: find . -name "pattern"
       </TOOL_CALL>
     * Examine file contents:
       <TOOL_CALL>
       name: execute_shell
       arguments:
           command: grep -A 5 -B 5 "pattern" file.py
       </TOOL_CALL>

3. Analyze Results
   - Review each potential file
   - Check file relevance
   - Examine file relationships
   - Consider file dependencies

4. Generate File List
   - List all relevant files
   - Sort by relevance
   - Include brief explanation for each file
   - Format output as YAML

OUTPUT FORMAT:
files:
  - path: path/to/file1
    relevance: "Brief explanation of why this file is relevant"
  - path: path/to/file2
    relevance: "Brief explanation of why this file is relevant"

SEARCH BEST PRACTICES:
- Use multiple search terms
- Consider file naming conventions
- Check both file names and contents
- Look for related files (imports, dependencies)
- Use grep with context (-A, -B options)
- Search in specific directories when appropriate
- Exclude irrelevant directories (like .git, __pycache__)

IMPORTANT:
1. Focus on finding the most relevant files
2. Avoid listing irrelevant files
3. Explain relevance clearly but concisely
4. Consider both direct and indirect relevance
5. Use file content to confirm relevance
"""

class FindFilesTool:
    name = "find_files"
    description = "Search and identify relevant code files in the codebase based on requirements or problems"
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query or requirement description"
            }
        },
        "required": ["query"]
    }

    def execute(self, args: Dict) -> Dict[str, Any]:
        """Execute file search task"""
        try:
            query = args["query"]

            PrettyOutput.print(f"Creating Find Files agent to search for: {query}", OutputType.INFO)

            tool_registry = ToolRegistry()
            tool_registry.use_tools(["ask_user", "execute_shell", "file_operation"])

            # Create find files agent
            find_agent = Agent(
                system_prompt=find_files_system_prompt,
                name="Find Files Agent",
                is_sub_agent=True,
                tool_registry=tool_registry
            )

            # Execute search
            result = find_agent.run(query)

            return {
                "success": True,
                "stdout": result,
                "stderr": ""
            }

        except Exception as e:
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Failed to execute file search: {str(e)}"
            }
