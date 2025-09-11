# -*- coding: utf-8 -*-
import os
import re
import subprocess
import tempfile
from typing import Any, Dict, Optional

import typer
import yaml  # type: ignore

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.config import get_git_commit_prompt
from jarvis.jarvis_utils.git_utils import (
    confirm_add_new_files,
    find_git_root_and_cd,
    has_uncommitted_changes,
)
from jarvis.jarvis_utils.globals import get_agent, current_agent_name
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.tag import ct, ot
from jarvis.jarvis_utils.utils import init_env, is_context_overflow

app = typer.Typer(help="Git提交工具")


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

        subprocess.Popen(
            ["git", "add", "."], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
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

            self._stage_changes()

            # 获取差异

            # 获取文件列表
            files_cmd = ["git", "diff", "--cached", "--name-only"]
            process = subprocess.Popen(
                files_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            files_output = process.communicate()[0]
            files = [f.strip() for f in files_output.split("\n") if f.strip()]
            file_count = len(files)

            # 获取完整差异
            process = subprocess.Popen(
                ["git", "diff", "--cached", "--exit-code"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            diff = process.communicate()[0]

            try:
                temp_diff_file_path = None
                # 生成提交信息
                PrettyOutput.print("正在生成提交消息...", OutputType.INFO)

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

                # 优先从调用方传入的 agent 获取平台与模型
                agent_from_args = args.get("agent")

                # Get model_group from args
                model_group = args.get("model_group")

                # Get platform and model based on model_group (thinking mode removed)
                from jarvis.jarvis_utils.config import (
                    get_normal_platform_name,
                    get_normal_model_name,
                )

                platform_name = None
                model_name = None

                if (
                    agent_from_args
                    and hasattr(agent_from_args, "model")
                    and getattr(agent_from_args, "model", None)
                ):
                    try:
                        platform_name = agent_from_args.model.platform_name()
                        model_name = agent_from_args.model.name()
                        if not model_group and hasattr(
                            agent_from_args.model, "model_group"
                        ):
                            model_group = agent_from_args.model.model_group
                    except Exception:
                        # 安全回退到后续逻辑
                        platform_name = None
                        model_name = None

                # 如果未能从agent获取到，再根据 model_group 获取
                if not platform_name:
                    platform_name = get_normal_platform_name(model_group)
                if not model_name:
                    model_name = get_normal_model_name(model_group)

                # If no explicit parameters, try to get from existing global agent
                if not platform_name:
                    agent = get_agent(current_agent_name)
                    if (
                        agent
                        and hasattr(agent, "model")
                        and getattr(agent, "model", None)
                    ):
                        platform_name = agent.model.platform_name()
                        model_name = agent.model.name()
                        if not model_group and hasattr(agent.model, "model_group"):
                            model_group = agent.model.model_group

                # Create a new platform instance
                if platform_name:
                    platform = PlatformRegistry().create_platform(platform_name)
                    if platform and model_name:
                        platform.set_model_name(model_name)
                    if platform and model_group:
                        try:
                            platform.set_model_group(model_group)
                        except Exception:
                            # 兼容早期实现
                            platform.model_group = model_group  # type: ignore
                else:
                    platform = PlatformRegistry().get_normal_platform()

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
                is_large_content = is_context_overflow(diff, model_group)

                if is_large_content:
                    if not platform.support_upload_files():
                        PrettyOutput.print("差异文件太大，无法处理", OutputType.ERROR)
                        return {
                            "success": False,
                            "stdout": "",
                            "stderr": "错误：差异文件太大，无法处理",
                        }

                    # 创建临时文件并写入差异内容
                    with tempfile.NamedTemporaryFile(
                        mode="w", suffix=".diff", delete=False
                    ) as temp_diff_file:
                        temp_diff_file_path = temp_diff_file.name
                        temp_diff_file.write(diff)
                        temp_diff_file.flush()

                    upload_success = platform.upload_files([temp_diff_file_path])
                    if upload_success:
                        pass
                    else:
                        PrettyOutput.print("上传代码差异文件失败", OutputType.ERROR)
                        return {
                            "success": False,
                            "stdout": "",
                            "stderr": "错误：上传代码差异文件失败",
                        }
                # 根据上传状态准备完整的提示
                if is_large_content:
                    # 尝试生成提交信息
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
                        text=True,
                    )
                    stdout, stderr = process.communicate()

                    if process.returncode != 0:
                        # 如果提交失败，重置暂存区
                        subprocess.run(["git", "reset", "HEAD"], check=False)
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
                # 清理临时差异文件
                if temp_diff_file_path is not None and os.path.exists(
                    temp_diff_file_path
                ):
                    try:
                        os.unlink(temp_diff_file_path)
                    except Exception as e:
                        PrettyOutput.print(
                            f"无法删除临时文件: {str(e)}", OutputType.WARNING
                        )

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

    model_group: Optional[str] = typer.Option(
        None, "-g", "--llm-group", help="使用的模型组，覆盖配置文件中的设置"
    ),
):
    init_env("欢迎使用 Jarvis-GitCommitTool，您的Git提交助手已准备就绪！")
    tool = GitCommitTool()
    tool.execute(
        {
            "root_dir": root_dir,
            "prefix": prefix,
            "suffix": suffix,

            "model_group": model_group,
        }
    )


def main():
    """Application entry point"""
    app()


if __name__ == "__main__":
    main()
