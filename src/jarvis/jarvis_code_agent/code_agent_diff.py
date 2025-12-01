# -*- coding: utf-8 -*-
"""CodeAgent 代码变更预览和统计模块"""

import os
import subprocess
from typing import Dict, List, Tuple

from jarvis.jarvis_utils.git_utils import get_latest_commit_hash


class DiffManager:
    """代码变更预览和统计管理器"""

    def __init__(self, root_dir: str):
        self.root_dir = root_dir

    def build_name_status_map(self) -> Dict[str, str]:
        """构造按文件的状态映射与差异文本，删除文件不展示diff，仅提示删除"""
        status_map = {}
        try:
            head_exists = bool(get_latest_commit_hash())
            # 临时 -N 以包含未跟踪文件的差异检测
            subprocess.run(
                ["git", "add", "-N", "."],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            cmd = ["git", "diff", "--name-status"] + (["HEAD"] if head_exists else [])
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        finally:
            subprocess.run(
                ["git", "reset"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        if res.returncode == 0 and res.stdout:
            for line in res.stdout.splitlines():
                if not line.strip():
                    continue
                parts = line.split("\t")
                if not parts:
                    continue
                status = parts[0]
                if status.startswith("R") or status.startswith("C"):
                    # 重命名/复制：使用新路径作为键
                    if len(parts) >= 3:
                        old_path, new_path = parts[1], parts[2]
                        status_map[new_path] = status
                        # 也记录旧路径，便于匹配 name-only 的结果
                        status_map[old_path] = status
                    elif len(parts) >= 2:
                        status_map[parts[-1]] = status
                else:
                    if len(parts) >= 2:
                        status_map[parts[1]] = status
        return status_map

    def get_file_diff(self, file_path: str) -> str:
        """获取单文件的diff，包含新增文件内容；失败时返回空字符串"""
        head_exists = bool(get_latest_commit_hash())
        try:
            # 为了让未跟踪文件也能展示diff，临时 -N 该文件
            subprocess.run(
                ["git", "add", "-N", "--", file_path],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            cmd = (
                ["git", "diff"] + (["HEAD"] if head_exists else []) + ["--", file_path]
            )
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if res.returncode == 0:
                return res.stdout or ""
            return ""
        finally:
            subprocess.run(
                ["git", "reset", "--", file_path],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    def build_per_file_patch_preview(self, modified_files: List[str]) -> str:
        """构建按文件的补丁预览"""
        status_map = self.build_name_status_map()
        lines: List[str] = []

        def _get_file_numstat(file_path: str) -> Tuple[int, int]:
            """获取单文件的新增/删除行数，失败时返回(0,0)"""
            head_exists = bool(get_latest_commit_hash())
            try:
                # 让未跟踪文件也能统计到新增行数
                subprocess.run(
                    ["git", "add", "-N", "--", file_path],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                cmd = (
                    ["git", "diff", "--numstat"]
                    + (["HEAD"] if head_exists else [])
                    + ["--", file_path]
                )
                res = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )
                if res.returncode == 0 and res.stdout:
                    for line in res.stdout.splitlines():
                        parts = line.strip().split("\t")
                        if len(parts) >= 3:
                            add_s, del_s = parts[0], parts[1]

                            def to_int(x: str) -> int:
                                try:
                                    return int(x)
                                except Exception:
                                    # 二进制或无法解析时显示为0
                                    return 0

                            return to_int(add_s), to_int(del_s)
            finally:
                subprocess.run(
                    ["git", "reset", "--", file_path],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            return (0, 0)

        for f in modified_files:
            status = status_map.get(f, "")
            adds, dels = _get_file_numstat(f)
            total_changes = adds + dels

            # 删除文件：不展示diff，仅提示（附带删除行数信息如果可用）
            if (status.startswith("D")) or (not os.path.exists(f)):
                if dels > 0:
                    lines.append(f"- {f} 文件被删除（删除{dels}行）")
                else:
                    lines.append(f"- {f} 文件被删除")
                continue

            # 变更过大：仅提示新增/删除行数，避免输出超长diff
            if total_changes > 300:
                lines.append(f"- {f} 新增{adds}行/删除{dels}行（变更过大，预览已省略）")
                continue

            # 其它情况：展示该文件的diff
            file_diff = self.get_file_diff(f)
            if file_diff.strip():
                lines.append(f"文件: {f}\n```diff\n{file_diff}\n```")
            else:
                # 当无法获取到diff（例如重命名或特殊状态），避免空输出
                lines.append(f"- {f} 变更已记录（无可展示的文本差异）")
        return "\n".join(lines)
