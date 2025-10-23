#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
C/C++ function scanner and call graph extractor using libclang.

Design decisions:
- Parser: clang.cindex (libclang) for robust C/C++ AST with precise types and locations.
- Output: JSONL files at <scan_root>/.jarvis/c2rust/functions.jsonl and types.jsonl
- Schema: JSONL records for functions/types; calls stored as arrays of strings.
  Future: schema evolves via meta.json 'schema_version' if needed.

JSONL files
- functions.jsonl
  Fields per line (JSON object):
  - id (int, sequential within one scan)
  - name (str)
  - qualified_name (str)
  - signature (str)
  - return_type (str)
  - params (list[{name, type}])
  - calls (list[str])
  - file (str)
  - start_line (int), start_col (int), end_line (int), end_col (int)
  - language (str)
  - created_at (str, ISO-like), updated_at (str, ISO-like)
- types.jsonl
  Fields per line (JSON object):
  - id (int)
  - name (str)
  - qualified_name (str)
  - kind (str: struct/class/union/enum/typedef/type_alias)
  - underlying_type (str, for typedef/alias)
  - file/loc/language, created_at/updated_at (same as above)
- meta.json
  {
    "functions": N,
    "types": M,
    "generated_at": "...",
    "schema_version": 1,
    "source_root": "<abs path>"
  }
Usage:
  python -m jarvis.jarvis_c2rust.scanner --root /path/to/scan

Notes:
- If compile_commands.json is present, it will be used to improve parsing accuracy.
- If libclang is not found, an informative error will be raised with hints to set env:
  - LIBCLANG_PATH (directory) or CLANG_LIBRARY_FILE (full path)
  - LLVM_HOME (prefix containing lib/libclang.so)
