from typing import Dict, Any, List
import subprocess
import yaml
from jarvis.models.registry import PlatformRegistry
from jarvis.tools.registry import ToolRegistry
from jarvis.utils import OutputType, PrettyOutput, init_env, find_git_root
from jarvis.agent import Agent
import re

class CodeReviewTool:
    name = "code_review"
    description = "Autonomous code review agent for code changes analysis"
    parameters = {
        "type": "object",
        "properties": {
            "review_type": {
                "type": "string",
                "description": "Type of review: 'commit' for specific commit, 'current' for current changes",
                "enum": ["commit", "current"],
                "default": "current"
            },
            "commit_sha": {
                "type": "string",
                "description": "Target commit SHA to analyze (required for review_type='commit')"
            }
        },
        "required": []
    }

    def __init__(self):
        init_env()
        self.repo_root = find_git_root()

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            review_type = args.get("review_type", "current").strip()
            
            # Build git diff command based on review type
            if review_type == "commit":
                if "commit_sha" not in args:
                    return {
                        "success": False,
                        "stdout": {},
                        "stderr": "commit_sha is required for commit review type"
                    }
                commit_sha = args["commit_sha"].strip()
                diff_cmd = f"git show {commit_sha} | cat -"
            else:  # current changes
                diff_cmd = "git diff HEAD | cat -"
            
            # Execute git diff command
            try:
                diff_output = subprocess.check_output(diff_cmd, shell=True, text=True)
                if not diff_output:
                    return {
                        "success": False,
                        "stdout": {},
                        "stderr": "No changes to review"
                    }
                PrettyOutput.print(diff_output, OutputType.CODE, lang="diff")
            except subprocess.CalledProcessError as e:
                return {
                    "success": False,
                    "stdout": {},
                    "stderr": f"Failed to get diff: {str(e)}"
                }

            prompt = """You are an autonomous code review expert. Perform in-depth analysis following these guidelines:

REVIEW FOCUS AREAS:
1. Requirement Alignment:
   - Verify implementation matches original requirements
   - Check for missing functionality
   - Identify over-implementation

2. Code Quality:
   - Code readability and structure
   - Proper error handling
   - Code duplication
   - Adherence to style guides
   - Meaningful variable/method names

3. Security:
   - Input validation
   - Authentication/Authorization checks
   - Sensitive data handling
   - Potential injection vulnerabilities
   - Secure communication practices

4. Testing:
   - Test coverage for new code
   - Edge case handling
   - Test readability and maintainability
   - Missing test scenarios

5. Performance:
   - Algorithm efficiency
   - Unnecessary resource consumption
   - Proper caching mechanisms
   - Database query optimization

6. Maintainability:
   - Documentation quality
   - Logging and monitoring
   - Configuration management
   - Technical debt indicators

7. Operational Considerations:
   - Backward compatibility
   - Migration script safety
   - Environment-specific configurations
   - Deployment impacts

REVIEW PROCESS:
1. Retrieve full commit context using git commands
2. Analyze code changes line-by-line
3. Cross-reference with project standards
4. Verify test coverage adequacy
5. Check documentation updates
6. Generate prioritized findings

OUTPUT REQUIREMENTS:
- Categorize issues by severity (Critical/Major/Minor)
- Reference specific code locations
- Provide concrete examples
- Suggest actionable improvements
- Highlight security risks clearly
- Separate technical debt from blockers

Please generate a concise summary report of the code review, format as yaml:
<REPORT>
- file: xxxx.py
  location: [start_line_number, end_line_number]
  description: 
  severity: 
  suggestion: 
</REPORT>

Diff:
```diff
{diff_output}
```
"""
            result = PlatformRegistry().get_thinking_platform().chat_until_success(prompt)

            return {
                "success": True,
                "stdout": result,
                "stderr": ""
            }
            
        except Exception as e:
            return {
                "success": False,
                "stdout": {},
                "stderr": f"Review failed: {str(e)}"
            }
        

def _extract_code_report(result: str) -> List[Dict[str, Any]]:
    sm = re.search(r"<REPORT>(.*?)</REPORT>", result, re.DOTALL)
    if sm:
        report = sm.group(1)
        try:
            report = yaml.safe_load(report)
        except Exception as e:
            return []
        return report
    return []

def main():
    """CLI entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Autonomous code review tool')
    parser.add_argument('--type', choices=['commit', 'current'], default='current',
                      help='Type of review: commit or current changes')
    parser.add_argument('--commit', help='Commit SHA to review (required for commit type)')
    args = parser.parse_args()
    
    # Validate arguments
    if args.type == 'commit' and not args.commit:
        parser.error("--commit is required when type is 'commit'")
    
    tool = CodeReviewTool()
    tool_args = {
        "review_type": args.type
    }
    if args.commit:
        tool_args["commit_sha"] = args.commit
    
    result = tool.execute(tool_args)
    
    if result["success"]:
        PrettyOutput.section("Autonomous Review Result:", OutputType.SUCCESS)
        report = _extract_code_report(result["stdout"])
        output = ""
        for item in report:
            for k, v in item.items():
                output += f"{k}: {v}\n"
            output += "=" * 80 + "\n"
        PrettyOutput.print(output, OutputType.SUCCESS)
        
    else:
        PrettyOutput.print(result["stderr"], OutputType.ERROR)

if __name__ == "__main__":
    main()
