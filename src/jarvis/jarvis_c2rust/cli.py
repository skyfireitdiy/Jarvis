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
from typing import Optional, List

import typer
from jarvis.jarvis_c2rust.scanner import run_scan as _run_scan
from jarvis.jarvis_c2rust.scanner import (
    compute_translation_order_jsonl as _compute_order,
)
from jarvis.jarvis_c2rust.library_replacer import (
    apply_library_replacement as _apply_library_replacement,
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
    max_retries: int = typer.Option(
        0, "-m", "--max-retries", help="构建/修复与审查的最大重试次数（0 表示不限制）"
    ),
    resume: bool = typer.Option(
        True, "--resume/--no-resume", help="是否启用断点续跑（默认启用）"
    ),
) -> None:
    """
    使用转译器按扫描顺序逐个函数转译并构建修复。
    需先执行: jarvis-c2rust scan 以生成数据文件（symbols.jsonl 与 translation_order.jsonl）
    默认使用当前目录作为项目根，并从 <root>/.jarvis/c2rust/symbols.jsonl 读取数据。
    未指定目标 crate 时，使用默认 <cwd>/<cwd.name>_rs。

    选项:
    - --only: 仅翻译指定的函数（名称或限定名称），以逗号分隔
    - --max-retries/-m: 构建/修复与审查的最大重试次数（0 表示不限制）
    - --resume/--no-resume: 是否启用断点续跑（默认启用）
    - --llm-group/-g: 指定用于翻译的 LLM 模型组
    """
    try:
        # Lazy import to avoid hard dependency if not used
        from jarvis.jarvis_c2rust.transpiler import run_transpile as _run_transpile
        only_list = [s.strip() for s in str(only).split(",") if s.strip()] if only else None
        _run_transpile(
            project_root=Path("."),
            crate_dir=None,
            llm_group=llm_group,
            max_retries=max_retries,
            resume=resume,
            only=only_list,
        )
    except Exception as e:
        typer.secho(f"[c2rust-transpiler] 错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command("lib-replace")
def lib_replace(
    llm_group: Optional[str] = typer.Option(
        None, "-g", "--llm-group", help="用于评估的 LLM 模型组"
    ),
    root_list_file: Optional[Path] = typer.Option(
        None, "--root-list-file", help="根列表文件：按行列出要参与评估的根符号名称或限定名（忽略空行与以#开头的注释）"
    ),
    root_list_syms: Optional[str] = typer.Option(
        None, "--root-list-syms", help="根列表内联：以逗号分隔的符号名称或限定名（仅评估这些根）"
    ),
    disabled_libs: Optional[str] = typer.Option(
        None, "--disabled-libs", help="禁用库列表：逗号分隔的库名（评估时禁止使用这些库）"
    ),
) -> None:
    """
    Root-list 评估模式（必须走 LLM 评估）：
    - 必须提供根列表（--root-list-file 或 --root-list-syms，至少一种）
    - 仅对根列表中的符号作为评估根执行 LLM 子树评估
    - 若可替代：替换该根的 ref 为库占位，并剪除其所有子孙函数（根本身保留）
    - 需先执行: jarvis-c2rust scan 以生成数据文件（symbols.jsonl）
    - 默认库: std（仅用于对后续流程保持一致的默认上下文）
    - 可选：--disabled-libs 指定评估时禁止使用的库列表（逗号分隔）
    """
    try:
        data_dir = Path(".") / ".jarvis" / "c2rust"
        curated_symbols = data_dir / "symbols.jsonl"
        raw_symbols = data_dir / "symbols_raw.jsonl"
        if not curated_symbols.exists() and not raw_symbols.exists():
            typer.secho("[c2rust-lib-replace] 未找到符号数据（symbols.jsonl 或 symbols_raw.jsonl），正在执行扫描以生成数据...", fg=typer.colors.YELLOW)
            _run_scan(dot=None, only_dot=False, subgraphs_dir=None, only_subgraphs=False, png=False)
            if not curated_symbols.exists() and not raw_symbols.exists():
                raise FileNotFoundError(f"未找到符号数据: {curated_symbols} 或 {raw_symbols}")

        # 使用默认库: std
        library = "std"

        # 读取根列表（必填，至少提供一种来源）
        root_names: List[str] = []
        # 文件来源
        if root_list_file is not None:
            try:
                txt = root_list_file.read_text(encoding="utf-8")
                root_names.extend([ln.strip() for ln in txt.splitlines() if ln.strip() and not ln.strip().startswith("#")])
            except Exception as _e:
                typer.secho(f"[c2rust-lib-replace] 读取根列表失败: {root_list_file}: {_e}", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1)
        # 内联来源
        if isinstance(root_list_syms, str) and root_list_syms.strip():
            parts = [s.strip() for s in root_list_syms.replace("\n", ",").split(",") if s.strip()]
            root_names.extend(parts)
        # 去重
        try:
            root_names = list(dict.fromkeys(root_names))
        except Exception:
            root_names = sorted(list(set(root_names)))
        if not root_names:
            typer.secho("[c2rust-lib-replace] 错误：必须提供根列表（--root-list-file 或 --root-list-syms）。", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)

        # 解析禁用库列表（可选）
        disabled_list: Optional[List[str]] = None
        if isinstance(disabled_libs, str) and disabled_libs.strip():
            disabled_list = [s.strip() for s in disabled_libs.replace("\n", ",").split(",") if s.strip()]
            if disabled_list:
                typer.secho(f"[c2rust-lib-replace] 禁用库: {', '.join(disabled_list)}", fg=typer.colors.YELLOW)

        # 必须走 LLM 评估：仅评估提供的根（candidates），不启用强制剪枝模式
        ret = _apply_library_replacement(
            db_path=Path("."),
            library_name=library,
            llm_group=llm_group,
            candidates=root_names,          # 仅评估这些根
            out_symbols_path=None,
            out_mapping_path=None,
            max_funcs=None,
            disabled_libraries=disabled_list,
        )
        # 输出简要结果摘要（底层已写出新的符号表与可选转译顺序）
        try:
            order_msg = f"\n[c2rust-lib-replace] 转译顺序: {ret['order']}" if 'order' in ret else ""
            typer.secho(
                f"[c2rust-lib-replace] 替代映射: {ret['mapping']}\n"
                f"[c2rust-lib-replace] 新符号表: {ret['symbols']}"
                + order_msg,
                fg=typer.colors.GREEN,
            )
        except Exception as _e:
            typer.secho(f"[c2rust-lib-replace] 结果输出时发生非致命错误: {_e}", fg=typer.colors.YELLOW, err=True)
    except Exception as e:
        typer.secho(f"[c2rust-lib-replace] 错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)



@app.command("collect")
def collect(
    files: List[Path] = typer.Argument(..., help="一个或多个 C/C++ 头文件路径（.h/.hh/.hpp/.hxx）"),
    out: Path = typer.Option(..., "-o", "--out", help="输出文件路径（写入唯一函数名，每行一个）"),
) -> None:
    """
    收集指定头文件中的函数名（使用 libclang 解析），并写入指定输出文件（每行一个）。
    示例:
      jarvis-c2rust collect a.h b.hpp -o funcs.txt
    说明:
      非头文件会被跳过（仅支持 .h/.hh/.hpp/.hxx）。
    """
    try:
        from jarvis.jarvis_c2rust.collector import collect_function_names as _collect_fn_names
        _collect_fn_names(files=files, out_path=out)
        typer.secho(f"[c2rust-collect] 函数名已写入: {out}", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"[c2rust-collect] 错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command("run")
def run(
    files: Optional[List[Path]] = typer.Option(
        None,
        "--files",
        help="用于 collect 阶段的头文件列表（.h/.hh/.hpp/.hxx）；提供则先执行 collect",
    ),
    out: Optional[Path] = typer.Option(
        None,
        "-o",
        "--out",
        help="collect 输出函数名文件；若未提供且指定 --files 则默认为 <root>/.jarvis/c2rust/roots.txt",
    ),
    llm_group: Optional[str] = typer.Option(
        None,
        "-g",
        "--llm-group",
        help="用于 LLM 相关阶段（lib-replace/prepare/transpile）的模型组",
    ),
    root_list_file: Optional[Path] = typer.Option(
        None,
        "--root-list-file",
        help="兼容占位：run 会使用 collect 的 --out 作为 lib-replace 的输入；当提供 --files 时本参数将被忽略；未提供 --files 时，本命令要求使用 --root-list-syms",
    ),
    root_list_syms: Optional[str] = typer.Option(
        None,
        "--root-list-syms",
        help="lib-replace 的根列表内联（逗号分隔）。未提供 --files 时该参数为必填",
    ),
    disabled_libs: Optional[str] = typer.Option(
        None,
        "--disabled-libs",
        help="lib-replace 禁用库列表（逗号分隔）",
    ),
) -> None:
    """
    依次执行流水线：collect -> scan -> lib-replace -> prepare -> transpile

    约束:
    - collect 的输出文件就是 lib-replace 的输入文件；
      当提供 --files 时，lib-replace 将固定读取 --out（或默认值）作为根列表文件，忽略 --root-list-file
    - 未提供 --files 时，必须通过 --root-list-syms 提供根列表
    - scan 始终执行以确保数据完整
    - prepare/transpile 会使用 --llm-group 指定的模型组
    """
    try:
        data_dir = Path(".") / ".jarvis" / "c2rust"
        default_roots = data_dir / "roots.txt"

        # Step 1: collect（可选）
        roots_path: Optional[Path] = None
        if files:
            try:
                if out is None:
                    out = default_roots
                out.parent.mkdir(parents=True, exist_ok=True)
                from jarvis.jarvis_c2rust.collector import (
                    collect_function_names as _collect_fn_names,
                )
                _collect_fn_names(files=files, out_path=out)
                typer.secho(f"[c2rust-run] collect: 函数名已写入: {out}", fg=typer.colors.GREEN)
                roots_path = out
            except Exception as _e:
                typer.secho(f"[c2rust-run] collect: 错误: {_e}", fg=typer.colors.RED, err=True)
                raise

        # Step 2: scan（始终执行）
        typer.secho("[c2rust-run] scan: 开始", fg=typer.colors.BLUE)
        _run_scan(dot=None, only_dot=False, subgraphs_dir=None, only_subgraphs=False, png=False)
        typer.secho("[c2rust-run] scan: 完成", fg=typer.colors.GREEN)

        # Step 3: lib-replace（强制执行，依据约束获取根列表）
        root_names: List[str] = []

        if files:
            # 约束：collect 的输出文件作为唯一文件来源
            if not roots_path or not roots_path.exists():
                typer.secho("[c2rust-run] lib-replace: 未找到 collect 输出文件，无法继续", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=2)
            try:
                txt = roots_path.read_text(encoding="utf-8")
                root_names.extend([ln.strip() for ln in txt.splitlines() if ln.strip() and not ln.strip().startswith("#")])
                typer.secho(f"[c2rust-run] lib-replace: 使用根列表文件: {roots_path}", fg=typer.colors.BLUE)
            except Exception as _e:
                typer.secho(f"[c2rust-run] lib-replace: 读取根列表失败: {roots_path}: {_e}", fg=typer.colors.RED, err=True)
                raise
            # 兼容参数提示
            if root_list_file is not None:
                typer.secho("[c2rust-run] 提示: --root-list-file 已被忽略（run 会固定使用 collect 的 --out 作为输入）", fg=typer.colors.YELLOW)
        else:
            # 约束：未传递 files 必须提供 --root-list-syms
            if not (isinstance(root_list_syms, str) and root_list_syms.strip()):
                typer.secho("[c2rust-run] 错误：未提供 --files 时，必须通过 --root-list-syms 指定根列表（逗号分隔）", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=2)
            parts = [s.strip() for s in root_list_syms.replace("\n", ",").split(",") if s.strip()]
            root_names.extend(parts)

        # 去重并校验非空
        try:
            root_names = list(dict.fromkeys(root_names))
        except Exception:
            root_names = sorted(list(set(root_names)))
        if not root_names:
            typer.secho("[c2rust-run] lib-replace: 根列表为空，无法继续", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)

        # 可选禁用库列表
        disabled_list: Optional[List[str]] = None
        if isinstance(disabled_libs, str) and disabled_libs.strip():
            disabled_list = [s.strip() for s in disabled_libs.replace("\n", ",").split(",") if s.strip()]
            if disabled_list:
                typer.secho(f"[c2rust-run] lib-replace: 禁用库: {', '.join(disabled_list)}", fg=typer.colors.YELLOW)

        # 执行 lib-replace（默认库 std）
        library = "std"
        typer.secho(f"[c2rust-run] lib-replace: 开始（库: {library}，根数: {len(root_names)}）", fg=typer.colors.BLUE)
        ret = _apply_library_replacement(
            db_path=Path("."),
            library_name=library,
            llm_group=llm_group,
            candidates=root_names,
            out_symbols_path=None,
            out_mapping_path=None,
            max_funcs=None,
            disabled_libraries=disabled_list,
        )
        try:
            order_msg = f"\n[c2rust-run] lib-replace: 转译顺序: {ret['order']}" if 'order' in ret else ""
            typer.secho(
                f"[c2rust-run] lib-replace: 替代映射: {ret['mapping']}\n"
                f"[c2rust-run] lib-replace: 新符号表: {ret['symbols']}"
                + order_msg,
                fg=typer.colors.GREEN,
            )
        except Exception as _e:
            typer.secho(f"[c2rust-run] lib-replace: 结果输出时发生非致命错误: {_e}", fg=typer.colors.YELLOW, err=True)

        # Step 4: prepare
        typer.secho("[c2rust-run] prepare: 开始", fg=typer.colors.BLUE)
        _execute_llm_plan(apply=True, llm_group=llm_group)
        typer.secho("[c2rust-run] prepare: 完成", fg=typer.colors.GREEN)

        # Step 5: transpile
        typer.secho("[c2rust-run] transpile: 开始", fg=typer.colors.BLUE)
        from jarvis.jarvis_c2rust.transpiler import run_transpile as _run_transpile
        _run_transpile(
            project_root=Path("."),
            crate_dir=None,
            llm_group=llm_group,
            only=None,
        )
        typer.secho("[c2rust-run] transpile: 完成", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"[c2rust-run] 错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


def main() -> None:
    """主入口"""
    app()


if __name__ == "__main__":
    main()