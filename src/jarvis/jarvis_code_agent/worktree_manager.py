"""Git Worktree 管理模块

该模块提供 WorktreeManager 类，用于管理 git worktree 的创建、合并和清理。
"""

import os
import random
import string
import subprocess
from datetime import datetime
from typing import Optional

from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_utils.utils import decode_output


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

    def create_worktree(self, branch_name: Optional[str] = None) -> str:
        """创建 git worktree 分支和目录

        参数:
            branch_name: 分支名，如果为 None 则自动生成

        返回:
            str: worktree 目录路径

        抛出:
            RuntimeError: 如果创建 worktree 失败
        """
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

        # 记录初始分支状态，用于异常恢复
        initial_branch = None
        try:
            # 获取当前分支（添加超时保护）
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                check=True,
                text=True,
                timeout=5,
                cwd=self.repo_root,
            )
            initial_branch = result.stdout.strip()
            if initial_branch == "HEAD":
                # detached HEAD 状态
                PrettyOutput.auto_print("⚠️ 当前处于 detached HEAD 状态")
        except subprocess.TimeoutExpired:
            PrettyOutput.auto_print("⚠️ 获取当前分支超时")
        except subprocess.CalledProcessError:
            PrettyOutput.auto_print("⚠️ 无法获取当前分支信息")

        # 标记是否需要恢复分支状态
        needs_restore = False

        try:
            # 第一步：切换到 worktree 分支并执行 rebase
            PrettyOutput.auto_print(f"📍 切换到 worktree 分支: {self.worktree_branch}")
            subprocess.run(
                ["git", "checkout", self.worktree_branch],
                capture_output=True,
                check=True,
                cwd=self.repo_root,
            )
            needs_restore = True  # 已切换分支，如果失败需要恢复

            # 执行 rebase
            PrettyOutput.auto_print(
                f"🔄 将 {self.worktree_branch} 变基到 {original_branch}..."
            )
            result = subprocess.run(
                ["git", "rebase", original_branch],
                capture_output=True,
                check=False,
                text=True,
                cwd=self.repo_root,
            )

            if result.returncode != 0:
                error_msg = result.stderr if result.stderr else "未知错误"
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
                        cwd=self.repo_root,
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

            # 第二步：切换回原分支
            PrettyOutput.auto_print(f"📍 切换回原分支: {original_branch}")
            subprocess.run(
                ["git", "checkout", original_branch],
                capture_output=True,
                check=True,
                cwd=self.repo_root,
            )
            needs_restore = False  # 已恢复到目标分支

            # 第三步：通过 fast-forward 合并
            PrettyOutput.auto_print(
                f"🔀 快速合并 {self.worktree_branch} (fast-forward)..."
            )
            result = subprocess.run(
                ["git", "merge", "--ff-only", self.worktree_branch],
                capture_output=True,
                check=False,
                text=True,
                cwd=self.repo_root,
            )

            if result.returncode != 0:
                error_msg = result.stderr if result.stderr else "未知错误"
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
            # 确保在异常情况下恢复到调用前的分支状态
            if needs_restore:
                # 优先恢复到 initial_branch（操作前的分支），其次尝试 original_branch
                target_branch = initial_branch if initial_branch else original_branch
                recovered = False  # 标记是否成功恢复

                if target_branch:
                    try:
                        # 尝试中止任何进行中的 rebase
                        abort_result = subprocess.run(
                            ["git", "rebase", "--abort"],
                            capture_output=True,
                            check=False,
                            timeout=5,
                            cwd=self.repo_root,
                        )
                        if abort_result.returncode != 0:
                            abort_error = (
                                decode_output(abort_result.stderr)
                                if abort_result.stderr
                                else "未知错误"
                            )
                            PrettyOutput.auto_print(
                                f"⚠️ 中止 rebase 时出现问题: {abort_error}"
                            )
                    except Exception:
                        pass

                    # 验证目标分支是否存在
                    try:
                        subprocess.run(
                            [
                                "git",
                                "rev-parse",
                                "--verify",
                                f"refs/heads/{target_branch}",
                            ],
                            capture_output=True,
                            check=True,
                            timeout=5,
                            cwd=self.repo_root,
                        )
                        # 分支存在，尝试切换
                        try:
                            PrettyOutput.auto_print(f"🔙 恢复到分支: {target_branch}")
                            subprocess.run(
                                ["git", "checkout", target_branch],
                                capture_output=True,
                                check=True,
                                timeout=10,
                                cwd=self.repo_root,
                            )
                            PrettyOutput.auto_print(f"✅ 已恢复到分支: {target_branch}")
                            recovered = True
                        except subprocess.CalledProcessError as e:
                            error_msg = decode_output(e.stderr) if e.stderr else str(e)
                            PrettyOutput.auto_print(f"⚠️ 恢复分支失败: {error_msg}")
                            raise
                    except subprocess.CalledProcessError:
                        # 分支不存在，尝试回退策略
                        PrettyOutput.auto_print(f"⚠️ 目标分支 '{target_branch}' 不存在")

                        # 尝试其他备选分支
                        backup_branches = [initial_branch, original_branch]
                        for backup in backup_branches:
                            if backup and backup != target_branch:
                                try:
                                    subprocess.run(
                                        [
                                            "git",
                                            "rev-parse",
                                            "--verify",
                                            f"refs/heads/{backup}",
                                        ],
                                        capture_output=True,
                                        check=True,
                                        timeout=5,
                                        cwd=self.repo_root,
                                    )
                                    PrettyOutput.auto_print(
                                        f"🔙 尝试恢复到备选分支: {backup}"
                                    )
                                    subprocess.run(
                                        ["git", "checkout", backup],
                                        capture_output=True,
                                        check=True,
                                        timeout=10,
                                        cwd=self.repo_root,
                                    )
                                    PrettyOutput.auto_print(
                                        f"✅ 已恢复到分支: {backup}"
                                    )
                                    recovered = True
                                    break
                                except Exception:
                                    continue

                        # 所有尝试都失败
                        if not recovered:
                            PrettyOutput.auto_print("⚠️ 无法自动恢复到任何分支")
                            PrettyOutput.auto_print("💡 当前 Git 状态:")
                            try:
                                status_result = subprocess.run(
                                    ["git", "status", "--short", "--branch"],
                                    capture_output=True,
                                    check=True,
                                    text=True,
                                    timeout=5,
                                    cwd=self.repo_root,
                                )
                                PrettyOutput.auto_print(status_result.stdout)
                            except Exception:
                                pass
                            PrettyOutput.auto_print("💡 请手动检查并恢复: git status")
                    except Exception as e:
                        PrettyOutput.auto_print(f"⚠️ 恢复分支时出错: {str(e)}")

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
