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
from jarvis.jarvis_utils.utils import init_env
from jarvis.jarvis_c2rust.llm_module_agent import (
    plan_crate_yaml_llm as _plan_crate_yaml_llm,
    apply_project_structure_from_yaml as _apply_project_structure_from_yaml,
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
) -> None:
    """
    使用 LLM Agent 基于根函数子图规划 Rust crate 模块结构，输出 YAML
    需先执行: jarvis-c2rust scan 以生成数据库
    默认使用当前目录作为项目根，并从 <root>/.jarvis/c2rust/functions.db 读取数据库
    """
    try:
        entries = _plan_crate_yaml_llm()
        # 将对象 entries 序列化为 YAML 文本（目录使用 'name/:' 形式，文件为字符串）
        def _entries_to_yaml(items, indent=0):
            lines = []
            for it in (items or []):
                if isinstance(it, str):
                    lines.append("  " * indent + f"- {it}")
                elif isinstance(it, dict) and len(it) == 1:
                    name, children = next(iter(it.items()))
                    name = str(name).rstrip("/")
                    lines.append("  " * indent + f"- {name}/:")
                    lines.extend(_entries_to_yaml(children or [], indent + 1))
            return lines
        yaml_text = "\n".join(_entries_to_yaml(entries))
        if apply:
            target_root = crate_name if crate_name else "."
            _apply_project_structure_from_yaml(yaml_text, project_root=target_root)
            typer.secho("[c2rust-llm-planner] Project structure applied.", fg=typer.colors.GREEN)

            # Post-apply: inspect actual structure and configure Cargo.toml via CodeAgent
            from jarvis.jarvis_code_agent.code_agent import CodeAgent  # local import to avoid global coupling
            import os

            # Resolve the created crate directory path (align with apply logic)
            try:
                cwd = Path(".").resolve()
                created_dir = (cwd / f"{cwd.name}-rs") if (target_root == ".") else Path(target_root).resolve()
            except Exception:
                created_dir = Path(target_root)

            # Commit once after creating directory structure
            import subprocess
            prev_cwd_commit = os.getcwd()
            try:
                os.chdir(str(created_dir))
                # ensure git repo
                res = subprocess.run(
                    ["git", "rev-parse", "--git-dir"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if res.returncode != 0:
                    init_res = subprocess.run(
                        ["git", "init"],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if init_res.returncode == 0:
                        typer.secho("[c2rust-llm-planner] Initialized git repository in crate directory.", fg=typer.colors.YELLOW)
                # add and commit
                subprocess.run(["git", "add", "."], check=False)
                commit_res = subprocess.run(
                    ["git", "commit", "-m", "[c2rust-llm-planner] Initialize crate structure"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if commit_res.returncode == 0:
                    typer.secho("[c2rust-llm-planner] Initial structure committed.", fg=typer.colors.GREEN)
                else:
                    # 常见原因：无变更、未配置 user.name/email 等
                    typer.secho("[c2rust-llm-planner] Initial commit skipped or failed (no changes or git config missing).", fg=typer.colors.YELLOW)
            finally:
                os.chdir(prev_cwd_commit)

            # Build a concise directory structure context
            def _format_tree(root: Path) -> str:
                lines = []
                exclude = {".git", "target", ".jarvis"}
                if not root.exists():
                    return ""
                for p in sorted(root.rglob("*")):
                    if any(part in exclude for part in p.parts):
                        continue
                    rel = p.relative_to(root)
                    depth = len(rel.parts) - 1
                    indent = "  " * depth
                    name = rel.name + ("/" if p.is_dir() else "")
                    lines.append(f"{indent}- {name}")
                return "\n".join(lines)

            dir_ctx = _format_tree(created_dir)
            crate_pkg_name = created_dir.name

            # Detect lib/bin entry files
            lib_exists = (created_dir / "src" / "lib.rs").exists()
            cli_main_path = created_dir / "src" / "cli" / "main.rs"
            root_main_path = created_dir / "src" / "main.rs"
            bin_path = ""
            if cli_main_path.exists():
                bin_path = "src/cli/main.rs"
            elif root_main_path.exists():
                bin_path = "src/main.rs"

            # Prepare CodeAgent requirement
            requirement_lines = [
                "请在该crate目录下编辑 Cargo.toml，配置入口并限制Rust版本：",
                f"- crate_dir: {created_dir}",
                f"- crate_name: {crate_pkg_name}",
                "目录结构（部分）：",
                dir_ctx,
                "",
                "修改要求：",
                '- 在 [package] 中将 edition 设置为 "2024"（如已存在则覆盖）。',
            ]
            if lib_exists:
                requirement_lines.append('- 添加或更新 [lib]：path = "src/lib.rs"。')
            if bin_path:
                requirement_lines.append(f'- 添加或更新 [[bin]]：name = "{crate_pkg_name}", path = "{bin_path}"。')
            requirement_lines.extend([
                "- 保留其他已有字段与依赖不变。",
                "- 仅修改 Cargo.toml 一个文件并提交补丁。",
            ])
            requirement_text = "\n".join(requirement_lines)

            prev_cwd = os.getcwd()
            try:
                os.chdir(str(created_dir))
                agent = CodeAgent(need_summary=False, non_interactive=False, plan=False)
                agent.run(requirement_text, prefix="[c2rust-llm-planner]", suffix="")
                typer.secho("[c2rust-llm-planner] Cargo.toml updated by CodeAgent.", fg=typer.colors.GREEN)
            finally:
                os.chdir(prev_cwd)
        if out is None:
            typer.echo(yaml_text)
        else:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(yaml_text, encoding="utf-8")
            typer.secho(f"[c2rust-llm-planner] YAML written: {out}", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"[c2rust-llm-planner] Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

def main() -> None:
    """主入口"""
    app()


if __name__ == "__main__":
    main()