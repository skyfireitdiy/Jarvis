# -*- coding: utf-8 -*-
"""
C2Rust 独立命令行入口。

提供分组式 CLI：
  - jarvis-c2rust run: 执行完整的转译流水线（scan -> lib-replace -> prepare -> transpile -> optimize），支持断点续跑
  - jarvis-c2rust config: 管理转译配置文件（根符号列表、禁用库列表、附加说明等）

实现策略：
- 使用 Typer 分组式结构，便于后续扩展更多子命令（如 analyze/export 等）。
- run 命令支持断点续跑，根据状态文件自动跳过已完成的阶段。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List
from typing import Optional

import typer

from jarvis.jarvis_c2rust.library_replacer import (
    apply_library_replacement as _apply_library_replacement,
)
from jarvis.jarvis_c2rust.llm_module_agent import execute_llm_plan as _execute_llm_plan
from jarvis.jarvis_c2rust.scanner import run_scan as _run_scan
from jarvis.jarvis_utils.utils import init_env


def _check_optimize_completed(crate_dir: Path) -> bool:
    """
    检查优化是否真正完成。
    需要检查 optimize_progress.json 中所有必要的步骤是否都完成了。
    特别是 clippy_elimination：如果有告警，必须完成；如果没有告警，可以跳过。
    """
    import json

    from jarvis.jarvis_c2rust.constants import C2RUST_DIRNAME

    progress_path = crate_dir / C2RUST_DIRNAME / "optimize_progress.json"
    if not progress_path.exists():
        # 如果没有进度文件，说明还没开始，不算完成
        return False

    try:
        with progress_path.open("r", encoding="utf-8") as f:
            progress = json.load(f)

        steps_completed = set(progress.get("steps_completed", []))

        # 检查是否有 clippy 告警
        # 直接调用 optimizer 模块中的函数（虽然是私有函数，但我们需要它来检查）
        import subprocess

        try:
            res = subprocess.run(
                ["cargo", "clippy", "--", "-W", "clippy::all"],
                capture_output=True,
                text=True,
                check=False,
                cwd=str(crate_dir),
            )
            stderr_output = (res.stderr or "").strip()
            stdout_output = (res.stdout or "").strip()
            output = (
                (stderr_output + "\n" + stdout_output).strip()
                if (stderr_output and stdout_output)
                else (stderr_output or stdout_output or "").strip()
            )
            output_lower = output.lower()
            has_warnings = (
                "warning:" in output_lower
                or "warn(" in output_lower
                or ("clippy::" in output_lower and res.returncode != 0)
            )
        except Exception:
            # 如果检查失败，保守地认为有告警（需要完成）
            has_warnings = True

        # 如果有告警，clippy_elimination 必须在 steps_completed 中
        if has_warnings:
            if "clippy_elimination" not in steps_completed:
                return False

        # 检查其他必要的步骤（根据 enable_* 选项，但这里我们假设都启用了）
        # 注意：这里我们只检查 clippy_elimination，其他步骤（unsafe_cleanup, visibility_opt, doc_opt）
        # 可能因为 enable_* 选项而未执行，所以不强制要求

        return True
    except Exception:
        # 如果读取失败，保守地认为未完成
        return False


app = typer.Typer(help="C2Rust 命令行工具")


# 显式定义根回调，确保为命令组而非单函数入口
@app.callback()
def _root():
    """
    C2Rust 命令行工具
    """
    # 设置环境变量，标识当前运行在 c2rust 环境中
    os.environ["JARVIS_C2RUST_ENABLED"] = "1"
    # 不做任何处理，仅作为命令组的占位，使 'scan' 作为子命令出现
    init_env("")
    pass


def _load_config() -> dict:
    """
    从配置文件加载配置。
    返回包含 root_symbols、disabled_libraries 和 additional_notes 的字典。
    """
    import json

    from jarvis.jarvis_c2rust.constants import C2RUST_DIRNAME
    from jarvis.jarvis_c2rust.constants import CONFIG_JSON

    data_dir = Path(".") / C2RUST_DIRNAME
    config_path = data_dir / CONFIG_JSON
    default_config = {
        "root_symbols": [],
        "disabled_libraries": [],
        "additional_notes": "",
    }

    if not config_path.exists():
        return default_config

    try:
        with config_path.open("r", encoding="utf-8") as f:
            config = json.load(f)
            if not isinstance(config, dict):
                return default_config
            # 确保包含所有必需的键
            return {
                "root_symbols": config.get("root_symbols", []),
                "disabled_libraries": config.get("disabled_libraries", []),
                "additional_notes": config.get("additional_notes", ""),
            }
    except Exception:
        return default_config


def _get_run_state_path() -> Path:
    """获取 run 状态文件路径"""
    from jarvis.jarvis_c2rust.constants import C2RUST_DIRNAME
    from jarvis.jarvis_c2rust.constants import RUN_STATE_JSON

    data_dir = Path(".") / C2RUST_DIRNAME
    return data_dir / RUN_STATE_JSON


def _load_run_state() -> dict:
    """加载 run 状态文件"""
    import json

    state_path = _get_run_state_path()
    default_state = {
        "scan": {"completed": False, "timestamp": None},
        "lib_replace": {"completed": False, "timestamp": None},
        "prepare": {"completed": False, "timestamp": None},
        "transpile": {"completed": False, "timestamp": None},
        "optimize": {"completed": False, "timestamp": None},
    }

    if not state_path.exists():
        return default_state

    try:
        with state_path.open("r", encoding="utf-8") as f:
            state = json.load(f)
            if not isinstance(state, dict):
                return default_state
            # 确保包含所有必需的阶段
            for stage in ["scan", "lib_replace", "prepare", "transpile", "optimize"]:
                if stage not in state:
                    state[stage] = {"completed": False, "timestamp": None}
            return state
    except Exception:
        return default_state


def _save_run_state(stage: str, completed: bool = True) -> None:
    """保存 run 状态文件"""
    import json
    import time

    state_path = _get_run_state_path()
    state = _load_run_state()

    state[stage] = {
        "completed": completed,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
        if completed
        else None,
    }

    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        with state_path.open("w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        typer.secho(
            f"[c2rust-run] 保存状态文件失败: {e}", fg=typer.colors.YELLOW, err=True
        )


@app.command("config")
def config(
    files: Optional[List[Path]] = typer.Option(
        None,
        "--files",
        help="头文件（.h/.hh/.hpp/.hxx）或函数名列表文件（每行一个函数名，忽略空行与以#开头的注释）",
    ),
    root_list_syms: Optional[str] = typer.Option(
        None, "--root-list-syms", help="根符号列表内联（逗号分隔）"
    ),
    disabled_libs: Optional[str] = typer.Option(
        None, "--disabled-libs", help="禁用库列表（逗号分隔）"
    ),
    additional_notes: Optional[str] = typer.Option(
        None, "--additional-notes", help="附加说明（将在所有 agent 的提示词中追加）"
    ),
    show: bool = typer.Option(False, "--show", help="显示当前配置内容"),
    clear: bool = typer.Option(False, "--clear", help="清空配置（重置为默认值）"),
) -> None:
    """
    管理转译配置文件（.jarvis/c2rust/config.json）。

    可以设置根符号列表（root_symbols）、禁用库列表（disabled_libraries）和附加说明（additional_notes）。
    这些配置会被 transpile 命令自动读取和使用。

    示例:
      # 从头文件自动提取函数名并设置根符号列表
      jarvis-c2rust config --files bzlib.h

      # 从多个头文件提取函数名
      jarvis-c2rust config --files a.h b.hpp c.hxx

      # 从函数名列表文件设置根符号列表
      jarvis-c2rust config --files roots.txt

      # 从命令行设置根符号列表
      jarvis-c2rust config --root-list-syms "func1,func2,func3"

      # 设置禁用库列表
      jarvis-c2rust config --disabled-libs "libc,libm"

      # 设置附加说明（将在所有 agent 的提示词中追加）
      jarvis-c2rust config --additional-notes "注意：所有函数必须处理错误情况，避免 panic"

      # 同时设置多个参数
      jarvis-c2rust config --files bzlib.h --disabled-libs "libc" --additional-notes "特殊要求说明"

      # 查看当前配置
      jarvis-c2rust config --show

      # 清空配置
      jarvis-c2rust config --clear
    """
    import json

    from jarvis.jarvis_c2rust.constants import C2RUST_DIRNAME
    from jarvis.jarvis_c2rust.constants import CONFIG_JSON

    data_dir = Path(".") / C2RUST_DIRNAME
    config_path = data_dir / CONFIG_JSON
    data_dir.mkdir(parents=True, exist_ok=True)

    # 读取现有配置
    default_config = {
        "root_symbols": [],
        "disabled_libraries": [],
        "additional_notes": "",
    }
    current_config = default_config.copy()

    if config_path.exists():
        try:
            with config_path.open("r", encoding="utf-8") as f:
                current_config = json.load(f)
                if not isinstance(current_config, dict):
                    current_config = default_config.copy()
        except Exception as e:
            typer.secho(
                f"[c2rust-config] 读取现有配置失败: {e}，将使用默认值",
                fg=typer.colors.YELLOW,
            )
            current_config = default_config.copy()

    # 如果只是查看配置
    if show:
        typer.secho(
            f"[c2rust-config] 当前配置文件: {config_path}", fg=typer.colors.BLUE
        )
        typer.secho(
            json.dumps(current_config, ensure_ascii=False, indent=2),
            fg=typer.colors.CYAN,
        )
        return

    # 如果清空配置
    if clear:
        current_config = default_config.copy()
        with config_path.open("w", encoding="utf-8") as f:
            json.dump(current_config, f, ensure_ascii=False, indent=2)
        typer.secho(f"[c2rust-config] 配置已清空: {config_path}", fg=typer.colors.GREEN)
        return

    # 读取根符号列表（从现有配置开始，以便追加而不是替换）
    root_symbols: List[str] = list(current_config.get("root_symbols", []))
    header_exts = {".h", ".hh", ".hpp", ".hxx"}

    if files:
        for file_path in files:
            try:
                file_path = Path(file_path).resolve()
                if not file_path.exists():
                    typer.secho(
                        f"[c2rust-config] 警告: 文件不存在，跳过: {file_path}",
                        fg=typer.colors.YELLOW,
                    )
                    continue

                # 检查是否是头文件
                if file_path.suffix.lower() in header_exts:
                    # 从头文件提取函数名
                    typer.secho(
                        f"[c2rust-config] 从头文件提取函数名: {file_path}",
                        fg=typer.colors.BLUE,
                    )
                    try:
                        # 使用临时文件存储提取的函数名
                        import tempfile

                        from jarvis.jarvis_c2rust.collector import (
                            collect_function_names as _collect_fn_names,
                        )

                        with tempfile.NamedTemporaryFile(
                            mode="w", suffix=".txt", delete=False, encoding="utf-8"
                        ) as tmp:
                            tmp_path = Path(tmp.name)
                        _collect_fn_names(
                            files=[file_path],
                            out_path=tmp_path,
                            compile_commands_root=None,
                        )
                        # 读取提取的函数名
                        txt = tmp_path.read_text(encoding="utf-8")
                        collected = [
                            ln.strip() for ln in txt.splitlines() if ln.strip()
                        ]
                        root_symbols.extend(collected)
                        typer.secho(
                            f"[c2rust-config] 从头文件 {file_path.name} 提取了 {len(collected)} 个函数名",
                            fg=typer.colors.GREEN,
                        )
                        # 清理临时文件
                        try:
                            tmp_path.unlink()
                        except Exception:
                            pass
                    except Exception as e:
                        typer.secho(
                            f"[c2rust-config] 从头文件提取函数名失败: {file_path}: {e}",
                            fg=typer.colors.RED,
                            err=True,
                        )
                        raise typer.Exit(code=1)
                else:
                    # 读取函数名列表文件（每行一个函数名）
                    txt = file_path.read_text(encoding="utf-8")
                    collected = [
                        ln.strip()
                        for ln in txt.splitlines()
                        if ln.strip() and not ln.strip().startswith("#")
                    ]
                    root_symbols.extend(collected)
                    typer.secho(
                        f"[c2rust-config] 从文件 {file_path.name} 读取了 {len(collected)} 个根符号",
                        fg=typer.colors.BLUE,
                    )
            except typer.Exit:
                raise
            except Exception as e:
                typer.secho(
                    f"[c2rust-config] 处理文件失败: {file_path}: {e}",
                    fg=typer.colors.RED,
                    err=True,
                )
                raise typer.Exit(code=1)

    # 标记是否处理了 root_list_syms，以便即使结果为空也更新配置
    processed_root_list_syms = False
    if isinstance(root_list_syms, str) and root_list_syms.strip():
        parts = [
            s.strip() for s in root_list_syms.replace("\n", ",").split(",") if s.strip()
        ]
        root_symbols.extend(parts)
        processed_root_list_syms = True
        typer.secho(
            f"[c2rust-config] 从命令行读取根符号: {len(parts)} 个", fg=typer.colors.BLUE
        )

    # 去重根符号列表（如果处理了 files 或 root_list_syms，或者 root_symbols 非空，则更新配置）
    if files or processed_root_list_syms or root_symbols:
        try:
            root_symbols = list(dict.fromkeys(root_symbols))
        except Exception:
            root_symbols = sorted(list(set(root_symbols)))
        current_config["root_symbols"] = root_symbols
        typer.secho(
            f"[c2rust-config] 已设置根符号列表: {len(root_symbols)} 个",
            fg=typer.colors.GREEN,
        )

    # 读取禁用库列表
    if isinstance(disabled_libs, str) and disabled_libs.strip():
        disabled_list = [
            s.strip() for s in disabled_libs.replace("\n", ",").split(",") if s.strip()
        ]
        if disabled_list:
            current_config["disabled_libraries"] = disabled_list
            typer.secho(
                f"[c2rust-config] 已设置禁用库列表: {', '.join(disabled_list)}",
                fg=typer.colors.GREEN,
            )

    # 读取附加说明
    if isinstance(additional_notes, str):
        current_config["additional_notes"] = additional_notes.strip()
        if additional_notes.strip():
            typer.secho(
                f"[c2rust-config] 已设置附加说明: {len(additional_notes.strip())} 字符",
                fg=typer.colors.GREEN,
            )
        else:
            typer.secho("[c2rust-config] 已清空附加说明", fg=typer.colors.GREEN)

    # 如果没有提供任何参数，提示用户
    if (
        not files
        and not root_list_syms
        and not disabled_libs
        and additional_notes is None
    ):
        typer.secho(
            "[c2rust-config] 未提供任何参数，使用 --show 查看当前配置，或使用 --help 查看帮助",
            fg=typer.colors.YELLOW,
        )
        return

    # 保存配置
    try:
        with config_path.open("w", encoding="utf-8") as f:
            json.dump(current_config, f, ensure_ascii=False, indent=2)
        typer.secho(f"[c2rust-config] 配置已保存: {config_path}", fg=typer.colors.GREEN)
        typer.secho(
            json.dumps(current_config, ensure_ascii=False, indent=2),
            fg=typer.colors.CYAN,
        )
    except Exception as e:
        typer.secho(f"[c2rust-config] 保存配置失败: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command("run")
def run(
    llm_group: Optional[str] = typer.Option(
        None,
        "-g",
        "--llm-group",
        help="用于 LLM 相关阶段（lib-replace/prepare/transpile/optimize）的模型组",
    ),
    max_retries: int = typer.Option(
        0,
        "-m",
        "--max-retries",
        help="transpile 构建/修复与审查的最大重试次数（0 表示不限制）",
    ),
    interactive: bool = typer.Option(
        False,
        "--interactive",
        help="启用交互模式（默认非交互模式）",
    ),
    reset: bool = typer.Option(
        False,
        "--reset",
        help="重置状态，从头开始执行所有阶段",
    ),
) -> None:
    """
    依次执行流水线：scan -> lib-replace -> prepare -> transpile -> optimize

    支持断点续跑：根据状态文件（.jarvis/c2rust/run_state.json）自动跳过已完成的阶段。

    约束:

    - 根符号列表和禁用库列表从配置文件（.jarvis/c2rust/config.json）读取
      使用 jarvis-c2rust config 命令设置这些配置（例如：jarvis-c2rust config --files bzlib.h）

    - 使用 --reset 可以重置状态，从头开始执行所有阶段

    - prepare/transpile 会使用 --llm-group 指定的模型组

    - optimize 阶段采用默认优化配置，自动检测 crate 根目录并进行保守优化（unsafe 清理、结构优化、可见性优化、文档补充）
    """

    try:
        # 加载状态文件
        if reset:
            # 重置状态
            state_path = _get_run_state_path()
            if state_path.exists():
                state_path.unlink()
                typer.secho(
                    "[c2rust-run] 已重置状态，将从头开始执行", fg=typer.colors.YELLOW
                )
            state = _load_run_state()
        else:
            state = _load_run_state()
            # 显示当前状态
            completed_stages = [
                s for s, info in state.items() if info.get("completed", False)
            ]
            if completed_stages:
                typer.secho(
                    f"[c2rust-run] 检测到已完成阶段: {', '.join(completed_stages)}，将从断点继续",
                    fg=typer.colors.CYAN,
                )

        # Step 1: scan
        if not state.get("scan", {}).get("completed", False):
            typer.secho("[c2rust-run] scan: 开始", fg=typer.colors.BLUE)
            _run_scan(
                dot=None,
                only_dot=False,
                subgraphs_dir=None,
                only_subgraphs=False,
                png=False,
                non_interactive=True,
            )
            typer.secho("[c2rust-run] scan: 完成", fg=typer.colors.GREEN)
            # 保存状态（因为直接调用 _run_scan 函数，需要手动保存状态）
            _save_run_state("scan", completed=True)
        else:
            typer.secho("[c2rust-run] scan: 已完成，跳过", fg=typer.colors.CYAN)

        # Step 2: lib-replace（从配置文件读取根列表和禁用库列表）
        if not state.get("lib_replace", {}).get("completed", False):
            # 从配置文件读取基础配置
            config = _load_config()
            root_names: List[str] = list(config.get("root_symbols", []))
            disabled_list: Optional[List[str]] = (
                config.get("disabled_libraries", []) or None
            )

            # 去重并校验（允许为空时回退为自动根集）
            if root_names:
                try:
                    root_names = list(dict.fromkeys(root_names))
                except Exception:
                    root_names = sorted(list(set(root_names)))

            candidates_list: Optional[List[str]] = root_names if root_names else None
            if not candidates_list:
                typer.secho(
                    "[c2rust-run] lib-replace: 根列表为空，将回退为自动检测的根集合（基于扫描结果）",
                    fg=typer.colors.YELLOW,
                )

            if disabled_list:
                typer.secho(
                    f"[c2rust-run] lib-replace: 从配置文件读取禁用库: {', '.join(disabled_list)}",
                    fg=typer.colors.BLUE,
                )

            # 执行 lib-replace（默认库 std）
            library = "std"
            root_count_str = (
                str(len(candidates_list)) if candidates_list is not None else "auto"
            )
            typer.secho(
                f"[c2rust-run] lib-replace: 开始（库: {library}，根数: {root_count_str}）",
                fg=typer.colors.BLUE,
            )
            ret = _apply_library_replacement(
                db_path=Path("."),
                library_name=library,
                llm_group=llm_group,
                candidates=candidates_list,  # None 表示自动检测全部根
                out_symbols_path=None,
                out_mapping_path=None,
                max_funcs=None,
                disabled_libraries=disabled_list,
                non_interactive=not interactive,
            )
            try:
                order_msg = (
                    f"\n[c2rust-run] lib-replace: 转译顺序: {ret['order']}"
                    if "order" in ret
                    else ""
                )
                typer.secho(
                    f"[c2rust-run] lib-replace: 替代映射: {ret['mapping']}\n"
                    f"[c2rust-run] lib-replace: 新符号表: {ret['symbols']}" + order_msg,
                    fg=typer.colors.GREEN,
                )
            except Exception as _e:
                typer.secho(
                    f"[c2rust-run] lib-replace: 结果输出时发生非致命错误: {_e}",
                    fg=typer.colors.YELLOW,
                    err=True,
                )
            # 保存状态（因为直接调用 _apply_library_replacement 函数，需要手动保存状态）
            _save_run_state("lib_replace", completed=True)
        else:
            typer.secho("[c2rust-run] lib-replace: 已完成，跳过", fg=typer.colors.CYAN)

        # Step 3: prepare
        if not state.get("prepare", {}).get("completed", False):
            typer.secho("[c2rust-run] prepare: 开始", fg=typer.colors.BLUE)
            _execute_llm_plan(
                apply=True, llm_group=llm_group, non_interactive=not interactive
            )
            typer.secho("[c2rust-run] prepare: 完成", fg=typer.colors.GREEN)
            # 保存状态（因为直接调用 _execute_llm_plan 函数，需要手动保存状态）
            _save_run_state("prepare", completed=True)
        else:
            typer.secho("[c2rust-run] prepare: 已完成，跳过", fg=typer.colors.CYAN)

        # Step 4: transpile
        if not state.get("transpile", {}).get("completed", False):
            typer.secho("[c2rust-run] transpile: 开始", fg=typer.colors.BLUE)
            from jarvis.jarvis_c2rust.transpiler import run_transpile as _run_transpile

            # 从配置文件读取配置（transpile 内部会自动读取）
            _run_transpile(
                project_root=Path("."),
                crate_dir=None,
                llm_group=llm_group,
                max_retries=max_retries,
                disabled_libraries=None,  # 从配置文件恢复
                root_symbols=None,  # 从配置文件恢复
                non_interactive=not interactive,
            )
            typer.secho("[c2rust-run] transpile: 完成", fg=typer.colors.GREEN)
            # 保存状态（因为直接调用 _run_transpile 函数，需要手动保存状态）
            _save_run_state("transpile", completed=True)
        else:
            typer.secho("[c2rust-run] transpile: 已完成，跳过", fg=typer.colors.CYAN)

        # Step 5: optimize
        if not state.get("optimize", {}).get("completed", False):
            try:
                typer.secho("[c2rust-run] optimize: 开始", fg=typer.colors.BLUE)
                from jarvis.jarvis_c2rust.optimizer import (
                    optimize_project as _optimize_project,
                )
                from jarvis.jarvis_c2rust.utils import default_crate_dir

                # 使用与 transpile 相同的逻辑确定项目根目录和 crate 目录
                project_root = Path(".")
                crate_dir = default_crate_dir(project_root)
                typer.secho(
                    f"[c2rust-run] optimize: 使用项目根目录: {project_root}, crate 目录: {crate_dir}",
                    fg=typer.colors.CYAN,
                )
                res = _optimize_project(
                    project_root=project_root,
                    crate_dir=crate_dir,
                    llm_group=llm_group,
                    non_interactive=not interactive,
                )
                summary = (
                    f"[c2rust-run] optimize: 结果摘要:\n"
                    f"  files_scanned: {res.get('files_scanned')}\n"
                    f"  unsafe_removed: {res.get('unsafe_removed')}\n"
                    f"  unsafe_annotated: {res.get('unsafe_annotated')}\n"
                    f"  visibility_downgraded: {res.get('visibility_downgraded')}\n"
                    f"  docs_added: {res.get('docs_added')}\n"
                    f"  cargo_checks: {res.get('cargo_checks')}\n"
                )
                typer.secho(summary, fg=typer.colors.GREEN)

                # 检查优化是否真正完成（所有步骤都完成，包括 clippy 告警修复）
                optimize_truly_completed = _check_optimize_completed(crate_dir)
                if optimize_truly_completed:
                    typer.secho("[c2rust-run] optimize: 完成", fg=typer.colors.GREEN)
                    # 保存状态（因为直接调用 _optimize_project 函数，需要手动保存状态）
                    _save_run_state("optimize", completed=True)
                else:
                    typer.secho(
                        "[c2rust-run] optimize: 部分步骤未完成（如 clippy 告警未完全修复），下次将继续",
                        fg=typer.colors.YELLOW,
                    )
                    # 不保存状态，下次恢复时会继续执行优化
            except Exception as _e:
                typer.secho(
                    f"[c2rust-run] optimize: 错误: {_e}", fg=typer.colors.RED, err=True
                )
                raise
        else:
            typer.secho("[c2rust-run] optimize: 已完成，跳过", fg=typer.colors.CYAN)

        # 所有阶段完成
        typer.secho("[c2rust-run] 所有阶段已完成！", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"[c2rust-run] 错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


def main() -> None:
    """主入口"""
    app()


if __name__ == "__main__":
    main()
