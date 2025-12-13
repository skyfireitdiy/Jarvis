# -*- coding: utf-8 -*-
"""CodeAgent 工具函数模块。

提供项目概况等工具函数。
"""

import subprocess
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

from jarvis.jarvis_utils.git_utils import get_recent_commits_with_files
from jarvis.jarvis_utils.utils import get_loc_stats


def get_git_tracked_files_info(
    project_root: str, max_files: int = 100
) -> Optional[str]:
    """获取git托管的文件列表或目录结构

    如果文件数量超过max_files，则返回目录结构（不含文件）

    参数:
        project_root: 项目根目录
        max_files: 文件数量阈值，超过此值则返回目录结构

    返回:
        str: 文件列表或目录结构的字符串表示，失败时返回None
    """
    try:
        # 获取所有git托管的文件
        result = subprocess.run(
            ["git", "ls-files"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            cwd=project_root,
        )

        if result.returncode != 0 or not result.stdout.strip():
            return None

        files = [
            line.strip() for line in result.stdout.strip().splitlines() if line.strip()
        ]
        file_count = len(files)

        if file_count == 0:
            return None

        # 如果文件数量超过阈值，返回目录结构
        if file_count > max_files:
            # 提取所有目录路径
            dirs = set()
            for file_path in files:
                # 获取文件所在的所有父目录
                parts = file_path.split("/")
                for i in range(1, len(parts)):
                    dir_path = "/".join(parts[:i])
                    if dir_path:
                        dirs.add(dir_path)

            # 构建树形目录结构
            dir_tree: Dict[str, Any] = {}
            for dir_path in sorted(dirs):
                parts = dir_path.split("/")
                current = dir_tree
                for part in parts:
                    if part not in current:
                        current[part] = {}
                    current = current[part]

            def format_tree(
                tree: dict, prefix: str = "", is_last: bool = True
            ) -> List[str]:
                """格式化目录树"""
                lines = []
                items = sorted(tree.items())
                for i, (name, subtree) in enumerate(items):
                    is_last_item = i == len(items) - 1
                    connector = "└── " if is_last_item else "├── "
                    lines.append(f"{prefix}{connector}{name}/")

                    extension = "    " if is_last_item else "│   "
                    if subtree:
                        lines.extend(
                            format_tree(subtree, prefix + extension, is_last_item)
                        )
                return lines

            tree_lines = format_tree(dir_tree)
            return f"Git托管目录结构（共{file_count}个文件）:\n" + "\n".join(tree_lines)
        else:
            # 文件数量不多，直接返回文件列表
            files_str = "\n".join(f"  - {file}" for file in sorted(files))
            return f"Git托管文件列表（共{file_count}个文件）:\n{files_str}"

    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    except Exception:
        # 其他异常，静默失败
        return None


def get_project_overview(project_root: str) -> str:
    """获取项目概况信息

    参数:
        project_root: 项目根目录

    返回:
        项目概况字符串
    """
    project_info = []

    # 获取代码统计
    try:
        loc_stats = get_loc_stats()
        if loc_stats:
            project_info.append(f"代码统计:\n{loc_stats}")
    except Exception:
        pass

    # 获取Git托管的文件信息
    try:
        git_files_info = get_git_tracked_files_info(project_root)
        if git_files_info:
            project_info.append(git_files_info)
    except Exception:
        pass

    # 获取最近提交信息
    try:
        commits_info = get_recent_commits_with_files()
        if commits_info:
            commits_str = "\n".join(
                f"提交 {i + 1}: {commit['hash'][:7]} - {commit['message']} ({len(commit['files'])}个文件)\n"
                + "\n".join(f"    - {file}" for file in commit["files"][:5])
                + ("\n    ..." if len(commit["files"]) > 5 else "")
                for i, commit in enumerate(commits_info[:5])
            )
            project_info.append(f"最近提交:\n{commits_str}")
    except Exception:
        pass

    if project_info:
        return "项目概况:\n" + "\n\n".join(project_info)
    return ""
