# -*- coding: utf-8 -*-
"""
Jarvis 安全分析套件 —— C/C++ 启发式安全检查器

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
from typing import Any
from typing import Iterable
from typing import List
from typing import Optional
from typing import Sequence
from typing import Tuple

from jarvis.jarvis_sec.types import Issue

# ---------------------------
# 规则库（正则表达式）
# ---------------------------

RE_UNSAFE_API = re.compile(
    r"\b(strcpy|strcat|gets|sprintf|vsprintf)\s*\(",
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
RE_PRINTF_LIKE = re.compile(
    r"\b(printf|sprintf|snprintf|vsprintf|vsnprintf)\s*\(", re.IGNORECASE
)
RE_FPRINTF = re.compile(r"\bfprintf\s*\(", re.IGNORECASE)
RE_INSECURE_TMP = re.compile(r"\b(tmpnam|tempnam|mktemp)\s*\(", re.IGNORECASE)
RE_SYSTEM_LIKE = re.compile(r"\b(system|popen)\s*\(", re.IGNORECASE)
RE_EXEC_LIKE = re.compile(
    r"\b(execvp|execlp|execvpe|execl|execve|execv)\s*\(", re.IGNORECASE
)
RE_SCANF_CALL = re.compile(r'\b(?:[fs]?scanf)\s*\(\s*"([^"]*)"', re.IGNORECASE)
# 线程/锁相关
RE_PTHREAD_LOCK = re.compile(
    r"\bpthread_mutex_lock\s*\(\s*&\s*([A-Za-z_]\w*)\s*\)\s*;?", re.IGNORECASE
)
RE_PTHREAD_UNLOCK = re.compile(
    r"\bpthread_mutex_unlock\s*\(\s*&\s*([A-Za-z_]\w*)\s*\)\s*;?", re.IGNORECASE
)
# 其他危险用法相关
RE_ATOI_FAMILY = re.compile(r"\b(atoi|atol|atoll|atof)\s*\(", re.IGNORECASE)
RE_RAND = re.compile(r"\b(rand|srand)\s*\(", re.IGNORECASE)
RE_STRTOK = re.compile(r"\bstrtok\s*\(", re.IGNORECASE)
RE_OPEN_PERMISSIVE = re.compile(
    r"\bopen\s*\(\s*[^,]+,\s*[^,]*O_CREAT[^,]*,\s*(0[0-7]{3,4})\s*\)", re.IGNORECASE
)
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
RE_PTHREAD_CREATE = re.compile(
    r"\bpthread_create\s*\(\s*&\s*([A-Za-z_]\w*)\s*,", re.IGNORECASE
)
RE_PTHREAD_JOIN = re.compile(r"\bpthread_join\s*\(\s*([A-Za-z_]\w*)\s*,", re.IGNORECASE)
RE_PTHREAD_DETACH = re.compile(
    r"\bpthread_detach\s*\(\s*([A-Za-z_]\w*)\s*\)", re.IGNORECASE
)
# C++ 标准库锁相关
RE_STD_MUTEX = re.compile(r"\b(?:std::)?mutex\s+([A-Za-z_]\w*)", re.IGNORECASE)
RE_MUTEX_LOCK = re.compile(r"\b([A-Za-z_]\w*)\s*\.lock\s*\(", re.IGNORECASE)
RE_MUTEX_UNLOCK = re.compile(r"\b([A-Za-z_]\w*)\s*\.unlock\s*\(", re.IGNORECASE)
RE_MUTEX_TRY_LOCK = re.compile(r"\b([A-Za-z_]\w*)\s*\.try_lock\s*\(", re.IGNORECASE)
RE_LOCK_GUARD = re.compile(
    r"\b(?:std::)?lock_guard\s*<[^>]+>\s*([A-Za-z_]\w*)", re.IGNORECASE
)
RE_UNIQUE_LOCK = re.compile(
    r"\b(?:std::)?unique_lock\s*<[^>]+>\s*([A-Za-z_]\w*)", re.IGNORECASE
)
RE_SHARED_LOCK = re.compile(
    r"\b(?:std::)?shared_lock\s*<[^>]+>\s*([A-Za-z_]\w*)", re.IGNORECASE
)
RE_STD_LOCK = re.compile(r"\bstd::lock\s*\(", re.IGNORECASE)
RE_SCOPED_LOCK = re.compile(r"\b(?:std::)?scoped_lock\s*<", re.IGNORECASE)
# 数据竞争检测相关
RE_STATIC_VAR = re.compile(
    r"\bstatic\s+(?:const\s+|volatile\s+)?[A-Za-z_]\w*(?:\s+\*|\s+)+([A-Za-z_]\w*)",
    re.IGNORECASE,
)
RE_EXTERN_VAR = re.compile(
    r"\bextern\s+[A-Za-z_]\w*(?:\s+\*|\s+)+([A-Za-z_]\w*)", re.IGNORECASE
)
RE_STD_THREAD = re.compile(r"\b(?:std::)?thread\s+([A-Za-z_]\w*)", re.IGNORECASE)
RE_ATOMIC = re.compile(r"\b(?:std::)?atomic\s*<[^>]+>\s*([A-Za-z_]\w*)", re.IGNORECASE)
RE_VOLATILE = re.compile(
    r"\bvolatile\s+[A-Za-z_]\w*(?:\s+\*|\s+)+([A-Za-z_]\w*)", re.IGNORECASE
)
RE_VAR_ACCESS = re.compile(r"\b([A-Za-z_]\w*)\s*(?:=|\[|->|\.)", re.IGNORECASE)
RE_VAR_ASSIGN = re.compile(r"\b([A-Za-z_]\w*)\s*=", re.IGNORECASE)
RE_INET_LEGACY = re.compile(r"\b(inet_addr|inet_aton)\s*\(", re.IGNORECASE)
RE_TIME_UNSAFE = re.compile(r"\b(asctime|ctime|localtime|gmtime)\s*\(", re.IGNORECASE)
RE_GETENV = re.compile(r'\bgetenv\s*\(\s*"[^"]*"\s*\)', re.IGNORECASE)

# 辅助正则
RE_REALLOC_ASSIGN_BACK = re.compile(
    r"\b([A-Za-z_]\w*)\s*=\s*realloc\s*\(\s*\1\s*,", re.IGNORECASE
)
RE_MALLOC_ASSIGN = re.compile(r"\b([A-Za-z_]\w*)\s*=\s*malloc\s*\(", re.IGNORECASE)
RE_CALLOC_ASSIGN = re.compile(r"\b([A-Za-z_]\w*)\s*=\s*calloc\s*\(", re.IGNORECASE)
RE_NEW_ASSIGN = re.compile(r"\b([A-Za-z_]\w*)\s*=\s*new\b", re.IGNORECASE)
RE_DEREF = re.compile(r"(\*|->)\s*[A-Za-z_]\w*|\b[A-Za-z_]\w*\s*\[", re.IGNORECASE)
RE_NULL_CHECK = re.compile(
    r"\bif\s*\(\s*(!\s*)?[A-Za-z_]\w*\s*(==|!=)\s*NULL\s*\)|\bif\s*\(\s*[A-Za-z_]\w*\s*\)",
    re.IGNORECASE,
)
RE_FREE_VAR = re.compile(r"free\s*\(\s*([A-Za-z_]\w*)\s*\)\s*;", re.IGNORECASE)
RE_USE_VAR = re.compile(r"\b([A-Za-z_]\w*)\b")
RE_STRLEN_IN_SIZE = re.compile(r"\bstrlen\s*\(", re.IGNORECASE)
RE_SIZEOF_PTR = re.compile(r"\bsizeof\s*\(\s*\*\s*[A-Za-z_]\w*\s*\)", re.IGNORECASE)
RE_STRNCPY = re.compile(r"\bstrncpy\s*\(", re.IGNORECASE)
RE_STRNCAT = re.compile(r"\bstrncat\s*\(", re.IGNORECASE)

# C++ 特定模式
RE_SHARED_PTR = re.compile(r"\b(?:std::)?shared_ptr\s*<", re.IGNORECASE)
RE_UNIQUE_PTR = re.compile(r"\b(?:std::)?unique_ptr\s*<", re.IGNORECASE)
RE_WEAK_PTR = re.compile(r"\b(?:std::)?weak_ptr\s*<", re.IGNORECASE)
RE_SMART_PTR_ASSIGN = re.compile(
    r"\b([A-Za-z_]\w*)\s*=\s*(?:std::)?(?:shared_ptr|unique_ptr|weak_ptr)\s*<",
    re.IGNORECASE,
)
RE_NEW_ARRAY = re.compile(r"\bnew\s+[A-Za-z_]\w*\s*\[", re.IGNORECASE)
RE_DELETE_ARRAY = re.compile(r"\bdelete\s*\[\s*\]", re.IGNORECASE)
RE_DELETE = re.compile(r"\bdelete\s+(?!\[)", re.IGNORECASE)
RE_STATIC_CAST = re.compile(r"\bstatic_cast\s*<", re.IGNORECASE)
RE_DYNAMIC_CAST = re.compile(r"\bdynamic_cast\s*<", re.IGNORECASE)
RE_REINTERPRET_CAST = re.compile(r"\breinterpret_cast\s*<", re.IGNORECASE)
RE_CONST_CAST = re.compile(r"\bconst_cast\s*<", re.IGNORECASE)
RE_VECTOR_ACCESS = re.compile(
    r"\b(?:std::)?vector\s*<[^>]+>\s*[A-Za-z_]\w*\s*\[", re.IGNORECASE
)
RE_STRING_ACCESS = re.compile(
    r"\b(?:std::)?(?:string|wstring)\s*[A-Za-z_]\w*\s*\[", re.IGNORECASE
)
RE_VECTOR_VAR = re.compile(
    r"\b(?:std::)?vector\s*<[^>]+>\s*([A-Za-z_]\w*)", re.IGNORECASE
)
RE_STRING_VAR = re.compile(
    r"\b(?:std::)?(?:string|wstring)\s+([A-Za-z_]\w*)", re.IGNORECASE
)
RE_AT_METHOD = re.compile(r"\.at\s*\(", re.IGNORECASE)
RE_VIRTUAL_DTOR = re.compile(r"\bvirtual\s+~[A-Za-z_]\w*\s*\(", re.IGNORECASE)
RE_CLASS_DECL = re.compile(r"\bclass\s+([A-Za-z_]\w*)", re.IGNORECASE)
RE_DTOR_DECL = re.compile(r"~\s*([A-Za-z_]\w*)\s*\(", re.IGNORECASE)
RE_MOVE = re.compile(r"\bstd::move\s*\(", re.IGNORECASE)
RE_MOVE_ASSIGN = re.compile(r"\b([A-Za-z_]\w*)\s*=\s*std::move\s*\(", re.IGNORECASE)
RE_THROW = re.compile(r"\bthrow\s+", re.IGNORECASE)
RE_TRY = re.compile(r"\btry\s*\{", re.IGNORECASE)
RE_CATCH = re.compile(r"\bcatch\s*\(", re.IGNORECASE)
RE_NOEXCEPT = re.compile(r"\bnoexcept\s*(?:\([^)]*\))?", re.IGNORECASE)


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
    移除 C/C++ 源码中的注释（// 与 /* */），保留字符串与字符字面量内容；
    为了保持行号与窗口定位稳定，注释内容会被空格替换并保留换行符。
    说明：本函数为启发式实现，旨在降低“注释中的API命中”造成的误报。
    """
    res: list[str] = []
    i = 0
    n = len(text)
    in_sl_comment = False  # //
    in_bl_comment = False  # /* */
    in_string = False  # "
    in_char = False  # '
    escape = False

    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""

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
        if ch == "/" and nxt == "/":
            in_sl_comment = True
            # 保留两个占位，避免拼接
            res.append(" ")
            res.append(" ")
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_bl_comment = True
            res.append(" ")
            res.append(" ")
            i += 2
            continue

        # 进入字符串/字符字面量
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
    用于在扫描通用 API 模式时避免误将字符串中的片段（如 "system("）当作代码。
    注意：此函数不移除注释，请在已移除注释的文本上调用。
    """
    res: list[str] = []
    in_string = False
    in_char = False
    escape = False
    for ch in text:
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
            continue
        if ch == '"':
            in_string = True
            res.append('"')
            continue
        if ch == "'":
            in_char = True
            res.append("'")
            continue
        res.append(ch)
    return "".join(res)


def _strip_if0_blocks(text: str) -> str:
    """
    预处理常见的 #if 0 … #else … #endif 结构：
    - 跳过 #if 0 的主体；若存在 #else，则保留 #else 分支
    - 保留行数与换行，确保行号稳定
    限制：仅识别常量 0 的条件，不对复杂表达式求值；#elif 未处理
    """
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    stack: list[
        dict[str, Any]
    ] = []  # 每帧：{"kind": "if0"|"if", "skipping": bool, "in_else": bool}

    def any_skipping() -> bool:
        return any(frame.get("skipping", False) for frame in stack)

    for line in lines:
        if re.match(r"^\s*#\s*if\s+0\b", line):
            # 进入 #if 0：主体跳过
            stack.append({"kind": "if0", "skipping": True, "in_else": False})
            out.append("\n" if line.endswith("\n") else "")
            continue
        if re.match(r"^\s*#\s*if\b", line):
            # 其他 #if：不求值，仅记录，继承外层 skipping
            stack.append({"kind": "if", "skipping": any_skipping(), "in_else": False})
            out.append(
                line if not any_skipping() else ("\n" if line.endswith("\n") else "")
            )
            continue
        if re.match(r"^\s*#\s*else\b", line):
            if stack:
                top = stack[-1]
                if top["kind"] == "if0":
                    # #if 0 的 else：翻转 skipping，使 else 分支有效
                    top["skipping"] = not top["skipping"]
                    top["in_else"] = True
            out.append(
                line if not any_skipping() else ("\n" if line.endswith("\n") else "")
            )
            continue
        if re.match(r"^\s*#\s*endif\b", line):
            if stack:
                stack.pop()
            out.append(
                line if not any_skipping() else ("\n" if line.endswith("\n") else "")
            )
            continue
        # 常规代码
        if any_skipping():
            out.append("\n" if line.endswith("\n") else "")
        else:
            out.append(line)
    return "".join(out)


def _has_null_check_around(
    var: str, lines: Sequence[str], line_no: int, radius: int = 5
) -> bool:
    """
    扩展空指针检查识别能力，减少误报：
    - if (ptr) / if (!ptr)
    - if (ptr == NULL/0) / if (NULL/0 == ptr)
    - 断言/检查宏：assert(ptr)、assert(ptr != NULL)、BUG_ON(!ptr)、WARN_ON(!ptr)、CHECK/ENSURE 等
    """
    for i, s in _window(lines, line_no, before=radius, after=radius):
        # 直接真假判断
        if re.search(rf"\bif\s*\(\s*{re.escape(var)}\s*\)", s):
            return True
        if re.search(rf"\bif\s*\(\s*!\s*{re.escape(var)}\s*\)", s):
            return True
        # 显式与 NULL/0 比较（任意顺序）
        if re.search(rf"\bif\s*\(\s*{re.escape(var)}\s*(==|!=)\s*(NULL|0)\s*\)", s):
            return True
        if re.search(rf"\bif\s*\(\s*(NULL|0)\s*(==|!=)\s*{re.escape(var)}\s*\)", s):
            return True
        # 断言/检查宏（常见宏名）：assert/BUG_ON/WARN_ON/CHECK/ENSURE
        if re.search(
            rf"\b(assert|BUG_ON|WARN_ON|CHECK|ENSURE)\s*\(\s*(!\s*)?{re.escape(var)}(\s*(==|!=)\s*(NULL|0))?\s*\)",
            s,
        ):
            return True
    return False


def _has_len_bound_around(lines: Sequence[str], line_no: int, radius: int = 3) -> bool:
    for _, s in _window(lines, line_no, before=radius, after=radius):
        # 检测是否出现长度上界/检查（非常粗略）
        if any(
            k in s
            for k in [
                "sizeof(",
                "BUFFER_SIZE",
                "MAX_",
                "min(",
                "clamp(",
                "snprintf",
                "strlcpy",
                "strlcat",
            ]
        ):
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
    is_header = str(relpath).lower().endswith((".h", ".hpp"))
    re_type_kw = re.compile(
        r"\b(static|inline|const|volatile|unsigned|signed|long|short|int|char|void|size_t|ssize_t)\b"
    )
    for idx, s in enumerate(lines, start=1):
        # 跳过预处理行与声明行，减少原型/宏中的误报
        t = s.lstrip()
        if t.startswith("#") or re.search(r"\b(typedef|extern)\b", s):
            continue
        m = RE_UNSAFE_API.search(s)
        if not m:
            continue
        # 若在头文件中，且形如“返回类型 + 函数原型”的声明行（以 ); 结尾），跳过，避免将原型误报为调用
        if is_header:
            before = s[: m.start()]
            if re_type_kw.search(before) and s.strip().endswith(");"):
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
        # 跳过预处理行与声明行，避免在 typedef/extern 原型中误报
        t = s.lstrip()
        if t.startswith("#") or re.search(r"\b(typedef|extern)\b", s):
            continue
        m = RE_BOUNDARY_FUNCS.search(s)
        if not m:
            continue
        api = m.group(1)
        conf = 0.65
        # 提取调用参数（启发式，便于准确性优化）
        args = ""
        try:
            start = s.index("(", m.start())
            end = s.rfind(")")
            if end != -1 and end > start:
                args = s[start + 1 : end]
        except Exception:
            args = ""

        # 若为 memcpy/memmove 且第三参明显使用 sizeof(...)（且非 sizeof(*ptr)）且未混入 strlen，
        # 通常为更安全的写法：降低误报（直接跳过告警）
        safe_sizeof = False
        if api.lower() in ("memcpy", "memmove") and args:
            if (
                "sizeof" in args
                and not RE_SIZEOF_PTR.search(args)
                and not RE_STRLEN_IN_SIZE.search(args)
            ):
                safe_sizeof = True
        if safe_sizeof:
            # 跳过该条，以提高准确性（避免将安全写法误报为风险）
            continue

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


def _rule_function_return_ptr_no_check(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测函数返回指针后未检查 NULL 就直接使用的情况。
    启发式：检测形如 "type *var = func(...);" 后直接使用 var 而未检查 NULL。
    """
    issues: List[Issue] = []
    # 匹配指针赋值：type *var = func(...); 或 type* var = func(...);
    # 支持 int *arr = allocate_array(a); 和 int* arr = allocate_array(a); 两种写法
    # 匹配模式：类型 * 变量名 = 函数名( 或 类型* 变量名 = 函数名(
    re_ptr_assign = re.compile(
        r"\b[A-Za-z_]\w+\s*\*\s*([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)\s*\(",
        re.IGNORECASE,
    )
    
    for idx, s in enumerate(lines, start=1):
        # 跳过类型声明行和预处理指令
        t = s.lstrip()
        if t.startswith("#") or re.search(r"\b(typedef|extern)\b", s):
            continue
        
        # 检测指针赋值：匹配 "type *var = func(" 或 "type* var = func("
        var_name = None
        func_name = None
        
        # 匹配 type *var = func(...) 或 type* var = func(...)
        m = re_ptr_assign.search(s)
        if m:
            var_name = m.group(1)  # 变量名
            func_name = m.group(2)  # 函数名
        
        if not var_name:
            continue
        
        # 检查后续几行是否有 NULL 检查
        has_check = _has_null_check_around(var_name, lines, idx, radius=4)
        
        # 检查后续几行是否直接使用了该变量（解引用或数组访问）
        used_without_check = False
        for j, sj in _window(lines, idx, before=0, after=6):
            if j == idx:
                continue
            # 检测解引用使用：var->, *var, var[...]
            if re.search(
                rf"\b{re.escape(var_name)}\s*(->|\[|\(|\s*\*)",
                sj,
            ):
                used_without_check = True
                break
        
        if used_without_check and not has_check:
            # 检查函数名是否可能是分配函数（提高置信度）
            conf = 0.5
            alloc_keywords = ("alloc", "malloc", "calloc", "realloc", "new", "create", "init")
            if any(kw in func_name.lower() for kw in alloc_keywords):
                conf += 0.2
            
            issues.append(
                Issue(
                    language="c/cpp",
                    category="memory_mgmt",
                    pattern="function_return_ptr_no_check",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(s),
                    description=f"函数 {func_name} 返回的指针赋值给 {var_name} 后，在使用前可能未检查 NULL，存在空指针解引用风险。",
                    suggestion="在使用函数返回的指针前检查是否为 NULL；确保所有可能的返回路径都进行了验证。",
                    confidence=min(conf, 0.85),
                    severity="high" if conf >= 0.7 else "medium",
                )
            )
    
    return issues


