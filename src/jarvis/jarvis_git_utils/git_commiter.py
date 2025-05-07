import re
import shlex
import subprocess
from typing import Dict, Any, Optional
import tempfile
import yaml
from yaspin import yaspin
from jarvis.jarvis_platform.registry import PlatformRegistry
import sys
import argparse
import os

from jarvis.jarvis_utils.git_utils import find_git_root, has_uncommitted_changes
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import init_env, is_context_overflow
from jarvis.jarvis_utils.tag import ot, ct


class GitCommitTool:
    name = "git_commit_agent"
    description = "根据代码变更自动生成并执行Git提交"
    labels = ['git', 'version_control']
    parameters = {
        "type": "object",
        "properties": {
            "lang": {
                "type": "string",
                "description": "提交信息的语言",
                "default": "Chinese"
            },
            "root_dir": {
                "type": "string",
                "description": "Git仓库的根目录路径（可选）",
                "default": "."
            }
        },
        "required": []
    }
    def _extract_commit_message(self, message)->Optional[str]:
        """Raw extraction preserving all characters"""
        r = re.search(
            r"(?i)" + ot("COMMIT_MESSAGE") + r"\s*([\s\S]*?)\s*" + ct("COMMIT_MESSAGE"),
            message
        )
        if r:
            # 直接返回原始内容，仅去除外围空白
            return shlex.quote(r.group(1).strip())
        return None

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
            root_dir = args.get("root_dir", ".")

            # Store current directory
            original_dir = os.getcwd()

            try:
                # Change to root_dir
                os.chdir(root_dir)

                find_git_root()
                if not has_uncommitted_changes():
                    PrettyOutput.print("没有未提交的更改", OutputType.SUCCESS)
                    return {"success": True, "stdout": "No changes to commit", "stderr": ""}

                with yaspin(text="正在初始化提交流程...", color="cyan") as spinner:
                    # 添加文件
                    spinner.text = "正在添加文件到提交..."
                    subprocess.Popen(
                        ["git", "add", "."],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    ).wait()
                    spinner.write("✅ 添加文件到提交")

                    # 获取差异
                    spinner.text = "正在获取代码差异..."
                    # 获取文件列表
                    files_cmd = ["git", "diff", "--cached", "--name-only"]
                    process = subprocess.Popen(
                        files_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    files_output = process.communicate()[0].decode()
                    files = [f.strip() for f in files_output.split("\n") if f.strip()]
                    file_count = len(files)
                    
                    # 获取完整差异
                    process = subprocess.Popen(
                        ["git", "diff", "--cached", "--exit-code"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    diff = process.communicate()[0].decode()
                    spinner.write(f"✅ 获取差异 ({file_count} 个文件)")
                    try:
                        temp_diff_file_path = None
                        # 生成提交信息
                        spinner.text = "正在生成提交消息..."
                        
                        # 准备提示信息
                        base_prompt = f'''根据代码差异生成提交信息：
                        提交信息应使用{args.get('lang', '中文')}书写
        # 必需结构
        必须使用以下格式：
        {ot("COMMIT_MESSAGE")}
        <类型>(<范围>): <主题>
        
        [可选] 详细描述变更内容和原因
        {ct("COMMIT_MESSAGE")}
        # 格式规则
        1. 类型: fix(修复bug), feat(新功能), docs(文档), style(格式), refactor(重构), test(测试), chore(其他)
        2. 范围表示变更的模块或组件 (例如: auth, database, ui)
        3. 主题行不超过72个字符，不以句号结尾，使用祈使语气
        4. 如有详细描述，使用空行分隔主题和详细描述
        5. 详细描述部分应解释"是什么"和"为什么"，而非"如何"
        6. 仅输出提交信息，不要输出其他内容
        '''

                        # 获取模型并尝试上传文件
                        platform = PlatformRegistry().get_normal_platform()
                        upload_success = False
                        
                        # Check if content is too large
                        is_large_content = is_context_overflow(diff)
                        
                        if is_large_content and hasattr(platform, 'upload_files'):
                            spinner.text = "正在上传代码差异文件..."
                            try:
                                with spinner.hidden():
                                    # 创建临时文件并写入差异内容
                                    with tempfile.NamedTemporaryFile(mode='w', suffix='.diff', delete=False) as temp_diff_file: 
                                        temp_diff_file_path = temp_diff_file.name
                                        temp_diff_file.write(diff)
                                        temp_diff_file.flush()
                                        spinner.write(f"✅ 差异内容已写入临时文件")
                                    upload_success = platform.upload_files([temp_diff_file_path])
                                if upload_success:
                                    spinner.write("✅ 成功上传代码差异文件")
                                else:
                                    spinner.write("⚠️ 上传代码差异文件失败，将使用分块处理")
                            except Exception as e:
                                spinner.write(f"⚠️ 上传文件时出错: {str(e)}")
                                upload_success = False
                        
                        # 根据上传状态准备完整的提示
                        if upload_success:
                            # 使用上传的文件
                            prompt = base_prompt + f'''
        # 变更概述
        - 变更文件数量: {file_count} 个文件
        - 已上传包含完整代码差异的文件
        
        请详细分析已上传的代码差异文件，生成符合上述格式的提交信息。
        '''
                            commit_message = platform.chat_until_success(prompt)
                        else:
                            # 如果上传失败但内容较大，使用chat_big_content
                            if is_large_content and hasattr(platform, 'chat_big_content'):
                                spinner.text = "正在使用分块处理生成提交信息..."
                                commit_message = platform.chat_big_content(diff, base_prompt)
                            else:
                                # 直接在提示中包含差异内容
                                prompt = base_prompt + f'''
        # 分析材料
        {diff}
        '''
                                commit_message = platform.chat_until_success(prompt)
                        
                        # 尝试生成提交信息
                        spinner.text = "正在生成提交消息..."
                        while True:
                            # 只在特定情况下重新获取commit_message
                            if not upload_success and not is_large_content and not commit_message:
                                commit_message = platform.chat_until_success(prompt)
                            extracted_message = self._extract_commit_message(commit_message)
                            # 如果成功提取，就跳出循环
                            if extracted_message:
                                commit_message = extracted_message
                                break
                            prompt = f"""格式错误，请按照以下格式重新生成提交信息：
                            {ot("COMMIT_MESSAGE")}
        <类型>(<范围>): <主题>
        
        [可选] 详细描述变更内容和原因
        {ct("COMMIT_MESSAGE")}
                            """
                            commit_message = platform.chat_until_success(prompt)
                        spinner.write("✅ 生成提交消息")

                        # 执行提交
                        spinner.text = "正在准备提交..."
                        with tempfile.NamedTemporaryFile(mode='w', delete=True) as tmp_file:
                            tmp_file.write(commit_message)
                            tmp_file.flush()
                            spinner.text = "正在执行提交..."
                            commit_cmd = ["git", "commit", "-F", tmp_file.name]
                            subprocess.Popen(
                                commit_cmd,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL
                            ).wait()
                            spinner.write("✅ 提交")

                        commit_hash = self._get_last_commit_hash()
                        spinner.text = "完成提交"
                        spinner.ok("✅")
                    finally:
                        # 清理临时差异文件
                        if temp_diff_file_path is not None and os.path.exists(temp_diff_file_path):
                            try:
                                os.unlink(temp_diff_file_path)
                            except Exception as e:
                                spinner.write(f"⚠️ 无法删除临时文件: {str(e)}")

                PrettyOutput.print(f"提交哈希: {commit_hash}\n提交消息: {commit_message}", OutputType.SUCCESS)

                return {
                    "success": True,
                    "stdout": yaml.safe_dump({
                        "commit_hash": commit_hash,
                        "commit_message": commit_message
                    }),
                    "stderr": ""
                }
            finally:
                # Always restore original directory
                os.chdir(original_dir)

        except Exception as e:
            PrettyOutput.print(f"提交失败: {str(e)}", OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Commit failed: {str(e)}"
            }

def main():
    init_env()
    parser = argparse.ArgumentParser(description='Git commit tool')
    parser.add_argument('--lang', type=str, default='Chinese', help='Language for commit messages')
    parser.add_argument('--root-dir', type=str, default='.', help='Root directory of the Git repository')
    args = parser.parse_args()
    tool = GitCommitTool()
    tool.execute({"lang": args.lang if hasattr(args, 'lang') else 'Chinese', "root_dir": args.root_dir})

if __name__ == "__main__":
    sys.exit(main())
