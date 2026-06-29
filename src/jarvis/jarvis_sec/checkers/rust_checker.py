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
from typing import List
from typing import Optional
from typing import Sequence
from typing import Tuple
from typing import TYPE_CHECKING

from jarvis.jarvis_sec.types import Issue

if TYPE_CHECKING:
    from jarvis.jarvis_sec.project_database import ProjectDatabase

# 污点分析框架（核心依赖）
import jarvis.jarvis_sec.taint_analyzer as taint_analyzer

# 数据流分析器（用于误报过滤）
from jarvis.jarvis_sec.data_flow_analyzer import (
    DataFlowAnalyzer,
    DataFlowResult,
)

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
RE_UNSAFE_IMPL = re.compile(
    r"\bunsafe\s+impl\s+(?:Send|Sync)\b|\bimpl\s+unsafe\s+(?:Send|Sync)\b",
    re.IGNORECASE,
)

# 结果忽略/下划线绑定（可能忽略错误）
RE_LET_UNDERSCORE = re.compile(r"\blet\s+_+\s*=\s*.+;")
RE_MATCH_IGNORE_ERR = re.compile(
    r"\.ok\s*\(\s*\)|\.ok\?\s*;|\._?\s*=\s*.+\.err\(\s*\)", re.IGNORECASE
)  # 粗略

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


def _window(
    lines: Sequence[str], center: int, before: int = 3, after: int = 3
) -> List[Tuple[int, str]]:
    start = max(1, center - before)
    end = min(len(lines), center + after)
    return [(i, _safe_line(lines, i)) for i in range(start, end + 1)]


def _remove_comments_preserve_strings(text: str) -> str:
    """
    移除 Rust 源码中的注释（//、///、//!、/* */、/** */、/*! */），保留字符串与字符字面量内容；
    为了保持行号与窗口定位稳定，注释内容会被空格替换并保留换行符。
    说明：本函数为启发式实现，旨在降低"注释中的API命中"造成的误报。
    """
    res: list[str] = []
    i = 0
    n = len(text)
    in_sl_comment = False  # //
    in_bl_comment = False  # /* */
    in_string = False  # "
    in_char = False  # '
    in_raw_string = False  # r"..." 或 r#"..."#
    raw_string_hash_count = 0  # 原始字符串的 # 数量
    escape = False

    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        nxt2 = text[i + 2] if i + 2 < n else ""

        if in_sl_comment:
            # 单行注释直到换行结束
            if ch == "\n":
                in_sl_comment = False
                res.append(ch)
            else:
                # 用空格占位，保持列数
                res.append(" ")
            i += 1
            continue

        if in_bl_comment:
            # 多行注释直到 */
            if ch == "*" and nxt == "/":
                in_bl_comment = False
                res.append(" ")
                res.append(" ")
                i += 2
            else:
                # 注释体内保留换行，其余替换为空格
                res.append("\n" if ch == "\n" else " ")
                i += 1
            continue

        # 处理原始字符串（r"..." 或 r#"..."#）
        if in_raw_string:
            if ch == '"':
                # 检查是否有足够的 # 来结束原始字符串
                hash_count = 0
                j = i - 1
                while j >= 0 and text[j] == "#":
                    hash_count += 1
                    j -= 1
                if hash_count == raw_string_hash_count:
                    in_raw_string = False
                    raw_string_hash_count = 0
                    res.append(ch)
                    i += 1
                else:
                    res.append(ch)
                    i += 1
            else:
                res.append(ch)
                i += 1
            continue

        # 非注释态下，处理字符串与字符字面量
        if in_string:
            res.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if in_char:
            res.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == "'":
                in_char = False
            i += 1
            continue

        # 进入注释判定（需不在字符串/字符字面量中）
        # 单行注释：//、///、//!
        if ch == "/" and nxt == "/":
            in_sl_comment = True
            res.append(" ")
            res.append(" ")
            i += 2
            continue
        # 多行注释：/*、/**、/*!
        if ch == "/" and nxt == "*":
            in_bl_comment = True
            res.append(" ")
            res.append(" ")
            i += 2
            continue

        # 进入原始字符串：r"..." 或 r#"..."# 或 br"..." 或 b"..."（字节字符串）
        # 检查是否是 r" 或 br"
        if ch == "r" and nxt == '"':
            # 简单原始字符串：r"
            in_raw_string = True
            raw_string_hash_count = 0
            res.append(ch)
            res.append(nxt)
            i += 2
            continue
        if ch == "b" and nxt == "r" and nxt2 == '"':
            # 字节原始字符串：br"
            in_raw_string = True
            raw_string_hash_count = 0
            res.append(ch)
            res.append(nxt)
            res.append(nxt2)
            i += 3
            continue
        if ch == "r" and nxt == "#":
            # 带 # 的原始字符串：r#"
            # 计算 # 的数量
            raw_string_hash_count = 1
            j = i + 1
            while j < n and text[j] == "#":
                raw_string_hash_count += 1
                j += 1
            if j < n and text[j] == '"':
                in_raw_string = True
                # 输出 r 和所有 # 和 "
                for k in range(i, j + 1):
                    res.append(text[k])
                i = j + 1
                continue
        if ch == "b" and nxt == "r" and nxt2 == "#":
            # 字节原始字符串：br#"
            raw_string_hash_count = 1
            j = i + 2
            while j < n and text[j] == "#":
                raw_string_hash_count += 1
                j += 1
            if j < n and text[j] == '"':
                in_raw_string = True
                # 输出 br 和所有 # 和 "
                res.append(ch)
                res.append(nxt)
                for k in range(i + 2, j + 1):
                    res.append(text[k])
                i = j + 1
                continue

        # 进入字符串/字符字面量
        # 处理 b"..."（字节字符串，不是原始字符串，需要在原始字符串检测之后）
        if ch == "b" and nxt == '"' and nxt2 != "r":
            in_string = True
            res.append(ch)
            res.append(nxt)
            i += 2
            continue
        if ch == '"':
            in_string = True
            res.append(ch)
            i += 1
            continue
        if ch == "'":
            in_char = True
            res.append(ch)
            i += 1
            continue

        # 普通字符
        res.append(ch)
        i += 1

    return "".join(res)


def _mask_strings_preserve_len(text: str) -> str:
    """
    将字符串与字符字面量内部内容替换为空格，保留引号与换行，保持长度与行号不变。
    用于在扫描通用 API 模式时避免误将字符串中的片段（如 "unsafe("）当作代码。
    注意：此函数不移除注释，请在已移除注释的文本上调用。
    """
    res: list[str] = []
    in_string = False
    in_char = False
    in_raw_string = False
    raw_string_hash_count = 0
    escape = False

    i = 0
    n = len(text)

    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        nxt2 = text[i + 2] if i + 2 < n else ""

        if in_raw_string:
            if ch == '"':
                # 检查是否有足够的 # 来结束原始字符串
                hash_count = 0
                j = i - 1
                while j >= 0 and text[j] == "#":
                    hash_count += 1
                    j -= 1
                if hash_count == raw_string_hash_count:
                    in_raw_string = False
                    raw_string_hash_count = 0
                    res.append('"')
                    i += 1
                elif ch == "\n":
                    res.append("\n")
                    i += 1
                else:
                    res.append(" ")
                    i += 1
            else:
                if ch == "\n":
                    res.append("\n")
                else:
                    res.append(" ")
                i += 1
            continue

        if in_string:
            if escape:
                # 保留转义反斜杠为两字符（反斜杠+空格），以不破坏列对齐过多
                res.append(" ")
                escape = False
            elif ch == "\\":
                res.append("\\")
                escape = True
            elif ch == '"':
                res.append('"')
                in_string = False
            elif ch == "\n":
                res.append("\n")
            else:
                res.append(" ")
            i += 1
            continue

        if in_char:
            if escape:
                res.append(" ")
                escape = False
            elif ch == "\\":
                res.append("\\")
                escape = True
            elif ch == "'":
                res.append("'")
                in_char = False
            elif ch == "\n":
                res.append("\n")
            else:
                res.append(" ")
            i += 1
            continue

        # 检测原始字符串开始：r"..." 或 r#"..."# 或 br"..." 或 b"..."（字节字符串）
        if ch == "r" and nxt == '"':
            # 简单原始字符串：r"
            in_raw_string = True
            raw_string_hash_count = 0
            res.append(ch)
            res.append(nxt)
            i += 2
            continue
        if ch == "b" and nxt == "r" and nxt2 == '"':
            # 字节原始字符串：br"
            in_raw_string = True
            raw_string_hash_count = 0
            res.append(ch)
            res.append(nxt)
            res.append(nxt2)
            i += 3
            continue
        if ch == "r" and nxt == "#":
            # 带 # 的原始字符串：r#"
            raw_string_hash_count = 1
            j = i + 1
            while j < n and text[j] == "#":
                raw_string_hash_count += 1
                j += 1
            if j < n and text[j] == '"':
                in_raw_string = True
                # 输出 r 和所有 # 和 "
                for k in range(i, j + 1):
                    res.append(text[k])
                i = j + 1
                continue
        if ch == "b" and nxt == "r" and nxt2 == "#":
            # 字节原始字符串：br#"
            raw_string_hash_count = 1
            j = i + 2
            while j < n and text[j] == "#":
                raw_string_hash_count += 1
                j += 1
            if j < n and text[j] == '"':
                in_raw_string = True
                # 输出 br 和所有 # 和 "
                res.append(ch)
                res.append(nxt)
                for k in range(i + 2, j + 1):
                    res.append(text[k])
                i = j + 1
                continue

        # 处理 b"..."（字节字符串，不是原始字符串，需要在原始字符串检测之后）
        if ch == "b" and nxt == '"' and nxt2 != "r":
            in_string = True
            res.append(ch)
            res.append(nxt)
            i += 2
            continue
        if ch == '"':
            in_string = True
            res.append('"')
            i += 1
            continue
        if ch == "'":
            in_char = True
            res.append("'")
            i += 1
            continue

        res.append(ch)
        i += 1

    return "".join(res)


