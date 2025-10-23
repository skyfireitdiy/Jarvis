#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
C/C++ function scanner and call graph extractor using libclang.

Design decisions:
- Parser: clang.cindex (libclang) for robust C/C++ AST with precise types and locations.
- Output: SQLite database at <scan_root>/.jarvis/c2rust/functions.db
- Schema: Single 'functions' table meeting current requirement, storing calls as JSON.
  Future: can add 'call_relations' table if needed.

Table: functions
- id INTEGER PRIMARY KEY AUTOINCREMENT
- name TEXT NOT NULL
- qualified_name TEXT
- signature TEXT
- return_type TEXT
- params_json TEXT            -- JSON array: [{"name": "...", "type": "..."}]
- calls_json TEXT             -- JSON array: ["callee1", "ns::Class::method", ...]
- file TEXT NOT NULL
- start_line INTEGER
- start_col INTEGER
- end_line INTEGER
- end_col INTEGER
- language TEXT
- created_at TEXT
- updated_at TEXT
UNIQUE(name, file, start_line, start_col) ON CONFLICT IGNORE

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
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

# ---------------------------
# libclang loader
# ---------------------------
def _try_import_libclang() -> "clang.cindex":
    """
    Load clang.cindex and force libclang 18. This project only supports clang 18.
    Resolution order:
    1) Respect CLANG_LIBRARY_FILE (must be clang 18)
    2) Respect LIBCLANG_PATH (pick libclang.so.18 / libclang.dylib in that dir)
    3) Respect LLVM_HOME/lib/libclang.*
    4) Probe common locations for version 18 only
    If Python bindings are not 18 or libclang is not 18, raise with actionable hints.
    """
    try:
        from clang import cindex  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "Failed to import clang.cindex. This tool only supports clang 18.\n"
            "Fix:\n"
            "- pip install 'clang==18.*'\n"
            "- Ensure libclang 18 is installed (e.g., apt install llvm-18 clang-18 libclang-18-dev)\n"
            "- Set env CLANG_LIBRARY_FILE to the 18.x shared library, or LIBCLANG_PATH to its directory."
        ) from e

    # Verify Python clang bindings are 18.x
    py_major: Optional[int] = None
    try:
        import clang as _clang  # type: ignore
        import re as _re
        v = getattr(_clang, "__version__", None)
        if v:
            m = _re.match(r"(\d+)", str(v))
            if m:
                py_major = int(m.group(1))
    except Exception:
        py_major = None

    # If version is known and not 18, fail; if unknown (None), proceed and rely on libclang probing
    if py_major is not None and py_major != 18:
        raise RuntimeError(
            "Python 'clang' bindings must be version 18.x for this tool.\n"
            "Fix:\n"
            "- pip install --upgrade 'clang==18.*'"
        )

    # Helper to probe libclang major version
    def _probe_major_from_lib(path: str) -> Optional[int]:
        try:
            import ctypes, re as _re
            class CXString(ctypes.Structure):
                _fields_ = [("data", ctypes.c_void_p), ("private_flags", ctypes.c_uint)]
            lib = ctypes.CDLL(path)
            lib.clang_getClangVersion.restype = CXString
            lib.clang_getCString.argtypes = [CXString]
            lib.clang_disposeString.argtypes = [CXString]
            s = lib.clang_getClangVersion()
            cstr = lib.clang_getCString(s)
            ver = ctypes.cast(cstr, ctypes.c_char_p).value
            lib.clang_disposeString(s)
            if ver:
                v = ver.decode("utf-8", "ignore")
                m = _re.search(r"clang version (\d+)", v)
                if m:
                    return int(m.group(1))
        except Exception:
            return None
        return None

    def _ensure_v18_and_set(lib_path: str) -> bool:
        major = _probe_major_from_lib(lib_path)
        if major == 18:
            try:
                cindex.Config.set_library_file(lib_path)
                return True
            except Exception:
                return False
        return False

    # 1) CLANG_LIBRARY_FILE
    lib_file = os.environ.get("CLANG_LIBRARY_FILE")
    if lib_file and Path(lib_file).exists():
        if _ensure_v18_and_set(lib_file):
            return cindex
        else:
            raise RuntimeError(
                f"CLANG_LIBRARY_FILE points to '{lib_file}', which is not libclang 18.x.\n"
                "Please set it to the clang-18 library (e.g., /usr/lib/llvm-18/lib/libclang.so)."
            )

    # 2) LIBCLANG_PATH
    lib_dir = os.environ.get("LIBCLANG_PATH")
    if lib_dir and Path(lib_dir).exists():
        base = Path(lib_dir)
        candidates = [
            base / "libclang.so.18",
            base / "libclang.so",
            base / "libclang.dylib",   # macOS
            base / "libclang.dll",     # Windows
        ]
        for cand in candidates:
            if cand.exists() and _ensure_v18_and_set(str(cand)):
                return cindex
        # If a directory is given but no valid 18 found, error out explicitly
        raise RuntimeError(
            f"LIBCLANG_PATH={lib_dir} does not contain libclang 18.x.\n"
            "Expected libclang.so.18 (Linux) or libclang.dylib from llvm@18 (macOS)."
        )

    # 3) LLVM_HOME
    llvm_home = os.environ.get("LLVM_HOME")
    if llvm_home:
        p = Path(llvm_home) / "lib"
        for cand in [
            p / "libclang.so.18",
            p / "libclang.so",
            p / "libclang.dylib",
            p / "libclang.dll",
        ]:
            if cand.exists() and _ensure_v18_and_set(str(cand)):
                return cindex

    # 4) Common locations for version 18 only
    import platform as _platform
    sys_name = _platform.system()
    candidates: List[Path] = []
    if sys_name == "Linux":
        candidates = [
            Path("/usr/lib/llvm-18/lib/libclang.so.18"),
            Path("/usr/lib/llvm-18/lib/libclang.so"),
            Path("/usr/local/lib/libclang.so.18"),
            Path("/usr/local/lib/libclang.so"),
            Path("/usr/lib/libclang.so.18"),
        ]
    elif sys_name == "Darwin":
        # Homebrew llvm@18
        candidates = [
            Path("/opt/homebrew/opt/llvm@18/lib/libclang.dylib"),
            Path("/usr/local/opt/llvm@18/lib/libclang.dylib"),
            # Some systems may symlink without @18, still verify major=18
            Path("/opt/homebrew/opt/llvm/lib/libclang.dylib"),
            Path("/usr/local/opt/llvm/lib/libclang.dylib"),
        ]
    else:
        # Best-effort on other systems
        candidates = [
            Path("C:/Program Files/LLVM/bin/libclang.dll"),
        ]

    for cand in candidates:
        if cand.exists() and _ensure_v18_and_set(str(cand)):
            return cindex

    # If we got here, we failed to locate a valid libclang 18
    raise RuntimeError(
        "Failed to locate libclang 18.x. This tool only supports clang 18.\n"
        "Fix options:\n"
        "- On Ubuntu/Debian: sudo apt-get install -y llvm-18 clang-18 libclang-18-dev\n"
        "- On macOS (Homebrew): brew install llvm@18\n"
        "- Then set env (if not auto-detected):\n"
        "    export CLANG_LIBRARY_FILE=/usr/lib/llvm-18/lib/libclang.so   # Linux\n"
        "    export CLANG_LIBRARY_FILE=/opt/homebrew/opt/llvm@18/lib/libclang.dylib  # macOS\n"
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
# SQLite helpers
# ---------------------------
def ensure_output_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS functions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            qualified_name TEXT,
            signature TEXT,
            return_type TEXT,
            params_json TEXT,
            calls_json TEXT,
            file TEXT NOT NULL,
            start_line INTEGER,
            start_col INTEGER,
            end_line INTEGER,
            end_col INTEGER,
            language TEXT,
            created_at TEXT,
            updated_at TEXT,
            UNIQUE(name, file, start_line, start_col) ON CONFLICT IGNORE
        )
        """
    )
    # Conversion status table (track C/C++ -> Rust conversion progress per function)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS function_conversion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            function_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','in_progress','converted','failed','ignored')),
            rust_name TEXT,
            rust_module TEXT,
            rust_signature TEXT,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY(function_id) REFERENCES functions(id) ON DELETE CASCADE,
            UNIQUE(function_id)
        )
        """
    )
    # Types table: store type definitions and their source locations
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            qualified_name TEXT,
            kind TEXT NOT NULL,            -- struct/class/union/enum/typedef/type_alias
            underlying_type TEXT,          -- for typedef/alias
            file TEXT NOT NULL,
            start_line INTEGER,
            start_col INTEGER,
            end_line INTEGER,
            end_col INTEGER,
            language TEXT,
            created_at TEXT,
            updated_at TEXT,
            UNIQUE(name, file, start_line, start_col) ON CONFLICT IGNORE
        )
        """
    )
    conn.commit()
    return conn


def insert_function(conn: sqlite3.Connection, fn: FunctionInfo) -> None:
    now = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    conn.execute(
        """
        INSERT OR IGNORE INTO functions
        (name, qualified_name, signature, return_type, params_json, calls_json, file,
         start_line, start_col, end_line, end_col, language, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fn.name,
            fn.qualified_name,
            fn.signature,
            fn.return_type,
            json.dumps(fn.params, ensure_ascii=False),
            json.dumps(fn.calls, ensure_ascii=False),
            fn.file,
            fn.start_line,
            fn.start_col,
            fn.end_line,
            fn.end_col,
            fn.language,
            now,
            now,
        ),
    )

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
    Scan a directory for C/C++ functions and store results into SQLite.

    Returns the path to the database.
    """
    scan_root = scan_root.resolve()
    out_dir = scan_root / ".jarvis" / "c2rust"
    out_dir.mkdir(parents=True, exist_ok=True)
    if db_path is None:
        db_path = out_dir / "functions.db"

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
                    "/usr/lib/llvm-20/lib/libclang.so",
                    "/usr/lib/llvm-19/lib/libclang.so",
                    "/usr/lib/llvm-18/lib/libclang.so",
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
                "- Install/update libclang to match your Python 'clang' major version (e.g., 19/20).\n"
                "- Or pin Python 'clang' to match your system libclang (e.g., pip install 'clang==18.*').\n"
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

    # Open DB
    conn = ensure_output_db(db_path)

    files = list(iter_source_files(scan_root))
    total_files = len(files)
    print(f"[c2rust-scanner] Scanning {total_files} files under {scan_root}")

    scanned = 0
    total_functions = 0

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
        for fn in funcs:
            insert_function(conn, fn)
        # Scan types in this file
        try:
            types = scan_types_file(cindex, p, args)
        except Exception:
            try:
                types = scan_types_file(cindex, p, [])
            except Exception:
                types = []
        for t in types:
            insert_type(conn, t)
        conn.commit()
        scanned += 1
        total_functions += len(funcs)
        if scanned % 20 == 0 or scanned == total_files:
            print(f"[c2rust-scanner] Progress: {scanned}/{total_files} files, {total_functions} functions")

    print(f"[c2rust-scanner] Done. Functions collected: {total_functions}")
    print(f"[c2rust-scanner] Database: {db_path}")
    conn.close()
    return db_path

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


def insert_type(conn: sqlite3.Connection, tp: TypeInfo) -> None:
    now = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    conn.execute(
        """
        INSERT OR IGNORE INTO types
        (name, qualified_name, kind, underlying_type, file,
         start_line, start_col, end_line, end_col, language, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tp.name,
            tp.qualified_name,
            tp.kind,
            tp.underlying_type,
            tp.file,
            tp.start_line,
            tp.start_col,
            tp.end_line,
            tp.end_col,
            tp.language,
            now,
            now,
        ),
    )


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
import typer

