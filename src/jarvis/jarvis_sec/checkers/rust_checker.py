# -*- coding: utf-8 -*-
"""
Jarvis 安全分析套件 —— Rust 启发式安全检查器

目标与范围：
- 聚焦 unsafe 使用、原始指针、错误处理、并发与 FFI 等基础安全问题。
- 提供可解释的启发式检测与置信度评估，面向 .rs 源文件。

输出约定：
- 返回 jarvis.jarvis_sec.workflow.Issue 列表（结构化，便于聚合评分与报告生成）。
- 置信度区间 [0,1]；严重性（severity）分为 high/medium/low。

使用方式：
- from jarvis.jarvis_sec.checkers.rust_checker import analyze_rust_files
- issues = analyze_rust_files("./repo", ["src/lib.rs", "src/foo.rs"])
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Sequence, Tuple

from ..types import Issue


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

# 类型转换相关
RE_AS_CAST = re.compile(r"\b\w+\s+as\s+[A-Za-z_]\w*", re.IGNORECASE)
RE_FROM_RAW_PARTS = re.compile(r"\bfrom_raw_parts\s*\(")
RE_FROM_RAW = re.compile(r"\bfrom_raw\s*\(")
RE_INTO_RAW = re.compile(r"\binto_raw\s*\(")

# 内存操作相关
RE_GET_UNCHECKED = re.compile(r"\.get_unchecked\s*\(")
RE_GET_UNCHECKED_MUT = re.compile(r"\.get_unchecked_mut\s*\(")
RE_OFFSET = re.compile(r"\.offset\s*\(")
RE_ADD = re.compile(r"\.add\s*\(")
RE_COPY_NONOVERLAPPING = re.compile(r"\bcopy_nonoverlapping\s*\(")
RE_COPY = re.compile(r"\bcopy\s*\(")
RE_WRITE = re.compile(r"\bwrite\s*\(")
RE_READ = re.compile(r"\bread\s*\(")
RE_MANUALLY_DROP = re.compile(r"\bManuallyDrop\b")

# 并发相关
RE_ARC = re.compile(r"\bArc\s*<", re.IGNORECASE)
RE_MUTEX = re.compile(r"\bMutex\s*<", re.IGNORECASE)
RE_RWLOCK = re.compile(r"\bRwLock\s*<", re.IGNORECASE)
RE_REFCELL = re.compile(r"\bRefCell\s*<", re.IGNORECASE)
RE_CELL = re.compile(r"\bCell\s*<", re.IGNORECASE)

# 错误处理相关
RE_PANIC = re.compile(r"\bpanic!\s*\(")
RE_UNREACHABLE = re.compile(r"\bunreachable!\s*\(")

# FFI 相关
RE_CSTRING = re.compile(r"\bCString\b")
RE_CSTR = re.compile(r"\bCStr\b")
RE_FFI_PTR_DEREF = re.compile(r"\*[A-Za-z_]\w*\s*[\[\.]")  # 原始指针解引用

# 生命周期相关
RE_LIFETIME_PARAM = re.compile(r"<['][a-z]\w*>")  # 生命周期参数
RE_STATIC_LIFETIME = re.compile(r"&'static\s+")

# 其他不安全模式
RE_UNINIT = re.compile(r"\buninit\s*\(")
RE_ZEROED = re.compile(r"\bzeroed\s*\(")


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
        # 支持英文与中文“SAFETY/安全性”标注，兼容全角冒号
        if (
            "SAFETY:" in s
            or "Safety:" in s
            or "safety:" in s
            or "SAFETY：" in s  # 全角冒号
            or "安全性" in s
            or "安全:" in s
            or "安全：" in s
        ):
            return True
    return False


def _in_test_context(lines: Sequence[str], line_no: int, radius: int = 20) -> bool:
    """
    近邻出现 #[test] 或 mod tests { ... } 等，可能处于测试上下文，适度降低严重度。
    """
    for _, s in _window(lines, line_no, before=radius, after=radius):
        if "#[test]" in s or "cfg(test)" in s or re.search(r"\bmod\s+tests\b", s):
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
        # 避免对 unsafe impl 重复上报，由专门规则处理
        if not RE_UNSAFE.search(s) or RE_UNSAFE_IMPL.search(s):
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


def _rule_forget(lines: Sequence[str], relpath: str) -> List[Issue]:
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        if not RE_FORGET.search(s):
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
                category="resource_management",
                pattern="mem::forget",
                file=relpath,
                line=idx,
                evidence=_strip_line(s),
                description="使用 mem::forget 会跳过 Drop 导致资源泄漏，若错误使用可能破坏不变式或造成泄漏。",
                suggestion="避免无必要的 mem::forget；如需抑制 Drop，优先使用 ManuallyDrop 或设计更安全的所有权转移。",
                confidence=conf,
                severity=_severity_from_confidence(conf),
            )
        )
    return issues


def _rule_get_unchecked(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测 get_unchecked/get_unchecked_mut 的使用，这些方法绕过边界检查。
    """
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        if not (RE_GET_UNCHECKED.search(s) or RE_GET_UNCHECKED_MUT.search(s)):
            continue
        conf = 0.8
        if _has_safety_comment_around(lines, idx):
            conf -= 0.1
        if _in_test_context(lines, idx):
            conf -= 0.05
        conf = max(0.6, min(0.95, conf))
        issues.append(
            Issue(
                language="rust",
                category="unsafe_usage",
                pattern="get_unchecked",
                file=relpath,
                line=idx,
                evidence=_strip_line(s),
                description="使用 get_unchecked/get_unchecked_mut 绕过边界检查，若索引无效将导致未定义行为。",
                suggestion="优先使用安全的索引方法（[] 或 get）；必须使用 get_unchecked 时，在 SAFETY 注释中证明索引有效性。",
                confidence=conf,
                severity=_severity_from_confidence(conf),
            )
        )
    return issues


