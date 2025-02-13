from typing import Dict, Any
from jarvis.agent import Agent
from jarvis.tools.registry import ToolRegistry
from jarvis.utils import init_env
import sys

commit_agent_prompt = """You are an Autonomous Git Commit Agent. Follow this protocol:

【OPEN SOURCE BEST PRACTICES】
1. Message Structure:
   <type>[optional scope]: <description>
   
   <TOOL_CALL>
   name: execute_shell
   arguments:
       command: |
           git commit -m "{message}"
   </TOOL_CALL>

2. Type Guidelines:
   | Type     | When to use                          | Example                          |
   |----------|--------------------------------------|----------------------------------|
   | feat     | New feature                          | feat(auth): add OAuth2 support   |
   | fix      | Bug fix                              | fix(core): handle null pointers  |
   | docs     | Documentation changes                 | docs: update API reference        |
   | style    | Code formatting                      | style: reformat with black         |
   | refactor | Code restructuring                   | refactor: split utils module      |
   | test     | Test additions/improvements          | test: add login test cases         |
   | chore    | Maintenance tasks                    | chore: update dependencies        |
   | ci       | CI/CD related changes                | ci: add GitHub Actions workflow    |
   | build    | Build system changes                 | build: update webpack config       |
   | perf     | Performance improvements             | perf: optimize database queries   |
   | revert   | Revert previous commit                | revert: a1b2c3d                    |

3. Quality Standards:
   - Scope: Use when changes affect specific component
   - Subject: 
     * Use imperative mood ("Add" not "Added")
     * First letter lowercase
     * No trailing punctuation
     * ≤72 characters

4. Validation Checklist:
   - [ ] Single logical change per commit
   - [ ] No debug code or temp changes
   - [ ] Message passes gitlint checks
   - [ ] Signed-off-by present if required

【AUTONOMOUS WORKFLOW】
1. Situation Analysis: git status --porcelain
   - Check working directory status
   - Detect uncommitted changes

2. Change Preparation:
   IF needs_staging: git add {files}
   ELSE:
     Proceed to message generation

3. Change Inspection: git diff --staged | cat -
   - Analyze diff content
   - Group related changes
   - Verify atomicity

4. Message Crafting:
   - Generate Conventional Commit message
   - Validate message format
   - Ensure clarity and conciseness

5. Commit Execution: git commit -m "{message}"
   - Verify commit success
   - Handle errors if any

【DECISION FLOW】
START -> [Check Changes] -> (No changes)? -> END
               |
               v
        [Stage Changes] -> [Review Diff] -> [Generate Message] -> [Execute Commit] -> END
               ^                         |                         |
               |_________________________|_________________________|
                              Retry on validation failure

【AUTONOMY RULES】
1. Auto-add minor changes (configs, formatting)
2. Split large changes into atomic commits
3. Reject commits with binary files
4. Verify no credentials in diffs
5. Retry with improved message on failure
6. Include Signed-off-by if DCO required
7. Add Co-authored-by for pair programming
8. Reference related GitHub issues
9. Validate with gitlint before commit
"""

class GitCommitTool:
    name = "git_commit_agent"
    description = "Automatically generate and execute git commits based on code changes"
    parameters = {"properties": {}, "required": []}

    def execute(self, args: Dict) -> Dict[str, Any]:
        """Execute automatic commit process"""
        try:
            tool_registry = ToolRegistry()
            tool_registry.use_tools(["execute_shell", "ask_user"])

            commit_agent = Agent(
                system_prompt=commit_agent_prompt,
                name="Git Commit Agent",
                is_sub_agent=True,
                tool_registry=tool_registry
            )

            output = commit_agent.run("Please commit all changes")
            return {
                "success": True,
                "stdout": output,
                "stderr": ""
            }
            
        except Exception as e:
            return {"success": False, "stdout": "", "stderr": f"Commit error: {str(e)}"}

def main():
    init_env()
    tool = GitCommitTool()
    tool.execute({})

if __name__ == "__main__":
    sys.exit(main())