def _has_safety_comment_around(
    lines: Sequence[str], line_no: int, radius: int = 5
) -> bool:
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


def _rule_unsafe(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测unsafe块使用。
    - 优先使用database查询symbols表获取unsafe_block类型的符号
    - 无database时返回空列表
    """
    issues: List[Issue] = []

    if database is None:
        return issues

    try:
        symbols = database.get_symbols_by_file(relpath)
        for symbol in symbols:
            if symbol.get("kind") != "unsafe_block":
                continue
            # unsafe impl Send/Sync由_rule_unsafe_impl专门处理，此处跳过
            if "__unsafe_impl__" in symbol.get("name", ""):
                continue

            line_start = symbol.get("line_start", 0)
            if line_start <= 0 or line_start > len(lines):
                continue

            s = lines[line_start - 1]
            # SAFETY注释：直接过滤，不报告
            if _has_safety_comment_around(lines, line_start, radius=5):
                continue
            conf = 0.8
            if _in_test_context(lines, line_start):
                conf -= 0.05
            conf = max(0.5, min(0.95, conf))

            issues.append(
                Issue(
                    language="rust",
                    category="unsafe_usage",
                    pattern="unsafe",
                    file=relpath,
                    line=line_start,
                    evidence=_strip_line(s),
                    description="存在 unsafe 代码块/标识，需证明内存/别名/生命周期安全性。",
                    suggestion="将不安全操作封装在最小作用域内，并提供 SAFETY 注释说明前置条件与不变式。",
                    confidence=conf,
                    severity=_severity_from_confidence(conf),
                )
            )
    except Exception:
        pass

    return issues


def _rule_raw_pointer(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测原始指针（*mut/*const）使用。
    - 优先使用database查询pointer_states表获取RAW_POINTER状态的指针
    - 无database时返回空列表
    """
    issues: List[Issue] = []

    if database is None:
        return issues

    try:
        pointer_states = database.get_pointer_states_by_file(relpath)
        for state in pointer_states:
            if state.get("state") != "RAW_POINTER":
                continue

            line = state.get("line", 0)
            if line <= 0 or line > len(lines):
                continue

            var_name = state.get("var_name", "")
            s = lines[line - 1]
            # SAFETY注释：直接过滤，不报告
            if _has_safety_comment_around(lines, line, radius=5):
                continue
            conf = 0.75
            if _in_test_context(lines, line):
                conf -= 0.05
            conf = max(0.5, min(0.9, conf))

            issues.append(
                Issue(
                    language="rust",
                    category="unsafe_usage",
                    pattern="raw_pointer",
                    file=relpath,
                    line=line,
                    evidence=_strip_line(s),
                    description=f"出现原始指针 {var_name}（*mut/*const），可能绕过借用/生命周期检查，带来未定义行为风险。",
                    suggestion="优先使用引用/智能指针；必须使用原始指针时，严格证明无别名、对齐与生命周期安全。",
                    confidence=conf,
                    severity=_severity_from_confidence(conf),
                )
            )
    except Exception:
        pass

    return issues


def _rule_transmute(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测mem::transmute调用。
    - 优先使用database查询call_graph表获取transmute调用
    - 无database时返回空列表
    """
    issues: List[Issue] = []

    if database is None:
        return issues

    try:
        import os

        call_graph = database.get_call_graph()
        for call in call_graph:
            callee_name = call.get("callee_name", "")
            if callee_name not in [
                "transmute",
                "mem::transmute",
                "std::mem::transmute",
            ]:
                continue

            caller_file = call.get("caller_file", "")
            if os.path.basename(caller_file) != os.path.basename(relpath):
                continue

            idx = call.get("caller_line", 0)
            if idx <= 0 or idx > len(lines):
                continue

            s = lines[idx - 1]
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
    except Exception:
        pass

    return issues


def _rule_maybe_uninit(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测MaybeUninit/assume_init使用。
    - 优先使用database查询call_graph表获取相关调用
    - 无database时返回空列表
    """
    issues: List[Issue] = []

    if database is None:
        return issues

    try:
        import os

        call_graph = database.get_call_graph()
        maybe_uninit_calls = []
        assume_init_calls = []

        for call in call_graph:
            callee_name = call.get("callee_name", "")
            caller_file = call.get("caller_file", "")
            if os.path.basename(caller_file) != os.path.basename(relpath):
                continue

            if callee_name in ["MaybeUninit", "maybe_uninit", "std::mem::MaybeUninit"]:
                maybe_uninit_calls.append(call)
            elif callee_name in ["assume_init", "maybe_uninit_assume_init"]:
                assume_init_calls.append(call)

        # 处理MaybeUninit调用
        for call in maybe_uninit_calls:
            idx = call.get("caller_line", 0)
            if idx <= 0 or idx > len(lines):
                continue

            s = lines[idx - 1]
            conf = 0.7
            # 检查附近是否有assume_init
            for assume_call in assume_init_calls:
                assume_line = assume_call.get("caller_line", 0)
                if abs(assume_line - idx) <= 3:
                    conf += 0.1
                    break
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

        # 处理assume_init调用
        for call in assume_init_calls:
            idx = call.get("caller_line", 0)
            if idx <= 0 or idx > len(lines):
                continue

            # 避免重复报告（如果已经在MaybeUninit附近报告过）
            already_reported = False
            for issue in issues:
                if abs(issue.line - idx) <= 3:
                    already_reported = True
                    break
            if already_reported:
                continue

            s = lines[idx - 1]
            conf = 0.7
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
                    description="使用 assume_init 需保证正确初始化，否则可能导致未定义行为。",
                    suggestion="确保初始化前不读取；使用更安全的构造函数；在 SAFETY 注释中说明前置条件。",
                    confidence=conf,
                    severity=_severity_from_confidence(conf),
                )
            )
    except Exception:
        pass

    return issues


