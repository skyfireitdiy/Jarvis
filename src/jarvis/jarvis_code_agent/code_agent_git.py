"""CodeAgent Git 操作模块"""

import os
import subprocess

from jarvis.jarvis_utils.output import PrettyOutput

# -*- coding: utf-8 -*-
import sys
from typing import Any
from typing import List
from typing import Optional
from typing import Tuple

from jarvis.jarvis_git_utils.git_commiter import GitCommitTool
from jarvis.jarvis_utils.git_utils import confirm_add_new_files
from jarvis.jarvis_utils.git_utils import find_git_root_and_cd
from jarvis.jarvis_utils.git_utils import get_commits_between
from jarvis.jarvis_utils.git_utils import has_uncommitted_changes
from jarvis.jarvis_utils.globals import get_global_model_group
from jarvis.jarvis_utils.input import user_confirm
from jarvis.jarvis_utils.output import OutputType


class GitManager:
    """Git 操作管理器"""

    def __init__(self, root_dir: str):
        self.root_dir = root_dir

    def check_git_config(self) -> None:
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
                PrettyOutput.auto_print(f"❌ {message}")
                sys.exit(1)

        except FileNotFoundError:
            PrettyOutput.auto_print("❌ 未找到 git 命令，请先安装 Git")
            sys.exit(1)
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 检查 Git 配置时出错: {str(e)}")
            sys.exit(1)

    def find_git_root(self) -> str:
        """查找并切换到git根目录

        返回:
            str: git根目录路径
        """
        curr_dir = os.getcwd()
        git_dir = find_git_root_and_cd(curr_dir)
        self.root_dir = git_dir
        return git_dir

    def update_gitignore(self, git_dir: str) -> None:
        """检查并更新.gitignore文件，确保忽略.jarvis目录，并追加常用语言的忽略规则（若缺失）

        参数:
            git_dir: git根目录路径
        """
        gitignore_path = os.path.join(git_dir, ".gitignore")

        # 常用忽略规则（按语言/场景分组）
        # 注意：以 / 开头的路径表示只在根目录匹配，避免误忽略子目录中的源码
        sections = {
            "General": [
                ".jarvis",
                ".DS_Store",
                "Thumbs.db",
                "*.log",
                "*.tmp",
                "*.swp",
                "*.swo",
                ".idea/",
                ".vscode/",
            ],
            "Python": [
                "__pycache__/",  # 任何目录下的 __pycache__
                "*.py[cod]",  # 任何目录下的编译文件
                "*$py.class",
                ".Python",
                "env/",  # 只在根目录
                "venv/",  # 只在根目录
                ".venv/",  # 只在根目录
                "build/",  # 只在根目录
                "dist/",  # 只在根目录
                "develop-eggs/",
                "downloads/",
                "eggs/",
                ".eggs/",
                # 注意：不忽略 lib/ 和 lib64/，因为这些目录可能存放源码
                "parts/",
                "sdist/",
                "var/",
                "wheels/",
                "pip-wheel-metadata/",
                "share/python-wheels/",
                "*.egg-info/",
                ".installed.cfg",
                "*.egg",
                "MANIFEST",
                ".mypy_cache/",
                ".pytest_cache/",
                ".ruff_cache/",
                ".tox/",
                ".coverage",
                ".coverage.*",
                "htmlcov/",
                ".hypothesis/",
                ".ipynb_checkpoints",
                ".pyre/",
                ".pytype/",
            ],
            "Rust": [
                "target/",  # 只在根目录
            ],
            "Node": [
                "node_modules/",  # 只在根目录
                "npm-debug.log*",
                "yarn-debug.log*",
                "yarn-error.log*",
                "pnpm-debug.log*",
                "lerna-debug.log*",
                "dist/",  # 只在根目录
                "coverage/",
                ".turbo/",  # 只在根目录
                ".next/",  # 只在根目录
                ".nuxt/",  # 只在根目录
                "out/",  # 只在根目录
            ],
            "Go": [
                # 注意：不忽略 bin/，因为这个目录可能存放源码
                "vendor/",  # 只在根目录
                "coverage.out",
            ],
            "Java": [
                "target/",  # 只在根目录
                "*.class",  # 任何目录下的编译文件
                ".gradle/",  # 只在根目录
                "build/",  # 只在根目录
                "out/",  # 只在根目录
            ],
            "C/C++": [
                "build/",  # 只在根目录
                "cmake-build-*/",  # 只在根目录
                "*.o",  # 任何目录下的编译文件
                "*.a",
                "*.so",
                "*.obj",
                "*.dll",
                "*.dylib",
                "*.exe",
                "*.pdb",
            ],
            ".NET": [
                # 注意：不忽略 bin/，因为这个目录可能存放源码
                "obj/",  # 只在根目录
            ],
        }

        existing_content = ""
        if os.path.exists(gitignore_path):
            with open(gitignore_path, "r", encoding="utf-8", errors="replace") as f:
                existing_content = f.read()

        # 已存在的忽略项（去除注释与空行）
        existing_set = set(
            ln.strip()
            for ln in existing_content.splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        )

        # 计算缺失项并准备追加内容
        new_lines: List[str] = []
        for name, patterns in sections.items():
            missing = [p for p in patterns if p not in existing_set]
            if missing:
                new_lines.append(f"# {name}")
                new_lines.extend(missing)
                new_lines.append("")  # 分组空行

        if not os.path.exists(gitignore_path):
            # 新建 .gitignore（仅包含缺失项；此处即为全部常用规则）
            with open(gitignore_path, "w", encoding="utf-8", newline="\n") as f:
                content_to_write = "\n".join(new_lines).rstrip()
                if content_to_write:
                    f.write(content_to_write + "\n")
            PrettyOutput.auto_print("✅ 已创建 .gitignore 并添加常用忽略规则")
        else:
            if new_lines:
                # 追加缺失的规则
                with open(gitignore_path, "a", encoding="utf-8", newline="\n") as f:
                    # 若原文件不以换行结尾，先补一行
                    if existing_content and not existing_content.endswith("\n"):
                        f.write("\n")
                    f.write("\n".join(new_lines).rstrip() + "\n")
                PrettyOutput.auto_print("✅ 已更新 .gitignore，追加常用忽略规则")

    def handle_git_changes(self, prefix: str, suffix: str, agent: Any) -> None:
        """处理git仓库中的未提交修改"""
        if has_uncommitted_changes():
            git_commiter = GitCommitTool()
            git_commiter.execute(
                {
                    "prefix": prefix,
                    "suffix": suffix,
                    "agent": agent,
                    # 使用全局模型组（不再从 agent 继承）
                    "model_group": get_global_model_group(),
                }
            )

    def init_env(self, prefix: str, suffix: str, agent: Any) -> None:
        """初始化环境，组合以下功能：
        1. 查找git根目录
        2. 检查并更新.gitignore文件
        3. 处理未提交的修改
        4. 配置git对换行符变化不敏感
        """
        git_dir = self.find_git_root()
        self.update_gitignore(git_dir)
        self.handle_git_changes(prefix, suffix, agent)
        # 配置git对换行符变化不敏感
        self.configure_line_ending_settings()

    def configure_line_ending_settings(self) -> None:
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
                ["git", "config", "--get", key],
                capture_output=True,
                text=True,
                check=False,
            )
            current_value = result.stdout.strip()
            current_settings[key] = current_value
            if current_value != target_value:
                need_change = True

        if not need_change:
            return

        PrettyOutput.auto_print(
            "⚠️ 正在修改git换行符敏感设置，这会影响所有文件的换行符处理方式"
        )
        # 避免在循环中逐条打印，先拼接后统一打印
        lines = ["将进行以下设置："]
        for key, value in target_settings.items():
            current = current_settings.get(key, "未设置")
            lines.append(f"{key}: {current} -> {value}")
        joined_lines = "\n".join(lines)
        PrettyOutput.auto_print(f"ℹ️ {joined_lines}")

        # 直接执行设置，不需要用户确认
        for key, value in target_settings.items():
            subprocess.run(["git", "config", key, value], check=True)

        # 对于Windows系统，提示用户可以创建.gitattributes文件
        if sys.platform.startswith("win"):
            self.handle_windows_line_endings()

        PrettyOutput.auto_print("✅ git换行符敏感设置已更新")

    def handle_windows_line_endings(self) -> None:
        """在Windows系统上处理换行符问题，提供建议而非强制修改"""
        gitattributes_path = os.path.join(self.root_dir, ".gitattributes")

        # 检查是否已存在.gitattributes文件
        if os.path.exists(gitattributes_path):
            with open(gitattributes_path, "r", encoding="utf-8") as f:
                content = f.read()
            # 如果已经有换行符相关配置，就不再提示
            if any(keyword in content for keyword in ["text=", "eol=", "binary"]):
                return

        PrettyOutput.auto_print(
            "ℹ️ 提示：在Windows系统上，建议配置 .gitattributes 文件来避免换行符问题。"
        )
        PrettyOutput.auto_print(
            "ℹ️ 这可以防止仅因换行符不同而导致整个文件被标记为修改。"
        )

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
                PrettyOutput.auto_print("✅ 已创建最小化的 .gitattributes 文件")
            else:
                PrettyOutput.auto_print("ℹ️ 将以下内容追加到现有 .gitattributes 文件：")
                PrettyOutput.print(
                    minimal_content, OutputType.CODE, lang="text"
                )  # 保留语法高亮
                if user_confirm("是否追加到现有文件？", True):
                    with open(
                        gitattributes_path, "a", encoding="utf-8", newline="\n"
                    ) as f:
                        f.write("\n" + minimal_content)
                    PrettyOutput.auto_print("✅ 已更新 .gitattributes 文件")
        else:
            PrettyOutput.auto_print(
                "ℹ️ 跳过 .gitattributes 文件创建。如遇换行符问题，可手动创建此文件。"
            )

    def record_code_changes_stats(self, diff_text: str) -> None:
        """记录代码变更的统计信息。

        Args:
            diff_text: git diff的文本输出
        """
        import re

        from jarvis.jarvis_stats.stats import StatsManager

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

    def handle_uncommitted_changes(self) -> None:
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
                    self.record_code_changes_stats(diff_result.stdout)
            except subprocess.CalledProcessError:
                pass

            PrettyOutput.auto_print("⚠️ 检测到未提交的修改，是否要提交？")
            if not user_confirm("是否要提交？", True):
                return

            try:
                confirm_add_new_files()

                if not has_uncommitted_changes():
                    return

                # 获取当前分支的提交总数
                # 兼容空仓库或无 HEAD 的场景：失败时将提交计数视为 0，继续执行提交流程
                commit_count = 0
                try:
                    commit_result = subprocess.run(
                        ["git", "rev-list", "--count", "HEAD"],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        check=False,
                    )
                    if commit_result.returncode == 0:
                        out = commit_result.stdout.strip()
                        if out.isdigit():
                            commit_count = int(out)
                except Exception:
                    commit_count = 0

                # 暂存所有修改
                subprocess.run(["git", "add", "."], check=True)

                # 提交变更
                subprocess.run(
                    ["git", "commit", "-m", f"CheckPoint #{commit_count + 1}"],
                    check=True,
                )
            except subprocess.CalledProcessError as e:
                PrettyOutput.auto_print(f"❌ 提交失败: {str(e)}")

    def show_commit_history(
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
            PrettyOutput.auto_print(f"ℹ️ {commit_messages}")
        return commits

    def handle_commit_confirmation(
        self,
        commits: List[Tuple[str, str]],
        start_commit: Optional[str],
        prefix: str,
        suffix: str,
        agent: Any,
        post_process_func: Any,
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

            # 检测变更文件并格式化
            from jarvis.jarvis_utils.git_utils import get_diff_file_list

            modified_files = get_diff_file_list()
            if modified_files:
                post_process_func(modified_files)

            git_commiter = GitCommitTool()
            git_commiter.execute(
                {
                    "prefix": prefix,
                    "suffix": suffix,
                    "agent": agent,
                    # 使用全局模型组（不再从 agent 继承）
                    "model_group": get_global_model_group(),
                }
            )

            # 在用户接受commit后，根据配置决定是否保存记忆
            if getattr(agent, "force_save_memory", False):
                agent.memory_manager.prompt_memory_save()
        elif start_commit and commits:
            if user_confirm("是否要重置到初始提交？", True):
                os.system(f"git reset --hard {str(start_commit)}")  # 确保转换为字符串
                PrettyOutput.auto_print("ℹ️ 已重置到初始提交")
