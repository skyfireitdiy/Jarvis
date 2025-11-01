# -*- coding: utf-8 -*-
"""
OpenHarmony 安全分析套件 —— Rust 启发式安全检查器

目标与范围：
- 聚焦 unsafe 使用、原始指针、错误处理、并发与 FFI 等基础安全问题。
- 提供可解释的启发式检测与置信度评估，面向 .rs 源文件。

输出约定：
- 返回 jarvis.jarvis_sec.workflow.Issue 列表（结构化，便于聚合评分与报告生成）。
- 置信度区间 [0,1]；严重性（severity）分为 high/medium/low。

使用方式：
- from jarvis.jarvis_sec.checkers.rust_checker import analyze_files
- issues = analyze_files("./repo", ["src/lib.rs", "src/foo.rs"])
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

from jarvis.jarvis_sec.types import Issue


# ---------------------------
# 规则库（正则表达式）
# ---------------------------

RE_UNSAFE = re.compile(r"\bunsafe\b")
RE_RAW_PTR = re.compile(r"\*(?:mut|const)\s+[A-Za-z_]\w*")  # 类型处的原始指针
RE_FORGET = re.compile(r"\bmem::forget\b")
RE_TRANSMUTE = re.compile(r"\bmem::transmute\b")
RE_MAYBE_UNINIT = re.compile(r"\bMaybeUninit\b")
RE_ASSUME_INIT = re.compile(r"\bassume_init\s*\(")

RE_UNWRAP = re.compile(r"\bunwrap\s*\(", re.IGNORECASE)
RE_EXPECT = re.compile(r"\bexpect\s*\(", re.IGNORECASE)
RE_EXTERN_C = re.compile(r'extern\s+"C"')
RE_UNSAFE_IMPL = re.compile(r"\bunsafe\s+impl\s+(?:Send|Sync)\b|\bimpl\s+unsafe\s+(?:Send|Sync)\b", re.IGNORECASE)

# 结果忽略/下划线绑定（可能忽略错误）
RE_LET_UNDERSCORE = re.compile(r"\blet\s+_+\s*=\s*.+;")
RE_MATCH_IGNORE_ERR = re.compile(r"\.ok\s*\(\s*\)|\.ok\?\s*;|\._?\s*=\s*.+\.err\(\s*\)", re.IGNORECASE)  # 粗略


# ---------------------------
# 公共工具
# ---------------------------

def _safe_line(lines: Sequence[str], idx: int) -> str:
    if 1 <= idx <= len(lines):
        return lines[idx - 1]
    return ""


def _strip_line(s: str, max_len: int = 200) -> str:
    s = s.strip().replace("\t", " ")
    return s if len(s) <= max_len else s[: max_len - 3] + "..."


def _window(lines: Sequence[str], center: int, before: int = 3, after: int = 3) -> List[Tuple[int, str]]:
    start = max(1, center - before)
    end = min(len(lines), center + after)
    return [(i, _safe_line(lines, i)) for i in range(start, end + 1)]


def _has_safety_comment_around(lines: Sequence[str], line_no: int, radius: int = 5) -> bool:
    """
    Rust 社区约定在 unsafe 附近写 SAFETY: 注释说明前置条件。
    如存在，适当降低置信度。
    """
    for _, s in _window(lines, line_no, before=radius, after=radius):
        if "SAFETY:" in s or "Safety:" in s or "safety:" in s:
            return True
    return False


def _in_test_context(lines: Sequence[str], line_no: int, radius: int = 20) -> bool:
    """
    近邻出现 #[test] 或 mod tests { ... } 等，可能处于测试上下文，适度降低严重度。
    """
    for _, s in _window(lines, line_no, before=radius, after=radius):
        if "#[test]" in s or re.search(r"\bmod\s+tests\b", s):
            return True
    return False


def _severity_from_confidence(conf: float) -> str:
    if conf >= 0.8:
        return "high"
    if conf >= 0.6:
        return "medium"
    return "low"


# ---------------------------
# 规则实现
# ---------------------------

def _rule_unsafe(lines: Sequence[str], relpath: str) -> List[Issue]:
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        if not RE_UNSAFE.search(s):
            continue
        conf = 0.8
        if _has_safety_comment_around(lines, idx, radius=5):
            conf -= 0.1
        if _in_test_context(lines, idx):
            conf -= 0.05
        conf = max(0.5, min(0.95, conf))
        issues.append(
            Issue(
                language="rust",
                category="unsafe_usage",
                pattern="unsafe",
                file=relpath,
                line=idx,
                evidence=_strip_line(s),
                description="存在 unsafe 代码块/标识，需证明内存/别名/生命周期安全性。",
                suggestion="将不安全操作封装在最小作用域内，并提供 SAFETY 注释说明前置条件与不变式。",
                confidence=conf,
                severity=_severity_from_confidence(conf),
            )
        )
    return issues


def _rule_raw_pointer(lines: Sequence[str], relpath: str) -> List[Issue]:
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        if not RE_RAW_PTR.search(s):
            continue
        conf = 0.75
        if _has_safety_comment_around(lines, idx):
            conf -= 0.1
        if _in_test_context(lines, idx):
            conf -= 0.05
        conf = max(0.5, min(0.9, conf))
        issues.append(
            Issue(
                language="rust",
                category="unsafe_usage",
                pattern="raw_pointer",
                file=relpath,
                line=idx,
                evidence=_strip_line(s),
                description="出现原始指针（*mut/*const），可能绕过借用/生命周期检查，带来未定义行为风险。",
                suggestion="优先使用引用/智能指针；必须使用原始指针时，严格证明无别名、对齐与生命周期安全。",
                confidence=conf,
                severity=_severity_from_confidence(conf),
            )
        )
    return issues


def _rule_transmute(lines: Sequence[str], relpath: str) -> List[Issue]:
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        if not RE_TRANSMUTE.search(s):
            continue
        conf = 0.85
        if _has_safety_comment_around(lines, idx):
            conf -= 0.1
        conf = max(0.6, min(0.95, conf))
        issues.append(
            Issue(
                language="rust",
                category="unsafe_usage",
                pattern="mem::transmute",
                file=relpath,
                line=idx,
                evidence=_strip_line(s),
                description="使用 mem::transmute 进行类型转换，若未严格保证布局/对齐/生命周期，将导致未定义行为。",
                suggestion="避免使用 transmute，优先采用安全转换或 bytemuck 等受审计抽象；必须使用时严格注明不变式。",
                confidence=conf,
                severity=_severity_from_confidence(conf),
            )
        )
    return issues


def _rule_maybe_uninit(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    MaybeUninit + assume_init 组合常见于优化/FFI，需特别小心初始化与有效性。
    """
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        if not (RE_MAYBE_UNINIT.search(s) or RE_ASSUME_INIT.search(s)):
            continue
        conf = 0.7
        # 若在邻近几行同时出现 MaybeUninit 与 assume_init，风险更高
        win_text = " ".join(t for _, t in _window(lines, idx, before=3, after=3))
        if RE_MAYBE_UNINIT.search(win_text) and RE_ASSUME_INIT.search(win_text):
            conf += 0.1
        if _has_safety_comment_around(lines, idx):
            conf -= 0.05
        conf = max(0.5, min(0.9, conf))
        issues.append(
            Issue(
                language="rust",
                category="unsafe_usage",
                pattern="MaybeUninit/assume_init",
                file=relpath,
                line=idx,
                evidence=_strip_line(s),
                description="使用 MaybeUninit/assume_init 需保证正确初始化与读取顺序，否则可能导致未定义行为。",
                suggestion="确保初始化前不读取；使用更安全的构造函数；在 SAFETY 注释中说明前置条件。",
                confidence=conf,
                severity=_severity_from_confidence(conf),
            )
        )
    return issues


