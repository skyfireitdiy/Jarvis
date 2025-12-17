"""
使用 libclang 的 C/C++ 函数扫描器和调用图提取器。

设计决策:
- 解析器: clang.cindex (libclang)，用于生成包含精确类型和位置的健壮 C/C++ AST。

JSONL 文件
- symbols_raw.jsonl
  原始扫描产物：每个符号（函数或类型）一个 JSON 对象，统一模式：
  字段:
  - id (int)
  - category (str): "function" | "type"
  - name (str)
  - qualified_name (str)
  - signature (str)           # 函数签名；类型则可选或为空
  - return_type (str)         # 函数返回类型；类型则可选或为空
  - params (list[{name, type}])  # 函数参数；类型则可选或为空
  - kind (str)                # 类型种类: struct/class/union/enum/typedef/type_alias
  - underlying_type (str)     # 针对 typedef/type_alias；其他为空
  - ref (list[str])           # 统一的引用：被调用的函数或引用的类型
  - file (str)
  - start_line (int), start_col (int), end_line (int), end_col (int)
  - language (str)
  - created_at (str, ISO-like), updated_at (str, ISO-like)
- symbols.jsonl
  经过裁剪/评估后的符号表（由 prune 子命令或人工整理生成），用于后续转译与规划
- meta.json
  {
    "functions": N,
    "types": M,
    "symbols": N+M,
    "generated_at": "...",
    "schema_version": 1,
    "source_root": "<abs path>"
  }
用法:
  python -m jarvis.jarvis_c2rust.scanner --root /path/to/scan

注意:
- 如果存在 compile_commands.json 文件，将会用它来提高解析准确性。
- 如果找不到 libclang，将引发一个信息丰富的错误，并提示设置环境变量：
  - LIBCLANG_PATH (目录) 或 CLANG_LIBRARY_FILE (完整路径)
  - LLVM_HOME (包含 lib/libclang.so 的前缀)
"""

from __future__ import annotations

import json

from jarvis.jarvis_utils.output import PrettyOutput

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

import typer

from jarvis.jarvis_c2rust.constants import SOURCE_EXTS, TYPE_KINDS


# ---------------------------
# libclang loader
# ---------------------------
def _try_import_libclang() -> Any:
    """
    Load clang.cindex and support libclang 16-21 (inclusive).
    Resolution order:
    1) Respect CLANG_LIBRARY_FILE (must be one of 16-21)
    2) Respect LIBCLANG_PATH (pick libclang from that dir and verify major 16-21)
    3) Respect LLVM_HOME/lib/libclang.*
    4) Probe common locations for versions 16-21
    If Python bindings or libclang are outside 16-21, raise with actionable hints.
    """
    SUPPORTED_MAJORS = {16, 17, 18, 19, 20, 21}

    try:
        from clang import cindex
    except Exception as e:
        raise RuntimeError(
            "导入 clang.cindex 失败。本工具支持 clang 16-21。\n"
            "修复方法：\n"
            "- pip install 'clang>=16,<22'\n"
            "- 确保已安装 libclang (16-21) (例如，apt install llvm-21 clang-21 libclang-21-dev)\n"
            "- 设置环境变量 CLANG_LIBRARY_FILE 指向匹配的共享库，或 LIBCLANG_PATH 指向其目录。"
        ) from e

    # Verify Python clang bindings major version (if available)
    py_major: Optional[int] = None
    try:
        import re as _re

        import clang as _clang

        v = getattr(_clang, "__version__", None)
        if v:
            m = _re.match(r"(\\d+)", str(v))
            if m:
                py_major = int(m.group(1))
    except Exception:
        py_major = None

    # If version is known and not in supported set, fail; if unknown (None), proceed and rely on libclang probing
    if py_major is not None and py_major not in SUPPORTED_MAJORS:
        raise RuntimeError(
            f"Python 'clang' 绑定的主版本必须是 {sorted(SUPPORTED_MAJORS)} 中的一个。\n"
            "修复方法：\n"
            "- pip install --upgrade 'clang>=16,<22'"
        )

    # Helper to probe libclang major version
    def _probe_major_from_lib(path: str) -> Optional[int]:
        try:
            import ctypes
            import re as _re

            class CXString(ctypes.Structure):
                _fields_ = [("data", ctypes.c_void_p), ("private_flags", ctypes.c_uint)]

            lib = ctypes.CDLL(path)
            # Ensure correct ctypes signatures to avoid mis-parsing strings
            lib.clang_getClangVersion.restype = CXString
            lib.clang_getCString.argtypes = [CXString]
            lib.clang_getCString.restype = ctypes.c_char_p
            lib.clang_disposeString.argtypes = [CXString]
            s = lib.clang_getClangVersion()
            cstr = lib.clang_getCString(s)  # returns const char*
            ver = ""
            try:
                if cstr is not None:
                    ver = cstr.decode("utf-8", "ignore")
                else:
                    ver = ""
            except Exception:
                # Fallback if restype not honored by platform
                try:
                    ptr = ctypes.cast(cstr, ctypes.c_char_p)
                    raw = getattr(ptr, "value", None)
                    ver = raw.decode("utf-8", "ignore") if raw is not None else ""
                except Exception:
                    ver = ""
            lib.clang_disposeString(s)
            if ver:
                m = _re.search(r"clang version (\d+)", ver)
                if m:
                    return int(m.group(1))
        except Exception:
            return None
        return None

    def _ensure_supported_and_set(lib_path: str) -> bool:
        major = _probe_major_from_lib(lib_path)
        if major in SUPPORTED_MAJORS:
            try:
                cindex.Config.set_library_file(lib_path)
                return True
            except Exception:
                return False
        return False

    # 1) CLANG_LIBRARY_FILE
    lib_file = os.environ.get("CLANG_LIBRARY_FILE")
    if lib_file and Path(lib_file).exists():
        if _ensure_supported_and_set(lib_file):
            return cindex
        else:
            raise RuntimeError(
                f"环境变量 CLANG_LIBRARY_FILE 指向 '{lib_file}', 但它不是 libclang 16-21 版本。\n"
                "请将其设置为受支持的 libclang (例如 /usr/lib/llvm-21/lib/libclang.so 或匹配的版本)。"
            )

    # 2) LIBCLANG_PATH
    lib_dir = os.environ.get("LIBCLANG_PATH")
    if lib_dir and Path(lib_dir).exists():
        base = Path(lib_dir)
        candidates: List[Path] = []

        # Versioned shared libraries
        for maj in (21, 20, 19, 18, 17, 16):
            candidates.append(base / f"libclang.so.{maj}")
        # Generic names
        candidates.extend(
            [
                base / "libclang.so",  # Linux
                base / "libclang.dylib",  # macOS
                base / "libclang.dll",  # Windows
            ]
        )
        for cand in candidates:
            if cand.exists() and _ensure_supported_and_set(str(cand)):
                return cindex
        # If a directory is given but no valid supported version found, error out explicitly
        raise RuntimeError(
            f"环境变量 LIBCLANG_PATH={lib_dir} 不包含 libclang 16-21。\n"
            "期望找到 libclang.so.[16-21] (Linux) 或来自 llvm@16..@21 的 libclang.dylib (macOS)。"
        )

    # 3) LLVM_HOME
    llvm_home = os.environ.get("LLVM_HOME")
    if llvm_home:
        p = Path(llvm_home) / "lib"
        candidates_llvm: List[Path] = []
        for maj in (21, 20, 19, 18, 17, 16):
            candidates_llvm.append(p / f"libclang.so.{maj}")
        candidates_llvm.extend(
            [
                p / "libclang.so",
                p / "libclang.dylib",
                p / "libclang.dll",
            ]
        )
        for cand in candidates_llvm:
            if cand.exists() and _ensure_supported_and_set(str(cand)):
                return cindex

    # 4) Common locations for versions 16-21
    import platform as _platform

    sys_name = _platform.system()
    path_candidates: List[Path] = []
    if sys_name == "Linux":
        for maj in (21, 20, 19, 18, 17, 16):
            path_candidates.extend(
                [
                    Path(f"/usr/lib/llvm-{maj}/lib/libclang.so.{maj}"),
                    Path(f"/usr/lib/llvm-{maj}/lib/libclang.so"),
                ]
            )
        # Generic fallbacks
        path_candidates.extend(
            [
                Path("/usr/local/lib/libclang.so.21"),
                Path("/usr/local/lib/libclang.so.20"),
                Path("/usr/local/lib/libclang.so.19"),
                Path("/usr/local/lib/libclang.so.18"),
                Path("/usr/local/lib/libclang.so.17"),
                Path("/usr/local/lib/libclang.so.16"),
                Path("/usr/local/lib/libclang.so"),
                Path("/usr/lib/libclang.so.21"),
                Path("/usr/lib/libclang.so.20"),
                Path("/usr/lib/libclang.so.19"),
                Path("/usr/lib/libclang.so.18"),
                Path("/usr/lib/libclang.so.17"),
                Path("/usr/lib/libclang.so.16"),
                Path("/usr/lib/libclang.so"),
            ]
        )
    elif sys_name == "Darwin":
        # Homebrew llvm@N formulas
        for maj in (21, 20, 19, 18, 17, 16):
            path_candidates.append(
                Path(f"/opt/homebrew/opt/llvm@{maj}/lib/libclang.dylib")
            )
            path_candidates.append(
                Path(f"/usr/local/opt/llvm@{maj}/lib/libclang.dylib")
            )
        # Generic llvm formula path (may be symlinked to a specific version)
        path_candidates.extend(
            [
                Path("/opt/homebrew/opt/llvm/lib/libclang.dylib"),
                Path("/usr/local/opt/llvm/lib/libclang.dylib"),
            ]
        )
    else:
        # Best-effort on other systems (Windows)
        path_candidates = [
            Path("C:/Program Files/LLVM/bin/libclang.dll"),
        ]

    # Include additional globbed candidates for distributions that install versioned sonames like libclang.so.21.1.4
    try:
        extra_glob_dirs = [
            Path("/usr/lib"),
            Path("/usr/local/lib"),
            Path("/lib"),
            Path("/usr/lib64"),
            Path("/lib64"),
            Path("/usr/lib/x86_64-linux-gnu"),
        ]
        extra_globs: List[Path] = []
        for d in extra_glob_dirs:
            try:
                extra_globs.extend(d.glob("libclang.so.*"))
            except Exception:
                pass
        # Deduplicate while preserving order (Path is hashable)
        seen = set()
        merged_candidates: List[Path] = []
        for p in list(path_candidates) + extra_globs:
            if p not in seen:
                merged_candidates.append(p)
                seen.add(p)
    except Exception:
        merged_candidates = list(path_candidates)

    for cand in merged_candidates:
        if cand.exists() and _ensure_supported_and_set(str(cand)):
            return cindex

    # Final fallback: try using system default resolution without explicitly setting the library file.
    # Some distributions (e.g., Arch) place libclang in standard linker paths (/usr/lib/libclang.so),
    # which clang.cindex can locate without Config.set_library_file.
    try:
        _ = cindex.Index.create()
        return cindex
    except Exception:
        pass

    # If we got here, we failed to locate a supported libclang 16-21
    raise RuntimeError(
        "未能定位到 libclang 16-21。本工具支持 clang 16-21 版本。\n"
        "修复选项:\n"
        "- 在 Ubuntu/Debian 上: sudo apt-get install -y llvm-21 clang-21 libclang-21-dev (或 20/19/18/17/16)。\n"
        "- 在 macOS (Homebrew) 上: brew install llvm@21 (或 @20/@19/@18/@17/@16)。\n"
        "- 在 Arch Linux 上: 确保 clang 提供了 /usr/lib/libclang.so (通常是这样) 或显式设置 CLANG_LIBRARY_FILE。\n"
        "- 然后设置环境变量 (如果未自动检测到):\n"
        "    export CLANG_LIBRARY_FILE=/usr/lib/llvm-21/lib/libclang.so   # Linux (请调整版本)\n"
        "    export CLANG_LIBRARY_FILE=/opt/homebrew/opt/llvm@21/lib/libclang.dylib  # macOS (请调整版本)\n"
    )