def _rule_uaf_suspect(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    启发式 UAF（use-after-free）线索检测（准确性优化版）：
    - 仅在 free(var) 之后的窗口内检测到明显“解引用使用”（v->、*v、v[...）而且在此之前未见重新赋值/置空时告警
    - 忽略 free 后立即将指针置为 NULL/0 的情况
    说明：仍为启发式，需要结合上下文确认。
    """
    issues: List[Issue] = []
    # 收集所有 free(var) 位置
    free_calls: List[Tuple[str, int]] = []
    for idx, s in enumerate(lines, start=1):
        for m in re.finditer(r"free\s*\(\s*([A-Za-z_]\w*)\s*\)\s*;", s):
            free_calls.append((m.group(1), idx))

    # 针对每个 free(var)，在后续窗口中寻找“危险使用”
    for var, free_ln in free_calls:
        # free 后 50 行窗口
        start = free_ln + 1
        end = min(len(lines), free_ln + 50)

        # 同/邻近行若有置空，先快速跳过
        early_null = False
        for j in range(free_ln, min(len(lines), free_ln + 3) + 1):
            sj = _safe_line(lines, j)
            if re.search(rf"\b{re.escape(var)}\s*=\s*(NULL|0)\s*;", sj):
                early_null = True
                break
        if early_null:
            continue

        reassigned = False
        uaf_evidence_line: Optional[int] = None

        deref_arrow = re.compile(rf"\b{re.escape(var)}\s*->")
        deref_star = re.compile(rf"(?<!\w)\*\s*{re.escape(var)}\b")
        deref_index = re.compile(rf"\b{re.escape(var)}\s*\[")
        assign_pat = re.compile(rf"\b{re.escape(var)}\s*=")

        for j in range(start, end + 1):
            sj = _safe_line(lines, j)
            # 先检测重新赋值（包括置NULL或重新指向），则视为“生命周期重置”，不报本条
            if assign_pat.search(sj):
                reassigned = True
                break
            # 检测明显的解引用使用
            if (
                deref_arrow.search(sj)
                or deref_star.search(sj)
                or deref_index.search(sj)
            ):
                uaf_evidence_line = j
                break

        if uaf_evidence_line and not reassigned:
            # 以 free 行作为证据点（保持与既有输出一致性）
            evidence = _strip_line(_safe_line(lines, free_ln))
            issues.append(
                Issue(
                    language="c/cpp",
                    category="memory_mgmt",
                    pattern="use_after_free_suspect",
                    file=relpath,
                    line=free_ln,
                    evidence=evidence,
                    description=f"变量 {var} 在 free 后的邻近窗口内出现了解引用使用（UAF 线索），且未检测到重新赋值/置空。",
                    suggestion="free 后应将指针置为 NULL，并避免在重新赋值前进行任何解引用；建议引入生命周期管理与动态/静态检测。",
                    confidence=0.65,
                    severity="high",
                )
            )
    return issues


def _rule_unchecked_io(lines: Sequence[str], relpath: str) -> List[Issue]:
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        # 排除预处理与声明
        t = s.lstrip()
        if t.startswith("#") or re.search(r"\b(typedef|extern)\b", s):
            continue
        m = RE_IO_API.search(s)
        if not m:
            continue

        # 若本行/紧随其后 2 行出现条件判断，认为已检查（直接跳过）
        nearby = " ".join(
            _safe_line(lines, i) for i in range(idx, min(idx + 2, len(lines)) + 1)
        )
        if re.search(r"\b(if|while|for)\s*\(", nearby) or re.search(
            r"(>=|<=|==|!=|<|>)", nearby
        ):
            continue

        # 若赋值给变量，则在后续窗口内寻找对该变量的检查
        assigned_var: Optional[str] = None
        try:
            # 仅截取调用前的左侧以匹配最近的 "var ="
            left = s[: m.start()]
            assigns = list(RE_GENERIC_ASSIGN.finditer(left))
            if assigns:
                assigned_var = assigns[-1].group(1)
        except Exception:
            assigned_var = None

        checked_via_var = False
        if assigned_var:
            end = min(len(lines), idx + 5)
            var_pat_cond = re.compile(
                rf"\b(if|while|for)\s*\([^)]*\b{re.escape(assigned_var)}\b[^)]*\)"
            )
            var_pat_cmp = re.compile(
                rf"\b{re.escape(assigned_var)}\b\s*(>=|<=|==|!=|<|>)"
            )
            for j in range(idx + 1, end + 1):
                sj = _safe_line(lines, j)
                if var_pat_cond.search(sj) or var_pat_cmp.search(sj):
                    checked_via_var = True
                    break
        if checked_via_var:
            continue

        # 到此仍未见检查，认为可能未检查错误
        conf = 0.65  # 较原先略微提高基础置信度，因已进行更多排除
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
            if not re.search(
                r"\\0|'\0'|\"\\0\"|len\s*-\s*1|sizeof\s*\(\s*\w+\s*\)\s*-\s*1",
                window_text,
            ):
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
    检测格式化字符串漏洞：printf/sprintf/snprintf/vsprintf/vsnprintf 的格式参数不是字面量；
    fprintf 的第二个参数不是字面量。
    准确性优化：
    - 允许常见本地化/包装宏作为格式参数包装字面量（如 _("..."), gettext("..."), tr("..."), QT_TR_NOOP("...")）
    - 若参数为变量名，回看若干行，若变量被赋值为字面量字符串，则视为较安全用法（跳过）
    - 针对不同函数，准确定位“格式串”所在的参数位置：
      printf: 第1参；sprintf/vsprintf: 第2参；snprintf/vsnprintf: 第3参；fprintf: 第2参
    """
    SAFE_WRAPPERS = (
        "_",
        "gettext",
        "dgettext",
        "ngettext",
        "tr",
        "QT_TR_NOOP",
        "QT_TRANSLATE_NOOP",
    )
    issues: List[Issue] = []

    def _arg_is_literal(s: str, j: int) -> bool:
        while j < len(s) and s[j].isspace():
            j += 1
        return j < len(s) and s[j] == '"'

    def _arg_is_wrapper_literal(s: str, j: int) -> bool:
        k = j
        while k < len(s) and (s[k].isalnum() or s[k] == "_"):
            k += 1
        name = s[j:k]
        p = k
        while p < len(s) and s[p].isspace():
            p += 1
        if name in SAFE_WRAPPERS and p < len(s) and s[p] == "(":
            q = p + 1
            while q < len(s) and s[q].isspace():
                q += 1
            return q < len(s) and s[q] == '"'
        return False

    def _leading_ident(s: str, j: int) -> Optional[str]:
        k = j
        if k < len(s) and (s[k].isalpha() or s[k] == "_"):
            while k < len(s) and (s[k].isalnum() or s[k] == "_"):
                k += 1
            return s[j:k]
        return None

    def _var_assigned_literal(
        var: str, lines: Sequence[str], upto_idx: int, lookback: int = 5
    ) -> bool:
        start = max(1, upto_idx - lookback)
        pat_assign = re.compile(rf"\b{re.escape(var)}\s*=\s*")
        for j in range(start, upto_idx):
            sj = _safe_line(lines, j)
            m = pat_assign.search(sj)
            if not m:
                continue
            k = m.end()
            while k < len(sj) and sj[k].isspace():
                k += 1
            if k < len(sj) and sj[k] == '"':
                return True
        return False

    def _nth_arg_start(s: str, open_paren_idx: int, n: int) -> Optional[int]:
        """
        返回第 n 个参数的起始索引（首个非空白字符），若失败返回 None。
        仅在单行内进行括号配对和逗号计数（启发式）。
        """
        depth = 0
        # 从 '(' 后开始
        i = open_paren_idx + 1
        # 跳到第一个参数
        # 如果需要第1个参数，先定位其起始
        # 统一逻辑：遍历，记录每个参数的起始位置
        starts: List[int] = []
        start_pos = None
        while i < len(s):
            ch = s[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                if depth == 0:
                    # 结束
                    if start_pos is not None:
                        starts.append(start_pos)
                        start_pos = None
                    break
                depth -= 1
            elif ch == "," and depth == 0:
                # 参数分隔
                if start_pos is None:
                    # 空参数，记录当前位置（可能是宏展开），尽量返回后续判断
                    starts.append(i + 1)
                else:
                    starts.append(start_pos)
                    start_pos = None
                # 下一个参数
            else:
                if not start_pos and not ch.isspace():
                    start_pos = i
            i += 1
        # 补上最后一个参数起点
        if start_pos is not None:
            starts.append(start_pos)
        # 去除参数起点的前导空白
        cleaned: List[int] = []
        for pos in starts:
            j = pos
            while j < len(s) and s[j].isspace():
                j += 1
            cleaned.append(j)
        if 1 <= n <= len(cleaned):
            return cleaned[n - 1]
        return None

    for idx, s in enumerate(lines, start=1):
        flagged = False
        # 处理 printf/sprintf/snprintf/vsprintf/vsnprintf（格式串参数位置不同）
        m1 = RE_PRINTF_LIKE.search(s)
        if m1:
            try:
                name = m1.group(1).lower()
                open_idx = s.index("(", m1.start())
                # 参数索引映射
                fmt_arg_map = {
                    "printf": 1,
                    "sprintf": 2,
                    "vsprintf": 2,
                    "snprintf": 3,
                    "vsnprintf": 3,
                }
                fmt_idx = fmt_arg_map.get(name, 1)
                j = _nth_arg_start(s, open_idx, fmt_idx)
                if j is not None:
                    # 字面量/包装字面量/回看字面量赋值的变量
                    if not _arg_is_literal(s, j):
                        if s[j].isalpha() or s[j] == "_":
                            if _arg_is_wrapper_literal(s, j):
                                flagged = False
                            else:
                                ident = _leading_ident(s, j)
                                if ident and _var_assigned_literal(
                                    ident, lines, idx, lookback=5
                                ):
                                    flagged = False
                                else:
                                    flagged = True
                        else:
                            flagged = True
                else:
                    # 无法解析参数位置，保守告警
                    flagged = True
            except Exception:
                pass

        # fprintf：第二个参数为格式串
        m2 = RE_FPRINTF.search(s)
        if not flagged and m2:
            try:
                open_idx = s.index("(", m2.start())
                j = _nth_arg_start(s, open_idx, 2)
                if j is not None:
                    if not _arg_is_literal(s, j):
                        if s[j].isalpha() or s[j] == "_":
                            if _arg_is_wrapper_literal(s, j):
                                flagged = False
                            else:
                                ident = _leading_ident(s, j)
                                if ident and _var_assigned_literal(
                                    ident, lines, idx, lookback=5
                                ):
                                    flagged = False
                                else:
                                    flagged = True
                        else:
                            flagged = True
                else:
                    flagged = True
            except Exception:
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
    准确性优化：
    - exec* 系列仅在第一个参数不是字面量路径时告警
    - 若第一个参数为变量名，向前回看若干行，若检测到该变量被赋值为字面量字符串，则视为较安全用法（跳过）
    """
    issues: List[Issue] = []

    def _arg_is_literal_or_wrapper(s: str, start_idx: int) -> bool:
        # 跳过空白，判断是否直接为字面量
        j = start_idx + 1
        while j < len(s) and s[j].isspace():
            j += 1
        return j < len(s) and s[j] == '"'

    def _first_arg_identifier(s: str, start_idx: int) -> Optional[str]:
        j = start_idx + 1
        while j < len(s) and s[j].isspace():
            j += 1
        if j < len(s) and (s[j].isalpha() or s[j] == "_"):
            k = j
            while k < len(s) and (s[k].isalnum() or s[k] == "_"):
                k += 1
            return s[j:k]
        return None

    def _var_assigned_literal(
        var: str, lines: Sequence[str], upto_idx: int, lookback: int = 5
    ) -> bool:
        # 在前 lookback 行内查找 var = "..."
        start = max(1, upto_idx - lookback)
        pat_assign = re.compile(rf"\b{re.escape(var)}\s*=\s*")
        for j in range(start, upto_idx):
            sj = _safe_line(lines, j)
            m = pat_assign.search(sj)
            if not m:
                continue
            # 检查赋值右侧是否为字面量（masked 文本中依旧保留引号）
            k = m.end()
            while k < len(sj) and sj[k].isspace():
                k += 1
            if k < len(sj) and sj[k] == '"':
                return True
        return False

    for idx, s in enumerate(lines, start=1):
        flagged = False
        m_sys = RE_SYSTEM_LIKE.search(s)
        if m_sys:
            try:
                start = s.index("(", m_sys.start())
                if not _arg_is_literal_or_wrapper(s, start):
                    # 若首参为变量且之前赋过字面量，则跳过
                    ident = _first_arg_identifier(s, start)
                    if ident and _var_assigned_literal(ident, lines, idx, lookback=5):
                        flagged = False
                    else:
                        flagged = True
            except Exception:
                pass
        if not flagged:
            m_exec = RE_EXEC_LIKE.search(s)
            if m_exec:
                try:
                    start = s.index("(", m_exec.start())
                    if not _arg_is_literal_or_wrapper(s, start):
                        ident = _first_arg_identifier(s, start)
                        if ident and _var_assigned_literal(
                            ident, lines, idx, lookback=5
                        ):
                            flagged = False
                        else:
                            flagged = True
                except Exception:
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
    准确性优化：
    - 忽略 GNU 扩展的 %ms（自动分配内存）与 %m[...] 模式（自动分配），这类不会对固定缓冲造成溢出
    - 忽略丢弃输入的 %*s（不写入目标缓冲）
    """
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        m = RE_SCANF_CALL.search(s)
        if not m:
            continue
        fmt = m.group(1)
        unsafe = False
        # 经典不安全情形：出现 %s 但未指定最大宽度
        if "%s" in fmt and not re.search(r"%\d+s", fmt):
            unsafe = True
        # 例外：%*s 丢弃输入，不写入目标缓冲
        if unsafe and re.search(r"%\*s", fmt):
            unsafe = False
        # 例外：GNU 扩展 %ms 或 %m[...]（自动分配）
        if unsafe and re.search(r"%m[a-z\[]", fmt, re.IGNORECASE):
            unsafe = False
        if unsafe:
            issues.append(
                Issue(
                    language="c/cpp",
                    category="buffer_overflow",
                    pattern="scanf_%s_no_width",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(s),
                    description="scanf/sscanf/fscanf 使用 %s 但未限制最大宽度，存在缓冲区溢出风险。",
                    suggestion='为 %s 指定最大宽度（如 "%255s"），或使用更安全的读取方式；若使用 GNU 扩展 %ms/%m[...] 请确保对返回内存进行释放。',
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
    - 出现 arr[...] 数组访问，且邻近未见明显的 NULL 检查。
    注：可能存在误报，需结合上下文确认。
    准确性优化：
    - 对于 *p 的检测，引入上下文判定，尽量排除乘法表达式 a * p 的误报
     （仅当 * 出现在典型解引用上下文，如行首/括号后/逗号后/赋值号后/分号后/冒号后/方括号后/逻辑非/取地址/另一解引用后）
    """
    issues: List[Issue] = []
    re_arrow = re.compile(r"\b([A-Za-z_]\w*)\s*->")
    re_star = re.compile(r"(?<!\w)\*\s*([A-Za-z_]\w*)\b")
    # 新增：检测数组访问 arr[...]，排除类型声明中的数组声明
    re_array_access = re.compile(r"\b([A-Za-z_]\w*)\s*\[")
    type_kw = re.compile(
        r"\b(typedef|struct|union|enum|class|char|int|long|short|void|size_t|ssize_t|FILE)\b"
    )

    def _is_deref_context(line: str, star_pos: int) -> bool:
        k = star_pos - 1
        while k >= 0 and line[k].isspace():
            k -= 1
        if k < 0:
            return True
        # 典型可视为解引用的前导字符集合
        return line[k] in "(*,=:{;[!&"

    def _is_array_declaration(line: str, var_pos: int) -> bool:
        """判断是否是数组声明而非数组访问"""
        # 检查变量前是否有类型关键字，且在同一行有分号（可能是声明）
        before = line[:var_pos]
        after = line[var_pos:]
        # 如果前面有类型关键字且后面有分号，可能是声明
        if type_kw.search(before) and ";" in after:
            # 进一步检查：如果后面是 ] 然后是 ; 或 =，更可能是声明
            if re.search(r"\]\s*[;=]", after):
                return True
        return False

    for idx, s in enumerate(lines, start=1):
        vars_hit: List[str] = []
        # '->' 访问几乎必为解引用
        for m in re_arrow.finditer(s):
            vars_hit.append(m.group(1))
        # '*p'：排除类型声明行；并通过上下文过滤乘法用法
        if "*" in s and not type_kw.search(s):
            for m in re_star.finditer(s):
                star_pos = m.start(0)
                if not _is_deref_context(s, star_pos):
                    continue
                vars_hit.append(m.group(1))
        # 数组访问 arr[...]：排除数组声明
        for m in re_array_access.finditer(s):
            var = m.group(1)
            var_pos = m.start(1)
            # 排除数组声明
            if _is_array_declaration(s, var_pos):
                continue
            # 排除明显的数组初始化（如 int arr[] = {...}）
            before_var = s[:var_pos]
            if type_kw.search(before_var) and "=" in s[var_pos:]:
                # 检查是否是初始化语法
                after_var = s[var_pos + len(var):]
                if re.match(r"\s*\[[^\]]*\]\s*=", after_var):
                    continue
            vars_hit.append(var)
        for v in set(vars_hit):
            if v == "this":  # C++ 成员函数中 this-> 通常不应视为空指针
                continue
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
    type_prefix = re.compile(
        r"\b(typedef|struct|union|enum|class|const|volatile|static|register|signed|unsigned|char|int|long|short|void|float|double)\b"
    )
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
            if re.search(rf"\b{re.escape(v)}\s*->", sj) or re.search(
                rf"(?<!\w)\*\s*{re.escape(v)}\b", sj
            ):
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
            m_un = RE_PTHREAD_UNLOCK.search(_safe_line(lines, j))
            if m_un and m_un.group(1) == mtx:
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


def _rule_double_free_and_free_non_heap(
    lines: Sequence[str], relpath: str
) -> List[Issue]:
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
            if re.fullmatch(
                r"\(?\s*(NULL|0|\(void\s*\*\)\s*0)\s*\)?", arg, re.IGNORECASE
            ):
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
    keywords = (
        "token",
        "nonce",
        "secret",
        "password",
        "passwd",
        "key",
        "auth",
        "salt",
        "session",
        "otp",
    )
    for idx, s in enumerate(lines, start=1):
        if RE_RAND.search(s):
            conf = 0.55
            window_text = " ".join(
                t for _, t in _window(lines, idx, before=1, after=1)
            ).lower()
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
    sensitive_keys = (
        "key",
        "secret",
        "token",
        "passwd",
        "password",
        "cred",
        "config",
        "cert",
        "private",
        "id_rsa",
    )
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
                window = " ".join(
                    t for _, t in _window(lines, idx, before=1, after=1)
                ).lower()
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
        # 宏常量（全大写+下划线/数字）通常为编译期常量，减少误报
        if re.fullmatch(r"[A-Z_][A-Z0-9_]*", arg):
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
    type_prefix = re.compile(
        r"\b(typedef|struct|union|enum|class|const|volatile|static|register|signed|unsigned|char|int|long|short|void|float|double|size_t|ssize_t)\b"
    )
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
        # 宏常量（全大写+下划线/数字）通常为编译期常量（非 VLA），降低误报
        if re.fullmatch(r"[A-Z_][A-Z0-9_]*", length_expr):
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
        nearby = " ".join(
            _safe_line(lines, i) for i in range(idx, min(idx + 2, len(lines)) + 1)
        )
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
    准确性优化：
    - 支持检测“与调用在同一行的 while(predicate) pthread_cond_wait(...)”写法，避免误报
    """
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        m = RE_PTHREAD_COND_WAIT.search(s)
        if not m:
            continue
        # 回看 2 行内是否有 while( ... )
        prev_text = " ".join(_safe_line(lines, j) for j in range(max(1, idx - 2), idx))
        has_prev_while = re.search(r"\bwhile\s*\(", prev_text) is not None
        # 同一行（调用前半部分）若包含 while(...)，也视为正确用法
        same_line_before = s[: m.start()]
        has_same_line_while = re.search(r"\bwhile\s*\(", same_line_before) is not None

        if has_prev_while or has_same_line_while:
            continue

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
            m_join = RE_PTHREAD_JOIN.search(sj)
            if m_join and m_join.group(1) == tid:
                joined_or_detached = True
                break
            m_detach = RE_PTHREAD_DETACH.search(sj)
            if m_detach and m_detach.group(1) == tid:
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


# ---------------------------
# C++ 特定检查规则
# ---------------------------


def _rule_new_delete_mismatch(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测 new[]/delete[] 和 new/delete 的匹配问题：
    - new[] 必须用 delete[] 释放
    - new 必须用 delete 释放（不能用 delete[]）
    """
    issues: List[Issue] = []
    new_array_vars: dict[str, int] = {}  # var -> line_no
    new_vars: dict[str, int] = {}  # var -> line_no

    # 收集 new[] 和 new 的分配
    for idx, s in enumerate(lines, start=1):
        # new[] 分配
        m = RE_NEW_ARRAY.search(s)
        if m:
            # 尝试提取变量名（简单启发式）
            assign_match = re.search(r"\b([A-Za-z_]\w*)\s*=\s*new\s+", s, re.IGNORECASE)
            if assign_match:
                var = assign_match.group(1)
                new_array_vars[var] = idx

        # new 分配（非数组）
        m_new = re.search(r"\b([A-Za-z_]\w*)\s*=\s*new\s+(?!.*\[)", s, re.IGNORECASE)
        if m_new:
            var = m_new.group(1)
            new_vars[var] = idx

    # 检查 delete[] 和 delete 的使用
    for idx, s in enumerate(lines, start=1):
        # delete[] 使用
        if RE_DELETE_ARRAY.search(s):
            # 提取变量名
            m = re.search(r"delete\s*\[\s*\]\s*([A-Za-z_]\w*)", s, re.IGNORECASE)
            if m:
                var = m.group(1)
                if var in new_vars:
                    # 用 delete[] 释放了 new 分配的内存
                    issues.append(
                        Issue(
                            language="c/cpp",
                            category="memory_mgmt",
                            pattern="delete_array_mismatch",
                            file=relpath,
                            line=idx,
                            evidence=_strip_line(s),
                            description="使用 delete[] 释放由 new 分配的内存（非数组），存在未定义行为风险。",
                            suggestion="new 分配的内存应使用 delete 释放；new[] 分配的内存应使用 delete[] 释放。",
                            confidence=0.85,
                            severity="high",
                        )
                    )

        # delete 使用（非数组）
        if RE_DELETE.search(s):
            m = re.search(r"delete\s+([A-Za-z_]\w*)", s, re.IGNORECASE)
            if m:
                var = m.group(1)
                if var in new_array_vars:
                    # 用 delete 释放了 new[] 分配的内存
                    issues.append(
                        Issue(
                            language="c/cpp",
                            category="memory_mgmt",
                            pattern="delete_mismatch",
                            file=relpath,
                            line=idx,
                            evidence=_strip_line(s),
                            description="使用 delete 释放由 new[] 分配的数组内存，存在未定义行为风险。",
                            suggestion="new[] 分配的内存应使用 delete[] 释放；new 分配的内存应使用 delete 释放。",
                            confidence=0.85,
                            severity="high",
                        )
                    )

    return issues


def _rule_reinterpret_cast_unsafe(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测 reinterpret_cast 的不安全使用（高风险类型转换）。
    """
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        if RE_REINTERPRET_CAST.search(s):
            conf = 0.7
            # 如果转换为指针类型，风险更高
            if "->" in s or "*" in s:
                conf += 0.1
            issues.append(
                Issue(
                    language="c/cpp",
                    category="type_safety",
                    pattern="reinterpret_cast_unsafe",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(s),
                    description="使用 reinterpret_cast 进行类型转换，可能导致未定义行为或类型安全问题。",
                    suggestion="优先使用 static_cast 或 dynamic_cast；若必须使用 reinterpret_cast，需确保类型布局兼容并添加详细注释说明。",
                    confidence=min(conf, 0.9),
                    severity="high",
                )
            )
    return issues


def _rule_const_cast_unsafe(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测 const_cast 的不安全使用（移除 const 修饰符可能导致未定义行为）。
    """
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        if RE_CONST_CAST.search(s):
            conf = 0.65
            # 如果通过 const_cast 修改原本为 const 的对象，风险更高
            if "=" in s and not re.search(r"const\s+[A-Za-z_]\w*\s*\*", s):
                conf += 0.1
            issues.append(
                Issue(
                    language="c/cpp",
                    category="type_safety",
                    pattern="const_cast_unsafe",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(s),
                    description="使用 const_cast 移除 const 修饰符，可能导致未定义行为（如修改常量对象）。",
                    suggestion="避免使用 const_cast；若必须使用，确保仅用于移除非底层 const 且对象本身可变。",
                    confidence=min(conf, 0.8),
                    severity="high",
                )
            )
    return issues


def _rule_vector_string_bounds_check(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测 vector 和 string 的越界访问（使用 [] 而非 .at()）。
    启发式：检测 [] 访问，若附近未见边界检查，则提示风险。
    """
    issues: List[Issue] = []
    vector_vars: set[str] = set()
    string_vars: set[str] = set()

    # 先收集 vector 和 string 变量
    for idx, s in enumerate(lines, start=1):
        m = RE_VECTOR_VAR.search(s)
        if m:
            vector_vars.add(m.group(1))
        m = RE_STRING_VAR.search(s)
        if m:
            string_vars.add(m.group(1))

    for idx, s in enumerate(lines, start=1):
        # vector 访问：检测 var[...] 模式
        for var in vector_vars:
            if re.search(rf"\b{re.escape(var)}\s*\[", s):
                # 检查是否使用了 .at()（安全访问）
                if not RE_AT_METHOD.search(s):
                    # 检查附近是否有边界检查
                    window_text = " ".join(
                        t for _, t in _window(lines, idx, before=2, after=2)
                    )
                    if not re.search(
                        rf"\b{re.escape(var)}\s*\.(size|length|empty|at)\s*\(",
                        window_text,
                        re.IGNORECASE,
                    ):
                        issues.append(
                            Issue(
                                language="c/cpp",
                                category="buffer_overflow",
                                pattern="vector_bounds_check",
                                file=relpath,
                                line=idx,
                                evidence=_strip_line(s),
                                description=f"vector {var} 使用 [] 访问可能越界，建议使用 .at() 进行边界检查。",
                                suggestion="使用 .at() 方法进行安全访问，或在使用 [] 前显式检查索引范围。",
                                confidence=0.6,
                                severity="medium",
                            )
                        )
                        break  # 每行只报告一次

        # string 访问：检测 var[...] 模式
        for var in string_vars:
            if re.search(rf"\b{re.escape(var)}\s*\[", s):
                if not RE_AT_METHOD.search(s):
                    window_text = " ".join(
                        t for _, t in _window(lines, idx, before=2, after=2)
                    )
                    if not re.search(
                        rf"\b{re.escape(var)}\s*\.(size|length|empty|at)\s*\(",
                        window_text,
                        re.IGNORECASE,
                    ):
                        issues.append(
                            Issue(
                                language="c/cpp",
                                category="buffer_overflow",
                                pattern="string_bounds_check",
                                file=relpath,
                                line=idx,
                                evidence=_strip_line(s),
                                description=f"string {var} 使用 [] 访问可能越界，建议使用 .at() 进行边界检查。",
                                suggestion="使用 .at() 方法进行安全访问，或在使用 [] 前显式检查索引范围。",
                                confidence=0.6,
                                severity="medium",
                            )
                        )
                        break  # 每行只报告一次
    return issues


def _rule_missing_virtual_dtor(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测基类缺少虚析构函数的问题。
    启发式：检测 class 声明，若存在虚函数但析构函数非虚，则提示。
    """
    issues: List[Issue] = []
    classes: dict[
        str, dict[str, Any]
    ] = {}  # class_name -> {"line": int, "has_virtual": bool, "has_virtual_dtor": bool}
    current_class: Optional[str] = None
    in_class = False
    brace_depth = 0

    for idx, s in enumerate(lines, start=1):
        # 检测 class 声明
        m_class = RE_CLASS_DECL.search(s)
        if m_class:
            class_name = m_class.group(1)
            classes[class_name] = {
                "line": idx,
                "has_virtual": False,
                "has_virtual_dtor": False,
            }
            current_class = class_name
            in_class = True
            brace_depth = s.count("{") - s.count("}")
            continue

        if in_class and current_class:
            brace_depth += s.count("{") - s.count("}")
            if brace_depth <= 0:
                in_class = False
                current_class = None
                continue

            # 检测虚函数
            if re.search(r"\bvirtual\s+[^~]", s, re.IGNORECASE):
                classes[current_class]["has_virtual"] = True

            # 检测虚析构函数
            if RE_VIRTUAL_DTOR.search(s):
                classes[current_class]["has_virtual_dtor"] = True

    # 检查有虚函数但无虚析构函数的类
    for class_name, info in classes.items():
        if info["has_virtual"] and not info["has_virtual_dtor"]:
            issues.append(
                Issue(
                    language="c/cpp",
                    category="memory_mgmt",
                    pattern="missing_virtual_dtor",
                    file=relpath,
                    line=info["line"],
                    evidence=_strip_line(_safe_line(lines, info["line"])),
                    description=f"类 {class_name} 包含虚函数但析构函数非虚，通过基类指针删除派生类对象可能导致未定义行为。",
                    suggestion="为基类添加虚析构函数，确保通过基类指针删除派生类对象时正确调用派生类析构函数。",
                    confidence=0.75,
                    severity="high",
                )
            )

    return issues


def _rule_move_after_use(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测移动后使用的风险：对象被 std::move 后仍被使用。
    """
    issues: List[Issue] = []
    moved_vars: dict[str, int] = {}  # var -> line_no

    for idx, s in enumerate(lines, start=1):
        # 检测 std::move 赋值
        m = RE_MOVE_ASSIGN.search(s)
        if m:
            var = m.group(1)
            moved_vars[var] = idx

        # 检测移动后的使用
        vars_to_remove: set[str] = set()  # 收集要删除的键，避免在遍历时修改字典
        for var, move_line in moved_vars.items():
            if idx > move_line and idx <= move_line + 10:  # 在移动后 10 行内
                # 检测变量使用（排除重新赋值）
                if re.search(rf"\b{re.escape(var)}\b", s) and not re.search(
                    rf"\b{re.escape(var)}\s*=", s
                ):
                    # 检查是否是重新赋值（重置移动状态）
                    if re.search(rf"\b{re.escape(var)}\s*=\s*(?!std::move)", s):
                        # 重新赋值，移除记录
                        vars_to_remove.add(var)
                    else:
                        # 可能是使用
                        if re.search(rf"\b{re.escape(var)}\s*(->|\[|\.|\(|,)", s):
                            issues.append(
                                Issue(
                                    language="c/cpp",
                                    category="memory_mgmt",
                                    pattern="move_after_use",
                                    file=relpath,
                                    line=idx,
                                    evidence=_strip_line(s),
                                    description=f"变量 {var} 在 std::move 后仍被使用，移动后的对象处于有效但未指定状态，可能导致未定义行为。",
                                    suggestion="移动后的对象不应再使用，除非重新赋值；考虑使用移动语义后立即停止使用该对象。",
                                    confidence=0.7,
                                    severity="high",
                                )
                            )
                            # 移除记录，避免重复报告
                            vars_to_remove.add(var)

        # 遍历结束后再删除
        for var in vars_to_remove:
            moved_vars.pop(var, None)

    return issues


def _rule_uncaught_exception(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测可能未捕获的异常：throw 语句附近未见 try-catch。
    """
    issues: List[Issue] = []
    for idx, s in enumerate(lines, start=1):
        if RE_THROW.search(s):
            # 检查附近是否有 try-catch
            window_text = " ".join(
                t for _, t in _window(lines, idx, before=10, after=10)
            )
            has_try = RE_TRY.search(window_text) is not None
            has_catch = RE_CATCH.search(window_text) is not None

            if not (has_try and has_catch):
                conf = 0.6
                # 如果在 noexcept 函数中抛出异常，风险更高
                prev_text = " ".join(
                    t for _, t in _window(lines, idx, before=5, after=0)
                )
                if RE_NOEXCEPT.search(prev_text):
                    conf += 0.2

                issues.append(
                    Issue(
                        language="c/cpp",
                        category="error_handling",
                        pattern="uncaught_exception",
                        file=relpath,
                        line=idx,
                        evidence=_strip_line(s),
                        description="检测到 throw 语句，但附近未见 try-catch 块，可能导致未捕获异常。",
                        suggestion="确保异常在适当的作用域内被捕获；考虑使用 RAII 确保资源在异常时正确释放。",
                        confidence=min(conf, 0.85),
                        severity="high" if conf >= 0.8 else "medium",
                    )
                )
    return issues


def _rule_smart_ptr_cycle(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测智能指针可能的循环引用问题（启发式）。
    注意：完全检测循环引用需要图分析，这里仅做简单启发式检测。
    """
    issues: List[Issue] = []
    shared_ptr_vars: set[str] = set()

    for idx, s in enumerate(lines, start=1):
        # 收集 shared_ptr 变量
        if RE_SHARED_PTR.search(s):
            m = RE_SMART_PTR_ASSIGN.search(s)
            if m:
                var = m.group(1)
                shared_ptr_vars.add(var)

        # 检测 shared_ptr 之间的相互引用（简单启发式）
        if RE_SHARED_PTR.search(s) and shared_ptr_vars:
            # 检查是否在 shared_ptr 初始化中使用了另一个 shared_ptr
            for var in shared_ptr_vars:
                if (
                    re.search(rf"\b{re.escape(var)}\b", s)
                    and "make_shared" in s.lower()
                ):
                    # 简单启发：如果两个 shared_ptr 相互引用，可能存在循环
                    # 这里仅做提示，实际需要更复杂的分析
                    pass

    # 检测 weak_ptr 的使用（通常用于打破循环引用）
    has_weak_ptr = False
    for idx, s in enumerate(lines, start=1):
        if RE_WEAK_PTR.search(s):
            has_weak_ptr = True
            break

    # 如果大量使用 shared_ptr 但未见 weak_ptr，提示可能的循环引用风险
    if len(shared_ptr_vars) > 3 and not has_weak_ptr:
        # 在第一个 shared_ptr 使用处提示
        for idx, s in enumerate(lines, start=1):
            if RE_SHARED_PTR.search(s):
                issues.append(
                    Issue(
                        language="c/cpp",
                        category="memory_mgmt",
                        pattern="smart_ptr_cycle_risk",
                        file=relpath,
                        line=idx,
                        evidence=_strip_line(s),
                        description="检测到多个 shared_ptr 使用但未见 weak_ptr，可能存在循环引用导致内存泄漏的风险。",
                        suggestion="检查对象间的引用关系，必要时使用 weak_ptr 打破循环引用；考虑使用 unique_ptr 替代 shared_ptr 以明确所有权。",
                        confidence=0.5,
                        severity="medium",
                    )
                )
                break

    return issues


def _rule_cpp_deadlock_patterns(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测 C++ 标准库（std::mutex）相关的死锁风险：
    - 双重加锁：同一 mutex 在未解锁情况下再次加锁
    - 可能缺失解锁：lock() 后在后续窗口内未看到对应 unlock()
    - 锁顺序反转：存在 (A->B) 与 (B->A) 两种加锁顺序
    - 未使用 std::lock/scoped_lock：手动锁定多个 mutex 时未使用死锁避免机制
    实现基于启发式，可能产生误报。
    """
    issues: List[Issue] = []
    lock_stack: list[str] = []  # 当前持有的锁栈
    order_pairs: dict[tuple[str, str], int] = {}  # 加锁顺序对 -> 行号
    mutex_vars: set[str] = set()  # 所有 mutex 变量名

    # 先收集所有 mutex 变量
    for idx, s in enumerate(lines, start=1):
        m = RE_STD_MUTEX.search(s)
        if m:
            mutex_vars.add(m.group(1))

    # 扫描加锁/解锁操作
    for idx, s in enumerate(lines, start=1):
        # 检测 lock() 调用
        m_lock = RE_MUTEX_LOCK.search(s)
        if m_lock:
            mtx = m_lock.group(1)
            if mtx in mutex_vars:
                # 双重加锁检测
                if mtx in lock_stack:
                    issues.append(
                        Issue(
                            language="c/cpp",
                            category="error_handling",
                            pattern="cpp_double_lock",
                            file=relpath,
                            line=idx,
                            evidence=_strip_line(s),
                            description=f"mutex {mtx} 在未解锁的情况下被再次加锁，存在死锁风险。",
                            suggestion="避免对同一 mutex 重复加锁；考虑使用 std::recursive_mutex 或重构代码避免嵌套加锁。",
                            confidence=0.8,
                            severity="high",
                        )
                    )
                # 锁顺序记录
                if lock_stack and lock_stack[-1] != mtx:
                    pair = (lock_stack[-1], mtx)
                    order_pairs.setdefault(pair, idx)
                lock_stack.append(mtx)

        # 检测 unlock() 调用
        m_unlock = RE_MUTEX_UNLOCK.search(s)
        if m_unlock:
            mtx = m_unlock.group(1)
            if mtx in mutex_vars and mtx in lock_stack:
                # 从栈中移除最近的相同锁
                for k in range(len(lock_stack) - 1, -1, -1):
                    if lock_stack[k] == mtx:
                        del lock_stack[k]
                        break

        # 检测 lock_guard/unique_lock（RAII，自动解锁，通常更安全）
        RE_LOCK_GUARD.search(s) or RE_UNIQUE_LOCK.search(s) or RE_SHARED_LOCK.search(s)

        # 检测 std::lock 或 scoped_lock（死锁避免机制）
        has_safe_lock = RE_STD_LOCK.search(s) or RE_SCOPED_LOCK.search(s)

        # 粗略按作用域结束重置
        if "}" in s and not has_safe_lock:
            # 如果作用域结束且栈中还有锁，可能是问题（但可能是 RAII 锁，所以降低置信度）
            if lock_stack:
                # 这里不直接报错，因为可能是 RAII 锁
                pass

        # 检测手动锁定多个 mutex 但未使用 std::lock
        if m_lock and len(lock_stack) > 1 and not has_safe_lock:
            # 在锁定第二个 mutex 时，如果之前已持有锁且未使用 std::lock，提示风险
            if idx > 1:
                prev_text = " ".join(
                    _safe_line(lines, j) for j in range(max(1, idx - 3), idx)
                )
                if not RE_STD_LOCK.search(prev_text) and not RE_SCOPED_LOCK.search(
                    prev_text
                ):
                    issues.append(
                        Issue(
                            language="c/cpp",
                            category="error_handling",
                            pattern="cpp_multiple_lock_unsafe",
                            file=relpath,
                            line=idx,
                            evidence=_strip_line(s),
                            description="检测到手动锁定多个 mutex 但未使用 std::lock 或 std::scoped_lock，存在死锁风险。",
                            suggestion="使用 std::lock 或 std::scoped_lock 同时锁定多个 mutex，可避免死锁；或统一加锁顺序。",
                            confidence=0.65,
                            severity="high",
                        )
                    )

    # 锁顺序反转检测
    for (a, b), ln in order_pairs.items():
        if (b, a) in order_pairs:
            issues.append(
                Issue(
                    language="c/cpp",
                    category="error_handling",
                    pattern="cpp_lock_order_inversion",
                    file=relpath,
                    line=order_pairs[(b, a)],
                    evidence=_strip_line(_safe_line(lines, order_pairs[(b, a)])),
                    description=f"检测到 mutex 加锁顺序反转：({a} -> {b}) 与 ({b} -> {a})，存在死锁风险。",
                    suggestion="统一多锁的获取顺序，制定全局锁等级；或使用 std::lock/scoped_lock 避免死锁。",
                    confidence=0.7,
                    severity="high",
                )
            )

    # 可能缺失解锁：在 lock() 后的 50 行窗口内未见对应 unlock()
    for idx, s in enumerate(lines, start=1):
        m_lock = RE_MUTEX_LOCK.search(s)
        if not m_lock:
            continue
        mtx = m_lock.group(1)
        if mtx not in mutex_vars:
            continue

        # 检查是否是 lock_guard/unique_lock（RAII，自动解锁）
        window_text = " ".join(
            _safe_line(lines, j) for j in range(idx, min(idx + 3, len(lines)) + 1)
        )
        is_raii = (
            RE_LOCK_GUARD.search(window_text)
            or RE_UNIQUE_LOCK.search(window_text)
            or RE_SHARED_LOCK.search(window_text)
        )
        if is_raii:
            continue  # RAII 锁会自动解锁，跳过

        end = min(len(lines), idx + 50)
        unlocked = False
        for j in range(idx + 1, end + 1):
            sj = _safe_line(lines, j)
            m_un = RE_MUTEX_UNLOCK.search(sj)
            if m_un and m_un.group(1) == mtx:
                unlocked = True
                break
            # 检查作用域结束（可能是 RAII 锁）
            if "}" in sj:
                # 检查是否是 lock_guard/unique_lock 的作用域
                prev_scope = " ".join(
                    _safe_line(lines, k) for k in range(max(1, j - 5), j)
                )
                if RE_LOCK_GUARD.search(prev_scope) or RE_UNIQUE_LOCK.search(
                    prev_scope
                ):
                    unlocked = True
                    break

        if not unlocked:
            issues.append(
                Issue(
                    language="c/cpp",
                    category="error_handling",
                    pattern="cpp_missing_unlock_suspect",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(s),
                    description=f"在 mutex {mtx} 调用 lock() 之后的邻近窗口内未检测到匹配 unlock()，可能存在缺失解锁的风险。",
                    suggestion="确保所有 lock() 路径都有配对的 unlock()；考虑使用 std::lock_guard 或 std::unique_lock（RAII）自动管理锁生命周期。",
                    confidence=0.55,
                    severity="medium",
                )
            )

    return issues


def _rule_data_race_suspect(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测可能的数据竞争（data race）风险：
    - 共享变量（全局/静态变量）在多线程环境下未受保护访问
    - 检测到线程创建但共享变量访问时未见锁保护
    - volatile 误用（volatile 不能保证线程安全）
    - 未使用原子操作保护共享变量

    实现基于启发式，需要结合上下文分析。
    """
    issues: List[Issue] = []
    shared_vars: set[str] = set()  # 共享变量集合
    thread_creation_lines: list[int] = []  # 线程创建行号
    atomic_vars: set[str] = set()  # 原子变量集合
    volatile_vars: set[str] = set()  # volatile 变量集合

    # 第一遍扫描：收集共享变量、线程创建、原子变量
    for idx, s in enumerate(lines, start=1):
        # 收集全局/静态变量
        m_static = RE_STATIC_VAR.search(s)
        if m_static:
            var = m_static.group(1)
            # 排除 const 变量（只读，通常安全）
            if "const" not in s.lower():
                shared_vars.add(var)

        m_extern = RE_EXTERN_VAR.search(s)
        if m_extern:
            var = m_extern.group(1)
            if "const" not in s.lower():
                shared_vars.add(var)

        # 检测全局变量声明（文件作用域）
        if idx == 1 or (idx > 1 and _safe_line(lines, idx - 1).strip().endswith("}")):
            # 可能是文件作用域的变量
            m_global = re.search(r"^[A-Za-z_]\w*(?:\s+\*|\s+)+([A-Za-z_]\w*)\s*[=;]", s)
            if m_global and "const" not in s.lower() and "static" not in s.lower():
                var = m_global.group(1)
                shared_vars.add(var)

        # 检测线程创建
        if RE_PTHREAD_CREATE.search(s) or RE_STD_THREAD.search(s):
            thread_creation_lines.append(idx)

        # 收集原子变量
        m_atomic = RE_ATOMIC.search(s)
        if m_atomic:
            var = m_atomic.group(1)
            atomic_vars.add(var)

        # 收集 volatile 变量
        m_volatile = RE_VOLATILE.search(s)
        if m_volatile:
            var = m_volatile.group(1)
            volatile_vars.add(var)

    # 如果没有线程创建，通常不存在数据竞争风险
    if not thread_creation_lines:
        return issues

    # 第二遍扫描：检测共享变量访问时的保护情况
    for idx, s in enumerate(lines, start=1):
        # 检测共享变量的访问（赋值或读取）
        for var in shared_vars:
            if var in atomic_vars:
                continue  # 原子变量，通常安全

            # 检测变量访问
            var_pattern = re.compile(rf"\b{re.escape(var)}\b")
            if not var_pattern.search(s):
                continue

            # 检查是否是赋值操作
            is_write = RE_VAR_ASSIGN.search(s) and var in s[: s.find("=")]

            # 检查附近是否有锁保护
            window_text = " ".join(t for _, t in _window(lines, idx, before=5, after=5))
            has_lock = (
                RE_PTHREAD_LOCK.search(window_text) is not None
                or RE_MUTEX_LOCK.search(window_text) is not None
                or RE_LOCK_GUARD.search(window_text) is not None
                or RE_UNIQUE_LOCK.search(window_text) is not None
                or RE_SHARED_LOCK.search(window_text) is not None
            )

            # 检查是否在锁的作用域内（简单启发式）
            # 查找最近的锁
            lock_line = None
            for j in range(max(1, idx - 10), idx):
                sj = _safe_line(lines, j)
                if (
                    RE_PTHREAD_LOCK.search(sj)
                    or RE_MUTEX_LOCK.search(sj)
                    or RE_LOCK_GUARD.search(sj)
                    or RE_UNIQUE_LOCK.search(sj)
                ):
                    lock_line = j
                    break

            # 检查锁是否已解锁
            unlocked = False
            if lock_line:
                for j in range(lock_line + 1, idx):
                    sj = _safe_line(lines, j)
                    if RE_PTHREAD_UNLOCK.search(sj) or RE_MUTEX_UNLOCK.search(sj):
                        unlocked = True
                        break

            # 如果未检测到锁保护，且是写操作，风险更高
            if not has_lock or (lock_line and unlocked):
                conf = 0.6
                if is_write:
                    conf += 0.15
                if var in volatile_vars:
                    # volatile 不能保证线程安全，但可能被误用
                    conf += 0.1

                # 检查是否在函数参数中（可能是局部变量，降低风险）
                if "(" in s and ")" in s:
                    # 可能是函数调用参数，降低置信度
                    conf -= 0.1

                issues.append(
                    Issue(
                        language="c/cpp",
                        category="concurrency",
                        pattern="data_race_suspect",
                        file=relpath,
                        line=idx,
                        evidence=_strip_line(s),
                        description=f"共享变量 {var} 在多线程环境下访问但未见明确的锁保护，可能存在数据竞争风险。",
                        suggestion="使用互斥锁保护共享变量访问；或使用原子操作（std::atomic）进行无锁编程；注意 volatile 不能保证线程安全。",
                        confidence=min(conf, 0.85),
                        severity="high" if conf >= 0.7 else "medium",
                    )
                )

    # 检测 volatile 的误用（volatile 不能保证线程安全）
    for idx, s in enumerate(lines, start=1):
        for var in volatile_vars:
            if var in atomic_vars:
                continue  # 如果同时是原子变量，跳过

            if re.search(rf"\b{re.escape(var)}\b", s):
                # 检查是否在多线程上下文中使用 volatile
                window_text = " ".join(
                    t for _, t in _window(lines, idx, before=3, after=3)
                )
                has_thread = (
                    RE_PTHREAD_CREATE.search(window_text) is not None
                    or RE_STD_THREAD.search(window_text) is not None
                    or any(abs(j - idx) < 20 for j in thread_creation_lines)
                )

                if has_thread:
                    # 检查是否有锁保护
                    has_lock = (
                        RE_PTHREAD_LOCK.search(window_text) is not None
                        or RE_MUTEX_LOCK.search(window_text) is not None
                        or RE_LOCK_GUARD.search(window_text) is not None
                    )

                    if not has_lock:
                        issues.append(
                            Issue(
                                language="c/cpp",
                                category="concurrency",
                                pattern="volatile_not_threadsafe",
                                file=relpath,
                                line=idx,
                                evidence=_strip_line(s),
                                description=f"volatile 变量 {var} 在多线程环境下使用，但 volatile 不能保证线程安全，可能存在数据竞争。",
                                suggestion="volatile 仅防止编译器优化，不能保证原子性或内存可见性；使用 std::atomic 或互斥锁保护共享变量。",
                                confidence=0.7,
                                severity="high",
                            )
                        )

    return issues


def _rule_smart_ptr_get_unsafe(lines: Sequence[str], relpath: str) -> List[Issue]:
    """
    检测智能指针的 .get() 方法不安全使用（返回的原始指针可能悬空）。
    """
    issues: List[Issue] = []
    smart_ptr_vars: set[str] = set()

    # 先收集智能指针变量
    for idx, s in enumerate(lines, start=1):
        m = RE_SMART_PTR_ASSIGN.search(s)
        if m:
            smart_ptr_vars.add(m.group(1))
        # 也检测声明
        if RE_SHARED_PTR.search(s) or RE_UNIQUE_PTR.search(s) or RE_WEAK_PTR.search(s):
            m = re.search(r"\b([A-Za-z_]\w*)\s*(?:=|;)", s)
            if m:
                smart_ptr_vars.add(m.group(1))

    for idx, s in enumerate(lines, start=1):
        # 检测 .get() 调用
        for var in smart_ptr_vars:
            if re.search(rf"\b{re.escape(var)}\s*\.get\s*\(", s, re.IGNORECASE):
                conf = 0.65
                # 如果 .get() 的结果被存储或传递，风险更高
                if "=" in s or re.search(r"\.get\s*\([^)]*\)\s*[=,\(]", s):
                    conf += 0.1

                issues.append(
                    Issue(
                        language="c/cpp",
                        category="memory_mgmt",
                        pattern="smart_ptr_get_unsafe",
                        file=relpath,
                        line=idx,
                        evidence=_strip_line(s),
                        description=f"智能指针 {var} 使用 .get() 方法获取原始指针，若智能指针生命周期结束，原始指针将悬空。",
                        suggestion="避免存储 .get() 返回的原始指针；若必须使用，确保智能指针的生命周期覆盖原始指针的使用期。",
                        confidence=min(conf, 0.8),
                        severity="high",
                    )
                )
                break  # 每行只报告一次
    return issues


def analyze_c_cpp_text(relpath: str, text: str) -> List[Issue]:
    """
    基于提供的文本进行 C/C++ 启发式分析。
    - 准确性优化：在启发式匹配前移除注释（保留字符串/字符字面量），
      以避免注释中的API命中导致的误报。
    - 准确性优化2：对通用 API 扫描使用“字符串内容掩蔽”的副本，避免把字符串里的片段当作代码。
    """
    pre_text = _strip_if0_blocks(text)
    clean_text = _remove_comments_preserve_strings(pre_text)
    masked_text = _mask_strings_preserve_len(clean_text)
    # 原始行：保留字符串内容，供需要解析字面量的规则使用（如格式串、scanf 宽度等）
    lines = clean_text.splitlines()
    # 掩蔽行：字符串内容已被空格替换，适合用于通用 API/关键字匹配，减少误报
    mlines = masked_text.splitlines()

    issues: List[Issue] = []
    # 通用 API/关键字匹配（使用掩蔽行）
    issues.extend(_rule_unsafe_api(mlines, relpath))
    issues.extend(_rule_boundary_funcs(mlines, relpath))
    issues.extend(_rule_realloc_assign_back(mlines, relpath))
    issues.extend(_rule_malloc_no_null_check(mlines, relpath))
    issues.extend(_rule_function_return_ptr_no_check(mlines, relpath))
    issues.extend(_rule_unchecked_io(mlines, relpath))
    # 需要字符串字面量信息的规则（使用原始行）
    issues.extend(_rule_strncpy_no_nullterm(lines, relpath))
    issues.extend(_rule_format_string(lines, relpath))
    issues.extend(_rule_scanf_no_width(lines, relpath))
    # 其他规则
    issues.extend(_rule_insecure_tmpfile(mlines, relpath))
    issues.extend(_rule_command_execution(mlines, relpath))
    issues.extend(_rule_alloc_size_overflow(mlines, relpath))
    issues.extend(_rule_double_free_and_free_non_heap(mlines, relpath))
    issues.extend(_rule_atoi_family(mlines, relpath))
    issues.extend(_rule_rand_insecure(mlines, relpath))
    issues.extend(_rule_strtok_nonreentrant(mlines, relpath))
    issues.extend(_rule_open_permissive_perms(mlines, relpath))
    issues.extend(_rule_alloca_unbounded(mlines, relpath))
    issues.extend(_rule_vla_usage(mlines, relpath))
    issues.extend(_rule_pthread_returns_unchecked(mlines, relpath))
    issues.extend(_rule_cond_wait_no_loop(mlines, relpath))
    issues.extend(_rule_thread_leak_no_join(mlines, relpath))
    issues.extend(_rule_inet_legacy(mlines, relpath))
    issues.extend(_rule_time_apis_not_threadsafe(mlines, relpath))
    issues.extend(_rule_getenv_unchecked(mlines, relpath))
    # 复杂语义（使用掩蔽行避免字符串干扰）
    issues.extend(_rule_uaf_suspect(mlines, relpath))
    issues.extend(_rule_possible_null_deref(mlines, relpath))
    issues.extend(_rule_uninitialized_ptr_use(mlines, relpath))
    issues.extend(_rule_deadlock_patterns(mlines, relpath))
    # C++ 特定检查规则
    issues.extend(_rule_new_delete_mismatch(mlines, relpath))
    issues.extend(_rule_reinterpret_cast_unsafe(mlines, relpath))
    issues.extend(_rule_const_cast_unsafe(mlines, relpath))
    issues.extend(_rule_vector_string_bounds_check(mlines, relpath))
    issues.extend(_rule_missing_virtual_dtor(mlines, relpath))
    issues.extend(_rule_move_after_use(mlines, relpath))
    issues.extend(_rule_uncaught_exception(mlines, relpath))
    issues.extend(_rule_smart_ptr_cycle(mlines, relpath))
    issues.extend(_rule_smart_ptr_get_unsafe(mlines, relpath))
    # C++ 死锁检测
    issues.extend(_rule_cpp_deadlock_patterns(mlines, relpath))
    # 数据竞争检测
    issues.extend(_rule_data_race_suspect(mlines, relpath))
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
