# -*- coding: utf-8 -*-
"""
C2Rust 独立命令行入口。

提供分组式 CLI，将扫描能力作为子命令 scan 暴露：
  - jarvis-c2rust scan --root <path> [--dot ...] [--only-dot] [--subgraphs-dir ...] [--only-subgraphs] [--png]

实现策略：
- 复用 scanner.cli 的核心逻辑，避免重复代码。
- 使用 Typer 分组式结构，便于后续扩展更多子命令（如 analyze/export 等）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from jarvis.jarvis_c2rust.scanner import run_scan as _run_scan
from jarvis.jarvis_utils.utils import init_env
from jarvis.jarvis_c2rust.llm_module_agent import (
    execute_llm_plan as _execute_llm_plan,
    entries_to_yaml as _entries_to_yaml,
)

app = typer.Typer(help="C2Rust 命令行工具")

# 显式定义根回调，确保为命令组而非单函数入口
@app.callback()
def _root():
    """
    C2Rust 命令行工具
    """
    # 不做任何处理，仅作为命令组的占位，使 'scan' 作为子命令出现
    init_env("欢迎使用 Jarvis C2Rust 工具")
    pass


@app.command("scan")
def scan(
    dot: Optional[Path] = typer.Option(
        None,
        "--dot",
        help="Write reference dependency graph to DOT file after scanning (or with --only-dot)",
    ),
    only_dot: bool = typer.Option(
        False,
        "--only-dot",
        help="Do not rescan. Read existing data (JSONL) and only generate DOT (requires --dot)",
    ),
    subgraphs_dir: Optional[Path] = typer.Option(
        None,
        "--subgraphs-dir",
        help="Directory to write per-root reference subgraph DOT files (one file per root function)",
    ),
    only_subgraphs: bool = typer.Option(
        False,
        "--only-subgraphs",
        help="Do not rescan. Only generate per-root reference subgraph DOT files (requires --subgraphs-dir)",
    ),
    png: bool = typer.Option(
        False,
        "--png",
        help="Also render PNG images for generated DOT files using Graphviz 'dot'",
    ),
) -> None:
    """
    进行 C/C++ 函数扫描并可选生成引用关系 DOT 图
    """
    _run_scan(
        dot=dot,
        only_dot=only_dot,
        subgraphs_dir=subgraphs_dir,
        only_subgraphs=only_subgraphs,
        png=png,
    )

@app.command("plan")
def llm_plan(
    out: Optional[Path] = typer.Option(
        None, "--out", help="Write LLM-generated Rust crate plan (YAML) to file (default: stdout)"
    ),
    apply: bool = typer.Option(
        False, "--apply", help="Create directories and add submodule declarations to mod.rs based on Agent output"
    ),
    crate_name: Optional[str] = typer.Option(
        None, "--crate-name", help="Override the crate name (and directory). When used with --apply, structure is created under this name"
    ),
    llm_group: Optional[str] = typer.Option(
        None, "-g", "--llm-group", help="Specify LLM model group for planning (only affects this run)"
    ),
) -> None:
    """
    使用 LLM Agent 基于根函数子图规划 Rust crate 模块结构，输出 YAML
    需先执行: jarvis-c2rust scan 以生成数据文件（functions.jsonl 与 types.jsonl）
    默认使用当前目录作为项目根，并从 <root>/.jarvis/c2rust/functions.jsonl 读取数据
    """
    try:
        entries = _execute_llm_plan(out=out, apply=apply, crate_name=crate_name, llm_group=llm_group)
        if out is None:
            typer.echo(_entries_to_yaml(entries))
    except Exception as e:
        typer.secho(f"[c2rust-llm-planner] Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command("transpile")
def transpile(
    crate_name: Optional[str] = typer.Option(
        None, "--crate-name", help="Target Rust crate name (directory). If provided, translations will be written under this crate"
    ),
    llm_group: Optional[str] = typer.Option(
        None, "-g", "--llm-group", help="Specify LLM model group for translation"
    ),
    only: Optional[str] = typer.Option(
        None, "--only", help="Only translate specified functions (name or qualified name), comma-separated"
    ),
) -> None:
    """
    使用转译器按扫描顺序逐个函数转译并构建修复。
    需先执行: jarvis-c2rust scan 以生成数据文件（functions.jsonl 与 translation_order.jsonl）
    默认使用当前目录作为项目根，并从 <root>/.jarvis/c2rust/functions.jsonl 读取数据。
    crate_name：用于指定目标crate目录名称（与llm规划中的参数一致）。未指定时使用默认 <cwd>/<cwd.name>-rs。
    """
    try:
        # Lazy import to avoid hard dependency if not used
        from jarvis.jarvis_c2rust.transpiler import run_transpile as _run_transpile
        only_list = [s.strip() for s in str(only).split(",") if s.strip()] if only else None
        crate_dir_path = Path(crate_name) if crate_name else None
        _run_transpile(
            project_root=Path("."),
            crate_dir=crate_dir_path,
            llm_group=llm_group,
            only=only_list,
        )
    except Exception as e:
        typer.secho(f"[c2rust-transpiler] Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


def main() -> None:
    """主入口"""
    app()


if __name__ == "__main__":
    main()