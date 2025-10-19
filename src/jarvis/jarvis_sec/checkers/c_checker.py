# -*- coding: utf-8 -*-
"""
OpenHarmony 安全演进多Agent套件 —— C/C++ 启发式安全检查器（阶段一）

目标与范围：
- 聚焦内存管理、缓冲区操作、错误处理三类基础安全问题，提供可解释的启发式检测与置信度评估。
- 面向 C/C++ 与头文件（.c/.cpp/.h/.hpp）。

输出约定：
- 返回 jarvis.jarvis_sec.workflow.Issue 列表（保持结构化，便于聚合评分与报告生成）。
- 置信度区间 [0,1]，基于命中规则与上下文线索加权计算；严重性（severity）分为 high/medium/low。

使用方式（示例）：
- from jarvis.jarvis_sec.checkers.c_checker import analyze_files
- issues = analyze_files("./repo", ["src/a.c", "include/a.h"])
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from jarvis.jarvis_sec.types import Issue


# ---------------------------
# 规则库（正则表达式）
# ---------------------------

RE_UNSAFE_API = re.compile(
    r"\b(strcpy|strcat|gets|sprintf|vsprintf|scanf)\s*\(",
    re.IGNORECASE,
)
RE_BOUNDARY_FUNCS = re.compile(
    r"\b(memcpy|memmove|strncpy|strncat)\s*\(",
    re.IGNORECASE,
)
RE_MEM_MGMT = re.compile(
    r"\b(malloc|calloc|realloc|free|new\s+|delete\b)",
    re.IGNORECASE,
)
RE_IO_API = re.compile(
    r"\b(fopen|fclose|fread|fwrite|read|write|open|close)\s*\(",
    re.IGNORECASE,
)

# 新增：格式化字符串/危险临时文件/命令执行等风险 API 模式
RE_PRINTF_LIKE = re.compile(r"\b(printf|sprintf|snprintf|vsprintf|vsnprintf)\s*\(", re.IGNORECASE)
RE_FPRINTF = re.compile(r"\bfprintf\s*\(", re.IGNORECASE)
RE_INSECURE_TMP = re.compile(r"\b(tmpnam|tempnam|mktemp)\s*\(", re.IGNORECASE)
RE_SYSTEM_LIKE = re.compile(r"\b(system|popen)\s*\(", re.IGNORECASE)
RE_EXEC_LIKE = re.compile(r"\b(execvp|execlp|execvpe|execl|execve|execv)\s*\(", re.IGNORECASE)
RE_SCANF_CALL = re.compile(r'\b(?:[fs]?scanf)\s*\(\s*"([^"]*)"', re.IGNORECASE)
# 线程/锁相关
RE_PTHREAD_LOCK = re.compile(r"\bpthread_mutex_lock\s*\(\s*&\s*([A-Za-z_]\w*)\s*\)\s*;?", re.IGNORECASE)
RE_PTHREAD_UNLOCK = re.compile(r"\bpthread_mutex_unlock\s*\(\s*&\s*([A-Za-z_]\w*)\s*\)\s*;?", re.IGNORECASE)
# 其他危险用法相关
RE_ATOI_FAMILY = re.compile(r"\b(atoi|atol|atoll|atof)\s*\(", re.IGNORECASE)
RE_RAND = re.compile(r"\b(rand|srand)\s*\(", re.IGNORECASE)
RE_STRTOK = re.compile(r"\bstrtok\s*\(", re.IGNORECASE)
RE_OPEN_PERMISSIVE = re.compile(r"\bopen\s*\(\s*[^,]+,\s*[^,]*O_CREAT[^,]*,\s*(0[0-7]{3,4})\s*\)", re.IGNORECASE)
RE_FOPEN_MODE = re.compile(r'\bfopen\s*\(\s*[^,]+,\s*"([^"]+)"\s*\)', re.IGNORECASE)
RE_GENERIC_ASSIGN = re.compile(r"\b([A-Za-z_]\w*)\s*=\s*")
RE_FREE_CALL_ANY = re.compile(r"\bfree\s*\(\s*([^)]+?)\s*\)", re.IGNORECASE)
# 扩展：更多危险用法相关
RE_ALLOCA = re.compile(r"\balloca\s*\(\s*([^)]+)\s*\)", re.IGNORECASE)
RE_VLA_DECL = re.compile(
    r"\b(?:const\s+|volatile\s+|static\s+|register\s+|unsigned\s+|signed\s+)?[A-Za-z_]\w*(?:\s+\*|\s+)+[A-Za-z_]\w*\s*\[\s*([^\]]+)\s*\]\s*;",
    re.IGNORECASE,
)
RE_PTHREAD_RET = re.compile(
    r"\b(pthread_(?:mutex_(?:lock|trylock|timedlock)|create|cond_(?:wait|timedwait)|join|detach))\s*\(",
    re.IGNORECASE,
)
RE_PTHREAD_COND_WAIT = re.compile(r"\bpthread_cond_(?:timed)?wait\s*\(", re.IGNORECASE)
RE_PTHREAD_CREATE = re.compile(r"\bpthread_create\s*\(\s*&\s*([A-Za-z_]\w*)\s*,", re.IGNORECASE)
RE_PTHREAD_JOIN = re.compile(r"\bpthread_join\s*\(\s*([A-Za-z_]\w*)\s*,", re.IGNORECASE)
RE_PTHREAD_DETACH = re.compile(r"\bpthread_detach\s*\(\s*([A-Za-z_]\w*)\s*\)", re.IGNORECASE)
RE_INET_LEGACY = re.compile(r"\b(inet_addr|inet_aton)\s*\(", re.IGNORECASE)
RE_TIME_UNSAFE = re.compile(r"\b(asctime|ctime|localtime|gmtime)\s*\(", re.IGNORECASE)
RE_GETENV = re.compile(r'\bgetenv\s*\(\s*"[^"]*"\s*\)', re.IGNORECASE)

# 辅助正则
RE_REALLOC_ASSIGN_BACK = re.compile(
    r"\b([A-Za-z_]\w*)\s*=\s*realloc\s*\(\s*\1\s*,", re.IGNORECASE
)
RE_MALLOC_ASSIGN = re.compile(
    r"\b([A-Za-z_]\w*)\s*=\s*malloc\s*\(", re.IGNORECASE
)
RE_CALLOC_ASSIGN = re.compile(
    r"\b([A-Za-z_]\w*)\s*=\s*calloc\s*\(", re.IGNORECASE
)
RE_NEW_ASSIGN = re.compile(
    r"\b([A-Za-z_]\w*)\s*=\s*new\b", re.IGNORECASE
)
RE_DEREF = re.compile(
    r"(\*|->)\s*[A-Za-z_]\w*|\b[A-Za-z_]\w*\s*\[", re.IGNORECASE
)
RE_NULL_CHECK = re.compile(
    r"\bif\s*\(\s*(!\s*)?[A-Za-z_]\w*\s*(==|!=)\s*NULL\s*\)|\bif\s*\(\s*[A-Za-z_]\w*\s*\)", re.IGNORECASE
)
RE_FREE_VAR = re.compile(r"free\s*\(\s*([A-Za-z_]\w*)\s*\)\s*;", re.IGNORECASE)
RE_USE_VAR = re.compile(r"\b([A-Za-z_]\w*)\b")
RE_STRLEN_IN_SIZE = re.compile(r"\bstrlen\s*\(", re.IGNORECASE)
RE_SIZEOF_PTR = re.compile(r"\bsizeof\s*\(\s*\*\s*[A-Za-z_]\w*\s*\)", re.IGNORECASE)
RE_STRNCPY = re.compile(r"\bstrncpy\s*\(", re.IGNORECASE)
RE_STRNCAT = re.compile(r"\bstrncat\s*\(", re.IGNORECASE)


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


def _has_null_check_around(var: str, lines: Sequence[str], line_no: int, radius: int = 5) -> bool:
    for i, s in _window(lines, line_no, before=radius, after=radius):
        # 粗略判定：出现 if(ptr) / if(ptr != NULL) / if(NULL != ptr) 等
        if re.search(rf"\bif\s*\(\s*{re.escape(var)}\s*\)", s):
            return True
        if re.search(rf"\bif\s*\(\s*{re.escape(var)}\s*(==|!=)\s*NULL\s*\)", s):
            return True
        if re.search(rf"\bif\s*\(\s*NULL\s*(==|!=)\s*{re.escape(var)}\s*\)", s):
            return True
    return False


def _has_len_bound_around(lines: Sequence[str], line_no: int, radius: int = 3) -> bool:
    for _, s in _window(lines, line_no, before=radius, after=radius):
        # 检测是否出现长度上界/检查（非常粗略）
        if any(k in s for k in ["sizeof(", "BUFFER_SIZE", "MAX_", "min(", "clamp(", "snprintf", "strlcpy", "strlcat"]):
            return True
    return False


def _severity_from_confidence(conf: float, base: str) -> str:
    # 基于基类目提供缺省严重度调整
    if conf >= 0.8:
        return "high"
    if conf >= 0.6:
        return "medium"
    return "low"


# ---------------------------
# 具体验证规则
# ---------------------------

def _rule_unsafe_api(lines: Sequence[str], relpath: str) -> List[Issue]:
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        m = RE_UNSAFE_API.search(s)
        if not m:
            continue
        api = m.group(1)
        conf = 0.85
        if not _has_len_bound_around(lines, idx, radius=2):
            conf += 0.05
        severity = _severity_from_confidence(conf, "unsafe_api")
        issues.append(
            Issue(
                language="c/cpp",
                category="unsafe_api",
                pattern=api,
                file=relpath,
                line=idx,
                evidence=_strip_line(s),
                description="使用不安全/高风险字符串API，可能导致缓冲区溢出或格式化风险。",
                suggestion="替换为带边界的安全API（如 snprintf/strlcpy 等）或加入显式长度检查。",
                confidence=min(conf, 0.95),
                severity=severity,
            )
        )
    return issues


def _rule_boundary_funcs(lines: Sequence[str], relpath: str) -> List[Issue]:
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        m = RE_BOUNDARY_FUNCS.search(s)
        if not m:
            continue
        api = m.group(1)
        conf = 0.65
        # 如果参数中包含 strlen 或 sizeof( *ptr )，提高风险（长度来源不稳定/指针大小）
        if RE_STRLEN_IN_SIZE.search(s) or RE_SIZEOF_PTR.search(s):
            conf += 0.15
        # 周围未见边界检查，再提高
        if not _has_len_bound_around(lines, idx, radius=2):
            conf += 0.1
        issues.append(
            Issue(
                language="c/cpp",
                category="buffer_overflow",
                pattern=api,
                file=relpath,
                line=idx,
                evidence=_strip_line(s),
                description="缓冲区操作涉及长度/边界，需确认长度来源是否可靠，避免越界。",
                suggestion="核对目标缓冲区大小与拷贝长度；对外部输入进行校验；优先使用安全封装。",
                confidence=min(conf, 0.95),
                severity=_severity_from_confidence(conf, "buffer_overflow"),
            )
        )
    return issues


def _rule_realloc_assign_back(lines: Sequence[str], relpath: str) -> List[Issue]:
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        m = RE_REALLOC_ASSIGN_BACK.search(s)
        if not m:
            continue
        var = m.group(1)
        conf = 0.8
        # 如果附近未见错误处理/NULL检查，置信度更高
        if not _has_null_check_around(var, lines, idx, radius=3):
            conf += 0.1
        issues.append(
            Issue(
                language="c/cpp",
                category="memory_mgmt",
                pattern="realloc_overwrite",
                file=relpath,
                line=idx,
                evidence=_strip_line(s),
                description=f"realloc 直接覆盖原指针 {var}，若失败将导致原内存泄漏。",
                suggestion="使用临时指针接收 realloc 返回值，判空成功后再赋值回原指针。",
                confidence=min(conf, 0.95),
                severity=_severity_from_confidence(conf, "memory_mgmt"),
            )
        )
    return issues


def _rule_malloc_no_null_check(lines: Sequence[str], relpath: str) -> List[Issue]:
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        for pat in (RE_MALLOC_ASSIGN, RE_CALLOC_ASSIGN, RE_NEW_ASSIGN):
            m = pat.search(s)
            if not m:
                continue
            var = m.group(1)
            # 在后续若干行中存在明显解引用/使用但未见 NULL 检查，提示
            conf = 0.55
            has_check = _has_null_check_around(var, lines, idx, radius=4)
            # 搜索后续 6 行是否出现变量使用（粗略）
            used = False
            for j, sj in _window(lines, idx, before=0, after=6):
                if j == idx:
                    continue
                if re.search(rf"\b{re.escape(var)}\b(\s*(->|\[|\())", sj):
                    used = True
                    break
            if used and not has_check:
                conf += 0.25
            elif not has_check:
                conf += 0.1
            issues.append(
                Issue(
                    language="c/cpp",
                    category="memory_mgmt",
                    pattern="alloc_no_null_check",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(s),
                    description=f"内存/对象分配给 {var} 后可能未检查是否成功（NULL 检查缺失）。",
                    suggestion="在使用前检查分配结果是否为 NULL，并在错误路径上释放已获取的资源。",
                    confidence=min(conf, 0.9),
                    severity=_severity_from_confidence(conf, "memory_mgmt"),
                )
            )
    return issues


def _rule_uaf_suspect(lines: Sequence[str], relpath: str) -> List[Issue]:
    # 搜集 free(var) 的变量，再检查后续是否出现变量使用
    issues: List[Issue] = []
    text = "\n".join(lines)
    free_vars = re.findall(RE_FREE_VAR, text)
    for v in set(free_vars):
        # free 后再次出现 v（非常粗糙的线索）
        pattern = re.compile(rf"free\s*\(\s*{re.escape(v)}\s*\)\s*;(.|\n)+?\b{re.escape(v)}\b", re.MULTILINE)
        if pattern.search(text):
            # 取第一次 free 的行号作为证据
            for idx, s in enumerate(lines, start=1):
                if re.search(rf"free\s*\(\s*{re.escape(v)}\s*\)\s*;", s):
                    issues.append(
                        Issue(
                            language="c/cpp",
                            category="memory_mgmt",
                            pattern="use_after_free_suspect",
                            file=relpath,
                            line=idx,
                            evidence=_strip_line(s),
                            description=f"变量 {v} 在 free 后可能仍被使用（UAF 线索，需人工确认）。",
                            suggestion="free 后将指针置 NULL；严格管理生命周期；增加动态/静态检测。",
                            confidence=0.6,
                            severity="high",
                        )
                    )
                    break
    return issues


def _rule_unchecked_io(lines: Sequence[str], relpath: str) -> List[Issue]:
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        if not RE_IO_API.search(s):
            continue
        # 简单启发：若本行或紧随其后 2 行没有涉及条件判断/返回值比较，认为可能未检查错误
        conf = 0.5
        nearby = " ".join(_safe_line(lines, i) for i in range(idx, min(idx + 2, len(lines)) + 1))
        if not re.search(r"\bif\s*\(|>=|<=|==|!=|<|>", nearby):
            conf += 0.15
        issues.append(
            Issue(
                language="c/cpp",
                category="error_handling",
                pattern="io_call",
                file=relpath,
                line=idx,
                evidence=_strip_line(s),
                description="I/O/系统调用可能未检查返回值，存在错误处理缺失风险。",
                suggestion="检查返回值/errno；在错误路径上释放资源（句柄/内存/锁）。",
                confidence=min(conf, 0.75),
                severity=_severity_from_confidence(conf, "error_handling"),
            )
        )
    return issues


def _rule_strncpy_no_nullterm(lines: Sequence[str], relpath: str) -> List[Issue]:
    # 使用 strncpy/strncat 后未确保目标缓冲区以 NUL 结尾的常见隐患（启发式）
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        if RE_STRNCPY.search(s) or RE_STRNCAT.search(s):
            conf = 0.55
            # 若邻近窗口未出现手动 '\0' 终止或显式长度-1 等处理，提升风险
            window_text = " ".join(t for _, t in _window(lines, idx, before=1, after=2))
            if not re.search(r"\\0|'\0'|\"\\0\"|len\s*-\s*1|sizeof\s*\(\s*\w+\s*\)\s*-\s*1", window_text):
                conf += 0.15
            issues.append(
                Issue(
                    language="c/cpp",
                    category="buffer_overflow",
                    pattern="strncpy/strncat",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(s),
                    description="使用 strncpy/strncat 可能未自动添加 NUL 终止，导致潜在字符串未终止风险。",
                    suggestion="确保目标缓冲区以 '\\0' 终止（例如手动结尾或采用更安全 API）。",
                    confidence=min(conf, 0.75),
                    severity=_severity_from_confidence(conf, "buffer_overflow"),
                )
            )
    return issues


# ---------------------------
# 对外主入口
# ---------------------------

# ---------------------------
# 额外规则（新增）
# ---------------------------

def _rule_format_string(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测格式化字符串漏洞：printf/s(n)printf/v(s)printf 首参数不是字符串字面量；
    fprintf 第二个参数不是字符串字面量。
    """
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        # printf/printf-like: 检查第一个参数是否为字面量
        m1 = RE_PRINTF_LIKE.search(s)
        flagged = False
        if m1:
            try:
                start = s.index("(", m1.start())
                j = start + 1
                while j < len(s) and s[j].isspace():
                    j += 1
                if j < len(s) and s[j] != '"':
                    flagged = True
            except ValueError:
                pass
        # fprintf: 检查第二个参数是否为字面量
        m2 = RE_FPRINTF.search(s)
        if not flagged and m2:
            try:
                start = s.index("(", m2.start())
                comma = s.find(",", start + 1)
                if comma != -1:
                    j = comma + 1
                    while j < len(s) and s[j].isspace():
                        j += 1
                    if j < len(s) and s[j] != '"':
                        flagged = True
            except ValueError:
                pass
        if flagged:
            issues.append(
                Issue(
                    language="c/cpp",
                    category="unsafe_usage",
                    pattern="format_string",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(s),
                    description="格式化字符串参数不是字面量，可能导致格式化字符串漏洞。",
                    suggestion="使用常量格式串并对外部输入进行参数化处理；避免将未验证的输入作为格式串。",
                    confidence=0.8,
                    severity="high",
                )
            )
    return issues


