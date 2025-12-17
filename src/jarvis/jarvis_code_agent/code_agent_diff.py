# -*- coding: utf-8 -*-
"""CodeAgent 代码变更预览和统计模块"""

import os
import subprocess
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

from jarvis.jarvis_utils.config import get_diff_large_file_threshold
from jarvis.jarvis_utils.config import get_diff_show_line_numbers
from jarvis.jarvis_utils.config import get_diff_visualization_mode
from jarvis.jarvis_utils.git_utils import get_latest_commit_hash


class DiffManager:
    """代码变更预览和统计管理器"""

    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        # 延迟导入，避免循环依赖
        self._visualizer = None

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

    def _get_visualizer(self) -> Optional[Any]:
        """获取可视化器实例（延迟初始化）"""
        if self._visualizer is None:
            try:
                from jarvis.jarvis_code_agent.diff_visualizer import DiffVisualizer

                self._visualizer = DiffVisualizer()  # type: ignore
            except ImportError:
                # 如果导入失败，返回 None
                self._visualizer = False  # type: ignore
        return self._visualizer if self._visualizer is not False else None

    def build_per_file_patch_preview(
        self, modified_files: List[str], use_enhanced_visualization: bool = True
    ) -> str:
        """构建按文件的补丁预览

        参数:
            modified_files: 修改的文件列表
            use_enhanced_visualization: 是否使用增强的可视化（默认 True）

        返回:
            str: 补丁预览的 markdown 文本（用于日志等）
        """
        status_map = self.build_name_status_map()
        lines: List[str] = []
        visualizer = self._get_visualizer() if use_enhanced_visualization else None
        visualization_mode = (
            get_diff_visualization_mode() if use_enhanced_visualization else "default"
        )
        show_line_numbers = get_diff_show_line_numbers()
        large_file_threshold = get_diff_large_file_threshold()

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
                # 使用可视化器显示统计
                if visualizer:
                    visualizer.visualize_statistics(f, 0, dels)
                continue

            # 变更过大：显示统计和紧凑预览
            if total_changes > large_file_threshold:
                if visualizer:
                    # 显示统计信息
                    visualizer.visualize_statistics(f, adds, dels, total_changes)
                    # 显示紧凑预览
                    file_diff = self.get_file_diff(f)
                    if file_diff.strip():
                        if visualization_mode == "compact":
                            visualizer.visualize_compact(file_diff, f, max_lines=100)
                        elif visualization_mode == "syntax":
                            visualizer.visualize_syntax_highlighted(file_diff, f)
                        else:
                            # unified 模式也显示，但限制行数
                            visualizer.visualize_compact(file_diff, f, max_lines=50)
                lines.append(f"- {f} 新增{adds}行/删除{dels}行（变更过大，预览已省略）")
                continue

            # 正常变更：展示该文件的diff
            file_diff = self.get_file_diff(f)
            if file_diff.strip():
                # 使用增强的可视化
                if visualizer:
                    if visualization_mode == "unified":
                        visualizer.visualize_unified_diff(
                            file_diff, f, show_line_numbers=show_line_numbers
                        )
                    elif visualization_mode == "syntax":
                        visualizer.visualize_syntax_highlighted(file_diff, f)
                    elif visualization_mode == "compact":
                        visualizer.visualize_compact(file_diff, f)
                    else:
                        # 默认使用 unified
                        visualizer.visualize_unified_diff(
                            file_diff, f, show_line_numbers=show_line_numbers
                        )

                # 同时保留 markdown 格式用于日志
                lines.append(f"文件: {f}\n```diff\n{file_diff}\n```")
            else:
                # 当无法获取到diff（例如重命名或特殊状态），避免空输出
                lines.append(f"- {f} 变更已记录（无可展示的文本差异）")
        return "\n".join(lines)
