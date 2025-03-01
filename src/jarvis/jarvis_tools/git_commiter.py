import os
import re
import shlex
from typing import Dict, Any
import tempfile

import yaml
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils import OutputType, PrettyOutput, has_uncommitted_changes, init_env
import sys


class GitCommitTool:
    name = "git_commit_agent"
    description = "Automatically generate and execute git commits based on code changes"
    parameters = {"properties": {}, "required": []}

    def _extract_commit_message(self, message):
        """Extract commit message from response, handling multi-line and special characters"""
        r = re.search(r"<COMMIT_MESSAGE>(.*?)</COMMIT_MESSAGE>", message, re.DOTALL)
        if r:
            # Clean up the message
            msg = r.group(1).strip()
            # Remove any extra quotes or backslashes
            msg = msg.replace('\\"', '"').replace("\\'", "'")
            # Escape special characters for shell
            return shlex.quote(msg)
        return "Unknown commit message"
    
    def _get_last_commit_hash(self):
        return os.popen("git log -1 --pretty=%H").read().strip()

    def execute(self, args: Dict) -> Dict[str, Any]:
        """Execute automatic commit process with support for multi-line messages and special characters"""
        try:
            if not has_uncommitted_changes():
                PrettyOutput.print("没有未提交的更改", OutputType.SUCCESS)
                return {"success": True, "stdout": "No changes to commit", "stderr": ""}
            
            PrettyOutput.print("准备添加文件到提交...", OutputType.SYSTEM)
            os.system("git add .")
            
            PrettyOutput.print("获取差异...", OutputType.SYSTEM)
            diff = os.popen("git diff --cached --exit-code").read()
            PrettyOutput.print(diff, OutputType.CODE, lang="diff")
            
            prompt = f'''Please generate a commit message for the following changes.
            Format:
            <COMMIT_MESSAGE>
            type(scope): description
            
            Detailed description:
            - file1: changes description
            - file2: changes description
            </COMMIT_MESSAGE>
            
            Notes:
            1. Use multi-line format for detailed description
            2. Can include special characters
            3. First line is the short description
            4. Following lines are detailed explanation

            Changes:
            {diff}
            '''
            
            PrettyOutput.print("生成提交消息...", OutputType.SYSTEM)
            platform = PlatformRegistry().get_codegen_platform()
            platform.set_suppress_output(True)
            commit_message = platform.chat_until_success(prompt)
            commit_message = self._extract_commit_message(commit_message)
            
            # 使用临时文件处理提交消息
            with tempfile.NamedTemporaryFile(mode='w', delete=True) as tmp_file:
                tmp_file.write(commit_message)
                tmp_file.flush()  # 确保内容写入文件
                commit_cmd = f"git commit -F {tmp_file.name}"
                PrettyOutput.print("提交...", OutputType.INFO)
                os.system(commit_cmd)

            commit_hash = self._get_last_commit_hash()
            PrettyOutput.print(f"提交哈希: {commit_hash}\n提交消息: {commit_message}", OutputType.SUCCESS)

            return {
                "success": True,
                "stdout": yaml.safe_dump({
                    "commit_hash": commit_hash,
                    "commit_message": commit_message
                }),
                "stderr": ""
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Commit failed: {str(e)}"
            }

def main():
    init_env()
    tool = GitCommitTool()
    tool.execute({})

if __name__ == "__main__":
    sys.exit(main())
