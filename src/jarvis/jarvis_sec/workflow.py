# -*- coding: utf-8 -*-
"""
OpenHarmony 安全分析套件 —— Workflow（含可复现直扫基线）

目标：
- 识别指定模块的安全问题（内存管理、缓冲区操作、错误处理等），检出率≥60% 为目标。
- 在不依赖外部服务的前提下，提供一个“可复现、可离线”的直扫基线（direct scan）。
- 当前采用“先直扫拆分子任务，再由单Agent逐条分析”的模式；保留接口便于后续切换。

本模块提供：
- direct_scan(entry_path, languages=None, exclude_dirs=None) -> Dict：纯Python+正则/命令行辅助扫描，生成结构化结果
- format_markdown_report(result_json: Dict) -> str：将结构化结果转为可读的 Markdown
- run_security_analysis_fast(entry_path, languages=None, exclude_dirs=None) -> str：一键运行直扫并输出（JSON + Markdown）
- run_with_agent(entry_path, languages=None) -> str：使用单Agent逐条子任务分析模式（复用 jarvis.jarvis_sec.__init__ 的实现）
"""

import os
import re
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, cast
from jarvis.jarvis_sec.checkers import analyze_c_files, analyze_rust_files
from jarvis.jarvis_sec.report import build_json_and_markdown
from jarvis.jarvis_sec.types import Issue


# ---------------------------
# 数据结构
# ---------------------------

# Issue dataclass is provided by jarvis.jarvis_sec.types to avoid circular imports


# ---------------------------
# 工具函数
# ---------------------------

def _rg_available() -> bool:
    return shutil.which("rg") is not None


def _iter_source_files(
    entry_path: str,
    languages: Optional[List[str]] = None,
    exclude_dirs: Optional[List[str]] = None,
) -> Iterable[Path]:
    """
    递归枚举源文件，支持按扩展名过滤与目录排除。
    默认语言扩展：c, cpp, h, hpp, rs
    """
    entry = Path(entry_path)
    if not entry.exists():
        return

    exts = set((languages or ["c", "cpp", "h", "hpp", "rs"]))
    excludes = set(exclude_dirs or [".git", "build", "out", "target", "third_party", "vendor"])

    for p in entry.rglob("*"):
        if not p.is_file():
            continue
        # 目录排除（任意祖先包含即排除）
        skip = False
        for parent in p.parents:
            if parent.name in excludes:
                skip = True
                break
        if skip:
            continue

        suf = p.suffix.lstrip(".").lower()
        if suf in exts:
            yield p.relative_to(entry)


def _read_file_lines(base: Path, relpath: Path) -> List[str]:
    try:
        return (base / relpath).read_text(errors="ignore").splitlines()
    except Exception:
        return []


def _safe_evidence(line: str, max_len: int = 200) -> str:
    s = line.strip().replace("\t", " ")
    if len(s) > max_len:
        return s[: max_len - 3] + "..."
    return s


def _try_rg_search(pattern: str, files: List[Path], cwd: Path) -> List[Tuple[Path, int, str]]:
    """
    使用 rg -n PATTERN file1 file2 ... 搜索，返回 (file, line, text)。
    若 rg 不可用或失败，返回空列表。
    """
    if not files:
        return []
    if not _rg_available():
        return []

    # rg 命令长度有限，分批执行
    results: List[Tuple[Path, int, str]] = []
    batch_size = 200
    for i in range(0, len(files), batch_size):
        batch = files[i : i + batch_size]
        cmd = ["rg", "-n", pattern] + [str(cwd / f) for f in batch]
        try:
            proc = subprocess.run(
                cmd, cwd=str(cwd), capture_output=True, text=True, check=False
            )
            if proc.returncode in (0, 1):  # 0: 有匹配；1: 无匹配
                out = proc.stdout.splitlines()
                for line in out:
                    # 解析: path:lineno:content
                    # 注意: Windows 路径中可能含冒号，这里采用从右侧第一次冒号分割两次的方案
                    parts = line.split(":", 2)
                    if len(parts) < 3:
                        continue
                    fpath = Path(parts[0])
                    try:
                        lineno = int(parts[1])
                    except ValueError:
                        continue
                    text = parts[2]
                    try:
                        rel = fpath.relative_to(cwd)
                    except Exception:
                        # 回退：将绝对路径转相对路径
                        try:
                            rel = Path(os.path.relpath(fpath, cwd))
                        except Exception:
                            rel = fpath
                    results.append((rel, lineno, text))
        except Exception:
            # 忽略 rg 错误，交由纯Python扫描兜底
            return []
    return results


# ---------------------------
# 规则库（阶段一）
# ---------------------------

