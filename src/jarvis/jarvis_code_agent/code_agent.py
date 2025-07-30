# -*- coding: utf-8 -*-
"""Jarvis代码代理模块。

该模块提供CodeAgent类，用于处理代码修改任务。
"""

import os
import subprocess
import sys
from typing import List, Optional, Tuple

import typer

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_agent.builtin_input_handler import builtin_input_handler
from jarvis.jarvis_agent.edit_file_handler import EditFileHandler
from jarvis.jarvis_agent.shell_input_handler import shell_input_handler
from jarvis.jarvis_code_agent.lint import get_lint_tools
from jarvis.jarvis_git_utils.git_commiter import GitCommitTool
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_utils.config import (
    is_confirm_before_apply_patch,
    is_enable_static_analysis,
)
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
from jarvis.jarvis_utils.input import get_multiline_input, user_confirm
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import get_loc_stats, init_env

app = typer.Typer(help="Jarvis 代码助手")


class CodeAgent:
    """Jarvis系统的代码修改代理。

    负责处理代码分析、修改和git操作。
    """

    def __init__(
        self,
        llm_type: str = "normal",
        model_group: Optional[str] = None,
        need_summary: bool = True,
    ):
        self.root_dir = os.getcwd()

        # 检测 git username 和 email 是否已设置
        self._check_git_config()
        tool_registry = ToolRegistry()  # type: ignore
        tool_registry.use_tools(
            [
                "execute_script",
                "search_web",
                "ask_user",
                "read_code",
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
   - 结构分析：优先使用文件搜索工具快速定位文件和目录结构
   - 内容搜索：优先使用全文搜索工具进行函数、类、变量等内容的搜索，避免遗漏
   - 依赖关系：如需分析依赖、调用关系，可结合代码分析工具辅助
   - 代码阅读：使用 read_code 工具获取目标文件的完整内容或指定范围内容，禁止凭空假设代码
   - 变更影响：如需分析变更影响范围，可结合版本控制工具辅助判断
   - 工具优先级：优先使用自动化工具，减少人工推断，确保分析结果准确
4. **方案设计**：确定最小变更方案，保持代码结构
5. **实施修改**：遵循"先读后写"原则，保持代码风格一致性

## 工具使用
- 项目结构：优先使用文件搜索命令查找文件
- 代码搜索：优先使用内容搜索工具
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
        self.agent = Agent(
            system_prompt=code_system_prompt,
            name="CodeAgent",
            auto_complete=False,
            output_handler=[tool_registry, EditFileHandler()],  # type: ignore
            llm_type=llm_type,
            model_group=model_group,
            input_handler=[shell_input_handler, builtin_input_handler],
            need_summary=need_summary,
            use_methodology=False,  # 禁用方法论
            use_analysis=False,  # 禁用分析
        )

        self.agent.set_after_tool_call_cb(self.after_tool_call_cb)

    def _check_git_config(self) -> None:
        """检查 git username 和 email 是否已设置，如果没有则提示并退出"""
        try:
            # 检查 git user.name
            result = subprocess.run(
                ["git", "config", "--get", "user.name"],
                capture_output=True,
                text=True,
                check=False,
            )
            username = result.stdout.strip()

            # 检查 git user.email
            result = subprocess.run(
                ["git", "config", "--get", "user.email"],
                capture_output=True,
                text=True,
                check=False,
            )
            email = result.stdout.strip()

            # 如果任一配置未设置，提示并退出
            if not username or not email:
                missing_configs = []
                if not username:
                    missing_configs.append(
                        '  git config --global user.name "Your Name"'
                    )
                if not email:
                    missing_configs.append(
                        '  git config --global user.email "your.email@example.com"'
                    )

                message = "❌ Git 配置不完整\n\n请运行以下命令配置 Git：\n" + "\n".join(
                    missing_configs
                )
                PrettyOutput.print(message, OutputType.WARNING)
                sys.exit(1)

        except FileNotFoundError:
            PrettyOutput.print("❌ 未找到 git 命令，请先安装 Git", OutputType.ERROR)
            sys.exit(1)
        except Exception as e:
            PrettyOutput.print(f"❌ 检查 Git 配置时出错: {str(e)}", OutputType.ERROR)
            sys.exit(1)

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
        4. 配置git对换行符变化不敏感
        """
        print("🚀 正在初始化环境...")
        git_dir = self._find_git_root()
        self._update_gitignore(git_dir)
        self._handle_git_changes()
        # 配置git对换行符变化不敏感
        self._configure_line_ending_settings()
        print("✅ 环境初始化完成")

    def _configure_line_ending_settings(self) -> None:
        """配置git对换行符变化不敏感，只在当前设置与目标设置不一致时修改"""
        target_settings = {
            "core.autocrlf": "false",
            "core.safecrlf": "false",
            "core.whitespace": "cr-at-eol",  # 忽略行尾的CR
        }

        # 获取当前设置并检查是否需要修改
        need_change = False
        current_settings = {}
        for key, target_value in target_settings.items():
            result = subprocess.run(
                ["git", "config", "--get", key], capture_output=True, text=True
            )
            current_value = result.stdout.strip()
            current_settings[key] = current_value
            if current_value != target_value:
                need_change = True

        if not need_change:
            print("✅ git换行符敏感设置已符合要求")
            return

        PrettyOutput.print(
            "⚠️ 即将修改git换行符敏感设置，这会影响所有文件的换行符处理方式",
            OutputType.WARNING,
        )
        print("将进行以下设置：")
        for key, value in target_settings.items():
            current = current_settings.get(key, "未设置")
            print(f"  {key}: {current} -> {value}")

        if user_confirm("是否继续修改git换行符敏感设置？", True):
            for key, value in target_settings.items():
                subprocess.run(["git", "config", key, value], check=True)

            # 对于Windows系统，提示用户可以创建.gitattributes文件
            if sys.platform.startswith("win"):
                self._handle_windows_line_endings()

            print("✅ git换行符敏感设置已更新")
        else:
            print("❌ 用户取消修改git换行符敏感设置")
            sys.exit(0)

    def _handle_windows_line_endings(self) -> None:
        """在Windows系统上处理换行符问题，提供建议而非强制修改"""
        gitattributes_path = os.path.join(self.root_dir, ".gitattributes")

        # 检查是否已存在.gitattributes文件
        if os.path.exists(gitattributes_path):
            with open(gitattributes_path, "r", encoding="utf-8") as f:
                content = f.read()
            # 如果已经有换行符相关配置，就不再提示
            if any(keyword in content for keyword in ["text=", "eol=", "binary"]):
                return

        print(
            "\n💡 提示：在Windows系统上，建议配置.gitattributes文件来避免换行符问题。"
        )
        print("这可以防止仅因换行符不同而导致整个文件被标记为修改。")

        if user_confirm("是否要创建一个最小化的.gitattributes文件？", False):
            # 最小化的内容，只影响特定类型的文件
            minimal_content = """# Jarvis建议的最小化换行符配置
# 默认所有文本文件使用LF，只有Windows特定文件使用CRLF

# 默认所有文本文件使用LF
* text=auto eol=lf

# Windows批处理文件需要CRLF
*.bat text eol=crlf
*.cmd text eol=crlf
*.ps1 text eol=crlf
"""

            if not os.path.exists(gitattributes_path):
                with open(gitattributes_path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(minimal_content)
                print("✅ 已创建最小化的.gitattributes文件")
            else:
                print("📝 将以下内容追加到现有.gitattributes文件：")
                print(minimal_content)
                if user_confirm("是否追加到现有文件？", True):
                    with open(
                        gitattributes_path, "a", encoding="utf-8", newline="\n"
                    ) as f:
                        f.write("\n" + minimal_content)
                    print("✅ 已更新.gitattributes文件")
        else:
            print(
                "ℹ️ 跳过.gitattributes文件创建。如果遇到换行符问题，可以手动创建此文件。"
            )

    def _record_code_changes_stats(self, diff_text: str) -> None:
        """记录代码变更的统计信息。

        Args:
            diff_text: git diff的文本输出
        """
        from jarvis.jarvis_stats.stats import StatsManager
        import re

        # 匹配插入行数
        insertions_match = re.search(r"(\d+)\s+insertions?\(\+\)", diff_text)
        if insertions_match:
            insertions = int(insertions_match.group(1))
            StatsManager.increment(
                "code_lines_inserted", amount=insertions, group="code_agent"
            )

        # 匹配删除行数
        deletions_match = re.search(r"(\d+)\s+deletions?\(\-\)", diff_text)
        if deletions_match:
            deletions = int(deletions_match.group(1))
            StatsManager.increment(
                "code_lines_deleted", amount=deletions, group="code_agent"
            )

    def _handle_uncommitted_changes(self) -> None:
        """处理未提交的修改，包括：
        1. 提示用户确认是否提交
        2. 如果确认，则检查新增文件数量
        3. 如果新增文件超过20个，让用户确认是否添加
        4. 如果用户拒绝添加大量文件，提示修改.gitignore并重新检测
        5. 暂存并提交所有修改
        """
        if has_uncommitted_changes():
            # 获取代码变更统计
            try:
                diff_result = subprocess.run(
                    ["git", "diff", "HEAD", "--shortstat"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=True,
                )
                if diff_result.returncode == 0 and diff_result.stdout:
                    self._record_code_changes_stats(diff_result.stdout)
            except subprocess.CalledProcessError:
                pass

            PrettyOutput.print("检测到未提交的修改，是否要提交？", OutputType.WARNING)
            if not user_confirm("是否要提交？", True):
                return

            # 用户确认修改，统计修改次数
            from jarvis.jarvis_stats.stats import StatsManager

            StatsManager.increment("code_modification_confirmed", group="code_agent")

            try:
                confirm_add_new_files()

                if not has_uncommitted_changes():
                    return

                # 获取当前分支的提交总数
                commit_result = subprocess.run(
                    ["git", "rev-list", "--count", "HEAD"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
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

                # 统计提交次数
                StatsManager.increment("code_commits_accepted", group="code_agent")
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
            # 统计生成的commit数量
            from jarvis.jarvis_stats.stats import StatsManager

            StatsManager.increment("commits_generated", group="code_agent")

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
            # 统计接受的commit数量
            from jarvis.jarvis_stats.stats import StatsManager

            StatsManager.increment("commits_accepted", group="code_agent")

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
                # 统计代码行数变化
                # 获取diff的统计信息
                try:
                    diff_result = subprocess.run(
                        ["git", "diff", "HEAD~1", "HEAD", "--shortstat"],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        check=True,
                    )
                    if diff_result.returncode == 0 and diff_result.stdout:
                        self._record_code_changes_stats(diff_result.stdout)
                except subprocess.CalledProcessError:
                    pass

                # 统计修改次数
                from jarvis.jarvis_stats.stats import StatsManager

                StatsManager.increment("code_modifications", group="code_agent")

                # 获取提交信息
                end_hash = get_latest_commit_hash()
                commits = get_commits_between(start_hash, end_hash)

                # 添加提交信息到final_ret
                if commits:
                    final_ret += (
                        f"\n\n代码已修改完成\n补丁内容:\n```diff\n{diff}\n```\n"
                    )
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
                    if lint_tools_info and is_enable_static_analysis():
                        addon_prompt = f"""
请对以下修改的文件进行静态扫描:
{file_list}
{tool_info}
如果本次修改引入了警告和错误，请根据警告和错误信息修复代码
注意：如果要进行静态检查，需要在所有的修改都完成之后进行集中检查，如果文件有多个检查工具，尽量一次全部调用，不要分多次调用
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
            agent.session.prompt += final_ret
            return
        PrettyOutput.print(final_ret, OutputType.USER, lang="markdown")
        if not is_confirm_before_apply_patch() or user_confirm(
            "是否使用此回复？", default=True
        ):
            agent.session.prompt += final_ret
            return
        agent.session.prompt += final_ret
        custom_reply = get_multiline_input("请输入自定义回复")
        if custom_reply.strip():  # 如果自定义回复为空，返回空字符串
            agent.set_addon_prompt(custom_reply)
        agent.session.prompt += final_ret


@app.command()
def cli(
    llm_type: str = typer.Option(
        "normal",
        "--llm_type",
        help="使用的LLM类型，可选值：'normal'（普通）或 'thinking'（思考模式）",
    ),
    model_group: Optional[str] = typer.Option(
        None, "--llm_group", help="使用的模型组，覆盖配置文件中的设置"
    ),
    requirement: Optional[str] = typer.Option(
        None, "-r", "--requirement", help="要处理的需求描述"
    ),
    restore_session: bool = typer.Option(
        False,
        "--restore-session",
        help="从 .jarvis/saved_session.json 恢复会话状态",
    ),
) -> None:
    """Jarvis主入口点。"""
    init_env("欢迎使用 Jarvis-CodeAgent，您的代码工程助手已准备就绪！")

    try:
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        curr_dir_path = os.getcwd()
        PrettyOutput.print(
            f"警告：当前目录 '{curr_dir_path}' 不是一个git仓库。", OutputType.WARNING
        )
        if user_confirm(
            f"是否要在 '{curr_dir_path}' 中初始化一个新的git仓库？", default=True
        ):
            try:
                subprocess.run(
                    ["git", "init"],
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                PrettyOutput.print("✅ 已成功初始化git仓库。", OutputType.SUCCESS)
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                PrettyOutput.print(f"❌ 初始化git仓库失败: {e}", OutputType.ERROR)
                sys.exit(1)
        else:
            PrettyOutput.print(
                "操作已取消。Jarvis需要在git仓库中运行。", OutputType.INFO
            )
            sys.exit(0)

    curr_dir = os.getcwd()
    git_dir = find_git_root_and_cd(curr_dir)
    PrettyOutput.print(f"当前目录: {git_dir}", OutputType.INFO)

    try:
        agent = CodeAgent(
            llm_type=llm_type,
            model_group=model_group,
            need_summary=False,
        )

        # 尝试恢复会话
        if restore_session:
            if agent.agent.restore_session():
                PrettyOutput.print(
                    "已从 .jarvis/saved_session.json 恢复会话。", OutputType.SUCCESS
                )
            else:
                PrettyOutput.print(
                    "无法从 .jarvis/saved_session.json 恢复会话。", OutputType.WARNING
                )

        if requirement:
            agent.run(requirement)
        else:
            while True:
                user_input = get_multiline_input("请输入你的需求（输入空行退出）:")
                if not user_input:
                    raise typer.Exit(code=0)
                agent.run(user_input)

    except typer.Exit:
        raise
    except RuntimeError as e:
        PrettyOutput.print(f"错误: {str(e)}", OutputType.ERROR)
        sys.exit(1)


def main() -> None:
    """Application entry point."""
    app()


if __name__ == "__main__":
    main()
