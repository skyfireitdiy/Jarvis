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
from jarvis.jarvis_c2rust.pruner import (
    evaluate_third_party_replacements as _eval_third_party_replacements,
)
from jarvis.jarvis_c2rust.scanner import (
    compute_translation_order_jsonl as _compute_order,
)
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
    需先执行: jarvis-c2rust scan 以生成数据文件（symbols.jsonl 与 translation_order.jsonl）
    默认使用当前目录作为项目根，并从 <root>/.jarvis/c2rust/symbols.jsonl 读取数据。
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


@app.command("prune")
def prune(
    llm_group: Optional[str] = typer.Option(
        None,
        "-g",
        "--llm-group",
        help="指定用于评估的 LLM 模型组（传递给 CodeAgent）",
    ),
) -> None:
    """
    使用 Agent 评估函数是否可由开源第三方库单函数替代：
    - 若可替代：移除该函数及其子引用（子引用不再评估）
    - 生成新的符号表与替代映射

    默认约定:
    - 数据源: <cwd>/.jarvis/c2rust/symbols.jsonl（若不存在将尝试自动扫描生成）
    - 新符号表输出: <cwd>/.jarvis/c2rust/symbols_third_party_pruned.jsonl
    - 替代映射输出: <cwd>/.jarvis/c2rust/third_party_replacements.jsonl
    """
    try:
        # 若未找到符号数据，则先执行一次扫描生成 symbols_raw.jsonl（保留中间产物）
        data_dir = Path(".") / ".jarvis" / "c2rust"
        curated_symbols = data_dir / "symbols.jsonl"
        raw_symbols = data_dir / "symbols_raw.jsonl"
        if not curated_symbols.exists() and not raw_symbols.exists():
            typer.secho("[c2rust-prune] 未找到符号数据（symbols.jsonl 或 symbols_raw.jsonl），正在执行扫描以生成数据...", fg=typer.colors.YELLOW)
            _run_scan(dot=None, only_dot=False, subgraphs_dir=None, only_subgraphs=False, png=False)
            if not curated_symbols.exists() and not raw_symbols.exists():
                raise FileNotFoundError(f"未找到符号数据: {curated_symbols} 或 {raw_symbols}")

        # 使用默认位置 (<cwd>/.jarvis/c2rust/symbols.jsonl) 与默认输出文件名
        ret = _eval_third_party_replacements(
            db_path=Path("."),            # 函数内部会解析到默认 JSONL 路径（优先 <cwd>/.jarvis/c2rust/symbols.jsonl）
            out_symbols_path=None,        # 使用默认输出路径
            out_mapping_path=None,        # 使用默认输出路径
            llm_group=llm_group,
            max_funcs=None,               # 默认不限制
        )

        # 覆盖默认 symbols.jsonl，使后续流程“直接使用新的符号表”
        data_dir.mkdir(parents=True, exist_ok=True)
        default_symbols = data_dir / "symbols.jsonl"
        pruned_symbols = Path(ret["symbols"])
        try:
            import shutil
            shutil.copy2(pruned_symbols, default_symbols)
        except Exception as _e:
            typer.secho(f"[c2rust-prune] 覆盖默认符号表失败: {default_symbols} <- {pruned_symbols}: {_e}", fg=typer.colors.RED, err=True)
            raise

        # 基于已覆盖的默认符号表，重新计算转译顺序（translation_order.jsonl）
        try:
            order_path = _compute_order(default_symbols)
        except Exception as _e2:
            typer.secho(f"[c2rust-prune] 计算转译顺序失败: {_e2}", fg=typer.colors.RED, err=True)
            raise

        typer.secho(
            (
                f"[c2rust-prune] 替代映射: {ret['mapping']}\n"
                f"[c2rust-prune] 新符号表(已覆盖默认): {default_symbols}\n"
                f"[c2rust-prune] 转译顺序已基于新符号表生成: {order_path}"
            ),
            fg=typer.colors.GREEN,
        )
    except Exception as e:
        typer.secho(f"[c2rust-prune] 错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

def main() -> None:
    """主入口"""
    app()


if __name__ == "__main__":
    main()