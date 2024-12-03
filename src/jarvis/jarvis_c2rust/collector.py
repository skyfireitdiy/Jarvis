# -*- coding: utf-8 -*-
"""
使用libclang收集头文件中函数名的轻量级工具。

用途:
- 给定一个或多个C/C++头文件(.h/.hh/.hpp/.hxx)，使用libclang解析每个文件并收集函数名
- 优先使用限定名称(qualified names)，否则回退到非限定名称
- 将唯一名称(去重并保留首次出现顺序)写入指定输出文件(每行一个)

设计:
- 复用扫描工具:
  - _try_import_libclang()
  - find_compile_commands()
  - load_compile_commands()
  - scan_file() (注意: scan_file只收集定义；内联头文件通常是定义)
- 如果存在compile_commands.json，使用其参数；否则回退到包含文件父目录的最小参数集
- 对于头文件解析，确保语言标志(-x c-header / -x c++-header)存在，如果参数中未指定

注意事项:
- 本模块注重正确性/鲁棒性而非性能
- 不尝试发现传递包含；仅通过添加-I <file.parent>来辅助解析器
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional
from typing import Any

from jarvis.jarvis_c2rust.constants import HEADER_EXTS
from jarvis.jarvis_c2rust.scanner import _try_import_libclang
from jarvis.jarvis_c2rust.scanner import find_compile_commands
from jarvis.jarvis_c2rust.scanner import load_compile_commands
from jarvis.jarvis_c2rust.scanner import scan_file


def _guess_lang_header_flag(file: Path) -> List[str]:
    """
    如果编译参数中未指定，则猜测头文件合适的-x语言标志
    """
    ext = file.suffix.lower()
    if ext in {".hh", ".hpp", ".hxx"}:
        return ["-x", "c++-header"]
    # 对于.h文件默认使用C头文件(保守选择)
    return ["-x", "c-header"]


def _ensure_parse_args_for_header(
    file: Path, base_args: Optional[List[str]]
) -> List[str]:
    """
    确保头文件解析所需的最小参数集:
    - 通过-I包含file.parent目录
    - 如果没有语言标志则添加-x c-header/c++-header
    """
    args = list(base_args or [])
    # 检测是否已存在语言标志(-x <lang>)
    has_lang = False
    for i, a in enumerate(args):
        if a == "-x":
            # 如果存在'-x'且后面有值，则认为已指定语言
            if i + 1 < len(args):
                has_lang = True
                break
        elif a.startswith("-x"):
            has_lang = True
            break

    if not has_lang:
        args.extend(_guess_lang_header_flag(file))

    # 确保存在-I <file.parent>
    inc_dir = str(file.parent)
    has_inc = False
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-I":
            if i + 1 < len(args) and args[i + 1] == inc_dir:
                has_inc = True
                break
            i += 2
            continue
        elif a.startswith("-I"):
            # 可能是-I/path格式
            if a[2:] == inc_dir:
                has_inc = True
                break
        i += 1
    if not has_inc:
        args.extend(["-I", inc_dir])

    return args


def _collect_decl_function_names(cindex: Any, file: Path, args: List[str]) -> List[str]:
    """
    对于没有内联定义的头文件的回退方案:
    收集此头文件中定义的函数声明(原型/方法)
    """
    try:
        index = cindex.Index.create()
        tu = index.parse(str(file), args=args, options=0)
    except Exception:
        return []
    names: List[str] = []
    seen = set()

    def visit(node: Any) -> None:
        try:
            kind = node.kind.name
        except Exception:
            kind = ""
        if kind in {
            "FUNCTION_DECL",
            "CXX_METHOD",
            "FUNCTION_TEMPLATE",
            "CONSTRUCTOR",
            "DESTRUCTOR",
        }:
            loc_file = getattr(getattr(node, "location", None), "file", None)
            try:
                same_file = (
                    loc_file is not None
                    and Path(loc_file.name).resolve() == file.resolve()
                )
            except Exception:
                same_file = False
            if same_file:
                try:
                    nm = str(node.spelling or "").strip()
                except Exception:
                    nm = ""
                if nm and nm not in seen:
                    seen.add(nm)
                    names.append(nm)
        for ch in node.get_children():
            visit(ch)

    try:
        visit(tu.cursor)
    except Exception:
        pass
    return names


def collect_function_names(
    files: List[Path],
    out_path: Path,
    compile_commands_root: Optional[Path] = None,
) -> Path:
    """
    从给定的头文件中收集函数名并将唯一名称写入out_path

    参数:
    - files: 头文件路径列表(.h/.hh/.hpp/.hxx)。非头文件将被跳过
    - out_path: 输出文件路径。将被创建(包括父目录)并覆盖
    - compile_commands_root: 可选，搜索compile_commands.json的根目录
      如果未提供，则从每个文件的目录向上搜索

    返回值:
    - 写入的out_path路径
    """
    # 标准化和过滤头文件
    hdrs: List[Path] = []
    for p in files or []:
        try:
            fp = Path(p).resolve()
        except Exception:
            continue
        if fp.is_file() and fp.suffix.lower() in HEADER_EXTS:
            hdrs.append(fp)

    if not hdrs:
        raise ValueError("未提供有效的头文件(.h/.hh/.hpp/.hxx)")

    # 准备libclang
    cindex = _try_import_libclang()
    if cindex is None:
        from clang import cindex as _ci

        cindex = _ci

    # 准备compile_commands参数映射(如果提供了根目录则全局一次，否则每个文件单独处理)
    cc_args_map_global: Optional[Dict[str, List[str]]] = None
    if compile_commands_root is not None:
        cc_file = find_compile_commands(Path(compile_commands_root))
        if cc_file:
            cc_args_map_global = load_compile_commands(cc_file)

    # 收集名称(保持顺序)
    seen = set()
    ordered_names: List[str] = []

    for hf in hdrs:
        # 确定此文件的参数
        cc_args_map = cc_args_map_global
        if cc_args_map is None:
            # 尝试在此文件附近查找compile_commands.json
            cc_file_local = find_compile_commands(hf.parent)
            if cc_file_local:
                try:
                    cc_args_map = load_compile_commands(cc_file_local)
                except Exception:
                    cc_args_map = None

        base_args = None
        if cc_args_map:
            base_args = cc_args_map.get(str(hf))
        if base_args is None:
            base_args = ["-I", str(hf.parent)]

        args = _ensure_parse_args_for_header(hf, base_args)

        # 尝试扫描。如果出错，尝试使用最小参数集的回退方案
        try:
            funcs = scan_file(cindex, hf, args)
        except Exception:
            try:
                funcs = scan_file(
                    cindex,
                    hf,
                    _ensure_parse_args_for_header(hf, ["-I", str(hf.parent)]),
                )
            except Exception:
                funcs = []

        # 从定义中提取首选名称(qualified_name或name)
        added_count = 0
        for fn in funcs:
            name = ""
            try:
                qn = getattr(fn, "qualified_name", "") or ""
                nm = getattr(fn, "name", "") or ""
                name = qn or nm
                name = str(name).strip()
            except Exception:
                name = ""
            if not name or name in seen:
                continue
            seen.add(name)
            ordered_names.append(name)
            added_count += 1

        # 回退: 如果在此头文件中未找到定义，则收集声明
        if not funcs or added_count == 0:
            try:
                decl_names = _collect_decl_function_names(cindex, hf, args)
            except Exception:
                decl_names = []
            for nm in decl_names:
                name = str(nm).strip()
                if not name or name in seen:
                    continue
                seen.add(name)
                ordered_names.append(name)

    # 写出文件(每行一个)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        out_path.write_text(
            "\n".join(ordered_names) + ("\n" if ordered_names else ""), encoding="utf-8"
        )
    except Exception as e:
        raise RuntimeError(f"写入输出文件失败: {out_path}: {e}")

    return out_path