C_UNSAFE_API = re.compile(r"\b(strcpy|strcat|gets|sprintf|vsprintf|scanf)\s*\(", re.IGNORECASE)
C_BOUNDARY_FUNCS = re.compile(r"\b(memcpy|memmove|strncpy|strncat)\s*\(", re.IGNORECASE)
C_MEM_MGMT = re.compile(r"\b(malloc|calloc|realloc|free|new\s+|delete\b)", re.IGNORECASE)
C_IO_API = re.compile(r"\b(fopen|fclose|fread|fwrite|read|write|open|close)\s*\(", re.IGNORECASE)

R_UNSAFE = re.compile(r"\bunsafe\b")
R_RAW_PTR = re.compile(r"\*(mut|const)\s+[A-Za-z_]\w*")
R_FORGET = re.compile(r"\bmem::forget\b")
R_UNWRAP = re.compile(r"\bunwrap\s*\(|\bexpect\s*\(", re.IGNORECASE)
R_EXTERN_C = re.compile(r'extern\s+"C"')
R_UNSAFE_IMPL = re.compile(r"\bunsafe\s+impl\s+(Send|Sync)\b|\bimpl\s+unsafe\s+(Send|Sync)\b")


# ---------------------------
# 扫描实现
# ---------------------------

def _scan_c_cpp(
    base: Path, relpath: Path, issues: List[Issue]
) -> None:
    """
    针对 C/C++ 文件进行启发式扫描。
    """
    lines = _read_file_lines(base, relpath)
    if not lines:
        return

    for idx, line in enumerate(lines, start=1):
        if C_UNSAFE_API.search(line):
            m = C_UNSAFE_API.search(line)
            pat = m.group(1) if m else "unsafe_api"
            issues.append(
                Issue(
                    language="c/cpp",
                    category="unsafe_api",
                    pattern=pat,
                    file=str(relpath),
                    line=idx,
                    evidence=_safe_evidence(line),
                    description="使用不安全/高风险字符串API，可能导致缓冲区溢出或格式化风险。",
                    suggestion="替换为带边界的安全API（如 snprintf/strlcpy 等）或加入显式长度检查。",
                    confidence=0.9,
                    severity="high",
                )
            )
        if C_BOUNDARY_FUNCS.search(line):
            m = C_BOUNDARY_FUNCS.search(line)
            pat = m.group(1) if m else "boundary_api"
            issues.append(
                Issue(
                    language="c/cpp",
                    category="buffer_overflow",
                    pattern=pat,
                    file=str(relpath),
                    line=idx,
                    evidence=_safe_evidence(line),
                    description="缓冲区操作涉及长度/边界，需确认长度来源是否可靠，避免越界。",
                    suggestion="核对目标缓冲区大小与拷贝长度；对外部输入进行校验；优先使用安全封装。",
                    confidence=0.7,
                    severity="medium",
                )
            )
        if C_MEM_MGMT.search(line):
            m = C_MEM_MGMT.search(line)
            pat = m.group(1) if m else "mem_mgmt"
            issues.append(
                Issue(
                    language="c/cpp",
                    category="memory_mgmt",
                    pattern=pat,
                    file=str(relpath),
                    line=idx,
                    evidence=_safe_evidence(line),
                    description="涉及内存管理API，需确认分配/释放匹配，realloc 的返回值处理，以及空指针检查。",
                    suggestion="确保 new/delete 与 malloc/free 匹配；realloc 先用临时变量接收；所有返回值做 NULL 检查。",
                    confidence=0.65,
                    severity="medium",
                )
            )
        if C_IO_API.search(line):
            m = C_IO_API.search(line)
            pat = m.group(1) if m else "io_api"
            issues.append(
                Issue(
                    language="c/cpp",
                    category="error_handling",
                    pattern=pat,
                    file=str(relpath),
                    line=idx,
                    evidence=_safe_evidence(line),
                    description="I/O/系统调用返回值可能未检查，存在错误处理缺失风险。",
                    suggestion="检查返回值/errno；在错误路径上释放资源（句柄/内存/锁）。",
                    confidence=0.6,
                    severity="low",
                )
            )

    # 简单 UAF 线索（非常粗略）：free(var); ... 后续再次出现 var
    # 仅用于提示，非严格判定
    text = "\n".join(lines)
    free_vars = re.findall(r"free\s*\(\s*([A-Za-z_]\w*)\s*\)\s*;", text)
    for v in set(free_vars):
        # 搜索 free 后再次出现 v 的位置（简化判定）
        pattern = re.compile(rf"free\s*\(\s*{re.escape(v)}\s*\)\s*;(.|\n)+?\b{re.escape(v)}\b", re.MULTILINE)
        if pattern.search(text):
            # 取第一次 free 的行号作为证据
            for idx, line in enumerate(lines, start=1):
                if re.search(rf"free\s*\(\s*{re.escape(v)}\s*\)\s*;", line):
                    issues.append(
                        Issue(
                            language="c/cpp",
                            category="memory_mgmt",
                            pattern="use_after_free_suspect",
                            file=str(relpath),
                            line=idx,
                            evidence=_safe_evidence(line),
                            description=f"变量 {v} 在 free 后可能仍被使用（UAF线索，需人工确认）。",
                            suggestion="free 后将指针置 NULL；为变量生命周期建立清晰约束；添加动态/静态检测。",
                            confidence=0.55,
                            severity="high",
                        )
                    )
                    break


