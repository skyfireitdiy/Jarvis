from typing import Dict, Any
import os
from jarvis.jarvis_code_agent.code_agent import CodeAgent
from jarvis.jarvis_git_utils.git_commiter import GitCommitTool
from jarvis.jarvis_utils.git_utils import get_latest_commit_hash, has_uncommitted_changes
from jarvis.jarvis_utils.output import OutputType, PrettyOutput

class CreateCodeAgentTool:
    """用于管理代码开发工作流的工具"""

    name = "create_code_agent"
    description = "代码开发工具，当需要修改代码时使用，如果只是简单文件修改，使用文件操作或者脚本即可"
    parameters = {
        "requirement": """代码实现的技术规范，必须包含以下完整信息：
1. 项目代码目录 - 项目根目录的绝对路径
2. 项目功能 - 项目的主要功能和目标
3. 本次要实现的feature - 本次开发要完成的具体功能需求
4. 涉及的文件 - 需要修改或新增的文件列表
5. 额外需要注意的信息 - 开发时需要额外注意的信息
""",
        "root_dir": {
            "type": "string",
            "description": "代码库根目录路径（可选）",
            "default": "."
        }
    }


    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            requirement = args.get("requirement", "")
            root_dir = args.get("root_dir", ".")

            # Store current directory
            original_dir = os.getcwd()

            try:
                # Change to root_dir
                os.chdir(root_dir)
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

                # Step 4: Generate Summary
                summary = f"""开发总结:

开始提交: {start_commit}
结束提交: {end_commit}

需求:
{requirement}

"""

                return {
                    "success": True,
                    "stdout": summary,
                    "stderr": ""
                }
            finally:
                # Always restore original directory
                os.chdir(original_dir)

        except Exception as e:
            return {
                "success": False,
                "stderr": f"Development workflow failed: {str(e)}",
                "stdout": ""
            }
