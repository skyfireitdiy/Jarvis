import re
import shlex
import subprocess
from typing import Dict, Any
import tempfile
import yaml
from jarvis.jarvis_platform.registry import PlatformRegistry
import sys
import argparse

from jarvis.jarvis_utils.git_utils import has_uncommitted_changes
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import init_env


class GitCommitTool:
    name = "git_commit_agent"
    description = "根据代码变更自动生成并执行Git提交"
    parameters = {
        "type": "object",
        "properties": {
            "lang": {
                "type": "string",
                "description": "提交信息的语言",
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
            
            prompt = f'''根据以下规则生成提交信息：
            提交信息应使用{args.get('lang', '中文')}书写
# 必需结构
必须使用以下格式：
<COMMIT_MESSAGE>
<类型>(<范围>): <主题>
使用祈使语气描述变更内容
</COMMIT_MESSAGE>
# 格式规则
1. 类型: fix, feat, docs, style, refactor, test, chore
2. 范围表示模块 (例如: auth, database)
3. 主题行 <= 72个字符，不以句号结尾
4. 正文使用现在时态解释每个变更的内容和原因
5. 不要遗漏任何变更
# 分析材料
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