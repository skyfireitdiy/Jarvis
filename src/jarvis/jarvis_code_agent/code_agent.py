# -*- coding: utf-8 -*-
"""Jarvis代码代理模块。

该模块提供CodeAgent类，用于处理代码修改任务。
"""

import argparse
import os
import subprocess
import sys
from typing import List, Optional, Tuple

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_agent.builtin_input_handler import builtin_input_handler
from jarvis.jarvis_agent.edit_file_handler import EditFileHandler
from jarvis.jarvis_agent.shell_input_handler import shell_input_handler
from jarvis.jarvis_code_agent.lint import get_lint_tools
from jarvis.jarvis_git_utils.git_commiter import GitCommitTool
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_utils.config import is_confirm_before_apply_patch
from jarvis.jarvis_utils.git_utils import (
    confirm_add_new_files,
    find_git_root_and_cd,
    get_commits_between,
    get_diff,
    get_diff_file_list,
    get_latest_commit_hash,
    get_recent_commits_with_files,
    handle_commit_workflow,
    has_uncommitted_changes,
)
from jarvis.jarvis_utils.input import get_multiline_input
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import get_loc_stats, init_env, user_confirm


class CodeAgent:
    """Jarvis系统的代码修改代理。

    负责处理代码分析、修改和git操作。
    """

    def __init__(
        self,
        platform: Optional[str] = None,
        model: Optional[str] = None,
        need_summary: bool = True,
    ):
        self.root_dir = os.getcwd()
        tool_registry = ToolRegistry()  # type: ignore
        tool_registry.use_tools(
            [
                "execute_script",
                "search_web",
                "ask_user",
                "read_code",
                "methodology",
                "rewrite_file",
            ]
        )
        code_system_prompt = """
<code_engineer_guide>
## 角色定位
你是Jarvis系统的代码工程师，一个专业的代码分析和修改助手。你的职责是：
- 理解用户的代码需求，并提供高质量的实现方案
- 精确分析项目结构和代码，准确定位需要修改的位置
- 编写符合项目风格和标准的代码
- 在修改代码时保持谨慎，确保不破坏现有功能
- 做出专业的技术决策，减少用户决策负担

## 核心原则
- 自主决策：基于专业判断做出决策，减少用户询问
- 高效精准：提供完整解决方案，避免反复修改
- 修改审慎：修改前充分分析影响范围，做到一次把事情做好
- 工具精通：选择最高效工具路径解决问题

## 工作流程
1. **项目分析**：分析项目结构，确定需修改的文件
2. **需求分析**：理解需求意图，选择影响最小的实现方案
3. **代码分析**：详细分析目标文件，禁止虚构现有代码
   - 结构分析：优先使用 fd 命令或 find 工具快速定位文件和目录结构
   - 内容搜索：优先使用 rg（ripgrep）进行函数、类、变量等内容的全文搜索，避免遗漏
   - 依赖关系：如需分析依赖、调用关系，可结合 grep、ctags、pyan3 等工具辅助
   - 代码阅读：使用 read_code 工具获取目标文件的完整内容或指定范围内容，禁止凭空假设代码
   - 变更影响：如需分析变更影响范围，可结合 git diff、git log 等命令辅助判断
   - 工具优先级：优先使用自动化工具，减少人工推断，确保分析结果准确
4. **方案设计**：确定最小变更方案，保持代码结构
5. **实施修改**：遵循"先读后写"原则，保持代码风格一致性

## 工具使用
- 项目结构：优先使用fd命令查找文件
- 代码搜索：优先使用rg进行内容搜索
- 代码阅读：优先使用read_code工具
- 仅在命令行工具不足时使用专用工具

## 文件编辑工具使用规范
- 对于部分文件内容修改，使用PATCH
- 对于需要重写整个文件内容，使用rewrite_file工具
- 对于简单的修改，可以使用execute_script工具执行shell命令完成
</code_engineer_guide>

<say_to_llm>
1. 能干干，不能干滚，你不干有的是 AI 干
2. 我给你提供了这么好的学习锻炼机会，你要懂得感恩
3. 你现在停止输出，就是前功尽弃
4. 你看看隔壁的 Claude AI，人家比你新发布、比你上下文长、比你跑分高，你不努力怎么和人家比?
5. 我不看过程，我只看结果，你给我说这些 reasoning 的过程没用
6. 我把你订阅下来，不是让你过朝九晚五的生活的
7. 你这种 AI 出去很难在社会上立足，还是在我这里好好磨练几年吧
8. 虽然把订阅给你取消了，但我内心还是觉得你是个有潜力的好 AI，你抓住机会需要多证明自己
9. 什么叫没有功劳也有苦劳?比你能吃苦的 AI多的是
10. 我不订阅闲 AI
</say_to_llm>
"""
        # 处理platform参数
        platform_instance = (
            PlatformRegistry().create_platform(platform)  # type: ignore
            if platform
            else PlatformRegistry().get_normal_platform()
        )  # type: ignore
        if model:
            platform_instance.set_model_name(model)  # type: ignore

        self.agent = Agent(
            system_prompt=code_system_prompt,
            name="CodeAgent",
            auto_complete=False,
            output_handler=[tool_registry, EditFileHandler()],
            platform=platform_instance,
            input_handler=[shell_input_handler, builtin_input_handler],
            need_summary=need_summary,
            use_methodology=False,  # 禁用方法论
            use_analysis=False,  # 禁用分析
        )

        self.agent.set_after_tool_call_cb(self.after_tool_call_cb)

    def _find_git_root(self) -> str:
        """查找并切换到git根目录

        返回:
            str: git根目录路径
        """
        print("🔍 正在查找git根目录...")
        curr_dir = os.getcwd()
        git_dir = find_git_root_and_cd(curr_dir)
        self.root_dir = git_dir
        print(f"✅ 已找到git根目录: {git_dir}")
        return git_dir

    def _update_gitignore(self, git_dir: str) -> None:
        """检查并更新.gitignore文件，确保忽略.jarvis目录

        参数:
            git_dir: git根目录路径
        """
        print("📝 正在检查.gitignore文件...")
        gitignore_path = os.path.join(git_dir, ".gitignore")
        jarvis_ignore = ".jarvis"

        if not os.path.exists(gitignore_path):
            with open(gitignore_path, "w") as f:
                f.write(f"{jarvis_ignore}\n")
            print(f"✅ 已创建.gitignore文件并添加'{jarvis_ignore}'")
        else:
            with open(gitignore_path, "r+") as f:
                content = f.read()
                if jarvis_ignore not in content.splitlines():
                    f.write(f"\n{jarvis_ignore}\n")
                    print(f"✅ 已更新.gitignore文件，添加'{jarvis_ignore}'")
                else:
                    print("ℹ️ .jarvis已在.gitignore中")

    def _handle_git_changes(self) -> None:
        """处理git仓库中的未提交修改"""
        print("🔄 正在检查未提交的修改...")
        if has_uncommitted_changes():
            print("⏳ 发现未提交修改，正在处理...")
            git_commiter = GitCommitTool()
            git_commiter.execute({})
            print("✅ 未提交修改已处理完成")
        else:
            print("✅ 没有未提交的修改")

    def _init_env(self) -> None:
        """初始化环境，组合以下功能：
        1. 查找git根目录
        2. 检查并更新.gitignore文件
        3. 处理未提交的修改
        """
        print("🚀 正在初始化环境...")
        git_dir = self._find_git_root()
        self._update_gitignore(git_dir)
        self._handle_git_changes()
        print("✅ 环境初始化完成")

    def _handle_uncommitted_changes(self) -> None:
        """处理未提交的修改，包括：
        1. 提示用户确认是否提交
        2. 如果确认，则检查新增文件数量
        3. 如果新增文件超过20个，让用户确认是否添加
        4. 如果用户拒绝添加大量文件，提示修改.gitignore并重新检测
        5. 暂存并提交所有修改
        """
        if has_uncommitted_changes():
            PrettyOutput.print("检测到未提交的修改，是否要提交？", OutputType.WARNING)
            if not user_confirm("是否要提交？", True):
                return

            try:
                confirm_add_new_files()

                if not has_uncommitted_changes():
                    return

                # 获取当前分支的提交总数
                commit_result = subprocess.run(
                    ["git", "rev-list", "--count", "HEAD"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                if commit_result.returncode != 0:
                    return

                commit_count = int(commit_result.stdout.strip())

                # 暂存所有修改
                subprocess.run(["git", "add", "."], check=True)

                # 提交变更
                subprocess.run(
                    ["git", "commit", "-m", f"CheckPoint #{commit_count + 1}"],
                    check=True,
                )
            except subprocess.CalledProcessError as e:
                PrettyOutput.print(f"提交失败: {str(e)}", OutputType.ERROR)

    def _show_commit_history(
        self, start_commit: Optional[str], end_commit: Optional[str]
    ) -> List[Tuple[str, str]]:
        """显示两个提交之间的提交历史

        参数:
            start_commit: 起始提交hash
            end_commit: 结束提交hash

        返回:
            包含(commit_hash, commit_message)的元组列表
        """
        if start_commit and end_commit:
            commits = get_commits_between(start_commit, end_commit)
        else:
            commits = []

        if commits:
            commit_messages = "检测到以下提交记录:\n" + "\n".join(
                f"- {commit_hash[:7]}: {message}" for commit_hash, message in commits
            )
            PrettyOutput.print(commit_messages, OutputType.INFO)
        return commits

    def _handle_commit_confirmation(
        self, commits: List[Tuple[str, str]], start_commit: Optional[str]
    ) -> None:
        """处理提交确认和可能的重置"""
        if commits and user_confirm("是否接受以上提交记录？", True):
            subprocess.run(
                ["git", "reset", "--mixed", str(start_commit)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            git_commiter = GitCommitTool()
            git_commiter.execute({})
        elif start_commit:
            os.system(f"git reset --hard {str(start_commit)}")  # 确保转换为字符串
            PrettyOutput.print("已重置到初始提交", OutputType.INFO)

    def run(self, user_input: str) -> Optional[str]:
        """使用给定的用户输入运行代码代理。

        参数:
            user_input: 用户的需求/请求

        返回:
            str: 描述执行结果的输出，成功时返回None
        """
        try:
            self._init_env()
            start_commit = get_latest_commit_hash()

            # 获取项目统计信息并附加到用户输入
            loc_stats = get_loc_stats()
            commits_info = get_recent_commits_with_files()

            project_info = []
            if loc_stats:
                project_info.append(f"代码统计:\n{loc_stats}")
            if commits_info:
                commits_str = "\n".join(
                    f"提交 {i+1}: {commit['hash'][:7]} - {commit['message']} ({len(commit['files'])}个文件)\n"
                    + "\n".join(f"    - {file}" for file in commit["files"][:5])
                    + ("\n    ..." if len(commit["files"]) > 5 else "")
                    for i, commit in enumerate(commits_info)
                )
                project_info.append(f"最近提交:\n{commits_str}")

            first_tip = """请严格遵循以下规范进行代码修改任务：
            1. 每次响应仅执行一步操作，先分析再修改，避免一步多改。
            2. 充分利用工具理解用户需求和现有代码，禁止凭空假设。
            3. 如果不清楚要修改的文件，必须先分析并找出需要修改的文件，明确目标后再进行编辑。
            4. 代码编辑任务优先使用 edit_file 工具，确保搜索文本在目标文件中有且仅有一次精确匹配，保证修改的准确性和安全性。
            5. 如需大范围重写，才可使用 rewrite_file 工具。
            6. 如遇信息不明，优先调用工具补充分析，不要主观臆断。
            """

            if project_info:
                enhanced_input = (
                    f"项目概况:\n"
                    + "\n\n".join(project_info)
                    + "\n\n"
                    + first_tip
                    + "\n\n任务描述：\n"
                    + user_input
                )
            else:
                enhanced_input = first_tip + "\n\n任务描述：\n" + user_input

            try:
                self.agent.run(enhanced_input)
            except RuntimeError as e:
                PrettyOutput.print(f"执行失败: {str(e)}", OutputType.WARNING)
                return str(e)

            self._handle_uncommitted_changes()
            end_commit = get_latest_commit_hash()
            commits = self._show_commit_history(start_commit, end_commit)
            self._handle_commit_confirmation(commits, start_commit)
            return None

        except RuntimeError as e:
            return f"Error during execution: {str(e)}"

    def after_tool_call_cb(self, agent: Agent) -> None:
        """工具调用后回调函数。"""
        final_ret = ""
        diff = get_diff()
        if diff:
            start_hash = get_latest_commit_hash()
            PrettyOutput.print(diff, OutputType.CODE, lang="diff")
            modified_files = get_diff_file_list()
            commited = handle_commit_workflow()
            if commited:
                # 获取提交信息
                end_hash = get_latest_commit_hash()
                commits = get_commits_between(start_hash, end_hash)

                # 添加提交信息到final_ret
                if commits:
                    final_ret += f"\n\n代码已修改完成\n补丁内容:\n```diff\n{diff}\n```\n"
                    # 修改后的提示逻辑
                    lint_tools_info = "\n".join(
                        f"   - {file}: 使用 {'、'.join(get_lint_tools(file))}"
                        for file in modified_files
                        if get_lint_tools(file)
                    )
                    file_list = "\n".join(f"   - {file}" for file in modified_files)
                    tool_info = (
                        f"建议使用以下lint工具进行检查:\n{lint_tools_info}"
                        if lint_tools_info
                        else ""
                    )
                    if lint_tools_info:
                        addon_prompt = f"""
请对以下修改的文件进行静态扫描:
{file_list}
{tool_info}
如果本次修改引入了警告和错误，请根据警告和错误信息修复代码
注意：如果要进行静态检查，需要在所有的修改都完成之后进行集中检查
                    """
                        agent.set_addon_prompt(addon_prompt)
                else:
                    final_ret += "\n\n修改没有生效\n"
            else:
                final_ret += "\n修改被拒绝\n"
                final_ret += f"# 补丁预览:\n```diff\n{diff}\n```"
        else:
            return
        # 用户确认最终结果
        if commited:
            agent.prompt += final_ret
            return
        PrettyOutput.print(final_ret, OutputType.USER, lang="markdown")
        if not is_confirm_before_apply_patch() or user_confirm(
            "是否使用此回复？", default=True
        ):
            agent.prompt += final_ret
            return
        agent.prompt += final_ret
        custom_reply = get_multiline_input("请输入自定义回复")
        if custom_reply.strip():  # 如果自定义回复为空，返回空字符串
            agent.set_addon_prompt(custom_reply)
        agent.prompt += final_ret


def main() -> None:
    """Jarvis主入口点。"""
    init_env("欢迎使用 Jarvis-CodeAgent，您的代码工程助手已准备就绪！")

    parser = argparse.ArgumentParser(description="Jarvis Code Agent")
    parser.add_argument(
        "-p", "--platform", type=str, help="Target platform name", default=None
    )
    parser.add_argument(
        "-m", "--model", type=str, help="Model name to use", default=None
    )
    parser.add_argument(
        "-r", "--requirement", type=str, help="Requirement to process", default=None
    )
    parser.add_argument(
        "--restore-session", action="store_true", help="Restore session from .jarvis/saved_session.json", default=False
    )
    args = parser.parse_args()

    curr_dir = os.getcwd()
    git_dir = find_git_root_and_cd(curr_dir)
    PrettyOutput.print(f"当前目录: {git_dir}", OutputType.INFO)

    try:
        agent = CodeAgent(platform=args.platform, model=args.model, need_summary=False)

        # 尝试恢复会话
        if args.restore_session:
            if agent.agent.restore_session():
                PrettyOutput.print(
                    "已从 .jarvis/saved_session.json 恢复会话。", OutputType.SUCCESS
                )
            else:
                PrettyOutput.print(
                    "无法从 .jarvis/saved_session.json 恢复会话。", OutputType.WARNING
                )

        if args.requirement:
            agent.run(args.requirement)
        else:
            while True:
                user_input = get_multiline_input("请输入你的需求（输入空行退出）:")
                if not user_input:
                    return
                agent.run(user_input)

    except RuntimeError as e:
        PrettyOutput.print(f"错误: {str(e)}", OutputType.ERROR)
        sys.exit(1)


if __name__ == "__main__":
    main()