# ---------------------------
# Data structures
# ---------------------------
@dataclass
class FunctionInfo:
    name: str
    qualified_name: str
    signature: str
    return_type: str
    params: List[Dict[str, str]]
    calls: List[str]
    file: str
    start_line: int
    start_col: int
    end_line: int
    end_col: int
    language: str


# ---------------------------
# Compile commands loader
# ---------------------------
def find_compile_commands(start: Path) -> Optional[Path]:
    """
    Search upward from 'start' for compile_commands.json
    """
    cur = start.resolve()
    root = cur.anchor
    while True:
        candidate = cur / "compile_commands.json"
        if candidate.exists():
            return candidate
        if str(cur) == root:
            break
        cur = cur.parent
    return None


def load_compile_commands(cc_path: Path) -> Dict[str, List[str]]:
    """
    Load compile_commands.json and return a mapping:
      file(abs path str) -> compile args (list[str], without compiler executable)
    """
    try:
        data = json.loads(cc_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    result: Dict[str, List[str]] = {}
    for entry in data:
        file_path = Path(entry.get("file", "")).resolve()
        if not file_path:
            continue
        if "arguments" in entry and isinstance(entry["arguments"], list):
            # arguments usually includes the compiler as argv[0]
            args = entry["arguments"][1:] if entry["arguments"] else []
            result[str(file_path)] = args
        else:
            # fallback to split command string
            command = entry.get("command", "")
            if command:
                result[str(file_path)] = (
                    command.split()[1:] if len(command.split()) > 1 else []
                )
    return result


def iter_source_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix in SOURCE_EXTS:
            yield p.resolve()


# ---------------------------
# AST utilities
# ---------------------------
def get_qualified_name(cursor: Any) -> str:
    parts = []
    cur = cursor.semantic_parent
    while cur is not None and cur.kind.name != "TRANSLATION_UNIT":
        if cur.spelling:
            parts.append(cur.spelling)
        cur = cur.semantic_parent
    parts.reverse()
    base = "::".join(parts)
    if base:
        return f"{base}::{cursor.spelling}"
    return cursor.spelling or ""


def collect_params(cursor: Any) -> List[Dict[str, str]]:
    params = []
    for c in cursor.get_children():
        # In libclang, parameters are PARM_DECL
        if c.kind.name == "PARM_DECL":
            t = ""
            try:
                t = c.type.spelling or ""
            except Exception:
                t = ""
            params.append({"name": c.spelling or "", "type": t})
    return params


def collect_calls(cursor: Any) -> List[str]:
    """
    Collect called function names within a function definition.
    """
    calls: List[str] = []

    def walk(node: Any) -> None:
        for ch in node.get_children():
            kind = ch.kind.name
            if kind == "CALL_EXPR":
                # Get referenced function if available
                name = ""
                try:
                    if ch.referenced is not None and ch.referenced.spelling:
                        # Prefer qualified if possible
                        qn = get_qualified_name(ch.referenced)
                        name = qn or ch.referenced.spelling
                    else:
                        # fallback to displayname
                        name = ch.displayname or ""
                except Exception:
                    name = ch.displayname or ""
                if name:
                    calls.append(name)
            # Recurse
            walk(ch)

    walk(cursor)
    return calls


def is_function_like(cursor: Any) -> bool:
    return cursor.kind.name in {
        "FUNCTION_DECL",
        "CXX_METHOD",
        "CONSTRUCTOR",
        "DESTRUCTOR",
        "FUNCTION_TEMPLATE",
    }


def lang_from_cursor(cursor: Any) -> str:
    try:
        return str(cursor.language.name)
    except Exception:
        # Guess by extension
        f = cursor.location.file
        if f is not None:
            ext = os.path.splitext(str(f))[1].lower()
            if ext in (".c",):
                return "C"
            return "CXX"
        return "UNKNOWN"


# ---------------------------
# Scanner core
# ---------------------------
def scan_file(cindex: Any, file_path: Path, args: List[str]) -> List[FunctionInfo]:
    index = cindex.Index.create()
    tu = index.parse(
        str(file_path),
        args=args,
        options=0,  # need bodies to collect calls
    )
    functions: List[FunctionInfo] = []

    def visit(node: Any) -> None:
        # Only consider functions with definitions in this file
        if is_function_like(node) and node.is_definition():
            loc_file = node.location.file
            if (
                loc_file is not None
                and Path(loc_file.name).resolve() == file_path.resolve()
            ):
                try:
                    name = node.spelling or ""
                    qualified_name = get_qualified_name(node)
                    signature = node.displayname or name
                    try:
                        return_type = (
                            node.result_type.spelling
                        )  # not available for constructors/destructors
                    except Exception:
                        return_type = ""
                    params = collect_params(node)
                    calls = collect_calls(node)
                    extent = node.extent
                    start_line = extent.start.line
                    start_col = extent.start.column
                    end_line = extent.end.line
                    end_col = extent.end.column
                    language = lang_from_cursor(node)
                    fi = FunctionInfo(
                        name=name,
                        qualified_name=qualified_name,
                        signature=signature,
                        return_type=return_type,
                        params=params,
                        calls=calls,
                        file=str(file_path),
                        start_line=start_line,
                        start_col=start_col,
                        end_line=end_line,
                        end_col=end_col,
                        language=language,
                    )
                    functions.append(fi)
                except Exception:
                    # Be robust, continue scanning
                    pass

        for ch in node.get_children():
            visit(ch)

    visit(tu.cursor)
    return functions


def scan_directory(scan_root: Path, db_path: Optional[Path] = None) -> Path:
    """
    Scan a directory for C/C++ symbols and store results into JSONL/JSON.

    Returns the path to symbols_raw.jsonl.
      - symbols_raw.jsonl: one JSON object per symbol (category: function/type),原始扫描产物
      - symbols.jsonl:     与原始产物等价的初始基线（便于未执行 prune 时直接进入后续流程）
      - meta.json:         summary counts and timestamp
    """
    scan_root = scan_root.resolve()
    out_dir = scan_root / ".jarvis" / "c2rust"
    out_dir.mkdir(parents=True, exist_ok=True)

    # JSONL/JSON outputs (symbols only)
    symbols_raw_jsonl = out_dir / "symbols_raw.jsonl"
    symbols_curated_jsonl = out_dir / "symbols.jsonl"
    meta_json = out_dir / "meta.json"

    # Prepare libclang
    cindex = _try_import_libclang()
    # Fallback safeguard: if loader returned None, try importing directly
    if cindex is None:
        try:
            from clang import cindex as _ci

            cindex = _ci
        except Exception as e:
            raise RuntimeError(f"Failed to load libclang bindings: {e}")

    # Preflight check: verify libclang/python bindings compatibility before scanning
    try:
        _ = cindex.Index.create()
    except Exception as e:
        msg = str(e)
        if "undefined symbol" in msg:
            # Try to suggest a better libclang candidate that contains the missing symbol
            def _has_symbol(lib_path: str, symbol: str) -> bool:
                try:
                    import ctypes

                    lib = ctypes.CDLL(lib_path)
                    getattr(lib, symbol)
                    return True
                except Exception:
                    return False

            # Build candidate search dirs (Linux/macOS)
            import platform as _platform

            sys_name = _platform.system()
            lib_candidates = []
            if sys_name == "Linux":
                lib_candidates = [
                    "/usr/lib/llvm-21/lib/libclang.so",
                    "/usr/lib/llvm-20/lib/libclang.so",
                    "/usr/lib/llvm-19/lib/libclang.so",
                    "/usr/lib/llvm-18/lib/libclang.so",
                    "/usr/lib/llvm-17/lib/libclang.so",
                    "/usr/lib/llvm-16/lib/libclang.so",
                    "/usr/lib/libclang.so",
                    "/usr/local/lib/libclang.so",
                ]
            elif sys_name == "Darwin":
                # Homebrew locations
                lib_candidates = [
                    "/opt/homebrew/opt/llvm/lib/libclang.dylib",
                    "/usr/local/opt/llvm/lib/libclang.dylib",
                ]

            good = [
                p
                for p in lib_candidates
                if Path(p).exists() and _has_symbol(p, "clang_getOffsetOfBase")
            ]
            hint = ""
            if good:
                hint = f"\n建议的包含所需符号的库:\n  export CLANG_LIBRARY_FILE={good[0]}\n然后重新运行: jarvis-c2rust scan -r {scan_root}"

            PrettyOutput.auto_print(
                "[c2rust-scanner] 检测到 libclang/python 绑定不匹配 (未定义符号)。"
                f"\n详情: {msg}"
                "\n这通常意味着您的 Python 'clang' 绑定版本高于已安装的 libclang。"
                "\n修复选项:\n"
                "- 安装/更新 libclang 以匹配您 Python 'clang' 的主版本 (例如 16-21)。\n"
                "- 或将 Python 'clang' 版本固定为与系统 libclang 匹配 (例如 pip install 'clang>=16,<22')。\n"
                "- 或设置 CLANG_LIBRARY_FILE 指向匹配的 libclang 共享库。\n"
                f"{hint}"
            )
            raise typer.Exit(code=2)
        else:
            # Other initialization errors: surface and exit
            PrettyOutput.auto_print(f"❌ [c2rust-scanner] libclang 初始化失败: {e}")
            raise typer.Exit(code=2)

    # compile_commands
    cc_file = find_compile_commands(scan_root)
    cc_args_map: Dict[str, List[str]] = {}
    if cc_file:
        cc_args_map = load_compile_commands(cc_file)

    # default args: at least include root dir to help header resolution
    default_args = ["-I", str(scan_root)]

    files = list(iter_source_files(scan_root))
    total_files = len(files)
    PrettyOutput.auto_print(
        f"📋 [c2rust-scanner] 正在扫描 {scan_root} 目录下的 {total_files} 个文件"
    )

    scanned = 0
    total_functions = 0
    total_types = 0

    # JSONL writers
    now_ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    sym_id_seq = 1

    def _fn_record(fn: FunctionInfo, id_val: int) -> Dict[str, Any]:
        return {
            "id": id_val,
            "name": fn.name,
            "qualified_name": fn.qualified_name,
            "signature": fn.signature,
            "return_type": fn.return_type,
            "params": fn.params,
            "ref": fn.calls,  # unified field: referenced functions/types
            "file": fn.file,
            "start_line": fn.start_line,
            "start_col": fn.start_col,
            "end_line": fn.end_line,
            "end_col": fn.end_col,
            "language": fn.language,
            "created_at": now_ts,
            "updated_at": now_ts,
        }

    def _tp_record(tp: TypeInfo, id_val: int) -> Dict[str, Any]:
        # For types, 'ref' 表示引用到的类型集合；当前最小实现：若为typedef/alias则包含 underlying_type
        refs: List[str] = []
        if tp.underlying_type:
            try:
                s = str(tp.underlying_type).strip()
                if s:
                    refs.append(s)
            except Exception:
                pass
        return {
            "id": id_val,
            "name": tp.name,
            "qualified_name": tp.qualified_name,
            "kind": tp.kind,
            "underlying_type": tp.underlying_type,
            "ref": refs,
            "file": tp.file,
            "start_line": tp.start_line,
            "start_col": tp.start_col,
            "end_line": tp.end_line,
            "end_col": tp.end_col,
            "language": tp.language,
            "created_at": now_ts,
            "updated_at": now_ts,
        }

    # Unified symbol records (functions and types)
    def _sym_record_from_function(fn: FunctionInfo, id_val: int) -> Dict[str, Any]:
        return {
            "id": id_val,
            "category": "function",
            "name": fn.name,
            "qualified_name": fn.qualified_name,
            "signature": fn.signature,
            "return_type": fn.return_type,
            "params": fn.params,
            "ref": fn.calls,
            "file": fn.file,
            "start_line": fn.start_line,
            "start_col": fn.start_col,
            "end_line": fn.end_line,
            "end_col": fn.end_col,
            "language": fn.language,
            "created_at": now_ts,
            "updated_at": now_ts,
        }

    def _sym_record_from_type(tp: TypeInfo, id_val: int) -> Dict[str, Any]:
        refs_t: List[str] = []
        if tp.underlying_type:
            try:
                s = str(tp.underlying_type).strip()
                if s:
                    refs_t.append(s)
            except Exception:
                pass
        return {
            "id": id_val,
            "category": "type",
            "name": tp.name,
            "qualified_name": tp.qualified_name,
            "kind": tp.kind,
            "underlying_type": tp.underlying_type,
            "ref": refs_t,
            "file": tp.file,
            "start_line": tp.start_line,
            "start_col": tp.start_col,
            "end_line": tp.end_line,
            "end_col": tp.end_col,
            "language": tp.language,
            "created_at": now_ts,
            "updated_at": now_ts,
        }

    # Open JSONL file (symbols only)
    f_sym = symbols_raw_jsonl.open("w", encoding="utf-8")
    try:
        for p in files:
            # prefer compile_commands args if available
            args = cc_args_map.get(str(p), default_args)
            try:
                funcs = scan_file(cindex, p, args)
            except Exception as e:
                # If we hit undefined symbol, it's a libclang/python bindings mismatch; abort with guidance
                msg = str(e)
                if "undefined symbol" in msg:

                    def _has_symbol(lib_path: str, symbol: str) -> bool:
                        try:
                            import ctypes

                            lib = ctypes.CDLL(lib_path)
                            getattr(lib, symbol)
                            return True
                        except Exception:
                            return False

                    import platform as _platform

                    sys_name = _platform.system()
                    lib_candidates2: List[str] = []
                    if sys_name == "Linux":
                        lib_candidates2 = [
                            "/usr/lib/llvm-20/lib/libclang.so",
                            "/usr/lib/llvm-19/lib/libclang.so",
                            "/usr/lib/llvm-18/lib/libclang.so",
                            "/usr/lib/libclang.so",
                            "/usr/local/lib/libclang.so",
                        ]
                    elif sys_name == "Darwin":
                        lib_candidates2 = [
                            "/opt/homebrew/opt/llvm/lib/libclang.dylib",
                            "/usr/local/opt/llvm/lib/libclang.dylib",
                        ]

                    good = [
                        lp
                        for lp in lib_candidates2
                        if Path(lp).exists()
                        and _has_symbol(lp, "clang_getOffsetOfBase")
                    ]
                    hint = ""
                    if good:
                        hint = f"\n建议的包含所需符号的库:\n  export CLANG_LIBRARY_FILE={good[0]}\n然后重新运行: jarvis-c2rust scan -r {scan_root}"

                    PrettyOutput.auto_print(
                        "[c2rust-scanner] 解析期间检测到 libclang/python 绑定不匹配 (未定义符号)。"
                        f"\n详情: {msg}"
                        "\n这通常意味着您的 Python 'clang' 绑定版本高于已安装的 libclang。"
                        "\n修复选项:\n"
                        "- 安装/更新 libclang 以匹配您 Python 'clang' 的主版本 (例如 19/20)。\n"
                        "- 或将 Python 'clang' 版本固定为与系统 libclang 匹配 (例如 pip install 'clang==18.*')。\n"
                        "- 或设置 CLANG_LIBRARY_FILE 指向匹配的 libclang 共享库。\n"
                        f"{hint}"
                    )
                    raise typer.Exit(code=2)

                # Try without args as fallback for regular parse errors
                try:
                    funcs = scan_file(cindex, p, [])
                except Exception:
                    PrettyOutput.auto_print(f"❌ [c2rust-scanner] 解析 {p} 失败: {e}")
                    continue

            # Write JSONL
            for fn in funcs:
                # write unified symbol record
                srec = _sym_record_from_function(fn, sym_id_seq)
                f_sym.write(json.dumps(srec, ensure_ascii=False) + "\n")
                # increase sequences
                sym_id_seq += 1
            total_functions += len(funcs)

            # Scan types in this file
            try:
                types = scan_types_file(cindex, p, args)
            except Exception:
                try:
                    types = scan_types_file(cindex, p, [])
                except Exception:
                    types = []

            for t in types:
                # write unified symbol record
                srec_t = _sym_record_from_type(t, sym_id_seq)
                f_sym.write(json.dumps(srec_t, ensure_ascii=False) + "\n")
                # increase sequences
                sym_id_seq += 1
            total_types += len(types)

            scanned += 1
            if scanned % 20 == 0 or scanned == total_files:
                PrettyOutput.auto_print(
                    f"📊 [c2rust-scanner] 进度: {scanned}/{total_files} 个文件, {total_functions} 个函数, {total_types} 个类型"
                )
    finally:
        try:
            f_sym.close()
        except Exception:
            pass

    # Write meta.json
    meta = {
        "functions": total_functions,
        "types": total_types,
        "symbols": total_functions + total_types,
        "generated_at": now_ts,
        "schema_version": 1,
        "source_root": str(scan_root),
    }
    try:
        meta_json.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass

    PrettyOutput.auto_print(
        f"✅ [c2rust-scanner] 完成。收集到的函数: {total_functions}, 类型: {total_types}, 符号: {total_functions + total_types}"
    )
    PrettyOutput.auto_print(
        f"📊 [c2rust-scanner] JSONL 已写入: {symbols_raw_jsonl} (原始符号)"
    )
    # 同步生成基线 symbols.jsonl（与 raw 等价），便于后续流程仅基于 symbols.jsonl 运行
    try:
        shutil.copy2(symbols_raw_jsonl, symbols_curated_jsonl)
        PrettyOutput.auto_print(
            f"📊 [c2rust-scanner] JSONL 基线已写入: {symbols_curated_jsonl} (用于后续流程)"
        )
    except Exception as _e:
        PrettyOutput.auto_print(f"❌ [c2rust-scanner] 生成 symbols.jsonl 失败: {_e}")
        raise
    PrettyOutput.auto_print(f"📋 [c2rust-scanner] 元数据已写入: {meta_json}")
    return symbols_raw_jsonl


# ---------------------------
# Type scanning
# ---------------------------
@dataclass
class TypeInfo:
    name: str
    qualified_name: str
    kind: str
    underlying_type: str
    file: str
    start_line: int
    start_col: int
    end_line: int
    end_col: int
    language: str


def scan_types_file(cindex: Any, file_path: Path, args: List[str]) -> List[TypeInfo]:
    index = cindex.Index.create()
    tu = index.parse(
        str(file_path),
        args=args,
        options=0,
    )
    types: List[TypeInfo] = []

    def visit(node: Any) -> None:
        kind = node.kind.name
        # Filter by file
        loc_file = node.location.file
        if loc_file is None or Path(loc_file.name).resolve() != file_path.resolve():
            for ch in node.get_children():
                visit(ch)
            return

        if kind in TYPE_KINDS:
            # Accept full definitions for record/enum; typedef/alias are inherently definitions
            need_def = kind in {
                "STRUCT_DECL",
                "UNION_DECL",
                "ENUM_DECL",
                "CXX_RECORD_DECL",
            }
            if (not need_def) or node.is_definition():
                try:
                    name = node.spelling or ""
                    qualified_name = get_qualified_name(node)
                    underlying = ""
                    if kind in {"TYPEDEF_DECL", "TYPE_ALIAS_DECL"}:
                        try:
                            underlying = node.underlying_typedef_type.spelling or ""
                        except Exception:
                            underlying = ""
                    extent = node.extent
                    start_line = extent.start.line
                    start_col = extent.start.column
                    end_line = extent.end.line
                    end_col = extent.end.column
                    language = lang_from_cursor(node)
                    ti = TypeInfo(
                        name=name,
                        qualified_name=qualified_name,
                        kind=kind.lower(),
                        underlying_type=underlying,
                        file=str(file_path),
                        start_line=start_line,
                        start_col=start_col,
                        end_line=end_line,
                        end_col=end_col,
                        language=language,
                    )
                    types.append(ti)
                except Exception:
                    pass

        for ch in node.get_children():
            visit(ch)

    visit(tu.cursor)
    return types


# ---------------------------
# CLI and DOT export
# ---------------------------


def generate_dot_from_db(db_path: Path, out_path: Path) -> Path:
    # Generate a global reference dependency graph (DOT) from symbols.jsonl.
    def _resolve_symbols_jsonl_path(hint: Path) -> Path:
        p = Path(hint)
        # 允许直接传入 .jsonl 文件
        if p.is_file() and p.suffix.lower() == ".jsonl":
            return p
        # 仅支持目录下的标准路径：<dir>/.jarvis/c2rust/symbols.jsonl
        if p.is_dir():
            prefer = p / ".jarvis" / "c2rust" / "symbols.jsonl"
            return prefer
        # 默认：项目 <cwd>/.jarvis/c2rust/symbols.jsonl
        return Path(".") / ".jarvis" / "c2rust" / "symbols.jsonl"

    sjsonl = _resolve_symbols_jsonl_path(db_path)
    if not sjsonl.exists():
        raise FileNotFoundError(f"未找到 symbols.jsonl: {sjsonl}")

    # Load symbols (functions and types), unified handling (no category filtering)
    by_id: Dict[int, Dict[str, Any]] = {}
    name_to_id: Dict[str, int] = {}
    adj_names: Dict[int, List[str]] = {}
    with open(sjsonl, "r", encoding="utf-8") as f:
        idx = 0
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            idx += 1
            fid = int(obj.get("id") or idx)
            nm = obj.get("name") or ""
            qn = obj.get("qualified_name") or ""
            sig = obj.get("signature") or ""
            refs = obj.get("ref")
            if not isinstance(refs, list):
                refs = []
            refs = [c for c in refs if isinstance(c, str) and c]

            by_id[fid] = {"name": nm, "qname": qn, "sig": sig}
            if nm:
                name_to_id.setdefault(nm, fid)
            if qn:
                name_to_id.setdefault(qn, fid)
            adj_names[fid] = refs

    # Convert name-based adjacency to id-based adjacency (internal edges only)
    adj_ids: Dict[int, List[int]] = {}
    all_ids: List[int] = sorted(by_id.keys())
    for src in all_ids:
        internal: List[int] = []
        for target in adj_names.get(src, []):
            tid = name_to_id.get(target)
            if tid is not None and tid != src:
                internal.append(tid)
        try:
            internal = list(dict.fromkeys(internal))
        except Exception:
            internal = sorted(list(set(internal)))
        adj_ids[src] = internal

    def base_label(fid: int) -> str:
        meta = by_id.get(fid, {})
        base = meta.get("qname") or meta.get("name") or f"sym_{fid}"
        sig = meta.get("sig") or ""
        if sig and sig != base:
            return f"{base}\\n{sig}"
        return base

    # Prepare output path
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Write global DOT
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("digraph refgraph {\n")
        f.write("  rankdir=LR;\n")
        f.write("  graph [fontsize=10];\n")
        f.write("  node  [fontsize=10];\n")
        f.write("  edge  [fontsize=9];\n")

        # Nodes
        for fid in all_ids:
            lbl = base_label(fid)
            safe_label = lbl.replace("\\", "\\\\").replace('"', '\\"')
            f.write(f'  n{fid} [label="{safe_label}", shape=box];\n')

        # Edges
        for src in all_ids:
            for dst in adj_ids.get(src, []):
                f.write(f"  n{src} -> n{dst};\n")

        f.write("}\n")

    return out_path


def find_root_function_ids(db_path: Path) -> List[int]:
    """
    Return IDs of root symbols (no incoming references) by reading symbols.jsonl (or given .jsonl path).
    - 严格使用 ref 字段
    - 函数与类型统一处理（不区分）
    """

    def _resolve_symbols_jsonl_path(hint: Path) -> Path:
        p = Path(hint)
        if p.is_file() and p.suffix.lower() == ".jsonl":
            return p
        if p.is_dir():
            prefer = p / ".jarvis" / "c2rust" / "symbols.jsonl"
            return prefer
        # 默认：项目 .jarvis/c2rust/symbols.jsonl
        return Path(".") / ".jarvis" / "c2rust" / "symbols.jsonl"

    fjsonl = _resolve_symbols_jsonl_path(db_path)
    if not fjsonl.exists():
        raise FileNotFoundError(f"未找到 symbols.jsonl: {fjsonl}")

    records: List[Any] = []
    with open(fjsonl, "r", encoding="utf-8") as f:
        idx = 0
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            idx += 1
            fid = int(obj.get("id") or idx)
            name = obj.get("name") or ""
            qname = obj.get("qualified_name") or ""
            refs = obj.get("ref")
            if not isinstance(refs, list):
                refs = []
            refs = [r for r in refs if isinstance(r, str) and r]
            records.append((fid, name, qname, refs))

    name_to_id: Dict[str, int] = {}
    all_ids: Set[int] = set()
    for fid, name, qname, _ in records:
        fid = int(fid)
        all_ids.add(fid)
        if isinstance(name, str) and name:
            name_to_id.setdefault(name, fid)
        if isinstance(qname, str) and qname:
            name_to_id.setdefault(qname, fid)

    non_roots: Set[int] = set()
    for fid, _name, _qname, refs in records:
        for target in refs:
            tid = name_to_id.get(target)
            if tid is not None and tid != fid:
                non_roots.add(tid)

    root_ids = sorted(list(all_ids - non_roots))
    return root_ids


def compute_translation_order_jsonl(
    db_path: Path, out_path: Optional[Path] = None
) -> Path:
    """
    Compute translation order on reference graph and write order to JSONL.
    Data source: symbols.jsonl (or provided .jsonl path), strictly using ref field and including all symbols.
    Output:
      Each line is a JSON object:
        {
          "step": int,
          "ids": [symbol_id, ...],
          "group": bool,
          "roots": [root_id],      # root this step is attributed to (empty if residual)
          "created_at": "YYYY-MM-DDTHH:MM:SS"
        }
    """

    def _resolve_symbols_jsonl_path(hint: Path) -> Path:
        p = Path(hint)
        if p.is_file() and p.suffix.lower() == ".jsonl":
            return p
        if p.is_dir():
            prefer = p / ".jarvis" / "c2rust" / "symbols.jsonl"
            return prefer
        return Path(".") / ".jarvis" / "c2rust" / "symbols.jsonl"

    fjsonl = _resolve_symbols_jsonl_path(db_path)
    if not fjsonl.exists():
        raise FileNotFoundError(f"未找到 symbols.jsonl: {fjsonl}")

    # Load symbols and build name-based adjacency from ref
    by_id: Dict[int, Dict[str, Any]] = {}
    name_to_id: Dict[str, int] = {}
    adj_names: Dict[int, List[str]] = {}
    with open(fjsonl, "r", encoding="utf-8") as f:
        idx = 0
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            idx += 1
            fid = int(obj.get("id") or idx)
            nm = obj.get("name") or ""
            qn = obj.get("qualified_name") or ""
            refs = obj.get("ref")
            if not isinstance(refs, list):
                refs = []
            refs = [r for r in refs if isinstance(r, str) and r]
            by_id[fid] = {
                "name": nm,
                "qname": qn,
                "cat": (obj.get("category") or ""),
                "file": obj.get("file") or "",
                "start_line": obj.get("start_line"),
                "end_line": obj.get("end_line"),
                "start_col": obj.get("start_col"),
                "end_col": obj.get("end_col"),
                "language": obj.get("language") or "",
                "record": obj,  # embed full symbol record for order file self-containment
            }
            if nm:
                name_to_id.setdefault(nm, fid)
            if qn:
                name_to_id.setdefault(qn, fid)
            adj_names[fid] = refs

    # Convert to id-based adjacency (internal edges only)
    adj_ids: Dict[int, List[int]] = {}
    all_ids: List[int] = sorted(by_id.keys())
    for src in all_ids:
        internal: List[int] = []
        for target in adj_names.get(src, []):
            tid = name_to_id.get(target)
            if tid is not None and tid != src:
                internal.append(tid)
        try:
            internal = list(dict.fromkeys(internal))
        except Exception:
            internal = sorted(list(set(internal)))
        adj_ids[src] = internal

    # Roots by incoming degree (no incoming)
    try:
        roots = find_root_function_ids(fjsonl)
    except Exception:
        roots = []

    # Tarjan SCC
    index_counter = 0
    stack: List[int] = []
    onstack: Set[int] = set()
    indices: Dict[int, int] = {}
    lowlinks: Dict[int, int] = {}
    sccs: List[List[int]] = []

    def strongconnect(v: int) -> None:
        nonlocal index_counter, stack
        indices[v] = index_counter
        lowlinks[v] = index_counter
        index_counter += 1
        stack.append(v)
        onstack.add(v)

        for w in adj_ids.get(v, []):
            if w not in indices:
                strongconnect(w)
                lowlinks[v] = min(lowlinks[v], lowlinks[w])
            elif w in onstack:
                lowlinks[v] = min(lowlinks[v], indices[w])

        if lowlinks[v] == indices[v]:
            comp: List[int] = []
            while True:
                w = stack.pop()
                onstack.discard(w)
                comp.append(w)
                if w == v:
                    break
            sccs.append(sorted(comp))

    for node in all_ids:
        if node not in indices:
            strongconnect(node)

    # Component DAG (reversed: dependency -> dependent) for leaves-first order
    id2comp: Dict[int, int] = {}
    for i, comp in enumerate(sccs):
        for nid in comp:
            id2comp[nid] = i

    comp_count = len(sccs)
    comp_rev_adj: Dict[int, Set[int]] = {i: set() for i in range(comp_count)}
    indeg: Dict[int, int] = {i: 0 for i in range(comp_count)}
    for u in all_ids:
        cu = id2comp[u]
        for v in adj_ids.get(u, []):
            cv = id2comp[v]
            if cu != cv:
                if cu not in comp_rev_adj[cv]:
                    comp_rev_adj[cv].add(cu)
    for cv, succs in comp_rev_adj.items():
        for cu in succs:
            indeg[cu] += 1

    # Kahn on reversed DAG
    from collections import deque

    q = deque(sorted([i for i in range(comp_count) if indeg[i] == 0]))
    comp_order: List[int] = []
    while q:
        c = q.popleft()
        comp_order.append(c)
        for nxt in sorted(comp_rev_adj.get(c, set())):
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                q.append(nxt)

    if len(comp_order) < comp_count:
        remaining = [i for i in range(comp_count) if i not in comp_order]
        comp_order.extend(sorted(remaining))

    # Emit steps by root priority
    emitted: Set[int] = set()
    steps: List[Dict[str, Any]] = []
    now_ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())

    # precompute reachability per root
    def _reachable(start_id: int) -> Set[int]:
        visited: Set[int] = set()
        stack2: List[int] = [start_id]
        visited.add(start_id)
        while stack2:
            s = stack2.pop()
            for v in adj_ids.get(s, []):
                if v not in visited:
                    visited.add(v)
                    stack2.append(v)
        return visited

    root_reach: Dict[int, Set[int]] = {rid: _reachable(rid) for rid in roots}

    def _emit_for_root(root_id: Optional[int]) -> None:
        # Emit order per root follows leaves-first (on reversed component DAG),
        # but delay entry functions (e.g., main) to the end if they are singleton components.
        reach = root_reach.get(root_id, set()) if root_id is not None else None

        def _is_entry(nid: int) -> bool:
            meta = by_id.get(nid, {})
            nm = str(meta.get("name") or "").lower()
            qn = str(meta.get("qname") or "").lower()
            # Configurable delayed entry symbols via env:
            # - c2rust_delay_entry_symbols
            # - c2rust_delay_entries
            # - C2RUST_DELAY_ENTRIES
            entries_env = (
                os.environ.get("c2rust_delay_entry_symbols")
                or os.environ.get("c2rust_delay_entries")
                or os.environ.get("C2RUST_DELAY_ENTRIES")
                or ""
            )
            entries_set = set()
            if entries_env:
                try:
                    import re as _re

                    parts = _re.split(r"[,\s;]+", entries_env.strip())
                except Exception:
                    parts = [
                        p.strip() for p in entries_env.replace(";", ",").split(",")
                    ]
                entries_set = {p.strip().lower() for p in parts if p and p.strip()}
            # If configured, use the provided entries; otherwise fallback to default 'main'
            if entries_set:
                return (nm in entries_set) or (qn in entries_set)
            return nm == "main" or qn == "main" or qn.endswith("::main")

        delayed_entries: List[int] = []

        for comp_idx in comp_order:
            comp_nodes = sccs[comp_idx]
            selected: List[int] = []
            # Select nodes for this component, deferring entry (main) if safe to do so
            for nid in comp_nodes:
                if nid in emitted:
                    continue
                if reach is not None and nid not in reach:
                    continue
                # Skip type symbols in order emission (types don't require translation steps)
                meta_n = by_id.get(nid, {})
                if str(meta_n.get("cat") or "") == "type":
                    continue
                # Only delay entry when the SCC is a singleton to avoid breaking intra-SCC semantics
                if _is_entry(nid) and len(comp_nodes) == 1:
                    delayed_entries.append(nid)
                else:
                    selected.append(nid)

            if selected:
                for nid in selected:
                    emitted.add(nid)
                syms = []
                for nid in sorted(selected):
                    meta = by_id.get(nid, {})
                    label = meta.get("qname") or meta.get("name") or f"sym_{nid}"
                    syms.append(label)
                roots_labels = []
                if root_id is not None:
                    meta_r = by_id.get(root_id, {})
                    rlabel = (
                        meta_r.get("qname") or meta_r.get("name") or f"sym_{root_id}"
                    )
                    roots_labels = [rlabel]
                steps.append(
                    {
                        "step": len(steps) + 1,
                        "ids": sorted(selected),
                        "items": [
                            by_id.get(nid, {}).get("record")
                            for nid in sorted(selected)
                            if isinstance(by_id.get(nid, {}).get("record"), dict)
                        ],
                        "symbols": syms,
                        "group": len(syms) > 1,
                        "roots": roots_labels,
                        "created_at": now_ts,
                    }
                )

        # Emit delayed entry functions as the final step for this root
        if delayed_entries:
            for nid in delayed_entries:
                emitted.add(nid)
            syms = []
            for nid in sorted(delayed_entries):
                meta = by_id.get(nid, {})
                label = meta.get("qname") or meta.get("name") or f"sym_{nid}"
                syms.append(label)
            roots_labels = []
            if root_id is not None:
                meta_r = by_id.get(root_id, {})
                rlabel = meta_r.get("qname") or meta_r.get("name") or f"sym_{root_id}"
                roots_labels = [rlabel]
            steps.append(
                {
                    "step": len(steps) + 1,
                    "ids": sorted(delayed_entries),
                    "items": [
                        by_id.get(nid, {}).get("record")
                        for nid in sorted(delayed_entries)
                        if isinstance(by_id.get(nid, {}).get("record"), dict)
                    ],
                    "symbols": syms,
                    "group": len(syms) > 1,
                    "roots": roots_labels,
                    "created_at": now_ts,
                }
            )

    for rid in sorted(roots, key=lambda r: len(root_reach.get(r, set())), reverse=True):
        _emit_for_root(rid)
    _emit_for_root(None)

    if out_path is None:
        # 根据输入符号表选择输出文件名：
        # - symbols_raw.jsonl -> translation_order_raw.jsonl（扫描阶段原始顺序）
        # - 其他（如 symbols.jsonl/curated） -> translation_order.jsonl（默认）
        base = "translation_order.jsonl"
        try:
            name = Path(fjsonl).name.lower()
            if "symbols_raw.jsonl" in name:
                base = "translation_order_raw.jsonl"
        except Exception:
            pass
        out_path = fjsonl.parent / base
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Purge redundant fields before writing (keep ids and records; drop symbols/items)
    try:
        # 保留 items（包含完整符号记录及替换信息），仅移除冗余的 symbols 文本标签
        steps = [
            dict((k, v) for k, v in st.items() if k not in ("symbols",)) for st in steps
        ]
    except Exception:
        pass
    with open(out_path, "w", encoding="utf-8") as fo:
        for st in steps:
            fo.write(json.dumps(st, ensure_ascii=False) + "\n")
    return out_path


