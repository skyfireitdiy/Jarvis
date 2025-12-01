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