def generate_dot_from_db(db_path: Path, out_path: Path) -> None:
    """
    Generate a call dependency graph in DOT format from the SQLite database.
    - Internal nodes (functions found in DB): box shape
    - External callees not found in DB: dashed gray ellipse
    """
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT id, name, qualified_name, signature, calls_json FROM functions"
    ).fetchall()

    # Build node map
    node_id_map: Dict[int, str] = {}      # function id -> dot node id
    name_to_node: Dict[str, str] = {}     # name/qualified_name -> dot node id
    node_labels: Dict[str, str] = {}      # dot node id -> label
    edges: Set[Tuple[str, str]] = set()

    for row in rows:
        fid = int(row[0])
        name = row[1] or ""
        qname = row[2] or ""
        signature = row[3] or ""
        dot_id = f"f{fid}"
        node_id_map[fid] = dot_id
        label_base = qname or name or f"fn_{fid}"
        label = label_base
        # Prefer shorter label; append signature if helpful
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
        dot_src = node_id_map[fid]
        try:
            calls = json.loads(row[4] or "[]")
            if not isinstance(calls, list):
                calls = []
        except Exception:
            calls = []
        for callee in calls:
            if not isinstance(callee, str) or not callee:
                continue
            # Find internal target
            if callee in name_to_node:
                dot_dst = name_to_node[callee]
            else:
                # create external node
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

    conn.close()


