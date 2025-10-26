# -*- coding: utf-8 -*-
"""
Lightweight function-name collector for header files using libclang.

Purpose:
- Given one or more C/C++ header files (.h/.hh/.hpp/.hxx), parse each file with libclang
  and collect function names.
- Prefer qualified names when available; fall back to unqualified names.
- Write unique names (de-duplicated, preserving first-seen order) to the specified output file (one per line).

Design:
- Reuse scanner utilities:
  - _try_import_libclang()
  - find_compile_commands()
  - load_compile_commands()
  - scan_file()  (note: scan_file collects only definitions; inline headers are often definitions)
- If compile_commands.json exists, use its args; otherwise, fall back to minimal include of file.parent.
- For header parsing, ensure a language flag (-x c-header / -x c++-header) is present if args do not specify one.

Notes:
- This module focuses on correctness/robustness over performance.
- It does not attempt to discover transitive includes; it only assists the parser by adding -I <file.parent>.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Dict

import typer

from jarvis.jarvis_c2rust.scanner import (
    _try_import_libclang,
    find_compile_commands,
    load_compile_commands,
    scan_file,
)


HEADER_EXTS = {".h", ".hh", ".hpp", ".hxx"}


def _guess_lang_header_flag(file: Path) -> List[str]:
    """
    Guess appropriate -x language flag for header if not specified in compile args.
    """
    ext = file.suffix.lower()
    if ext in {".hh", ".hpp", ".hxx"}:
        return ["-x", "c++-header"]
    # Default to C header for .h (conservative)
    return ["-x", "c-header"]


def _ensure_parse_args_for_header(file: Path, base_args: Optional[List[str]]) -> List[str]:
    """
    Ensure minimal args for header parsing:
    - include file.parent via -I
    - add a language flag -x c-header/c++-header if none exists
    """
    args = list(base_args or [])
    # Detect if a language flag already exists (-x <lang>)
    has_lang = False
    for i, a in enumerate(args):
        if a == "-x":
            # If '-x' present and followed by a value, treat as language specified
            if i + 1 < len(args):
                has_lang = True
                break
        elif a.startswith("-x"):
            has_lang = True
            break

    if not has_lang:
        args.extend(_guess_lang_header_flag(file))

    # Ensure -I <file.parent> is present
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
            # Could be like -I/path
            if a[2:] == inc_dir:
                has_inc = True
                break
        i += 1
    if not has_inc:
        args.extend(["-I", inc_dir])

    return args


def collect_function_names(
    files: List[Path],
    out_path: Path,
    compile_commands_root: Optional[Path] = None,
) -> Path:
    """
    Collect function names from given header files and write unique names to out_path.

    Parameters:
    - files: list of header file paths (.h/.hh/.hpp/.hxx). Non-header files will be skipped.
    - out_path: output file path. Will be created (parents too) and overwritten.
    - compile_commands_root: optional root directory to search for compile_commands.json.
      If not provided, we search upward from each file's directory.

    Returns:
    - Path to the written out_path.
    """
    # Normalize and filter header files
    hdrs: List[Path] = []
    for p in files or []:
        try:
            fp = Path(p).resolve()
        except Exception:
            continue
        if fp.is_file() and fp.suffix.lower() in HEADER_EXTS:
            hdrs.append(fp)

    if not hdrs:
        raise ValueError("No valid header files (.h/.hh/.hpp/.hxx) were provided.")

    # Prepare libclang
    cindex = _try_import_libclang()
    if cindex is None:
        from clang import cindex as _ci  # type: ignore
        cindex = _ci

    # Prepare compile_commands args map (either once for provided root, or per-file if None)
    cc_args_map_global: Optional[Dict[str, List[str]]] = None
    if compile_commands_root is not None:
        cc_file = find_compile_commands(Path(compile_commands_root))
        if cc_file:
            cc_args_map_global = load_compile_commands(cc_file)

    # Collect names (preserving order)
    seen = set()
    ordered_names: List[str] = []

    for hf in hdrs:
        # Determine args for this file
        cc_args_map = cc_args_map_global
        if cc_args_map is None:
            # Try to find compile_commands.json near this file
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

        # Attempt to scan. If error, try a fallback with minimal args.
        try:
            funcs = scan_file(cindex, hf, args)
        except Exception:
            try:
                funcs = scan_file(cindex, hf, _ensure_parse_args_for_header(hf, ["-I", str(hf.parent)]))
            except Exception:
                funcs = []

        # Extract preferred name (qualified_name or name)
        for fn in funcs:
            name = ""
            try:
                qn = getattr(fn, "qualified_name", "") or ""
                nm = getattr(fn, "name", "") or ""
                name = qn or nm
                name = str(name).strip()
            except Exception:
                name = ""
            if not name:
                continue
            if name in seen:
                continue
            seen.add(name)
            ordered_names.append(name)

    # Write out file (one per line)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        out_path.write_text("\n".join(ordered_names) + ("\n" if ordered_names else ""), encoding="utf-8")
    except Exception as e:
        raise RuntimeError(f"Failed to write output file: {out_path}: {e}")

    return out_path


__all__ = ["collect_function_names"]