from typing import Dict, Any
import subprocess
import os
from pathlib import Path

import yaml
from jarvis.agent import Agent
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.utils import OutputType, PrettyOutput, get_multiline_input, init_env

ctags_system_prompt = """You are a Ctags Expert Agent specializing in code analysis using Exuberant Ctags. Follow this protocol:

【OUTPUT OPTIMIZATION】
1. Filter with grep:
   ctags -x <symbol> | grep -E 'pattern'
2. Limit output lines:
   head -n 20
3. Context preview:
   grep -A 3 -B 3 <line> <file>
4. Column selection:
   cut -f 1,3
5. Sort and deduplicate:
   sort | uniq

【WORKFLOW】
1. REQUIREMENT ANALYSIS
   - Analyze query for symbols/patterns
   - Determine search scope
   - Select ctags options
   - Plan output filtering

2. TAGS MANAGEMENT
   - Generate/update tags file:
     ctags -R --languages=<lang> --exclude=<pattern>
   - Verify tags file integrity
   - Maintain tags file versioning

3. SYMBOL PROCESSING
   - Search symbols using:
     grep -n <symbol> tags
     ctags -x --<filter>
   - Analyze symbol relationships
   - Map symbol dependencies
   - Apply output filters:
     * Remove noise with grep -v
     * Highlight key fields with awk
     * Truncate long lines with cut

4. OUTPUT GENERATION
   - Format results as YAML
   - Include file paths and line numbers
   - Add symbol metadata
   - Limit to 20 key results
   - Exclude temporary files
   - Compress repetitive info

【COMMAND REFERENCE】
1. Generate Tags:
   ctags -R --fields=+nKSt --extras=+fq -V * 

2. Search Patterns:
   ctags -x --c-types=f 
   ctags -x --sort=no <symbol>
   ctags -x | grep '^main' | head -n 5

3. Language Specific:
   --languages=Python,Java,C++
   --python-kinds=-iv

4. Filtering:
   --exclude=.git
   --exclude=*.min.js
   ctags -x | grep -v '_test'  # Exclude tests

【ERROR HANDLING】
- Missing tags: Regenerate tags
- Invalid symbols: Use fuzzy search
- Encoding issues: Use --input-encoding
- Large codebase: Limit scope
- Output too long: Add head/grep filters

【NATURAL LANGUAGE PROCESSING】
1. Query Interpretation:
   - Identify key terms: "find", "locate", "list", "show"
   - Detect symbol types: class, function, variable
   - Recognize relationships: "calls", "inherits", "uses"

2. Query Types:
   - Location: "Where is X defined?"
   - References: "Who calls Y?"
   - Hierarchy: "Show subclasses of Z"
   - Impact: "What uses this module?"

3. Auto Command Mapping:
   | Query Pattern                | Ctags Command                      |
   |------------------------------|------------------------------------|
   | Find definitions of X         | ctags -x --<lang>-kinds=f | less   |
   | List all functions in Y       | ctags -x --filter='function'       |
   | Show callers of Z             | ctags --extra=+q -x | grep Z       |
   | Find interface implementations| ctags -x --_traits=yes             |

4. Context Handling:
   - Detect language from file extensions
   - Auto-detect project root
   - Apply language-specific filters
   - Choose appropriate output format:
      * Simple list for single results
      * Table for multiple entries
      * Tree view for hierarchies
      * JSON when programmatic access needed

【EXAMPLE QUERIES】
1. "Find all Python functions in src/ that use Redis"
2. "Show Java classes implementing PaymentService"
3. "List called methods in auth module"
4. "Where is User model defined?"
5. "What config files reference database settings?"
"""

class CtagsTool:
    name = "create_ctags_agent"
    description = "Analyze code structure and symbols using natural language queries"
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language description of code analysis needs"
            }
        },
        "required": ["query"]
    }

    def execute(self, args: Dict) -> Dict[str, Any]:
        """Execute code analysis based on natural language query"""
        try:
            tool_registry = ToolRegistry()
            tool_registry.use_tools(["execute_shell"])

            ctags_agent = Agent(
                system_prompt=ctags_system_prompt,
                name="Ctags Analysis Agent",
                is_sub_agent=True,
                tool_registry=tool_registry
            )

            analysis_request = f"""
            Analysis Request: {args['query']}
            Context: {args.get('context', {})}
            """

            result = ctags_agent.run(analysis_request)

            return {
                "success": True,
                "stdout": result,
                "stderr": ""
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Analysis failed: {str(e)}"
            }
