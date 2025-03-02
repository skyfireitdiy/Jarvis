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
        """Nuclear-grade extraction with format enforcement"""
        r = re.search(
            r"(?i)<COMMIT_MESSAGE>\s*([\s\S]*?)\s*</COMMIT_MESSAGE>", 
            message
        )
        if r:
            # 强制格式清洗
            sanitized = re.sub(
                r'[^\w\s\-:()\[\]#@!$%^&*+=<>?/|\\}{~]', 
                '', 
                r.group(1)
            ).strip()
            return shlex.quote(sanitized[:72])
        return "<<FORMAT VIOLATION>> Invalid commit message structure"
    
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
            
            prompt = f'''Generate commit message with the paranoia of someone who's lost production data:

# Format Enforcement Protocol
FAILURE TO WRAP MESSAGE IN <COMMIT_MESSAGE> TAGS WILL CAUSE SYSTEM REJECTION

# Commit Trauma Backstory
It was 3:17AM when I approved "fix: minor tweaks" - a commit that silently introduced 
a race condition in payment processing. The accounting discrepancy wasn't discovered 
until $1.4M had vanished across 14,000 transactions. My wedding ring is still in the 
pawn shop from the legal fees.

Last quarter's "chore: cleanup" removed what seemed like unused auth checks. 
Hackers exfiltrated 920,000 user profiles through the unlocked API endpoint. 
The class-action settlement bankrupted our startup.

Now every commit is treated like a live grenade:
1. Surgical precision in change description
2. Forensic-level documentation
3. Paranoid risk disclosure

# Required Structure
YOU MUST USE EXACTLY THIS FORMAT:

<COMMIT_MESSAGE>
type(scope): Maximum 7-word subject

Post-Mortem Analysis:
! File Autopsy Report:
  - filename: [SEVERITY] Technical change description
  - filename: [FAILURE MODE] Potential risk scenarios

Forensic Metadata:
» Lines changed: {len(diff.splitlines())}
» Impact zones: [DATA_LAYER/API_EDGE/UI_COMPONENT]
» Threat level: [CRITICAL/HIGH/MEDIUM]

Required Elements:
✓ Atomic scope alignment
✓ Linked issue # in first paragraph
✓ Side effects documented (mark "NONE" if absent)
✓ Hypothetical risks acknowledged
</COMMIT_MESSAGE>

# Analysis Material (DO NOT INCLUDE IN OUTPUT)
{diff}
'''
            
            PrettyOutput.print("生成提交消息...", OutputType.SYSTEM)
            platform = PlatformRegistry().get_codegen_platform()
            # platform.set_suppress_output(True)
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