def export_root_subgraphs_to_dir(db_path: Path, out_dir: Path) -> List[Path]:
    # Generate per-root reference subgraph DOT files from symbols.jsonl into out_dir (unified: functions and types).
    def _resolve_symbols_jsonl_path(hint: Path) -> Path:
        p = Path(hint)
        if p.is_file() and p.suffix.lower() == ".jsonl":
            return p
        if p.is_dir():
            prefer = p / ".jarvis" / "c2rust" / "symbols.jsonl"
            return prefer
        return Path(".") / ".jarvis" / "c2rust" / "symbols.jsonl"

    sjsonl = _resolve_symbols_jsonl_path(db_path)
    if not sjsonl.exists():
        raise FileNotFoundError(f"未找到 symbols.jsonl: {sjsonl}")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load symbols (unified)
    by_id: Dict[int, Dict[str, str]] = {}
    name_to_id: Dict[str, int] = {}
    adj: Dict[int, List[str]] = {}

    with open(sjsonl, "r", encoding="utf-8") as f:
        idx = 0
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            idx += 1
            # unified handling: include all symbols
            fid = int(obj.get("id") or idx)
            nm = obj.get("name") or ""
            qn = obj.get("qualified_name") or ""
            sig = obj.get("signature") or ""
            refs = obj.get("ref")
            if not isinstance(refs, list):
                refs = []
            refs = [c for c in refs if isinstance(c, str) and c]

            by_id[fid] = {"name": nm, "qname": qn, "sig": sig}
            if nm:
                name_to_id.setdefault(nm, fid)
            if qn:
                name_to_id.setdefault(qn, fid)
            adj[fid] = refs

    def base_label(fid: int) -> str:
        meta = by_id.get(fid, {})
        base = meta.get("qname") or meta.get("name") or f"sym_{fid}"
        sig = meta.get("sig") or ""
        if sig and sig != base:
            return f"{base}\\n{sig}"
        return base

    def sanitize_filename(s: str) -> str:
        if not s:
            return "root"
        s = s.replace("::", "__")
        return "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in s)[
            :120
        ]

    generated: List[Path] = []
    root_ids = find_root_function_ids(db_path)

    for rid in root_ids:
        # DFS over internal refs from the root
        visited: Set[int] = set()
        stack: List[int] = [rid]
        visited.add(rid)
        while stack:
            src = stack.pop()
            for callee in adj.get(src, []):
                cid = name_to_id.get(callee)
                if cid is not None and cid not in visited:
                    visited.add(cid)
                    stack.append(cid)

        # Build nodes and edges
        node_labels: Dict[str, str] = {}
        external_nodes: Dict[str, str] = {}
        ext_count = 0
        edges = set()

        id_to_node = {fid: f"n{fid}" for fid in visited}

        # Internal nodes
        for fid in visited:
            node_labels[id_to_node[fid]] = base_label(fid)

        # Edges (internal -> internal/external)
        for src in visited:
            src_node = id_to_node[src]
            for callee in adj.get(src, []):
                cid = name_to_id.get(callee)
                if cid is not None and cid in visited:
                    edges.add((src_node, id_to_node[cid]))
                else:
                    dst = external_nodes.get(callee)
                    if dst is None:
                        dst = f"ext{ext_count}"
                        ext_count += 1
                        external_nodes[callee] = dst
                        node_labels[dst] = callee
                    edges.add((src_node, dst))

        # Write DOT
        root_base = (
            by_id.get(rid, {}).get("qname")
            or by_id.get(rid, {}).get("name")
            or f"sym_{rid}"
        )
        fname = f"subgraph_root_{rid}_{sanitize_filename(root_base)}.dot"
        out_path = out_dir / fname
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("digraph refgraph_sub {\n")
            f.write("  rankdir=LR;\n")
            f.write("  graph [fontsize=10];\n")
            f.write("  node  [fontsize=10];\n")
            f.write("  edge  [fontsize=9];\n")

            # Emit nodes
            for nid, lbl in node_labels.items():
                safe_label = lbl.replace("\\", "\\\\").replace('"', '\\"')
                if nid.startswith("ext"):
                    f.write(
                        f'  {nid} [label="{safe_label}", shape=ellipse, style=dashed, color=gray50, fontcolor=gray30];\n'
                    )
                else:
                    f.write(f'  {nid} [label="{safe_label}", shape=box];\n')

            # Emit edges
            for s, d in sorted(edges):
                f.write(f"  {s} -> {d};\n")

            f.write("}\n")

        generated.append(out_path)

    return generated