def _rule_unwrap_expect(lines: Sequence[str], relpath: str) -> List[Issue]:
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        if not (RE_UNWRAP.search(s) or RE_EXPECT.search(s)):
            continue
        conf = 0.65
        if _in_test_context(lines, idx):
            conf -= 0.1
        conf = max(0.45, min(0.8, conf))
        issues.append(
            Issue(
                language="rust",
                category="error_handling",
                pattern="unwrap/expect",
                file=relpath,
                line=idx,
                evidence=_strip_line(s),
                description="直接 unwrap/expect 可能在错误条件下 panic，缺少健壮的错误处理路径。",
                suggestion="使用 ? 传播错误或 match 显式处理；为关键路径提供错误上下文与恢复策略。",
                confidence=conf,
                severity=_severity_from_confidence(conf),
            )
        )
    return issues


def _rule_extern_c(lines: Sequence[str], relpath: str) -> List[Issue]:
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        if not RE_EXTERN_C.search(s):
            continue
        conf = 0.7
        if _has_safety_comment_around(lines, idx):
            conf -= 0.05
        conf = max(0.5, min(0.85, conf))
        issues.append(
            Issue(
                language="rust",
                category="ffi",
                pattern='extern "C"',
                file=relpath,
                line=idx,
                evidence=_strip_line(s),
                description="FFI 边界需要确保指针有效性、长度/对齐、生命周期、线程安全等约束，否则可能产生未定义行为。",
                suggestion="在 FFI 边界进行严格的参数校验与安全封装；在 SAFETY 注释中记录不变式与约束。",
                confidence=conf,
                severity=_severity_from_confidence(conf),
            )
        )
    return issues


