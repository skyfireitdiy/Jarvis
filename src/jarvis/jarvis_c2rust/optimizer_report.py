# -*- coding: utf-8 -*-
"""优化器报告管理模块。"""

import json
from dataclasses import asdict
from pathlib import Path

from jarvis.jarvis_c2rust.optimizer_options import OptimizeStats
from jarvis.jarvis_c2rust.optimizer_utils import write_file


def get_report_display_path(
    report_path: Path, project_root: Path, crate_dir: Path
) -> str:
    """
    获取报告文件的显示路径（优先使用相对路径）。

    Args:
        report_path: 报告文件的绝对路径
        project_root: 项目根目录
        crate_dir: crate 根目录

    Returns:
        显示路径字符串
    """
    try:
        return str(report_path.relative_to(project_root))
    except ValueError:
        try:
            return str(report_path.relative_to(crate_dir))
        except ValueError:
            try:
                return str(report_path.relative_to(Path.cwd()))
            except ValueError:
                return str(report_path)


def write_final_report(report_path: Path, stats: OptimizeStats) -> None:
    """
    写入最终优化报告。

    Args:
        report_path: 报告文件路径
        stats: 优化统计信息
    """
    try:
        write_file(
            report_path,
            json.dumps(asdict(stats), ensure_ascii=False, indent=2),
        )
    except Exception:
        pass