# ---------------------------
# Third-party replacement evaluation
# ---------------------------


def run_scan(
    dot: Optional[Path] = None,
    only_dot: bool = False,
    subgraphs_dir: Optional[Path] = None,
    only_subgraphs: bool = False,
    png: bool = False,
    non_interactive: bool = True,
) -> None:
    # Scan for C/C++ functions and persist results to JSONL; optionally generate DOT.
    # Determine data path
    root = Path(".")
    Path(".") / ".jarvis" / "c2rust" / "symbols_raw.jsonl"
    data_path_curated = Path(".") / ".jarvis" / "c2rust" / "symbols.jsonl"

    # Helper: render a DOT file to PNG using Graphviz 'dot'
    def _render_dot_to_png(dot_file: Path, png_out: Optional[Path] = None) -> Path:
        try:
            import subprocess
            from shutil import which
        except Exception as _e:
            raise RuntimeError(f"准备 PNG 渲染时出现环境问题: {_e}")
        exe = which("dot")
        if not exe:
            raise RuntimeError(
                "在 PATH 中未找到 Graphviz 'dot'。请安装 graphviz 并确保 'dot' 可用。"
            )
        dot_file = Path(dot_file)
        if png_out is None:
            png_out = dot_file.with_suffix(".png")
        else:
            png_out = Path(png_out)
        png_out.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                [exe, "-Tpng", str(dot_file), "-o", str(png_out)], check=True
            )
        except FileNotFoundError:
            raise RuntimeError("未找到 Graphviz 'dot' 可执行文件。")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"'dot' 渲染 {dot_file} 为 PNG 失败: {e}")
        return png_out

    if not (only_dot or only_subgraphs):
        try:
            scan_directory(root)
        except Exception as e:
            PrettyOutput.auto_print(f"❌ [c2rust-scanner] 错误: {e}")
            raise typer.Exit(code=1)
    else:
        # Only-generate mode (no rescan). 验证输入，仅基于既有 symbols.jsonl 进行可选的 DOT/子图输出；此处不计算翻译顺序。
        if not data_path_curated.exists():
            PrettyOutput.auto_print(
                f"⚠️ [c2rust-scanner] 未找到数据: {data_path_curated}"
            )
            raise typer.Exit(code=2)
        if only_dot and dot is None:
            PrettyOutput.auto_print(
                "⚠️ [c2rust-scanner] --only-dot 需要 --dot 来指定输出文件"
            )
            raise typer.Exit(code=2)
        if only_subgraphs and subgraphs_dir is None:
            PrettyOutput.auto_print(
                "⚠️ [c2rust-scanner] --only-subgraphs 需要 --subgraphs-dir 来指定输出目录"
            )
            raise typer.Exit(code=2)

    # Generate DOT (global) if requested
    if dot is not None:
        try:
            # 使用正式符号表生成可视化
            generate_dot_from_db(data_path_curated, dot)
            PrettyOutput.auto_print(f"📊 [c2rust-scanner] DOT 文件已写入: {dot}")
            if png:
                png_path = _render_dot_to_png(dot)
                PrettyOutput.auto_print(
                    f"📊 [c2rust-scanner] PNG 文件已写入: {png_path}"
                )
        except Exception as e:
            PrettyOutput.auto_print(f"❌ [c2rust-scanner] 写入 DOT/PNG 失败: {e}")
            raise typer.Exit(code=1)

    # Generate per-root subgraphs if requested
    if subgraphs_dir is not None:
        try:
            # 使用正式符号表生成根节点子图
            files = export_root_subgraphs_to_dir(data_path_curated, subgraphs_dir)
            if png:
                png_count = 0
                for dp in files:
                    try:
                        _render_dot_to_png(dp)
                        png_count += 1
                    except Exception as _e:
                        # Fail fast on PNG generation error for subgraphs to make issues visible
                        raise
                PrettyOutput.auto_print(
                    f"📊 [c2rust-scanner] 根节点子图已写入: {len(files)} 个 DOT 文件和 {png_count} 个 PNG 文件 -> {subgraphs_dir}"
                )
            else:
                PrettyOutput.auto_print(
                    f"📊 [c2rust-scanner] 根节点子图已写入: {len(files)} 个文件 -> {subgraphs_dir}"
                )
        except Exception as e:
            PrettyOutput.auto_print(f"❌ [c2rust-scanner] 写入子图 DOT/PNG 失败: {e}")
            raise typer.Exit(code=1)