def _scan_rust(
    base: Path, relpath: Path, issues: List[Issue]
) -> None:
    """
    针对 Rust 文件进行启发式扫描。
    """
    lines = _read_file_lines(base, relpath)
    if not lines:
        return

    for idx, line in enumerate(lines, start=1):
        if R_UNSAFE.search(line):
            issues.append(
                Issue(
                    language="rust",
                    category="unsafe_usage",
                    pattern="unsafe",
                    file=str(relpath),
                    line=idx,
                    evidence=_safe_evidence(line),
                    description="存在 unsafe 代码块/标识，需证明内存/别名/生命周期安全性。",
                    suggestion="将不安全操作封装在最小作用域内，补充不变式与前置条件，优先使用安全抽象。",
                    confidence=0.8,
                    severity="high",
                )
            )
        if R_RAW_PTR.search(line):
            issues.append(
                Issue(
                    language="rust",
                    category="unsafe_usage",
                    pattern="raw_pointer",
                    file=str(relpath),
                    line=idx,
                    evidence=_safe_evidence(line),
                    description="出现原始指针（*mut/*const），可能绕过借用检查器。",
                    suggestion="使用引用/智能指针；必须使用时，谨慎证明无别名、对齐、生命周期安全。",
                    confidence=0.75,
                    severity="medium",
                )
            )
        if R_FORGET.search(line):
            issues.append(
                Issue(
                    language="rust",
                    category="unsafe_usage",
                    pattern="mem::forget",
                    file=str(relpath),
                    line=idx,
                    evidence=_safe_evidence(line),
                    description="使用 mem::forget 可能导致资源泄漏或生命周期不匹配。",
                    suggestion="评估必要性；可使用 ManuallyDrop 等更安全模式；确保不破坏析构语义。",
                    confidence=0.7,
                    severity="medium",
                )
            )
        if R_UNWRAP.search(line):
            pat = "unwrap/expect"
            issues.append(
                Issue(
                    language="rust",
                    category="error_handling",
                    pattern=pat,
                    file=str(relpath),
                    line=idx,
                    evidence=_safe_evidence(line),
                    description="直接 unwrap/expect 可能在错误条件下 panic，缺少健壮的错误处理。",
                    suggestion="使用 ? 传播错误或 match 显式处理，返回 Result。",
                    confidence=0.65,
                    severity="low",
                )
            )
        if R_EXTERN_C.search(line):
            issues.append(
                Issue(
                    language="rust",
                    category="ffi",
                    pattern='extern "C"',
                    file=str(relpath),
                    line=idx,
                    evidence=_safe_evidence(line),
                    description="FFI 边界需检查指针有效性、长度与生命周期，防止未定义行为。",
                    suggestion="在FFI边界进行严格的参数校验与安全封装；记录安全不变式。",
                    confidence=0.7,
                    severity="medium",
                )
            )
        if R_UNSAFE_IMPL.search(line):
            issues.append(
                Issue(
                    language="rust",
                    category="concurrency",
                    pattern="unsafe_impl_Send_or_Sync",
                    file=str(relpath),
                    line=idx,
                    evidence=_safe_evidence(line),
                    description="手写 unsafe impl Send/Sync 可能破坏并发安全保证。",
                    suggestion="避免手写 unsafe impl；必要时严格证明线程安全前置条件。",
                    confidence=0.7,
                    severity="high",
                )
            )


# ---------------------------
# 汇总与报告
# ---------------------------

