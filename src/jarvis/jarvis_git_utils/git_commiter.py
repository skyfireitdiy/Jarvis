# -*- coding: utf-8 -*-
import argparse
import os
import re
import subprocess
import sys
import tempfile
from typing import Any, Dict, Optional

import yaml  # type: ignore

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.config import get_git_commit_prompt
from jarvis.jarvis_utils.git_utils import (
    confirm_add_new_files,
    find_git_root_and_cd,
    has_uncommitted_changes,
)
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.tag import ct, ot
from jarvis.jarvis_utils.utils import init_env, is_context_overflow


class GitCommitTool:
    name = "git_commit_agent"
    description = "根据代码变更自动生成并执行Git提交"
    labels = ["git", "version_control"]
    parameters = {
        "type": "object",
        "properties": {
            "root_dir": {
                "type": "string",
                "description": "Git仓库的根目录路径（可选）",
                "default": ".",
            },
            "prefix": {
                "type": "string",
                "description": "提交信息前缀（可选）",
                "default": "",
            },
            "suffix": {
                "type": "string",
                "description": "提交信息后缀（可选）",
                "default": "",
            },
        },
        "required": [],
    }

    def _extract_commit_message(self, message) -> Optional[str]:
        """Raw extraction preserving all characters"""
        r = re.search(
            r"(?i)" + ot("COMMIT_MESSAGE") + r"\s*([\s\S]*?)\s*" + ct("COMMIT_MESSAGE"),
            message,
        )
        if r:
            # 直接返回原始内容，仅去除外围空白
            return r.group(1).strip()
        return None

    def _get_last_commit_hash(self) -> str:
        process = subprocess.Popen(
            ["git", "log", "-1", "--pretty=%H"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, _ = process.communicate()
        return stdout.decode().strip()

    def _prepare_git_environment(self, root_dir: str) -> Optional[str]:
        """Prepare git environment by changing directory and checking for changes"""
        original_dir = os.getcwd()
        os.chdir(root_dir)
        find_git_root_and_cd()
        if not has_uncommitted_changes():
            PrettyOutput.print("没有未提交的更改", OutputType.SUCCESS)
            return None
        return original_dir

    def _stage_changes(self) -> None:
        """Stage all changes for commit"""
        print("📁 正在添加文件到提交...")
        subprocess.Popen(
            ["git", "add", "."], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ).wait()
        print("✅ 添加文件到提交")

    def execute(self, args: Dict) -> Dict[str, Any]:
        """Execute automatic commit process with support for multi-line messages and special characters"""
        try:
            original_dir = os.getcwd()
            root_dir = args.get("root_dir", ".")
            prefix = args.get("prefix", "")
            suffix = args.get("suffix", "")

            # Prepare git environment
            result = self._prepare_git_environment(root_dir)
            if result is None:
                return {"success": True, "stdout": "No changes to commit", "stderr": ""}
            original_dir = result

            confirm_add_new_files()

            if not has_uncommitted_changes():
                return {"success": True, "stdout": "No changes to commit", "stderr": ""}

            print("🚀 正在初始化提交流程...")
            self._stage_changes()

            # 获取差异
            print("📊 正在获取代码差异...")
            # 获取文件列表
            files_cmd = ["git", "diff", "--cached", "--name-only"]
            process = subprocess.Popen(
                files_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            files_output = process.communicate()[0].decode()
            files = [f.strip() for f in files_output.split("\n") if f.strip()]
            file_count = len(files)

            # 获取完整差异
            process = subprocess.Popen(
                ["git", "diff", "--cached", "--exit-code"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            diff = process.communicate()[0].decode(errors="ignore")
            print(f"✅ 获取差异 ({file_count} 个文件)")
            try:
                temp_diff_file_path = None
                # 生成提交信息
                print("✨ 正在生成提交消息...")

                # 准备提示信息
                custom_prompt = get_git_commit_prompt()
                base_prompt = (
                    custom_prompt
                    if custom_prompt
                    else f"""根据代码差异生成提交信息：
                提交信息应使用中文书写
# 格式模板
必须使用以下格式：

<类型>(<范围>): <主题>

[可选] 详细描述变更内容和原因

# 格式规则
1. 类型: fix(修复bug), feat(新功能), docs(文档), style(格式), refactor(重构), test(测试), chore(其他)
2. 范围表示变更的模块或组件 (例如: auth, database, ui)
3. 主题行不超过72个字符，不以句号结尾，使用祈使语气
4. 如有详细描述，使用空行分隔主题和详细描述
5. 详细描述部分应解释"是什么"和"为什么"，而非"如何"
6. 仅输出提交信息，不要输出其他内容
"""
                )
                base_prompt += f"""
# 输出格式
{ot("COMMIT_MESSAGE")}
commit信息
{ct("COMMIT_MESSAGE")}
                """

                # 获取模型并尝试上传文件
                platform = PlatformRegistry().get_normal_platform()
                upload_success = False

                # Check if content is too large
                is_large_content = is_context_overflow(diff)

                if is_large_content:
                    if not platform.support_upload_files():
                        print("❌ 差异文件太大，无法处理")
                        return {
                            "success": False,
                            "stdout": "",
                            "stderr": "错误：差异文件太大，无法处理",
                        }
                    print("📤 正在上传代码差异文件...")
                    # 创建临时文件并写入差异内容
                    with tempfile.NamedTemporaryFile(
                        mode="w", suffix=".diff", delete=False
                    ) as temp_diff_file:
                        temp_diff_file_path = temp_diff_file.name
                        temp_diff_file.write(diff)
                        temp_diff_file.flush()
                        print(f"✅ 差异内容已写入临时文件")
                    upload_success = platform.upload_files([temp_diff_file_path])
                    if upload_success:
                        print("✅ 成功上传代码差异文件")
                    else:
                        print("❌ 上传代码差异文件失败")
                        return {
                            "success": False,
                            "stdout": "",
                            "stderr": "错误：上传代码差异文件失败",
                        }
                # 根据上传状态准备完整的提示
                if is_large_content:
                    # 尝试生成提交信息
                    print("✨ 正在生成提交消息...")
                    # 使用上传的文件
                    prompt = (
                        base_prompt
                        + f"""
# 变更概述
- 变更文件数量: {file_count} 个文件
- 已上传包含完整代码差异的文件

请详细分析已上传的代码差异文件，生成符合上述格式的提交信息。
"""
                    )
                    commit_message = platform.chat_until_success(prompt)
                else:
                    prompt = (
                        base_prompt
                        + f"""
# 分析材料
{diff}
"""
                    )
                    commit_message = platform.chat_until_success(prompt)

                while True:
                    # 只在特定情况下重新获取commit_message
                    if (
                        not upload_success
                        and not is_large_content
                        and not commit_message
                    ):
                        commit_message = platform.chat_until_success(prompt)
                    extracted_message = self._extract_commit_message(commit_message)
                    # 如果成功提取，就跳出循环
                    if extracted_message:
                        commit_message = extracted_message
                        # 应用prefix和suffix
                        if prefix:
                            commit_message = f"{prefix} {commit_message}"
                        if suffix:
                            commit_message = f"{commit_message}\n{suffix}"
                        break
                    prompt = f"""格式错误，请按照以下格式重新生成提交信息：
                    {ot("COMMIT_MESSAGE")}
                    commit信息
                    {ct("COMMIT_MESSAGE")}
                    """
                    commit_message = platform.chat_until_success(prompt)
                print("✅ 生成提交消息")

                # 执行提交
                print("⚙️ 正在准备提交...")
                with tempfile.NamedTemporaryFile(mode="w", delete=True) as tmp_file:
                    tmp_file.write(commit_message)
                    tmp_file.flush()
                    print("💾 正在执行提交...")
                    commit_cmd = ["git", "commit", "-F", tmp_file.name]
                    subprocess.Popen(
                        commit_cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    ).wait()
                    print("✅ 提交")

                commit_hash = self._get_last_commit_hash()
                print("✅ 完成提交")
            finally:
                # 清理临时差异文件
                if temp_diff_file_path is not None and os.path.exists(
                    temp_diff_file_path
                ):
                    try:
                        os.unlink(temp_diff_file_path)
                    except Exception as e:
                        print(f"⚠️ 无法删除临时文件: {str(e)}")

            PrettyOutput.print(
                f"提交哈希: {commit_hash}\n提交消息: {commit_message}",
                OutputType.SUCCESS,
            )

            return {
                "success": True,
                "stdout": yaml.safe_dump(
                    {"commit_hash": commit_hash, "commit_message": commit_message},
                    allow_unicode=True,
                ),
                "stderr": "",
            }
        except Exception as e:
            PrettyOutput.print(f"提交失败: {str(e)}", OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Commit failed: {str(e)}",
            }
        finally:
            # Always restore original directory
            os.chdir(original_dir)


def main():
    init_env("欢迎使用 Jarvis-GitCommitTool，您的Git提交助手已准备就绪！")
    parser = argparse.ArgumentParser(description="Git commit tool")
    parser.add_argument(
        "--root-dir", type=str, default=".", help="Root directory of the Git repository"
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default="",
        help="Prefix to prepend to commit message (separated by space)",
    )
    parser.add_argument(
        "--suffix",
        type=str,
        default="",
        help="Suffix to append to commit message (separated by newline)",
    )
    args = parser.parse_args()
    tool = GitCommitTool()
    tool.execute(
        {
            "root_dir": args.root_dir,
            "prefix": args.prefix if hasattr(args, "prefix") else "",
            "suffix": args.suffix if hasattr(args, "suffix") else "",
        }
    )


if __name__ == "__main__":
    sys.exit(main())
