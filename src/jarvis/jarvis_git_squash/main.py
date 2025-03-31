import sys
import argparse
from typing import Dict
from jarvis.jarvis_git_utils.git_commiter import GitCommitTool
import subprocess

from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import init_env, user_confirm
class GitSquashTool:
    name = "git_squash_agent"
    description = "Squash commits interactively using a base commit hash"
    labels = ['git', 'version_control', 'squash']

    def _confirm_squash(self) -> bool:
        """Prompt user for confirmation to squash commits"""
        return user_confirm("是否确认压缩提交?", default=True)

    def _reset_to_commit(self, commit_hash: str) -> bool:
        """Perform soft reset to specified commit hash"""
        try:
            subprocess.Popen(
                ["git", "reset", "--mixed", commit_hash],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            ).wait()
            return True
        except Exception:
            return False

    def execute(self, args: Dict):
        """Execute the squash operation"""
        try:
            if not self._confirm_squash():
                PrettyOutput.print("操作已取消", OutputType.WARNING)
                return

            if not self._reset_to_commit(args['commit_hash']):
                PrettyOutput.print("重置到指定提交失败", OutputType.WARNING)
                return

            # Use existing GitCommitTool for new commit
            commit_tool = GitCommitTool()
            commit_tool.execute({"lang": args.get('lang', 'Chinese')})
        except Exception as e:
            PrettyOutput.print(f"压缩提交失败: {str(e)}", OutputType.WARNING)

def main():
    init_env()
    parser = argparse.ArgumentParser(description='Git squash tool')
    parser.add_argument('commit_hash', type=str, help='Base commit hash to squash from')
    parser.add_argument('--lang', type=str, default='Chinese', help='Language for commit messages')
    args = parser.parse_args()

    tool = GitSquashTool()
    tool.execute({
        'commit_hash': args.commit_hash,
        'lang': args.lang
    })
if __name__ == "__main__":
    sys.exit(main())
