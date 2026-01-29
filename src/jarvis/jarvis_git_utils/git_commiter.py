# -*- coding: utf-8 -*-
import os
import re
import subprocess
import tempfile
from typing import Any
from typing import Dict
from typing import Optional

import typer
import yaml
from rich.console import Console
from rich.panel import Panel

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.config import get_git_commit_prompt
from jarvis.jarvis_utils.git_utils import confirm_add_new_files
from jarvis.jarvis_utils.git_utils import find_git_root_and_cd
from jarvis.jarvis_utils.git_utils import has_uncommitted_changes
from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_utils.tag import ct
from jarvis.jarvis_utils.tag import ot
from jarvis.jarvis_utils.utils import decode_output
from jarvis.jarvis_utils.utils import init_env
from jarvis.jarvis_utils.utils import is_context_overflow
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.config import get_max_input_token_count

app = typer.Typer(help="Git提交工具")


class GitCommitTool:
    console = Console()
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

    def _truncate_diff_for_commit(
        self,
        git_diff: str,
        base_prompt: str,
        platform: Optional[Any] = None,
        token_ratio: float = 0.5,
    ) -> str:
        """截断 git diff 以适应 token 限制（用于提交信息生成）

        参数:
            git_diff: 原始的 git diff 内容
            base_prompt: 基础提示词内容
            llm_group: 模型组名称（可选）
            platform: 平台实例（可选），如果提供则使用剩余token数量判断
            token_ratio: token 使用比例（默认 0.5，即 50%，考虑 base_prompt 和响应空间）

        返回:
            str: 截断后的 git diff（如果超出限制则截断并添加提示和文件列表）
        """
        if not git_diff or not git_diff.strip():
            return git_diff

        # 计算 base_prompt 的 token 数量
        base_prompt_tokens = get_context_token_count(base_prompt)

        # 获取最大输入 token 数量
        try:
            if platform is not None:
                # 优先使用剩余 token 数量（更准确，考虑对话历史）
                try:
                    remaining_tokens = platform.get_remaining_token_count()
                    if remaining_tokens > 0:
                        # 预留 20% 给响应，使用剩余 token 的 50% 给 diff
                        max_diff_tokens = int(remaining_tokens * token_ratio)
                        # 确保 diff 不超过剩余 token 减去 base_prompt
                        max_diff_tokens = min(
                            max_diff_tokens,
                            remaining_tokens - base_prompt_tokens - 1000,
                        )
                        if max_diff_tokens <= 0:
                            # 如果剩余 token 不足，使用文件列表策略
                            return ""
                except Exception:
                    pass

            # 回退方案：使用输入窗口限制
            max_input_tokens = get_max_input_token_count()
            # 预留一部分给 base_prompt 和响应，使用指定比例作为 diff 的限制
            max_diff_tokens = int(max_input_tokens * token_ratio)
            # 确保 diff 不超过输入窗口减去 base_prompt
            max_diff_tokens = min(
                max_diff_tokens, max_input_tokens - base_prompt_tokens - 2000
            )
            if max_diff_tokens <= 0:
                # 如果输入窗口不足，使用文件列表策略
                return ""
        except Exception:
            # 如果获取失败，使用默认值（约 50000 tokens）
            max_input_tokens = 50000
            max_diff_tokens = int(max_input_tokens * token_ratio)
            max_diff_tokens = min(
                max_diff_tokens, max_input_tokens - base_prompt_tokens - 2000
            )
            if max_diff_tokens <= 0:
                return ""

        # 计算 diff 的 token 数量
        diff_token_count = get_context_token_count(git_diff)

        if diff_token_count <= max_diff_tokens:
            return git_diff

        # 如果 diff 内容太大，进行截断
        # 先提取修改的文件列表
        files = set()
        # 匹配 "diff --git a/path b/path" 格式
        pattern = r"^diff --git a/([^\s]+) b/([^\s]+)$"
        for line in git_diff.split("\n"):
            match = re.match(pattern, line)
            if match:
                file_a = match.group(1)
                file_b = match.group(2)
                files.add(file_b)
                if file_a != file_b:
                    files.add(file_a)
        modified_files = sorted(list(files))

        lines = git_diff.split("\n")
        truncated_lines = []
        current_tokens = 0

        for line in lines:
            line_tokens = get_context_token_count(line)
            if current_tokens + line_tokens > max_diff_tokens:
                # 添加截断提示
                truncated_lines.append("")
                truncated_lines.append(
                    "# ⚠️ diff内容过大，已截断显示（提交信息生成需要更多上下文）"
                )
                truncated_lines.append(
                    f"# 原始diff共 {len(lines)} 行，{diff_token_count} tokens"
                )
                truncated_lines.append(
                    f"# 显示前 {len(truncated_lines)} 行，约 {current_tokens} tokens"
                )
                truncated_lines.append(
                    f"# 限制: {max_diff_tokens} tokens (输入窗口的 {token_ratio * 100:.0f}%，已考虑 base_prompt)"
                )

                # 添加完整修改文件列表
                if modified_files:
                    truncated_lines.append("")
                    truncated_lines.append(
                        f"# 完整修改文件列表（共 {len(modified_files)} 个文件）："
                    )
                    for file_path in modified_files:
                        truncated_lines.append(f"#   - {file_path}")

                break

            truncated_lines.append(line)
            current_tokens += line_tokens

        return "\n".join(truncated_lines)

    def _get_last_commit_hash(self) -> str:
        process = subprocess.Popen(
            ["git", "log", "-1", "--pretty=%H"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, _ = process.communicate()
        return decode_output(stdout).strip()

    def _prepare_git_environment(self, root_dir: str) -> Optional[str]:
        """Prepare git environment by changing directory and checking for changes"""
        original_dir = os.getcwd()
        os.chdir(root_dir)
        find_git_root_and_cd()
        if not has_uncommitted_changes():
            PrettyOutput.auto_print("✅ 没有未提交的更改")
            return None
        return original_dir

    def _stage_changes(self) -> None:
        """Stage all changes for commit"""

        subprocess.Popen(
            ["git", "add", "-A"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ).wait()

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

            # 在执行git add .之前，记录当前暂存区的文件（可能有用户手动添加的被gitignore的文件）
            process = subprocess.Popen(
                ["git", "diff", "--cached", "--name-only"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
            )
            stdout_bytes, _ = process.communicate()
            staged_files_before_add = decode_output(stdout_bytes)
            manually_staged_files = [
                f.strip() for f in staged_files_before_add.split("\n") if f.strip()
            ]

            self._stage_changes()

            # 执行 git add . 后，重新添加之前手动暂存的可能被gitignore忽略的文件
            for file_path in manually_staged_files:
                if os.path.exists(file_path):
                    # 使用 -f 参数强制添加被 .gitignore 忽略的文件
                    subprocess.run(["git", "add", "-f", file_path], check=False)

            # 获取差异

            # 获取文件列表
            files_cmd = ["git", "diff", "--cached", "--name-only"]
            process = subprocess.Popen(
                files_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=False
            )
            stdout_bytes, _ = process.communicate()
            files_output = decode_output(stdout_bytes)
            files = [f.strip() for f in files_output.split("\n") if f.strip()]
            file_count = len(files)

            # 获取完整差异
            process = subprocess.Popen(
                ["git", "diff", "--cached", "--exit-code"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
            )
            diff_bytes, _ = process.communicate()
            diff = decode_output(diff_bytes)

            try:
                # Get platform and model based on llm_group (thinking mode removed)
                from jarvis.jarvis_utils.config import get_normal_model_name

                platform = PlatformRegistry().get_normal_platform()

                # 生成提交信息
                model_display_name = get_normal_model_name() or (
                    platform.name() if platform else "AI"
                )
                PrettyOutput.auto_print(
                    f"ℹ️ 正在使用{model_display_name}生成提交消息..."
                )

                # 准备提示信息
                custom_prompt = get_git_commit_prompt()
                base_prompt = (
                    custom_prompt
                    if custom_prompt
                    else """根据代码差异生成提交信息：
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

                # 跳过模型可用性校验：
                # 为避免某些平台/代理不支持 get_model_list 接口导致的噪音日志（如 404），
                # 这里默认不调用 platform.get_model_list() 进行模型可用性校验。
                # 如果未来需要恢复校验，可参考被移除的逻辑。
                # no-op

                # Ensure platform is not None
                if not platform:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "错误：无法创建平台实例",
                    }

                upload_success = False

                # Check if content is too large
                is_large_content = is_context_overflow(diff, platform)
                use_file_list = False

                # 对于大内容，直接使用文件列表生成提交信息（不再支持文件上传）
                if is_large_content:
                    PrettyOutput.auto_print(
                        "⚠️ 差异内容过大，将使用文件列表生成提交信息"
                    )
                    use_file_list = True

                # 即使 is_large_content 为 False，也需要检查 base_prompt + diff 的总长度
                # 对 diff 进行截断处理，确保不会超出上下文限制
                if not use_file_list:
                    truncated_diff = self._truncate_diff_for_commit(
                        diff, base_prompt, platform, token_ratio=0.5
                    )
                    if not truncated_diff or truncated_diff != diff:
                        if not truncated_diff:
                            # 如果截断后为空，降级到文件列表策略
                            PrettyOutput.auto_print(
                                "⚠️ 差异内容过大（考虑 base_prompt 后），将使用文件列表生成提交信息"
                            )
                            use_file_list = True
                        else:
                            # 如果被截断，使用截断后的 diff
                            diff = truncated_diff
                            PrettyOutput.auto_print("⚠️ 差异内容已截断以适应上下文限制")

                # 根据上传状态准备完整的提示
                if is_large_content and not use_file_list:
                    max_files_to_show = 20
                    if file_count <= max_files_to_show:
                        files_list = "\n".join(f"- {f}" for f in files)
                    else:
                        files_list = "\n".join(
                            f"- {f}" for f in files[:max_files_to_show]
                        )
                        files_list += (
                            f"\n- ...及其他 {file_count - max_files_to_show} 个文件"
                        )

                    prompt = (
                        base_prompt
                        + f"""
# 变更概述
- 变更文件数量: {file_count} 个文件
- 已上传包含完整代码差异的文件

# 变更文件列表
{files_list}

请详细分析已上传的代码差异文件，生成符合上述格式的提交信息。
"""
                    )
                    commit_message = platform.chat_until_success(prompt)
                elif use_file_list:
                    # 降级策略：使用文件列表生成提交信息
                    # 格式化文件列表，如果太长则截断
                    max_files_to_show = 20
                    if file_count <= max_files_to_show:
                        files_list = "\n".join(f"- {f}" for f in files)
                    else:
                        files_list = "\n".join(
                            f"- {f}" for f in files[:max_files_to_show]
                        )
                        files_list += (
                            f"\n- ...及其他 {file_count - max_files_to_show} 个文件"
                        )

                    prompt = (
                        base_prompt
                        + f"""
# 变更概述
- 变更文件数量: {file_count} 个文件

# 变更文件列表
{files_list}

请根据上述文件列表生成符合格式的提交信息。
"""
                    )
                    commit_message = platform.chat_until_success(prompt)
                else:
                    # 正常情况：直接使用 diff 内容
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

                # 执行提交

                # Windows 兼容性：使用 delete=False 避免权限错误
                tmp_file = tempfile.NamedTemporaryFile(mode="w", delete=False)
                tmp_file_path = tmp_file.name
                try:
                    tmp_file.write(commit_message)
                    tmp_file.close()  # Windows 需要先关闭文件才能被其他进程读取

                    commit_cmd = ["git", "commit", "-F", tmp_file_path]
                    process = subprocess.Popen(
                        commit_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=False,
                    )
                    stdout_bytes, stderr_bytes = process.communicate()
                    _, stderr = decode_output(stdout_bytes), decode_output(stderr_bytes)

                    if process.returncode != 0:
                        # 如果提交失败，重置暂存区
                        subprocess.run(["git", "reset", "HEAD"], check=False)

                        # 重置后，重新添加之前手动暂存的可能被gitignore的文件
                        for file_path in manually_staged_files:
                            if os.path.exists(file_path):
                                # 使用 -f 参数强制添加被 .gitignore 忽略的文件
                                subprocess.run(
                                    ["git", "add", "-f", file_path], check=False
                                )

                        error_msg = (
                            stderr.strip() if stderr else "Unknown git commit error"
                        )
                        raise Exception(f"Git commit failed: {error_msg}")

                finally:
                    # 手动删除临时文件
                    try:
                        os.unlink(tmp_file_path)
                    except Exception:
                        pass

                commit_hash = self._get_last_commit_hash()
            finally:
                pass

            self.console.print(
                Panel(
                    f"[bold green]✅ 提交成功[/bold green]\n\n"
                    f"[bold]提交哈希:[/bold] {commit_hash}\n"
                    f"[bold]提交消息:[/bold]\n{commit_message}",
                    title="Git Commit Result",
                    border_style="green",
                )
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
            self.console.print(
                Panel(
                    f"[bold red]❌ 提交失败[/bold red]\n\n{str(e)}",
                    title="Git Commit Error",
                    border_style="red",
                )
            )
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Commit failed: {str(e)}",
            }
        finally:
            # Always restore original directory
            os.chdir(original_dir)


@app.command()
def cli(
    root_dir: str = typer.Option(".", "--root-dir", help="Git仓库的根目录路径"),
    prefix: str = typer.Option(
        "",
        "--prefix",
        help="提交信息前缀（用空格分隔）",
    ),
    suffix: str = typer.Option(
        "",
        "--suffix",
        help="提交信息后缀（用换行分隔）",
    ),
    llm_group: Optional[str] = typer.Option(
        None, "-g", "--llm-group", help="使用的模型组，覆盖配置文件中的设置"
    ),
):
    init_env(llm_group=llm_group)
    tool = GitCommitTool()
    tool.execute(
        {
            "root_dir": root_dir,
            "prefix": prefix,
            "suffix": suffix,
        }
    )


def main():
    """Application entry point"""
    app()


if __name__ == "__main__":
    main()
