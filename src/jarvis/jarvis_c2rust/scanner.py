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
    try:
        from clang import cindex  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "Failed to import clang.cindex. Please install libclang and the python bindings.\n"
            "Hints:\n"
            "- pip install clang\n"
            "- Ensure libclang is installed (e.g., apt install libclang-14 or newer)\n"
            "- Set env LIBCLANG_PATH to the directory containing libclang.so, or CLANG_LIBRARY_FILE to full path.\n"
            "- Alternatively set LLVM_HOME to LLVM installation prefix."
        ) from e

    # Try to set library path/file from environment or common locations
    lib_file = os.environ.get("CLANG_LIBRARY_FILE")
    lib_dir = os.environ.get("LIBCLANG_PATH")
    llvm_home = os.environ.get("LLVM_HOME")

    set_ok = False
    if lib_file and Path(lib_file).exists():
        try:
            cindex.Config.set_library_file(lib_file)
            set_ok = True
        except Exception:
            set_ok = False

    if not set_ok and lib_dir and Path(lib_dir).exists():
        try:
            cindex.Config.set_library_path(lib_dir)
            set_ok = True
        except Exception:
            set_ok = False

    if not set_ok and llvm_home:
        cand = Path(llvm_home) / "lib" / "libclang.so"
        if cand.exists():
            try:
                cindex.Config.set_library_file(str(cand))
                set_ok = True
            except Exception:
                set_ok = False

    if not set_ok:
        # Try some common paths heuristically; ignore errors
        for p in [
            "/usr/lib/llvm-18/lib",
            "/usr/lib/llvm-17/lib",
            "/usr/lib/llvm-16/lib",
            "/usr/lib/llvm-15/lib",
            "/usr/lib/llvm-14/lib",
            "/usr/lib",
            "/usr/local/lib",
        ]:
            try:
                if (Path(p) / "libclang.so").exists():
                    cindex.Config.set_library_file(str(Path(p) / "libclang.so"))
                    set_ok = True
                    break
            except Exception:
                continue

    return cindex


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
    # Search upward for compile_commands.json
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
    Returns: mapping file -> compile args (excluding the compiler executable)
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
            args = entry["arguments"][1:] if entry["arguments"] else []
        else:
            # fallback to split command string
            cmd = entry.get("command", "")
            # naive split; a robust split would need shlex
            import shlex

            parts = shlex.split(cmd) if cmd else []
            args = parts[1:] if parts else []
        # Remove output flags and compile-only flags that confuse libclang parse
        cleaned = []
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
            # Try without args as fallback
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


def cli(
    root: Path = typer.Option(..., "--root", "-r", help="Directory to scan"),
    db: Optional[Path] = typer.Option(
        None,
        "--db",
        "-d",
        help="Output sqlite db path (default: <root>/.jarvis/c2rust/functions.db)",
    ),
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
) -> None:
    """
    Scan a directory for C/C++ functions and store results into SQLite.
    Optionally, generate a DOT call graph from the database.
    """
    # Determine effective DB path
    default_db = Path(root) / ".jarvis" / "c2rust" / "functions.db"
    db_path = db if db else default_db

    if not only_dot:
        if not root.exists():
            typer.secho(f"Root path does not exist: {root}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)
        try:
            scan_directory(root, db_path)
        except Exception as e:
            typer.secho(f"[c2rust-scanner] Error: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    else:
        # Only generate DOT from existing DB
        if dot is None:
            typer.secho("[c2rust-scanner] --only-dot requires --dot to specify output file", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)
        if not db_path.exists():
            typer.secho(f"[c2rust-scanner] Database not found: {db_path}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)

    # Generate DOT if requested
    if dot is not None:
        try:
            generate_dot_from_db(db_path, dot)
            typer.secho(f"[c2rust-scanner] DOT written: {dot}", fg=typer.colors.GREEN)
        except Exception as e:
            typer.secho(f"[c2rust-scanner] Failed to write DOT: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)


def main() -> None:
    # Entry point used by console_scripts
    typer.run(cli)


if __name__ == "__main__":
    main()