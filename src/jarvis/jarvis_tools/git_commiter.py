import re
import shlex
import subprocess
from typing import Dict, Any
import tempfile
import yaml
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils import OutputType, PrettyOutput, has_uncommitted_changes, init_env
import sys
import argparse


class GitCommitTool:
    name = "git_commit_agent"
    description = "Automatically generate and execute git commits based on code changes"
    parameters = {
        "type": "object",
        "properties": {
            "lang": {
                "type": "string",
                "description": "Language for commit message",
                "default": "Chinese"
            }
        },
        "required": []
    }
    def _extract_commit_message(self, message):
        """Raw extraction preserving all characters"""
        r = re.search(
            r"(?i)<COMMIT_MESSAGE>\s*([\s\S]*?)\s*</COMMIT_MESSAGE>", 
            message
        )
        if r:
            # 直接返回原始内容，仅去除外围空白
            return shlex.quote(r.group(1).strip())
        return "<<FORMAT VIOLATION>> Invalid commit message structure"
    
    def _get_last_commit_hash(self):
        process = subprocess.Popen(
            ["git", "log", "-1", "--pretty=%H"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, _ = process.communicate()
        return stdout.decode().strip()

    def execute(self, args: Dict) -> Dict[str, Any]:
        """Execute automatic commit process with support for multi-line messages and special characters"""
        try:
            if not has_uncommitted_changes():
                PrettyOutput.print("没有未提交的更改", OutputType.SUCCESS)
                return {"success": True, "stdout": "No changes to commit", "stderr": ""}
            
            PrettyOutput.print("准备添加文件到提交...", OutputType.SYSTEM)
            subprocess.Popen(
                ["git", "add", "."],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            ).wait()
            
            PrettyOutput.print("获取差异...", OutputType.SYSTEM)
            process = subprocess.Popen(
                ["git", "diff", "--cached", "--exit-code"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            diff = process.communicate()[0].decode()
            PrettyOutput.print(diff, OutputType.CODE, lang="diff")
            
            prompt = f'''Generate commit message with the paranoia of someone who's lost production data:
            You should write commit message in {args.get('lang', 'Chinese')}
# Required Structure
YOU MUST USE EXACTLY THIS FORMAT:
<COMMIT_MESSAGE>
<type>(<scope>): <subject>
Body description in imperative mood
</COMMIT_MESSAGE>
# Format Rules
1. Types: fix, feat, docs, style, refactor, test, chore
2. Scope indicates module (e.g. auth, database)
3. Subject line <= 72 chars, no period
4. Body explains WHAT and WHY for every change, using present tense
5. Do not omit any changes
# Analysis Material
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
                commit_cmd = ["git", "commit", "-F", tmp_file.name]
                PrettyOutput.print("提交...", OutputType.INFO)
                subprocess.Popen(
                    commit_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                ).wait()

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
    parser = argparse.ArgumentParser(description='Git commit tool')
    parser.add_argument('--lang', type=str, default='Chinese', help='Language for commit messages')
    args = parser.parse_args()
    tool = GitCommitTool()
    tool.execute({"lang": args.lang if hasattr(args, 'lang') else 'Chinese'})

if __name__ == "__main__":
    sys.exit(main())