def _rule_insecure_tmpfile(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测不安全临时文件API：tmpnam/tempnam/mktemp
    """
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        if RE_INSECURE_TMP.search(s):
            issues.append(
                Issue(
                    language="c/cpp",
                    category="unsafe_usage",
                    pattern="insecure_tmpfile",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(s),
                    description="使用不安全的临时文件API（tmpnam/tempnam/mktemp）可能导致竞态条件与劫持风险。",
                    suggestion="使用 mkstemp/mkdtemp 或安全封装，并设置合适的权限。",
                    confidence=0.85,
                    severity="high",
                )
            )
    return issues


def _rule_command_execution(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测命令执行API：system/popen 和 exec* 系列，其中参数不是字面量（可能引入命令注入风险）
    """
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        flagged = False
        m_sys = RE_SYSTEM_LIKE.search(s)
        if m_sys:
            try:
                start = s.index("(", m_sys.start())
                j = start + 1
                while j < len(s) and s[j].isspace():
                    j += 1
                if j < len(s) and s[j] != '"':
                    flagged = True
            except Exception:
                pass
        if not flagged and RE_EXEC_LIKE.search(s):
            # 对 exec* 系列保守告警：难以可靠判断参数是否安全构造
            flagged = True
        if flagged:
            issues.append(
                Issue(
                    language="c/cpp",
                    category="unsafe_usage",
                    pattern="command_exec",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(s),
                    description="外部命令执行可能使用了非字面量参数，存在命令注入风险。",
                    suggestion="避免拼接命令，使用参数化接口或受控白名单；严格校验/转义外部输入。",
                    confidence=0.7,
                    severity="high",
                )
            )
    return issues


def _rule_scanf_no_width(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测 scanf/sscanf/fscanf 使用 %s 但未指定最大宽度，存在缓冲区溢出风险。
    仅对格式串直接字面量的情况进行粗略检查。
    """
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        m = RE_SCANF_CALL.search(s)
        if not m:
            continue
        fmt = m.group(1)
        # 若包含 "%s" 但未出现 "%<digits>s" 形式，则告警
        if "%s" in fmt and not re.search(r"%\d+s", fmt):
            issues.append(
                Issue(
                    language="c/cpp",
                    category="buffer_overflow",
                    pattern="scanf_%s_no_width",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(s),
                    description="scanf/sscanf/fscanf 使用 %s 但未限制最大宽度，存在缓冲区溢出风险。",
                    suggestion="为 %s 指定最大宽度（如 \"%255s\"），或使用更安全的读取方式。",
                    confidence=0.75,
                    severity="high",
                )
            )
    return issues


def _rule_alloc_size_overflow(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测分配大小可能溢出的简单情形：malloc/calloc/realloc 形参存在乘法表达式且未显式使用 sizeof。
    该规则为启发式，需人工确认。
    """
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        m = re.search(r"\bmalloc\s*\(", s, re.IGNORECASE)
        if not m:
            continue
        try:
            start = s.index("(", m.start())
            end = s.find(")", start + 1)
            if end != -1:
                args = s[start + 1 : end]
                if "*" in args and not re.search(r"\bsizeof\s*\(", args):
                    issues.append(
                        Issue(
                            language="c/cpp",
                            category="memory_mgmt",
                            pattern="alloc_size_overflow",
                            file=relpath,
                            line=idx,
                            evidence=_strip_line(s),
                            description="malloc 大小计算包含乘法且未显式使用 sizeof，存在整数溢出或尺寸计算错误的风险。",
                            suggestion="使用 sizeof 计算元素大小并检查乘法是否可能溢出；引入范围/上界校验。",
                            confidence=0.6,
                            severity="medium",
                        )
                    )
        except Exception:
            pass
    return issues


# ---------------------------
# 空指针/野指针/死锁 等新增规则
# ---------------------------

def _rule_possible_null_deref(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    启发式检测空指针解引用：
    - 出现 p->... 或 *p 访问，且邻近未见明显的 NULL 检查。
    注：可能存在误报，需结合上下文确认。
    """
    issues: List[Issue] = []
    re_arrow = re.compile(r"\b([A-Za-z_]\w*)\s*->")
    re_star = re.compile(r"(?<!\w)\*\s*([A-Za-z_]\w*)\b")
    type_kw = re.compile(r"\b(typedef|struct|union|enum|class|char|int|long|short|void|size_t|ssize_t|FILE)\b")
    for idx, s in enumerate(lines, start=1):
        vars_hit = []
        # '->' 访问几乎必为解引用
        for m in re_arrow.finditer(s):
            vars_hit.append(m.group(1))
        # '*p' 可能是声明，粗略排除类型声明行与函数指针/形参
        if "*" in s and not type_kw.search(s):
            for m in re_star.finditer(s):
                # 排除赋值左侧的声明模式很困难，保守纳入
                vars_hit.append(m.group(1))
        for v in set(vars_hit):
            if not _has_null_check_around(v, lines, idx, radius=3):
                issues.append(
                    Issue(
                        language="c/cpp",
                        category="memory_mgmt",
                        pattern="possible_null_deref",
                        file=relpath,
                        line=idx,
                        evidence=_strip_line(s),
                        description=f"可能对指针 {v} 进行了解引用，但附近未见 NULL 检查，存在空指针解引用风险。",
                        suggestion="在使用指针前执行 NULL 判定；确保所有返回/赋值路径均进行了合法性检查。",
                        confidence=0.6,
                        severity="high",
                    )
                )
    return issues


def _rule_uninitialized_ptr_use(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测野指针（未初始化指针）使用的简单情形：
    - 出现形如 `type *p;`（行内不含 '=' 且不含 '('，避免函数指针）后，在后续若干行内出现 p-> 或 *p 访问，
      且未见 p 的赋值/初始化，则认为可能为野指针解引用。
    """
    issues: List[Issue] = []
    # 收集候选未初始化指针声明
    candidates = []  # (var, decl_line)
    decl_ptr_line = re.compile(r"\*")
    type_prefix = re.compile(r"\b(typedef|struct|union|enum|class|const|volatile|static|register|signed|unsigned|char|int|long|short|void|float|double)\b")
    for idx, s in enumerate(lines, start=1):
        if ";" not in s or "(" in s or "=" in s:
            continue
        if not decl_ptr_line.search(s):
            continue
        if not type_prefix.search(s):
            continue
        # 提取形如 *p, *q
        for m in re.finditer(r"\*\s*([A-Za-z_]\w*)\b", s):
            v = m.group(1)
            candidates.append((v, idx))

    # 检查候选在接下来的窗口中是否在赋值前被解引用
    for v, decl_line in candidates:
        # 向后查看 20 行
        end = min(len(lines), decl_line + 20)
        initialized = False
        deref_line = None
        for j in range(decl_line + 1, end + 1):
            sj = _safe_line(lines, j)
            # 赋值/初始化：p = ..., p = &x, p = malloc(...)
            if re.search(rf"\b{re.escape(v)}\s*=\s*", sj):
                initialized = True
                break
            # 解引用：p-> 或 *p
            if re.search(rf"\b{re.escape(v)}\s*->", sj) or re.search(rf"(?<!\w)\*\s*{re.escape(v)}\b", sj):
                deref_line = j
                # 若命中，若附近没有 NULL 检查/初始化则认为风险较高
                break
        if deref_line and not initialized:
            issues.append(
                Issue(
                    language="c/cpp",
                    category="memory_mgmt",
                    pattern="wild_pointer_deref",
                    file=relpath,
                    line=deref_line,
                    evidence=_strip_line(_safe_line(lines, deref_line)),
                    description=f"指针 {v} 声明后未见初始化即被解引用，可能为野指针使用。",
                    suggestion="在声明后立即将指针初始化为 NULL，并在使用前进行显式赋值与有效性校验。",
                    confidence=0.65,
                    severity="high",
                )
            )
    return issues


def _rule_deadlock_patterns(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测常见死锁风险：
    - 双重加锁：同一互斥量在未解锁情况下再次加锁
    - 可能缺失解锁：加锁后在后续窗口内未看到对应解锁
    - 锁顺序反转：存在 (A->B) 与 (B->A) 两种加锁顺序
    实现基于启发式，可能产生误报。
    """
    issues: List[Issue] = []
    lock_stack: list[str] = []
    # 记录出现过的加锁顺序对及其行号
    order_pairs: dict[tuple[str, str], int] = {}

    # 先行扫描：顺序和双重加锁
    for idx, s in enumerate(lines, start=1):
        m_lock = RE_PTHREAD_LOCK.search(s)
        m_unlock = RE_PTHREAD_UNLOCK.search(s)
        if m_lock:
            mtx = m_lock.group(1)
            # 双重加锁检测
            if mtx in lock_stack:
                issues.append(
                    Issue(
                        language="c/cpp",
                        category="error_handling",
                        pattern="double_lock",
                        file=relpath,
                        line=idx,
                        evidence=_strip_line(s),
                        description=f"互斥量 {mtx} 在未解锁的情况下被再次加锁，存在死锁风险。",
                        suggestion="避免对同一互斥量重复加锁；检查代码路径确保加锁/解锁严格匹配。",
                        confidence=0.8,
                        severity="high",
                    )
                )
            # 锁顺序记录
            if lock_stack and lock_stack[-1] != mtx:
                pair = (lock_stack[-1], mtx)
                order_pairs.setdefault(pair, idx)
            lock_stack.append(mtx)
        elif m_unlock:
            mtx = m_unlock.group(1)
            # 从栈中移除最近的相同锁
            if mtx in lock_stack:
                # 移除最后一次加锁的该互斥量（近似）
                for k in range(len(lock_stack) - 1, -1, -1):
                    if lock_stack[k] == mtx:
                        del lock_stack[k]
                        break
        # 粗略按函数/作用域结束重置
        if "}" in s and not lock_stack:
            lock_stack = []

    # 锁顺序反转检测
    for (a, b), ln in order_pairs.items():
        if (b, a) in order_pairs:
            # 在第二次发现处报一次
            issues.append(
                Issue(
                    language="c/cpp",
                    category="error_handling",
                    pattern="lock_order_inversion",
                    file=relpath,
                    line=order_pairs[(b, a)],
                    evidence=_strip_line(_safe_line(lines, order_pairs[(b, a)])),
                    description=f"检测到互斥量加锁顺序反转：({a} -> {b}) 与 ({b} -> {a})，存在死锁风险。",
                    suggestion="统一多锁的获取顺序，制定全局锁等级或严格的加锁顺序规范。",
                    confidence=0.7,
                    severity="high",
                )
            )

    # 可能缺失解锁：在加锁后的 50 行窗口内未见对应解锁
    for idx, s in enumerate(lines, start=1):
        m_lock = RE_PTHREAD_LOCK.search(s)
        if not m_lock:
            continue
        mtx = m_lock.group(1)
        end = min(len(lines), idx + 50)
        unlocked = False
        for j in range(idx + 1, end + 1):
            if RE_PTHREAD_UNLOCK.search(_safe_line(lines, j)):
                if RE_PTHREAD_UNLOCK.search(_safe_line(lines, j)).group(1) == mtx:
                    unlocked = True
                    break
        if not unlocked:
            issues.append(
                Issue(
                    language="c/cpp",
                    category="error_handling",
                    pattern="missing_unlock_suspect",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(s),
                    description=f"在加锁 {mtx} 之后的邻近窗口内未检测到匹配解锁，可能存在缺失解锁的风险。",
                    suggestion="确保所有加锁路径都有配对的解锁；考虑使用 RAII/DEFER 风格避免遗漏。",
                    confidence=0.55,
                    severity="medium",
                )
            )
    return issues


# ---------------------------
# 其他危险用法规则（新增一批低误报）
# ---------------------------

def _rule_double_free_and_free_non_heap(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测：
    - double_free：同一指针在未重新赋值/置空情况下被重复 free
    - free_non_heap：free(&x) 或 free("literal") 等明显非堆内存释放
    说明：启发式实现，复杂场景可能仍需人工确认。
    """
    issues: List[Issue] = []
    last_free_line: dict[str, int] = {}
    last_assign_line: dict[str, int] = {}

    for idx, s in enumerate(lines, start=1):
        # 记录简单赋值（用于判断 free 之间是否有重新赋值）
        for m in RE_GENERIC_ASSIGN.finditer(s):
            var = m.group(1)
            last_assign_line[var] = idx

        # 处理 free(...) 调用
        for m in RE_FREE_CALL_ANY.finditer(s):
            arg = m.group(1).strip()

            # 忽略 free(NULL)/free(0)
            if re.fullmatch(r"\(?\s*(NULL|0|\(void\s*\*\)\s*0)\s*\)?", arg, re.IGNORECASE):
                continue

            # 明显非堆：&... 或 字符串字面量
            if re.match(r"^\(?\s*&", arg) or arg.lstrip().startswith('"'):
                issues.append(
                    Issue(
                        language="c/cpp",
                        category="memory_mgmt",
                        pattern="free_non_heap",
                        file=relpath,
                        line=idx,
                        evidence=_strip_line(s),
                        description="检测到对非堆内存的释放（如 &var 或字符串字面量），属于未定义行为。",
                        suggestion="仅释放由 malloc/calloc/realloc/new/new[] 获得的堆内存；避免对栈地址/字面量调用 free。",
                        confidence=0.85,
                        severity="high",
                    )
                )
                continue

            # double_free：仅在参数为单一标识符时检测
            if re.fullmatch(r"[A-Za-z_]\w*", arg):
                var = arg
                prev = last_free_line.get(var)
                if prev is not None:
                    assign_after_prev = last_assign_line.get(var, -1)
                    if assign_after_prev < prev:
                        # 在上次 free 之后没有重新赋值/置空即再次 free，认为 double_free 风险高
                        issues.append(
                            Issue(
                                language="c/cpp",
                                category="memory_mgmt",
                                pattern="double_free",
                                file=relpath,
                                line=idx,
                                evidence=_strip_line(s),
                                description=f"指针 {var} 可能在未重新赋值/置空情况下被重复释放（double free）。",
                                suggestion="free 后将指针置 NULL；确保每块内存仅释放一次；理清所有权与释放路径。",
                                confidence=0.8,
                                severity="high",
                            )
                        )
                last_free_line[var] = idx
    return issues


def _rule_atoi_family(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测 atoi/atol/atoll/atof 的使用（缺乏错误与范围检查，易产生解析歧义）。
    建议改用 strtol/strtoul/strtod 并检查 errno/端点指针。
    """
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        if RE_ATOI_FAMILY.search(s):
            issues.append(
                Issue(
                    language="c/cpp",
                    category="input_validation",
                    pattern="atoi_family",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(s),
                    description="使用 atoi/atol/atoll/atof 缺乏错误与范围检查，容易产生解析错误或未定义行为。",
                    suggestion="使用 strtol/strtoul/strtod 等并检查 errno 和 endptr；进行范围与格式校验。",
                    confidence=0.65,
                    severity="medium",
                )
            )
    return issues


def _rule_rand_insecure(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测 rand/srand 的使用。若上下文包含安全敏感关键词，提升风险。
    """
    issues: List[Issue] = []
    keywords = ("token", "nonce", "secret", "password", "passwd", "key", "auth", "salt", "session", "otp")
    for idx, s in enumerate(lines, start=1):
        if RE_RAND.search(s):
            conf = 0.55
            window_text = " ".join(t for _, t in _window(lines, idx, before=1, after=1)).lower()
            if any(k in window_text for k in keywords):
                conf += 0.2
            issues.append(
                Issue(
                    language="c/cpp",
                    category="crypto",
                    pattern="rand_insecure",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(s),
                    description="检测到 rand/srand，用于安全敏感场景可能不安全，易被预测。",
                    suggestion="使用系统级 CSPRNG（如 getrandom/arc4random/openssl RAND_bytes），避免用于密钥/令牌生成。",
                    confidence=min(conf, 0.8),
                    severity="high" if conf >= 0.7 else "medium",
                )
            )
    return issues


def _rule_strtok_nonreentrant(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测 strtok 非重入/线程不安全使用。
    """
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        if RE_STRTOK.search(s):
            issues.append(
                Issue(
                    language="c/cpp",
                    category="thread_safety",
                    pattern="strtok_nonreentrant",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(s),
                    description="使用 strtok 非重入且线程不安全，可能导致竞态或数据覆盖。",
                    suggestion="使用 strtok_r（POSIX）或可重入/线程安全的分割方案。",
                    confidence=0.6,
                    severity="medium",
                )
            )
    return issues


def _rule_open_permissive_perms(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测过宽文件权限：
    - open(..., O_CREAT, 0666/0777/...) 直接授予过宽权限
    - fopen(..., "w"/"w+") 在安全敏感上下文可提示收紧权限（基于关键词启发）
    """
    issues: List[Issue] = []
    sensitive_keys = ("key", "secret", "token", "passwd", "password", "cred", "config", "cert", "private", "id_rsa")
    for idx, s in enumerate(lines, start=1):
        m = RE_OPEN_PERMISSIVE.search(s)
        if m:
            mode = m.group(1)
            issues.append(
                Issue(
                    language="c/cpp",
                    category="insecure_permissions",
                    pattern="open_permissive_perms",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(s),
                    description=f"open 使用 O_CREAT 且权限 {mode} 过宽，存在敏感信息泄露风险。",
                    suggestion="显式使用更严格的权限（如 0600/0640），或设置合适 umask 后再创建文件。",
                    confidence=0.8,
                    severity="high",
                )
            )
        # fopen 模式为写入且上下文敏感时，进行提醒
        m2 = RE_FOPEN_MODE.search(s)
        if m2:
            mode = m2.group(1)
            if "w" in mode:
                window = " ".join(t for _, t in _window(lines, idx, before=1, after=1)).lower()
                if any(k in window for k in sensitive_keys):
                    issues.append(
                        Issue(
                            language="c/cpp",
                            category="insecure_permissions",
                            pattern="fopen_write_sensitive",
                            file=relpath,
                            line=idx,
                            evidence=_strip_line(s),
                            description="fopen 以写入模式操作可能的敏感文件，需确认创建权限与 umask 设置是否足够严格。",
                            suggestion="确认运行态 umask；必要时使用 open+fchmod/umask 控制权限，或以 0600 创建后再放宽。",
                            confidence=0.55,
                            severity="medium",
                        )
                    )
    return issues


# ---------------------------
# 更多危险用法规则（第二批）
# ---------------------------

def _rule_alloca_unbounded(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测 alloca 使用非常量/未受控大小，可能导致栈耗尽或崩溃。
    仅在参数非纯数字常量、且不含 sizeof 时告警。
    """
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        m = RE_ALLOCA.search(s)
        if not m:
            continue
        arg = m.group(1).strip()
        # 纯数字常量或包含 sizeof 视为更安全
        if re.fullmatch(r"\d+\s*", arg) or "sizeof" in arg:
            continue
        conf = 0.6
        if re.search(r"(len|size|count|n)\b", arg, re.IGNORECASE):
            conf += 0.1
        issues.append(
            Issue(
                language="c/cpp",
                category="memory_mgmt",
                pattern="alloca_unbounded",
                file=relpath,
                line=idx,
                evidence=_strip_line(s),
                description="alloca 使用的大小不是编译期常量，可能导致未受控的栈分配与崩溃风险。",
                suggestion="避免使用 alloca；改用堆分配并对大小做上界检查与错误处理。",
                confidence=min(conf, 0.8),
                severity="high" if conf >= 0.7 else "medium",
            )
        )
    return issues


def _rule_vla_usage(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测可变长度数组（VLA）使用：声明中使用变量/表达式作为数组长度。
    仅在长度非纯数字常量时提示。
    """
    issues: List[Issue] = []
    type_prefix = re.compile(r"\b(typedef|struct|union|enum|class|const|volatile|static|register|signed|unsigned|char|int|long|short|void|float|double|size_t|ssize_t)\b")
    for idx, s in enumerate(lines, start=1):
        if ";" not in s or "=" in s:
            continue
        if not type_prefix.search(s):
            continue
        m = RE_VLA_DECL.search(s)
        if not m:
            continue
        length_expr = m.group(1).strip()
        if re.fullmatch(r"\d+\s*", length_expr):
            continue
        issues.append(
            Issue(
                language="c/cpp",
                category="memory_mgmt",
                pattern="vla_usage",
                file=relpath,
                line=idx,
                evidence=_strip_line(s),
                description="检测到可变长度数组（VLA），在栈上进行不定大小分配，可能导致栈溢出/不可控内存使用。",
                suggestion="避免 VLA；改用堆分配并进行上界校验，或使用固定上界的静态分配。",
                confidence=0.6,
                severity="medium",
            )
        )
    return issues


def _rule_pthread_returns_unchecked(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测 pthread 常见接口的返回值未检查的情形（同/后一两行缺少 if/比较判断）。
    """
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        if not RE_PTHREAD_RET.search(s):
            continue
        nearby = " ".join(_safe_line(lines, i) for i in range(idx, min(idx + 2, len(lines)) + 1))
        if not re.search(r"\bif\s*\(|>=|<=|==|!=|<|>", nearby):
            issues.append(
                Issue(
                    language="c/cpp",
                    category="error_handling",
                    pattern="pthread_ret_unchecked",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(s),
                    description="pthread 接口返回值可能未检查，错误处理缺失可能导致死锁/资源泄漏。",
                    suggestion="检查 pthread 接口返回码并进行错误路径处理；必要时记录日志与清理资源。",
                    confidence=0.6,
                    severity="medium",
                )
            )
    return issues


def _rule_cond_wait_no_loop(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测 pthread_cond_wait 未在 while 循环中使用（防止虚假唤醒）。
    """
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        if not RE_PTHREAD_COND_WAIT.search(s):
            continue
        # 回看 2 行内是否有 while( ... )
        prev_text = " ".join(_safe_line(lines, j) for j in range(max(1, idx - 2), idx))
        if not re.search(r"\bwhile\s*\(", prev_text):
            issues.append(
                Issue(
                    language="c/cpp",
                    category="thread_safety",
                    pattern="cond_wait_no_loop",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(s),
                    description="pthread_cond_wait 建议置于条件谓词的 while 循环中，以防止虚假唤醒。",
                    suggestion="使用 while(predicate_not_satisfied) 包裹 pthread_cond_wait 调用并在唤醒后重新检查条件。",
                    confidence=0.6,
                    severity="medium",
                )
            )
    return issues


def _rule_thread_leak_no_join(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测创建线程后未 join/detach 的可能线程泄漏。
    """
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        m = RE_PTHREAD_CREATE.search(s)
        if not m:
            continue
        tid = m.group(1)
        end = min(len(lines), idx + 80)
        joined_or_detached = False
        for j in range(idx + 1, end + 1):
            sj = _safe_line(lines, j)
            if RE_PTHREAD_JOIN.search(sj) and RE_PTHREAD_JOIN.search(sj).group(1) == tid:
                joined_or_detached = True
                break
            if RE_PTHREAD_DETACH.search(sj) and RE_PTHREAD_DETACH.search(sj).group(1) == tid:
                joined_or_detached = True
                break
        if not joined_or_detached:
            issues.append(
                Issue(
                    language="c/cpp",
                    category="resource_leak",
                    pattern="thread_leak_no_join",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(s),
                    description=f"pthread_create 创建线程 {tid} 后的邻近窗口内未检测到 join/detach，可能导致线程泄漏或资源占用。",
                    suggestion="确保创建的线程被显式 join 或 detach；遵循统一的线程生命周期管理策略。",
                    confidence=0.6,
                    severity="medium",
                )
            )
    return issues


def _rule_inet_legacy(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测 inet_addr/inet_aton 等旧接口的使用。
    """
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        if RE_INET_LEGACY.search(s):
            issues.append(
                Issue(
                    language="c/cpp",
                    category="network_api",
                    pattern="inet_legacy",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(s),
                    description="使用 inet_addr/inet_aton 等旧接口，错误语义模糊/不一致。",
                    suggestion="使用 inet_pton/inet_ntop 进行地址转换，错误处理更可靠且支持 IPv6。",
                    confidence=0.6,
                    severity="low",
                )
            )
    return issues


def _rule_time_apis_not_threadsafe(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测 asctime/ctime/localtime/gmtime 非线程安全接口（非 *_r）。
    """
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        # 排除 *_r 版本
        if RE_TIME_UNSAFE.search(s) and not re.search(r"_r\s*\(", s):
            issues.append(
                Issue(
                    language="c/cpp",
                    category="thread_safety",
                    pattern="time_api_not_threadsafe",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(s),
                    description="使用 asctime/ctime/localtime/gmtime 等非重入接口，线程安全性不足。",
                    suggestion="改用 *_r 线程安全版本（如 localtime_r/gmtime_r/ctime_r）。",
                    confidence=0.6,
                    severity="medium",
                )
            )
    return issues


def _rule_getenv_unchecked(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测 getenv 使用（环境变量未校验可能导致配置/路径/命令注入风险）。
    """
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        if RE_GETENV.search(s):
            issues.append(
                Issue(
                    language="c/cpp",
                    category="input_validation",
                    pattern="getenv_unchecked",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(s),
                    description="读取环境变量后未见显式校验，可能被用于构造路径/命令等引入安全风险。",
                    suggestion="对白名单键进行读取；对取值执行格式/长度/字符集校验；避免直接拼接为命令/路径。",
                    confidence=0.55,
                    severity="medium",
                )
            )
    return issues


def analyze_c_cpp_text(relpath: str, text: str) -> List[Issue]:
    """
    基于提供的文本进行 C/C++ 启发式分析。
    """
    lines = text.splitlines()
    issues: List[Issue] = []
    issues.extend(_rule_unsafe_api(lines, relpath))
    issues.extend(_rule_boundary_funcs(lines, relpath))
    issues.extend(_rule_realloc_assign_back(lines, relpath))
    issues.extend(_rule_malloc_no_null_check(lines, relpath))
    issues.extend(_rule_uaf_suspect(lines, relpath))
    issues.extend(_rule_unchecked_io(lines, relpath))
    issues.extend(_rule_strncpy_no_nullterm(lines, relpath))
    # 新增规则
    issues.extend(_rule_format_string(lines, relpath))
    issues.extend(_rule_insecure_tmpfile(lines, relpath))
    issues.extend(_rule_command_execution(lines, relpath))
    issues.extend(_rule_scanf_no_width(lines, relpath))
    issues.extend(_rule_alloc_size_overflow(lines, relpath))
    # 新增：其他危险用法（低误报优先）
    issues.extend(_rule_double_free_and_free_non_heap(lines, relpath))
    issues.extend(_rule_atoi_family(lines, relpath))
    issues.extend(_rule_rand_insecure(lines, relpath))
    issues.extend(_rule_strtok_nonreentrant(lines, relpath))
    issues.extend(_rule_open_permissive_perms(lines, relpath))
    # 更多危险用法（第二批）
    issues.extend(_rule_alloca_unbounded(lines, relpath))
    issues.extend(_rule_vla_usage(lines, relpath))
    issues.extend(_rule_pthread_returns_unchecked(lines, relpath))
    issues.extend(_rule_cond_wait_no_loop(lines, relpath))
    issues.extend(_rule_thread_leak_no_join(lines, relpath))
    issues.extend(_rule_inet_legacy(lines, relpath))
    issues.extend(_rule_time_apis_not_threadsafe(lines, relpath))
    issues.extend(_rule_getenv_unchecked(lines, relpath))
    # 新增：空指针/野指针/死锁检测
    issues.extend(_rule_possible_null_deref(lines, relpath))
    issues.extend(_rule_uninitialized_ptr_use(lines, relpath))
    issues.extend(_rule_deadlock_patterns(lines, relpath))
    return issues


def analyze_c_cpp_file(base: Path, relpath: Path) -> List[Issue]:
    """
    从磁盘读取文件进行分析。
    """
    try:
        text = (base / relpath).read_text(errors="ignore")
    except Exception:
        return []
    return analyze_c_cpp_text(str(relpath), text)


def analyze_files(base_path: str, files: Iterable[str]) -> List[Issue]:
    """
    批量分析文件，相对路径相对于 base_path。
    """
    base = Path(base_path).resolve()
    out: List[Issue] = []
    for f in files:
        rel = Path(f)
        out.extend(analyze_c_cpp_file(base, rel))
    return out