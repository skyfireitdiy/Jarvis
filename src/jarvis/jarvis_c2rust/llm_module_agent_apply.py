# -*- coding: utf-8 -*-
"""LLM 模块规划 Agent 的项目结构应用模块。"""

import re
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Set
from typing import Union

from jarvis.jarvis_c2rust.llm_module_agent_utils import parse_project_json_entries


def ensure_pub_mod_declarations(existing_text: str, child_mods: List[str]) -> str:
    """
    在给定文本中确保存在并升级子模块声明为 `pub mod <name>;`：
    - 解析已有的 `mod`/`pub mod`/`pub(...) mod` 声明；
    - 已存在但非 pub 的同名声明就地升级为 `pub mod`，保留原行的缩进；
    - 不存在的模块名则在末尾追加一行 `pub mod <name>;`；
    - 返回更新后的完整文本（保留结尾换行）。
    """
    try:
        lines = (existing_text or "").splitlines()
    except Exception:
        lines = []
    mod_decl_pattern = re.compile(
        r"^\s*(pub(?:\s*\([^)]+\))?\s+)?mod\s+([A-Za-z_][A-Za-z0-9_]*)\s*;\s*$"
    )
    name_to_indices: Dict[str, List[int]] = {}
    name_has_pub: Set[str] = set()
    for i, ln in enumerate(lines):
        m = mod_decl_pattern.match(ln.strip())
        if not m:
            continue
        mod_name = m.group(2)
        name_to_indices.setdefault(mod_name, []).append(i)
        if m.group(1):
            name_has_pub.add(mod_name)
    for mod_name in sorted(set(child_mods or [])):
        if mod_name in name_to_indices:
            if mod_name not in name_has_pub:
                for idx in name_to_indices[mod_name]:
                    ws_match = re.match(r"^(\s*)", lines[idx])
                    leading_ws = ws_match.group(1) if ws_match else ""
                    lines[idx] = f"{leading_ws}pub mod {mod_name};"
        else:
            lines.append(f"pub mod {mod_name};")
    return "\n".join(lines).rstrip() + ("\n" if lines else "")


def apply_entries_with_mods(entries: List[Any], base_path: Path) -> None:
    """
    根据解析出的 entries 创建目录与文件结构（不在此阶段写入/更新任何 Rust 源文件内容）：
    - 对于目录项：创建目录，并递归创建其子项；
    - 对于文件项：若不存在则创建空文件；
    约束与约定：
    - crate 根的 src 目录：不生成 src/mod.rs，也不写入 src/lib.rs 的模块声明；
    - 非 src 目录：不创建或更新 mod.rs；如需创建 mod.rs，请在 YAML 中显式列出；
    - 模块声明的补齐将在后续 CodeAgent 阶段完成（扫描目录结构并最小化补齐 pub mod 声明）。
    """

    def apply_item(item: Any, dir_path: Path) -> None:
        if isinstance(item, str):
            # 文件
            file_path = dir_path / item
            file_path.parent.mkdir(parents=True, exist_ok=True)
            if not file_path.exists():
                try:
                    file_path.touch(exist_ok=True)
                except Exception:
                    pass
            return

        if isinstance(item, dict) and len(item) == 1:
            dir_name, children = next(iter(item.items()))
            name = str(dir_name).rstrip("/").strip()
            new_dir = dir_path / name
            new_dir.mkdir(parents=True, exist_ok=True)

            child_mods: List[str] = []
            # 是否为 crate 根下的 src 目录
            is_src_root_dir = new_dir == base_path / "src"

            # 先创建子项
            for child in children or []:
                if isinstance(child, str):
                    apply_item(child, new_dir)
                    # 收集 .rs 文件作为子模块
                    if child.endswith(".rs") and child != "mod.rs":
                        stem = Path(child).stem
                        # 在 src 根目录下，忽略 lib.rs 与 main.rs 的自引用
                        if is_src_root_dir and stem in ("lib", "main"):
                            pass
                        else:
                            child_mods.append(stem)
                    if child == "mod.rs":
                        pass
                elif isinstance(child, dict):
                    # 子目录
                    sub_name = list(child.keys())[0]
                    sub_mod_name = str(sub_name).rstrip("/").strip()
                    child_mods.append(sub_mod_name)
                    apply_item(child, new_dir)

            # 对 crate 根的 src 目录，使用 lib.rs 聚合子模块，不创建/更新 src/mod.rs
            if is_src_root_dir:
                # 不在 src 根目录写入任何文件内容；仅由子项创建对应空文件（如有）
                return

            # 非 src 目录：
            # 为避免覆盖现有实现，当前阶段不创建或更新 mod.rs 内容。
            # 如需创建 mod.rs，应在 JSON 中显式指定为文件项；
            # 如需补齐模块声明，将由后续的 CodeAgent 阶段根据目录结构自动补齐。
            return

    for entry in entries:
        apply_item(entry, base_path)


def ensure_cargo_toml(base_dir: Path, package_name: str) -> None:
    """
    确保在 base_dir 下存在合理的 Cargo.toml：
    - 如果不存在，则创建最小可用的 Cargo.toml，并设置 package.name = package_name
    - 如果已存在，则不覆盖现有内容（避免误改）
    """
    cargo_path = base_dir / "Cargo.toml"
    if cargo_path.exists():
        return
    try:
        cargo_path.touch(exist_ok=True)
    except (OSError, PermissionError):
        # 如果无法创建文件，记录错误但不中断流程
        # 后续 CodeAgent 可能会处理 Cargo.toml 的创建
        pass


def apply_project_structure_from_json(
    json_text: str, project_root: Union[Path, str] = "."
) -> None:
    """
    基于 Agent 返回的 <PROJECT> 中的目录结构 JSON，创建实际目录与文件（不在此阶段写入或更新任何 Rust 源文件内容）。
    - project_root: 目标应用路径；当为 "."（默认）时，将使用"父目录/当前目录名_rs"作为crate根目录
    注意：模块声明（mod/pub mod）补齐将在后续的 CodeAgent 步骤中完成。按新策略不再创建或更新 workspace（构建直接在 crate 目录内进行）。
    """
    entries, parse_error = parse_project_json_entries(json_text)
    if parse_error:
        raise ValueError(f"JSON解析失败: {parse_error}")
    if not entries:
        # 严格模式：解析失败直接报错并退出，由上层 CLI 捕获打印错误
        raise ValueError("[c2rust-llm-planner] 从LLM输出解析目录结构失败。正在中止。")
    requested_root = Path(project_root).resolve()
    try:
        cwd = Path(".").resolve()
        if requested_root == cwd:
            # 默认crate不能设置为 .，设置为 父目录/当前目录名_rs（与当前目录同级）
            base_dir = cwd.parent / f"{cwd.name}_rs"
        else:
            base_dir = requested_root
    except Exception:
        base_dir = requested_root
    base_dir.mkdir(parents=True, exist_ok=True)
    # crate name 与目录名保持一致（用于 Cargo 包名，允许连字符）
    crate_pkg_name = base_dir.name
    apply_entries_with_mods(entries, base_dir)
    # 确保 Cargo.toml 存在并设置包名
    ensure_cargo_toml(base_dir, crate_pkg_name)

    # 已弃用：不再将 crate 添加到 workspace（按新策略去除 workspace）
    # 构建与工具运行将直接在 crate 目录内进行