def _rule_pointer_arithmetic(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测指针算术操作（offset/add），这些操作可能产生无效指针。
    """
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        if not (RE_OFFSET.search(s) or RE_ADD.search(s)):
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
                pattern="pointer_arithmetic",
                file=relpath,
                line=idx,
                evidence=_strip_line(s),
                description="使用 offset/add 进行指针算术，若计算结果超出有效范围将导致未定义行为。",
                suggestion="确保指针算术结果在有效对象边界内；使用 slice 等安全抽象替代原始指针算术。",
                confidence=conf,
                severity=_severity_from_confidence(conf),
            )
        )
    return issues


def _rule_unsafe_mem_ops(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测不安全的内存操作（copy_nonoverlapping/copy/write/read）。
    """
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        if not (RE_COPY_NONOVERLAPPING.search(s) or RE_COPY.search(s) or RE_WRITE.search(s) or RE_READ.search(s)):
            continue
        # 检查是否在 unsafe 块中
        window_text = " ".join(t for _, t in _window(lines, idx, before=5, after=5))
        if "unsafe" not in window_text.lower():
            continue  # 这些函数必须在 unsafe 块中使用
        
        conf = 0.8
        if _has_safety_comment_around(lines, idx):
            conf -= 0.1
        if _in_test_context(lines, idx):
            conf -= 0.05
        conf = max(0.6, min(0.95, conf))
        issues.append(
            Issue(
                language="rust",
                category="unsafe_usage",
                pattern="unsafe_mem_ops",
                file=relpath,
                line=idx,
                evidence=_strip_line(s),
                description="使用不安全的内存操作（copy/copy_nonoverlapping/write/read），需确保指针有效性、对齐与重叠检查。",
                suggestion="优先使用安全的复制方法；必须使用时，在 SAFETY 注释中证明指针有效性、对齐与边界条件。",
                confidence=conf,
                severity=_severity_from_confidence(conf),
            )
        )
    return issues


def _rule_from_raw_parts(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测 from_raw_parts/from_raw 等不安全构造函数。
    """
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        if not (RE_FROM_RAW_PARTS.search(s) or RE_FROM_RAW.search(s)):
            continue
        conf = 0.85
        if _has_safety_comment_around(lines, idx):
            conf -= 0.1
        if _in_test_context(lines, idx):
            conf -= 0.05
        conf = max(0.6, min(0.95, conf))
        issues.append(
            Issue(
                language="rust",
                category="unsafe_usage",
                pattern="from_raw_parts/from_raw",
                file=relpath,
                line=idx,
                evidence=_strip_line(s),
                description="使用 from_raw_parts/from_raw 从原始指针构造，需确保指针有效性、对齐与生命周期安全。",
                suggestion="优先使用安全的构造函数；必须使用时，在 SAFETY 注释中证明所有前置条件（有效性/对齐/生命周期）。",
                confidence=conf,
                severity=_severity_from_confidence(conf),
            )
        )
    return issues


def _rule_manually_drop(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测 ManuallyDrop 的使用，需要手动管理 Drop。
    """
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        if not RE_MANUALLY_DROP.search(s):
            continue
        conf = 0.7
        if _has_safety_comment_around(lines, idx):
            conf -= 0.1
        if _in_test_context(lines, idx):
            conf -= 0.05
        conf = max(0.5, min(0.85, conf))
        issues.append(
            Issue(
                language="rust",
                category="resource_management",
                pattern="ManuallyDrop",
                file=relpath,
                line=idx,
                evidence=_strip_line(s),
                description="使用 ManuallyDrop 需要手动管理 Drop，若使用不当可能导致资源泄漏或双重释放。",
                suggestion="确保 ManuallyDrop 包装的对象在适当时候手动调用 drop；在 SAFETY 注释中说明生命周期管理策略。",
                confidence=conf,
                severity=_severity_from_confidence(conf),
            )
        )
    return issues


def _rule_panic_unreachable(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测 panic!/unreachable! 的使用，可能导致程序崩溃。
    """
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        if not (RE_PANIC.search(s) or RE_UNREACHABLE.search(s)):
            continue
        conf = 0.6
        if _in_test_context(lines, idx):
            conf -= 0.15  # 测试中 panic 更常见
        if "assert" in s.lower():
            conf -= 0.1  # assert! 宏中的 panic 通常可接受
        conf = max(0.4, min(0.75, conf))
        issues.append(
            Issue(
                language="rust",
                category="error_handling",
                pattern="panic/unreachable",
                file=relpath,
                line=idx,
                evidence=_strip_line(s),
                description="使用 panic!/unreachable! 可能导致程序崩溃，缺少优雅的错误处理。",
                suggestion="优先使用 Result 类型进行错误处理；仅在确实不可恢复的情况下使用 panic。",
                confidence=conf,
                severity=_severity_from_confidence(conf),
            )
        )
    return issues


def _rule_refcell_borrow(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测 RefCell 的使用，运行时借用检查可能 panic。
    """
    issues: List[Issue] = []
    refcell_vars: set[str] = set()
    
    # 收集 RefCell 变量
    for idx, s in enumerate(lines, start=1):
        if RE_REFCELL.search(s):
            # 简单提取变量名
            m = re.search(r"\bRefCell\s*<[^>]+>\s*([A-Za-z_]\w*)", s, re.IGNORECASE)
            if m:
                refcell_vars.add(m.group(1))
    
    # 检测 borrow/borrow_mut 的使用
    for idx, s in enumerate(lines, start=1):
        for var in refcell_vars:
            if re.search(rf"\b{re.escape(var)}\s*\.borrow\s*\(", s, re.IGNORECASE):
                conf = 0.55
                # 检查是否有 try_borrow（更安全）
                if "try_borrow" in s.lower():
                    continue
                if _in_test_context(lines, idx):
                    conf -= 0.1
                conf = max(0.4, min(0.7, conf))
                issues.append(
                    Issue(
                        language="rust",
                        category="error_handling",
                        pattern="RefCell_borrow",
                        file=relpath,
                        line=idx,
                        evidence=_strip_line(s),
                        description=f"RefCell {var} 使用 borrow/borrow_mut 可能在运行时 panic（借用冲突）。",
                        suggestion="考虑使用 try_borrow/try_borrow_mut 返回 Result，或使用 Mutex/RwLock 进行编译时检查。",
                        confidence=conf,
                        severity=_severity_from_confidence(conf),
                    )
                )
                break  # 每行只报告一次
    return issues


def _rule_ffi_cstring(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测 FFI 中 CString/CStr 的使用，需要确保正确转换与生命周期。
    """
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        if not (RE_CSTRING.search(s) or RE_CSTR.search(s)):
            continue
        # 检查是否在 FFI 上下文中
        window_text = " ".join(t for _, t in _window(lines, idx, before=5, after=5))
        if RE_EXTERN_C.search(window_text) or "ffi" in window_text.lower():
            conf = 0.65
            if _has_safety_comment_around(lines, idx):
                conf -= 0.1
            conf = max(0.5, min(0.8, conf))
            issues.append(
                Issue(
                    language="rust",
                    category="ffi",
                    pattern="CString/CStr",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(s),
                    description="FFI 中使用 CString/CStr 需要确保正确的生命周期管理与空字节处理。",
                    suggestion="确保 CString 生命周期覆盖 FFI 调用期间；注意 CStr 不能包含内部空字节。",
                    confidence=conf,
                    severity=_severity_from_confidence(conf),
                )
            )
    return issues


def _rule_uninit_zeroed(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测 uninit/zeroed 的使用，未初始化内存访问风险。
    """
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        if not (RE_UNINIT.search(s) or RE_ZEROED.search(s)):
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
                pattern="uninit/zeroed",
                file=relpath,
                line=idx,
                evidence=_strip_line(s),
                description="使用 uninit/zeroed 创建未初始化内存，若在初始化前读取将导致未定义行为。",
                suggestion="确保在使用前完成初始化；优先使用 MaybeUninit 进行更安全的未初始化内存管理。",
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
    # 基础 unsafe 使用
    issues.extend(_rule_unsafe(lines, relpath))
    issues.extend(_rule_raw_pointer(lines, relpath))
    issues.extend(_rule_transmute(lines, relpath))
    issues.extend(_rule_forget(lines, relpath))
    issues.extend(_rule_maybe_uninit(lines, relpath))
    # 错误处理
    issues.extend(_rule_unwrap_expect(lines, relpath))
    issues.extend(_rule_ignore_result(lines, relpath))
    issues.extend(_rule_panic_unreachable(lines, relpath))
    # FFI 相关
    issues.extend(_rule_extern_c(lines, relpath))
    issues.extend(_rule_ffi_cstring(lines, relpath))
    # 并发相关
    issues.extend(_rule_unsafe_impl(lines, relpath))
    issues.extend(_rule_refcell_borrow(lines, relpath))
    # 内存操作相关
    issues.extend(_rule_get_unchecked(lines, relpath))
    issues.extend(_rule_pointer_arithmetic(lines, relpath))
    issues.extend(_rule_unsafe_mem_ops(lines, relpath))
    issues.extend(_rule_from_raw_parts(lines, relpath))
    issues.extend(_rule_manually_drop(lines, relpath))
    issues.extend(_rule_uninit_zeroed(lines, relpath))
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


def analyze_rust_files(base_path: str, relative_paths: List[str]) -> List[Issue]:
    """
    批量分析文件，相对路径相对于 base_path。
    """
    base = Path(base_path).resolve()
    out: List[Issue] = []
    for f in relative_paths:
        p = Path(f)
        if p.suffix.lower() == ".rs":
            out.extend(analyze_rust_file(base, p))
    return out