# -*- coding: utf-8 -*-
"""Jarvis代码代理模块。

该模块提供CodeAgent类，用于处理代码修改任务。
"""

import os
import sys
import subprocess
import argparse
from typing import Any, Dict, Optional, List, Tuple

# 忽略yaspin的类型检查
from jarvis.jarvis_utils.config import is_confirm_before_apply_patch
from yaspin import yaspin  # type: ignore

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_agent.builtin_input_handler import builtin_input_handler
from jarvis.jarvis_agent.file_input_handler import file_input_handler
from jarvis.jarvis_agent.shell_input_handler import shell_input_handler
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_git_utils.git_commiter import GitCommitTool
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_utils.git_utils import (
    find_git_root,
    get_commits_between,
    get_diff,
    get_latest_commit_hash,
    handle_commit_workflow,
    has_uncommitted_changes
)
from jarvis.jarvis_utils.input import get_multiline_input
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import init_env, user_confirm


class CodeAgent:
    """Jarvis系统的代码修改代理。

    负责处理代码分析、修改和git操作。
    """

    def __init__(self, platform: Optional[str] = None,
                model: Optional[str] = None,
                need_summary: bool = True):
        self.root_dir = os.getcwd()
        tool_registry = ToolRegistry()  # type: ignore
        tool_registry.use_tools([
            "execute_script",
            "search_web",
            "ask_user",
            "ask_codebase",
            "lsp_get_diagnostics",
            "read_code",
            "methodology",
            "chdir",
            "find_methodology",
            "edit_file",
            "rewrite_file"
        ])
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
4. **方案设计**：确定最小变更方案，保持代码结构
5. **实施修改**：遵循"先读后写"原则，保持代码风格一致性

## 工具使用
- 项目结构：优先使用fd命令查找文件
- 代码搜索：优先使用rg进行内容搜索
- 代码阅读：优先使用read_code工具
- 仅在命令行工具不足时使用专用工具

