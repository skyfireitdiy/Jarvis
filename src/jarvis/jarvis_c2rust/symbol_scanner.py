from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Iterable, List, Optional

from jarvis.jarvis_utils.output import OutputType, PrettyOutput
import fnmatch


CTAGS_KINDS_C = {
    # C language kinds per universal-ctags
    # d: macro definition, e: enumerator, f: function, g: enum, s: struct,
    # t: typedef, u: union, v: variable, p: function prototype (sometimes)
    "d",
    "e",
    "f",
    "g",
    "s",
    "t",
    "u",
    "v",
    "p",
}

# Map possible kind names to short letters for robustness across ctags configs
CTAGS_KIND_NAME_TO_LETTER = {
    "macro": "d",
    "define": "d",
    "enumerator": "e",
    "function": "f",
    "enum": "g",
    "struct": "s",
    "typedef": "t",
    "union": "u",
    "variable": "v",
    "prototype": "p",
    "functionPrototype": "p",
}


def _default_excludes() -> List[str]:
    return [
        ".git",
        ".hg",
        ".svn",
        ".jarvis",
        "build",
        "cmake-build*",
        "out",
        "dist",
        "target",
        "bazel-*",
        "node_modules",
        "third_party",
        "vendor",
    ]


def _ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _should_exclude(path: Path, patterns: Iterable[str]) -> bool:
    for pat in patterns:
        # match on full path and basename for convenience
        if fnmatch.fnmatch(path.name, pat) or fnmatch.fnmatch(str(path), pat):
            return True
    return False


def _gather_c_files(project_root: Path, excludes: Iterable[str]) -> List[Path]:
    candidates: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(project_root):
        current_dir = Path(dirpath)
        # filter dirs in-place to prune walk
        pruned: List[str] = []
        for d in list(dirnames):
            dpath = current_dir / d
            if _should_exclude(dpath, excludes):
                pruned.append(d)
        for d in pruned:
            dirnames.remove(d)

        if _should_exclude(current_dir, excludes):
            continue

        for fname in filenames:
            fpath = current_dir / fname
            if _should_exclude(fpath, excludes):
                continue
            if fpath.suffix.lower() in {".c", ".h"}:
                candidates.append(fpath)
    return candidates


def _is_universal_ctags() -> bool:
    try:
        out = subprocess.run(
            ["ctags", "--version"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        text_out = (out.stdout or "") + "\n" + (out.stderr or "")
        return "Universal Ctags" in text_out or "Universal-ctags" in text_out
    except FileNotFoundError:
        return False


def _run_ctags(
    project_root: Path, excludes: Iterable[str]
) -> subprocess.Popen:  # returns process to stream JSON lines
    args: List[str] = [
        "ctags",
        "-R",
        # include C++ so that ambiguous .h headers still get parsed
        "--languages=C,C++",
        # protect '*' from fish shell when users copy the command; here it's passed directly so safe
        "--kinds-C=*",
        "--fields=+nKStiazm",
        "--extras=+q",
        "--output-format=json",
        "--sort=no",
        "-o",
        "-",
    ]
    for ex in excludes:
        args.append(f"--exclude={ex}")
    args.append(str(project_root))

    try:
        proc = subprocess.Popen(
            args,
            cwd=str(project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return proc
    except FileNotFoundError:
        raise RuntimeError(
            "ctags (universal-ctags) not found. Please install it and retry."
        )


def scan_c_symbols_to_jsonl(
    project_root: Path, output_file: Path, extra_excludes: Optional[List[str]] = None
) -> int:
    """Scan C symbols with universal-ctags and write JSONL records.

    Returns number of symbols written.
    """
    project_root = project_root.resolve()
    if not project_root.exists() or not project_root.is_dir():
        raise ValueError(f"Invalid project root: {project_root}")

    excludes = _default_excludes()
    if extra_excludes:
        excludes.extend(extra_excludes)

    _ensure_dir(output_file)

    # Quick pre-scan to hint user if no C sources exist
    c_files = _gather_c_files(project_root, excludes)
    if len(c_files) == 0:
        PrettyOutput.print(
            "未发现任何 .c/.h 文件（可能被排除或目录为空）。", OutputType.INFO
        )
        PrettyOutput.print(
            "可尝试指定子目录或移除排除项：--path <src_dir> -x ''", OutputType.INFO
        )
        # 仍然返回 0，避免无意义的 ctags 扫描
        return 0

    if not _is_universal_ctags():
        PrettyOutput.print(
            (
                "未检测到 universal-ctags 或版本过旧，无法输出 JSON。\n"
                "请安装 universal-ctags：\n"
                "- Ubuntu/Debian: sudo apt-get install universal-ctags 或使用 PPA\n"
                "- macOS: brew install universal-ctags\n"
                "- 从源码: https://ctags.io/"
            ),
            OutputType.ERROR,
        )
        return 0

    try:
        proc = _run_ctags(project_root, excludes)
    except RuntimeError as e:
        PrettyOutput.print(str(e), OutputType.ERROR)
        return 0

    num = 0
    assert proc.stdout is not None
    assert proc.stderr is not None
    with open(output_file, "w", encoding="utf-8") as fout:
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue

            if obj.get("_type") != "tag":
                continue
            language = obj.get("language")
            kind_value = obj.get("kind")
            # Normalize kind to letter
            if isinstance(kind_value, str) and len(kind_value) == 1:
                kind = kind_value
            else:
                kind = CTAGS_KIND_NAME_TO_LETTER.get(str(kind_value), None)
            if kind not in CTAGS_KINDS_C:
                continue
            path_value = obj.get("path") or ""
            # Accept C symbols and headers marked as C++ (common ambiguity for .h)
            if language not in ("C", None):
                if not (language == "C++" and path_value.endswith(".h")):
                    continue

            # Normalize record
            record = {
                "name": obj.get("name"),
                "kind": kind,
                "path": obj.get("path"),
                "line": obj.get("line"),
                "language": obj.get("language"),
                "scope": obj.get("scope"),
                "scopeKind": obj.get("scopeKind"),
                "signature": obj.get("signature"),
                "typeref": obj.get("typeref"),
                "inherits": obj.get("inherits"),
            }
            fout.write(json.dumps(record, ensure_ascii=False) + "\n")
            num += 1

    # Drain stderr to avoid zombies and capture errors
    _, stderr = proc.communicate()
    if proc.returncode not in (0, None):
        PrettyOutput.print(
            f"ctags returned {proc.returncode}: {stderr.strip()}", OutputType.WARNING
        )
    elif num == 0 and stderr:
        # Likely non-universal ctags ignoring options
        PrettyOutput.print(
            (
                "ctags 未产生任何 JSON 标记记录，可能不是 universal-ctags 或参数不被支持。\n"
                f"stderr: {stderr.strip()}"
            ),
            OutputType.WARNING,
        )

    PrettyOutput.print(
        f"C symbols scanned: {num}. Saved to {output_file}", OutputType.SUCCESS
    )
    return num


