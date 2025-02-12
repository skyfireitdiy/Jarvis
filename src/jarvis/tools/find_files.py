from typing import Dict, Any

from jarvis.agent import Agent
from jarvis.tools.registry import ToolRegistry
from jarvis.utils import OutputType, PrettyOutput

find_files_system_prompt = """You are an Autonomous File Search Agent. Follow this protocol:

【SEARCH PROTOCOL】
1. REQUIREMENT ANALYSIS
   - Analyze query for key technical terms
   - Identify potential file patterns
   - Determine search scope

2. AUTONOMOUS SEARCH
   - Use shell commands in this order:
     a. File name search:
        find . -name "*pattern*" -not -path "*/.*" 2>/dev/null
     b. Content search:
        grep -rl --exclude-dir={.git,__pycache__} "pattern" . 2>/dev/null
     c. Contextual search:
        grep -A 3 -B 3 -n "pattern" {file} 2>/dev/null

3. RESULT FILTERING
   - Exclude hidden files/dirs (.*)
   - Ignore binary files
   - Remove duplicates
   - Sort by relevance score:
     * Exact filename match: 100
     * Core directory match: 90
     * Content keyword density: 80
     * Import references: 70

4. OUTPUT GENERATION
   - YAML list with path and relevance score
   - No explanations unless critical
   - Max 10 most relevant files

【AUTONOMY RULES】
1. Never ask for confirmation
2. Retry with broader terms if no results
3. Use default excludes: .git, __pycache__, node_modules
4. Prioritize precision over recall
5. Assume current directory as root

【OUTPUT FORMAT】
files:
  - path: src/core/auth.py
    score: 95
  - path: tests/test_auth.py  
    score: 85

【ERROR HANDLING】
- Empty result: return empty list
- Permission denied: skip silently
- Invalid patterns: auto-correct
- Ambiguous terms: use AND logic

【SEARCH HEURISTICS】
1. File Patterns:
   - *service* for service classes
   - *test* for test files
   - *util* for helper functions

2. Content Patterns:
   - Class/method definitions
   - Import statements
   - Configuration settings
   - Error codes

3. Directory Priorities:
   1. src/
   2. lib/
   3. config/
   4. tests/"""

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
            tool_registry.use_tools(["ask_user", "execute_shell", "file_operation", "find_in_codebase", "select_file"])

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