def direct_scan(
    entry_path: str,
    languages: Optional[List[str]] = None,
    exclude_dirs: Optional[List[str]] = None,
) -> Dict:
    """
    直扫基线：对 C/C++/Rust 进行启发式扫描，输出结构化 JSON。
    - 改进：委派至模块化检查器（oh_sec.checkers），统一规则与置信度模型。
    """
    base = Path(entry_path).resolve()
    files = list(_iter_source_files(entry_path, languages, exclude_dirs))

    # 按语言分组
    c_like_exts = {".c", ".cpp", ".h", ".hpp"}
    rust_exts = {".rs"}
    c_files: List[Path] = [p for p in files if p.suffix.lower() in c_like_exts]
    r_files: List[Path] = [p for p in files if p.suffix.lower() in rust_exts]

    # 调用检查器（保持相对路径，基于 base_path 解析）
    issues_c = analyze_c_files(str(base), [str(p) for p in c_files]) if c_files else []
    issues_r = analyze_rust_files(str(base), [str(p) for p in r_files]) if r_files else []
    issues: List[Issue] = issues_c + issues_r


    summary: Dict[str, Any] = {
        "total": len(issues),
        "by_language": {"c/cpp": 0, "rust": 0},
        "by_category": {},
        "top_risk_files": [],
        "scanned_files": len(files),
        "scanned_root": str(base),
    }
    file_score: Dict[str, int] = {}
    # Safely update language/category counts with explicit typing
    lang_counts = cast(Dict[str, int], summary["by_language"])
    cat_counts = cast(Dict[str, int], summary["by_category"])
    for it in issues:
        lang_counts[it.language] = lang_counts.get(it.language, 0) + 1
        cat_counts[it.category] = cat_counts.get(it.category, 0) + 1
        file_score[it.file] = file_score.get(it.file, 0) + 1
    # Top 风险文件
    summary["top_risk_files"] = [f for f, _ in sorted(file_score.items(), key=lambda x: x[1], reverse=True)[:10]]

    result = {
        "summary": summary,
        "issues": [asdict(i) for i in issues],
    }
    return result


def format_markdown_report(result_json: Dict) -> str:
    """
    将结构化 JSON 转为 Markdown 可读报告。
    """
    s = result_json.get("summary", {})
    issues: List[Dict] = result_json.get("issues", [])
    md: List[str] = []
    md.append("# OpenHarmony 安全问题分析报告（直扫基线）")
    md.append("")
    md.append(f"- 扫描根目录: {s.get('scanned_root', '')}")
    md.append(f"- 扫描文件数: {s.get('scanned_files', 0)}")
    md.append(f"- 检出问题总数: {s.get('total', 0)}")
    md.append("")
    md.append("## 统计概览")
    by_lang = s.get("by_language", {})
    md.append(f"- 按语言: c/cpp={by_lang.get('c/cpp', 0)}, rust={by_lang.get('rust', 0)}")
    md.append("- 按类别:")
    for k, v in s.get("by_category", {}).items():
        md.append(f"  - {k}: {v}")
    if s.get("top_risk_files"):
        md.append("- Top 风险文件:")
        for f in s["top_risk_files"]:
            md.append(f"  - {f}")
    md.append("")
    md.append("## 详细问题")
    for i, it in enumerate(issues, start=1):
        md.append(f"### [{i}] {it.get('file')}:{it.get('line')} ({it.get('language')}, {it.get('category')})")
        md.append(f"- 模式: {it.get('pattern')}")
        md.append(f"- 证据: `{it.get('evidence')}`")
        md.append(f"- 描述: {it.get('description')}")
        md.append(f"- 建议: {it.get('suggestion')}")
        md.append(f"- 置信度: {it.get('confidence')}, 严重性: {it.get('severity')}")
        md.append("")
    return "\n".join(md)


def run_security_analysis_fast(
    entry_path: str,
    languages: Optional[List[str]] = None,
    exclude_dirs: Optional[List[str]] = None,
) -> str:
    """
    一键运行直扫基线，返回 JSON + Markdown 文本。
    - 改进：使用统一的报告聚合与评分模块（oh_sec.report.build_json_and_markdown），
      输出结构与多Agent Aggregator一致，便于评测与专家审阅。
    """
    result = direct_scan(entry_path, languages=languages, exclude_dirs=exclude_dirs)
    summary = result.get("summary", {})
    issues = result.get("issues", [])
    return build_json_and_markdown(
        issues,
        scanned_root=summary.get("scanned_root"),
        scanned_files=summary.get("scanned_files"),
    )


def run_with_agent(
    entry_path: str,
    languages: Optional[List[str]] = None,
    llm_group: Optional[str] = None,
    report_file: Optional[str] = None,
    batch_limit: int = 10,
) -> str:
    """
    使用单Agent逐条子任务分析模式运行（与 jarvis.jarvis_sec.__init__ 中保持一致）。
    - 先执行本地直扫，生成候选问题
    - 为每条候选创建一次普通Agent任务进行分析与验证
    - 聚合为最终报告（JSON + Markdown）返回

    其他：
    - llm_group: 本次分析使用的模型组（仅透传给 Agent，不修改全局配置）
    - report_file: JSONL 报告文件路径（可选，透传）
    """
    from jarvis.jarvis_sec import run_security_analysis  # 延迟导入，避免循环
    return run_security_analysis(
        entry_path,
        languages=languages,
        llm_group=llm_group,
        report_file=report_file,
        batch_limit=batch_limit,
    )


__all__ = [
    "Issue",
    "direct_scan",
    "format_markdown_report",
    "run_security_analysis_fast",
    "run_with_agent",
]