def find_root_function_ids(db_path: Path) -> List[int]:
    """
    Find all 'root' functions in the database: functions that have no callers within the DB.
    A function is considered internal if it appears in the 'functions' table. To match calls,
    both qualified_name and name are considered.
    Returns a sorted list of function IDs.
    """
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    rows = cur.execute("SELECT id, name, qualified_name, calls_json FROM functions").fetchall()

    name_to_id: Dict[str, int] = {}
    all_ids: Set[int] = set()
    for fid, name, qname, _ in rows:
        fid = int(fid)
        all_ids.add(fid)
        if isinstance(name, str) and name:
            name_to_id.setdefault(name, fid)
        if isinstance(qname, str) and qname:
            name_to_id.setdefault(qname, fid)

    non_roots: Set[int] = set()
    for fid, _name, _qname, calls_json in rows:
        fid = int(fid)
        try:
            calls = json.loads(calls_json or "[]")
            if not isinstance(calls, list):
                calls = []
        except Exception:
            calls = []
        for callee in calls:
            if not isinstance(callee, str) or not callee:
                continue
            callee_id = name_to_id.get(callee)
            if callee_id is not None and callee_id != fid:
                non_roots.add(callee_id)

    conn.close()
    root_ids = sorted(list(all_ids - non_roots))
    return root_ids


