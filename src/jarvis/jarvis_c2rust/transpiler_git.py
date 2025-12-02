# -*- coding: utf-8 -*-
"""
Git 操作模块
"""

import subprocess
from typing import Optional

from jarvis.jarvis_utils.git_utils import get_latest_commit_hash


class GitManager:
    """Git 操作管理器"""

    def __init__(self, crate_dir: str) -> None:
        self.crate_dir = crate_dir

    def get_crate_commit_hash(self) -> Optional[str]:
        """获取 crate 目录的当前 commit id"""
        try:
            # 由于 transpile() 开始时已切换到 crate 目录，此处无需再次切换
            commit_hash = get_latest_commit_hash()
            return commit_hash if commit_hash else None
        except Exception:
            return None

    def get_git_diff(self, base_commit: Optional[str] = None) -> str:
        """
        获取 git diff，显示从 base_commit 到当前工作区的变更

        参数:
            base_commit: 基准 commit hash，如果为 None 则使用 HEAD

        返回:
            str: git diff 内容，如果获取失败则返回空字符串
        """
        try:
            # 检查是否是 git 仓库
            check_git_result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                capture_output=True,
                text=True,
                check=False,
                cwd=self.crate_dir,
            )
            if check_git_result.returncode != 0:
                # 不是 git 仓库，无法获取 diff
                return ""

            if base_commit:
                # 先检查 base_commit 是否存在
                check_result = subprocess.run(
                    ["git", "rev-parse", "--verify", base_commit],
                    capture_output=True,
                    text=True,
                    check=False,
                    cwd=self.crate_dir,
                )
                if check_result.returncode != 0:
                    # base_commit 不存在，使用 HEAD 作为基准
                    base_commit = None

            # 检查是否有 HEAD
            head_check = subprocess.run(
                ["git", "rev-parse", "--verify", "HEAD"],
                capture_output=True,
                text=True,
                check=False,
                cwd=self.crate_dir,
            )
            has_head = head_check.returncode == 0

            # 临时暂存新增文件以便获取完整的 diff
            subprocess.run(
                ["git", "add", "-N", "."],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=self.crate_dir,
            )

            try:
                if base_commit:
                    # 获取从 base_commit 到当前工作区的差异
                    result = subprocess.run(
                        ["git", "diff", base_commit],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        check=False,
                        cwd=self.crate_dir,
                    )
                elif has_head:
                    # 获取从 HEAD 到当前工作区的差异
                    result = subprocess.run(
                        ["git", "diff", "HEAD"],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        check=False,
                        cwd=self.crate_dir,
                    )
                else:
                    # 空仓库，获取工作区差异
                    result = subprocess.run(
                        ["git", "diff"],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        check=False,
                        cwd=self.crate_dir,
                    )

                return result.stdout or "" if result.returncode == 0 else ""
            finally:
                # 重置暂存区
                subprocess.run(
                    ["git", "reset"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    cwd=self.crate_dir,
                )
        except Exception:
            return ""

    def reset_to_commit(self, commit_hash: str) -> bool:
        """回退 crate 目录到指定的 commit"""
        try:
            # 由于 transpile() 开始时已切换到 crate 目录，此处无需再次切换
            # 检查是否是 git 仓库
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                # 不是 git 仓库，无法回退
                return False

            # 执行硬重置
            result = subprocess.run(
                ["git", "reset", "--hard", commit_hash],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                # 清理未跟踪的文件
                subprocess.run(
                    ["git", "clean", "-fd"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                return True
            return False
        except Exception:
            return False
