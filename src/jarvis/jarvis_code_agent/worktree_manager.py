"""Git Worktree 管理模块

该模块提供 WorktreeManager 类，用于管理 git worktree 的创建、合并和清理。
"""

import os
import random
import shutil
import string
import subprocess
from datetime import datetime
from typing import Optional

from jarvis.jarvis_git_utils.git_commiter import GitCommitTool
from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_utils.utils import decode_output
from jarvis.jarvis_utils.git_utils import (
    has_uncommitted_changes,
)


class WorktreeManager:
    """Git Worktree 管理器

    负责管理 git worktree 的创建、合并和清理操作。
    """

    def __init__(self, repo_root: str):
        """初始化 WorktreeManager

        参数:
            repo_root: git 仓库根目录
        """
        self.repo_root = repo_root
        self.worktree_path: Optional[str] = None
        self.worktree_branch: Optional[str] = None

    def _auto_commit_if_needed(self) -> None:
        """检测并自动提交未提交的更改

        在创建 worktree 前，确保主仓库处于干净状态。
        如果有未提交的更改，自动执行提交。
        """
        try:
            if has_uncommitted_changes():
                PrettyOutput.auto_print("⚠️  检测到主仓库有未提交的更改")
                PrettyOutput.auto_print("🔄 自动提交主仓库更改...")
                git_commiter = GitCommitTool()
                git_commiter.execute(
                    {
                        "root_dir": self.repo_root,
                    }
                )
                PrettyOutput.auto_print("✅ 已自动提交主仓库更改")
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️  自动提交过程中出错: {str(e)}")

    def _get_project_name(self) -> str:
        """获取项目名称

        尝试从 git remote URL 提取项目名，如果没有 remote 则使用目录名

        返回:
            str: 项目名称
        """
        try:
            # 尝试从 git remote 获取 URL
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True,
                check=True,
                text=True,
            )
            url = result.stdout.strip()
            # 从 URL 提取项目名：如 https://github.com/user/repo.git 提取 repo
            if url:
                # 移除 .git 后缀
                if url.endswith(".git"):
                    url = url[:-4]
                # 获取最后一部分
                project_name = os.path.basename(url)
                if project_name:
                    return project_name
        except (subprocess.CalledProcessError, Exception):
            pass

        # 降级策略：使用当前目录名
        return os.path.basename(self.repo_root)

    def _has_commits(self) -> bool:
        """检测仓库是否有至少一次提交记录

        返回:
            bool: 如果有提交返回 True，否则返回 False
        """
        try:
            # 使用 git rev-parse HEAD 检测是否有提交
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                check=False,
                cwd=self.repo_root,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _generate_branch_name(self) -> str:
        """生成 worktree 分支名

        返回:
            str: 格式为 jarvis-{project_name}-YYYYMMDD-HHMMSS-<4位随机字符>
        """
        project_name = self._get_project_name()
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        random_suffix = "".join(random.choices(string.ascii_lowercase, k=4))
        return f"jarvis-{project_name}-{timestamp}-{random_suffix}"

    def get_current_branch(self) -> str:
        """获取当前分支名

        返回:
            str: 当前分支名

        抛出:
            RuntimeError: 如果获取分支名失败
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                check=True,
            )
            branch = decode_output(result.stdout).strip()
            if not branch or branch == "HEAD":
                raise RuntimeError("当前不在任何分支上（处于 detached HEAD 状态）")
            return branch
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"获取当前分支失败: {decode_output(e.stderr)}")
        except Exception as e:
            raise RuntimeError(f"获取当前分支时出错: {str(e)}")

    def _link_jarvis_dir(self, worktree_path: str) -> None:
        """在worktree中设置分层.jarvis目录结构

        采用分层软链接策略：
        1. 创建独立的.jarvis目录（用于Git跟踪的配置文件）
        2. 为运行时数据目录创建软链接（共享主仓库数据）

        这样设计的原因：
        - .jarvis/rule和.jarvis/rules/需要独立，避免分支间修改冲突
        - .jarvis/memory/等运行时数据需要共享，避免重复和混乱

        参数:
            worktree_path: worktree 目录路径

        抛出:
            RuntimeError: 如果创建目录或软链接失败
        """
        original_jarvis_dir = os.path.join(self.repo_root, ".jarvis")
        worktree_jarvis_dir = os.path.join(worktree_path, ".jarvis")

        # 检查原仓库的 .jarvis 目录是否存在
        if not os.path.exists(original_jarvis_dir):
            PrettyOutput.auto_print("⚠️ 原仓库不存在 .jarvis 目录，跳过设置")
            return

        # 定义需要独立复制的Git跟踪文件/目录
        # 这些文件在每个worktree中独立，避免分支间修改冲突
        git_tracked_items = [
            "rule",  # .jarvis/rule
            "rules",  # .jarvis/rules/
        ]

        try:
            # 步骤1：处理已存在的.jarvis目录
            if os.path.islink(worktree_jarvis_dir):
                # 如果是软链接（旧配置），删除它
                PrettyOutput.auto_print("🔗 检测到旧的.jarvis软链接，准备重建...")
                os.unlink(worktree_jarvis_dir)
                need_create_dir = True
            elif os.path.exists(worktree_jarvis_dir):
                # 如果目录已存在（Git自动检出的rule和rules），不需要重建
                PrettyOutput.auto_print("✅ .jarvis目录已存在（Git自动检出）")
                need_create_dir = False
            else:
                # 目录不存在，需要创建
                need_create_dir = True

            # 步骤2：创建独立的.jarvis目录（如果需要）
            if need_create_dir:
                os.makedirs(worktree_jarvis_dir, exist_ok=True)
                PrettyOutput.auto_print(
                    f"📁 已创建独立.jarvis目录: {worktree_jarvis_dir}"
                )

                # 步骤3：复制Git跟踪的文件到独立目录
                for item in git_tracked_items:
                    src_path = os.path.join(original_jarvis_dir, item)
                    dst_path = os.path.join(worktree_jarvis_dir, item)

                    if os.path.exists(src_path):
                        if os.path.isdir(src_path):
                            # 复制目录
                            shutil.copytree(src_path, dst_path)
                            PrettyOutput.auto_print(f"📋 已复制Git目录: {item}")
                        else:
                            # 复制文件
                            shutil.copy2(src_path, dst_path)
                            PrettyOutput.auto_print(f"📄 已复制Git文件: {item}")
                    else:
                        PrettyOutput.auto_print(f"⚠️ Git跟踪项不存在: {item}")

            # 步骤4：为其他所有文件和目录创建软链接（除了rule和rules）
            # 遍历主仓库.jarvis下的所有项目
            for item in os.listdir(original_jarvis_dir):
                # 跳过Git跟踪项（它们应该已经存在或已复制）
                if item in git_tracked_items:
                    continue

                src_path = os.path.join(original_jarvis_dir, item)
                dst_path = os.path.join(worktree_jarvis_dir, item)

                # 如果软链接已存在，跳过
                if os.path.exists(dst_path) or os.path.islink(dst_path):
                    continue

                # 创建软链接：worktree/.jarvis/item -> 原仓库/.jarvis/item
                try:
                    os.symlink(src_path, dst_path)
                    item_type = "目录" if os.path.isdir(src_path) else "文件"
                    PrettyOutput.auto_print(f"🔗 已创建{item_type}软链接: {item}")
                except Exception as e:
                    PrettyOutput.auto_print(f"⚠️ 创建软链接失败 {item}: {str(e)}")

            PrettyOutput.auto_print("✅ .jarvis目录设置完成（分层软链接模式）")

        except Exception as e:
            # 发生错误时尝试回滚：删除已创建的.jarvis目录
            PrettyOutput.auto_print(f"❌ 设置.jarvis目录时出错: {str(e)}")
            PrettyOutput.auto_print("🧹 尝试回滚...")
            try:
                if os.path.exists(worktree_jarvis_dir):
                    if os.path.islink(worktree_jarvis_dir):
                        os.unlink(worktree_jarvis_dir)
                    else:
                        shutil.rmtree(worktree_jarvis_dir)
                PrettyOutput.auto_print("✅ 回滚成功")
            except Exception as rollback_error:
                PrettyOutput.auto_print(f"⚠️ 回滚失败: {str(rollback_error)}")
                PrettyOutput.auto_print(f"💡 请手动清理: {worktree_jarvis_dir}")

            raise RuntimeError(f"设置.jarvis目录失败: {str(e)}")

    def create_worktree(self, branch_name: Optional[str] = None) -> str:
        """创建 git worktree 分支和目录

        参数:
            branch_name: 分支名，如果为 None 则自动生成

        返回:
            str: worktree 目录路径

        抛出:
            RuntimeError: 如果创建 worktree 失败
        """
        # 检测并自动提交未提交的更改（确保主仓库处于干净状态）
        self._auto_commit_if_needed()

        # 检测仓库是否有提交记录，如果没有则自动创建初始提交
        if not self._has_commits():
            PrettyOutput.auto_print("⚠️ 仓库没有任何提交记录，自动创建初始提交...")
            try:
                # 配置 git 用户信息（避免提交失败）
                subprocess.run(
                    ["git", "config", "user.email", "jarvis@localhost"],
                    capture_output=True,
                    check=True,
                    cwd=self.repo_root,
                )
                subprocess.run(
                    ["git", "config", "user.name", "Jarvis AI Agent"],
                    capture_output=True,
                    check=True,
                    cwd=self.repo_root,
                )
                # 创建空提交
                subprocess.run(
                    ["git", "commit", "--allow-empty", "-m", "Initial commit"],
                    capture_output=True,
                    check=True,
                    cwd=self.repo_root,
                )
                PrettyOutput.auto_print("✅ 已自动创建初始提交")
            except subprocess.CalledProcessError as e:
                error_msg = decode_output(e.stderr) if e.stderr else str(e)
                raise RuntimeError(
                    f"自动创建初始提交失败: {error_msg}\n"
                    f"请手动执行: git commit --allow-empty -m 'Initial commit'"
                )

        if branch_name is None:
            branch_name = self._generate_branch_name()

        self.worktree_branch = branch_name

        PrettyOutput.auto_print(f"🌿 创建 git worktree: {branch_name}")

        try:
            # 创建 worktree
            subprocess.run(
                ["git", "worktree", "add", "-b", branch_name, f"../{branch_name}"],
                capture_output=True,
                check=True,
                text=True,
            )

            # 获取 worktree 目录路径
            worktree_path = os.path.join(os.path.dirname(self.repo_root), branch_name)
            self.worktree_path = worktree_path

            PrettyOutput.auto_print(f"✅ Worktree 创建成功: {worktree_path}")

            # 将原仓库的 .jarvis 目录软链接到 worktree 中
            self._link_jarvis_dir(worktree_path)

            return worktree_path

        except subprocess.CalledProcessError as e:
            error_msg = decode_output(e.stderr) if e.stderr else str(e)
            raise RuntimeError(f"创建 worktree 失败: {error_msg}")
        except Exception as e:
            raise RuntimeError(f"创建 worktree 时出错: {str(e)}")

    def merge_back(self, original_branch: str, non_interactive: bool = False) -> bool:
        """将 worktree 分支变基后合并回原分支

        使用 rebase 策略：先在 worktree 分支上执行 rebase 到原分支，
        然后通过 fast-forward 合并，保持线性历史。

        参数:
            original_branch: 原始分支名
            non_interactive: 是否为非交互模式

        返回:
            bool: 是否合并成功
        """
        if not self.worktree_branch:
            PrettyOutput.auto_print("⚠️ 没有活动的 worktree 分支")
            return False

        PrettyOutput.auto_print(
            f"🔀 将 {self.worktree_branch} 变基并合并到 {original_branch}"
        )

        # 检查主仓库状态，确保是干净的
        try:
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                check=True,
                text=True,
                timeout=5,
                cwd=self.repo_root,
            )
            if status_result.stdout.strip():
                PrettyOutput.auto_print("⚠️ 主仓库有未提交的更改，无法安全合并")
                PrettyOutput.auto_print("💡 请先提交或暂存主仓库的更改")
                return False
        except subprocess.CalledProcessError:
            PrettyOutput.auto_print("⚠️ 无法检查主仓库状态")
            return False

        try:
            # 第一步：在 worktree 目录中执行 rebase
            PrettyOutput.auto_print(
                f"🔄 在 worktree 中将 {self.worktree_branch} 变基到 {original_branch}..."
            )
            result = subprocess.run(
                ["git", "rebase", original_branch],
                capture_output=True,
                check=False,
                cwd=self.worktree_path,
            )

            if result.returncode != 0:
                error_msg = (
                    decode_output(result.stderr) if result.stderr else "未知错误"
                )
                if "CONFLICT" in error_msg or "conflict" in error_msg.lower():
                    PrettyOutput.auto_print("⚠️ Rebase 产生冲突")
                    PrettyOutput.auto_print("📋 冲突处理选项:")
                    PrettyOutput.auto_print(
                        "   1. 手动解决冲突后，执行: git rebase --continue"
                    )
                    PrettyOutput.auto_print(
                        "   2. 放弃本次 rebase，执行: git rebase --abort"
                    )

                    # 自动中止 rebase 以清理状态（保持仓库一致性）
                    PrettyOutput.auto_print("🧹 自动中止 rebase 以恢复状态...")
                    abort_result = subprocess.run(
                        ["git", "rebase", "--abort"],
                        capture_output=True,
                        check=False,
                        timeout=5,
                        cwd=self.worktree_path,
                    )
                    if abort_result.returncode != 0:
                        abort_error = (
                            decode_output(abort_result.stderr)
                            if abort_result.stderr
                            else "未知错误"
                        )
                        PrettyOutput.auto_print(f"⚠️ 中止 rebase 失败: {abort_error}")
                        PrettyOutput.auto_print("💡 请手动执行: git rebase --abort")
                    return False
                else:
                    raise RuntimeError(f"Rebase 失败: {error_msg}")

            # 第二步：通过 fast-forward 合并
            PrettyOutput.auto_print(
                f"🔀 快速合并 {self.worktree_branch} (fast-forward)..."
            )
            result = subprocess.run(
                ["git", "merge", "--ff-only", self.worktree_branch],
                capture_output=True,
                check=False,
                cwd=self.repo_root,
            )

            if result.returncode != 0:
                error_msg = (
                    decode_output(result.stderr) if result.stderr else "未知错误"
                )
                raise RuntimeError(f"Fast-forward 合并失败: {error_msg}")

            PrettyOutput.auto_print("✅ Rebase 并合并成功")
            return True

        except subprocess.CalledProcessError as e:
            error_msg = decode_output(e.stderr) if e.stderr else str(e)
            PrettyOutput.auto_print(f"❌ 操作失败: {error_msg}")
            return False
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 操作时出错: {str(e)}")
            return False
        finally:
            # 清理 worktree 中的 rebase 状态（如果 rebase 失败）
            try:
                abort_result = subprocess.run(
                    ["git", "rebase", "--abort"],
                    capture_output=True,
                    check=False,
                    timeout=5,
                    cwd=self.worktree_path,
                )
                # 如果没有进行中的 rebase，返回码非0是正常的，忽略错误
            except Exception:
                pass

            # 检查 worktree 状态，提供恢复指导
            try:
                status_result = subprocess.run(
                    ["git", "status", "--short", "--branch"],
                    capture_output=True,
                    check=True,
                    text=True,
                    timeout=5,
                    cwd=self.worktree_path,
                )
                # 如果有未合并的文件或冲突，提示用户
                if (
                    "rebasing" in status_result.stdout
                    or "conflict" in status_result.stdout.lower()
                ):
                    PrettyOutput.auto_print("⚠️ Worktree 状态异常，可能存在未解决的冲突")
                    PrettyOutput.auto_print(f"💡 Worktree 路径: {self.worktree_path}")
                    PrettyOutput.auto_print("💡 请手动检查并处理:")
                    PrettyOutput.auto_print(f"   cd {self.worktree_path}")
                    PrettyOutput.auto_print("   git status")
            except Exception:
                pass

    def cleanup(self, worktree_path: Optional[str] = None) -> bool:
        """清理 worktree 目录

        参数:
            worktree_path: worktree 目录路径，如果为 None 则使用当前 worktree_path

        返回:
            bool: 是否清理成功
        """
        target_path = worktree_path or self.worktree_path
        if not target_path:
            PrettyOutput.auto_print("⚠️ 没有可清理的 worktree")
            return False

        PrettyOutput.auto_print(f"🧹 清理 worktree: {target_path}")

        try:
            # 获取分支名
            branch_name = os.path.basename(target_path)

            # 使用 git worktree remove 删除
            result = subprocess.run(
                ["git", "worktree", "remove", branch_name],
                capture_output=True,
                check=False,
            )

            if result.returncode != 0:
                error_msg = (
                    decode_output(result.stderr) if result.stderr else "未知错误"
                )
                PrettyOutput.auto_print(f"⚠️ 删除 worktree 失败: {error_msg}")
                return False

            PrettyOutput.auto_print("✅ Worktree 清理成功")

            # 删除对应的分支
            if self.worktree_branch:
                PrettyOutput.auto_print(f"🗑️  删除分支: {self.worktree_branch}")
                try:
                    delete_result = subprocess.run(
                        ["git", "branch", "-D", self.worktree_branch],
                        capture_output=True,
                        check=False,
                        cwd=self.repo_root,
                    )
                    if delete_result.returncode == 0:
                        PrettyOutput.auto_print(
                            f"✅ 分支 {self.worktree_branch} 已删除"
                        )
                    else:
                        error_msg = (
                            decode_output(delete_result.stderr)
                            if delete_result.stderr
                            else "未知错误"
                        )
                        PrettyOutput.auto_print(f"⚠️ 删除分支失败: {error_msg}")
                        PrettyOutput.auto_print(
                            f"💡 请手动删除分支: git branch -D {self.worktree_branch}"
                        )
                except Exception as e:
                    PrettyOutput.auto_print(f"⚠️ 删除分支时出错: {str(e)}")

            return True

        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 清理 worktree 时出错: {str(e)}")
            return False

    def get_worktree_info(self) -> dict:
        """获取当前 worktree 信息

        返回:
            dict: 包含 worktree_path 和 worktree_branch 的字典
        """
        return {
            "worktree_path": self.worktree_path,
            "worktree_branch": self.worktree_branch,
        }
