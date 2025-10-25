# -*- coding: utf-8 -*-
"""
C/C++ 头文件函数名收集器（基于 libclang）。

功能:
- 接受一个或多个头文件路径（.h/.hh/.hpp/.hxx），使用 libclang 精确解析，收集这些头文件中声明或定义的函数名。
- 优先输出限定名（qualified_name），回退到普通名称（name）。
- 自动逐层向上查找 compile_commands.json（直到文件系统根目录）；若未找到则跳过并使用基础 -I 参数；失败时回退为空参数。
- 自动为头文件设置语言选项 (-x c-header 或 -x c++-header)，提升解析成功率。

输出:
- 将唯一的函数名集合写入指定输出文件（每行一个函数名，UTF-8 编码）。

与现有实现的关系:
- 复用 jarvis.jarvis_c2rust.scanner 中的能力：
  - _try_import_libclang: 兼容多版本 libclang 的加载器
  - find_compile_commands / load_compile_commands: compile_commands.json 解析与逐层向上搜索
  - get_qualified_name / is_function_like: 统一限定名生成和函数节点类型判断
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Set

# 复用 scanner 内的核心能力
from jarvis.jarvis_c2rust.scanner import (  # type: ignore
    _try_import_libclang,
    find_compile_commands,
    load_compile_commands,
    get_qualified_name,
    is_function_like,
)


HEADER_EXTS = {".h", ".hh", ".hpp", ".hxx"}


def _resolve_compile_args_map(files: List[Path]) -> Dict[str, List[str]]:
    """
    逐文件尝试向上查找 compile_commands.json（直到根目录），并合并解析为:
      file_abs_path_str -> compile_args(list[str])
    若未找到任何 compile_commands.json，则返回空映射。
    """
    mapping: Dict[str, List[str]] = {}
    visited_cc_paths: Set[Path] = set()

    for f in files:
        try:
            cc_path = find_compile_commands(f.parent)
        except Exception:
            cc_path = None
        if cc_path and cc_path.exists() and cc_path not in visited_cc_paths:
            try:
                m = load_compile_commands(cc_path)
                if isinstance(m, dict):
                    mapping.update(m)
                visited_cc_paths.add(cc_path)
            except Exception:
                # ignore parse errors, continue searching next file's tree
                pass

    return mapping


def _ensure_lang_header_args(file_path: Path, base_args: List[str]) -> List[str]:
    """
    确保为头文件设置合适的语言选项：
    - C 头文件: -x c-header
    - C++ 头文件: -x c++-header
    若 base_args 已包含 -x，则尊重现有设置，不再强制覆盖。
    """
    args = list(base_args or [])
    has_x = any(a == "-x" or a.startswith("-x") for a in args)
    if has_x:
        return args
    ext = file_path.suffix.lower()
    if ext in {".hpp", ".hxx", ".hh"}:
        args.extend(["-x", "c++-header"])
    else:
        args.extend(["-x", "c-header"])
    return args


def _scan_header_for_names(cindex, file_path: Path, args: List[str]) -> List[str]:
    """
    扫描单个头文件，返回该文件中声明或定义的函数的限定名/名称列表。
    - 不要求 is_definition()，以捕获函数原型声明
    - 仅收集位于该文件本身的符号（根据 location.file 判断）
    """
    index = cindex.Index.create()
    tu = index.parse(
        str(file_path),
        args=args,
        options=0,
    )
    names: List[str] = []

    def visit(node):
        # 只收集属于当前文件的节点
        loc_file = node.location.file
        if loc_file is None or Path(loc_file.name).resolve() != file_path.resolve():
            for ch in node.get_children():
                visit(ch)
            return

        if is_function_like(node):
            try:
                qn = get_qualified_name(node)
                nm = node.spelling or ""
                label = (qn or nm or "").strip()
                if label:
                    names.append(label)
            except Exception:
                nm = (node.spelling or "").strip()
                if nm:
                    names.append(nm)

        for ch in node.get_children():
            visit(ch)

    visit(tu.cursor)
    return names


def collect_function_names(
    files: List[Path],
    out_path: Path,
) -> Path:
    """
    收集给定头文件中的函数名并写入指定文件。

    参数:
    - files: 一个或多个 C/C++ 头文件路径（.h/.hh/.hpp/.hxx）
    - out_path: 输出文件路径（将创建目录）

    返回:
    - 写入的输出文件路径
    """
    if not files:
        raise ValueError("必须至少提供一个头文件路径")

    # 归一化与存在性检查，仅保留头文件
    file_list: List[Path] = []
    for p in files:
        rp = Path(p).resolve()
        if not rp.exists():
            print(f"[c2rust-collector] 警告: 文件不存在，已跳过: {rp}")
            continue
        if not rp.is_file():
            print(f"[c2rust-collector] 警告: 非普通文件，已跳过: {rp}")
            continue
        if rp.suffix.lower() not in HEADER_EXTS:
            print(f"[c2rust-collector] 警告: 非头文件（仅支持 .h/.hh/.hpp/.hxx），已跳过: {rp}")
            continue
        file_list.append(rp)

    if not file_list:
        raise FileNotFoundError("提供的文件列表均不可用或不包含头文件（支持 .h/.hh/.hpp/.hxx）")

    # 准备 libclang
    cindex = _try_import_libclang()
    if cindex is None:
        # 与 scanner 的防御式处理保持一致：尽量不让 None 向下游传播
        from clang import cindex as _ci  # type: ignore
        cindex = _ci

    # 预检 Index 创建
    try:
        _ = cindex.Index.create()
    except Exception as e:
        raise RuntimeError(f"libclang 初始化失败: {e}")

    # 逐层向上自动查找 compile_commands.json，构建参数映射
    cc_args_map = _resolve_compile_args_map(file_list)

    # 收集唯一函数名（优先限定名）
    names: Set[str] = set()

    for f in file_list:
        # 优先使用 compile_commands 的精确参数；若无则提供基础 -I 与头文件语言选项
        base_args = cc_args_map.get(str(f), ["-I", str(f.parent)])
        args = _ensure_lang_header_args(f, base_args)
        try:
            fn_names = _scan_header_for_names(cindex, f, args)
        except Exception:
            # 回退到无参数解析（仍添加语言选项）
            try:
                fn_names = _scan_header_for_names(cindex, f, _ensure_lang_header_args(f, []))
            except Exception as e2:
                print(f"[c2rust-collector] 解析失败，已跳过 {f}: {e2}")
                continue

        for label in fn_names:
            if label:
                names.add(label.strip())

    # 写出结果
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with out_path.open("w", encoding="utf-8") as fo:
            for nm in sorted(names):
                fo.write(nm + "\n")
    except Exception as e:
        raise RuntimeError(f"写入输出文件失败: {out_path}: {e}")

    print(f"[c2rust-collector] 已收集到 {len(names)} 个函数名（来自头文件） -> {out_path}")
    return out_path