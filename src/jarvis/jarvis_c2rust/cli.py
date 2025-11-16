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

import os
from pathlib import Path
from typing import Optional, List

import typer
from jarvis.jarvis_c2rust.scanner import run_scan as _run_scan
from jarvis.jarvis_c2rust.library_replacer import (
    apply_library_replacement as _apply_library_replacement,
)
from jarvis.jarvis_utils.utils import init_env
from jarvis.jarvis_c2rust.llm_module_agent import (
    execute_llm_plan as _execute_llm_plan,
)

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
    init_env("欢迎使用 Jarvis C2Rust 工具")
    pass


def _load_config() -> dict:
    """
    从配置文件加载配置。
    返回包含 root_symbols 和 disabled_libraries 的字典。
    """
    import json
    from jarvis.jarvis_c2rust.transpiler import CONFIG_JSON, C2RUST_DIRNAME
    
    data_dir = Path(".") / C2RUST_DIRNAME
    config_path = data_dir / CONFIG_JSON
    default_config = {"root_symbols": [], "disabled_libraries": []}
    
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
            }
    except Exception:
        return default_config


RUN_STATE_JSON = "run_state.json"


def _get_run_state_path() -> Path:
    """获取 run 状态文件路径"""
    from jarvis.jarvis_c2rust.transpiler import C2RUST_DIRNAME
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
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()) if completed else None,
    }
    
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        with state_path.open("w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        typer.secho(f"[c2rust-run] 保存状态文件失败: {e}", fg=typer.colors.YELLOW, err=True)


def _get_next_stage(current_state: dict) -> Optional[str]:
    """根据状态文件确定下一个需要执行的阶段"""
    stages = ["scan", "lib_replace", "prepare", "transpile", "optimize"]
    for stage in stages:
        if not current_state.get(stage, {}).get("completed", False):
            return stage
    return None  # 所有阶段都已完成


# 定义各阶段的前置依赖关系
STAGE_DEPENDENCIES = {
    "scan": [],  # scan 没有前置依赖
    "lib_replace": ["scan"],  # lib-replace 需要 scan 完成
    "prepare": ["scan"],  # prepare 需要 scan 完成（可选：lib_replace）
    "transpile": ["scan", "prepare"],  # transpile 需要 scan 和 prepare 完成
    "optimize": ["transpile"],  # optimize 需要 transpile 完成
}


def _check_prerequisites(stage: str, interactive: bool = False) -> bool:
    """
    检查指定阶段的前置依赖是否已完成。
    
    Args:
        stage: 要检查的阶段名称
        interactive: 是否在交互模式下询问用户是否继续
    
    Returns:
        True 如果前置依赖已满足，False 如果未满足且用户选择不继续
    """
    if stage not in STAGE_DEPENDENCIES:
        return True  # 未知阶段，不检查
    
    dependencies = STAGE_DEPENDENCIES[stage]
    if not dependencies:
        return True  # 没有前置依赖
    
    state = _load_run_state()
    missing = []
    
    for dep in dependencies:
        if not state.get(dep, {}).get("completed", False):
            missing.append(dep)
    
    if not missing:
        return True  # 所有前置依赖都已完成
    
    # 前置依赖未完成
    dep_names = {
        "scan": "扫描",
        "lib_replace": "库替代评估",
        "prepare": "模块规划",
        "transpile": "代码转译",
        "optimize": "代码优化",
    }
    missing_names = [dep_names.get(d, d) for d in missing]
    stage_name = dep_names.get(stage, stage)
    
    typer.secho(
        f"[c2rust-{stage}] 警告：前置阶段未完成: {', '.join(missing_names)}",
        fg=typer.colors.YELLOW,
        err=True,
    )
    typer.secho(
        f"[c2rust-{stage}] 执行 {stage_name} 前需要先完成这些阶段",
        fg=typer.colors.YELLOW,
        err=True,
    )
    
    if interactive:
        # 交互模式下询问用户是否继续
        try:
            response = typer.prompt(
                "是否仍要继续执行？(y/N)",
                default="N",
                type=str,
            )
            if response.lower() in ["y", "yes"]:
                typer.secho(
                    f"[c2rust-{stage}] 用户选择继续执行，但可能遇到错误",
                    fg=typer.colors.YELLOW,
                )
                return True
            else:
                typer.secho(f"[c2rust-{stage}] 已取消执行", fg=typer.colors.RED)
                return False
        except Exception:
            return False
    else:
        # 非交互模式下直接提示并退出
        typer.secho(
            f"[c2rust-{stage}] 请先完成前置阶段，或使用 --interactive 参数在交互模式下继续",
            fg=typer.colors.RED,
            err=True,
        )
        return False


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
    try:
        _run_scan(
            dot=dot,
            only_dot=only_dot,
            subgraphs_dir=subgraphs_dir,
            only_subgraphs=only_subgraphs,
            png=True,
            non_interactive=True,
        )
        # 只有在真正执行扫描（而非仅生成 DOT）时才记录状态
        if not only_dot and not only_subgraphs:
            _save_run_state("scan", completed=True)
    except Exception as e:
        typer.secho(f"[c2rust-scan] 错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command("prepare")
def prepare(
    llm_group: Optional[str] = typer.Option(
        None, "-g", "--llm-group", help="指定用于规划的 LLM 模型组（仅影响本次运行）"
    ),
    interactive: bool = typer.Option(
        False,
        "--interactive",
        help="启用交互模式（默认非交互模式）",
    ),
) -> None:
    """
    使用 LLM Agent 基于根函数子图规划 Rust crate 模块结构并直接应用到磁盘。
    需先执行: jarvis-c2rust scan 以生成数据文件（symbols.jsonl）
    默认使用当前目录作为项目根，并从 <root>/.jarvis/c2rust/symbols.jsonl 读取数据
    """
    # 检查前置依赖
    if not _check_prerequisites("prepare", interactive=interactive):
        raise typer.Exit(code=1)
    
    try:
        _execute_llm_plan(apply=True, llm_group=llm_group, non_interactive=not interactive)
        _save_run_state("prepare", completed=True)
    except Exception as e:
        typer.secho(f"[c2rust-llm-planner] 错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command("transpile")
def transpile(
    llm_group: Optional[str] = typer.Option(
        None, "-g", "--llm-group", help="指定用于翻译的 LLM 模型组"
    ),
    max_retries: int = typer.Option(
        0, "-m", "--max-retries", help="构建/修复与审查的最大重试次数（0 表示不限制）"
    ),
    interactive: bool = typer.Option(
        False,
        "--interactive",
        help="启用交互模式（默认非交互模式）",
    ),
) -> None:
    """
    使用转译器按扫描顺序逐个函数转译并构建修复。
    需先执行: jarvis-c2rust scan 以生成数据文件（symbols.jsonl 与 translation_order.jsonl）
    默认使用当前目录作为项目根，并从 <root>/.jarvis/c2rust/symbols.jsonl 读取数据。
    未指定目标 crate 时，使用默认 <cwd>/<cwd.name>_rs。

    注意: disabled_libraries、root_symbols 等配置参数会从配置文件（.jarvis/c2rust/config.json）中自动恢复，
    这些参数应该在前面的流程（如 run 或 lib-replace）中设置。
    如果配置文件不存在，系统会自动从 progress.json 迁移配置（向后兼容）。
    断点续跑功能默认始终启用。

    选项:
    - --max-retries/-m: 构建/修复与审查的最大重试次数（0 表示不限制）
    - --llm-group/-g: 指定用于翻译的 LLM 模型组
    """
    # 检查前置依赖
    if not _check_prerequisites("transpile", interactive=interactive):
        raise typer.Exit(code=1)
    
    try:
        # Lazy import to avoid hard dependency if not used
        from jarvis.jarvis_c2rust.transpiler import run_transpile as _run_transpile
        # disabled_libraries、root_symbols 从配置文件恢复，不通过命令行参数传入
        # 断点续跑功能默认始终启用
        _run_transpile(
            project_root=Path("."),
            crate_dir=None,
            llm_group=llm_group,
            max_retries=max_retries,
            disabled_libraries=None,  # 从配置文件恢复
            root_symbols=None,  # 从配置文件恢复
            non_interactive=not interactive,
        )
        _save_run_state("transpile", completed=True)
    except Exception as e:
        typer.secho(f"[c2rust-transpiler] 错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command("lib-replace")
def lib_replace(
    llm_group: Optional[str] = typer.Option(
        None, "-g", "--llm-group", help="用于评估的 LLM 模型组"
    ),
    interactive: bool = typer.Option(
        False,
        "--interactive",
        help="启用交互模式（默认非交互模式）",
    ),
) -> None:
    """
    Root-list 评估模式（必须走 LLM 评估）：
    - 从配置文件（.jarvis/c2rust/config.json）读取根符号列表和禁用库列表
    - 仅对配置中的根符号作为评估根执行 LLM 子树评估
    - 若可替代：替换该根的 ref 为库占位，并剪除其所有子孙函数（根本身保留）
    - 需先执行: jarvis-c2rust scan 以生成数据文件（symbols.jsonl）
    - 默认库: std（仅用于对后续流程保持一致的默认上下文）
    - 使用 jarvis-c2rust config 命令设置根符号列表和禁用库列表
    """
    # 检查前置依赖
    if not _check_prerequisites("lib_replace", interactive=interactive):
        raise typer.Exit(code=1)
    
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

        # 从配置文件读取根列表和禁用库列表
        config = _load_config()
        root_names = config.get("root_symbols", [])
        disabled_list = config.get("disabled_libraries", [])
        
        if root_names:
            typer.secho(f"[c2rust-lib-replace] 从配置文件读取根符号: {len(root_names)} 个", fg=typer.colors.BLUE)
        else:
            typer.secho("[c2rust-lib-replace] 警告：配置文件中未设置根符号列表，将使用自动检测的根集合", fg=typer.colors.YELLOW)
        
        if disabled_list:
            typer.secho(f"[c2rust-lib-replace] 从配置文件读取禁用库: {', '.join(disabled_list)}", fg=typer.colors.BLUE)
        
        # 去重根符号列表
        if root_names:
            try:
                root_names = list(dict.fromkeys(root_names))
            except Exception:
                root_names = sorted(list(set(root_names)))
            # 排除 main
            root_names = [s for s in root_names if s.lower() != "main"]
        
        # 如果根列表为空，使用 None 表示自动检测
        candidates_list: Optional[List[str]] = root_names if root_names else None
        
        # 禁用库列表
        disabled_libraries_list: Optional[List[str]] = disabled_list if disabled_list else None

        # 必须走 LLM 评估：仅评估提供的根（candidates），不启用强制剪枝模式
        ret = _apply_library_replacement(
            db_path=Path("."),
            library_name=library,
            llm_group=llm_group,
            candidates=candidates_list,  # None 表示自动检测全部根
            out_symbols_path=None,
            out_mapping_path=None,
            max_funcs=None,
            disabled_libraries=disabled_libraries_list,
            non_interactive=not interactive,
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
        _save_run_state("lib_replace", completed=True)
    except Exception as e:
        typer.secho(f"[c2rust-lib-replace] 错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)



@app.command("config")
def config(
    files: Optional[List[Path]] = typer.Option(
        None, "--files", help="头文件（.h/.hh/.hpp/.hxx）或函数名列表文件（每行一个函数名，忽略空行与以#开头的注释）"
    ),
    root_list_syms: Optional[str] = typer.Option(
        None, "--root-list-syms", help="根符号列表内联（逗号分隔）"
    ),
    disabled_libs: Optional[str] = typer.Option(
        None, "--disabled-libs", help="禁用库列表（逗号分隔）"
    ),
    show: bool = typer.Option(
        False, "--show", help="显示当前配置内容"
    ),
    clear: bool = typer.Option(
        False, "--clear", help="清空配置（重置为默认值）"
    ),
) -> None:
    """
    管理转译配置文件（.jarvis/c2rust/config.json）。
    
    可以设置根符号列表（root_symbols）和禁用库列表（disabled_libraries）。
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
      
      # 同时设置多个参数
      jarvis-c2rust config --files bzlib.h --disabled-libs "libc"
      
      # 查看当前配置
      jarvis-c2rust config --show
      
      # 清空配置
      jarvis-c2rust config --clear
    """
    import json
    from jarvis.jarvis_c2rust.transpiler import CONFIG_JSON, C2RUST_DIRNAME
    
    data_dir = Path(".") / C2RUST_DIRNAME
    config_path = data_dir / CONFIG_JSON
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # 读取现有配置
    default_config = {"root_symbols": [], "disabled_libraries": []}
    current_config = default_config.copy()
    
    if config_path.exists():
        try:
            with config_path.open("r", encoding="utf-8") as f:
                current_config = json.load(f)
                if not isinstance(current_config, dict):
                    current_config = default_config.copy()
        except Exception as e:
            typer.secho(f"[c2rust-config] 读取现有配置失败: {e}，将使用默认值", fg=typer.colors.YELLOW)
            current_config = default_config.copy()
    
    # 如果只是查看配置
    if show:
        typer.secho(f"[c2rust-config] 当前配置文件: {config_path}", fg=typer.colors.BLUE)
        typer.secho(json.dumps(current_config, ensure_ascii=False, indent=2), fg=typer.colors.CYAN)
        return
    
    # 如果清空配置
    if clear:
        current_config = default_config.copy()
        with config_path.open("w", encoding="utf-8") as f:
            json.dump(current_config, f, ensure_ascii=False, indent=2)
        typer.secho(f"[c2rust-config] 配置已清空: {config_path}", fg=typer.colors.GREEN)
        return
    
    # 读取根符号列表
    root_symbols: List[str] = []
    header_exts = {".h", ".hh", ".hpp", ".hxx"}
    
    if files:
        for file_path in files:
            try:
                file_path = Path(file_path).resolve()
                if not file_path.exists():
                    typer.secho(f"[c2rust-config] 警告: 文件不存在，跳过: {file_path}", fg=typer.colors.YELLOW)
                    continue
                
                # 检查是否是头文件
                if file_path.suffix.lower() in header_exts:
                    # 从头文件提取函数名
                    typer.secho(f"[c2rust-config] 从头文件提取函数名: {file_path}", fg=typer.colors.BLUE)
                    try:
                        from jarvis.jarvis_c2rust.collector import collect_function_names as _collect_fn_names
                        # 使用临时文件存储提取的函数名
                        import tempfile
                        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as tmp:
                            tmp_path = Path(tmp.name)
                        _collect_fn_names(files=[file_path], out_path=tmp_path, compile_commands_root=None)
                        # 读取提取的函数名
                        txt = tmp_path.read_text(encoding="utf-8")
                        collected = [ln.strip() for ln in txt.splitlines() if ln.strip()]
                        root_symbols.extend(collected)
                        typer.secho(f"[c2rust-config] 从头文件 {file_path.name} 提取了 {len(collected)} 个函数名", fg=typer.colors.GREEN)
                        # 清理临时文件
                        try:
                            tmp_path.unlink()
                        except Exception:
                            pass
                    except Exception as e:
                        typer.secho(f"[c2rust-config] 从头文件提取函数名失败: {file_path}: {e}", fg=typer.colors.RED, err=True)
                        raise typer.Exit(code=1)
                else:
                    # 读取函数名列表文件（每行一个函数名）
                    txt = file_path.read_text(encoding="utf-8")
                    collected = [ln.strip() for ln in txt.splitlines() if ln.strip() and not ln.strip().startswith("#")]
                    root_symbols.extend(collected)
                    typer.secho(f"[c2rust-config] 从文件 {file_path.name} 读取了 {len(collected)} 个根符号", fg=typer.colors.BLUE)
            except typer.Exit:
                raise
            except Exception as e:
                typer.secho(f"[c2rust-config] 处理文件失败: {file_path}: {e}", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1)
    
    if isinstance(root_list_syms, str) and root_list_syms.strip():
        parts = [s.strip() for s in root_list_syms.replace("\n", ",").split(",") if s.strip()]
        root_symbols.extend(parts)
        typer.secho(f"[c2rust-config] 从命令行读取根符号: {len(parts)} 个", fg=typer.colors.BLUE)
    
    # 去重根符号列表
    if root_symbols:
        try:
            root_symbols = list(dict.fromkeys(root_symbols))
        except Exception:
            root_symbols = sorted(list(set(root_symbols)))
        # 排除 main
        root_symbols = [s for s in root_symbols if s.lower() != "main"]
        current_config["root_symbols"] = root_symbols
        typer.secho(f"[c2rust-config] 已设置根符号列表: {len(root_symbols)} 个", fg=typer.colors.GREEN)
    
    # 读取禁用库列表
    if isinstance(disabled_libs, str) and disabled_libs.strip():
        disabled_list = [s.strip() for s in disabled_libs.replace("\n", ",").split(",") if s.strip()]
        if disabled_list:
            current_config["disabled_libraries"] = disabled_list
            typer.secho(f"[c2rust-config] 已设置禁用库列表: {', '.join(disabled_list)}", fg=typer.colors.GREEN)
    
    # 如果没有提供任何参数，提示用户
    if not files and not root_list_syms and not disabled_libs:
        typer.secho("[c2rust-config] 未提供任何参数，使用 --show 查看当前配置，或使用 --help 查看帮助", fg=typer.colors.YELLOW)
        return
    
    # 保存配置
    try:
        with config_path.open("w", encoding="utf-8") as f:
            json.dump(current_config, f, ensure_ascii=False, indent=2)
        typer.secho(f"[c2rust-config] 配置已保存: {config_path}", fg=typer.colors.GREEN)
        typer.secho(json.dumps(current_config, ensure_ascii=False, indent=2), fg=typer.colors.CYAN)
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
        0, "-m", "--max-retries", help="transpile 构建/修复与审查的最大重试次数（0 表示不限制）"
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

    补充:

    - 如需精细化控制，可独立调用子命令：scan、lib-replace、prepare、transpile、optimize
    """
    
    try:
        # 加载状态文件
        if reset:
            # 重置状态
            state_path = _get_run_state_path()
            if state_path.exists():
                state_path.unlink()
                typer.secho("[c2rust-run] 已重置状态，将从头开始执行", fg=typer.colors.YELLOW)
            state = _load_run_state()
        else:
            state = _load_run_state()
            # 显示当前状态
            completed_stages = [s for s, info in state.items() if info.get("completed", False)]
            if completed_stages:
                typer.secho(f"[c2rust-run] 检测到已完成阶段: {', '.join(completed_stages)}，将从断点继续", fg=typer.colors.CYAN)
        
        # Step 1: scan
        if not state.get("scan", {}).get("completed", False):
            typer.secho("[c2rust-run] scan: 开始", fg=typer.colors.BLUE)
            _run_scan(dot=None, only_dot=False, subgraphs_dir=None, only_subgraphs=False, png=False, non_interactive=True)
            typer.secho("[c2rust-run] scan: 完成", fg=typer.colors.GREEN)
            # 状态由 scan 命令自己记录
        else:
            typer.secho("[c2rust-run] scan: 已完成，跳过", fg=typer.colors.CYAN)

        # Step 2: lib-replace（从配置文件读取根列表和禁用库列表）
        if not state.get("lib_replace", {}).get("completed", False):
            # 从配置文件读取基础配置
            config = _load_config()
            root_names: List[str] = list(config.get("root_symbols", []))
            disabled_list: Optional[List[str]] = config.get("disabled_libraries", []) or None
            
            # 去重并校验（允许为空时回退为自动根集）
            if root_names:
                try:
                    root_names = list(dict.fromkeys(root_names))
                except Exception:
                    root_names = sorted(list(set(root_names)))
                # 排除 main
                root_names = [s for s in root_names if s.lower() != "main"]
            
            candidates_list: Optional[List[str]] = root_names if root_names else None
            if not candidates_list:
                typer.secho("[c2rust-run] lib-replace: 根列表为空，将回退为自动检测的根集合（基于扫描结果）", fg=typer.colors.YELLOW)
            
            if disabled_list:
                typer.secho(f"[c2rust-run] lib-replace: 从配置文件读取禁用库: {', '.join(disabled_list)}", fg=typer.colors.BLUE)

            # 执行 lib-replace（默认库 std）
            library = "std"
            root_count_str = str(len(candidates_list)) if candidates_list is not None else "auto"
            typer.secho(f"[c2rust-run] lib-replace: 开始（库: {library}，根数: {root_count_str}）", fg=typer.colors.BLUE)
            ret = _apply_library_replacement(
                db_path=Path("."),
                library_name=library,
                llm_group=llm_group,
                candidates=candidates_list,   # None 表示自动检测全部根
                out_symbols_path=None,
                out_mapping_path=None,
                max_funcs=None,
                disabled_libraries=disabled_list,
                non_interactive=not interactive,
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
            # 状态由 lib-replace 命令自己记录
        else:
            typer.secho("[c2rust-run] lib-replace: 已完成，跳过", fg=typer.colors.CYAN)

        # Step 3: prepare
        if not state.get("prepare", {}).get("completed", False):
            typer.secho("[c2rust-run] prepare: 开始", fg=typer.colors.BLUE)
            _execute_llm_plan(apply=True, llm_group=llm_group, non_interactive=not interactive)
            typer.secho("[c2rust-run] prepare: 完成", fg=typer.colors.GREEN)
            # 状态由 prepare 命令自己记录
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
            # 状态由 transpile 命令自己记录
        else:
            typer.secho("[c2rust-run] transpile: 已完成，跳过", fg=typer.colors.CYAN)

        # Step 5: optimize
        if not state.get("optimize", {}).get("completed", False):
            try:
                typer.secho("[c2rust-run] optimize: 开始", fg=typer.colors.BLUE)
                from jarvis.jarvis_c2rust.optimizer import optimize_project as _optimize_project
                res = _optimize_project(crate_dir=None, llm_group=llm_group, non_interactive=not interactive)
                summary = (
                    f"[c2rust-run] optimize: 结果摘要:\n"
                    f"  files_scanned: {res.get('files_scanned')}\n"
                    f"  unsafe_removed: {res.get('unsafe_removed')}\n"
                    f"  unsafe_annotated: {res.get('unsafe_annotated')}\n"
                    f"  duplicates_tagged: {res.get('duplicates_tagged')}\n"
                    f"  visibility_downgraded: {res.get('visibility_downgraded')}\n"
                    f"  docs_added: {res.get('docs_added')}\n"
                    f"  cargo_checks: {res.get('cargo_checks')}\n"
                )
                typer.secho(summary, fg=typer.colors.GREEN)
                typer.secho("[c2rust-run] optimize: 完成", fg=typer.colors.GREEN)
                # 状态由 optimize 命令自己记录
            except Exception as _e:
                typer.secho(f"[c2rust-run] optimize: 错误: {_e}", fg=typer.colors.RED, err=True)
                raise
        else:
            typer.secho("[c2rust-run] optimize: 已完成，跳过", fg=typer.colors.CYAN)
        
        # 所有阶段完成
        typer.secho("[c2rust-run] 所有阶段已完成！", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"[c2rust-run] 错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command("optimize")
def optimize(
    crate_dir: Optional[Path] = typer.Option(
        None, "--crate-dir", help="Rust crate 根目录（包含 Cargo.toml）；未提供时自动检测"
    ),
    llm_group: Optional[str] = typer.Option(
        None,
        "-g",
        "--llm-group",
        help="用于 CodeAgent 修复与整体优化的 LLM 模型组",
    ),
    enable_unsafe_cleanup: bool = typer.Option(
        True, "--unsafe/--no-unsafe", help="启用 unsafe 清理"
    ),
    enable_structure_opt: bool = typer.Option(
        True, "--structure/--no-structure", help="启用代码结构优化（重复代码标注）"
    ),
    enable_visibility_opt: bool = typer.Option(
        True, "--visibility/--no-visibility", help="启用可见性优化（尽可能最小可见性）"
    ),
    enable_doc_opt: bool = typer.Option(
        True, "--doc/--no-doc", help="启用文档补充（模块/函数占位文档）"
    ),
    max_checks: int = typer.Option(
        0, "-m", "--max-checks", help="cargo check 最大次数限制（0 表示不限）"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="仅统计潜在修改，不写回文件"
    ),
    include_patterns: Optional[str] = typer.Option(
        None,
        "--include",
        help="仅处理匹配的文件（逗号分隔 glob，相对 crate 根，如: src/**/*.rs,src/foo/*.rs）",
    ),
    exclude_patterns: Optional[str] = typer.Option(
        None,
        "--exclude",
        help="排除匹配的文件（逗号分隔 glob，相对 crate 根）",
    ),
    max_files: int = typer.Option(
        0,
        "-n",
        "--max-files",
        help="本次最多处理的文件数（0 表示不限，用于大项目分批优化）",
    ),
    resume: bool = typer.Option(
        True,
        "--resume/--no-resume",
        help="是否启用断点续跑，跳过已处理文件（默认启用）",
    ),
    reset_progress: bool = typer.Option(
        False,
        "--reset-progress",
        help="重置优化进度（清空已处理文件记录）后再执行",
    ),
    build_fix_retries: int = typer.Option(
        3,
        "-r",
        "--build-fix-retries",
        help="构建失败后的最小修复重试次数（使用 CodeAgent 迭代修复）",
    ),
    git_guard: bool = typer.Option(
        True,
        "--git-guard/--no-git-guard",
        help="启用Git保护：每一步优化前记录当前HEAD，修复耗尽时自动git reset --hard回快照（默认启用）",
    ),
    interactive: bool = typer.Option(
        False,
        "--interactive",
        help="启用交互模式（默认非交互模式）",
    ),

) -> None:
    """
    对生成的 Rust 代码执行保守优化（unsafe 清理、结构优化、可见性优化、文档补充）。
    建议在转译完成后执行：jarvis-c2rust optimize
    """
    # 检查前置依赖
    if not _check_prerequisites("optimize", interactive=interactive):
        raise typer.Exit(code=1)
    
    try:
        from jarvis.jarvis_c2rust.optimizer import optimize_project as _optimize_project

        typer.secho("[c2rust-optimize] 开始", fg=typer.colors.BLUE)
        res = _optimize_project(
            crate_dir=crate_dir,
            enable_unsafe_cleanup=enable_unsafe_cleanup,
            enable_structure_opt=enable_structure_opt,
            enable_visibility_opt=enable_visibility_opt,
            enable_doc_opt=enable_doc_opt,
            max_checks=max_checks,
            dry_run=dry_run,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            max_files=max_files,
            resume=resume,
            reset_progress=reset_progress,
            build_fix_retries=build_fix_retries,
            git_guard=git_guard,
            llm_group=llm_group,
            non_interactive=not interactive,
        )
        # 摘要输出
        summary = (
            f"[c2rust-optimize] 结果摘要:\n"
            f"  files_scanned: {res.get('files_scanned')}\n"
            f"  unsafe_removed: {res.get('unsafe_removed')}\n"
            f"  unsafe_annotated: {res.get('unsafe_annotated')}\n"
            f"  duplicates_tagged: {res.get('duplicates_tagged')}\n"
            f"  visibility_downgraded: {res.get('visibility_downgraded')}\n"
            f"  docs_added: {res.get('docs_added')}\n"
            f"  cargo_checks: {res.get('cargo_checks')}\n"
        )
        typer.secho(summary, fg=typer.colors.GREEN)
        _save_run_state("optimize", completed=True)
    except Exception as e:
        typer.secho(f"[c2rust-optimize] 错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

def main() -> None:
    """主入口"""
    app()


if __name__ == "__main__":
    main()