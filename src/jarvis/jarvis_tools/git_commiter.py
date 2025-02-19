import os
import re
from typing import Dict, Any

import yaml
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.utils import OutputType, PrettyOutput, init_env
import sys


class GitCommitTool:
    name = "git_commit_agent"
    description = "Automatically generate and execute git commits based on code changes"
    parameters = {"properties": {}, "required": []}

    def _extract_commit_message(self, message):
        r = re.search(r"<COMMIT_MESSAGE>(.*)</COMMIT_MESSAGE>", message, re.DOTALL)
        if r:
            return ';'.join(r.group(1).strip().splitlines())
        return "Unknown commit message"
    
    def _get_last_commit_hash(self):
        return os.popen("git log -1 --pretty=%H").read().strip()

    def execute(self, args: Dict) -> Dict[str, Any]:
        """Execute automatic commit process"""
        try:
            PrettyOutput.print("Add files to commit...", OutputType.SYSTEM)
            os.system("git add .")
            PrettyOutput.print("Get diff...", OutputType.SYSTEM)
            diff = os.popen("git diff --cached --exit-code").read()
            PrettyOutput.print(diff, OutputType.CODE, lang="diff")
            prompt = f'''Please generate a commit message for the following changes.
            Format:
            <COMMIT_MESSAGE>
            type(scope): description
            </COMMIT_MESSAGE>
            
            Don't include any other information.

            {diff}
            '''
            PrettyOutput.print("Generate commit message...", OutputType.SYSTEM)
            platform = PlatformRegistry().get_codegen_platform()
            platform.set_suppress_output(True)
            commit_message = platform.chat_until_success(prompt)
            commit_message = self._extract_commit_message(commit_message)
            PrettyOutput.print("Commit...", OutputType.INFO)
            os.popen(f"git commit -m '{commit_message}'")

            commit_hash = self._get_last_commit_hash()

            PrettyOutput.section(f"Commit hash: {commit_hash}\nCommit message: {commit_message}", OutputType.SUCCESS)

            return {"success": True, "stdout": yaml.safe_dump({"commit_hash": commit_hash, "commit_message": commit_message}), "stderr": ""}

        except Exception as e:
            return {"success": False, "stdout": "", "stderr": f"Commit error: {str(e)}"}

def main():
    init_env()
    tool = GitCommitTool()
    tool.execute({})

if __name__ == "__main__":
    sys.exit(main())
