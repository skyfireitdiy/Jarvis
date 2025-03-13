from typing import Dict, Any
from jarvis.jarvis_code_agent.code_agent import CodeAgent
from jarvis.jarvis_tools.git_commiter import GitCommitTool
from jarvis.jarvis_tools.code_review import CodeReviewTool, extract_code_report
from jarvis.jarvis_utils.git_utils import get_latest_commit_hash, has_uncommitted_changes
from jarvis.jarvis_utils.output import OutputType, PrettyOutput

class CreateCodeAgentTool:
    """用于管理代码开发工作流的工具"""
    
    name = "create_code_agent"
    description = "技术代码实现和开发过程管理工具"
    parameters = {
        "requirement": "代码实现的技术规范"
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
                PrettyOutput.print("发现未提交的更改，正在提交...", OutputType.INFO)
                git_commiter = GitCommitTool()
                result = git_commiter.execute({})
                if not result["success"]:
                    return {
                        "success": False,
                        "stderr": "Failed to commit changes: " + result["stderr"],
                        "stdout": ""
                    }
            
            # Get current commit hash
            start_commit = get_latest_commit_hash()
            
            # Step 2: Development
            PrettyOutput.print("开始开发...", OutputType.INFO)
            agent = CodeAgent()
            agent.run(requirement)
            
            # Get new commit hash after development
            end_commit = get_latest_commit_hash()
            
            # Step 3: Code Review
            PrettyOutput.print("开始代码审查...", OutputType.INFO)
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
            summary = f"""开发总结:
            
开始提交: {start_commit}
结束提交: {end_commit}

需求:
{requirement}

代码审查结果:
{extract_code_report(review_result["stdout"])}
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
        PrettyOutput.print(result["stderr"], OutputType.WARNING)

if __name__ == "__main__":
    main()