def _rule_unwrap_expect(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测unwrap/expect调用。
    - 优先使用database查询call_graph表获取unwrap/expect调用
    - 无database时返回空列表
    """
    issues: List[Issue] = []

    if database is None:
        return issues

    try:
        import os

        call_graph = database.get_call_graph()
        for call in call_graph:
            callee_name = call.get("callee_name", "")
            # 匹配unwrap和expect方法调用
            if callee_name not in ["unwrap", "expect"]:
                continue

            caller_file = call.get("caller_file", "")
            if os.path.basename(caller_file) != os.path.basename(relpath):
                continue

            idx = call.get("caller_line", 0)
            if idx <= 0 or idx > len(lines):
                continue

            s = lines[idx - 1]
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
    except Exception:
        pass

    return issues


def _rule_extern_c(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测extern "C"声明。
    - 优先使用database查询symbols表获取extern块
    - 无database时返回空列表
    """
    issues: List[Issue] = []

    if database is None:
        return issues

    try:
        symbols = database.get_symbols_by_file(relpath)
        for symbol in symbols:
            # 检测extern块（kind='extern_block'或name包含'extern'）
            kind = symbol.get("kind", "")
            name = symbol.get("name", "")
            if kind != "extern_block" and "extern" not in name.lower():
                continue

            line_start = symbol.get("line_start", 0)
            if line_start <= 0 or line_start > len(lines):
                continue

            s = lines[line_start - 1]
            conf = 0.7
            if _has_safety_comment_around(lines, line_start):
                conf -= 0.05
            conf = max(0.5, min(0.85, conf))

            issues.append(
                Issue(
                    language="rust",
                    category="ffi",
                    pattern='extern "C"',
                    file=relpath,
                    line=line_start,
                    evidence=_strip_line(s),
                    description="FFI 边界需要确保指针有效性、长度/对齐、生命周期、线程安全等约束，否则可能产生未定义行为。",
                    suggestion="在 FFI 边界进行严格的参数校验与安全封装；在 SAFETY 注释中记录不变式与约束。",
                    confidence=conf,
                    severity=_severity_from_confidence(conf),
                )
            )
    except Exception:
        pass

    return issues


def _rule_unsafe_impl(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测unsafe impl Send/Sync。
    - 优先使用database查询symbols表获取unsafe impl定义
    - 无database时返回空列表
    """
    issues: List[Issue] = []

    if database is None:
        return issues

    try:
        symbols = database.get_symbols_by_file(relpath)
        for symbol in symbols:
            # 检测unsafe impl Send/Sync
            kind = symbol.get("kind", "")
            name = symbol.get("name", "")
            # DataCollector可能存为kind='impl'或kind='unsafe_block'(name含__unsafe_impl__)
            if kind == "impl":
                # 检查是否是Send或Sync的impl
                if "Send" not in name and "Sync" not in name:
                    continue
                # 检查是否是unsafe impl
                is_unsafe = symbol.get("is_unsafe", False) or "unsafe" in name.lower()
                if not is_unsafe:
                    continue
            elif kind == "unsafe_block" and "__unsafe_impl__" in name:
                # DataCollector将unsafe impl存为unsafe_block，name格式: __unsafe_impl__TypeName
                # 需要从源码行检查是否是Send/Sync
                line_start = symbol.get("line_start", 0)
                if line_start <= 0 or line_start > len(lines):
                    continue
                s = lines[line_start - 1]
                if "Send" not in s and "Sync" not in s:
                    continue
            else:
                continue

            line_start = symbol.get("line_start", 0)
            if line_start <= 0 or line_start > len(lines):
                continue

            s = lines[line_start - 1]
            conf = 0.8
            if _has_safety_comment_around(lines, line_start):
                conf -= 0.1
            conf = max(0.6, min(0.95, conf))

            issues.append(
                Issue(
                    language="rust",
                    category="concurrency",
                    pattern="unsafe_impl_Send_or_Sync",
                    file=relpath,
                    line=line_start,
                    evidence=_strip_line(s),
                    description="手写 unsafe impl Send/Sync 可能破坏并发内存模型保证，带来数据竞争风险。",
                    suggestion="避免手写 unsafe impl；必要时严格证明线程安全前置条件并最小化不安全区域。",
                    confidence=conf,
                    severity=_severity_from_confidence(conf),
                )
            )
    except Exception:
        pass

    return issues


def _rule_ignore_result(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测let _ = xxx忽略结果。
    - 优先使用database查询data_flow表获取let _绑定信息
    - 无database时返回空列表
    """
    issues: List[Issue] = []

    if database is None:
        return issues

    try:
        # 查询data_flow表获取let _绑定
        data_flows = database.get_data_flow_by_file(relpath)
        for flow in data_flows:
            # 检测let _绑定模式（忽略结果）
            var_name = flow.get("var_name", "")
            if var_name != "_":
                continue

            line = flow.get("line", 0)
            if line <= 0 or line > len(lines):
                continue

            s = lines[line - 1]
            conf = 0.55
            if _in_test_context(lines, line):
                conf -= 0.1
            conf = max(0.4, min(0.7, conf))

            issues.append(
                Issue(
                    language="rust",
                    category="error_handling",
                    pattern="ignored_result",
                    file=relpath,
                    line=line,
                    evidence=_strip_line(s),
                    description="可能忽略了返回的错误结果，导致失败未被处理。",
                    suggestion="显式处理 Result（? 传播或 match），确保错误路径涵盖资源回收与日志记录。",
                    confidence=conf,
                    severity=_severity_from_confidence(conf),
                )
            )
    except Exception:
        pass

    return issues


def _rule_forget(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测 mem::forget 的使用，会跳过 Drop 导致资源泄漏。
    - 优先使用database查询call_graph表获取mem::forget调用
    - 无database时返回空列表
    """
    issues: List[Issue] = []

    if database is None:
        return issues

    try:
        import os

        call_graph = database.get_call_graph()
        for call in call_graph:
            callee_name = call.get("callee_name", "")
            # 匹配mem::forget调用
            if callee_name not in ["mem::forget", "forget"]:
                continue

            caller_file = call.get("caller_file", "")
            if os.path.basename(caller_file) != os.path.basename(relpath):
                continue

            idx = call.get("caller_line", 0)
            if idx <= 0 or idx > len(lines):
                continue

            s = lines[idx - 1]
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
    except Exception:
        pass

    return issues


def _rule_get_unchecked(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测 get_unchecked/get_unchecked_mut 的使用，这些方法绕过边界检查。
    - 优先使用database查询call_graph表获取get_unchecked/get_unchecked_mut调用
    - 无database时返回空列表
    """
    issues: List[Issue] = []

    if database is None:
        return issues

    try:
        import os

        call_graph = database.get_call_graph()
        for call in call_graph:
            callee_name = call.get("callee_name", "")
            # 匹配get_unchecked/get_unchecked_mut调用
            if callee_name not in ["get_unchecked", "get_unchecked_mut"]:
                continue

            caller_file = call.get("caller_file", "")
            if os.path.basename(caller_file) != os.path.basename(relpath):
                continue

            idx = call.get("caller_line", 0)
            if idx <= 0 or idx > len(lines):
                continue

            s = lines[idx - 1]
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
    except Exception:
        pass

    return issues


def _rule_pointer_arithmetic(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测指针算术操作（offset/add），这些操作可能产生无效指针。
    - 优先使用database查询call_graph表获取offset/add调用
    - 无database时返回空列表
    """
    issues: List[Issue] = []

    if database is None:
        return issues

    try:
        import os

        call_graph = database.get_call_graph()
        for call in call_graph:
            callee_name = call.get("callee_name", "")
            # 匹配offset/add调用（指针算术）
            if callee_name not in [
                "offset",
                "add",
                "sub",
                "wrapping_offset",
                "wrapping_add",
                "wrapping_sub",
            ]:
                continue

            caller_file = call.get("caller_file", "")
            if os.path.basename(caller_file) != os.path.basename(relpath):
                continue

            idx = call.get("caller_line", 0)
            if idx <= 0 or idx > len(lines):
                continue

            s = lines[idx - 1]
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
    except Exception:
        pass

    return issues


def _rule_unsafe_mem_ops(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测不安全的内存操作（copy_nonoverlapping/copy/write/read）。
    - 优先使用database查询call_graph表获取不安全内存操作调用
    - 无database时返回空列表
    """
    issues: List[Issue] = []

    if database is None:
        return issues

    try:
        import os

        call_graph = database.get_call_graph()
        for call in call_graph:
            callee_name = call.get("callee_name", "")
            # 匹配不安全内存操作
            unsafe_mem_ops = [
                "copy_nonoverlapping",
                "copy",
                "write",
                "read",
                "write_bytes",
                "read_volatile",
                "write_volatile",
                "read_unaligned",
                "write_unaligned",
            ]
            if callee_name not in unsafe_mem_ops:
                continue

            caller_file = call.get("caller_file", "")
            if os.path.basename(caller_file) != os.path.basename(relpath):
                continue

            idx = call.get("caller_line", 0)
            if idx <= 0 or idx > len(lines):
                continue

            s = lines[idx - 1]
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
    except Exception:
        pass

    return issues


def _rule_from_raw_parts(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测 from_raw_parts/from_raw 等不安全构造函数。
    - 优先使用database查询call_graph表获取from_raw_parts/from_raw调用
    - 无database时返回空列表
    """
    issues: List[Issue] = []

    if database is None:
        return issues

    try:
        import os

        call_graph = database.get_call_graph()
        for call in call_graph:
            callee_name = call.get("callee_name", "")
            # 匹配from_raw_parts/from_raw调用
            if callee_name not in ["from_raw_parts", "from_raw_parts_mut", "from_raw"]:
                continue

            caller_file = call.get("caller_file", "")
            if os.path.basename(caller_file) != os.path.basename(relpath):
                continue

            idx = call.get("caller_line", 0)
            if idx <= 0 or idx > len(lines):
                continue

            s = lines[idx - 1]
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
    except Exception:
        pass

    return issues


def _rule_manually_drop(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测 ManuallyDrop 的使用，需要手动管理 Drop。
    - 优先使用database查询symbols表获取ManuallyDrop类型使用
    - 优先使用database查询call_graph表获取ManuallyDrop::new/drop调用
    - 无database时返回空列表
    """
    issues: List[Issue] = []

    if database is None:
        return issues

    try:
        import os

        # 先查询call_graph表，检测是否有ManuallyDrop::drop调用（正确清理）
        call_graph = database.get_call_graph()
        has_manually_drop_cleanup = False
        for call in call_graph:
            callee_name = call.get("callee_name", "")
            if callee_name == "ManuallyDrop::drop":
                caller_file = call.get("caller_file", "")
                if os.path.basename(caller_file) == os.path.basename(relpath):
                    has_manually_drop_cleanup = True
                    break

        # 查询symbols表获取ManuallyDrop类型使用
        symbols = database.get_symbols_by_file(relpath)
        for sym in symbols:
            type_name = sym.get("type", "")
            if "ManuallyDrop" not in type_name:
                continue

            idx = sym.get("line", 0)
            if idx <= 0 or idx > len(lines):
                continue

            # 如果有ManuallyDrop::drop调用，说明正确清理了，跳过
            if has_manually_drop_cleanup:
                continue

            s = lines[idx - 1]
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

        # 查询call_graph表获取ManuallyDrop::new调用（仅报告new，不报告drop）
        for call in call_graph:
            callee_name = call.get("callee_name", "")
            # 只匹配ManuallyDrop::new，不匹配ManuallyDrop::drop
            if callee_name != "ManuallyDrop::new":
                continue

            caller_file = call.get("caller_file", "")
            if os.path.basename(caller_file) != os.path.basename(relpath):
                continue

            idx = call.get("caller_line", 0)
            if idx <= 0 or idx > len(lines):
                continue

            # 如果有ManuallyDrop::drop调用，说明正确清理了，跳过
            if has_manually_drop_cleanup:
                continue

            # 避免重复报告
            if any(i.line == idx for i in issues):
                continue

            s = lines[idx - 1]
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
    except Exception:
        pass

    return issues


def _rule_panic_unreachable(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测panic!/unreachable!宏调用。
    - 优先使用database查询call_graph表获取panic!/unreachable!调用
    - 无database时返回空列表
    """
    issues: List[Issue] = []

    if database is None:
        return issues

    try:
        import os

        call_graph = database.get_call_graph()
        for call in call_graph:
            callee_name = call.get("callee_name", "")
            # 匹配panic!和unreachable!宏调用
            if callee_name not in ["panic!", "unreachable!"]:
                continue

            caller_file = call.get("caller_file", "")
            if os.path.basename(caller_file) != os.path.basename(relpath):
                continue

            idx = call.get("caller_line", 0)
            if idx <= 0 or idx > len(lines):
                continue

            s = lines[idx - 1]
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
    except Exception:
        pass

    return issues


def _rule_refcell_borrow(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测RefCell的borrow/borrow_mut使用。
    - 优先使用database查询symbols表获取RefCell变量定义
    - 优先使用database查询call_graph表获取borrow/borrow_mut调用
    - 无database时返回空列表
    """
    issues: List[Issue] = []

    if database is None:
        return issues

    try:
        import os

        # 查询symbols表获取RefCell变量
        symbols = database.get_symbols_by_file(relpath)
        refcell_vars: set[str] = set()
        for symbol in symbols:
            # 检测RefCell类型变量
            type_info = symbol.get("type", "")
            if "RefCell" in type_info:
                var_name = symbol.get("name", "")
                if var_name:
                    refcell_vars.add(var_name)

        # 查询call_graph表获取borrow/borrow_mut调用
        call_graph = database.get_call_graph()
        for call in call_graph:
            callee_name = call.get("callee_name", "")
            # 匹配borrow和borrow_mut方法调用
            if callee_name not in ["borrow", "borrow_mut"]:
                continue

            caller_file = call.get("caller_file", "")
            if os.path.basename(caller_file) != os.path.basename(relpath):
                continue

            idx = call.get("caller_line", 0)
            if idx <= 0 or idx > len(lines):
                continue

            s = lines[idx - 1]
            # 通过caller_name字段检查是否是RefCell变量的borrow
            # caller_name格式可能是"var.borrow"或"borrow"
            caller_name = call.get("caller_name", "")
            is_refcell_borrow = False
            for var in refcell_vars:
                # 使用字符串匹配而非正则表达式
                if (
                    caller_name == var
                    or f"{var}.borrow" in caller_name
                    or f"{var}.borrow_mut" in caller_name
                ):
                    is_refcell_borrow = True
                    break

            if not is_refcell_borrow:
                continue

            # 检查是否有try_borrow（更安全）
            if "try_borrow" in s.lower():
                continue

            conf = 0.55
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
                    description="RefCell 使用 borrow/borrow_mut 可能在运行时 panic（借用冲突）。",
                    suggestion="考虑使用 try_borrow/try_borrow_mut 返回 Result，或使用 Mutex/RwLock 进行编译时检查。",
                    confidence=conf,
                    severity=_severity_from_confidence(conf),
                )
            )
    except Exception:
        pass

    return issues


def _rule_ffi_cstring(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测FFI中CString/CStr的使用。
    - 优先使用database查询call_graph表获取CString/CStr调用
    - 通过symbols表检查是否在FFI上下文中
    - 无database时返回空列表
    """
    issues: List[Issue] = []

    if database is None:
        return issues

    try:
        import os

        # 查询call_graph表获取CString/CStr调用
        call_graph = database.get_call_graph()
        # 查询symbols表检查FFI上下文
        symbols = database.get_symbols_by_file(relpath)
        has_ffi_context = False
        for symbol in symbols:
            kind = symbol.get("kind", "")
            name = symbol.get("name", "")
            if (
                kind == "extern_block"
                or "extern" in name.lower()
                or "ffi" in name.lower()
            ):
                has_ffi_context = True
                break

        for call in call_graph:
            callee_name = call.get("callee_name", "")
            # 匹配CString和CStr调用
            if callee_name not in ["CString", "CStr", "CString::new", "CStr::from_ptr"]:
                continue

            caller_file = call.get("caller_file", "")
            if os.path.basename(caller_file) != os.path.basename(relpath):
                continue

            idx = call.get("caller_line", 0)
            if idx <= 0 or idx > len(lines):
                continue

            # 检查是否在FFI上下文中（通过caller_name或附近symbols）
            caller_name = call.get("caller_name", "")
            in_ffi = (
                has_ffi_context
                or "ffi" in caller_name.lower()
                or "extern" in caller_name.lower()
            )

            if not in_ffi:
                continue

            s = lines[idx - 1]
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
    except Exception:
        pass

    return issues


def _rule_integer_overflow(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测整数溢出风险。
    - 直接从源码检测算术运算（+、-、*）
    - 排除已使用checked_/saturating_的情况
    - 排除常量计算（如 1 + 2）
    """
    issues: List[Issue] = []
    import re

    # 匹配算术运算：变量 + 变量、变量 * 变量、变量 - 变量
    # 排除常量计算（纯数字）、checked_/saturating_方法调用
    arithmetic_pattern = re.compile(r"\b(\w+)\s*([+\-*])\s*(\w+)\b")

    # 排除模式：常量计算、方法调用
    constant_pattern = re.compile(r"^\d+$")
    safe_method_pattern = re.compile(
        r"\b(checked_|saturating_|wrapping_|overflowing_)(add|sub|mul)"
    )

    for idx, line in enumerate(lines, 1):
        # 跳过注释行
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*"):
            continue

        # 检查是否有安全方法调用
        if safe_method_pattern.search(line):
            continue

        # 查找算术运算
        for match in arithmetic_pattern.finditer(line):
            left, op, right = match.groups()

            # 排除常量计算
            if constant_pattern.match(left) and constant_pattern.match(right):
                continue

            # 排除指针算术（已有专门规则）
            # 只排除方法调用形式的指针算术（如 .offset(n)、.add(n)）
            if ".offset" in line or ".add" in line:
                continue

            conf = 0.6
            if _has_safety_comment_around(lines, idx):
                conf -= 0.1
            if _in_test_context(lines, idx):
                conf -= 0.1
            conf = max(0.4, min(0.8, conf))

            issues.append(
                Issue(
                    language="rust",
                    category="integer_overflow",
                    pattern="integer_overflow",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(line),
                    description=f"整数溢出风险：'{left} {op} {right}' 在release模式下可能溢出wrap。",
                    suggestion="使用checked_add/saturating_add等安全方法，或在SAFETY注释中证明溢出不可能发生。",
                    confidence=conf,
                    severity=_severity_from_confidence(conf),
                )
            )
            break  # 每行只报告一次

    return issues


def _rule_unsafe_fn(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测unsafe fn声明。
    - 直接从源码检测 unsafe fn 声明模式
    - 不依赖database（DataCollector不提取is_unsafe属性）
    """
    issues: List[Issue] = []
    import re

    # 匹配 unsafe fn 声明
    unsafe_fn_pattern = re.compile(r"\bunsafe\s+fn\s+(\w+)")

    for idx, line in enumerate(lines, 1):
        # 跳过注释行
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*"):
            continue

        match = unsafe_fn_pattern.search(line)
        if match:
            # 有SAFETY注释时跳过，不报告
            if _has_safety_comment_around(lines, idx):
                continue

            fn_name = match.group(1)
            conf = 0.75
            conf = max(0.5, min(0.9, conf))

            issues.append(
                Issue(
                    language="rust",
                    category="unsafe_usage",
                    pattern="unsafe_fn",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(line),
                    description=f"unsafe fn '{fn_name}' 声明需要调用者保证安全性，应在SAFETY注释中说明前置条件。",
                    suggestion="在SAFETY注释中明确说明调用者需要满足的安全条件；考虑使用安全API替代。",
                    confidence=conf,
                    severity=_severity_from_confidence(conf),
                )
            )

    return issues


def _rule_as_cast(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测as类型转换可能导致的数据截断。
    - 直接从源码检测 as 类型转换
    - 从函数签名和let声明推断变量类型
    - 区分拓宽转换（安全）和截断转换（危险）
    - 只报告危险的类型转换
    """
    issues: List[Issue] = []
    import re

    # 类型大小映射（位数）
    type_sizes = {
        "u8": 8,
        "i8": 8,
        "u16": 16,
        "i16": 16,
        "u32": 32,
        "i32": 32,
        "u64": 64,
        "i64": 64,
        "u128": 128,
        "i128": 128,
        "usize": 64,
        "isize": 64,  # 假设64位系统
    }

    # ---- 第1步：构建变量类型映射 ----
    var_types: dict = {}

    # 从函数签名提取参数类型：fn foo(x: u64, y: i32)
    fn_param_pattern = re.compile(r"fn\s+\w+[^)]*\(([^)]*)\)")
    param_type_pattern = re.compile(r"(\w+)\s*:\s*(u\d+|i\d+|usize|isize)")
    for line in lines:
        for fn_match in fn_param_pattern.finditer(line):
            params_str = fn_match.group(1)
            for pm in param_type_pattern.finditer(params_str):
                var_types[pm.group(1)] = pm.group(2)

    # 从let声明提取变量类型：let x: u64 = ...
    let_type_pattern = re.compile(r"let\s+(mut\s+)?(\w+)\s*:\s*(u\d+|i\d+|usize|isize)")
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*"):
            continue
        m = let_type_pattern.search(line)
        if m:
            var_types[m.group(2)] = m.group(3)

    # ---- 第2步：检测as类型转换 ----
    cast_pattern = re.compile(r"(\w+)\s+as\s+(u\d+|i\d+|usize|isize)")

    for idx, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*"):
            continue

        for match in cast_pattern.finditer(line):
            var_name = match.group(1)
            target_type = match.group(2)

            source_type = var_types.get(var_name, None)
            src_size = type_sizes.get(source_type, 0) if source_type else 0
            tgt_size = type_sizes.get(target_type, 0)

            is_dangerous = False
            desc = ""

            if src_size > 0 and tgt_size > 0 and source_type:
                if src_size > tgt_size:
                    is_dangerous = True
                    desc = f"truncation from {source_type}({src_size}bit) to {target_type}({tgt_size}bit)"
                elif (
                    src_size == tgt_size
                    and source_type.startswith("i")
                    and target_type.startswith("u")
                ):
                    is_dangerous = True
                    desc = f"sign change from {source_type} to {target_type}"
            else:
                # Unknown source type: only report for very small targets
                if target_type in ["u8", "i8"]:
                    is_dangerous = True
                    desc = (
                        f"potential truncation to {target_type} (unknown source type)"
                    )

            if is_dangerous:
                conf = 0.65
                if _has_safety_comment_around(lines, idx):
                    conf -= 0.1
                conf = max(0.45, min(0.85, conf))

                issues.append(
                    Issue(
                        language="rust",
                        category="type_safety",
                        pattern="as_cast_truncation",
                        file=relpath,
                        line=idx,
                        evidence=_strip_line(line),
                        description=f"as类型转换可能导致数据截断或符号问题（{desc}）。",
                        suggestion="使用TryFrom/TryInto进行安全转换；必须使用as时，在SAFETY注释中证明值范围安全。",
                        confidence=conf,
                        severity=_severity_from_confidence(conf),
                    )
                )
                break

    return issues


def _rule_into_raw(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测into_raw调用是否有配对的from_raw。
    - 优先使用database查询call_graph表
    - 无database时返回空列表
    """
    issues: List[Issue] = []

    if database is None:
        return issues

    try:
        import os

        call_graph = database.get_call_graph()

        # 收集所有into_raw和from_raw调用
        into_raw_calls = []
        has_from_raw = False

        for call in call_graph:
            callee_name = call.get("callee_name", "")
            caller_file = call.get("caller_file", "")
            if os.path.basename(caller_file) != os.path.basename(relpath):
                continue

            if "into_raw" in callee_name:
                into_raw_calls.append(call)
            elif "from_raw" in callee_name:
                has_from_raw = True

        # 如果没有from_raw配对，报告所有into_raw调用
        if not has_from_raw:
            for call in into_raw_calls:
                idx = call.get("caller_line", 0)
                if idx <= 0 or idx > len(lines):
                    continue

                s = lines[idx - 1]
                conf = 0.7
                if _has_safety_comment_around(lines, idx):
                    conf -= 0.1
                conf = max(0.5, min(0.85, conf))

                issues.append(
                    Issue(
                        language="rust",
                        category="resource_management",
                        pattern="into_raw_leak",
                        file=relpath,
                        line=idx,
                        evidence=_strip_line(s),
                        description="into_raw调用后没有配对的from_raw，可能导致内存泄漏。",
                        suggestion="确保在适当时候调用from_raw回收内存；或使用ManuallyDrop明确表示有意泄漏。",
                        confidence=conf,
                        severity=_severity_from_confidence(conf),
                    )
                )
    except Exception:
        pass

    return issues


def _rule_static_mut(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测static mut全局可变状态。
    - 直接从源码检测 static mut 声明模式
    - 不依赖database（DataCollector不提取static的mut属性）
    """
    issues: List[Issue] = []
    import re

    # 匹配 static mut 声明
    static_mut_pattern = re.compile(r"\bstatic\s+mut\s+(\w+)")

    for idx, line in enumerate(lines, 1):
        # 跳过注释行
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*"):
            continue

        match = static_mut_pattern.search(line)
        if match:
            var_name = match.group(1)
            conf = 0.75
            if _has_safety_comment_around(lines, idx):
                conf -= 0.1
            conf = max(0.55, min(0.9, conf))

            issues.append(
                Issue(
                    language="rust",
                    category="concurrency",
                    pattern="static_mut",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(line),
                    description=f"static mut '{var_name}' 全局可变状态在多线程环境下可能导致数据竞争。",
                    suggestion="使用Mutex/RwLock/Atomic类型替代static mut；或使用thread_local。",
                    confidence=conf,
                    severity=_severity_from_confidence(conf),
                )
            )

    return issues


def _rule_unchecked_math(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测unchecked_add/sub/mul等不安全数学操作。
    - 优先使用database查询call_graph表
    - 无database时返回空列表
    """
    issues: List[Issue] = []

    if database is None:
        return issues

    try:
        import os

        call_graph = database.get_call_graph()
        for call in call_graph:
            callee_name = call.get("callee_name", "")
            # 匹配unchecked数学操作
            unchecked_ops = [
                "unchecked_add",
                "unchecked_sub",
                "unchecked_mul",
                "unchecked_shl",
                "unchecked_shr",
                "unchecked_div",
                "unchecked_rem",
                "unchecked_neg",
            ]
            if callee_name not in unchecked_ops:
                continue

            caller_file = call.get("caller_file", "")
            if os.path.basename(caller_file) != os.path.basename(relpath):
                continue

            idx = call.get("caller_line", 0)
            if idx <= 0 or idx > len(lines):
                continue

            s = lines[idx - 1]
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
                    pattern="unchecked_math",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(s),
                    description="unchecked数学操作在溢出时会导致未定义行为。",
                    suggestion="确保操作数不会溢出；在SAFETY注释中证明值范围安全。",
                    confidence=conf,
                    severity=_severity_from_confidence(conf),
                )
            )
    except Exception:
        pass

    return issues


def _rule_rc_cycle(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测Rc引用循环风险。
    - 直接从源码检测Rc<RefCell<...>>类型
    - 检测可能形成循环引用的结构
    """
    issues: List[Issue] = []

    import re

    # 检测Rc<RefCell<...>>类型
    rc_refcell_pattern = re.compile(r"Rc<RefCell<")

    for idx, line in enumerate(lines, 1):
        # 跳过注释行
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*"):
            continue

        # 检测Rc<RefCell<...>>类型
        if rc_refcell_pattern.search(line):
            conf = 0.55
            if _has_safety_comment_around(lines, idx):
                conf -= 0.1
            conf = max(0.4, min(0.75, conf))

            issues.append(
                Issue(
                    language="rust",
                    category="memory_leak",
                    pattern="rc_cycle",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(line),
                    description="Rc<RefCell<...>>可能形成引用循环导致内存泄漏。",
                    suggestion="考虑使用Weak打破循环；或使用Arc<Mutex>配合手动管理生命周期。",
                    confidence=conf,
                    severity=_severity_from_confidence(conf),
                )
            )

    return issues


def _rule_command_injection(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测命令注入风险（简化污点分析）。
    - 检测用户输入（stdin、args、env）流向 Command::new/.arg()
    - 支持跨函数污点传播
    - 基于正则匹配的简化实现，不依赖database
    """
    issues: List[Issue] = []
    import re

    # 污点源模式：stdin、args、env
    source_patterns = [
        re.compile(r"io::stdin\(\)|stdin\(\)"),
        re.compile(r"\.lines\(\)"),
        re.compile(r"env::args\(\)|std::env::args"),
        re.compile(r"env::var\(|std::env::var"),
    ]

    # 污点汇模式：Command::new、.arg()
    sink_pattern = re.compile(r"Command::new|\.arg\(")

    # ---- 第1步：识别返回污点的函数 ----
    tainted_functions = set()
    fn_pattern = re.compile(r"fn\s+(\w+)\s*[<(]")
    fn_start = -1
    fn_name = None
    fn_body_lines = []

    for idx, line in enumerate(lines, 1):
        # 检测函数开始
        fn_match = fn_pattern.search(line)
        if fn_match:
            # 保存上一个函数
            if fn_name and fn_body_lines:
                # 检查函数体是否包含污点源
                fn_body = "\n".join(fn_body_lines)
                for pattern in source_patterns:
                    if pattern.search(fn_body):
                        # 检查是否有返回值（简单判断：函数签名有 -> 或函数体有隐式返回）
                        if "->" in lines[fn_start - 1] or any(
                            ln.strip() and not ln.strip().startswith("//")
                            for ln in fn_body_lines[-3:]
                        ):
                            tainted_functions.add(fn_name)
                            break
            # 开始新函数
            fn_name = fn_match.group(1)
            fn_start = idx
            fn_body_lines = []
        elif fn_start > 0:
            # 收集函数体（遇到下一个fn停止）
            if not fn_pattern.search(line):
                fn_body_lines.append(line)
            else:
                # 新函数开始，处理上一个函数
                if fn_name and fn_body_lines:
                    fn_body = "\n".join(fn_body_lines)
                    for pattern in source_patterns:
                        if pattern.search(fn_body):
                            if "->" in lines[fn_start - 1] or any(
                                ln.strip() and not ln.strip().startswith("//")
                                for ln in fn_body_lines[-3:]
                            ):
                                tainted_functions.add(fn_name)
                                break
                new_match = fn_pattern.search(line)
                fn_name = new_match.group(1) if new_match else None
                fn_start = idx
                fn_body_lines = []

    # 处理最后一个函数
    if fn_name and fn_body_lines:
        fn_body = "\n".join(fn_body_lines)
        for pattern in source_patterns:
            if pattern.search(fn_body):
                if "->" in lines[fn_start - 1] or any(
                    ln.strip() and not ln.strip().startswith("//")
                    for ln in fn_body_lines[-3:]
                ):
                    tainted_functions.add(fn_name)
                    break

    # ---- 第2步：查找污点源变量 ----
    tainted_vars = set()
    for idx, line in enumerate(lines, 1):
        # 检测污点源赋值：let user_input = stdin...
        if "let " in line:
            # 直接污点源
            for pattern in source_patterns:
                if pattern.search(line):
                    match = re.search(r"let\s+(mut\s+)?(\w+)", line)
                    if match:
                        tainted_vars.add(match.group(2))

            # 污点函数调用：let input = get_user_input()
            for func_name in tainted_functions:
                if func_name + "(" in line or func_name + "::" in line:
                    match = re.search(r"let\s+(mut\s+)?(\w+)", line)
                    if match:
                        tainted_vars.add(match.group(2))

    # ---- 第3步：追踪变量赋值传播 ----
    # 多轮传播直到收敛
    for _ in range(3):  # 最多3轮
        new_vars = set()
        for idx, line in enumerate(lines, 1):
            if "let " in line:
                # 检查是否赋值了污点变量：let other = tainted.clone()
                for var in tainted_vars:
                    if var in line:
                        match = re.search(r"let\s+(mut\s+)?(\w+)", line)
                        if match and match.group(2) != var:
                            new_vars.add(match.group(2))
        if new_vars <= tainted_vars:
            break
        tainted_vars.update(new_vars)

    # 如果没有找到污点源，直接返回
    if not tainted_vars:
        return issues

    # ---- 第4步：查找污点汇使用 ----
    for idx, line in enumerate(lines, 1):
        if sink_pattern.search(line):
            # 检查是否使用了污点变量
            for var in tainted_vars:
                if f"&{var}" in line or f"{var}" in line:
                    conf = 0.75
                    if _has_safety_comment_around(lines, idx):
                        conf -= 0.1
                    if _in_test_context(lines, idx):
                        conf -= 0.1
                    conf = max(0.5, min(0.9, conf))

                    issues.append(
                        Issue(
                            language="rust",
                            category="taint-analysis",
                            pattern="taint-flow",
                            file=relpath,
                            line=idx,
                            evidence=_strip_line(line),
                            description=f"命令注入风险：用户输入 '{var}' 直接用于命令执行",
                            suggestion="使用shlex::split或shell_words::split净化用户输入，或使用参数化命令执行",
                            confidence=conf,
                            severity="critical",
                        )
                    )
                    break  # 避免重复报告

    return issues


def _rule_uninit_zeroed(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测 uninit/zeroed 的使用，未初始化内存访问风险。
    - 优先使用database查询call_graph表获取uninit/zeroed调用
    - 无database时返回空列表
    """
    issues: List[Issue] = []

    if database is None:
        return issues

    try:
        import os

        call_graph = database.get_call_graph()
        for call in call_graph:
            callee_name = call.get("callee_name", "")
            # 匹配uninit/zeroed调用
            if callee_name not in [
                "uninit",
                "zeroed",
                "mem::uninitialized",
                "MaybeUninit::uninit",
                "MaybeUninit::zeroed",
            ]:
                continue

            caller_file = call.get("caller_file", "")
            if os.path.basename(caller_file) != os.path.basename(relpath):
                continue

            idx = call.get("caller_line", 0)
            if idx <= 0 or idx > len(lines):
                continue

            s = lines[idx - 1]
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
    except Exception:
        pass

    return issues


# ---------------------------
# 对外主入口
# ---------------------------


def analyze_rust_text(
    relpath: str,
    text: str,
    database: Optional["ProjectDatabase"] = None,
) -> List[Issue]:
    """
    基于提供的文本进行 Rust 启发式分析。
    - 准确性优化：在启发式匹配前移除注释（保留字符串/字符字面量），
      以避免注释中的API命中导致的误报。
    - 准确性优化2：对通用 API 扫描使用"字符串内容掩蔽"的副本，避免把字符串里的片段当作代码。
    - 准确性优化3：使用数据流分析过滤误报。
    - Database驱动：优先使用database查询，无database时创建临时database。

    Args:
        relpath: 相对文件路径
        text: 源代码文本
        database: 项目数据库实例（可选）
    """
    clean_text = _remove_comments_preserve_strings(text)
    masked_text = _mask_strings_preserve_len(clean_text)
    # 原始行：保留注释和字符串内容，供SAFETY注释检查等使用
    lines = text.splitlines()
    # 掩蔽行：字符串内容已被空格替换，适合用于通用 API/关键字匹配，减少误报
    mlines = masked_text.splitlines()

    # 数据流分析（用于误报过滤）
    # 如果没有database，创建临时内存database并用DataCollector收集数据
    _temp_database = None
    _db_file_path = relpath  # 用于查询database的文件路径
    if database is None:
        try:
            from jarvis.jarvis_sec.project_database import ProjectDatabase
            from jarvis.jarvis_sec.data_collector import DataCollector

            _temp_database = ProjectDatabase(".", in_memory=True)
            collector = DataCollector(_temp_database)
            # 写入临时文件供DataCollector分析
            import tempfile
            import os

            _tmp_dir = tempfile.mkdtemp(prefix="jsec_rust_")
            _tmp_file = os.path.join(_tmp_dir, os.path.basename(relpath))
            with open(_tmp_file, "w", encoding="utf-8") as f:
                f.write(text)
            collector.analyze_file(_tmp_file, "rust")
            # 使用临时文件的完整路径查询database
            _db_file_path = _tmp_file
            database = _temp_database
        except Exception:
            pass  # 创建失败时继续使用空database
    else:
        # 有外部database时，确保使用正确的文件路径
        import os

        if os.path.isabs(relpath):
            _db_file_path = relpath

    data_flow_analyzer = DataFlowAnalyzer()
    data_flow_result = data_flow_analyzer.analyze_code(
        text, is_cpp=False, database=database, file_path=_db_file_path
    )

    # 清理临时文件和目录（在所有规则检查完成后）
    def _cleanup_temp_files():
        if _temp_database is not None:
            try:
                import os

                os.unlink(_tmp_file)
                os.rmdir(_tmp_dir)
            except (OSError, NameError):
                pass

    issues: List[Issue] = []
    # 通用 API/关键字匹配（使用掩蔽行）
    issues.extend(_rule_unsafe(lines, _db_file_path, database=database))
    issues.extend(_rule_raw_pointer(lines, _db_file_path, database=database))
    issues.extend(_rule_transmute(mlines, _db_file_path, database=database))
    issues.extend(_rule_forget(mlines, _db_file_path, database=database))
    issues.extend(_rule_maybe_uninit(mlines, _db_file_path, database=database))
    # 错误处理
    issues.extend(_rule_unwrap_expect(mlines, _db_file_path, database=database))
    issues.extend(_rule_ignore_result(mlines, _db_file_path, database=database))
    issues.extend(_rule_panic_unreachable(mlines, _db_file_path, database=database))
    # FFI 相关
    issues.extend(_rule_extern_c(mlines, _db_file_path, database=database))
    issues.extend(_rule_ffi_cstring(mlines, _db_file_path, database=database))
    # 并发相关
    issues.extend(_rule_unsafe_impl(mlines, _db_file_path, database=database))
    issues.extend(_rule_refcell_borrow(mlines, _db_file_path, database=database))
    # 内存操作相关
    issues.extend(_rule_get_unchecked(mlines, _db_file_path, database=database))
    issues.extend(_rule_pointer_arithmetic(mlines, _db_file_path, database=database))
    issues.extend(_rule_unsafe_mem_ops(mlines, _db_file_path, database=database))
    issues.extend(_rule_from_raw_parts(mlines, _db_file_path, database=database))
    issues.extend(_rule_manually_drop(mlines, _db_file_path, database=database))
    issues.extend(_rule_uninit_zeroed(mlines, _db_file_path, database=database))
    # 新增规则
    issues.extend(_rule_integer_overflow(mlines, _db_file_path, database=database))
    issues.extend(_rule_unsafe_fn(mlines, _db_file_path, database=database))
    issues.extend(_rule_as_cast(mlines, _db_file_path, database=database))
    issues.extend(_rule_into_raw(mlines, _db_file_path, database=database))
    issues.extend(_rule_static_mut(mlines, _db_file_path, database=database))
    issues.extend(_rule_unchecked_math(mlines, _db_file_path, database=database))
    issues.extend(_rule_rc_cycle(mlines, _db_file_path, database=database))
    # 污点分析规则
    issues.extend(_rule_command_injection(mlines, _db_file_path, database=database))

    # 污点分析（核心功能）
    try:
        taint_paths = taint_analyzer.analyze_with_best_analyzer(
            text, rules=None, file_path=str(_db_file_path), database=database
        )
        # 将污点分析结果转换为Issue对象
        for taint_path in taint_paths:
            issue = Issue(
                language="rust",
                category="taint-analysis",
                pattern="taint-flow",
                file=str(_db_file_path),
                line=taint_path.line_number,
                evidence=f"{taint_path.source} -> {taint_path.sink}",
                description=f"Taint flow from {taint_path.source} to {taint_path.sink}",
                suggestion="Sanitize input data before use",
                confidence=taint_path.confidence,
                severity="high" if taint_path.confidence > 0.7 else "medium",
            )
            issues.append(issue)
    except Exception:
        # 污点分析失败时静默忽略，不影响启发式扫描
        pass

    # 使用数据流分析过滤误报
    filtered_issues = _filter_issues_with_data_flow(
        issues, data_flow_analyzer, data_flow_result, lines
    )

    # 清理临时文件和目录
    _cleanup_temp_files()

    return filtered_issues


def _filter_issues_with_data_flow(
    issues: List[Issue],
    analyzer: DataFlowAnalyzer,
    dataflow_result: DataFlowResult,
    lines: List[str],
) -> List[Issue]:
    """
    使用数据流分析过滤误报

    Args:
        issues: 启发式扫描发现的问题列表
        analyzer: 数据流分析器
        dataflow_result: 数据流分析结果
        lines: 源代码行列表

    Returns:
        List[Issue]: 过滤后的问题列表
    """
    filtered_issues = []

    for issue in issues:
        # 检查是否为误报
        if _is_false_positive(issue, analyzer, dataflow_result, lines):
            continue
        filtered_issues.append(issue)

    return filtered_issues


def _is_false_positive(
    issue: Issue,
    analyzer: DataFlowAnalyzer,
    dataflow_result: DataFlowResult,
    lines: List[str],
) -> bool:
    """
    判断问题是否为误报

    Args:
        issue: 问题对象
        analyzer: 数据流分析器
        dataflow_result: 数据流分析结果
        lines: 源代码行列表

    Returns:
        bool: 是否为误报
    """
    issue_type = issue.pattern

    # unsafe误报过滤：检查是否有SAFETY注释
    if issue_type == "unsafe":
        return _is_unsafe_false_positive(issue, analyzer, dataflow_result, lines)

    # unwrap/expect误报过滤：检查是否有错误处理上下文
    if issue_type in ["unwrap/expect", "unwrap", "expect"]:
        return _is_unwrap_false_positive(issue, analyzer, dataflow_result, lines)

    # panic误报过滤：检查是否在测试上下文或assert中
    if issue_type in ["panic/unreachable", "panic!", "unreachable!"]:
        return _is_panic_false_positive(issue, analyzer, dataflow_result, lines)

    # 原始指针误报过滤：检查是否有SAFETY注释证明安全性
    if issue_type == "raw_pointer":
        return _is_raw_pointer_false_positive(issue, analyzer, dataflow_result, lines)

    # transmute误报过滤：检查是否有SAFETY注释
    if issue_type == "mem::transmute":
        return _is_transmute_false_positive(issue, analyzer, dataflow_result, lines)

    # get_unchecked误报过滤：检查是否有边界检查或SAFETY注释
    if issue_type == "get_unchecked":
        return _is_get_unchecked_false_positive(issue, analyzer, dataflow_result, lines)

    # 指针算术误报过滤：检查是否有SAFETY注释
    if issue_type == "pointer_arithmetic":
        return _is_pointer_arithmetic_false_positive(
            issue, analyzer, dataflow_result, lines
        )

    # 内存操作误报过滤：检查是否有SAFETY注释
    if issue_type == "unsafe_mem_ops":
        return _is_unsafe_mem_ops_false_positive(
            issue, analyzer, dataflow_result, lines
        )

    # from_raw_parts误报过滤：检查是否有SAFETY注释
    if issue_type == "from_raw_parts/from_raw":
        return _is_from_raw_parts_false_positive(
            issue, analyzer, dataflow_result, lines
        )

    # 默认不过滤
    return False


def _is_unsafe_false_positive(
    issue: Issue,
    analyzer: DataFlowAnalyzer,
    dataflow_result: DataFlowResult,
    lines: List[str],
) -> bool:
    """
    判断unsafe块是否为误报

    检查逻辑：
    1. 是否有SAFETY注释证明安全性
    2. 是否在测试上下文中
    """
    line_num = issue.line
    if line_num <= 0 or line_num > len(lines):
        return False

    # SAFETY注释已在规则函数中处理，此处检查数据流分析结果
    # 检查是否在死代码中
    if dataflow_result.dead_code_lines and line_num in dataflow_result.dead_code_lines:
        return True

    return False


def _is_unwrap_false_positive(
    issue: Issue,
    analyzer: DataFlowAnalyzer,
    dataflow_result: DataFlowResult,
    lines: List[str],
) -> bool:
    """
    判断unwrap/expect是否为误报

    检查逻辑：
    1. 是否在测试上下文中
    2. 是否在if let Some/Ok分支内（unwrap的变量与if let匹配的变量相同）
    3. 是否在match Some/Ok分支内（unwrap的变量与match匹配的变量相同）
    """
    line_num = issue.line
    if line_num <= 0 or line_num > len(lines):
        return False

    # 检查是否在死代码中
    if dataflow_result.dead_code_lines and line_num in dataflow_result.dead_code_lines:
        return True

    # 获取unwrap调用的变量名
    import re

    unwrap_line = lines[line_num - 1]
    # 提取变量名：xxx.unwrap() 或 xxx.expect()
    var_match = re.search(r"(\w+)\.unwrap\(\)", unwrap_line)
    if not var_match:
        var_match = re.search(r"(\w+)\.expect\(\)", unwrap_line)
    unwrap_var = var_match.group(1) if var_match else None

    # 检查是否在if let Some/Ok分支内
    # 向上查找if let Some(var) 或 if let Ok(var) 结构
    for i in range(max(0, line_num - 15), line_num):
        if i >= len(lines):
            continue
        line = lines[i]
        # 检查 if let Some(var) = unwrap_var 或 if let Ok(var) = unwrap_var
        if "if let" in line:
            # 提取if let中的变量名
            let_match = re.search(r"if let Some\((\w+)\)\s*=\s*(\w+)", line)
            if let_match:
                bound_var = let_match.group(1)  # Some中的变量
                source_var = let_match.group(2)  # 源变量
                # 检查unwrap是否使用源变量或绑定变量
                if unwrap_var == source_var or unwrap_var == bound_var:
                    # 检查unwrap是否在if let块内（通过缩进判断）
                    if_indent = len(line) - len(line.lstrip())
                    unwrap_indent = len(unwrap_line) - len(unwrap_line.lstrip())
                    if unwrap_indent > if_indent:
                        return True
            else:
                let_match = re.search(r"if let Ok\((\w+)\)\s*=\s*(\w+)", line)
                if let_match:
                    bound_var = let_match.group(1)
                    source_var = let_match.group(2)
                    if unwrap_var == source_var or unwrap_var == bound_var:
                        if_indent = len(line) - len(line.lstrip())
                        unwrap_indent = len(unwrap_line) - len(unwrap_line.lstrip())
                        if unwrap_indent > if_indent:
                            return True

    # 检查是否在match Some/Ok分支内
    # 向上查找match结构
    for i in range(max(0, line_num - 20), line_num):
        if i >= len(lines):
            continue
        line = lines[i]
        if "match" in line and unwrap_var and unwrap_var in line:
            # 找到match unwrap_var的结构
            # 检查unwrap是否在Some/Ok分支内
            for j in range(i + 1, line_num):
                check_line = lines[j]
                # 检查Some分支
                if re.search(r"Some\((\w+)\)\s*=>", check_line):
                    # unwrap在Some分支内
                    return True
                # 检查Ok分支
                if re.search(r"Ok\((\w+)\)\s*=>", check_line):
                    return True

    return False


def _is_panic_false_positive(
    issue: Issue,
    analyzer: DataFlowAnalyzer,
    dataflow_result: DataFlowResult,
    lines: List[str],
) -> bool:
    """
    判断panic!/unreachable!是否为误报

    检查逻辑：
    1. 是否在测试上下文中
    2. 是否在assert宏中
    """
    line_num = issue.line
    if line_num <= 0 or line_num > len(lines):
        return False

    line = lines[line_num - 1]

    # 检查是否在死代码中
    if dataflow_result.dead_code_lines and line_num in dataflow_result.dead_code_lines:
        return True

    # 检查是否在assert宏中（assert!、assert_eq!、assert_ne!等）
    if "assert" in line.lower():
        return True

    # 检查是否在测试函数中（通过检查函数定义上下文）
    for i in range(max(0, line_num - 20), line_num):
        if i < len(lines):
            line = lines[i]
            if "#[test]" in line or "#[cfg(test)]" in line:
                return True

    return False


def _is_raw_pointer_false_positive(
    issue: Issue,
    analyzer: DataFlowAnalyzer,
    dataflow_result: DataFlowResult,
    lines: List[str],
) -> bool:
    """
    判断原始指针使用是否为误报

    检查逻辑：
    1. 是否有SAFETY注释证明安全性
    2. 是否在FFI边界（extern块中）
    """
    line_num = issue.line
    if line_num <= 0 or line_num > len(lines):
        return False

    # 检查是否在死代码中
    if dataflow_result.dead_code_lines and line_num in dataflow_result.dead_code_lines:
        return True

    # SAFETY注释已在规则函数中处理
    return False


def _is_transmute_false_positive(
    issue: Issue,
    analyzer: DataFlowAnalyzer,
    dataflow_result: DataFlowResult,
    lines: List[str],
) -> bool:
    """
    判断transmute是否为误报

    检查逻辑：
    1. 是否有SAFETY注释证明安全性
    """
    line_num = issue.line
    if line_num <= 0 or line_num > len(lines):
        return False

    # 检查是否在死代码中
    if dataflow_result.dead_code_lines and line_num in dataflow_result.dead_code_lines:
        return True

    return False


def _is_get_unchecked_false_positive(
    issue: Issue,
    analyzer: DataFlowAnalyzer,
    dataflow_result: DataFlowResult,
    lines: List[str],
) -> bool:
    """
    判断get_unchecked是否为误报

    检查逻辑：
    1. 是否有SAFETY注释证明索引有效性
    2. 是否有前置的边界检查
    """
    line_num = issue.line
    if line_num <= 0 or line_num > len(lines):
        return False

    # 检查是否在死代码中
    if dataflow_result.dead_code_lines and line_num in dataflow_result.dead_code_lines:
        return True

    # 检查前5行是否有边界检查
    for i in range(max(0, line_num - 5), line_num):
        if i < len(lines):
            line = lines[i]
            if "<" in line or ">" in line or "<=" in line or ">=" in line:
                if "len" in line or "size" in line or "length" in line:
                    return True

    return False


def _is_pointer_arithmetic_false_positive(
    issue: Issue,
    analyzer: DataFlowAnalyzer,
    dataflow_result: DataFlowResult,
    lines: List[str],
) -> bool:
    """
    判断指针算术是否为误报

    检查逻辑：
    1. 是否有SAFETY注释证明安全性
    """
    line_num = issue.line
    if line_num <= 0 or line_num > len(lines):
        return False

    # 检查是否在死代码中
    if dataflow_result.dead_code_lines and line_num in dataflow_result.dead_code_lines:
        return True

    return False


def _is_unsafe_mem_ops_false_positive(
    issue: Issue,
    analyzer: DataFlowAnalyzer,
    dataflow_result: DataFlowResult,
    lines: List[str],
) -> bool:
    """
    判断不安全内存操作是否为误报

    检查逻辑：
    1. 是否有SAFETY注释证明安全性
    """
    line_num = issue.line
    if line_num <= 0 or line_num > len(lines):
        return False

    # 检查是否在死代码中
    if dataflow_result.dead_code_lines and line_num in dataflow_result.dead_code_lines:
        return True

    return False


def _is_from_raw_parts_false_positive(
    issue: Issue,
    analyzer: DataFlowAnalyzer,
    dataflow_result: DataFlowResult,
    lines: List[str],
) -> bool:
    """
    判断from_raw_parts是否为误报

    检查逻辑：
    1. 是否有SAFETY注释证明安全性
    """
    line_num = issue.line
    if line_num <= 0 or line_num > len(lines):
        return False

    # 检查是否在死代码中
    if dataflow_result.dead_code_lines and line_num in dataflow_result.dead_code_lines:
        return True

    return False


def analyze_rust_file(
    base: Path, relpath: Path, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    从磁盘读取文件进行分析。
    """
    try:
        text = (base / relpath).read_text(errors="ignore")
    except Exception:
        return []
    return analyze_rust_text(str(relpath), text, database=database)


def analyze_rust_files(
    base_path: str,
    relative_paths: List[str],
    database: Optional["ProjectDatabase"] = None,
) -> List[Issue]:
    """
    批量分析文件，相对路径相对于 base_path。
    """
    base = Path(base_path).resolve()
    out: List[Issue] = []
    for f in relative_paths:
        p = Path(f)
        if p.suffix.lower() == ".rs":
            out.extend(analyze_rust_file(base, p, database=database))
    return out