"""

from __future__ import annotations


import json
import os

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set
import typer

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
        from clang import cindex  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "Failed to import clang.cindex. This tool supports clang 16-21.\n"
            "Fix:\n"
            "- pip install 'clang>=16,<22'\n"
            "- Ensure libclang (16-21) is installed (e.g., apt install llvm-21 clang-21 libclang-21-dev)\n"
            "- Set env CLANG_LIBRARY_FILE to the matching shared library, or LIBCLANG_PATH to its directory."
        ) from e

    # Verify Python clang bindings major version (if available)
    py_major: Optional[int] = None
    try:
        import clang as _clang  # type: ignore
        import re as _re
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
            f"Python 'clang' bindings major version must be one of {sorted(SUPPORTED_MAJORS)}.\n"
            "Fix:\n"
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
            try:
                ver = cstr.decode("utf-8", "ignore") if cstr else ""
            except Exception:
                # Fallback if restype not honored by platform
                ver = ctypes.cast(cstr, ctypes.c_char_p).value.decode("utf-8", "ignore") if cstr else ""
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
                f"CLANG_LIBRARY_FILE points to '{lib_file}', which is not libclang 16-21.\n"
                "Please set it to a supported libclang (e.g., /usr/lib/llvm-21/lib/libclang.so or matching version)."
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
        candidates.extend([
            base / "libclang.so",      # Linux
            base / "libclang.dylib",   # macOS
            base / "libclang.dll",     # Windows
        ])
        for cand in candidates:
            if cand.exists() and _ensure_supported_and_set(str(cand)):
                return cindex
        # If a directory is given but no valid supported version found, error out explicitly
        raise RuntimeError(
            f"LIBCLANG_PATH={lib_dir} does not contain libclang 16-21.\n"
            "Expected libclang.so.[16-21] (Linux) or libclang.dylib from llvm@16..@21 (macOS)."
        )

    # 3) LLVM_HOME
    llvm_home = os.environ.get("LLVM_HOME")
    if llvm_home:
        p = Path(llvm_home) / "lib"
        candidates: List[Path] = []
        for maj in (21, 20, 19, 18, 17, 16):
            candidates.append(p / f"libclang.so.{maj}")
        candidates.extend([
            p / "libclang.so",
            p / "libclang.dylib",
            p / "libclang.dll",
        ])
        for cand in candidates:
            if cand.exists() and _ensure_supported_and_set(str(cand)):
                return cindex

    # 4) Common locations for versions 16-21
    import platform as _platform
    sys_name = _platform.system()
    path_candidates: List[Path] = []
    if sys_name == "Linux":
        for maj in (21, 20, 19, 18, 17, 16):
            path_candidates.extend([
                Path(f"/usr/lib/llvm-{maj}/lib/libclang.so.{maj}"),
                Path(f"/usr/lib/llvm-{maj}/lib/libclang.so"),
            ])
        # Generic fallbacks
        path_candidates.extend([
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
        ])
    elif sys_name == "Darwin":
        # Homebrew llvm@N formulas
        for maj in (21, 20, 19, 18, 17, 16):
            path_candidates.append(Path(f"/opt/homebrew/opt/llvm@{maj}/lib/libclang.dylib"))
            path_candidates.append(Path(f"/usr/local/opt/llvm@{maj}/lib/libclang.dylib"))
        # Generic llvm formula path (may be symlinked to a specific version)
        path_candidates.extend([
            Path("/opt/homebrew/opt/llvm/lib/libclang.dylib"),
            Path("/usr/local/opt/llvm/lib/libclang.dylib"),
        ])
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
        "Failed to locate libclang 16-21. This tool supports clang 16-21.\n"
        "Fix options:\n"
        "- On Ubuntu/Debian: sudo apt-get install -y llvm-21 clang-21 libclang-21-dev (or 20/19/18/17/16).\n"
        "- On macOS (Homebrew): brew install llvm@21 (or @20/@19/@18/@17/@16).\n"
        "- On Arch Linux: ensure clang provides /usr/lib/libclang.so (it usually does) or set CLANG_LIBRARY_FILE explicitly.\n"
        "- Then set env (if not auto-detected):\n"
        "    export CLANG_LIBRARY_FILE=/usr/lib/llvm-21/lib/libclang.so   # Linux (adjust version)\n"
        "    export CLANG_LIBRARY_FILE=/opt/homebrew/opt/llvm@21/lib/libclang.dylib  # macOS (adjust version)\n"
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

    mapping: Dict[str, List[str]] = {}
    for entry in data:
        file_path = Path(entry.get("file", "")).resolve()
        if not file_path:
            continue
        if "arguments" in entry and isinstance(entry["arguments"], list):
            # arguments usually includes the compiler as argv[0]
            args = entry["arguments"][1:] if entry["arguments"] else []
        else:
            # fallback to split command string
            cmd = entry.get("command", "")
            import shlex
            parts = shlex.split(cmd) if cmd else []
            args = parts[1:] if parts else []

        # Clean args: drop compile-only/output flags that confuse libclang
        cleaned: List[str] = []
        skip_next = False
        for a in args:
            if skip_next:
                skip_next = False
                continue
            if a in ("-c",):
                continue
            if a in ("-o", "-MF"):
                skip_next = True
                continue
            if a.startswith("-o"):
                continue
            cleaned.append(a)
        mapping[str(file_path)] = cleaned
    return mapping

# ---------------------------
# File discovery
# ---------------------------
SOURCE_EXTS: Set[str] = {
    ".c", ".cc", ".cpp", ".cxx", ".C",
    ".h", ".hh", ".hpp", ".hxx",
}

def iter_source_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix in SOURCE_EXTS:
            yield p.resolve()


# ---------------------------
# AST utilities
# ---------------------------
def get_qualified_name(cursor) -> str:
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


def collect_params(cursor) -> List[Dict[str, str]]:
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


def collect_calls(cursor) -> List[str]:
    """
    Collect called function names within a function definition.
    """
    calls: List[str] = []

    def walk(node):
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


def is_function_like(cursor) -> bool:
    return cursor.kind.name in {
        "FUNCTION_DECL",
        "CXX_METHOD",
        "CONSTRUCTOR",
        "DESTRUCTOR",
        "FUNCTION_TEMPLATE",
    }


def lang_from_cursor(cursor) -> str:
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
def scan_file(cindex, file_path: Path, args: List[str]) -> List[FunctionInfo]:
    index = cindex.Index.create()
    tu = index.parse(
        str(file_path),
        args=args,
        options=0,  # need bodies to collect calls
    )
    functions: List[FunctionInfo] = []

    def visit(node):
        # Only consider functions with definitions in this file
        if is_function_like(node) and node.is_definition():
            loc_file = node.location.file
            if loc_file is not None and Path(loc_file.name).resolve() == file_path.resolve():
                try:
                    name = node.spelling or ""
                    qualified_name = get_qualified_name(node)
                    signature = node.displayname or name
                    try:
                        return_type = node.result_type.spelling  # not available for constructors/destructors
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
    Scan a directory for C/C++ functions and store results into JSONL/JSON.

    Returns the path to functions.jsonl.
      - functions.jsonl: one JSON object per function
      - types.jsonl:     one JSON object per type
      - meta.json:       summary counts and timestamp
    """
    scan_root = scan_root.resolve()
    out_dir = scan_root / ".jarvis" / "c2rust"
    out_dir.mkdir(parents=True, exist_ok=True)

    # JSONL/JSON outputs
    functions_jsonl = out_dir / "functions.jsonl"
    types_jsonl = out_dir / "types.jsonl"
    meta_json = out_dir / "meta.json"

    # Prepare libclang
    cindex = _try_import_libclang()
    # Fallback safeguard: if loader returned None, try importing directly
    if cindex is None:
        try:
            from clang import cindex as _ci  # type: ignore
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
            candidates: List[str] = []
            if sys_name == "Linux":
                candidates = [
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
                candidates = [
                    "/opt/homebrew/opt/llvm/lib/libclang.dylib",
                    "/usr/local/opt/llvm/lib/libclang.dylib",
                ]

            good = [p for p in candidates if Path(p).exists() and _has_symbol(p, "clang_getOffsetOfBase")]
            hint = ""
            if good:
                hint = f"\nSuggested library with required symbol:\n  export CLANG_LIBRARY_FILE={good[0]}\nThen rerun: jarvis-c2rust scan -r {scan_root}"

            typer.secho(
                "[c2rust-scanner] Detected libclang/python bindings mismatch (undefined symbol)."
                f"\nDetail: {msg}"
                "\nThis usually means your Python 'clang' bindings are newer than the installed libclang."
                "\nFix options:\n"
                "- Install/update libclang to match your Python 'clang' major version (e.g., 16-21).\n"
                "- Or pin Python 'clang' to match your system libclang (e.g., pip install 'clang>=16,<22').\n"
                "- Or set CLANG_LIBRARY_FILE to a matching libclang shared library.\n"
                f"{hint}",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=2)
        else:
            # Other initialization errors: surface and exit
            typer.secho(f"[c2rust-scanner] libclang init failed: {e}", fg=typer.colors.RED, err=True)
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
    print(f"[c2rust-scanner] Scanning {total_files} files under {scan_root}")

    scanned = 0
    total_functions = 0
    total_types = 0

    # JSONL writers
    now_ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    fn_id_seq = 1
    tp_id_seq = 1

    def _fn_record(fn: FunctionInfo, id_val: int) -> Dict[str, Any]:
        return {
            "id": id_val,
            "name": fn.name,
            "qualified_name": fn.qualified_name,
            "signature": fn.signature,
            "return_type": fn.return_type,
            "params": fn.params,
            "calls": fn.calls,
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
        return {
            "id": id_val,
            "name": tp.name,
            "qualified_name": tp.qualified_name,
            "kind": tp.kind,
            "underlying_type": tp.underlying_type,
            "file": tp.file,
            "start_line": tp.start_line,
            "start_col": tp.start_col,
            "end_line": tp.end_line,
            "end_col": tp.end_col,
            "language": tp.language,
            "created_at": now_ts,
            "updated_at": now_ts,
        }

    # Open JSONL files
    f_fn = functions_jsonl.open("w", encoding="utf-8")
    f_tp = types_jsonl.open("w", encoding="utf-8")
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
                    candidates: List[str] = []
                    if sys_name == "Linux":
                        candidates = [
                            "/usr/lib/llvm-20/lib/libclang.so",
                            "/usr/lib/llvm-19/lib/libclang.so",
                            "/usr/lib/llvm-18/lib/libclang.so",
                            "/usr/lib/libclang.so",
                            "/usr/local/lib/libclang.so",
                        ]
                    elif sys_name == "Darwin":
                        candidates = [
                            "/opt/homebrew/opt/llvm/lib/libclang.dylib",
                            "/usr/local/opt/llvm/lib/libclang.dylib",
                        ]

                    good = [lp for lp in candidates if Path(lp).exists() and _has_symbol(lp, "clang_getOffsetOfBase")]
                    hint = ""
                    if good:
                        hint = f"\nSuggested library with required symbol:\n  export CLANG_LIBRARY_FILE={good[0]}\nThen rerun: jarvis-c2rust scan -r {scan_root}"

                    typer.secho(
                        "[c2rust-scanner] Detected libclang/python bindings mismatch during parsing (undefined symbol)."
                        f"\nDetail: {msg}"
                        "\nThis usually means your Python 'clang' bindings are newer than the installed libclang."
                        "\nFix options:\n"
                        "- Install/update libclang to match your Python 'clang' major version (e.g., 19/20).\n"
                        "- Or pin Python 'clang' to match your system libclang (e.g., pip install 'clang==18.*').\n"
                        "- Or set CLANG_LIBRARY_FILE to a matching libclang shared library.\n"
                        f"{hint}",
                        fg=typer.colors.RED,
                        err=True,
                    )
                    raise typer.Exit(code=2)

                # Try without args as fallback for regular parse errors
                try:
                    funcs = scan_file(cindex, p, [])
                except Exception:
                    print(f"[c2rust-scanner] Failed to parse {p}: {e}", file=sys.stderr)
                    continue

            # Write JSONL
            for fn in funcs:
                rec = _fn_record(fn, fn_id_seq)
                f_fn.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fn_id_seq += 1
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
                trec = _tp_record(t, tp_id_seq)
                f_tp.write(json.dumps(trec, ensure_ascii=False) + "\n")
                tp_id_seq += 1
            total_types += len(types)

            scanned += 1
            if scanned % 20 == 0 or scanned == total_files:
                print(f"[c2rust-scanner] Progress: {scanned}/{total_files} files, {total_functions} functions, {total_types} types")
    finally:
        try:
            f_fn.close()
        except Exception:
            pass
        try:
            f_tp.close()
        except Exception:
            pass

    # Write meta.json
    meta = {
        "functions": total_functions,
        "types": total_types,
        "generated_at": now_ts,
        "schema_version": 1,
        "source_root": str(scan_root),
    }
    try:
        meta_json.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    print(f"[c2rust-scanner] Done. Functions collected: {total_functions}, Types collected: {total_types}")
    print(f"[c2rust-scanner] JSONL written: {functions_jsonl} (functions), {types_jsonl} (types)")
    print(f"[c2rust-scanner] Meta written: {meta_json}")
    return functions_jsonl

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




TYPE_KINDS: Set[str] = {
    "STRUCT_DECL",
    "UNION_DECL",
    "ENUM_DECL",
    "CXX_RECORD_DECL",   # C++ class/struct/union
    "TYPEDEF_DECL",
    "TYPE_ALIAS_DECL",
}


def scan_types_file(cindex, file_path: Path, args: List[str]) -> List[TypeInfo]:
    index = cindex.Index.create()
    tu = index.parse(
        str(file_path),
        args=args,
        options=0,
    )
    types: List[TypeInfo] = []

    def visit(node):
        kind = node.kind.name
        # Filter by file
        loc_file = node.location.file
        if loc_file is None or Path(loc_file.name).resolve() != file_path.resolve():
            for ch in node.get_children():
                visit(ch)
            return

        if kind in TYPE_KINDS:
            # Accept full definitions for record/enum; typedef/alias are inherently definitions
            need_def = kind in {"STRUCT_DECL", "UNION_DECL", "ENUM_DECL", "CXX_RECORD_DECL"}
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


def generate_dot_from_db(db_path: Path, out_path: Path) -> None:
    # Generate a call dependency graph (DOT) from JSONL data.
    def _resolve_functions_jsonl_path(hint: Path) -> Path:
        p = Path(hint)
        if p.is_file():
            if p.suffix.lower() == ".jsonl":
                return p
            # old db path: use sibling functions.jsonl
            if p.suffix.lower() in (".db", ".sqlite", ".sqlite3"):
                cand = p.parent / "functions.jsonl"
                if cand.exists():
                    return cand
        if p.is_dir():
            cand = p / "functions.jsonl"
            if cand.exists():
                return cand
        # fallback
        return Path(".") / ".jarvis" / "c2rust" / "functions.jsonl"

    fjsonl = _resolve_functions_jsonl_path(db_path)
    if not fjsonl.exists():
        raise FileNotFoundError(f"functions.jsonl not found: {fjsonl}")

    # Load function records from JSONL
    rows: List[Any] = []
    with open(fjsonl, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                rows.append((
                    int(obj.get("id") or len(rows) + 1),
                    obj.get("name") or "",
                    obj.get("qualified_name") or "",
                    obj.get("signature") or "",
                    obj.get("calls") or [],
                ))
            except Exception:
                continue

    # Build node map
    node_id_map: Dict[int, str] = {}      # function id -> dot node id
    name_to_node: Dict[str, str] = {}     # name/qualified_name -> dot node id
    node_labels: Dict[str, str] = {}      # dot node id -> label
    edges = set()

    for row in rows:
        fid = int(row[0])
        name = row[1] or ""
        qname = row[2] or ""
        signature = row[3] or ""
        dot_id = f"f{fid}"
        node_id_map[fid] = dot_id
        label_base = qname or name or f"fn_{fid}"
        label = label_base
        if signature and signature != label_base:
            label = f"{label_base}\\n{signature}"
        node_labels[dot_id] = label
        if label_base:
            name_to_node[label_base] = dot_id
        if name:
            name_to_node.setdefault(name, dot_id)
        if qname:
            name_to_node.setdefault(qname, dot_id)

    # External nodes cache
    external_nodes: Dict[str, str] = {}  # callee name -> dot node id
    ext_count = 0

    # Build edges
    for row in rows:
        fid = int(row[0])
        dot_src = node_id_map.get(fid)
        if not dot_src:
            continue
        calls = row[4] or []
        if not isinstance(calls, list):
            continue
        for callee in calls:
            if not isinstance(callee, str) or not callee:
                continue
            if callee in name_to_node:
                dot_dst = name_to_node[callee]
            else:
                dot_dst = external_nodes.get(callee)
                if dot_dst is None:
                    dot_dst = f"ext{ext_count}"
                    ext_count += 1
                    external_nodes[callee] = dot_dst
                    node_labels[dot_dst] = callee
            edges.add((dot_src, dot_dst))

    # Write DOT
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("digraph callgraph {\n")
        f.write("  rankdir=LR;\n")
        f.write("  graph [fontsize=10];\n")
        f.write("  node  [fontsize=10];\n")
        f.write("  edge  [fontsize=9];\n")

        # Emit nodes: internal (box), external (ellipse dashed gray)
        for dot_id, label in node_labels.items():
            is_external = dot_id.startswith("ext")
            safe_label = label.replace("\\", "\\\\").replace('"', '\\"')
            if is_external:
                f.write(f'  {dot_id} [label="{safe_label}", shape=ellipse, style=dashed, color=gray50, fontcolor=gray30];\n')
            else:
                f.write(f'  {dot_id} [label="{safe_label}", shape=box];\n')

        # Emit edges
        for src, dst in sorted(edges):
            f.write(f"  {src} -> {dst};\n")

        f.write("}\n")


def find_root_function_ids(db_path: Path) -> List[int]:
    # Return IDs of functions with no callers (roots) by reading functions.jsonl.
    def _resolve_functions_jsonl_path(hint: Path) -> Path:
        p = Path(hint)
        if p.is_file():
            if p.suffix.lower() == ".jsonl":
                return p
            if p.suffix.lower() in (".db", ".sqlite", ".sqlite3"):
                cand = p.parent / "functions.jsonl"
                if cand.exists():
                    return cand
        if p.is_dir():
            cand = p / "functions.jsonl"
            if cand.exists():
                return cand
        return Path(".") / ".jarvis" / "c2rust" / "functions.jsonl"

    fjsonl = _resolve_functions_jsonl_path(db_path)
    if not fjsonl.exists():
        raise FileNotFoundError(f"functions.jsonl not found: {fjsonl}")

    # Load functions
    records: List[Any] = []
    with open(fjsonl, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                fid = int(obj.get("id") or len(records) + 1)
                name = obj.get("name") or ""
                qname = obj.get("qualified_name") or ""
                calls = obj.get("calls") or []
                records.append((fid, name, qname, calls))
            except Exception:
                continue

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
    for fid, _name, _qname, calls in records:
        fid = int(fid)
        if not isinstance(calls, list):
            continue
        for callee in calls:
            if not isinstance(callee, str) or not callee:
                continue
            callee_id = name_to_id.get(callee)
            if callee_id is not None and callee_id != fid:
                non_roots.add(callee_id)

    root_ids = sorted(list(all_ids - non_roots))
    return root_ids


def compute_translation_order_jsonl(db_path: Path, out_path: Optional[Path] = None) -> Path:
    """
    Compute translation order considering multi-roots and recursive cycles, then write order to JSONL.
    Steps:
    - Load functions.jsonl and build internal call graph (ID-based).
    - Find root functions (no callers), sort roots by the size of their reachable subgraph (desc).
    - Compute SCCs to collapse cycles; perform topological ordering on the condensed DAG from leaves to roots
      (i.e., nodes/components with no dependencies/callees first) using reversed edges.
    - Merge components order per root priority: for each root in sorted roots, emit components' nodes in leaves-first order,
      only those reachable from that root and not yet emitted; finally emit remaining nodes.
    - Write each emitted step as one JSON object line:
      {
        "step": int,
        "ids": [function_id, ...],    # a group if multiple nodes in SCC or multiple nodes selected
        "group": bool,
        "roots": [root_id],           # the root this step is attributed to (empty if residual)
        "created_at": "YYYY-MM-DDTHH:MM:SS"
      }
    """
    def _resolve_functions_jsonl_path(hint: Path) -> Path:
        p = Path(hint)
        if p.is_file():
            if p.suffix.lower() == ".jsonl":
                return p
            if p.suffix.lower() in (".db", ".sqlite", ".sqlite3"):
                cand = p.parent / "functions.jsonl"
                if cand.exists():
                    return cand
        if p.is_dir():
            cand = p / "functions.jsonl"
            if cand.exists():
                return cand
        return Path(".") / ".jarvis" / "c2rust" / "functions.jsonl"

    fjsonl = _resolve_functions_jsonl_path(db_path)
    if not fjsonl.exists():
        raise FileNotFoundError(f"functions.jsonl not found: {fjsonl}")

    # Load functions and build internal adjacency
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
            calls = obj.get("calls") or []
            if not isinstance(calls, list):
                calls = []
            calls = [c for c in calls if isinstance(c, str) and c]
            by_id[fid] = {"name": nm, "qname": qn}
            if nm:
                name_to_id.setdefault(nm, fid)
            if qn:
                name_to_id.setdefault(qn, fid)
            adj_names[fid] = calls

    # Convert name-based adjacency to id-based adjacency (internal edges only)
    adj_ids: Dict[int, List[int]] = {}
    all_ids: List[int] = sorted(by_id.keys())
    for src in all_ids:
        internal: List[int] = []
        for callee in adj_names.get(src, []):
            cid = name_to_id.get(callee)
            if cid is not None and cid != src:
                internal.append(cid)
        # dedupe
        try:
            internal = list(dict.fromkeys(internal))
        except Exception:
            internal = sorted(list(set(internal)))
        adj_ids[src] = internal

    # Root detection and sorting by reachable size (desc)
    try:
        roots = find_root_function_ids(db_path)
    except Exception:
        roots = []

    def _reachable(start_id: int) -> Set[int]:
        visited: Set[int] = set()
        stack: List[int] = [start_id]
        visited.add(start_id)
        while stack:
            s = stack.pop()
            for v in adj_ids.get(s, []):
                if v not in visited:
                    visited.add(v)
                    stack.append(v)
        return visited

    root_reach: Dict[int, Set[int]] = {rid: _reachable(rid) for rid in roots}
    roots_sorted: List[int] = sorted(roots, key=lambda r: len(root_reach.get(r, set())), reverse=True)

    # Tarjan SCC to handle cycles
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

        # If v is a root node, pop the stack and output an SCC
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

    # Map id -> component index
    id2comp: Dict[int, int] = {}
    for i, comp in enumerate(sccs):
        for nid in comp:
            id2comp[nid] = i

    # Build reversed component DAG (callee -> caller as edges), for leaves-first topo
    comp_count = len(sccs)
    comp_rev_adj: Dict[int, Set[int]] = {i: set() for i in range(comp_count)}  # comp_v -> set(comp_u) where u calls v
    indeg: Dict[int, int] = {i: 0 for i in range(comp_count)}

    for u in all_ids:
        cu = id2comp[u]
        for v in adj_ids.get(u, []):
            cv = id2comp[v]
            if cu != cv:
                # reversed: cv -> cu (v dependency to u)
                if cu not in comp_rev_adj[cv]:
                    comp_rev_adj[cv].add(cu)

    # indegree on reversed DAG
    for cv, succs in comp_rev_adj.items():
        for cu in succs:
            indeg[cu] += 1

    # Kahn's algorithm on reversed DAG -> leaves-first component order
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

    # If not all components are ordered (shouldn't happen), append remaining to stabilize
    if len(comp_order) < comp_count:
        remaining = [i for i in range(comp_count) if i not in comp_order]
        comp_order.extend(sorted(remaining))

    # Emit steps per root priority
    emitted: Set[int] = set()
    steps: List[Dict[str, Any]] = []
    now_ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())

    def _emit_for_root(root_id: Optional[int]) -> None:
        reach = root_reach.get(root_id, set()) if root_id is not None else None
        for comp_idx in comp_order:
            comp_nodes = sccs[comp_idx]
            # Select nodes in this component that are both reachable (if root given) and not yet emitted
            selected: List[int] = []
            for nid in comp_nodes:
                if nid in emitted:
                    continue
                if reach is None or nid in reach:
                    selected.append(nid)
            if selected:
                # Mark emitted
                for nid in selected:
                    emitted.add(nid)
                steps.append({
                    "step": len(steps) + 1,
                    "ids": sorted(selected),
                    "group": len(selected) > 1,
                    "roots": [root_id] if root_id is not None else [],
                    "created_at": now_ts,
                })

    # Per-root emission in priority order
    for rid in roots_sorted:
        _emit_for_root(rid)
    # Residual nodes not covered by any root (e.g., cycles not reachable from any root or orphan constructs)
    _emit_for_root(None)

    # Prepare output path
    if out_path is None:
        out_path = fjsonl.parent / "translation_order.jsonl"
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Write JSONL
    with open(out_path, "w", encoding="utf-8") as fo:
        for st in steps:
            fo.write(json.dumps(st, ensure_ascii=False) + "\n")

    return out_path


def export_root_subgraphs_to_dir(db_path: Path, out_dir: Path) -> List[Path]:
    # Generate per-root subgraph DOT files from functions.jsonl into out_dir.
    def _resolve_functions_jsonl_path(hint: Path) -> Path:
        p = Path(hint)
        if p.is_file():
            if p.suffix.lower() == ".jsonl":
                return p
            if p.suffix.lower() in (".db", ".sqlite", ".sqlite3"):
                cand = p.parent / "functions.jsonl"
                if cand.exists():
                    return cand
        if p.is_dir():
            cand = p / "functions.jsonl"
            if cand.exists():
                return cand
        return Path(".") / ".jarvis" / "c2rust" / "functions.jsonl"

    fjsonl = _resolve_functions_jsonl_path(db_path)
    if not fjsonl.exists():
        raise FileNotFoundError(f"functions.jsonl not found: {fjsonl}")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load functions
    by_id: Dict[int, Dict[str, str]] = {}
    name_to_id: Dict[str, int] = {}
    adj: Dict[int, List[str]] = {}

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
            sig = obj.get("signature") or ""
            calls = obj.get("calls") or []
            if not isinstance(calls, list):
                calls = []
            calls = [c for c in calls if isinstance(c, str) and c]

            by_id[fid] = {"name": nm, "qname": qn, "sig": sig}
            if nm:
                name_to_id.setdefault(nm, fid)
            if qn:
                name_to_id.setdefault(qn, fid)
            adj[fid] = calls

    def base_label(fid: int) -> str:
        meta = by_id.get(fid, {})
        base = meta.get("qname") or meta.get("name") or f"fn_{fid}"
        sig = meta.get("sig") or ""
        if sig and sig != base:
            return f"{base}\\n{sig}"
        return base

    def sanitize_filename(s: str) -> str:
        if not s:
            return "root"
        s = s.replace("::", "__")
        return "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in s)[:120]

    generated: List[Path] = []
    root_ids = find_root_function_ids(db_path)

    for rid in root_ids:
        # BFS/DFS over internal calls from the root
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

        # Build nodes and edges for this subgraph
        node_labels: Dict[str, str] = {}
        external_nodes: Dict[str, str] = {}
        ext_count = 0
        edges = set()

        id_to_node = {fid: f"f{fid}" for fid in visited}

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
        root_base = by_id.get(rid, {}).get("qname") or by_id.get(rid, {}).get("name") or f"fn_{rid}"
        fname = f"subgraph_root_{rid}_{sanitize_filename(root_base)}.dot"
        out_path = out_dir / fname
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("digraph callgraph_sub {\n")
            f.write("  rankdir=LR;\n")
            f.write("  graph [fontsize=10];\n")
            f.write("  node  [fontsize=10];\n")
            f.write("  edge  [fontsize=9];\n")

            # Emit nodes
            for nid, lbl in node_labels.items():
                safe_label = lbl.replace("\\", "\\\\").replace('"', '\\"')
                if nid.startswith("ext"):
                    f.write(f'  {nid} [label="{safe_label}", shape=ellipse, style=dashed, color=gray50, fontcolor=gray30];\n')
                else:
                    f.write(f'  {nid} [label="{safe_label}", shape=box];\n')

            # Emit edges
            for s, d in sorted(edges):
                f.write(f"  {s} -> {d};\n")

            f.write("}\n")

        generated.append(out_path)

    return generated


def run_scan(
    dot: Optional[Path] = None,
    only_dot: bool = False,
    subgraphs_dir: Optional[Path] = None,
    only_subgraphs: bool = False,
    png: bool = False,
) -> None:
    # Scan for C/C++ functions and persist results to JSONL; optionally generate DOT.
    # Determine data path
    root = Path('.')
    data_path = Path('.') / ".jarvis" / "c2rust" / "functions.jsonl"

    # Helper: render a DOT file to PNG using Graphviz 'dot'
    def _render_dot_to_png(dot_file: Path, png_out: Optional[Path] = None) -> Path:
        try:
            from shutil import which
            import subprocess
        except Exception as _e:
            raise RuntimeError(f"Environment issue while preparing PNG rendering: {_e}")
        exe = which("dot")
        if not exe:
            raise RuntimeError("Graphviz 'dot' not found in PATH. Please install graphviz and ensure 'dot' is available.")
        dot_file = Path(dot_file)
        if png_out is None:
            png_out = dot_file.with_suffix(".png")
        else:
            png_out = Path(png_out)
        png_out.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run([exe, "-Tpng", str(dot_file), "-o", str(png_out)], check=True)
        except FileNotFoundError:
            raise RuntimeError("Graphviz 'dot' executable not found.")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"'dot' failed to render PNG for {dot_file}: {e}")
        return png_out

    if not (only_dot or only_subgraphs):
        try:
            scan_directory(root)
            # After data generated, compute translation order JSONL
            try:
                order_path = compute_translation_order_jsonl(data_path)
                typer.secho(f"[c2rust-scanner] Translation order written: {order_path}", fg=typer.colors.GREEN)
            except Exception as e2:
                typer.secho(f"[c2rust-scanner] Failed to compute translation order: {e2}", fg=typer.colors.RED, err=True)
        except Exception as e:
            typer.secho(f"[c2rust-scanner] Error: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    else:
        # Only-generate mode (no rescan)
        if not data_path.exists():
            typer.secho(f"[c2rust-scanner] Data not found: {data_path}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)
        if only_dot and dot is None:
            typer.secho("[c2rust-scanner] --only-dot requires --dot to specify output file", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)
        if only_subgraphs and subgraphs_dir is None:
            typer.secho("[c2rust-scanner] --only-subgraphs requires --subgraphs-dir to specify output directory", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)
        # Data exists: compute translation order based on current JSONL
        try:
            order_path = compute_translation_order_jsonl(data_path)
            typer.secho(f"[c2rust-scanner] Translation order written: {order_path}", fg=typer.colors.GREEN)
        except Exception as e2:
            typer.secho(f"[c2rust-scanner] Failed to compute translation order: {e2}", fg=typer.colors.RED, err=True)

    # Generate DOT (global) if requested
    if dot is not None:
        try:
            generate_dot_from_db(data_path, dot)
            typer.secho(f"[c2rust-scanner] DOT written: {dot}", fg=typer.colors.GREEN)
            if png:
                png_path = _render_dot_to_png(dot)
                typer.secho(f"[c2rust-scanner] PNG written: {png_path}", fg=typer.colors.GREEN)
        except Exception as e:
            typer.secho(f"[c2rust-scanner] Failed to write DOT/PNG: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

    # Generate per-root subgraphs if requested
    if subgraphs_dir is not None:
        try:
            files = export_root_subgraphs_to_dir(data_path, subgraphs_dir)
            if png:
                png_count = 0
                for dp in files:
                    try:
                        _render_dot_to_png(dp)
                        png_count += 1
                    except Exception as _e:
                        # Fail fast on PNG generation error for subgraphs to make issues visible
                        raise
                typer.secho(
                    f"[c2rust-scanner] Root subgraphs written: {len(files)} DOTs and {png_count} PNGs -> {subgraphs_dir}",
                    fg=typer.colors.GREEN,
                )
            else:
                typer.secho(
                    f"[c2rust-scanner] Root subgraphs written: {len(files)} files -> {subgraphs_dir}",
                    fg=typer.colors.GREEN,
                )
        except Exception as e:
            typer.secho(f"[c2rust-scanner] Failed to write subgraph DOTs/PNGs: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)