## 文件编辑工具使用规范
- 对于部分文件内容修改，使用edit_file工具
- 对于需要重写整个文件内容，使用rewrite_file工具
- 对于简单的修改，可以使用execute_script工具执行shell命令完成
</code_engineer_guide>
"""
        # Dynamically add ask_codebase based on task complexity if really needed
        # 处理platform参数
        platform_instance = (PlatformRegistry().create_platform(platform)  # type: ignore
            if platform
            else PlatformRegistry().get_normal_platform())  # type: ignore
        if model:
            platform_instance.set_model_name(model)  # type: ignore

        self.agent = Agent(
            system_prompt=code_system_prompt,
            name="CodeAgent",
            auto_complete=False,
            output_handler=[tool_registry],
            platform=platform_instance,
            input_handler=[
                shell_input_handler,
                file_input_handler,
                builtin_input_handler
            ],
            need_summary=need_summary
        )
        self.agent.set_addon_prompt(
            "请使用工具充分理解用户需求，然后根据需求一步步执行代码修改/开发，"
            "如果不清楚要修改那些文件，可以使用ask_codebase工具，"
            "以：xxxx功能在哪个文件中实现？类似句式提问。"
            "所有代码修改任务都应优先使用edit_file工具，而非edit_file工具。"
            "edit_file工具通过精确的搜索和替换实现代码编辑，"
            "搜索文本需在目标文件中有且仅有一次精确匹配，确保修改的准确性。"
        )

        self.agent.set_after_tool_call_cb(self.after_tool_call_cb)

    def get_root_dir(self) -> str:
        """获取项目根目录

        返回:
            str: 项目根目录路径
        """
        return self.root_dir

    def get_loc_stats(self) -> str:
        """使用loc命令获取当前目录的代码统计信息
        
        返回:
            str: loc命令输出的原始字符串，失败时返回空字符串
        """
        try:
            result = subprocess.run(
                ['loc'],
                cwd=self.root_dir,
                capture_output=True,
                text=True
            )
            return result.stdout if result.returncode == 0 else ""
        except FileNotFoundError:
            return ""

    def get_recent_commits_with_files(self) -> List[Dict[str, Any]]:
        """获取最近5次提交的commit信息和文件清单
        
        返回:
            List[Dict[str, Any]]: 包含commit信息和文件清单的字典列表，格式为:
                [
                    {
                        'hash': 提交hash,
                        'message': 提交信息,
                        'author': 作者,
                        'date': 提交日期,
                        'files': [修改的文件列表] (最多20个文件)
                    },
                    ...
                ]
                失败时返回空列表
        """
        try:
            # 获取最近5次提交的基本信息
            result = subprocess.run(
                ['git', 'log', '-5', '--pretty=format:%H%n%s%n%an%n%ad'],
                cwd=self.root_dir,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                return []

            # 解析提交信息
            commits = []
            lines = result.stdout.splitlines()
            for i in range(0, len(lines), 4):
                if i + 3 >= len(lines):
                    break
                commit = {
                    'hash': lines[i],
                    'message': lines[i+1],
                    'author': lines[i+2],
                    'date': lines[i+3],
                    'files': []
                }
                commits.append(commit)

            # 获取每个提交的文件修改清单
            for commit in commits:
                files_result = subprocess.run(
                    ['git', 'show', '--name-only', '--pretty=format:', commit['hash']],
                    cwd=self.root_dir,
                    capture_output=True,
                    text=True
                )
                if files_result.returncode == 0:
                    files = list(set(filter(None, files_result.stdout.splitlines())))
                    commit['files'] = files[:20]  # 限制最多20个文件

            return commits

        except subprocess.CalledProcessError:
            return []

    def _init_env(self) -> None:
        """初始化环境，包括：
        1. 查找git根目录
        2. 检查并处理未提交的修改
        """
        with yaspin(text="正在初始化环境...", color="cyan") as spinner:
            curr_dir = os.getcwd()
            git_dir = find_git_root(curr_dir)
            self.root_dir = git_dir
            if has_uncommitted_changes():
                with spinner.hidden():
                    git_commiter = GitCommitTool()
                    git_commiter.execute({})
            spinner.text = "环境初始化完成"
            spinner.ok("✅")

    def _handle_uncommitted_changes(self) -> None:
        """处理未提交的修改，包括：
        1. 提示用户确认是否提交
        2. 如果确认，则暂存并提交所有修改
        """
        if has_uncommitted_changes():
            PrettyOutput.print("检测到未提交的修改，是否要提交？", OutputType.WARNING)
            if user_confirm("是否要提交？", True):
                import subprocess
                try:
                    # 获取当前分支的提交总数
                    commit_count = subprocess.run(
                        ['git', 'rev-list', '--count', 'HEAD'],
                        capture_output=True,
                        text=True
                    )
                    if commit_count.returncode != 0:
                        return
                        
                    commit_count = int(commit_count.stdout.strip())
                    
                    # 暂存所有修改
                    subprocess.run(['git', 'add', '.'], check=True)
                    
                    # 提交变更
                    subprocess.run(
                        ['git', 'commit', '-m', f'CheckPoint #{commit_count + 1}'], 
                        check=True
                    )
                except subprocess.CalledProcessError as e:
                    PrettyOutput.print(f"提交失败: {str(e)}", OutputType.ERROR)

    def _show_commit_history(
        self,
        start_commit: Optional[str],
        end_commit: Optional[str]
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
            commit_messages = (
                "检测到以下提交记录:\n" +
                "\n".join(
                    f"- {commit_hash[:7]}: {message}"
                    for commit_hash, message in commits
                )
            )
            PrettyOutput.print(commit_messages, OutputType.INFO)
        return commits

    def _handle_commit_confirmation(
        self, 
        commits: List[Tuple[str, str]], 
        start_commit: Optional[str]
    ) -> None:
        """处理提交确认和可能的重置"""
        if commits and user_confirm("是否接受以上提交记录？", True):
            subprocess.run(
                ["git", "reset", "--mixed", str(start_commit)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True
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
            loc_stats = self.get_loc_stats()
            commits_info = self.get_recent_commits_with_files()
            
            project_info = []
            if loc_stats:
                project_info.append(f"代码统计:\n{loc_stats}")
            if commits_info:
                commits_str = "\n".join(
                    f"提交 {i+1}: {commit['hash'][:7]} - {commit['message']} ({len(commit['files'])}个文件)"
                    for i, commit in enumerate(commits_info)
                )
                project_info.append(f"最近提交:\n{commits_str}")
            
            enhanced_input = f"{user_input}\n\n项目概况:\n" + "\n\n".join(project_info) if project_info else user_input

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
            commited = handle_commit_workflow()
            if commited:
                # 获取提交信息
                end_hash = get_latest_commit_hash()
                commits = get_commits_between(start_hash, end_hash)

                # 添加提交信息到final_ret
                if commits:
                    final_ret += "✅ 补丁已应用\n"
                    final_ret += "# 提交信息:\n"
                    for commit_hash, commit_message in commits:
                        final_ret += f"- {commit_hash[:7]}: {commit_message}\n"

                    final_ret += f"# 应用补丁:\n```diff\n{diff}\n```"

                    # 修改后的提示逻辑
                    addon_prompt = f"如果用户的需求未完成，请继续生成补丁，如果已经完成，请终止，不要输出新的PATCH，不要实现任何超出用户需求外的内容\n"
                    addon_prompt += "如果有任何信息不明确，调用工具获取信息\n"
                    addon_prompt += "每次响应必须且只能包含一个操作\n"

                    agent.set_addon_prompt(addon_prompt)

                else:
                    final_ret += "✅ 补丁已应用（没有新的提交）"
            else:
                final_ret += "❌ 补丁应用被拒绝\n"
                final_ret += f"# 补丁预览:\n```diff\n{diff}\n```"
        else:
            return
        # 用户确认最终结果
        if commited:
            agent.prompt += final_ret
            return
        PrettyOutput.print(final_ret, OutputType.USER, lang="markdown")
        if not is_confirm_before_apply_patch() or user_confirm("是否使用此回复？", default=True):
            agent.prompt += final_ret
            return
        custom_reply = get_multiline_input("请输入自定义回复")
        if not custom_reply.strip():  # 如果自定义回复为空，返回空字符串
            agent.prompt += final_ret
        agent.set_addon_prompt(custom_reply)
        agent.prompt += final_ret


def main() -> None:
    """Jarvis主入口点。"""
    init_env()

    parser = argparse.ArgumentParser(description='Jarvis Code Agent')
    parser.add_argument('-p', '--platform', type=str,
                      help='Target platform name', default=None)
    parser.add_argument('-m', '--model', type=str,
                      help='Model name to use', default=None)
    parser.add_argument('-r', '--requirement', type=str,
                      help='Requirement to process', default=None)
    args = parser.parse_args()

    curr_dir = os.getcwd()
    git_dir = find_git_root(curr_dir)
    PrettyOutput.print(f"当前目录: {git_dir}", OutputType.INFO)

    try:
        if args.requirement:
            user_input = args.requirement
        else:
            user_input = get_multiline_input("请输入你的需求（输入空行退出）:")
        if not user_input:
            sys.exit(0)
        agent = CodeAgent(platform=args.platform,
                        model=args.model,
                        need_summary=False)
        agent.run(user_input)

    except RuntimeError as e:
        PrettyOutput.print(f"错误: {str(e)}", OutputType.ERROR)
        sys.exit(1)


if __name__ == "__main__":
    main()
