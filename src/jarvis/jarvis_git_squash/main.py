import sys
import argparse
from typing import Dict, Any
from jarvis.jarvis_tools.git_commiter import GitCommitTool
import subprocess

from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import init_env, user_confirm
class GitSquashTool:
    name = "git_squash_agent"
    description = "Squash commits interactively using a base commit hash"
    
    def _confirm_squash(self) -> bool:
        """Prompt user for confirmation to squash commits"""
        return user_confirm("是否确认压缩提交?", default=True)
    
    def _reset_to_commit(self, commit_hash: str) -> bool:
        """Perform soft reset to specified commit hash"""
        try:
            subprocess.Popen(
                ["git", "reset", "--soft", commit_hash],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            ).wait()
            return True
        except Exception:
            return False
    
    def execute(self, args: Dict) -> Dict[str, Any]:
        """Execute the squash operation"""
        try:
            if not self._confirm_squash():
                return {
                    "success": False,
                    "stdout": "Operation cancelled",
                    "stderr": ""
                }
            
            if not self._reset_to_commit(args['commit_hash']):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "Failed to reset to specified commit"
                }
            
            # Use existing GitCommitTool for new commit
            commit_tool = GitCommitTool()
            result = commit_tool.execute({"lang": args.get('lang', 'Chinese')})
            
            return {
                "success": result['success'],
                "stdout": result['stdout'],
                "stderr": result['stderr']
            }
            
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Squash failed: {str(e)}"
            }
def main():
    init_env()
    parser = argparse.ArgumentParser(description='Git squash tool')
    parser.add_argument('commit_hash', type=str, help='Base commit hash to squash from')
    parser.add_argument('--lang', type=str, default='Chinese', help='Language for commit messages')
    args = parser.parse_args()
    
    tool = GitSquashTool()
    result = tool.execute({
        'commit_hash': args.commit_hash,
        'lang': args.lang
    })
    
    if not result['success']:
        PrettyOutput.print(result['stderr'], OutputType.ERROR)
        sys.exit(1)
        
    PrettyOutput.print(result['stdout'], OutputType.SUCCESS)
if __name__ == "__main__":
    sys.exit(main())
