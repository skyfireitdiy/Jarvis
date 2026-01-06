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

    def _generate_branch_name(self) -> str:
        """生成 worktree 分支名

        返回:
            str: 格式为 worktree-YYYYMMDD-HHMMSS-<4位随机字符>
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        random_suffix = ''.join(random.choices(string.ascii_lowercase, k=4))
        return f"worktree-{timestamp}-{random_suffix}"

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
        """将 worktree 分支合并回原分支

        参数:
            original_branch: 原始分支名
            non_interactive: 是否为非交互模式

        返回:
            bool: 是否合并成功
        """
        if not self.worktree_branch:
            PrettyOutput.auto_print("⚠️ 没有活动的 worktree 分支")
            return False

        PrettyOutput.auto_print(f"🔀 合并 {self.worktree_branch} 到 {original_branch}")

        try:
            # 切换回原分支（在原仓库目录中）
            PrettyOutput.auto_print(f"📍 切换回分支: {original_branch}")
            subprocess.run(
                ["git", "checkout", original_branch],
                capture_output=True,
                check=True,
                cwd=self.repo_root,
            )

            # 合并 worktree 分支
            PrettyOutput.auto_print(f"🔀 合并分支 {self.worktree_branch}...")
            result = subprocess.run(
                ["git", "merge", "--no-ff", self.worktree_branch, "-m", f"Merge worktree branch '{self.worktree_branch}'"],
                capture_output=True,
                check=False,
                text=True,
                cwd=self.repo_root,
            )

            if result.returncode != 0:
                error_msg = result.stderr if result.stderr else "未知错误"
                if "CONFLICT" in error_msg or "conflict" in error_msg.lower():
                    PrettyOutput.auto_print("⚠️ 合并冲突，请手动解决冲突")
                    return False
                else:
                    raise RuntimeError(f"合并失败: {error_msg}")

            PrettyOutput.auto_print("✅ 合并成功")
            return True

        except subprocess.CalledProcessError as e:
            error_msg = decode_output(e.stderr) if e.stderr else str(e)
            PrettyOutput.auto_print(f"❌ 合并失败: {error_msg}")
            return False
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 合并时出错: {str(e)}")
            return False

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
                error_msg = decode_output(result.stderr) if result.stderr else "未知错误"
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