def _rule_unsafe_impl(lines: Sequence[str], relpath: str) -> List[Issue]:
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        if not RE_UNSAFE_IMPL.search(s):
            continue
        conf = 0.8
        if _has_safety_comment_around(lines, idx):
            conf -= 0.1
        conf = max(0.6, min(0.95, conf))
        issues.append(
            Issue(
                language="rust",
                category="concurrency",
                pattern="unsafe_impl_Send_or_Sync",
                file=relpath,
                line=idx,
                evidence=_strip_line(s),
                description="手写 unsafe impl Send/Sync 可能破坏并发内存模型保证，带来数据竞争风险。",
                suggestion="避免手写 unsafe impl；必要时严格证明线程安全前置条件并最小化不安全区域。",
                confidence=conf,
                severity=_severity_from_confidence(conf),
            )
        )
    return issues


def _rule_ignore_result(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    启发式：使用 let _ = xxx; 或 .ok() 等可能忽略错误。
    该规则误报可能较高，因此置信度较低。
    """
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        if not (RE_LET_UNDERSCORE.search(s) or RE_MATCH_IGNORE_ERR.search(s)):
            continue
        conf = 0.55
        if _in_test_context(lines, idx):
            conf -= 0.1
        conf = max(0.4, min(0.7, conf))
        issues.append(
            Issue(
                language="rust",
                category="error_handling",
                pattern="ignored_result",
                file=relpath,
                line=idx,
                evidence=_strip_line(s),
                description="可能忽略了返回的错误结果，导致失败未被处理。",
                suggestion="显式处理 Result（? 传播或 match），确保错误路径涵盖资源回收与日志记录。",
                confidence=conf,
                severity=_severity_from_confidence(conf),
            )
        )
    return issues


# ---------------------------
# 对外主入口
# ---------------------------

def analyze_rust_text(relpath: str, text: str) -> List[Issue]:
    """
    基于提供的文本进行 Rust 启发式分析。
    """
    lines = text.splitlines()
    issues: List[Issue] = []
    issues.extend(_rule_unsafe(lines, relpath))
    issues.extend(_rule_raw_pointer(lines, relpath))
    issues.extend(_rule_transmute(lines, relpath))
    issues.extend(_rule_maybe_uninit(lines, relpath))
    issues.extend(_rule_unwrap_expect(lines, relpath))
    issues.extend(_rule_extern_c(lines, relpath))
    issues.extend(_rule_unsafe_impl(lines, relpath))
    issues.extend(_rule_ignore_result(lines, relpath))
    return issues


def analyze_rust_file(base: Path, relpath: Path) -> List[Issue]:
    """
    从磁盘读取文件进行分析。
    """
    try:
        text = (base / relpath).read_text(errors="ignore")
    except Exception:
        return []
    return analyze_rust_text(str(relpath), text)


def analyze_files(base_path: str, files: Iterable[str]) -> List[Issue]:
    """
    批量分析文件，相对路径相对于 base_path。
    """
    base = Path(base_path).resolve()
    out: List[Issue] = []
    for f in files:
        p = Path(f)
        if p.suffix.lower() == ".rs":
            out.extend(analyze_rust_file(base, p))
    return out