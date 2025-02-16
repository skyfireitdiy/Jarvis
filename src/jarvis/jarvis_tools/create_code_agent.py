import os
from typing import Dict, Any
from jarvis.jarvis_code_agent.code_agent import CodeAgent
from jarvis.jarvis_tools.git_commiter import GitCommitTool
from jarvis.jarvis_tools.code_review import CodeReviewTool
from jarvis.utils import OutputType, PrettyOutput, has_uncommitted_changes
import subprocess

class CreateCodeAgentTool:
    """Tool for managing the code development workflow."""
    
    name = "create_code_agent"
    description = "Manage code development workflow including commit, development, and review"
    parameters = {
        "requirement": "The development requirement or task description"
    }
    
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            requirement = args.get("requirement", "")
            if not requirement:
                return {
                    "success": False,
                    "stderr": "Requirement must be provided",
                    "stdout": ""
                }
            
            # Step 1: Handle uncommitted changes
            start_commit = None
            if has_uncommitted_changes():
                PrettyOutput.print("Found uncommitted changes, committing first...", OutputType.INFO)
                git_commiter = GitCommitTool()
                result = git_commiter.execute({})
                if not result["success"]:
                    return {
                        "success": False,
                        "stderr": "Failed to commit changes: " + result["stderr"],
                        "stdout": ""
                    }
            
            # Get current commit hash
            start_commit = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
            
            # Step 2: Development
            PrettyOutput.print("Starting development...", OutputType.INFO)
            agent = CodeAgent()
            agent.run(requirement)
            
            # Get new commit hash after development
            end_commit = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
            
            # Step 3: Code Review
            PrettyOutput.print("Starting code review...", OutputType.INFO)
            reviewer = CodeReviewTool()
            review_result = reviewer.execute({
                "review_type": "range",
                "start_commit": start_commit,
                "end_commit": end_commit
            })
            
            if not review_result["success"]:
                return {
                    "success": False,
                    "stderr": "Code review failed: " + review_result["stderr"],
                    "stdout": ""
                }
            
            # Step 4: Generate Summary
            summary = f"""Development Summary:
            
Start Commit: {start_commit}
End Commit: {end_commit}

Requirement:
{requirement}

Code Review Result:
{review_result["stdout"]}
"""
            
            return {
                "success": True,
                "stdout": summary,
                "stderr": ""
            }
            
        except Exception as e:
            return {
                "success": False,
                "stderr": f"Development workflow failed: {str(e)}",
                "stdout": ""
            }

def main():
    """CLI entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Code development workflow tool')
    parser.add_argument('requirement', help='Development requirement or task description')
    
    args = parser.parse_args()
    
    tool = CreateCodeAgentTool()
    result = tool.execute({"requirement": args.requirement})
    
    if result["success"]:
        PrettyOutput.print(result["stdout"], OutputType.SUCCESS)
    else:
        PrettyOutput.print(result["stderr"], OutputType.ERROR)

if __name__ == "__main__":
    main()
