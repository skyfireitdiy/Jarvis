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
        help="扫描后将引用依赖图写入 DOT 文件（或与 --only-dot 一起使用）",
    ),
    only_dot: bool = typer.Option(
        False,
        "--only-dot",
        help="不重新扫描。读取现有数据 (JSONL) 并仅生成 DOT（需要 --dot）",
    ),
    subgraphs_dir: Optional[Path] = typer.Option(
        None,
        "--subgraphs-dir",
        help="用于写入每个根函数引用子图 DOT 文件的目录（每个根函数一个文件）",
    ),
    only_subgraphs: bool = typer.Option(
        False,
        "--only-subgraphs",
        help="不重新扫描。仅生成每个根函数的引用子图 DOT 文件（需要 --subgraphs-dir）",
    ),
) -> None:
    """
    进行 C/C++ 函数扫描并生成引用关系 DOT 图；PNG 渲染默认启用（无需参数）。
    """
    _run_scan(
        dot=dot,
        only_dot=only_dot,
        subgraphs_dir=subgraphs_dir,
        only_subgraphs=only_subgraphs,
        png=True,
    )

@app.command("prepare")
def prepare(
    llm_group: Optional[str] = typer.Option(
        None, "-g", "--llm-group", help="指定用于规划的 LLM 模型组（仅影响本次运行）"
    ),
) -> None:
    """
    使用 LLM Agent 基于根函数子图规划 Rust crate 模块结构并直接应用到磁盘。
    需先执行: jarvis-c2rust scan 以生成数据文件（symbols.jsonl）
    默认使用当前目录作为项目根，并从 <root>/.jarvis/c2rust/symbols.jsonl 读取数据
    """
    try:
        _execute_llm_plan(apply=True, llm_group=llm_group)
    except Exception as e:
        typer.secho(f"[c2rust-llm-planner] 错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command("transpile")
def transpile(
    llm_group: Optional[str] = typer.Option(
        None, "-g", "--llm-group", help="指定用于翻译的 LLM 模型组"
    ),
    only: Optional[str] = typer.Option(
        None, "--only", help="仅翻译指定的函数（名称或限定名称），以逗号分隔"
    ),
) -> None:
    """
    使用转译器按扫描顺序逐个函数转译并构建修复。
    需先执行: jarvis-c2rust scan 以生成数据文件（functions.jsonl 与 translation_order.jsonl）
    默认使用当前目录作为项目根，并从 <root>/.jarvis/c2rust/functions.jsonl 读取数据。
    未指定目标 crate 时，使用默认 <cwd>/<cwd.name>-rs。
    """
    try:
        # Lazy import to avoid hard dependency if not used
        from jarvis.jarvis_c2rust.transpiler import run_transpile as _run_transpile
        only_list = [s.strip() for s in str(only).split(",") if s.strip()] if only else None
        _run_transpile(
            project_root=Path("."),
            crate_dir=None,
            llm_group=llm_group,
            only=only_list,
        )
    except Exception as e:
        typer.secho(f"[c2rust-transpiler] 错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)



def main() -> None:
    """主入口"""
    app()


if __name__ == "__main__":
    main()