def export_root_subgraphs_to_dir(db_path: Path, out_dir: Path) -> List[Path]:
    """
    Generate a DOT subgraph file for each root function (no callers) into 'out_dir'.

    Behavior:
    - For each root function R, traverse outbound call edges to collect reachable internal functions.
    - External callees (not present in DB) are rendered as dashed gray ellipse nodes.
    - Internal functions are rendered as boxes with label "qualified_name\\nsignature" when available.

    Returns:
    - A list of generated dot file paths.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT id, name, qualified_name, signature, calls_json FROM functions"
    ).fetchall()

    # Build indices
    by_id: Dict[int, Dict[str, str]] = {}
    name_to_id: Dict[str, int] = {}
    adj: Dict[int, List[str]] = {}

    for fid, name, qname, signature, calls_json in rows:
        fid = int(fid)
        nm = name or ""
        qn = qname or ""
        sig = signature or ""
        by_id[fid] = {"name": nm, "qname": qn, "sig": sig}

        if nm:
            name_to_id.setdefault(nm, fid)
        if qn:
            name_to_id.setdefault(qn, fid)

        try:
            calls = json.loads(calls_json or "[]")
            if not isinstance(calls, list):
                calls = []
        except Exception:
            calls = []
        # Keep only string callees
        adj[fid] = [c for c in calls if isinstance(c, str) and c]

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

    conn.close()
    return generated


def run_scan(
    dot: Optional[Path] = None,
    only_dot: bool = False,
    subgraphs_dir: Optional[Path] = None,
    only_subgraphs: bool = False,
    png: bool = False,
) -> None:
    """
    Scan a directory for C/C++ functions and store results into SQLite.
    Optionally, generate:
    - a global DOT call graph (--dot)
    - per-root subgraphs as individual DOT files (--subgraphs-dir)
    Use --only-dot / --only-subgraphs to skip scanning and generate from existing DB.
    """
    # Determine effective DB path
    root = Path('.')
    db_path = Path('.') / ".jarvis" / "c2rust" / "functions.db"

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
            scan_directory(root, db_path)
        except Exception as e:
            typer.secho(f"[c2rust-scanner] Error: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    else:
        # Only-generate mode (no rescan)
        if not db_path.exists():
            typer.secho(f"[c2rust-scanner] Database not found: {db_path}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)
        if only_dot and dot is None:
            typer.secho("[c2rust-scanner] --only-dot requires --dot to specify output file", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)
        if only_subgraphs and subgraphs_dir is None:
            typer.secho("[c2rust-scanner] --only-subgraphs requires --subgraphs-dir to specify output directory", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)

    # Generate DOT (global) if requested
    if dot is not None:
        try:
            generate_dot_from_db(db_path, dot)
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
            files = export_root_subgraphs_to_dir(db_path, subgraphs_dir)
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


