# -*- coding: utf-8 -*-
"""
C2Rust 独立命令行入口。

提供分组式 CLI，将扫描能力作为子命令 scan 暴露：
  - jarvis-c2rust scan --root <path> [--db ...] [--dot ...] [--only-dot] [--subgraphs-dir ...] [--only-subgraphs] [--png]

实现策略：
- 复用 scanner.cli 的核心逻辑，避免重复代码。
- 使用 Typer 分组式结构，便于后续扩展更多子命令（如 analyze/export 等）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from jarvis.jarvis_c2rust.scanner import run_scan as _run_scan

app = typer.Typer(help="C2Rust 命令行工具")

# 显式定义根回调，确保为命令组而非单函数入口
@app.callback()
def _root():
    """
    C2Rust 命令行工具
    """
    # 不做任何处理，仅作为命令组的占位，使 'scan' 作为子命令出现
    pass


@app.command("scan")
def scan(
    dot: Optional[Path] = typer.Option(
        None,
        "--dot",
        help="Write call dependency graph to DOT file after scanning (or with --only-dot)",
    ),
    only_dot: bool = typer.Option(
        False,
        "--only-dot",
        help="Do not rescan. Read existing DB and only generate DOT (requires --dot)",
    ),
    subgraphs_dir: Optional[Path] = typer.Option(
        None,
        "--subgraphs-dir",
        help="Directory to write per-root subgraph DOT files (one file per root function)",
    ),
    only_subgraphs: bool = typer.Option(
        False,
        "--only-subgraphs",
        help="Do not rescan. Only generate per-root subgraph DOT files (requires --subgraphs-dir)",
    ),
    png: bool = typer.Option(
        False,
        "--png",
        help="Also render PNG images for generated DOT files using Graphviz 'dot'",
    ),
) -> None:
    """
    进行 C/C++ 函数扫描并可选生成调用关系 DOT 图
    """
    _run_scan(
        dot=dot,
        only_dot=only_dot,
        subgraphs_dir=subgraphs_dir,
        only_subgraphs=only_subgraphs,
        png=png,
    )


def main() -> None:
    """主入口"""
    app()


if __name__ == "__main__":
    main()