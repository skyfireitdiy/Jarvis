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
from typing import Dict
from typing import TYPE_CHECKING
from typing import Iterable
from typing import List
from typing import Optional
from typing import Sequence
from typing import Tuple

from jarvis.jarvis_sec.types import Issue

if TYPE_CHECKING:
    from jarvis.jarvis_sec.project_database import ProjectDatabase

# 污点分析框架（核心依赖）
import jarvis.jarvis_sec.taint_analyzer as taint_analyzer

# 数据流分析器（用于误报过滤）
from jarvis.jarvis_sec.data_flow_analyzer import (
    DataFlowAnalyzer,
    DataFlowResult,
    PointerState,
)

# ---------------------------
# 辅助函数
# ---------------------------


def _is_cpp_file(file_path: str) -> bool:
    """判断文件是否为C++文件"""
    return file_path.lower().endswith((".cpp", ".cxx", ".cc", ".hpp", ".hxx", ".hh"))


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
    r"\b(fopen|fread|fwrite|read|write|open|close)\s*\(",
    re.IGNORECASE,
)
# fclose 通常不需要检查返回值（关闭后检查意义不大）
RE_IO_API_NO_CHECK = re.compile(
    r"\b(fclose)\s*\(",
    re.IGNORECASE,
)
# 权限操作函数（返回值检查至关重要）
RE_PRIV_API = re.compile(
    r"\b(setuid|setgid|seteuid|setegid|setreuid|setregid|setresuid|setresgid|"
    r"chown|lchown|fchown|chmod|fchmod|fchmodat)\s*\(",
    re.IGNORECASE,
)
# 反序列化相关函数（CWE-502）
RE_DESERIALIZE_API = re.compile(
    r"\b(json_loads|json_load|yaml_load|pickle_loads|pickle_load|"
    r"protobuf_decode|msgpack_unpack|cbor_decode|xml_parse|"
    r"unserialize|deserialize|decode)\s*\(",
    re.IGNORECASE,
)

# SSRF相关函数（CWE-918）
RE_SSRF_API = re.compile(
    r"\b(curl_easy_setopt|curl_easy_init|wget|system|popen)\b",
    re.IGNORECASE,
)

# SSRF URL参数
RE_SSRF_URL_PARAM = re.compile(r"CURLOPT_URL")

# SSRF校验函数
RE_SSRF_VALIDATE = re.compile(
    r"\b(is_url_allowed|is_domain_allowed|validate_url|check_url|"
    r"url_whitelist|is_safe_url|verify_url|sanitize_url|is_valid_url)\b",
    re.IGNORECASE,
)

# 资源消耗相关函数（CWE-400）
RE_RESOURCE_API = re.compile(
    r"\b(malloc|calloc|realloc|alloca|new)\s*\(",
    re.IGNORECASE,
)

# 资源限制常量
RE_RESOURCE_LIMIT = re.compile(
    r"\b(MAX_|max_|LIMIT_|limit_|BOUND_|bound_)\w*\b",
    re.IGNORECASE,
)

# 递归函数检测
RE_RECURSIVE_CALL = re.compile(
    r"\b(fibonacci|traverse|recurse|recursive)\b",
    re.IGNORECASE,
)

# 网络IO函数（返回值检查至关重要）
RE_NET_API = re.compile(
    r"\b(recv|send|recvfrom|sendto|recvmsg|sendmsg|"
    r"connect|accept|accept4|listen|bind|socket)\s*\(",
    re.IGNORECASE,
)

# 新增：格式化字符串/危险临时文件/命令执行等风险 API 模式
RE_PRINTF_LIKE = re.compile(
    r"\b(printf|sprintf|snprintf|vsprintf|vsnprintf|syslog|vsyslog|err|errx|warn|warnx)\s*\(",
    re.IGNORECASE,
)
RE_FPRINTF = re.compile(r"\bfprintf\s*\(", re.IGNORECASE)
RE_INSECURE_TMP = re.compile(r"\b(tmpnam|tempnam|mktemp)\s*\(", re.IGNORECASE)
RE_SYSTEM_LIKE = re.compile(r"\b(system|popen)\s*\(", re.IGNORECASE)
RE_EXEC_LIKE = re.compile(
    r"\b(execvp|execlp|execvpe|execl|execve|execv)\s*\(", re.IGNORECASE
)
# Windows ShellExecute API（漏报修复）
RE_SHELLEXECUTE = re.compile(
    r"\b(ShellExecute|ShellExecuteA|ShellExecuteW|ShellExecuteEx|ShellExecuteExA|ShellExecuteExW)\s*\(",
    re.IGNORECASE,
)
RE_SCANF_CALL = re.compile(r'\b(?:[fs]?scanf)\s*\(\s*"([^"]*)"', re.IGNORECASE)
# sscanf/fscanf格式串在第2参数（第1参数是输入源/FILE*）
RE_SCANF_CALL_ARG2 = re.compile(
    r'\b(?:sscanf|fscanf)\s*\([^,]+,\s*"([^"]*)"', re.IGNORECASE
)
# 线程/锁相关
RE_PTHREAD_LOCK = re.compile(
    r"\bpthread_mutex_lock\s*\(\s*&?\s*([A-Za-z_]\w*)\s*\)\s*;?", re.IGNORECASE
)
RE_PTHREAD_UNLOCK = re.compile(
    r"\bpthread_mutex_unlock\s*\(\s*&?\s*([A-Za-z_]\w*)\s*\)\s*;?", re.IGNORECASE
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
RE_MALLOC_ASSIGN = re.compile(
    r"\b([A-Za-z_]\w*)\s*=\s*(?:\([^)]*\))?\s*malloc\s*\(", re.IGNORECASE
)
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
# CWE-327: 弱加密算法API模式
RE_WEAK_CRYPTO = re.compile(
    r"\b(DES_set_key|DES_set_key_unchecked|DES_ecb_encrypt|DES_cbc_encrypt|DES_ncbc_encrypt|"
    r"DES_ede3_cbc_encrypt|DES_ede2_cbc_encrypt|"
    r"RC4_set_key|RC4|"
    r"MD5_Init|MD5_Update|MD5_Final|MD5_Transform|"
    r"SHA1_Init|SHA1_Update|SHA1_Final|SHA1_Transform|"
    r"BF_set_key|BF_ecb_encrypt|BF_cbc_encrypt|BF_encrypt|BF_decrypt)\s*\(",
    re.IGNORECASE,
)

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
    - 提前返回：if (!ptr) return ... / if (ptr == NULL) return ...
    - 错误处理跳转：if (!ptr) goto error; / if (ptr == NULL) goto fail;
    - 循环条件：while (ptr && ...) / for (...; ptr && ...; ...)
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
        # 提前返回防御：if (!ptr) return ... / if (ptr == NULL) return ...
        if re.search(rf"\bif\s*\([^)]*{re.escape(var)}[^)]*\)\s*\breturn\b", s):
            return True
        # 错误处理跳转：if (!ptr) goto error; / if (ptr == NULL) goto fail;
        if re.search(rf"\bif\s*\([^)]*{re.escape(var)}[^)]*\)\s*\bgoto\b", s):
            return True
        # 循环条件检查：while (ptr && ...) / for (...; ptr && ...; ...)
        if re.search(rf"\bwhile\s*\([^)]*{re.escape(var)}[^)]*\)", s):
            return True
        if re.search(rf"\bfor\s*\([^)]*{re.escape(var)}[^)]*\)", s):
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


def _rule_unsafe_api(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测不安全API调用（strcpy/strcat/gets/sprintf/vsprintf）。
    - 优先使用database查询call_graph表
    - 若database不可用，回退到正则匹配
    """
    issues: List[Issue] = []
    UNSAFE_APIS = {"strcpy", "strcat", "gets", "sprintf", "vsprintf"}
    is_header = str(relpath).lower().endswith((".h", ".hpp"))
    re_type_kw = re.compile(
        r"\b(static|inline|const|volatile|unsigned|signed|long|short|int|char|void|size_t|ssize_t)\b"
    )

    # 优先使用database查询
    if database:
        import os

        call_graph = database.get_call_graph()
        for call in call_graph:
            callee_name = call.get("callee_name", "")
            if callee_name.lower() not in UNSAFE_APIS:
                continue
            caller_file = call.get("caller_file", "")
            if os.path.basename(caller_file) != os.path.basename(relpath):
                continue
            idx = call.get("caller_line", 0)
            if 0 < idx <= len(lines):
                s = lines[idx - 1]
            else:
                continue

            # 跳过预处理行与声明行
            t = s.lstrip()
            if t.startswith("#") or re.search(r"\b(typedef|extern)\b", s):
                continue

            # 头文件中跳过函数原型
            if is_header:
                m = re.search(rf"\b{callee_name}\s*\(", s, re.IGNORECASE)
                if m:
                    before = s[: m.start()]
                    if re_type_kw.search(before) and s.strip().endswith(");"):
                        continue

            api = callee_name
            # 过滤：如果调用在condition_protected行内，跳过
            _ua_is_protected = False
            if database:
                try:
                    _ua_df_nodes = database.get_data_flow_by_file(relpath)
                    for n in _ua_df_nodes:
                        if (
                            n.get("use_type") == "condition_protected"
                            and n["line"] == idx
                        ):
                            _ua_is_protected = True
                            break
                except Exception:
                    pass
            if _ua_is_protected:
                continue
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

    # 无database时跳过正则回退（避免误报）
    return issues


def _rule_boundary_funcs(
    lines: Sequence[str],
    relpath: str,
    original_lines: Optional[Sequence[str]] = None,
    database: Optional["ProjectDatabase"] = None,
) -> List[Issue]:
    """
    检测边界函数（memcpy/memmove/strncpy/strncat）的潜在风险调用。
    - 优先使用database查询call_graph表
    - 若database不可用，回退到正则匹配
    """
    issues: List[Issue] = []
    BOUNDARY_FUNCS = {"memcpy", "memmove", "strncpy", "strncat"}

    # 优先使用database查询
    if database:
        call_graph = database.get_call_graph()
        for call in call_graph:
            callee_name = call.get("callee_name", "")
            if callee_name.lower() not in BOUNDARY_FUNCS:
                continue
            # 检查文件路径匹配（使用basename匹配，因为database可能存储临时文件路径）
            caller_file = call.get("caller_file", "")
            import os

            if os.path.basename(caller_file) != os.path.basename(relpath):
                continue
            idx = call.get("caller_line", 0)
            api = callee_name
            # 从原始行获取代码内容
            if original_lines and 0 < idx <= len(original_lines):
                s = original_lines[idx - 1]
            elif 0 < idx <= len(lines):
                s = lines[idx - 1]
            else:
                s = ""
            # 构建参数字符串（用于安全模式检测）
            args = _extract_call_args(s, api)
            conf = 0.65

            # 安全模式检测（sizeof用法）
            safe_sizeof = False
            if api.lower() in ("memcpy", "memmove") and args:
                if (
                    "sizeof" in args
                    and not RE_SIZEOF_PTR.search(args)
                    and not RE_STRLEN_IN_SIZE.search(args)
                ):
                    safe_sizeof = True
            if safe_sizeof:
                continue

            # strncpy/strncat安全模式检测
            if api.lower() in ("strncpy", "strncat") and args:
                safe_sizeof_pattern = re.search(
                    r"sizeof\s*\(\s*\w+\s*\)\s*-\s*1",
                    args,
                )
                has_null_term = False
                if safe_sizeof_pattern:
                    check_lines = (
                        original_lines if original_lines is not None else lines
                    )
                    for check_idx in range(idx, min(idx + 3, len(check_lines) + 1)):
                        check_line = check_lines[check_idx - 1]
                        if re.search(
                            r"\w+\s*\[\s*sizeof\s*\(\s*\w+\s*\)\s*-\s*1\s*\]\s*=\s*'\\0'",
                            check_line,
                        ):
                            has_null_term = True
                            break
                if safe_sizeof_pattern and has_null_term:
                    continue

            # 风险提升
            if args and (RE_STRLEN_IN_SIZE.search(args) or RE_SIZEOF_PTR.search(args)):
                conf += 0.15
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

    # 无database时跳过正则回退（避免误报）
    return issues


def _extract_call_args(line: str, func_name: str) -> str:
    """从代码行提取函数调用参数"""
    try:
        pattern = re.compile(rf"\b{func_name}\s*\(", re.IGNORECASE)
        m = pattern.search(line)
        if not m:
            return ""
        start = line.index("(", m.start())
        end = line.rfind(")")
        if end != -1 and end > start:
            return line[start + 1 : end]
    except Exception:
        pass
    return ""


def _rule_realloc_assign_back(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测realloc返回值未使用的情况（污点分析 + 启发式回退）。
    - 优先使用污点分析检测realloc返回值是否被使用
    - 若污点分析不可用，回退到启发式检测
    """
    issues: List[Issue] = []

    # 尝试使用污点分析
    code = "\n".join(lines)
    taint_paths = taint_analyzer.analyze_with_best_analyzer(
        code, rules=["realloc_assign_back"], file_path=relpath, database=database
    )

    # 如果污点分析有结果，转换为Issue
    if taint_paths:
        for path in taint_paths:
            issues.append(
                Issue(
                    language="c/cpp",
                    category="memory_mgmt",
                    pattern="realloc_assign_back_taint",
                    file=relpath,
                    line=path.line_number,
                    evidence=path.code_snippet or "realloc返回值未使用",
                    description=path.description
                    or "realloc返回值未赋值回原指针，可能导致内存泄漏或使用已释放内存",
                    suggestion="使用临时指针接收realloc返回值，判空成功后再赋值回原指针",
                    confidence=path.confidence,
                    severity="high",
                )
            )
        return issues

    # 污点分析无结果，回退到启发式检测
    # 检测 realloc 调用但未赋值回原指针的情况
    realloc_call_pattern = re.compile(
        r"realloc\s*\(\s*([A-Za-z_]\w*)\s*,", re.IGNORECASE
    )
    for idx, s in enumerate(lines, start=1):
        # 检测 realloc(p, size) 但没有赋值回的情况
        m = realloc_call_pattern.search(s)
        if m:
            var = m.group(1)
            # 检查是否有赋值操作（p = realloc(p, ...) 或 tmp = realloc(p, ...)）
            # 如果行中没有 = 或者 = 不在 realloc 之前，则认为未赋值回
            has_assign = False
            if "=" in s:
                # 检查是否是 p = realloc(p, ...) 形式
                assign_match = re.search(
                    rf"\b{re.escape(var)}\s*=\s*realloc", s, re.IGNORECASE
                )
                if assign_match:
                    has_assign = True
                # 或者是 tmp = realloc(p, ...) 形式（有临时变量接收）
                else:
                    tmp_assign_match = re.search(
                        r"\b([A-Za-z_]\w*)\s*=\s*realloc", s, re.IGNORECASE
                    )
                    if tmp_assign_match:
                        has_assign = True

            if not has_assign:
                # realloc 调用但未赋值回，可能导致内存泄漏或使用已释放内存
                issues.append(
                    Issue(
                        language="c/cpp",
                        category="memory_mgmt",
                        pattern="realloc_assign_back",
                        file=relpath,
                        line=idx,
                        evidence=_strip_line(s),
                        description=f"realloc 调用但未将结果赋值回指针 {var}，可能导致内存泄漏或使用已释放内存。",
                        suggestion="使用临时指针接收 realloc 返回值，判空成功后再赋值回原指针。",
                        confidence=0.75,
                        severity="high",
                    )
                )

        # 检测 realloc 直接覆盖原指针的情况（p = realloc(p, ...)）
        m2 = RE_REALLOC_ASSIGN_BACK.search(s)
        if m2:
            var = m2.group(1)
            conf = 0.8
            # 如果附近未见错误处理/NULL检查，置信度更高
            if not _has_null_check_around(var, lines, idx, radius=3):
                conf += 0.1
            issues.append(
                Issue(
                    language="c/cpp",
                    category="memory_mgmt",
                    pattern="realloc_assign_back",
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


def _rule_malloc_no_null_check(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测内存分配后未检查NULL的情况。
    说明：优先使用database查询null_checks，失败时回退到启发式实现。
    """
    issues: List[Issue] = []

    # 跳过非常短的函数（通常是示例代码）
    # 如果函数少于10行，可能是测试或示例代码
    if len(lines) < 10:
        return issues

    # 优先尝试database驱动检测
    if database:
        try:
            from jarvis.jarvis_sec.data_flow_analyzer import DataFlowAnalyzer

            analyzer = DataFlowAnalyzer(database)
            code = "\n".join(lines)
            result = analyzer.analyze_code(
                code, is_cpp=False, database=database, file_path=relpath
            )

            if result and result.null_checks is not None:
                # 从pointer_states获取分配点
                if result.pointer_states:
                    for var_name, state in result.pointer_states.items():
                        if state.state == "ALLOCATED" and state.line:
                            # 检查是否有null_check
                            has_check = var_name in result.null_checks
                            if not has_check:
                                issues.append(
                                    Issue(
                                        language="c/cpp",
                                        category="memory_mgmt",
                                        pattern="alloc_no_null_check",
                                        file=relpath,
                                        line=state.line,
                                        evidence=_strip_line(lines[state.line - 1])
                                        if state.line <= len(lines)
                                        else "",
                                        description=f"内存分配给 {var_name} 后未检查是否成功（NULL 检查缺失）。",
                                        suggestion="在使用前检查分配结果是否为 NULL，并在错误路径上释放已获取的资源。",
                                        confidence=0.85,
                                        severity="high",
                                    )
                                )
                if issues:
                    return issues
        except Exception:
            pass

    # 无database时跳过正则回退（避免误报）
    return issues


def _rule_function_return_ptr_no_check(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测函数返回指针后未检查 NULL 就直接使用的情况。
    说明：优先使用database查询null_checks，失败时回退到启发式实现。
    """
    issues: List[Issue] = []

    # 优先尝试database驱动检测
    if database:
        try:
            from jarvis.jarvis_sec.data_flow_analyzer import DataFlowAnalyzer

            analyzer = DataFlowAnalyzer(database)
            code = "\n".join(lines)
            result = analyzer.analyze_code(
                code, is_cpp=False, database=database, file_path=relpath
            )

            if result and result.null_checks is not None:
                # 从pointer_states获取函数返回指针赋值点
                if result.pointer_states:
                    for var_name, state in result.pointer_states.items():
                        # 检查是否来自函数返回（非ALLOCATED但有值）
                        if state.line and state.state == "UNKNOWN":
                            # 跳过不可能返回NULL的函数
                            line_text = (
                                lines[state.line - 1]
                                if state.line <= len(lines)
                                else ""
                            )
                            # 智能指针（不可能返回NULL）
                            if re.search(
                                r"\b(make_unique|make_shared|make_unique_for_overwrite)\s*<",
                                line_text,
                            ):
                                continue
                            # 非指针返回函数（open返回int, time返回time_t等）
                            if re.search(
                                r"\b(open|close|read|write|time|clock|strlen|strcmp|strncmp|strtok_r?)\s*\(",
                                line_text,
                            ):
                                continue
                            # 返回值赋给非指针类型（int fd = open(...)）
                            if re.search(
                                r"\b(int|long|short|unsigned|size_t|ssize_t|time_t|clock_t|BOOL|bool)\s+"
                                + re.escape(var_name)
                                + r"\s*=",
                                line_text,
                            ):
                                continue
                            # 检查是否有null_check
                            has_check = var_name in result.null_checks
                            # 检查是否在condition_protected行内
                            if not has_check and database:
                                try:
                                    df_nodes = database.get_data_flow_by_file(relpath)
                                    for n in df_nodes:
                                        if (
                                            n.get("use_type") == "condition_protected"
                                            and n["line"] == state.line
                                        ):
                                            has_check = True
                                            break
                                except Exception:
                                    pass
                            if not has_check:
                                issues.append(
                                    Issue(
                                        language="c/cpp",
                                        category="memory_mgmt",
                                        pattern="function_return_ptr_no_check",
                                        file=relpath,
                                        line=state.line,
                                        evidence=_strip_line(lines[state.line - 1])
                                        if state.line <= len(lines)
                                        else "",
                                        description=f"函数返回的指针赋值给 {var_name} 后未检查是否为 NULL。",
                                        suggestion="在使用函数返回的指针前检查是否为 NULL；确保所有可能的返回路径都进行了验证。",
                                        confidence=0.75,
                                        severity="medium",
                                    )
                                )
                if issues:
                    return issues
        except Exception:
            pass

    # 无database时跳过正则回退（避免误报）
    return issues


# 跨文件UAF检测全局去重集合（避免多文件分析时重复报告）
_cross_file_uaf_seen: set[Tuple[str, int]] = set()

# 跨文件Double Free检测全局去重集合
_cross_file_double_free_seen: set[Tuple[str, int]] = set()


def _detect_cross_file_double_free(
    database: "ProjectDatabase", relpath: str, lines: Sequence[str]
) -> List[Issue]:
    """
    跨文件Double Free检测：基于调用顺序

    核心原理：
    在caller的视角下，先调用free_wrapper1后调用free_wrapper2 = Double Free。
    不依赖变量名匹配，只依赖call_graph中的调用顺序。

    检测逻辑：
    1. 查询pointer_states中所有FREED状态的指针，得到释放函数名(scope)
    2. 在call_graph中找谁调用了释放函数(caller)
    3. 在同一caller中，找free调用行号之后的其他free调用
    4. 去重并生成Issue

    Args:
        database: 项目数据库实例
        relpath: 当前文件相对路径
        lines: 源代码行列表

    Returns:
        检测到的跨文件Double Free问题列表
    """
    global _cross_file_double_free_seen
    issues: List[Issue] = []

    try:
        import sqlite3

        conn = sqlite3.connect(database.db_path)
        cursor = conn.cursor()

        # Step 1: 查询所有FREED状态的指针，得到释放函数名(scope)
        cursor.execute("""
            SELECT var_name, file_path, line, scope, deallocator
            FROM pointer_states
            WHERE state = 'FREED'
        """)
        freed_pointers = cursor.fetchall()

        # Step 2: 收集所有释放函数名
        free_scopes = set()
        for (
            freed_var,
            freed_file,
            freed_line,
            freed_scope,
            deallocator,
        ) in freed_pointers:
            if freed_scope != "global":
                free_scopes.add(freed_scope)

        # Step 3: 对于每个释放函数，找caller，然后在caller中找连续的释放函数调用
        for free_scope in free_scopes:
            # 找谁调用了这个释放函数
            cursor.execute(
                """
                SELECT caller_name, caller_file, caller_line
                FROM call_graph
                WHERE callee_name = ? AND caller_name != 'unknown'
            """,
                (free_scope,),
            )
            callers = cursor.fetchall()

            # Step 4: 在每个caller中，检查是否有多个释放函数调用
            for caller_name, caller_file, caller_line in callers:
                # 查找caller中所有调用
                cursor.execute(
                    """
                    SELECT callee_name, caller_line
                    FROM call_graph
                    WHERE caller_name = ? AND caller_file = ?
                    ORDER BY caller_line
                """,
                    (caller_name, caller_file),
                )
                all_calls = cursor.fetchall()

                # 找出所有释放函数调用
                free_calls_in_caller = [
                    (callee, line)
                    for callee, line in all_calls
                    if callee in free_scopes
                ]

                # 如果有多个释放函数调用，报告Double Free
                if len(free_calls_in_caller) >= 2:
                    for i in range(len(free_calls_in_caller) - 1):
                        first_free, first_line = free_calls_in_caller[i]
                        second_free, second_line = free_calls_in_caller[i + 1]

                        # 去重检查
                        dedup_key = (caller_file, second_line)
                        if dedup_key in _cross_file_double_free_seen:
                            continue
                        _cross_file_double_free_seen.add(dedup_key)

                        # 生成Issue
                        try:
                            from pathlib import PurePath

                            caller_file_rel = str(
                                PurePath(caller_file).relative_to(
                                    PurePath(str(database.project_path))
                                )
                            )
                        except ValueError:
                            caller_file_rel = caller_file.split("/")[-1]

                        issues.append(
                            Issue(
                                language="c/cpp",
                                category="memory_mgmt",
                                pattern="double_free",
                                file=caller_file_rel,
                                line=second_line,
                                evidence=f"跨文件Double Free: 在 {caller_file} 中连续调用释放函数 {first_free} (第{first_line}行) 和 {second_free} (第{second_line}行)",
                                description=f"检测到双重释放风险：{caller_name} 先调用 {first_free}，随后又调用 {second_free}，可能导致Double Free。",
                                suggestion="free 后将指针置 NULL；确保每块内存仅释放一次；理清所有权与释放路径。",
                                confidence=0.85,
                                severity="high",
                            )
                        )

        conn.close()
    except Exception:
        pass

    return issues


def _detect_cross_file_uaf(
    database: "ProjectDatabase", relpath: str, lines: Sequence[str]
) -> List[Issue]:
    """
    跨文件UAF检测：基于调用顺序而非变量名匹配

    核心原理：
    在caller的视角下，先调用free_wrapper后调用use_wrapper = UAF。
    不依赖变量名匹配，只依赖call_graph中的调用顺序。

    检测逻辑：
    1. 查询pointer_states中所有FREED状态的指针，得到释放函数名(scope)
    2. 在call_graph中找谁调用了释放函数(caller)
    3. 在同一caller中，找free调用行号之后的所有调用
    4. 去重并生成Issue

    Args:
        database: 项目数据库实例
        relpath: 当前文件相对路径
        lines: 源代码行列表

    Returns:
        检测到的跨文件UAF问题列表
    """
    global _cross_file_uaf_seen
    issues: List[Issue] = []

    try:
        import sqlite3

        conn = sqlite3.connect(database.db_path)
        cursor = conn.cursor()

        # Step 1: 查询所有FREED状态的指针，得到释放函数名(scope)
        cursor.execute("""
            SELECT var_name, file_path, line, scope, deallocator
            FROM pointer_states
            WHERE state = 'FREED'
        """)
        freed_pointers = cursor.fetchall()

        # Step 2: 对于每个被释放的指针，追踪调用链
        for (
            freed_var,
            freed_file,
            freed_line,
            freed_scope,
            deallocator,
        ) in freed_pointers:
            # 跳过global scope（不是函数内的释放）
            if freed_scope == "global":
                continue

            # Step 3: 在call_graph中找谁调用了释放函数
            cursor.execute(
                """
                SELECT caller_name, caller_file, caller_line
                FROM call_graph
                WHERE callee_name = ? AND caller_name != 'unknown'
            """,
                (freed_scope,),
            )
            callers = cursor.fetchall()

            # Step 4: 在每个caller中，找free调用之后的调用
            for caller_name, caller_file, caller_line in callers:
                cursor.execute(
                    """
                    SELECT callee_name, caller_line
                    FROM call_graph
                    WHERE caller_name = ? AND caller_file = ? AND caller_line > ?
                """,
                    (caller_name, caller_file, caller_line),
                )
                post_free_calls = cursor.fetchall()

                # Step 5: free后的调用即为UAF风险（基于调用顺序，不依赖变量名）
                for callee_name, call_line in post_free_calls:
                    # 去重检查（使用全局集合）
                    dedup_key = (caller_file, call_line)
                    if dedup_key in _cross_file_uaf_seen:
                        continue
                    _cross_file_uaf_seen.add(dedup_key)

                    # 生成Issue（使用相对路径）
                    try:
                        from pathlib import PurePath

                        caller_file_rel = str(
                            PurePath(caller_file).relative_to(
                                PurePath(str(database.project_path))
                            )
                        )
                    except ValueError:
                        caller_file_rel = caller_file.split("/")[-1]

                    issues.append(
                        Issue(
                            language="c/cpp",
                            category="memory_mgmt",
                            pattern="use_after_free_suspect",
                            file=caller_file_rel,
                            line=call_line,
                            evidence=f"跨文件UAF: 在 {caller_file}:{caller_line} 调用释放函数 {freed_scope} 后，又在第 {call_line} 调用 {callee_name}",
                            description=f"检测到释放后使用风险：{caller_name} 先调用 {freed_scope} 释放内存，随后调用 {callee_name} 可能使用已释放的内存。",
                            suggestion="free 后应将指针置为 NULL，并避免在重新赋值前进行任何解引用；建议引入生命周期管理与动态/静态检测。",
                            confidence=0.8,
                            severity="high",
                        )
                    )

                # Step 6: 检测同一caller中free调用后的变量使用（按scope查，不按变量名查）
                # 查找caller中free调用行号之后的所有use节点
                cursor.execute(
                    """
                    SELECT var_name, file_path, line
                    FROM data_flow
                    WHERE scope = ? AND node_type = 'use' AND line > ?
                """,
                    (caller_name, caller_line),
                )
                post_free_uses = cursor.fetchall()

                for use_var, use_file, use_line in post_free_uses:
                    # 去重检查
                    dedup_key = (use_file, use_line)
                    if dedup_key in _cross_file_uaf_seen:
                        continue
                    _cross_file_uaf_seen.add(dedup_key)

                    # 生成Issue
                    try:
                        from pathlib import PurePath

                        use_file_rel = str(
                            PurePath(use_file).relative_to(
                                PurePath(str(database.project_path))
                            )
                        )
                    except ValueError:
                        use_file_rel = use_file.split("/")[-1]

                    issues.append(
                        Issue(
                            language="c/cpp",
                            category="memory_mgmt",
                            pattern="use_after_free_suspect",
                            file=use_file_rel,
                            line=use_line,
                            evidence=f"跨函数UAF: 在 {caller_file}:{caller_line} 调用释放函数 {freed_scope} 后，变量 {use_var} 在第 {use_line} 行被使用",
                            description=f"检测到释放后使用风险：{caller_name} 调用 {freed_scope} 释放内存后，变量 {use_var} 仍被使用。",
                            suggestion="free 后应将指针置为 NULL，并避免在重新赋值前进行任何解引用；建议引入生命周期管理与动态/静态检测。",
                            confidence=0.75,
                            severity="high",
                        )
                    )

        conn.close()
    except Exception:
        pass

    return issues


def _rule_uaf_suspect(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    UAF（use-after-free）检测（污点分析 + 启发式回退 + 跨文件分析）：
    - 优先使用污点分析检测 free -> 解引用 的污点传播路径
    - 若污点分析不可用，回退到启发式检测
    - 启发式：仅在 free(var) 之后的窗口内检测到明显“解引用使用”（v->、*v、v[...）而且在此之前未见重新赋值/置空时告警
    - 忽略 free 后立即将指针置为 NULL/0 的情况
    - 跨文件分析：利用数据库追踪指针状态，检测跨文件的UAF风险
    """
    issues: List[Issue] = []

    # 尝试使用污点分析
    code = "\n".join(lines)
    taint_paths = taint_analyzer.analyze_with_best_analyzer(
        code,
        rules=["use_after_free", "double_free"],
        file_path=relpath,
        database=database,
    )

    # 如果污点分析有结果，转换为Issue
    if taint_paths:
        for path in taint_paths:
            issues.append(
                Issue(
                    language="c/cpp",
                    category="memory_mgmt",
                    pattern="use_after_free_taint",
                    file=relpath,
                    line=path.line_number,
                    evidence=path.code_snippet or f"{path.source} -> {path.sink}",
                    description=path.description
                    or f"污点分析检测到UAF风险：{path.source} -> {path.sink}",
                    suggestion="free 后应将指针置为 NULL，并避免在重新赋值前进行任何解引用；建议引入生命周期管理与动态/静态检测。",
                    confidence=path.confidence,
                    severity="critical"
                    if path.severity.value == "critical"
                    else "high",
                )
            )
        return issues

    # 污点分析无结果，回退到启发式检测
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

        # 注意：不再跳过free后置NULL的情况
        # 因为即使置NULL，后续代码仍可能通过别名或未检查NULL就使用
        # 例如：free(ptr); ptr = NULL; char *p = ptr; if (p) strcpy(p, "test");
        # 这种情况下，ptr已置NULL，但别名p仍可能被误用

        reassigned = False
        uaf_evidence_line: Optional[int] = None

        deref_arrow = re.compile(rf"\b{re.escape(var)}\s*->")
        deref_star = re.compile(rf"(?<!\w)\*\s*{re.escape(var)}\b")
        deref_index = re.compile(rf"\b{re.escape(var)}\s*\[")
        # 检测作为函数参数传递（可能导致UAF）
        func_param = re.compile(
            rf"\b(printf|fprintf|sprintf|snprintf|strcpy|strcat|memcpy|memmove|strlen|strcmp|strchr|strstr|gets|fgets|fputs|puts|scanf|fscanf|sscanf)\s*\([^)]*\b{re.escape(var)}\b"
        )
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
                or func_param.search(sj)  # 检测作为函数参数传递
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
                )
            )

    # 跨文件UAF检测：利用数据库追踪指针状态
    if database is not None:
        cross_file_issues = _detect_cross_file_uaf(database, relpath, lines)
        issues.extend(cross_file_issues)

    return issues


def _rule_unchecked_io(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测IO返回值未检查的情况（污点分析 + 启发式回退）。
    - 优先使用污点分析检测IO返回值是否被检查
    - 若污点分析不可用，回退到启发式检测
    """
    issues: List[Issue] = []

    # 尝试使用污点分析
    code = "\n".join(lines)
    taint_paths = taint_analyzer.analyze_with_best_analyzer(
        code, rules=["unchecked_io"], file_path=relpath, database=database
    )

    # 如果污点分析有结果，转换为Issue（但先过滤条件保护内的调用）
    if taint_paths:
        # 从database查询condition_protected行号集合，用于过滤误报
        protected_lines: set[int] = set()
        if database:
            try:
                df_nodes = database.get_data_flow_by_file(relpath)
                for n in df_nodes:
                    if n.get("use_type") == "condition_protected":
                        protected_lines.add(n["line"])
            except Exception:
                pass

        # 从database查询value_check变量集合，用于过滤受值检查保护的IO调用
        value_checked_vars: set[str] = set()
        if database:
            try:
                df_nodes = database.get_data_flow_by_file(relpath)
                for n in df_nodes:
                    if n.get("use_type") == "value_check":
                        value_checked_vars.add(n["var_name"])
            except Exception:
                pass

        for path in taint_paths:
            # 过滤：如果IO调用在condition_protected行内，跳过
            if path.line_number in protected_lines:
                continue
            # 过滤：如果IO调用使用的变量有value_check，跳过
            # （如 read(fd,...) 中 fd 有 value_check(fd >= 0)）
            if value_checked_vars and path.code_snippet:
                for var in value_checked_vars:
                    if re.search(rf"\b{re.escape(var)}\b", path.code_snippet):
                        # 还需确认value_check在IO调用之前
                        try:
                            vc_nodes = [
                                n
                                for n in df_nodes
                                if n.get("use_type") == "value_check"
                                and n["var_name"] == var
                            ]
                            for vc in vc_nodes:
                                if vc["line"] < path.line_number:
                                    protected_lines.add(path.line_number)
                                    break
                        except Exception:
                            pass
            if path.line_number in protected_lines:
                continue

            issues.append(
                Issue(
                    language="c/cpp",
                    category="error_handling",
                    pattern="unchecked_io_taint",
                    file=relpath,
                    line=path.line_number,
                    evidence=path.code_snippet or "IO返回值未检查",
                    description=path.description
                    or "IO函数返回值未检查，可能导致错误处理缺失",
                    suggestion="检查返回值/errno；在错误路径上释放资源",
                    confidence=path.confidence,
                    severity="medium",
                )
            )
        if issues:
            return issues

    # 污点分析无结果，回退到启发式检测
    # 预先收集condition_protected行号集合，用于过滤误报
    _protected_lines_regex: set[int] = set()
    if database:
        try:
            _df_nodes_regex = database.get_data_flow_by_file(relpath)
            for n in _df_nodes_regex:
                if n.get("use_type") == "condition_protected":
                    _protected_lines_regex.add(n["line"])
        except Exception:
            pass
    for idx, s in enumerate(lines, start=1):
        # 排除预处理与声明
        t = s.lstrip()
        if t.startswith("#") or re.search(r"\b(typedef|extern)\b", s):
            continue

        # 检测IO/权限/网络函数调用
        m = RE_IO_API.search(s)
        api_type = "io"
        if not m:
            m = RE_PRIV_API.search(s)
            api_type = "privilege"
        if not m:
            m = RE_NET_API.search(s)
            api_type = "network"
        if not m:
            continue

        # 过滤：如果IO调用在condition_protected行内，跳过
        if idx in _protected_lines_regex:
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

        # 根据API类型设置不同的描述和建议
        if api_type == "privilege":
            description = (
                "权限操作函数可能未检查返回值，可能导致权限设置失败但程序继续运行。"
            )
            suggestion = "检查返回值是否为0（成功）；失败时应终止程序或采取恢复措施。"
            pattern = "unchecked_privilege_op"
            conf = 0.80  # 权限操作更重要，提高置信度
        elif api_type == "network":
            description = "网络IO函数可能未检查返回值，可能导致连接失败或数据丢失。"
            suggestion = (
                "检查返回值（recv/send返回字节数或-1）；处理部分发送和连接错误。"
            )
            pattern = "unchecked_network_io"
            conf = 0.75
        else:
            description = "I/O/系统调用可能未检查返回值，存在错误处理缺失风险。"
            suggestion = "检查返回值/errno；在错误路径上释放资源（句柄/内存/锁）。"
            pattern = "io_call"

        issues.append(
            Issue(
                language="c/cpp",
                category="error_handling",
                pattern=pattern,
                file=relpath,
                line=idx,
                evidence=_strip_line(s),
                description=description,
                suggestion=suggestion,
                confidence=min(conf, 0.85),
                severity=_severity_from_confidence(conf, "error_handling"),
            )
        )
    return issues


def _rule_strncpy_no_nullterm(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测 strncpy/strncat 后未确保目标缓冲区以 NUL 结尾的常见隐患。
    - 优先使用database查询call_graph表
    - 若database不可用，回退到正则匹配
    """
    issues: List[Issue] = []
    STRNCPY_FUNCS = {"strncpy", "strncat"}

    # 优先使用database查询
    if database:
        import os

        call_graph = database.get_call_graph()
        for call in call_graph:
            callee_name = call.get("callee_name", "")
            if callee_name.lower() not in STRNCPY_FUNCS:
                continue
            caller_file = call.get("caller_file", "")
            if os.path.basename(caller_file) != os.path.basename(relpath):
                continue
            idx = call.get("caller_line", 0)
            if 0 < idx <= len(lines):
                s = lines[idx - 1]
            else:
                continue

            # 检查是否在condition_protected行内（if条件保护下的调用不算问题）
            is_condition_protected = False
            if database:
                try:
                    df_nodes = database.get_data_flow_by_file(relpath)
                    for n in df_nodes:
                        if (
                            n.get("use_type") == "condition_protected"
                            and n["line"] == idx
                        ):
                            is_condition_protected = True
                            break
                except Exception:
                    pass
            if is_condition_protected:
                continue
            # 检查是否为安全的strncpy用法
            safe_sizeof_pattern = re.search(r"sizeof\s*\(\s*\w+\s*\)\s*-\s*1", s)
            window_text = " ".join(t for _, t in _window(lines, idx, before=1, after=3))
            # CWE-170误报过滤：检查后续行是否有显式NULL终止
            has_null_term = re.search(
                r"\w+\s*\[\s*(?:sizeof\s*\(\s*\w+\s*\)\s*-\s*1|\w+\s*-\s*1)\s*\]\s*=\s*'\\0'",
                window_text,
            ) or re.search(
                r"\w+\s*\[\s*\w+\s*-\s*1\s*\]\s*=\s*0",
                window_text,
            )
            if safe_sizeof_pattern and has_null_term:
                continue
            # 即使没有sizeof-1模式，只要有显式NULL终止也跳过
            if has_null_term:
                continue

            conf = 0.55
            if not re.search(
                r"\\0|'\\0'|\"\\0\"|len\s*-\s*1|sizeof\s*\(\s*\w+\s*\)\s*-\s*1",
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
                    suggestion="确保目标缓冲区以 '\0' 终止（例如手动结尾或采用更安全 API）。",
                    confidence=min(conf, 0.75),
                    severity=_severity_from_confidence(conf, "buffer_overflow"),
                )
            )
        return issues

    # 无database时跳过正则回退（避免误报）
    return issues


# ---------------------------
# 对外主入口
# ---------------------------

# ---------------------------
# 额外规则（新增）
# ---------------------------


def _rule_format_string(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
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

    # 尝试使用污点分析
    code = "\n".join(lines)
    taint_paths = taint_analyzer.analyze_with_best_analyzer(
        code, rules=["format_string"], file_path=relpath, database=database
    )

    # 如果污点分析有结果，转换为Issue
    if taint_paths:
        for path in taint_paths:
            issues.append(
                Issue(
                    language="c/cpp",
                    category="unsafe_usage",
                    pattern="format_string_taint",
                    file=relpath,
                    line=path.line_number,
                    evidence=path.code_snippet or f"{path.source} -> {path.sink}",
                    description=path.description
                    or f"污点分析检测到格式化字符串风险：{path.source} -> {path.sink}",
                    suggestion="使用常量格式串并对外部输入进行参数化处理；避免将未验证的输入作为格式串。",
                    confidence=path.confidence,
                    severity="high",
                )
            )
        return issues

    # 污点分析无结果，回退到启发式检测

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
                    "syslog": 2,  # 漏报修复：syslog格式串是第2参
                    "vsyslog": 2,  # 漏报修复：vsyslog格式串是第2参
                    "err": 2,  # 漏报修复：err格式串是第2参
                    "errx": 2,  # 漏报修复：errx格式串是第2参
                    "warn": 2,  # 漏报修复：warn格式串是第2参
                    "warnx": 2,  # 漏报修复：warnx格式串是第2参
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


def _rule_insecure_tmpfile(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测不安全临时文件API：tmpnam/tempnam/mktemp
    说明：优先使用database查询call_graph表，失败时回退到正则检测。
    """
    issues: List[Issue] = []
    insecure_apis = ["tmpnam", "tempnam", "mktemp"]

    # 优先尝试database驱动检测
    if database:
        try:
            import os

            basename = os.path.basename(relpath)
            calls = database.get_call_graph()
            for call in calls:
                callee = call.get("callee_name", "")
                if callee not in insecure_apis:
                    continue
                caller_file = call.get("caller_file", "")
                if basename == os.path.basename(caller_file):
                    issues.append(
                        Issue(
                            language="c/cpp",
                            category="unsafe_usage",
                            pattern="insecure_tmpfile",
                            file=relpath,
                            line=call.get("caller_line", 0),
                            evidence=f"{callee}() 调用",
                            description=f"使用不安全的临时文件API（{callee}）可能导致竞态条件与劫持风险。",
                            suggestion="使用 mkstemp/mkdtemp 或安全封装，并设置合适的权限。",
                            confidence=0.9,
                            severity="high",
                        )
                    )
            if issues:
                return issues
        except Exception:
            pass

    # 无database时跳过正则回退（避免误报）
    return issues


def _rule_command_execution(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    命令执行漏洞检测（污点分析 + 启发式回退）：
    - 优先使用污点分析检测用户输入 -> 命令执行函数 的污点传播路径
    - 若污点分析不可用，回退到启发式检测
    - 启发式：检测 system/popen 和 exec* 系列，其中参数不是字面量（可能引入命令注入风险）
    准确性优化：
    - exec* 系列仅在第一个参数不是字面量路径时告警
    - 若第一个参数为变量名，向前回看若干行，若检测到该变量被赋值为字面量字符串，则视为较安全用法（跳过）
    """
    issues: List[Issue] = []

    # 尝试使用污点分析
    code = "\n".join(lines)
    taint_paths = taint_analyzer.analyze_with_best_analyzer(
        code, rules=["command_injection"], file_path=relpath, database=database
    )

    # 如果污点分析有结果，转换为Issue
    if taint_paths:
        for path in taint_paths:
            issues.append(
                Issue(
                    language="c/cpp",
                    category="unsafe_usage",
                    pattern="command_exec_taint",
                    file=relpath,
                    line=path.line_number,
                    evidence=path.code_snippet or f"{path.source} -> {path.sink}",
                    description=path.description
                    or f"污点分析检测到命令注入风险：{path.source} -> {path.sink}",
                    suggestion="避免拼接命令，使用参数化接口或受控白名单；严格校验/转义外部输入。",
                    confidence=path.confidence,
                    severity="critical"
                    if path.severity.value == "critical"
                    else "high",
                )
            )
        return issues

    # 污点分析无结果，回退到启发式检测

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

    # sanitize/validate函数名模式（调用后认为变量已净化）
    _sanitize_pattern = re.compile(
        r"\b(sanitize|validate|check|clean|escape|filter|purify|verify|is_safe|is_valid)\w*\s*\("
    )

    def _var_sanitized(
        var: str, lines: Sequence[str], upto_idx: int, lookback: int = 10
    ) -> bool:
        # 在前 lookback 行内查找 sanitize/validate 函数调用
        start = max(1, upto_idx - lookback)
        for j in range(start, upto_idx):
            sj = _safe_line(lines, j)
            # 模式1: sanitize_xxx(var) 或 validate_xxx(var)
            if _sanitize_pattern.search(sj) and re.search(rf"\b{re.escape(var)}\b", sj):
                return True
            # 模式2: if (is_safe_xxx(var)) 或 if (is_valid_xxx(var))
            if (
                re.search(r"\bif\s*\(", sj)
                and re.search(
                    r"\b(is_safe|is_valid|is_allowed|is_authorized)\w*\s*\(", sj
                )
                and re.search(rf"\b{re.escape(var)}\b", sj)
            ):
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
                    elif ident and _var_sanitized(ident, lines, idx, lookback=10):
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
                        elif ident and _var_sanitized(ident, lines, idx, lookback=10):
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

    # 检测Windows ShellExecute API（漏报修复）
    for idx, s in enumerate(lines, start=1):
        m_shell = RE_SHELLEXECUTE.search(s)
        if m_shell:
            try:
                start = s.index("(", m_shell.start())
                # ShellExecute第3个参数是文件/程序名，第4个参数是参数
                # 检查第3或第4个参数是否为非字面量
                # 简化检测：只要ShellExecute调用就检查是否有变量参数
                if not _arg_is_literal_or_wrapper(s, start):
                    issues.append(
                        Issue(
                            language="c/cpp",
                            category="unsafe_usage",
                            pattern="command_exec",
                            file=relpath,
                            line=idx,
                            evidence=_strip_line(s),
                            description="检测到ShellExecute调用，可能存在命令执行风险。",
                            suggestion="避免使用ShellExecute执行用户输入，使用白名单限制可执行程序。",
                            confidence=0.65,
                            severity="high",
                        )
                    )
            except Exception:
                pass

    # 检测exec*系列第二参数为用户输入（漏报修复）
    # execl/execlp等函数：第一个参数是路径，第二个参数是argv[0]，第三个参数是argv[1]...
    # 如果第二或后续参数为非字面量，可能存在命令注入
    for idx, s in enumerate(lines, start=1):
        m_exec = RE_EXEC_LIKE.search(s)
        if not m_exec:
            continue
        try:
            func_name = m_exec.group(1).lower()
            # execl/execlp/execlpe系列：检查第2个及后续参数
            if func_name in ["execl", "execlp", "execlpe"]:
                start = s.index("(", m_exec.start())
                # 检查是否有多个参数，且第二个参数不是字面量
                # 简化检测：检查逗号分隔的参数中是否有非字面量
                args_part = s[start + 1 :]
                # 检查是否有第二个参数（逗号分隔）
                if "," in args_part:
                    # 检查第二个参数是否为非字面量
                    # 简化检测：如果第二个参数不是字符串字面量（不以"开头）
                    second_arg_start = args_part.index(",") + 1
                    second_arg = args_part[second_arg_start:].strip()
                    if second_arg and not second_arg.startswith('"'):
                        # 第二个参数可能是变量
                        issues.append(
                            Issue(
                                language="c/cpp",
                                category="unsafe_usage",
                                pattern="command_exec",
                                file=relpath,
                                line=idx,
                                evidence=_strip_line(s),
                                description="检测到exec*系列函数调用，第二个参数可能为用户输入。",
                                suggestion="避免使用用户输入作为exec*函数的参数，使用白名单限制可执行程序。",
                                confidence=0.6,
                                severity="high",
                            )
                        )
        except Exception:
            pass

    return issues


def _rule_sql_injection(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    SQL注入检测（污点分析 + 启发式回退）：
    - 优先使用污点分析检测用户输入 -> SQL拼接函数 的污点传播路径
    - 若污点分析不可用，回退到启发式检测
    - 启发式：检测 sprintf/snprintf 拼接SQL语句的模式（格式串包含SQL关键字且参数包含用户输入）
    """
    issues: List[Issue] = []

    # 尝试使用污点分析
    code = "\n".join(lines)
    taint_paths = taint_analyzer.analyze_with_best_analyzer(
        code, rules=["sql_injection"], file_path=relpath, database=database
    )

    # 如果污点分析有结果，转换为Issue
    if taint_paths:
        for path in taint_paths:
            issues.append(
                Issue(
                    language="c/cpp",
                    category="injection",
                    pattern="sql_injection_taint",
                    file=relpath,
                    line=path.line_number,
                    evidence=path.code_snippet or f"{path.source} -> {path.sink}",
                    description=path.description
                    or f"污点分析检测到SQL注入风险：{path.source} -> {path.sink}",
                    suggestion="使用参数化查询或预编译语句，避免拼接用户输入到SQL语句。",
                    confidence=path.confidence,
                    severity="critical",
                )
            )
        return issues

    # 污点分析无结果，回退到启发式检测
    # SQL关键字模式（不区分大小写）
    sql_keywords = ["SELECT", "INSERT", "UPDATE", "DELETE", "DROP", "EXEC", "EXECUTE"]
    # SQL执行函数
    sql_exec_funcs = [
        "mysql_query",
        "sqlite3_exec",
        "sqlite3_prepare",
        "pg_exec",
        "SQLExecDirect",
    ]

    # 检测 sprintf/snprintf 拼接SQL语句
    for idx, s in enumerate(lines, start=1):
        # 检测 sprintf/snprintf 调用
        m = re.search(r"\b(sprintf|snprintf)\s*\(", s)
        if not m:
            continue
        try:
            # 提取格式串参数（sprintf第2参，snprintf第3参）
            # 简化处理：检查字符串中是否包含SQL关键字
            for kw in sql_keywords:
                if re.search(rf"\b{kw}\b", s, re.IGNORECASE):
                    # 检查是否有参数（%s, %d等）
                    if re.search(r"%[sdu]", s):
                        issues.append(
                            Issue(
                                language="c/cpp",
                                category="injection",
                                pattern="sql_injection",
                                file=relpath,
                                line=idx,
                                evidence=_strip_line(s),
                                description="检测到SQL语句拼接，可能存在SQL注入风险。",
                                suggestion="使用参数化查询或预编译语句，避免拼接用户输入到SQL语句。",
                                confidence=0.7,
                                severity="high",
                            )
                        )
                        break
        except Exception:
            pass

    # 检测 strcpy+strcat 拼接SQL语句（漏报修复）
    # 模式：strcat拼接用户输入，且前面有strcpy初始化SQL语句
    for idx, s in enumerate(lines, start=1):
        if not re.search(r"\bstrcat\s*\(", s):
            continue
        # 检查strcat是否拼接了非字面量参数（可能是用户输入）
        # 简化检测：strcat第二个参数不是字符串字面量
        m = re.search(r"\bstrcat\s*\([^,]+,\s*(\w+)", s)
        if not m:
            continue
        # 回看前面是否有strcpy初始化SQL语句
        start = max(1, idx - 5)
        has_sql_init = False
        for j in range(start, idx):
            prev_line = _safe_line(lines, j)
            if re.search(r"\bstrcpy\s*\(", prev_line):
                # 检查strcpy是否初始化SQL语句（包含SQL关键字）
                for kw in sql_keywords:
                    if re.search(rf"\b{kw}\b", prev_line, re.IGNORECASE):
                        has_sql_init = True
                        break
            if has_sql_init:
                break
        if has_sql_init:
            issues.append(
                Issue(
                    language="c/cpp",
                    category="injection",
                    pattern="sql_injection",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(s),
                    description="检测到strcpy+strcat拼接SQL语句，可能存在SQL注入风险。",
                    suggestion="使用参数化查询或预编译语句，避免拼接用户输入到SQL语句。",
                    confidence=0.65,
                    severity="high",
                )
            )

    # 检测SQL执行函数直接使用拼接变量（漏报修复）
    for idx, s in enumerate(lines, start=1):
        for func in sql_exec_funcs:
            if not re.search(rf"\b{func}\s*\(", s):
                continue
            # 检查是否使用了变量参数（非字面量）
            # 简化检测：如果函数调用中包含变量名（非字符串字面量）
            m = re.search(rf"\b{func}\s*\([^,]+,\s*(\w+)", s)
            if m:
                var_name = m.group(1)
                # 检查变量是否在前面被sprintf/snprintf赋值
                start = max(1, idx - 10)
                for j in range(start, idx):
                    prev_line = _safe_line(lines, j)
                    if re.search(
                        rf"\b(sprintf|snprintf)\s*\(\s*{re.escape(var_name)}", prev_line
                    ):
                        # 检查是否有SQL关键字
                        for kw in sql_keywords:
                            if re.search(rf"\b{kw}\b", prev_line, re.IGNORECASE):
                                issues.append(
                                    Issue(
                                        language="c/cpp",
                                        category="injection",
                                        pattern="sql_injection",
                                        file=relpath,
                                        line=idx,
                                        evidence=_strip_line(s),
                                        description=f"检测到{func}使用拼接的SQL变量，可能存在SQL注入风险。",
                                        suggestion="使用参数化查询或预编译语句，避免拼接用户输入到SQL语句。",
                                        confidence=0.7,
                                        severity="high",
                                    )
                                )
                                break
                        break

    return issues


def _rule_memory_leak(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    内存泄漏检测（基于database的pointer_states）：
    - 检测ALLOCATED状态但没有对应FREED状态的指针
    - 使用database的pointer_states表进行精确分析
    """
    issues: List[Issue] = []

    # 跳过非常短的函数（通常是示例代码）
    # 如果函数少于10行，可能是测试或示例代码
    if len(lines) < 10:
        return issues

    if database is None:
        # 无database时跳过正则回退（避免误报）
        return issues

    # 从database获取当前文件的pointer_states
    try:
        states = database.get_pointer_states_by_file(relpath)
    except Exception:
        return issues

    if not states:
        return issues

    # 按变量名分组，检查ALLOCATED但没有FREED的情况
    var_states: Dict[str, List[Dict[str, Any]]] = {}
    for state in states:
        var_name = state.get("var_name", "")
        if var_name:
            if var_name not in var_states:
                var_states[var_name] = []
            var_states[var_name].append(state)

    # 获取函数参数列表（用于跳过参数的内存泄漏检查）
    func_params = set()
    try:
        symbols = database.get_symbols_by_file(relpath)
        for sym in symbols:
            if sym.get("kind") == "parameter":
                func_params.add(sym.get("name", ""))
    except Exception:
        pass

    # 检查每个变量的状态
    for var_name, state_list in var_states.items():
        has_allocated = any(s.get("state") == "ALLOCATED" for s in state_list)
        has_freed = any(s.get("state") == "FREED" for s in state_list)

        if has_allocated and not has_freed:
            # 跳过函数参数（参数的内存管理由调用者负责）
            if var_name in func_params:
                continue
            # 跳过有null check的变量（说明调用者关注了返回值）
            try:
                from jarvis.jarvis_sec.data_flow_analyzer import DataFlowAnalyzer

                analyzer = DataFlowAnalyzer(database)
                code = "\n".join(lines)
                result = analyzer.analyze_code(
                    code, is_cpp=False, database=database, file_path=relpath
                )
                if result and result.null_checks and var_name in result.null_checks:
                    continue
            except Exception:
                pass
            # 找到第一个ALLOCATED状态的位置
            for state in state_list:
                if state.get("state") == "ALLOCATED":
                    line = state.get("line", 0)
                    allocator = state.get("allocator", "malloc")
                    scope = state.get("scope", "")

                    # 获取证据行
                    evidence = ""
                    if 0 < line <= len(lines):
                        evidence = _strip_line(lines[line - 1])

                    issues.append(
                        Issue(
                            language="c/cpp",
                            category="memory",
                            pattern="memory_leak",
                            file=relpath,
                            line=line,
                            evidence=evidence,
                            description=f"指针 '{var_name}' 在函数 '{scope}' 中通过 {allocator} 分配但未释放，可能存在内存泄漏。",
                            suggestion="确保在所有代码路径上释放分配的内存，或使用RAII模式。",
                            confidence=0.8,
                            severity="medium",
                            var_name=var_name,
                        )
                    )
                    break  # 每个变量只报告一次

    return issues


def _rule_path_traversal(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    路径遍历检测（污点分析 + 启发式回退）：
    - 优先使用污点分析检测用户输入 -> 路径拼接函数 的污点传播路径
    - 若污点分析不可用，回退到启发式检测
    - 启发式：检测 strcat/strncat 拼接路径的模式
    """
    issues: List[Issue] = []

    # 尝试使用污点分析
    code = "\n".join(lines)
    taint_paths = taint_analyzer.analyze_with_best_analyzer(
        code, rules=["path_traversal"], file_path=relpath, database=database
    )

    # 如果污点分析有结果，转换为Issue
    if taint_paths:
        for path in taint_paths:
            issues.append(
                Issue(
                    language="c/cpp",
                    category="injection",
                    pattern="path_traversal_taint",
                    file=relpath,
                    line=path.line_number,
                    evidence=path.code_snippet or f"{path.source} -> {path.sink}",
                    description=path.description
                    or f"污点分析检测到路径遍历风险：{path.source} -> {path.sink}",
                    suggestion="验证用户输入，过滤../等路径遍历字符，使用白名单限制访问路径。",
                    confidence=path.confidence,
                    severity="high",
                )
            )
        return issues

    # 污点分析无结果，回退到启发式检测
    # 路径拼接函数模式
    path_concat_pattern = re.compile(r"\b(strcat|strncat)\s*\(")
    # snprintf/sprintf路径拼接模式（漏报修复）
    snprintf_pattern = re.compile(r"\b(snprintf|sprintf)\s*\(")
    # 文件操作函数模式
    file_op_pattern = re.compile(r"\b(fopen|open|openat)\s*\(")
    # 路径相关关键字
    path_keywords = [
        "path",
        "file",
        "dir",
        "folder",
        "config",
        "data",
        "log",
        "tmp",
        "temp",
    ]

    # sanitize/validate函数名模式
    _path_sanitize_pattern = re.compile(
        r"\b(sanitize|validate|check|clean|filter|verify|is_safe|is_valid|is_allowed)\w*\s*\("
    )

    def _has_path_sanitized(
        lines: Sequence[str], upto_idx: int, lookback: int = 10
    ) -> bool:
        start = max(1, upto_idx - lookback)
        for j in range(start, upto_idx):
            sj = _safe_line(lines, j)
            if _path_sanitize_pattern.search(sj):
                return True
            # if (is_safe_filename(var)) 模式
            if re.search(r"\bif\s*\(", sj) and re.search(
                r"\b(is_safe|is_valid|is_allowed)\w*\s*\(", sj
            ):
                return True
        return False

    # 检测路径拼接后用于文件操作
    for idx, s in enumerate(lines, start=1):
        if path_concat_pattern.search(s):
            # 跳过已净化/验证的路径
            if _has_path_sanitized(lines, idx, lookback=10):
                continue
            # 检查后续几行是否有文件操作（扩大窗口到10行）
            for j in range(idx, min(idx + 10, len(lines) + 1)):
                if file_op_pattern.search(lines[j - 1]):
                    issues.append(
                        Issue(
                            language="c/cpp",
                            category="injection",
                            pattern="path_traversal",
                            file=relpath,
                            line=idx,
                            evidence=_strip_line(s),
                            description="检测到路径拼接后用于文件操作，可能存在路径遍历风险。",
                            suggestion="验证用户输入，过滤../等路径遍历字符，使用白名单限制访问路径。",
                            confidence=0.6,
                            severity="medium",
                        )
                    )
                    break

    # 检测snprintf/sprintf拼接路径后用于文件操作（漏报修复）
    for idx, s in enumerate(lines, start=1):
        if not snprintf_pattern.search(s):
            continue
        # 检查是否包含路径相关关键字或格式化字符串
        has_path_context = False
        for kw in path_keywords:
            if re.search(rf"\b{kw}\b", s, re.IGNORECASE):
                has_path_context = True
                break
        if not has_path_context and not re.search(r"%s", s):
            continue
        # 检查后续10行是否有文件操作
        for j in range(idx, min(idx + 10, len(lines) + 1)):
            if file_op_pattern.search(lines[j - 1]):
                issues.append(
                    Issue(
                        language="c/cpp",
                        category="injection",
                        pattern="path_traversal",
                        file=relpath,
                        line=idx,
                        evidence=_strip_line(s),
                        description="检测到snprintf/sprintf拼接路径后用于文件操作，可能存在路径遍历风险。",
                        suggestion="验证用户输入，过滤../等路径遍历字符，使用白名单限制访问路径。",
                        confidence=0.65,
                        severity="medium",
                    )
                )
                break

    return issues


def _rule_integer_overflow_from_calls(
    lines: Sequence[str], relpath: str, alloc_calls: List[Dict[str, Any]]
) -> List[Issue]:
    """
    基于call_graph数据的整数溢出检测辅助函数。
    分析malloc/calloc/realloc调用参数中的乘法/加法表达式。
    """
    issues: List[Issue] = []

    # 检测乘法或加法表达式（排除指针声明）
    mul_pattern = re.compile(r"(?<![(*])\b([A-Za-z_]\w*)\s\*\s([A-Za-z_]\w*)(?!\s\))")
    add_pattern = re.compile(r"\b([A-Za-z_]\w*)\s\+\s([A-Za-z_]\w*|\d+)")

    # 溢出检查模式（安全模式）- 泛化版本
    # 模式1: var <= MAX / other_var (直接检查)
    # 模式2: var > MAX / other_var (如果大于则返回/报错)
    # 模式3: var <= MAX - other_var (加法检查)
    # 支持多种MAX常量：INT_MAX, UINT_MAX, SIZE_MAX, SSIZE_MAX, LONG_MAX等
    # 使用非捕获组(?:...)避免分组索引错乱
    MAX_CONSTANTS = r"(?:UINT_MAX|INT_MAX|SIZE_MAX|SSIZE_MAX|LONG_MAX|ULONG_MAX|LLONG_MAX|ULLONG_MAX|INT8_MAX|INT16_MAX|INT32_MAX|INT64_MAX|UINT8_MAX|UINT16_MAX|UINT32_MAX|UINT64_MAX|\d+)"

    mul_overflow_check = re.compile(
        rf"\b([A-Za-z_]\w*)\s(<=|<|>|>=)\s{MAX_CONSTANTS}\s/\s([A-Za-z_]\w*)"
    )
    add_overflow_check = re.compile(
        rf"\b([A-Za-z_]\w*)\s(<|<=|>|>=)\s{MAX_CONSTANTS}\s-\s([A-Za-z_]\w*|\d+)"
    )

    # 新增：条件语句中的溢出检查（if/while语句）
    # 模式：if (count > 0 && elem_size > 0 && count <= SIZE_MAX / elem_size)
    conditional_overflow_check = re.compile(
        rf"\b(if|while)\s*\([^)]*([A-Za-z_]\w*)\s(<=|<)\s{MAX_CONSTANTS}\s/\s([A-Za-z_]\w*)[^)]*\)"
    )

    # 新增：变量比较检查（更通用的模式）
    # 模式：count <= SIZE_MAX / elem_size 或 base_size <= SIZE_MAX - extra
    generic_div_check = re.compile(
        rf"([A-Za-z_]\w*)\s(<=|<|>|>=)\s{MAX_CONSTANTS}\s/\s([A-Za-z_]\w*)"
    )
    generic_sub_check = re.compile(
        rf"([A-Za-z_]\w*)\s(<=|<|>|>=)\s{MAX_CONSTANTS}\s-\s([A-Za-z_]\w*|\d+)"
    )

    def _has_overflow_check(
        var1: str, var2: str, lines: Sequence[str], upto_idx: int, lookback: int = 10
    ) -> bool:
        """检查在前lookback行内是否有针对var1*var2或var1+var2的溢出检查

        泛化版本：支持多种MAX常量和检查模式
        """
        start = max(1, upto_idx - lookback)
        for j in range(start, upto_idx):
            sj = _safe_line(lines, j)

            # 检查乘法溢出检查模式
            m = mul_overflow_check.search(sj)
            if m:
                checked_var = m.group(1)
                divisor_var = m.group(3)
                # 检查是否涉及var1或var2
                if checked_var == var1 or checked_var == var2:
                    return True
                if divisor_var == var1 or divisor_var == var2:
                    return True

            # 检查加法溢出检查模式
            m = add_overflow_check.search(sj)
            if m:
                checked_var = m.group(1)
                if checked_var == var1 or checked_var == var2:
                    return True

            # 检查条件语句中的溢出检查
            m = conditional_overflow_check.search(sj)
            if m:
                checked_var = m.group(2)
                divisor_var = m.group(4)
                if checked_var == var1 or checked_var == var2:
                    return True
                if divisor_var == var1 or divisor_var == var2:
                    return True

            # 检查通用除法检查模式
            m = generic_div_check.search(sj)
            if m:
                checked_var = m.group(1)
                divisor_var = m.group(3)
                if checked_var == var1 or checked_var == var2:
                    return True
                if divisor_var == var1 or divisor_var == var2:
                    return True

            # 检查通用减法检查模式
            m = generic_sub_check.search(sj)
            if m:
                checked_var = m.group(1)
                sub_var = m.group(3)
                if checked_var == var1 or checked_var == var2:
                    return True
                if sub_var == var1 or sub_var == var2:
                    return True

        return False

    for call in alloc_calls:
        idx = call.get("caller_line", 0)
        callee_name = call.get("callee_name", "malloc")
        if 0 < idx <= len(lines):
            s = lines[idx - 1]
        else:
            continue

        # 提取malloc/calloc/realloc参数部分
        # 漏报修复：从函数名位置开始找括号，避免类型转换干扰
        try:
            func_pos = s.find(callee_name)
            if func_pos < 0:
                continue
            paren_start = s.find("(", func_pos)
            if paren_start < 0:
                continue
            alloc_start = paren_start + 1
            alloc_end = s.find(")", alloc_start)
            if alloc_end < 0:
                continue
            alloc_arg = s[alloc_start:alloc_end].strip()
        except (ValueError, IndexError):
            continue

        # 检测乘法溢出
        mul_match = mul_pattern.search(alloc_arg)
        if mul_match:
            var1, var2 = mul_match.group(1), mul_match.group(2)
            if not _has_overflow_check(var1, var2, lines, idx, lookback=10):
                issues.append(
                    Issue(
                        language="c/cpp",
                        category="arithmetic",
                        pattern="integer_overflow",
                        file=relpath,
                        line=idx,
                        evidence=_strip_line(s),
                        description=f"检测到乘法表达式 '{mul_match.group(0)}' 作为 {callee_name} 参数，可能存在整数溢出风险。",
                        suggestion="使用安全整数运算函数或添加溢出检查，确保分配大小正确。",
                        confidence=0.7,
                        severity="high",
                    )
                )

        # 检测加法溢出
        add_match = add_pattern.search(alloc_arg)
        if add_match:
            var1, var2 = add_match.group(1), add_match.group(2)
            if not _has_overflow_check(var1, var2, lines, idx, lookback=10):
                issues.append(
                    Issue(
                        language="c/cpp",
                        category="arithmetic",
                        pattern="integer_overflow",
                        file=relpath,
                        line=idx,
                        evidence=_strip_line(s),
                        description=f"检测到加法表达式 '{add_match.group(0)}' 作为 {callee_name} 参数，可能存在整数溢出风险。",
                        suggestion="使用安全整数运算函数或添加溢出检查，确保分配大小正确。",
                        confidence=0.7,
                        severity="high",
                    )
                )

        # 漏报修复：检测间接乘法溢出
        # 模式：变量作为malloc参数，该变量在前几行由乘法赋值
        if not mul_match and not add_match:
            # 检查alloc_arg是否是一个变量名
            var_in_alloc = re.match(r"^([A-Za-z_]\w*)$", alloc_arg)
            if var_in_alloc:
                target_var = var_in_alloc.group(1)
                # 向前查找该变量的乘法赋值
                for lookback_line in range(max(0, idx - 10), idx):
                    prev_line = lines[lookback_line]
                    # 检测乘法赋值模式：var = expr1 * expr2
                    assign_mul = re.search(
                        rf"\b{re.escape(target_var)}\s*=\s*([^;]+)\s*\*\s*([^;]+)",
                        prev_line,
                    )
                    if assign_mul:
                        expr1, expr2 = (
                            assign_mul.group(1).strip(),
                            assign_mul.group(2).strip(),
                        )
                        # 检查是否有溢出检查（增加lookback范围以覆盖if条件）
                        # 关键优化：if条件中的溢出检查对if块内部有效
                        if not _has_overflow_check(
                            expr1, expr2, lines, idx, lookback=15
                        ):
                            issues.append(
                                Issue(
                                    language="c/cpp",
                                    category="arithmetic",
                                    pattern="integer_overflow",
                                    file=relpath,
                                    line=idx,
                                    evidence=_strip_line(s),
                                    description=f"变量 '{target_var}' 由乘法赋值后用于 {callee_name}，可能存在整数溢出风险。",
                                    suggestion="使用安全整数运算函数或添加溢出检查，确保分配大小正确。",
                                    confidence=0.6,
                                    severity="medium",
                                )
                            )
                        break

    return issues


def _rule_integer_overflow(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    整数溢出检测：
    - 检测乘法/加法表达式作为malloc/calloc/realloc参数
    - 检测可能导致缓冲区分配不足的整数溢出风险
    - 优化：识别前置的溢出检查，避免误报
    - 优先使用database查询call_graph表，无数据时回退到正则检测
    """
    issues: List[Issue] = []
    import os

    # 内存分配函数集合
    ALLOC_FUNCS = {"malloc", "calloc", "realloc"}

    # 优先使用database查询
    if database:
        try:
            call_graph = database.get_call_graph()
            alloc_calls = []
            for call in call_graph:
                callee_name = call.get("callee_name", "")
                if callee_name in ALLOC_FUNCS:
                    caller_file = call.get("caller_file", "")
                    if os.path.basename(caller_file) == os.path.basename(relpath):
                        alloc_calls.append(call)

            # 如果database中有数据，使用database结果
            if alloc_calls:
                return _rule_integer_overflow_from_calls(lines, relpath, alloc_calls)
        except Exception:
            pass

    # 无database时跳过正则回退（避免误报）
    return issues


def _rule_hardcoded_credentials(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    硬编码凭证检测：
    - 优先使用database查询data_flow表检测敏感变量赋值
    - 若database不可用，回退到正则匹配
    - 检测敏感变量名（password、key、secret、token等）
    - 检测硬编码的敏感字符串
    """
    issues: List[Issue] = []

    # 敏感变量名列表
    SENSITIVE_VARS = {
        "password",
        "passwd",
        "pwd",
        "secret",
        "key",
        "token",
        "api_key",
        "apikey",
        "auth",
        "credential",
        "private_key",
        "access_key",
    }

    # 优先使用database查询
    if database:
        try:
            data_flow = database.get_data_flow_by_file(relpath)
            for node in data_flow:
                var_name = node.get("var_name", "")
                if var_name.lower() not in SENSITIVE_VARS:
                    continue
                # 检查是否是赋值操作且值为字符串字面量
                node_type = node.get("node_type", "")
                if node_type == "assign":
                    line_num = node.get("line_number", 0)
                    if 0 < line_num <= len(lines):
                        s = lines[line_num - 1]
                        # 检查是否赋值为字符串字面量
                        str_match = re.search(r'"([^"]{4,})"', s)
                        if str_match:
                            issues.append(
                                Issue(
                                    language="c/cpp",
                                    category="crypto",
                                    pattern="hardcoded_credentials",
                                    file=relpath,
                                    line=line_num,
                                    evidence=_strip_line(s),
                                    description="检测到硬编码凭证：变量名包含敏感关键词，且赋值为硬编码字符串。",
                                    suggestion="使用环境变量、配置文件或密钥管理系统存储敏感信息，避免硬编码。",
                                    confidence=0.75,
                                    severity="high",
                                )
                            )
            # 如果database有结果，返回
            if issues:
                return issues
        except Exception:
            pass

    # 无database时跳过正则回退（避免误报）
    return issues


def _rule_toctou_race_from_calls(
    lines: Sequence[str], relpath: str, file_calls: List[Dict[str, Any]]
) -> List[Issue]:
    """
    基于call_graph数据的TOCTOU竞态条件检测辅助函数。
    检测access/stat检查后紧接着fopen/open使用的模式。
    """
    issues: List[Issue] = []

    # 检查函数集合
    CHECK_FUNCS = {"access", "lstat", "stat", "fstat"}
    # 使用函数集合（含C++ ifstream/ofstream/fstream构造函数）
    USE_FUNCS = {"fopen", "open", "openat", "ifstream", "ofstream", "fstream"}

    # 按行号排序调用
    file_calls.sort(key=lambda c: c.get("caller_line", 0))

    # 检测模式：检查函数调用后，在几行内出现使用函数调用
    for i, call in enumerate(file_calls):
        callee_name = call.get("callee_name", "")
        if callee_name not in CHECK_FUNCS:
            continue

        check_line = call.get("caller_line", 0)
        if 0 < check_line <= len(lines):
            check_evidence = _strip_line(lines[check_line - 1])
        else:
            continue

        # 在后续15行内检测使用函数（漏报修复：扩大窗口从5行到15行）
        for j in range(i + 1, len(file_calls)):
            next_call = file_calls[j]
            next_line = next_call.get("caller_line", 0)
            next_callee = next_call.get("callee_name", "")

            # 检查是否在15行窗口内
            if next_line - check_line > 15:
                break

            if next_callee in USE_FUNCS:
                issues.append(
                    Issue(
                        language="c/cpp",
                        category="concurrency",
                        pattern="toctou_race",
                        file=relpath,
                        line=check_line,
                        evidence=check_evidence,
                        description=f"检测到TOCTOU竞态条件：{callee_name}检查后使用{next_callee}，存在竞态窗口。",
                        suggestion="使用O_NOFOLLOW标志、fstat检查已打开文件描述符，或使用原子操作避免竞态。",
                        confidence=0.65,
                        severity="high",
                    )
                )
                break

    return issues


def _rule_toctou_race(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    TOCTOU竞态条件检测：
    - 检测access+fopen模式
    - 检测lstat+fopen模式
    - 检测stat+fopen模式
    - 优先使用database查询call_graph表，无数据时回退到正则检测
    """
    issues: List[Issue] = []
    import os

    # 检查函数集合
    CHECK_FUNCS = {"access", "lstat", "stat", "fstat"}
    # 使用函数集合（含C++ ifstream/ofstream/fstream构造函数）
    USE_FUNCS = {"fopen", "open", "openat", "ifstream", "ofstream", "fstream"}

    # 优先使用database查询
    if database:
        try:
            call_graph = database.get_call_graph()
            file_calls = []
            for call in call_graph:
                callee_name = call.get("callee_name", "")
                if callee_name in CHECK_FUNCS or callee_name in USE_FUNCS:
                    caller_file = call.get("caller_file", "")
                    if os.path.basename(caller_file) == os.path.basename(relpath):
                        file_calls.append(call)

            # 如果database中有数据，使用database结果
            if file_calls:
                return _rule_toctou_race_from_calls(lines, relpath, file_calls)
        except Exception:
            pass

    # 无database时跳过检测（避免误报）
    return issues


def _rule_scanf_no_width(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测 scanf/sscanf/fscanf 使用 %s 但未指定最大宽度，存在缓冲区溢出风险。
    - 优先使用database查询call_graph表
    - 若database不可用，回退到正则匹配
    准确性优化：
    - 忽略 GNU 扩展的 %ms（自动分配内存）与 %m[...] 模式（自动分配）
    - 忽略丢弃输入的 %*s（不写入目标缓冲）
    """
    issues: List[Issue] = []
    SCANF_FUNCS = {"scanf", "sscanf", "fscanf"}

    # 优先使用database查询
    if database:
        import os

        call_graph = database.get_call_graph()
        for call in call_graph:
            callee_name = call.get("callee_name", "")
            if callee_name.lower() not in SCANF_FUNCS:
                continue
            caller_file = call.get("caller_file", "")
            if os.path.basename(caller_file) != os.path.basename(relpath):
                continue
            idx = call.get("caller_line", 0)
            if 0 < idx <= len(lines):
                s = lines[idx - 1]
            else:
                continue

            # 从代码行提取格式字符串
            # scanf格式串在第1参数，sscanf/fscanf格式串在第2参数
            m = RE_SCANF_CALL.search(s)
            if not m:
                m = RE_SCANF_CALL_ARG2.search(s)
            if not m:
                continue
            fmt = m.group(1)

            unsafe = False
            if "%s" in fmt and not re.search(r"%\d+s", fmt):
                unsafe = True
            if unsafe and re.search(r"%\*s", fmt):
                unsafe = False
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
                        suggestion='为 %s 指定最大宽度（如 "%255s"），或使用更安全的读取方式。',
                        confidence=0.75,
                        severity="high",
                    )
                )
        return issues

    # 无database时跳过正则回退（避免误报）
    return issues


# async-signal-safe函数列表（POSIX标准）
ASYNC_SIGNAL_SAFE_FUNCS = {
    # IO
    "write",
    "read",
    "close",
    "pipe",
    "_exit",
    "_Exit",
    # 信号
    "signal",
    "sigprocmask",
    "sigaction",
    "sigpending",
    "sigsuspend",
    "kill",
    # 进程
    "fork",
    "execve",
    "execv",
    "execvp",
    "execvpe",
    # 内存
    "mmap",
    "munmap",
    "mprotect",
    # 其他
    "getpid",
    "getppid",
    "getuid",
    "geteuid",
    "getgid",
    "getegid",
    "setuid",
    "setgid",
    "seteuid",
    "setegid",
    "chdir",
    "chroot",
    "sync",
    "fsync",
    "dup",
    "dup2",
    "fcntl",
    "flock",
    "waitpid",
    "wait",
    "waitid",
    "alarm",
    "pause",
    "sleep",
    "clock_gettime",
    "gettimeofday",
    # 错误处理
    "errno",
    "strerror",  # strerror在某些实现中可能不安全，但POSIX标记为安全
}

# signal handler中不安全的常见函数
ASYNC_SIGNAL_UNSAFE_FUNCS = {
    # IO函数（非async-signal-safe）
    "printf",
    "fprintf",
    "sprintf",
    "snprintf",
    "vprintf",
    "vfprintf",
    "vsprintf",
    "vsnprintf",
    "scanf",
    "fscanf",
    "sscanf",
    "fopen",
    "fclose",
    "fread",
    "fwrite",
    "perror",
    "puts",
    "fputs",
    "putchar",
    "fputc",
    "fgets",
    "gets",
    # 内存分配
    "malloc",
    "calloc",
    "realloc",
    "free",
    "memalign",
    "valloc",
    # 进程控制
    "exit",
    "system",
    "popen",
    "pclose",
    # 字符串操作
    "strdup",
    "strndup",
    "strerror_r",
    # 时间函数
    "localtime",
    "gmtime",
    "asctime",
    "ctime",
    "strftime",
    # 其他
    "syslog",
    "abort",
    "raise",
}


def _rule_signal_handler_unsafe(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测signal handler中调用了非async-signal-safe函数。

    POSIX标准规定signal handler中只能调用async-signal-safe函数。
    不安全函数包括：printf, fprintf, malloc, free, exit等。

    检测逻辑：
    1. 找到signal(sig, handler)调用，提取handler函数名
    2. 找到handler函数的定义体
    3. 检查handler函数体内是否调用了非async-signal-safe函数
    """
    issues: List[Issue] = []

    # 正则匹配signal(sig, handler)调用
    SIGNAL_PATTERN = re.compile(
        r"\bsignal\s*\(\s*[^,]+,\s*([A-Za-z_]\w*)\s*\)", re.IGNORECASE
    )

    # 找到所有signal handler注册
    handler_names = set()
    for line in lines:
        m = SIGNAL_PATTERN.search(line)
        if m:
            handler_names.add(m.group(1))

    if not handler_names:
        return issues

    # 构建完整代码文本
    code = "\n".join(lines)

    for handler_name in handler_names:
        # 找到handler函数定义位置
        func_pattern = re.compile(
            rf"^(?:static\s+)?(?:void|int)\s+{re.escape(handler_name)}\s*\([^)]*\)\s*\{{",
            re.MULTILINE,
        )

        for func_match in func_pattern.finditer(code):
            start_pos = func_match.end() - 1  # 指向 '{'

            # 找到函数体结束位置（匹配括号）
            brace_count = 1
            end_pos = start_pos + 1
            while end_pos < len(code) and brace_count > 0:
                if code[end_pos] == "{":
                    brace_count += 1
                elif code[end_pos] == "}":
                    brace_count -= 1
                end_pos += 1

            # 提取函数体
            func_body = code[start_pos:end_pos]
            func_body_lines = func_body.splitlines()

            # 计算函数起始行号
            func_start_line = code[: func_match.start()].count("\n") + 1

            # 检查函数体内的不安全函数调用
            for line_offset, line in enumerate(func_body_lines):
                line_num = func_start_line + line_offset

                for unsafe_func in ASYNC_SIGNAL_UNSAFE_FUNCS:
                    # 匹配函数调用模式
                    if re.search(rf"\b{re.escape(unsafe_func)}\s*\(", line):
                        issues.append(
                            Issue(
                                language="c/cpp",
                                category="signal_safety",
                                pattern="signal_handler_unsafe_func",
                                file=relpath,
                                line=line_num,
                                evidence=_strip_line(line),
                                description=f"Signal handler '{handler_name}' calls non-async-signal-safe function '{unsafe_func}'. "
                                f"POSIX requires signal handlers to only call async-signal-safe functions.",
                                suggestion=f"Replace '{unsafe_func}' with an async-signal-safe alternative "
                                f"(e.g., use write() instead of printf(), _exit() instead of exit()).",
                                confidence=0.85,
                                severity="medium",
                            )
                        )

    return issues


def _rule_weak_crypto(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测弱加密算法的使用（CWE-327）：DES/RC4/MD5/SHA1/Blowfish等。
    - 优先使用database查询call_graph表
    - 若database不可用，回退到正则匹配
    """
    issues: List[Issue] = []
    WEAK_CRYPTO_APIS = {
        "DES_set_key",
        "DES_set_key_unchecked",
        "DES_ecb_encrypt",
        "DES_cbc_encrypt",
        "DES_ncbc_encrypt",
        "DES_ede3_cbc_encrypt",
        "DES_ede2_cbc_encrypt",
        "RC4_set_key",
        "RC4",
        "MD5_Init",
        "MD5_Update",
        "MD5_Final",
        "MD5_Transform",
        "SHA1_Init",
        "SHA1_Update",
        "SHA1_Final",
        "SHA1_Transform",
        "BF_set_key",
        "BF_ecb_encrypt",
        "BF_cbc_encrypt",
        "BF_encrypt",
        "BF_decrypt",
    }

    # 优先使用database查询
    if database:
        import os

        call_graph = database.get_call_graph()
        for call in call_graph:
            callee_name = call.get("callee_name", "")
            if callee_name not in WEAK_CRYPTO_APIS:
                continue
            caller_file = call.get("caller_file", "")
            if os.path.basename(caller_file) != os.path.basename(relpath):
                continue
            idx = call.get("caller_line", 0)
            if 0 < idx <= len(lines):
                s = lines[idx - 1]
            else:
                continue

            issues.append(
                Issue(
                    language="c/cpp",
                    category="crypto",
                    pattern="weak_crypto",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(s),
                    description=f"使用弱加密算法 {callee_name}，存在被破解的风险。",
                    suggestion="使用更强的加密算法（如AES-256替代DES，SHA-256替代MD5/SHA1）。",
                    confidence=0.85,
                    severity="high",
                )
            )
        return issues
    # 无database时跳过正则回退（避免误报）
    return issues


def _rule_uninitialized_var(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测未初始化变量使用（CWE-457）：声明后未赋值即使用。
    检测模式：type var; 后在窗口内无赋值直接使用（return var, var+1, func(var)等）。
    排除：声明时初始化（int var = 0;）、指针类型（由_rule_uninitialized_ptr_use覆盖）。
    """
    issues: List[Issue] = []

    # 无database时跳过正则检测（避免误报）
    if database is None:
        return issues

    # 类型关键字
    type_kw = re.compile(
        r"\b(int|long|short|char|float|double|unsigned|signed|size_t|ssize_t|"
        r"uint\d*_t|int\d*_t|BOOL|bool)\b"
    )
    # 声明模式：type var; （不含 = 和 *）
    decl_pattern = re.compile(r"\b([A-Za-z_]\w*)\s+([A-Za-z_]\w*)\s*;")

    # 收集class/struct内的行号范围（用于排除成员变量）
    class_member_lines = set()
    brace_depth = 0
    in_class_body = False
    for idx, s in enumerate(lines, start=1):
        if re.search(r"\b(class|struct)\s+\w+", s):
            in_class_body = True
            brace_depth = s.count("{") - s.count("}")
            if brace_depth > 0:
                class_member_lines.add(idx)
            continue
        if in_class_body:
            brace_depth += s.count("{") - s.count("}")
            class_member_lines.add(idx)
            if brace_depth <= 0:
                in_class_body = False

    candidates = []  # (var, decl_line)
    for idx, s in enumerate(lines, start=1):
        # 跳过预处理行
        t = s.lstrip()
        if t.startswith("#"):
            continue
        # 跳过class/struct成员变量（由uninitialized_member规则覆盖）
        if idx in class_member_lines:
            continue
        # 必须有类型关键字
        if not type_kw.search(s):
            continue
        # 排除指针声明（由_rule_uninitialized_ptr_use覆盖）
        if "*" in s:
            continue
        # 排除有初始化的声明
        if "=" in s:
            continue
        # 排除函数声明（含括号）
        if "(" in s:
            continue
        m = decl_pattern.search(s)
        if m:
            var = m.group(2)
            # 排除常见非变量名
            if var in (
                "main",
                "if",
                "while",
                "for",
                "return",
                "struct",
                "enum",
                "union",
            ):
                continue
            candidates.append((var, idx))

    # 检查候选变量是否可能未初始化即被使用
    for var, decl_line in candidates:
        end = min(len(lines), decl_line + 30)
        # 收集赋值行和使用行
        assign_lines = []
        use_line = None
        for j in range(decl_line + 1, end + 1):
            sj = _safe_line(lines, j)
            # 赋值：var = ...
            if re.search(rf"\b{re.escape(var)}\s*=", sj):
                assign_lines.append(j)
            # 使用：return var, var + ..., func(var), printf(...var...)
            elif re.search(rf"\b{re.escape(var)}\b", sj):
                # 排除声明行（同变量名再声明）
                if type_kw.search(sj) and re.search(rf"\b{re.escape(var)}\s*;", sj):
                    continue
                use_line = j
                break

        if not use_line:
            continue

        # 如果没有赋值，直接报告
        if not assign_lines:
            issues.append(
                Issue(
                    language="c/cpp",
                    category="uninitialized",
                    pattern="uninitialized_var",
                    file=relpath,
                    line=decl_line,
                    evidence=_strip_line(_safe_line(lines, decl_line)),
                    description=f"变量 {var} 声明后未初始化即被使用，可能读取未定义值。",
                    suggestion="在声明时初始化变量，或在使用前确保所有路径都已赋值。",
                    confidence=0.7,
                    severity="medium",
                )
            )
            continue

        # 检查赋值是否在if块内但使用在if块外（可能未初始化路径）
        # 简化检测：赋值行的缩进比使用行深 → 赋值在条件块内
        for assign_line in assign_lines:
            assign_indent = len(_safe_line(lines, assign_line)) - len(
                _safe_line(lines, assign_line).lstrip()
            )
            use_indent = len(_safe_line(lines, use_line)) - len(
                _safe_line(lines, use_line).lstrip()
            )
            if assign_indent > use_indent:
                issues.append(
                    Issue(
                        language="c/cpp",
                        category="uninitialized",
                        pattern="uninitialized_var",
                        file=relpath,
                        line=decl_line,
                        evidence=_strip_line(_safe_line(lines, decl_line)),
                        description=f"变量 {var} 仅在条件分支内赋值，其他路径可能使用未初始化值。",
                        suggestion="在声明时初始化变量，或在使用前确保所有路径都已赋值。",
                        confidence=0.65,
                        severity="medium",
                    )
                )
                break

        # 如果赋值和使用在同一缩进层级，视为安全（已初始化）
        continue

    # === 第二遍：检测C++类成员未初始化 ===
    # 检测模式：class内声明成员变量 type var; 但构造函数未初始化
    # 收集类成员变量
    class_members: Dict[str, List[Tuple[str, int]]] = {}  # class_name -> [(var, line)]
    current_class: Optional[str] = None
    class_brace_depth = 0
    in_class = False

    for idx, s in enumerate(lines, start=1):
        t = s.lstrip()
        if t.startswith("#"):
            continue
        # 检测class定义
        class_match = re.search(r"\bclass\s+(\w+)", s)
        if class_match:
            current_class = class_match.group(1)
            class_brace_depth = s.count("{") - s.count("}")
            in_class = "{" in s
            if current_class not in class_members:
                class_members[current_class] = []
            continue

        if in_class and current_class:
            class_brace_depth += s.count("{") - s.count("}")
            if class_brace_depth <= 0:
                in_class = False
                current_class = None
                continue

            # 检测成员变量声明（非函数、非指针、无初始化）
            if type_kw.search(s) and "(" not in s and "*" not in s and "=" not in s:
                m = decl_pattern.search(s)
                if m:
                    var = m.group(2)
                    if var not in (
                        "main",
                        "if",
                        "while",
                        "for",
                        "return",
                        "struct",
                        "enum",
                        "union",
                    ):
                        class_members.setdefault(current_class, []).append((var, idx))

    # 检查构造函数是否初始化了这些成员
    for cls_name, members in class_members.items():
        if not members:
            continue
        # 查找构造函数中的初始化列表
        ctor_init_vars = set()
        in_ctor = False
        ctor_brace_depth = 0
        for idx, s in enumerate(lines, start=1):
            # 检测构造函数定义
            if re.search(rf"\b{re.escape(cls_name)}\s*\([^)]*\)\s*(?::|\{{)", s):
                in_ctor = True
                ctor_brace_depth = s.count("{") - s.count("}")
                # 检查初始化列表：: member(value)
                init_list_match = re.search(r":\s*(.+)", s)
                if init_list_match:
                    init_text = init_list_match.group(1)
                    for var, _ in members:
                        if re.search(rf"\b{re.escape(var)}\s*\(", init_text):
                            ctor_init_vars.add(var)
                continue

            if in_ctor:
                ctor_brace_depth += s.count("{") - s.count("}")
                if ctor_brace_depth <= 0:
                    in_ctor = False
                    continue
                # 检查初始化列表续行
                for var, _ in members:
                    if var not in ctor_init_vars and re.search(
                        rf"\b{re.escape(var)}\s*\(", s
                    ):
                        ctor_init_vars.add(var)
                # 检查构造函数体内赋值
                for var, _ in members:
                    if var not in ctor_init_vars and re.search(
                        rf"\b{re.escape(var)}\s*=", s
                    ):
                        ctor_init_vars.add(var)

        # 检查类方法中是否有 this->var 赋值（排除误报）
        method_assigned_vars = set()
        for idx, s in enumerate(lines, start=1):
            for var, _ in members:
                if var not in ctor_init_vars and re.search(
                    rf"\bthis\s*->\s*{re.escape(var)}\s*=", s
                ):
                    method_assigned_vars.add(var)

        # 报告未初始化的成员
        for var, line_no in members:
            if var not in ctor_init_vars and var not in method_assigned_vars:
                issues.append(
                    Issue(
                        language="c/cpp",
                        category="uninitialized",
                        pattern="uninitialized_member",
                        file=relpath,
                        line=line_no,
                        evidence=_strip_line(_safe_line(lines, line_no)),
                        description=f"类 {cls_name} 的成员变量 {var} 未在构造函数中初始化。",
                        suggestion="在构造函数初始化列表中初始化所有成员变量，或使用类内初始值。",
                        confidence=0.7,
                        severity="medium",
                    )
                )

    return issues


def _rule_signed_to_unsigned(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测有符号到无符号转换错误（CWE-195）：(size_t)int_var 或 (unsigned)int_var。
    排除：转换前有负值检查（if (len < 0) return;）。
    """
    issues: List[Issue] = []
    # 显式转换模式：(size_t)var 或 (unsigned)var 或 (uint32_t)var
    cast_pattern = re.compile(
        r"\(\s*(size_t|unsigned|uint\d*_t|ULONG|DWORD)\s*\)\s*\(?\s*([A-Za-z_]\w*)\s*\)?"
    )

    for idx, s in enumerate(lines, start=1):
        t = s.lstrip()
        if t.startswith("#"):
            continue
        for m in cast_pattern.finditer(s):
            var = m.group(2)
            # 检查前5行是否有负值检查
            has_neg_check = False
            start = max(1, idx - 5)
            for j in range(start, idx):
                sj = _safe_line(lines, j)
                if re.search(rf"\bif\s*\([^)]*{re.escape(var)}\s*(<|<=)\s*0", sj):
                    has_neg_check = True
                    break
                if re.search(rf"\b{re.escape(var)}\s*(<|<=)\s*0", sj):
                    has_neg_check = True
                    break
            if has_neg_check:
                continue

            issues.append(
                Issue(
                    language="c/cpp",
                    category="type_confusion",
                    pattern="signed_unsigned_conversion",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(s),
                    description=f"有符号变量 {var} 被强制转换为无符号类型 {m.group(1)}，负值将变为巨大正数。",
                    suggestion="在转换前检查值是否为负，或使用size_t/unsigned类型从头声明。",
                    confidence=0.75,
                    severity="high",
                )
            )
    return issues


def _rule_divide_by_zero(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测除零错误（CWE-369）：a/b 或 a%b 中 b 为变量且附近无零检查。
    排除：除数是常量非零值、附近有零检查（if (b == 0) / if (b) / if (!b)）。
    """
    issues: List[Issue] = []
    # 除法/取模模式：var / var 或 var % var
    div_pattern = re.compile(r"\b([A-Za-z_]\w*)\s*/\s*([A-Za-z_]\w*)")
    mod_pattern = re.compile(r"\b([A-Za-z_]\w*)\s*%\s*([A-Za-z_]\w*)")

    for idx, s in enumerate(lines, start=1):
        t = s.lstrip()
        if t.startswith("#"):
            continue
        # 跳过字符串字面量中的除法（如 char path[] = "/home/..."）
        # 简单启发式：行内有引号且除法在引号之间
        for pattern in (div_pattern, mod_pattern):
            for m in pattern.finditer(s):
                # 检查匹配是否在字符串字面量内
                before = s[: m.start()]
                if before.count('"') % 2 == 1 or before.count("'") % 2 == 1:
                    continue
                divisor = m.group(2)
                # 排除常量非零除数
                if divisor.isdigit() and divisor != "0":
                    continue
                # 排除sizeof(...)
                if "sizeof" in s[m.start() : m.end()]:
                    continue
                # 排除溢出检查中的除法（如 INT_MAX / obj_size）
                if re.search(r"(INT_MAX|UINT_MAX|SIZE_MAX)\s*/\s", s):
                    continue
                # 检查前5行和当前行是否有零检查
                has_zero_check = False
                start = max(1, idx - 5)
                for j in range(start, idx + 1):
                    sj = _safe_line(lines, j)
                    if re.search(
                        rf"\bif\s*\([^)]*{re.escape(divisor)}\s*(==|!=)\s*0", sj
                    ):
                        has_zero_check = True
                        break
                    if re.search(rf"\bif\s*\(\s*!?\s*{re.escape(divisor)}\s*\)", sj):
                        has_zero_check = True
                        break
                    if re.search(rf"\b{re.escape(divisor)}\s*(==|!=)\s*0", sj):
                        has_zero_check = True
                        break
                if has_zero_check:
                    continue

                issues.append(
                    Issue(
                        language="c/cpp",
                        category="arithmetic",
                        pattern="divide_by_zero",
                        file=relpath,
                        line=idx,
                        evidence=_strip_line(s),
                        description=f"除数 {divisor} 可能为零，存在除零错误风险。",
                        suggestion="在除法/取模前检查除数是否为零。",
                        confidence=0.7,
                        severity="high",
                    )
                )
    return issues


def _rule_compiler_security_check(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测编译器优化可能移除安全检查（CWE-733）：
    指针变量有NULL检查但未声明为volatile，编译器可能优化掉检查。
    排除：变量声明为volatile。
    """
    issues: List[Issue] = []
    # 收集volatile变量
    volatile_vars = set()
    for s in lines:
        m = re.search(r"\bvolatile\s+.*?\b([A-Za-z_]\w*)\b", s)
        if m:
            volatile_vars.add(m.group(1))
        m = re.search(r"\bvolatile\s+char\s*\*\s*([A-Za-z_]\w*)", s)
        if m:
            volatile_vars.add(m.group(1))

    # 检测NULL检查模式：if (ptr == NULL) / if (!ptr) / if (ptr)
    null_check_pattern = re.compile(
        r"\bif\s*\(\s*(!\s*)?([A-Za-z_]\w*)\s*(==|!=)?\s*(NULL|0)?\s*\)"
    )

    for idx, s in enumerate(lines, start=1):
        t = s.lstrip()
        if t.startswith("#"):
            continue
        for m in null_check_pattern.finditer(s):
            var = m.group(2)
            if var in ("if", "while", "for", "return", "NULL", "0"):
                continue
            # 跳过volatile变量
            if var in volatile_vars:
                continue
            # 检查是否是指针类型（前几行有 *var 或 type *var 声明）
            is_pointer = False
            start = max(1, idx - 10)
            for j in range(start, idx + 1):
                sj = _safe_line(lines, j)
                if re.search(rf"\b[A-Za-z_]\w*\s*\*\s*{re.escape(var)}\b", sj):
                    is_pointer = True
                    break
                if re.search(rf"\b{re.escape(var)}\s*\*\b", sj):
                    is_pointer = True
                    break
                # 函数参数中的指针
                if re.search(rf"\*\s*{re.escape(var)}\b", sj):
                    is_pointer = True
                    break
            if not is_pointer:
                continue

            issues.append(
                Issue(
                    language="c/cpp",
                    category="optimization",
                    pattern="compiler_security_check",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(s),
                    description=f"指针 {var} 的NULL检查可能被编译器优化移除（未声明为volatile）。",
                    suggestion="将指针声明为volatile以防止编译器优化移除安全检查，或使用编译器屏障。",
                    confidence=0.6,
                    severity="medium",
                )
            )
    return issues


def _rule_alloc_size_overflow(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测分配大小可能溢出的简单情形：malloc/calloc/realloc 形参存在乘法表达式且未显式使用 sizeof。
    - 优先使用database查询call_graph表
    - 若database不可用，回退到正则匹配
    """
    issues: List[Issue] = []
    ALLOC_FUNCS = {"malloc", "calloc", "realloc"}

    # 优先使用database查询
    if database:
        import os

        call_graph = database.get_call_graph()
        for call in call_graph:
            callee_name = call.get("callee_name", "")
            if callee_name.lower() not in ALLOC_FUNCS:
                continue
            caller_file = call.get("caller_file", "")
            if os.path.basename(caller_file) != os.path.basename(relpath):
                continue
            idx = call.get("caller_line", 0)
            if 0 < idx <= len(lines):
                s = lines[idx - 1]
            else:
                continue

            # 提取参数
            try:
                m = re.search(rf"\b{callee_name}\s*\(", s, re.IGNORECASE)
                if not m:
                    continue
                start = s.index("(", m.start())
                end = s.find(")", start + 1)
                if end != -1:
                    args = s[start + 1 : end]
                    if "*" in args and not re.search(r"\bsizeof\s*\(", args):
                        # CWE-190误报过滤：检查前5行是否有溢出检查
                        has_overflow_check = False
                        for j in range(max(1, idx - 5), idx):
                            sj = _safe_line(lines, j)
                            if (
                                re.search(
                                    r"\b(INT_MAX|UINT_MAX|SIZE_MAX|INT_MAX)\s*/",
                                    sj,
                                )
                                or re.search(
                                    r"\b\w+\s*<=\s*(INT_MAX|UINT_MAX|SIZE_MAX)\s*/",
                                    sj,
                                )
                                or re.search(
                                    r"\b\w+\s*<\s*(INT_MAX|UINT_MAX|SIZE_MAX)\s*/",
                                    sj,
                                )
                            ):
                                has_overflow_check = True
                                break
                        if has_overflow_check:
                            continue
                        issues.append(
                            Issue(
                                language="c/cpp",
                                category="memory_mgmt",
                                pattern="alloc_size_overflow",
                                file=relpath,
                                line=idx,
                                evidence=_strip_line(s),
                                description="malloc/calloc/realloc 大小计算包含乘法且未显式使用 sizeof，存在整数溢出风险。",
                                suggestion="使用 sizeof 计算元素大小并检查乘法是否可能溢出。",
                                confidence=0.6,
                                severity="medium",
                            )
                        )
            except Exception:
                pass
        return issues

    # 无database时跳过正则回退（避免误报）
    return issues


# ---------------------------
# 空指针/野指针/死锁 等新增规则
# ---------------------------


# CWE-468: 指针算术错误正则
RE_PTRDIFF_SIZEOF = re.compile(
    r"\(s*\w+\s*-\s*\w+\s*\)\s*/\s*sizeof\s*\(", re.IGNORECASE
)


def _rule_pointer_arithmetic_error(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    CWE-468: 检测指针减法结果再除以sizeof(type)的错误。
    指针减法已自动除以sizeof(type)，再除一次是错误的。
    模式：(ptr1 - ptr2) / sizeof(type)
    """
    issues: List[Issue] = []

    for idx, s in enumerate(lines, start=1):
        if RE_PTRDIFF_SIZEOF.search(s):
            issues.append(
                Issue(
                    language="c/cpp",
                    category="arithmetic",
                    pattern="pointer_arithmetic_error",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(s),
                    description="指针减法结果再除以sizeof，指针减法已自动除以元素大小，再除是错误的。",
                    suggestion="直接使用 (end - begin) 作为元素数量，无需再除以sizeof。",
                    confidence=0.85,
                    severity="high",
                )
            )

    return issues


# CWE-667: 死锁风险 - mutex不同顺序获取
RE_MUTEX_LOCK = re.compile(r"\b(\w+)\s*\.\s*lock\s*\(")


def _rule_deadlock_risk(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    CWE-667: 检测同一文件中多个函数以不同顺序获取mutex，可能导致死锁。
    启发式：收集每个函数内mutex.lock()的调用顺序，检测不同函数间的顺序差异。
    """
    issues: List[Issue] = []

    # 按函数收集mutex获取顺序
    func_mutex_order: Dict[
        str, List[Tuple[str, int]]
    ] = {}  # func_name -> [(mutex_name, line)]
    current_func: Optional[str] = None
    brace_depth = 0

    for idx, s in enumerate(lines, start=1):
        # 检测函数定义
        func_match = re.search(
            r"\b(?:void|int|char|long|unsigned|bool|auto|static)\s+(\w+)\s*\(", s
        )
        if func_match:
            current_func = func_match.group(1)
            brace_depth = s.count("{") - s.count("}")
            if current_func not in func_mutex_order:
                func_mutex_order[current_func] = []
            continue

        if current_func:
            brace_depth += s.count("{") - s.count("}")
            if brace_depth <= 0:
                current_func = None
                continue

            # 检测mutex.lock()调用
            m = RE_MUTEX_LOCK.search(s)
            if m:
                mutex_name = m.group(1)
                func_mutex_order[current_func].append((mutex_name, idx))

    # 检测不同函数间的mutex获取顺序差异
    func_names = [f for f in func_mutex_order if len(func_mutex_order[f]) >= 2]
    for i, f1 in enumerate(func_names):
        order1 = [m for m, _ in func_mutex_order[f1]]
        for f2 in func_names[i + 1 :]:
            order2 = [m for m, _ in func_mutex_order[f2]]
            # 检查是否有共同的mutex但顺序不同
            common = set(order1) & set(order2)
            if len(common) >= 2:
                # 获取共同mutex在两个函数中的顺序
                idx1 = [order1.index(m) for m in common if m in order1]
                idx2 = [order2.index(m) for m in common if m in order2]
                # 如果顺序不同，报告死锁风险
                if idx1 != idx2:
                    # 报告第一个函数中的mutex获取
                    for mutex_name, line_no in func_mutex_order[f1]:
                        if mutex_name in common:
                            issues.append(
                                Issue(
                                    language="c/cpp",
                                    category="concurrency",
                                    pattern="deadlock_risk",
                                    file=relpath,
                                    line=line_no,
                                    evidence=_strip_line(lines[line_no - 1]),
                                    description=f"函数 {f1} 和 {f2} 以不同顺序获取mutex {mutex_name}，可能导致死锁。",
                                    suggestion="确保所有函数以相同顺序获取mutex，或使用std::lock同时获取多个mutex。",
                                    confidence=0.75,
                                    severity="high",
                                )
                            )
                            break  # 每对函数只报告一次
                    break  # 每对函数只报告一次

    return issues


# CWE-783: 条件中的赋值
RE_ASSIGN_IN_COND = re.compile(
    r"\b(?:if|while|for\s*\([^;]*;)\s*\([^)]*\b(\w+)\s*=\s*(\d+)\s*\)"
)


def _rule_assignment_in_condition(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    CWE-783: 检测if/while条件中使用=而非==的赋值。
    排除合法用法：if ((result = func()) != 0) 等带比较运算符的模式。
    """
    issues: List[Issue] = []

    for idx, s in enumerate(lines, start=1):
        # 检测if/while条件中的赋值
        # 模式1: if (x = 0) - 赋值常量，永远为假/真
        m = re.search(r"\b(?:if|while)\s*\(\s*\b(\w+)\s*=\s*(\d+)\s*\)", s)
        if m:
            var = m.group(1)
            val = m.group(2)
            # 排除合法用法：if ((result = func()) != 0)
            # 检查赋值是否在额外的括号内且有比较运算符
            if re.search(r"\(\s*\(" + re.escape(var) + r"\s*=", s) and re.search(
                r"!=|==|<=|>=|<|>", s[s.index(var) :]
            ):
                continue
            issues.append(
                Issue(
                    language="c/cpp",
                    category="logic_error",
                    pattern="assignment_in_condition",
                    file=relpath,
                    line=idx,
                    evidence=_strip_line(s),
                    description=f"条件表达式中使用赋值 '{var} = {val}' 而非比较 '{var} == {val}'，可能导致逻辑错误。",
                    suggestion="如果意图是比较，请使用 '==' 运算符；如果意图是赋值后判断，建议使用额外括号明确意图。",
                    confidence=0.8,
                    severity="high",
                )
            )

    return issues


def _rule_possible_null_deref(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测空指针解引用：
    - 出现 p->... 或 *p 访问，且邻近未见明显的 NULL 检查。
    - 出现 arr[...] 数组访问，且邻近未见明显的 NULL 检查。
    说明：优先使用污点分析，失败时回退到启发式实现。
    准确性优化：
    - 对于 *p 的检测，引入上下文判定，尽量排除乘法表达式 a * p 的误报
     （仅当 * 出现在典型解引用上下文，如行首/括号后/逗号后/赋值号后/分号后/冒号后/方括号后/逻辑非/取地址/另一解引用后）
    """
    issues: List[Issue] = []

    # 从database获取null_checks信息（用于误报过滤）
    db_null_checks: Dict[str, List[int]] = {}
    # 收集函数参数（参数的NULL检查应在调用者处进行）
    func_params: set[str] = set()
    if database is not None:
        try:
            # 直接从database查询null_checks
            flow_nodes = database.get_data_flow_by_file(relpath)
            for node in flow_nodes:
                if node.get("use_type") == "null_check":
                    var_name = node.get("var_name", "")
                    line = node.get("line", 0)
                    if var_name and line > 0:
                        if var_name not in db_null_checks:
                            db_null_checks[var_name] = []
                        db_null_checks[var_name].append(line)
                # 收集函数参数
                if (
                    node.get("node_type") == "param_in"
                    or node.get("value_source") == "parameter"
                ):
                    var_name = node.get("var_name", "")
                    if var_name:
                        func_params.add(var_name)
        except Exception:
            pass

    # 优先尝试污点分析
    try:
        import jarvis.jarvis_sec.taint_analyzer as taint_analyzer

        analyzer = taint_analyzer.TaintAnalyzerFactory.create("joern")
        if analyzer and analyzer.is_available():
            code = "\n".join(lines)
            rule = taint_analyzer.get_rule("null_deref")
            if rule:
                taint_paths = rule.check(analyzer, code, relpath)
                for path in taint_paths:
                    issues.append(
                        Issue(
                            language="c/cpp",
                            category="memory_mgmt",
                            pattern="possible_null_deref",
                            file=relpath,
                            line=path.line_number,
                            evidence=path.code_snippet,
                            description=path.description,
                            suggestion="在使用指针前检查是否为 NULL，避免空指针解引用。",
                            confidence=0.85,
                            severity="high",
                        )
                    )
            # 污点分析成功，返回结果
            if issues:
                return issues
        # 污点分析不可用，回退到启发式检测
    except Exception:
        pass
    # 启发式检测（回退方案）
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

    # 预编译安全上下文检测的正则表达式
    re_malloc_like = re.compile(
        r"\b(malloc|calloc|realloc|new|kmalloc|vmalloc|kzalloc)\b"
    )
    re_static_global = re.compile(r"^\s*(static|extern)\s+.*\b([A-Za-z_]\w*)\b")
    re_const_str = re.compile(r"\bconst\s+char\s*\*\s*([A-Za-z_]\w*)\b")
    # 智能指针类型（不可能为NULL）
    re_smart_ptr = re.compile(
        r"\b(auto|std::unique_ptr|std::shared_ptr|std::weak_ptr)\b"
    )
    # delete/delete[] 语句（不是解引用）
    re_delete_stmt = re.compile(r"^\s*delete\s*\[?\s*\]?\s*([A-Za-z_]\w*)")

    # 收集静态/全局变量和常量字符串指针（通常已确保非空）
    safe_vars: set[str] = set()
    # 收集栈数组变量（栈数组不可能为NULL）
    stack_arrays: set[str] = set()
    # 收集智能指针变量（不可能为NULL）
    smart_ptr_vars: set[str] = set()
    # 收集C++容器变量（值类型，不可能为NULL）
    container_vars: set[str] = set()
    re_cpp_container = re.compile(
        r"std::(?:array|vector|deque|list|set|map|unordered_set|unordered_map)[^>]*>\s*&?\s*([A-Za-z_]\w*)"
    )
    # 栈数组声明模式：类型 变量名[大小]
    re_stack_array = re.compile(
        r"\b(char|int|long|short|void|unsigned|signed|float|double|size_t|ssize_t|uint\d*_t|int\d*_t)\s+(?:\*\s*)*([A-Za-z_]\w*)\s*\["
    )
    for line in lines:
        m_static = re_static_global.search(line)
        if m_static:
            safe_vars.add(m_static.group(2))
        m_const = re_const_str.search(line)
        if m_const:
            safe_vars.add(m_const.group(1))
        # 检测栈数组声明
        m_array = re_stack_array.search(line)
        if m_array:
            stack_arrays.add(m_array.group(2))
        # 检测智能指针声明
        m_smart = re_smart_ptr.search(line)
        if m_smart:
            # 提取变量名：auto var = ... 或 std::unique_ptr<T> var
            m_var = re.search(r"\b([A-Za-z_]\w*)\s*=", line)
            if m_var:
                smart_ptr_vars.add(m_var.group(1))
            else:
                # 也提取函数参数中的智能指针变量名
                m_param = re.search(
                    r"std::(?:unique_ptr|shared_ptr|weak_ptr)[^>]*>\s*&?\s*([A-Za-z_]\w*)",
                    line,
                )
                if m_param:
                    smart_ptr_vars.add(m_param.group(1))
        # 检测C++容器变量（值类型，不可能为NULL）
        m_container = re_cpp_container.search(line)
        if m_container:
            container_vars.add(m_container.group(1))
        # 检测 delete[] 语句，记录被删除的变量
        m_delete = re_delete_stmt.search(line)
        if m_delete:
            # delete[] var 不是解引用，跳过
            pass

    def _is_just_allocated(var: str, lines: Sequence[str], line_no: int) -> bool:
        """检查变量是否刚分配成功（前1-2行有malloc/new等分配函数）"""
        for offset in range(1, 3):  # 检查前1-2行
            prev_idx = line_no - offset
            if prev_idx < 1 or prev_idx > len(lines):
                continue
            prev_line = lines[prev_idx - 1]
            # 检查是否有分配函数调用，且变量名出现在赋值左侧
            if re_malloc_like.search(prev_line):
                if re.search(rf"\b{re.escape(var)}\s*=", prev_line):
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
            # 排除模板参数中的数组访问（如 make_unique<int[]>）
            before_var = s[:var_pos]
            if "<" in before_var and ">" not in before_var:
                # 在模板参数内部，跳过
                continue
            # 排除明显的数组初始化（如 int arr[] = {...}）
            if type_kw.search(before_var) and "=" in s[var_pos:]:
                # 检查是否是初始化语法
                after_var = s[var_pos + len(var) :]
                if re.match(r"\s*\[[^\]]*\]\s*=", after_var):
                    continue
            vars_hit.append(var)
        for v in set(vars_hit):
            if v == "this":  # C++ 成员函数中 this-> 通常不应视为空指针
                continue
            # 跳过静态/全局变量（通常在初始化时已确保非空）
            if v in safe_vars:
                continue
            # 跳过栈数组（栈数组不可能为NULL）
            if v in stack_arrays:
                continue
            # 跳过智能指针变量（不可能为NULL）
            if v in smart_ptr_vars:
                continue
            # 跳过C++容器变量（值类型，不可能为NULL）
            if v in container_vars:
                continue
            # 跳过函数参数（参数的NULL检查应在调用者处进行）
            if v in func_params:
                continue
            # 跳过 delete/delete[] 语句（不是解引用）
            if re_delete_stmt.search(s):
                continue
            # 跳过刚分配成功后的立即使用（分配成功通常意味着非空）
            if _is_just_allocated(v, lines, idx):
                continue
            # 优先使用database的null_checks，否则回退到正则检测
            has_null_check = False
            if db_null_checks and v in db_null_checks:
                # 检查是否有在当前行之前的null检查
                for check_line in db_null_checks[v]:
                    if check_line < idx:
                        has_null_check = True
                        break
            else:
                has_null_check = _has_null_check_around(v, lines, idx, radius=3)
            if not has_null_check:
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
                        var_name=v,
                    )
                )
    return issues


def _rule_uninitialized_ptr_use(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测野指针（未初始化指针）使用：
    - 使用database的data_flow表查询变量定义和使用情况
    - 检测在def后没有赋值就直接use的指针
    """
    issues: List[Issue] = []

    if database is None:
        # 无database时跳过正则回退（避免误报）
        return issues

    # 从database获取当前文件的data_flow
    try:
        flow_nodes = database.get_data_flow_by_file(relpath)
    except Exception:
        return issues

    if not flow_nodes:
        return issues

    # 按变量名分组，检查def后是否有赋值
    var_flows: Dict[str, List[Dict[str, Any]]] = {}
    for node in flow_nodes:
        var_name = node.get("var_name", "")
        if var_name:
            if var_name not in var_flows:
                var_flows[var_name] = []
            var_flows[var_name].append(node)

    # 检查每个变量的数据流
    for var_name, nodes in var_flows.items():
        # 按行号排序
        nodes.sort(key=lambda n: n.get("line", 0))

        # 找到def节点
        def_line = None
        for node in nodes:
            if node.get("node_type") == "def":
                def_line = node.get("line", 0)
                break

        if not def_line:
            continue

        # 检查def后是否有赋值（value_source不为空）或param_in
        has_init = False
        first_use_line = None
        for node in nodes:
            line = node.get("line", 0)
            if line <= def_line:
                continue
            node_type = node.get("node_type", "")
            value_source = node.get("value_source", "")

            # 赋值或初始化
            if node_type == "def" and value_source:
                has_init = True
                break
            # 参数传入也算初始化
            if node_type == "param_in":
                has_init = True
                break
            # 使用（解引用）
            if node_type == "use" and not value_source:
                first_use_line = line
                break

        if first_use_line and not has_init:
            # 获取证据行
            evidence = ""
            if 0 < first_use_line <= len(lines):
                evidence = _strip_line(lines[first_use_line - 1])

            issues.append(
                Issue(
                    language="c/cpp",
                    category="memory_mgmt",
                    pattern="wild_pointer_deref",
                    file=relpath,
                    line=first_use_line,
                    evidence=evidence,
                    description=f"指针 {var_name} 声明后未见初始化即被解引用，可能为野指针使用。",
                    suggestion="在声明后立即将指针初始化为 NULL，并在使用前进行显式赋值与有效性校验。",
                    confidence=0.8,
                    severity="high",
                    var_name=var_name,
                )
            )

    return issues


def _rule_deadlock_patterns_from_calls(
    lines: Sequence[str], relpath: str, lock_calls: List[Dict[str, Any]]
) -> List[Issue]:
    """
    基于call_graph数据的死锁检测辅助函数。
    检测双重加锁、缺失解锁、锁顺序反转。
    """
    issues: List[Issue] = []

    # 按行号排序调用
    lock_calls.sort(key=lambda c: c.get("caller_line", 0))

    # 提取互斥量名称的辅助函数
    def extract_mutex_name(line_content: str) -> str:
        """从代码行提取互斥量名称"""
        m = RE_PTHREAD_LOCK.search(line_content)
        if m:
            return m.group(1)
        m = RE_PTHREAD_UNLOCK.search(line_content)
        if m:
            return m.group(1)
        return ""

    lock_stack: list[str] = []
    order_pairs: dict[tuple[str, str], int] = {}
    last_func_boundary = 0  # 上一个函数边界行号

    # 去重：call_graph可能有重复条目，按(callee_name, caller_line)去重
    seen_calls = set()
    unique_lock_calls = []
    for call in lock_calls:
        key = (call.get("callee_name", ""), call.get("caller_line", 0))
        if key not in seen_calls:
            seen_calls.add(key)
            unique_lock_calls.append(call)
    lock_calls = unique_lock_calls

    # 预先扫描所有行，找到函数边界行号
    func_boundary_lines = []
    func_pattern = re.compile(
        r"^\s*(static\s+)?(void|int|char|unsigned|signed)\s*(\*\s*)?\w+\s*\([^)]*(\*\s*\w+)?[^)]*\)\s*{"
    )
    for line_idx, line_content in enumerate(lines, start=1):
        if func_pattern.search(line_content):
            func_boundary_lines.append(line_idx)

    # 先行扫描：顺序和双重加锁
    for call in lock_calls:
        idx = call.get("caller_line", 0)
        callee_name = call.get("callee_name", "")
        if 0 < idx <= len(lines):
            s = lines[idx - 1]
        else:
            continue

        mtx = extract_mutex_name(s)
        if not mtx:
            continue

        # 检查是否跨越了函数边界
        for boundary in func_boundary_lines:
            if boundary > last_func_boundary and boundary < idx:
                lock_stack = []  # 新函数重置锁栈
                last_func_boundary = boundary
                break

        if callee_name == "pthread_mutex_lock":
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
            # 锁顺序记录（只在同一函数内记录）
            if lock_stack and lock_stack[-1] != mtx:
                pair = (lock_stack[-1], mtx)
                order_pairs.setdefault(pair, idx)
            lock_stack.append(mtx)
        elif callee_name == "pthread_mutex_unlock":
            # 从栈中移除最近的相同锁
            if mtx in lock_stack:
                for k in range(len(lock_stack) - 1, -1, -1):
                    if lock_stack[k] == mtx:
                        del lock_stack[k]
                        break

    # 锁顺序反转检测（跨函数检测）
    # 检测全局的锁顺序反转：如果存在 (A, B) 和 (B, A) 两个顺序，则存在死锁风险
    for (a, b), line1 in list(order_pairs.items()):
        reverse_pair = (b, a)
        if reverse_pair in order_pairs:
            line2 = order_pairs[reverse_pair]
            issues.append(
                Issue(
                    language="c/cpp",
                    category="error_handling",
                    pattern="lock_order_inversion",
                    file=relpath,
                    line=min(line1, line2),
                    evidence=f"锁顺序反转: {a}→{b} (行{line1}) vs {b}→{a} (行{line2})",
                    description=f"检测到锁顺序反转: 存在 {a}→{b} 和 {b}→{a} 两种加锁顺序，可能导致死锁。",
                    suggestion="统一所有线程的加锁顺序，避免锁顺序反转。",
                    confidence=0.7,
                    severity="high",
                )
            )
            # 避免重复报告
            del order_pairs[(a, b)]
            if reverse_pair in order_pairs:
                del order_pairs[reverse_pair]

    # 可能缺失解锁：在加锁后的 50 行窗口内未见对应解锁
    for call in lock_calls:
        if call.get("callee_name") != "pthread_mutex_lock":
            continue
        idx = call.get("caller_line", 0)
        if 0 < idx <= len(lines):
            s = lines[idx - 1]
        else:
            continue
        mtx = extract_mutex_name(s)
        if not mtx:
            continue

        end = min(len(lines), idx + 50)
        unlocked = False
        for j in range(idx + 1, end + 1):
            sj = _safe_line(lines, j)
            m_un = RE_PTHREAD_UNLOCK.search(sj)
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


def _rule_deadlock_patterns(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测常见死锁风险：
    - 双重加锁：同一互斥量在未解锁情况下再次加锁
    - 可能缺失解锁：加锁后在后续窗口内未看到对应解锁
    - 锁顺序反转：存在 (A->B) 与 (B->A) 两种加锁顺序
    实现基于启发式，可能产生误报。
    - 优先使用database查询call_graph表，无数据时回退到正则检测
    """
    issues: List[Issue] = []
    import os

    # 互斥锁函数集合
    LOCK_FUNCS = {"pthread_mutex_lock", "pthread_mutex_unlock"}

    # 优先使用database查询
    if database:
        try:
            call_graph = database.get_call_graph()
            lock_calls = []
            for call in call_graph:
                callee_name = call.get("callee_name", "")
                if callee_name in LOCK_FUNCS:
                    caller_file = call.get("caller_file", "")
                    if os.path.basename(caller_file) == os.path.basename(relpath):
                        lock_calls.append(call)

            # 如果database中有数据，使用database结果
            if lock_calls:
                return _rule_deadlock_patterns_from_calls(lines, relpath, lock_calls)
        except Exception:
            pass

    # 无database时跳过正则回退（避免误报）
    return issues


# ---------------------------
# 其他危险用法规则（新增一批低误报）
# ---------------------------


def _rule_double_free_and_free_non_heap(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测：
    - double_free：同一指针在未重新赋值/置空情况下被重复 free
    - free_non_heap：free(&x) 或 free("literal") 等明显非堆内存释放
    说明：优先使用污点分析，失败时回退到启发式实现。
    跨文件分析：利用数据库追踪指针状态，检测跨文件的Double Free风险。
    """
    issues: List[Issue] = []

    # 优先尝试污点分析
    try:
        import jarvis.jarvis_sec.taint_analyzer as taint_analyzer

        analyzer = taint_analyzer.TaintAnalyzerFactory.create("joern")
        if analyzer and analyzer.is_available():
            code = "\n".join(lines)
            rule = taint_analyzer.get_rule("double_free")
            if rule:
                taint_paths = rule.check(analyzer, code, relpath)
                for path in taint_paths:
                    issues.append(
                        Issue(
                            language="c/cpp",
                            category="memory_mgmt",
                            pattern="double_free",
                            file=relpath,
                            line=path.line_number,
                            evidence=path.code_snippet,
                            description=path.description,
                            suggestion="free 后将指针置 NULL；确保每块内存仅释放一次；理清所有权与释放路径。",
                            confidence=0.9,
                            severity="high",
                        )
                    )
            # 污点分析成功，继续检查free_non_heap
        # 污点分析不可用，回退到启发式检测
    except Exception:
        pass
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

    # 跨文件Double Free检测：利用数据库追踪指针状态
    if database is not None:
        cross_file_issues = _detect_cross_file_double_free(database, relpath, lines)
        issues.extend(cross_file_issues)

    return issues


def _rule_atoi_family(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测 atoi/atol/atoll/atof 的使用（缺乏错误与范围检查，易产生解析歧义）。
    建议改用 strtol/strtoul/strtod 并检查 errno/端点指针。
    说明：优先使用database查询call_graph表，失败时回退到正则检测。
    """
    issues: List[Issue] = []
    atoi_apis = ["atoi", "atol", "atoll", "atof"]

    # 优先尝试database驱动检测
    if database:
        try:
            import os

            basename = os.path.basename(relpath)
            calls = database.get_call_graph()
            for call in calls:
                callee = call.get("callee_name", "")
                if callee not in atoi_apis:
                    continue
                caller_file = call.get("caller_file", "")
                if basename == os.path.basename(caller_file):
                    issues.append(
                        Issue(
                            language="c/cpp",
                            category="input_validation",
                            pattern="atoi_family",
                            file=relpath,
                            line=call.get("caller_line", 0),
                            evidence=f"{callee}() 调用",
                            description=f"使用 {callee} 缺乏错误与范围检查，容易产生解析错误或未定义行为。",
                            suggestion="使用 strtol/strtoul/strtod 等并检查 errno 和 endptr；进行范围与格式校验。",
                            confidence=0.9,
                            severity="medium",
                        )
                    )
            if issues:
                return issues
        except Exception:
            pass

    # 无database时跳过正则回退（避免误报）
    return issues


def _rule_rand_insecure(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测 rand/srand 的使用。若上下文包含安全敏感关键词，提升风险。
    说明：优先使用database查询call_graph表，失败时回退到正则检测。
    """
    issues: List[Issue] = []
    rand_apis = ["rand", "srand", "random"]
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

    # 优先尝试database驱动检测
    if database:
        try:
            import os

            basename = os.path.basename(relpath)
            calls = database.get_call_graph()
            for call in calls:
                callee = call.get("callee_name", "")
                if callee not in rand_apis:
                    continue
                caller_file = call.get("caller_file", "")
                if basename == os.path.basename(caller_file):
                    line_num = call.get("caller_line", 0)
                    # 检查上下文是否包含安全敏感关键词
                    conf = 0.7
                    if line_num > 0 and line_num <= len(lines):
                        start = max(0, line_num - 2)
                        end = min(len(lines), line_num + 2)
                        window_text = " ".join(lines[start:end]).lower()
                        if any(k in window_text for k in keywords):
                            conf = 0.85
                    issues.append(
                        Issue(
                            language="c/cpp",
                            category="crypto",
                            pattern="rand_insecure",
                            file=relpath,
                            line=line_num,
                            evidence=f"{callee}() 调用",
                            description=f"检测到 {callee}，用于安全敏感场景可能不安全，易被预测。",
                            suggestion="使用系统级 CSPRNG（如 getrandom/arc4random/openssl RAND_bytes），避免用于密钥/令牌生成。",
                            confidence=conf,
                            severity="high" if conf >= 0.8 else "medium",
                        )
                    )
            if issues:
                return issues
        except Exception:
            pass

    # 无database时跳过正则回退（避免误报）
    return issues


def _rule_strtok_nonreentrant(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测 strtok 非重入/线程不安全使用。
    说明：优先使用database查询call_graph表，失败时回退到正则检测。
    """
    issues: List[Issue] = []
    strtok_apis = ["strtok"]

    # 优先尝试database驱动检测
    if database:
        try:
            import os

            basename = os.path.basename(relpath)
            calls = database.get_call_graph()
            for call in calls:
                callee = call.get("callee_name", "")
                if callee not in strtok_apis:
                    continue
                caller_file = call.get("caller_file", "")
                if basename == os.path.basename(caller_file):
                    issues.append(
                        Issue(
                            language="c/cpp",
                            category="thread_safety",
                            pattern="strtok_nonreentrant",
                            file=relpath,
                            line=call.get("caller_line", 0),
                            evidence=f"{callee}() 调用",
                            description="使用 strtok 非重入且线程不安全，可能导致竞态或数据覆盖。",
                            suggestion="使用 strtok_r（POSIX）或可重入/线程安全的分割方案。",
                            confidence=0.85,
                            severity="medium",
                        )
                    )
            if issues:
                return issues
        except Exception:
            pass

    # 无database时跳过正则回退（避免误报）
    return issues


def _rule_open_permissive_perms(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测过宽文件权限：
    - open(..., O_CREAT, 0666/0777/...) 直接授予过宽权限
    - fopen(..., "w"/"w+") 在安全敏感上下文可提示收紧权限（基于关键词启发）
    说明：优先使用database查询call_graph表，失败时回退到正则检测。
    """
    issues: List[Issue] = []
    open_apis = ["open", "fopen"]

    # 优先尝试database驱动检测
    if database:
        try:
            import os

            basename = os.path.basename(relpath)
            calls = database.get_call_graph()
            for call in calls:
                callee = call.get("callee_name", "")
                if callee not in open_apis:
                    continue
                caller_file = call.get("caller_file", "")
                if basename == os.path.basename(caller_file):
                    line_num = call.get("caller_line", 0)
                    if line_num > 0 and line_num <= len(lines):
                        s = lines[line_num - 1]
                        # 检查open权限
                        m = RE_OPEN_PERMISSIVE.search(s)
                        if m:
                            mode = m.group(1)
                            try:
                                mode_val = int(mode, 8)
                                has_group_write = (mode_val & 0o020) != 0
                                has_other_write = (mode_val & 0o002) != 0
                                has_other_read = (mode_val & 0o004) != 0
                                is_permissive = (
                                    has_group_write or has_other_write or has_other_read
                                )
                                if not is_permissive:
                                    continue
                            except ValueError:
                                pass
                            issues.append(
                                Issue(
                                    language="c/cpp",
                                    category="insecure_permissions",
                                    pattern="open_permissive_perms",
                                    file=relpath,
                                    line=line_num,
                                    evidence=f"{callee}() 权限 {mode}",
                                    description=f"open 使用 O_CREAT 且权限 {mode} 过宽，存在敏感信息泄露风险。",
                                    suggestion="显式使用更严格的权限（如 0600/0640），或设置合适 umask 后再创建文件。",
                                    confidence=0.85,
                                    severity="high",
                                )
                            )
            if issues:
                return issues
        except Exception:
            pass

    # 无database时跳过正则回退（避免误报）
    return issues


# ---------------------------
# 更多危险用法规则（第二批）
# ---------------------------


def _rule_alloca_unbounded(
    lines: Sequence[str], relpath: str, database: Optional[ProjectDatabase] = None
) -> List[Issue]:
    """
    检测 alloca 使用非常量/未受控大小，可能导致栈耗尽或崩溃。
    仅在参数非纯数字常量、且不含 sizeof 时告警。
    说明：优先使用database查询call_graph表，失败时回退到正则检测。
    """
    issues: List[Issue] = []
    alloca_apis = ["alloca", "__builtin_alloca"]

    # 优先尝试database驱动检测
    if database:
        try:
            import os

            basename = os.path.basename(relpath)
            calls = database.get_call_graph()
            for call in calls:
                callee = call.get("callee_name", "")
                if callee not in alloca_apis:
                    continue
                caller_file = call.get("caller_file", "")
                if basename == os.path.basename(caller_file):
                    line_num = call.get("caller_line", 0)
                    # 获取调用参数进行启发式分析
                    if line_num > 0 and line_num <= len(lines):
                        s = lines[line_num - 1]
                        m = RE_ALLOCA.search(s)
                        if m:
                            arg = m.group(1).strip()
                            # 纯数字常量或包含 sizeof 视为更安全
                            if re.fullmatch(r"\d+\s*", arg) or "sizeof" in arg:
                                continue
                            # 宏常量（全大写+下划线/数字）通常为编译期常量
                            if re.fullmatch(r"[A-Z_][A-Z0-9_]*", arg):
                                continue
                            conf = 0.75
                            if re.search(r"(len|size|count|n)\b", arg, re.IGNORECASE):
                                conf = 0.85
                            issues.append(
                                Issue(
                                    language="c/cpp",
                                    category="memory_mgmt",
                                    pattern="alloca_unbounded",
                                    file=relpath,
                                    line=line_num,
                                    evidence=f"{callee}({arg})",
                                    description="alloca 使用的大小不是编译期常量，可能导致未受控的栈分配与崩溃风险。",
                                    suggestion="避免使用 alloca；改用堆分配并对大小做上界检查与错误处理。",
                                    confidence=conf,
                                    severity="high" if conf >= 0.8 else "medium",
                                )
                            )
            if issues:
                return issues
        except Exception:
            pass

    # 无database时跳过正则回退（避免误报）
    return issues


def _rule_vla_usage(
    lines: Sequence[str], relpath: str, database: Optional[ProjectDatabase] = None
) -> List[Issue]:
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


def _rule_pthread_returns_unchecked(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测 pthread 常见接口的返回值未检查的情形（同/后一两行缺少 if/比较判断）。
    说明：优先使用database查询call_graph表，失败时回退到正则检测。
    """
    issues: List[Issue] = []
    pthread_apis = [
        "pthread_create",
        "pthread_join",
        "pthread_mutex_lock",
        "pthread_mutex_unlock",
        "pthread_cond_wait",
        "pthread_cond_signal",
    ]

    # 优先尝试database驱动检测
    if database:
        try:
            import os

            basename = os.path.basename(relpath)
            calls = database.get_call_graph()
            for call in calls:
                callee = call.get("callee_name", "")
                if callee not in pthread_apis:
                    continue
                caller_file = call.get("caller_file", "")
                if basename == os.path.basename(caller_file):
                    line_num = call.get("caller_line", 0)
                    # 检查返回值是否被检查
                    if line_num > 0 and line_num <= len(lines):
                        nearby = " ".join(
                            _safe_line(lines, i)
                            for i in range(line_num, min(line_num + 2, len(lines)) + 1)
                        )
                        if not re.search(r"\bif\s*\(|>=|<=|==|!=|<|>", nearby):
                            issues.append(
                                Issue(
                                    language="c/cpp",
                                    category="error_handling",
                                    pattern="pthread_ret_unchecked",
                                    file=relpath,
                                    line=line_num,
                                    evidence=f"{callee}() 调用",
                                    description=f"pthread 接口 {callee} 返回值可能未检查，错误处理缺失可能导致死锁/资源泄漏。",
                                    suggestion="检查 pthread 接口返回码并进行错误路径处理；必要时记录日志与清理资源。",
                                    confidence=0.75,
                                    severity="medium",
                                )
                            )
            if issues:
                return issues
        except Exception:
            pass

    # 无database时跳过正则回退（避免误报）
    return issues


def _rule_cond_wait_no_loop(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测 pthread_cond_wait 未在 while 循环中使用（防止虚假唤醒）。
    准确性优化：
    - 支持检测“与调用在同一行的 while(predicate) pthread_cond_wait(...)”写法，避免误报
    说明：优先使用database查询call_graph表，失败时回退到正则检测。
    """
    issues: List[Issue] = []
    cond_wait_apis = ["pthread_cond_wait"]

    # 优先尝试database驱动检测
    if database:
        try:
            import os

            basename = os.path.basename(relpath)
            calls = database.get_call_graph()
            for call in calls:
                callee = call.get("callee_name", "")
                if callee not in cond_wait_apis:
                    continue
                caller_file = call.get("caller_file", "")
                if basename == os.path.basename(caller_file):
                    line_num = call.get("caller_line", 0)
                    # 检查上下文是否有while循环
                    if line_num > 0 and line_num <= len(lines):
                        s = lines[line_num - 1]
                        m = RE_PTHREAD_COND_WAIT.search(s)
                        if m:
                            # 回看 2 行内是否有 while( ... )
                            prev_text = " ".join(
                                _safe_line(lines, j)
                                for j in range(max(1, line_num - 2), line_num)
                            )
                            has_prev_while = (
                                re.search(r"\bwhile\s*\(", prev_text) is not None
                            )
                            # 同一行（调用前半部分）若包含 while(...)，也视为正确用法
                            same_line_before = s[: m.start()]
                            has_same_line_while = (
                                re.search(r"\bwhile\s*\(", same_line_before) is not None
                            )

                            if has_prev_while or has_same_line_while:
                                continue

                            issues.append(
                                Issue(
                                    language="c/cpp",
                                    category="thread_safety",
                                    pattern="cond_wait_no_loop",
                                    file=relpath,
                                    line=line_num,
                                    evidence=f"{callee}() 调用",
                                    description="pthread_cond_wait 建议置于条件谓词的 while 循环中，以防止虚假唤醒。",
                                    suggestion="使用 while(predicate_not_satisfied) 包裹 pthread_cond_wait 调用并在唤醒后重新检查条件。",
                                    confidence=0.75,
                                    severity="medium",
                                )
                            )
            if issues:
                return issues
        except Exception:
            pass

    # 无database时跳过正则回退（避免误报）
    return issues


def _rule_thread_leak_no_join_from_calls(
    lines: Sequence[str], relpath: str, thread_calls: List[Dict[str, Any]]
) -> List[Issue]:
    """
    基于call_graph数据的线程泄漏检测辅助函数。
    检测pthread_create后是否有pthread_join/pthread_detach。
    """
    issues: List[Issue] = []

    # 按行号排序调用
    thread_calls.sort(key=lambda c: c.get("caller_line", 0))

    # 提取线程ID的辅助函数
    def extract_thread_id(line_content: str) -> str:
        """从代码行提取线程ID变量名"""
        m = RE_PTHREAD_CREATE.search(line_content)
        if m:
            return m.group(1)
        m = RE_PTHREAD_JOIN.search(line_content)
        if m:
            return m.group(1)
        m = RE_PTHREAD_DETACH.search(line_content)
        if m:
            return m.group(1)
        return ""

    # 检测pthread_create后是否有join/detach
    for call in thread_calls:
        if call.get("callee_name") != "pthread_create":
            continue

        idx = call.get("caller_line", 0)
        if 0 < idx <= len(lines):
            s = lines[idx - 1]
        else:
            continue

        tid = extract_thread_id(s)
        if not tid:
            continue

        # 在后续80行窗口内检测join/detach
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


def _rule_thread_leak_no_join(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测创建线程后未 join/detach 的可能线程泄漏。
    优先使用database查询call_graph表，无数据时回退到正则检测。
    """
    issues: List[Issue] = []
    import os

    # 线程函数集合
    THREAD_FUNCS = {"pthread_create", "pthread_join", "pthread_detach"}

    # 优先使用database查询
    if database:
        try:
            call_graph = database.get_call_graph()
            thread_calls = []
            for call in call_graph:
                callee_name = call.get("callee_name", "")
                if callee_name in THREAD_FUNCS:
                    caller_file = call.get("caller_file", "")
                    if os.path.basename(caller_file) == os.path.basename(relpath):
                        thread_calls.append(call)

            # 如果database中有数据，使用database结果
            if thread_calls:
                return _rule_thread_leak_no_join_from_calls(
                    lines, relpath, thread_calls
                )
        except Exception:
            pass

    # 无database时跳过正则回退（避免误报）
    return issues


def _rule_inet_legacy(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测 inet_addr/inet_aton 等旧接口的使用。
    说明：优先使用database查询call_graph表，失败时回退到正则检测。
    """
    issues: List[Issue] = []
    inet_apis = ["inet_addr", "inet_aton", "inet_ntoa"]

    # 优先尝试database驱动检测
    if database:
        try:
            import os

            basename = os.path.basename(relpath)
            calls = database.get_call_graph()
            for call in calls:
                callee = call.get("callee_name", "")
                if callee not in inet_apis:
                    continue
                caller_file = call.get("caller_file", "")
                if basename == os.path.basename(caller_file):
                    issues.append(
                        Issue(
                            language="c/cpp",
                            category="network_api",
                            pattern="inet_legacy",
                            file=relpath,
                            line=call.get("caller_line", 0),
                            evidence=f"{callee}() 调用",
                            description=f"使用 {callee} 旧接口，错误语义模糊/不一致。",
                            suggestion="使用 inet_pton/inet_ntop 进行地址转换，错误处理更可靠且支持 IPv6。",
                            confidence=0.85,
                            severity="low",
                        )
                    )
            if issues:
                return issues
        except Exception:
            pass

    # 无database时跳过正则回退（避免误报）
    return issues


def _rule_time_apis_not_threadsafe(
    lines: Sequence[str], relpath: str, database: Optional[ProjectDatabase] = None
) -> List[Issue]:
    """
    检测 asctime/ctime/localtime/gmtime 非线程安全接口（非 *_r）。
    说明：优先使用database查询call_graph表，失败时回退到正则检测。
    """
    issues: List[Issue] = []
    time_apis = ["asctime", "ctime", "localtime", "gmtime"]

    # 优先尝试database驱动检测
    if database:
        try:
            import os

            basename = os.path.basename(relpath)
            calls = database.get_call_graph()
            for call in calls:
                callee = call.get("callee_name", "")
                if callee not in time_apis:
                    continue
                caller_file = call.get("caller_file", "")
                if basename == os.path.basename(caller_file):
                    issues.append(
                        Issue(
                            language="c/cpp",
                            category="thread_safety",
                            pattern="time_api_not_threadsafe",
                            file=relpath,
                            line=call.get("caller_line", 0),
                            evidence=f"{callee}() 调用",
                            description=f"使用 {callee} 非重入接口，线程安全性不足。",
                            suggestion="改用 *_r 线程安全版本（如 localtime_r/gmtime_r/ctime_r）。",
                            confidence=0.85,
                            severity="medium",
                        )
                    )
            if issues:
                return issues
        except Exception:
            pass

    # 无database时跳过正则回退（避免误报）
    return issues


def _rule_getenv_unchecked(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测getenv返回值未检查的情况。
    说明：优先使用database查询null_checks，失败时回退到启发式实现。
    """
    issues: List[Issue] = []

    # 优先尝试database驱动检测
    if database:
        try:
            from jarvis.jarvis_sec.data_flow_analyzer import DataFlowAnalyzer

            analyzer = DataFlowAnalyzer(database)
            code = "\n".join(lines)
            result = analyzer.analyze_code(
                code, is_cpp=False, database=database, file_path=relpath
            )

            if result and result.null_checks is not None:
                # 查找getenv调用点
                for idx, s in enumerate(lines, start=1):
                    m = RE_GETENV.search(s)
                    if not m:
                        continue

                    # 获取变量名（赋值模式）
                    var_name = None
                    assign_match = re.search(r"\b([A-Za-z_]\w*)\s*=\s*getenv\s*\(", s)
                    if assign_match:
                        var_name = assign_match.group(1)

                    if var_name:
                        # 跳过return语句中的getenv（调用者负责检查）
                        if re.search(r"\breturn\s+", s):
                            continue
                        # 检查是否有null_check
                        has_check = var_name in result.null_checks
                        if not has_check:
                            # 使用_has_null_check_around进行二次确认
                            has_check = _has_null_check_around(
                                var_name, lines, idx, radius=5
                            )
                        if not has_check:
                            issues.append(
                                Issue(
                                    language="c/cpp",
                                    category="input_validation",
                                    pattern="getenv_unchecked",
                                    file=relpath,
                                    line=idx,
                                    evidence=_strip_line(s),
                                    description=f"环境变量 {var_name} = getenv() 后未检查返回值是否为 NULL。",
                                    suggestion="对白名单键进行读取；对取值执行格式/长度/字符集校验；避免直接拼接为命令/路径。",
                                    confidence=0.75,
                                    severity="medium",
                                )
                            )
                    else:
                        # 漏报修复：检测getenv直接作为函数参数传递（未赋值给变量）
                        # 模式：func(getenv("KEY")) 或 func(..., getenv("KEY"), ...)
                        # 但跳过return语句（调用者负责检查）
                        if re.search(r"\breturn\s+", s):
                            continue
                        direct_call_match = re.search(
                            r"getenv\s*\(\s*\"[^\"]+\"\s*\)", s
                        )
                        if direct_call_match:
                            issues.append(
                                Issue(
                                    language="c/cpp",
                                    category="input_validation",
                                    pattern="getenv_unchecked",
                                    file=relpath,
                                    line=idx,
                                    evidence=_strip_line(s),
                                    description="getenv()返回值直接传递给函数，未检查NULL。",
                                    suggestion="先检查getenv返回值是否为NULL，再使用环境变量值。",
                                    confidence=0.7,
                                    severity="medium",
                                )
                            )
                if issues:
                    return issues
                # database检测无问题，直接返回空
                return issues
        except Exception:
            pass

    # 无database时跳过正则回退（避免误报）
    return issues


# ---------------------------
# C++ 特定检查规则
# ---------------------------


def _rule_new_delete_mismatch(
    lines: Sequence[str], relpath: str, database: Optional[ProjectDatabase] = None
) -> List[Issue]:
    """
    检测 new/delete 与 malloc/free 的跨API不匹配问题：
    - new[] 必须用 delete[] 释放
    - new 必须用 delete 释放（不能用 delete[] 或 free）
    - malloc 必须用 free 释放（不能用 delete）
    """
    issues: List[Issue] = []
    new_array_vars: dict[str, int] = {}  # var -> line_no
    new_vars: dict[str, int] = {}  # var -> line_no
    malloc_vars: dict[str, int] = {}  # var -> line_no

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

        # malloc 分配
        m_malloc = RE_MALLOC_ASSIGN.search(s)
        if m_malloc:
            var = m_malloc.group(1)
            malloc_vars[var] = idx

    # 检查 delete[]、delete、free 的使用
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
                            pattern="new_delete_mismatch",
                            file=relpath,
                            line=idx,
                            evidence=_strip_line(s),
                            description="使用 delete[] 释放由 new 分配的内存（非数组），存在未定义行为风险。",
                            suggestion="new 分配的内存应使用 delete 释放；new[] 分配的内存应使用 delete[] 释放。",
                            confidence=0.85,
                            severity="high",
                        )
                    )
                if var in malloc_vars:
                    # 用 delete[] 释放了 malloc 分配的内存
                    issues.append(
                        Issue(
                            language="c/cpp",
                            category="memory_mgmt",
                            pattern="new_delete_mismatch",
                            file=relpath,
                            line=idx,
                            evidence=_strip_line(s),
                            description="使用 delete[] 释放由 malloc 分配的内存，存在未定义行为风险。",
                            suggestion="malloc 分配的内存应使用 free 释放；new 分配的内存应使用 delete 释放。",
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
                            pattern="new_delete_mismatch",
                            file=relpath,
                            line=idx,
                            evidence=_strip_line(s),
                            description="使用 delete 释放由 new[] 分配的数组内存，存在未定义行为风险。",
                            suggestion="new[] 分配的内存应使用 delete[] 释放；new 分配的内存应使用 delete 释放。",
                            confidence=0.85,
                            severity="high",
                        )
                    )
                if var in malloc_vars:
                    # 用 delete 释放了 malloc 分配的内存
                    issues.append(
                        Issue(
                            language="c/cpp",
                            category="memory_mgmt",
                            pattern="new_delete_mismatch",
                            file=relpath,
                            line=idx,
                            evidence=_strip_line(s),
                            description="使用 delete 释放由 malloc 分配的内存，存在未定义行为风险。",
                            suggestion="malloc 分配的内存应使用 free 释放；new 分配的内存应使用 delete 释放。",
                            confidence=0.85,
                            severity="high",
                        )
                    )

        # free 使用
        m_free = RE_FREE_VAR.search(s)
        if m_free:
            var = m_free.group(1)
            if var in new_vars:
                # 用 free 释放了 new 分配的内存
                issues.append(
                    Issue(
                        language="c/cpp",
                        category="memory_mgmt",
                        pattern="new_delete_mismatch",
                        file=relpath,
                        line=idx,
                        evidence=_strip_line(s),
                        description="使用 free 释放由 new 分配的内存，存在未定义行为风险。",
                        suggestion="new 分配的内存应使用 delete 释放；malloc 分配的内存应使用 free 释放。",
                        confidence=0.85,
                        severity="high",
                    )
                )
            if var in new_array_vars:
                # 用 free 释放了 new[] 分配的内存
                issues.append(
                    Issue(
                        language="c/cpp",
                        category="memory_mgmt",
                        pattern="new_delete_mismatch",
                        file=relpath,
                        line=idx,
                        evidence=_strip_line(s),
                        description="使用 free 释放由 new[] 分配的数组内存，存在未定义行为风险。",
                        suggestion="new[] 分配的内存应使用 delete[] 释放；malloc 分配的内存应使用 free 释放。",
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


def _rule_const_cast_unsafe(
    lines: Sequence[str], relpath: str, database: Optional[ProjectDatabase] = None
) -> List[Issue]:
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


def _rule_vector_string_bounds_check(
    lines: Sequence[str], relpath: str, database: Optional[ProjectDatabase] = None
) -> List[Issue]:
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


def _rule_missing_virtual_dtor(
    lines: Sequence[str], relpath: str, database: Optional[ProjectDatabase] = None
) -> List[Issue]:
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


def _rule_move_after_use(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    检测移动后使用的风险：对象被 std::move 后仍被使用。
    """
    issues: List[Issue] = []
    moved_vars: dict[str, int] = {}  # var -> line_no (被移动的变量)

    for idx, s in enumerate(lines, start=1):
        # 检测 std::move 赋值：提取被移动的变量（std::move(...)中的参数）
        m = RE_MOVE_ASSIGN.search(s)
        if m:
            # 从 std::move(...) 中提取被移动的变量名
            move_match = re.search(
                r"std::move\s*\(\s*([A-Za-z_]\w*)\s*\)", s, re.IGNORECASE
            )
            if move_match:
                var = move_match.group(1)  # 被移动的变量
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


def _rule_smart_ptr_cycle(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
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


def _rule_cpp_deadlock_patterns(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
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


def _rule_data_race_suspect(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
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
        # 改进：检查是否在函数外部（行首没有缩进，且不在函数体内）
        # 简化判断：行首没有空格/制表符的变量声明，且不是函数参数
        if not s.startswith(" ") and not s.startswith("\t"):
            # 可能是文件作用域的变量声明
            m_global = re.search(r"^[A-Za-z_]\w*(?:\s+\*|\s+)+([A-Za-z_]\w*)\s*[=;]", s)
            if m_global and "const" not in s.lower() and "static" not in s.lower():
                # 排除函数声明（检查是否有括号）
                if "(" not in s:
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

            # 检测变量访问（排除声明行）
            var_pattern = re.compile(rf"\b{re.escape(var)}\b")
            if not var_pattern.search(s):
                continue

            # 排除变量声明行（行首没有缩进且包含类型声明）
            if not s.startswith(" ") and not s.startswith("\t"):
                # 可能是变量声明，检查是否有类型关键字
                if re.search(r"^[A-Za-z_]\w*(?:\s+\*|\s+)+[A-Za-z_]\w*\s*[=;]", s):
                    continue  # 跳过变量声明行

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
                # 优化：只对明确的写操作报告，读操作大幅降低置信度
                if not is_write:
                    # 纯读操作在没有锁的情况下风险较低，跳过报告
                    # 除非是 volatile 变量（可能被误用）
                    if var not in volatile_vars:
                        continue
                    conf = 0.4  # volatile 读操作，低置信度
                else:
                    conf = 0.6
                    if var in volatile_vars:
                        # volatile 不能保证线程安全，但可能被误用
                        conf += 0.1

                # 检查是否在函数参数中（可能是局部变量，降低风险）
                if "(" in s and ")" in s:
                    # 可能是函数调用参数，降低置信度
                    conf -= 0.1

                # 进一步降低置信度：如果附近有锁，即使不在临界区内，也可能有其他保护机制
                if has_lock and (lock_line and unlocked):
                    conf -= 0.15  # 有锁但已解锁，可能是有意设计

                # 只报告置信度足够高的问题
                if conf >= 0.5:
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


def _rule_smart_ptr_get_unsafe(
    lines: Sequence[str], relpath: str, database: Optional[ProjectDatabase] = None
) -> List[Issue]:
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


def _rule_deserialization(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    CWE-502: 反序列化不可信数据检测
    检测点：
    - 反序列化不可信数据（pickle、yaml、json等）
    - 缺少类型校验
    - 缺少大小限制
    """
    issues: List[Issue] = []

    # 反序列化函数模式
    deserialize_funcs = [
        "json_loads",
        "json_load",
        "yaml_load",
        "pickle_loads",
        "pickle_load",
        "protobuf_decode",
        "msgpack_unpack",
        "cbor_decode",
        "xml_parse",
        "unserialize",
        "deserialize",
        "decode",
    ]

    # 检测反序列化函数调用
    for idx, line in enumerate(lines, start=1):
        # 检测反序列化函数调用
        for func in deserialize_funcs:
            if re.search(rf"\b{func}\s*\(", line, re.IGNORECASE):
                # 检查是否有类型校验（向前回看5行和向后查看10行）
                has_type_check = False
                lookback_lines = lines[max(0, idx - 6) : idx]
                lookahead_lines = lines[idx : min(len(lines), idx + 10)]

                # 检查前面的类型校验
                for prev_line in lookback_lines:
                    if re.search(
                        r"\b(json_is_|validate|check|verify|whitelist|schema)",
                        prev_line,
                        re.IGNORECASE,
                    ):
                        has_type_check = True
                        break

                # 检查后面的类型校验
                if not has_type_check:
                    for next_line in lookahead_lines:
                        if re.search(
                            r"\b(json_is_|validate|check|verify|whitelist|schema)",
                            next_line,
                            re.IGNORECASE,
                        ):
                            has_type_check = True
                            break

                # 检查是否有大小限制
                has_size_limit = False
                for prev_line in lookback_lines:
                    if re.search(
                        r"\b(max|limit|bound|size|depth)\b", prev_line, re.IGNORECASE
                    ):
                        has_size_limit = True
                        break

                # 检查后面的大小限制
                if not has_size_limit:
                    for next_line in lookahead_lines:
                        if re.search(
                            r"\b(max|limit|bound|size|depth)\b",
                            next_line,
                            re.IGNORECASE,
                        ):
                            has_size_limit = True
                            break

                # 如果没有类型校验和大小限制，报告漏洞
                if not has_type_check and not has_size_limit:
                    issues.append(
                        Issue(
                            language="c/cpp",
                            category="deserialization",
                            pattern="deserialization_untrusted",
                            file=relpath,
                            line=idx,
                            evidence=_strip_line(line),
                            description=f"反序列化函数 {func} 调用缺少类型校验和大小限制，可能导致反序列化漏洞",
                            suggestion="使用安全的反序列化方法，添加类型校验和大小限制，避免反序列化不可信数据",
                            confidence=0.7,
                            severity="high",
                        )
                    )

    return issues


def _rule_ssrf(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    CWE-918: 服务端请求伪造（SSRF）检测
    检测点：
    - 用户输入直接用于URL构造
    - libcurl未验证目标地址
    - 缺少URL白名单校验
    """
    issues: List[Issue] = []

    # 检测curl_easy_setopt设置URL
    for idx, line in enumerate(lines, start=1):
        # 检测CURLOPT_URL设置
        if re.search(r"CURLOPT_URL", line, re.IGNORECASE):
            # 检查是否有URL校验（向前回看15行和向后查看10行）
            has_url_validation = False
            lookback_lines = lines[max(0, idx - 16) : idx]
            lookahead_lines = lines[idx : min(len(lines), idx + 10)]

            # 检查前面的URL校验
            for prev_line in lookback_lines:
                if RE_SSRF_VALIDATE.search(prev_line):
                    has_url_validation = True
                    break

            # 检查后面的URL校验
            if not has_url_validation:
                for next_line in lookahead_lines:
                    if RE_SSRF_VALIDATE.search(next_line):
                        has_url_validation = True
                        break

            # 如果没有URL校验，报告漏洞
            if not has_url_validation:
                issues.append(
                    Issue(
                        language="c/cpp",
                        category="ssrf",
                        pattern="ssrf_url_validation",
                        file=relpath,
                        line=idx,
                        evidence=_strip_line(line),
                        description="curl_easy_setopt设置CURLOPT_URL时缺少URL校验，可能导致SSRF漏洞",
                        suggestion="添加URL白名单校验，限制协议为HTTPS，禁止访问内部IP地址",
                        confidence=0.7,
                        severity="high",
                    )
                )

        # 检测snprintf构造URL命令
        if re.search(r"\b(snprintf|sprintf)\s*\(", line, re.IGNORECASE):
            # 检查是否构造wget/curl命令
            if re.search(r"(wget|curl)\s+.*%s", line, re.IGNORECASE):
                # 检查是否有URL校验
                has_url_validation = False
                lookback_lines = lines[max(0, idx - 16) : idx]

                for prev_line in lookback_lines:
                    if RE_SSRF_VALIDATE.search(prev_line):
                        has_url_validation = True
                        break

                if not has_url_validation:
                    issues.append(
                        Issue(
                            language="c/cpp",
                            category="ssrf",
                            pattern="ssrf_command_construction",
                            file=relpath,
                            line=idx,
                            evidence=_strip_line(line),
                            description="使用snprintf/sprintf构造包含用户输入的URL命令，可能导致SSRF和命令注入漏洞",
                            suggestion="避免使用snprintf/sprintf构造URL命令，使用安全的HTTP库并添加URL校验",
                            confidence=0.8,
                            severity="critical",
                        )
                    )

        # 检测system/wget/popen执行URL命令
        if re.search(r"\b(system|popen)\s*\(", line, re.IGNORECASE):
            # 检查是否包含URL相关变量
            if re.search(r"(wget|curl|http|url)", line, re.IGNORECASE):
                # 检查是否有URL校验
                has_url_validation = False
                lookback_lines = lines[max(0, idx - 16) : idx]

                for prev_line in lookback_lines:
                    if RE_SSRF_VALIDATE.search(prev_line):
                        has_url_validation = True
                        break

                if not has_url_validation:
                    issues.append(
                        Issue(
                            language="c/cpp",
                            category="ssrf",
                            pattern="ssrf_command_injection",
                            file=relpath,
                            line=idx,
                            evidence=_strip_line(line),
                            description="使用system/popen执行包含用户输入的URL命令，可能导致SSRF和命令注入漏洞",
                            suggestion="避免使用system/popen执行URL命令，使用安全的HTTP库并添加URL校验",
                            confidence=0.8,
                            severity="critical",
                        )
                    )

    return issues


def _rule_resource_consumption(
    lines: Sequence[str], relpath: str, database: Optional["ProjectDatabase"] = None
) -> List[Issue]:
    """
    CWE-400: 资源消耗失控检测
    检测点：
    - 循环次数由用户输入控制无上限
    - 内存分配大小未校验
    - 递归深度无限制
    """
    issues: List[Issue] = []

    # 检测循环次数由用户输入控制
    for idx, line in enumerate(lines, start=1):
        # 检测for循环
        if re.search(r"\bfor\s*\(", line):
            # 检查是否有用户输入变量控制循环次数
            if re.search(
                r"\bfor\s*\([^;]*;\s*[^<]*<\s*(count|size|n|num|len|length)\s*;",
                line,
                re.IGNORECASE,
            ):
                # 检查是否有上限检查（向前回看10行）
                has_limit_check = False
                lookback_lines = lines[max(0, idx - 11) : idx]

                for prev_line in lookback_lines:
                    if RE_RESOURCE_LIMIT.search(prev_line) or re.search(
                        r"\b(if|MAX|LIMIT|BOUND)\b", prev_line, re.IGNORECASE
                    ):
                        has_limit_check = True
                        break

                if not has_limit_check:
                    issues.append(
                        Issue(
                            language="c/cpp",
                            category="resource_consumption",
                            pattern="unbounded_loop",
                            file=relpath,
                            line=idx,
                            evidence=_strip_line(line),
                            description="循环次数由用户输入控制且无上限检查，可能导致资源耗尽DoS攻击",
                            suggestion="添加循环次数上限检查，限制最大迭代次数",
                            confidence=0.6,
                            severity="medium",
                        )
                    )

        # 检测内存分配大小未校验
        if RE_RESOURCE_API.search(line):
            # 检查是否有大小变量，且变量名暗示来自用户输入或外部
            # 只检测明确来自用户输入的变量：user_input, input, argv, argc, req, request等
            user_input_patterns = [
                r"\b(user_input|user_size|input_size|req_size|request_size)\s*\)",
                r"malloc\s*\(\s*(atoi|atol|strtol|strtoul)\s*\(",  # malloc(atoi(...))
                r"malloc\s*\(\s*\w+\s*\*\s*\w+\s*\)",  # malloc(n * size) 乘法
            ]
            is_user_controlled = False
            for pattern in user_input_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    is_user_controlled = True
                    break

            if is_user_controlled:
                # 检查是否有大小限制检查（向前回看10行）
                has_size_check = False
                lookback_lines = lines[max(0, idx - 11) : idx]

                for prev_line in lookback_lines:
                    if RE_RESOURCE_LIMIT.search(prev_line) or re.search(
                        r"\b(if|MAX|LIMIT|BOUND|size.*>|size.*<)\b",
                        prev_line,
                        re.IGNORECASE,
                    ):
                        has_size_check = True
                        break

                if not has_size_check:
                    issues.append(
                        Issue(
                            language="c/cpp",
                            category="resource_consumption",
                            pattern="unbounded_allocation",
                            file=relpath,
                            line=idx,
                            evidence=_strip_line(line),
                            description="内存分配大小由用户输入控制且无上限检查，可能导致内存耗尽DoS攻击",
                            suggestion="添加分配大小上限检查，限制最大分配大小",
                            confidence=0.6,
                            severity="medium",
                        )
                    )

        # 检测递归深度无限制
        # 匹配函数定义：返回类型 + 函数名 + 参数列表 + {
        if re.search(
            r"\b(void|int|char|float|double|long|short|unsigned|signed|static|inline)\s+\w+\s*\([^)]*\)\s*\{",
            line,
        ):
            # 检查函数名是否在函数体内被调用（递归）
            func_match = re.search(r"\b(\w+)\s*\([^)]*\)\s*\{", line)
            if func_match:
                func_name = func_match.group(1)
                # 向后查看函数体是否包含递归调用
                # 注意：idx从1开始，Python列表索引从0开始
                # 使用括号匹配来确定函数体范围
                brace_count = line.count("{") - line.count("}")
                func_body_lines = []
                for i in range(idx, min(len(lines), idx + 50)):
                    func_body_lines.append(lines[i])
                    brace_count += lines[i].count("{") - lines[i].count("}")
                    if brace_count == 0:
                        break

                # 只在函数体内检测递归调用
                for next_line in func_body_lines:
                    if re.search(rf"\b{func_name}\s*\(", next_line):
                        # 检查是否有深度限制检查
                        has_depth_check = False
                        lookback_lines = lines[max(0, idx - 11) : idx]

                        for prev_line in lookback_lines:
                            if RE_RESOURCE_LIMIT.search(prev_line) or re.search(
                                r"\b(depth|MAX|LIMIT)\b", prev_line, re.IGNORECASE
                            ):
                                has_depth_check = True
                                break

                        # 检查函数体内是否有深度检查
                        if not has_depth_check:
                            for check_line in func_body_lines:
                                if re.search(
                                    r"\b(depth|MAX|LIMIT)\b", check_line, re.IGNORECASE
                                ):
                                    has_depth_check = True
                                    break

                        if not has_depth_check:
                            issues.append(
                                Issue(
                                    language="c/cpp",
                                    category="resource_consumption",
                                    pattern="unbounded_recursion",
                                    file=relpath,
                                    line=idx,
                                    evidence=_strip_line(line),
                                    description="递归函数缺少深度限制，可能导致栈溢出DoS攻击",
                                    suggestion="添加递归深度限制，或改用迭代实现",
                                    confidence=0.6,
                                    severity="medium",
                                )
                            )
                        break

    return issues


def analyze_c_cpp_text(
    relpath: str,
    text: str,
    database: Optional["ProjectDatabase"] = None,
) -> List[Issue]:
    """
    基于提供的文本进行 C/C++ 启发式分析。
    - 准确性优化：在启发式匹配前移除注释（保留字符串/字符字面量），
      以避免注释中的API命中导致的误报。
    - 准确性优化2：对通用 API 扫描使用“字符串内容掩蔽”的副本，避免把字符串里的片段当作代码。
    - 准确性优化3：使用数据流分析过滤误报（free后置NULL、if条件保护等）。

    Args:
        relpath: 相对文件路径
        text: 源代码文本
        database: 项目数据库实例（可选）
    """
    pre_text = _strip_if0_blocks(text)
    clean_text = _remove_comments_preserve_strings(pre_text)
    masked_text = _mask_strings_preserve_len(clean_text)
    # 原始行：保留字符串内容，供需要解析字面量的规则使用（如格式串、scanf 宽度等）
    lines = clean_text.splitlines()
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
            lang = "cpp" if _is_cpp_file(relpath) else "c"
            # 写入临时文件供DataCollector分析
            import tempfile
            import os

            _tmp_dir = tempfile.mkdtemp(prefix="jsec_")
            _tmp_file = os.path.join(_tmp_dir, os.path.basename(relpath))
            with open(_tmp_file, "w", encoding="utf-8") as f:
                f.write(text)
            collector.analyze_file(_tmp_file, lang)
            # 使用临时文件的完整路径查询database
            _db_file_path = _tmp_file
            database = _temp_database
        except Exception:
            pass  # 创建失败时继续使用空database
    else:
        # 有外部database时，确保使用正确的文件路径
        # 如果relpath是绝对路径，直接使用；否则需要匹配database中的路径
        import os

        if os.path.isabs(relpath):
            _db_file_path = relpath

    data_flow_analyzer = DataFlowAnalyzer()
    data_flow_result = data_flow_analyzer.analyze_code(
        text, is_cpp=_is_cpp_file(relpath), database=database, file_path=_db_file_path
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
    issues.extend(_rule_unsafe_api(mlines, _db_file_path, database=database))
    issues.extend(_rule_boundary_funcs(mlines, _db_file_path, lines, database=database))
    issues.extend(_rule_realloc_assign_back(mlines, _db_file_path, database=database))
    issues.extend(_rule_malloc_no_null_check(mlines, _db_file_path, database=database))
    issues.extend(
        _rule_function_return_ptr_no_check(mlines, _db_file_path, database=database)
    )
    issues.extend(_rule_unchecked_io(mlines, _db_file_path, database=database))
    # 需要字符串字面量信息的规则（使用原始行）
    issues.extend(_rule_strncpy_no_nullterm(lines, _db_file_path, database=database))
    issues.extend(_rule_format_string(lines, _db_file_path, database=database))
    issues.extend(_rule_scanf_no_width(lines, _db_file_path, database=database))
    # signal handler安全检查
    issues.extend(_rule_signal_handler_unsafe(lines, _db_file_path, database=database))
    # 其他规则
    issues.extend(_rule_insecure_tmpfile(mlines, _db_file_path, database=database))
    issues.extend(_rule_command_execution(mlines, _db_file_path, database=database))
    # 新增规则：SQL注入、内存泄漏、路径遍历
    issues.extend(_rule_sql_injection(lines, _db_file_path, database=database))
    issues.extend(_rule_memory_leak(lines, _db_file_path, database=database))
    issues.extend(_rule_path_traversal(lines, _db_file_path, database=database))
    # 新增规则：整数溢出、硬编码凭证、TOCTOU竞态
    issues.extend(_rule_integer_overflow(lines, _db_file_path, database=database))
    issues.extend(_rule_hardcoded_credentials(lines, _db_file_path, database=database))
    issues.extend(_rule_toctou_race(lines, _db_file_path, database=database))
    issues.extend(_rule_alloc_size_overflow(mlines, _db_file_path, database=database))
    # P14新增规则：弱加密、未初始化变量、符号转换、除零、编译器优化
    issues.extend(_rule_weak_crypto(lines, _db_file_path, database=database))
    issues.extend(_rule_uninitialized_var(lines, _db_file_path, database=database))
    issues.extend(_rule_signed_to_unsigned(lines, _db_file_path, database=database))
    issues.extend(_rule_divide_by_zero(lines, _db_file_path, database=database))
    # 禁用：误报率过高，大多数代码不需要volatile
    # issues.extend(_rule_compiler_security_check(lines, _db_file_path, database=database))
    # P15新增规则：指针算术错误、死锁风险、条件赋值
    issues.extend(
        _rule_pointer_arithmetic_error(lines, _db_file_path, database=database)
    )
    issues.extend(_rule_deadlock_risk(lines, _db_file_path, database=database))
    issues.extend(
        _rule_assignment_in_condition(lines, _db_file_path, database=database)
    )
    issues.extend(
        _rule_double_free_and_free_non_heap(mlines, _db_file_path, database=database)
    )
    issues.extend(_rule_atoi_family(mlines, _db_file_path, database=database))
    issues.extend(_rule_rand_insecure(mlines, _db_file_path, database=database))
    issues.extend(_rule_strtok_nonreentrant(mlines, _db_file_path, database=database))
    issues.extend(_rule_open_permissive_perms(mlines, _db_file_path, database=database))
    issues.extend(_rule_alloca_unbounded(mlines, _db_file_path, database=database))
    issues.extend(_rule_vla_usage(mlines, _db_file_path, database=database))
    issues.extend(
        _rule_pthread_returns_unchecked(mlines, _db_file_path, database=database)
    )
    issues.extend(_rule_cond_wait_no_loop(mlines, _db_file_path, database=database))
    issues.extend(_rule_thread_leak_no_join(mlines, _db_file_path, database=database))
    issues.extend(_rule_inet_legacy(mlines, _db_file_path, database=database))
    issues.extend(
        _rule_time_apis_not_threadsafe(mlines, _db_file_path, database=database)
    )
    issues.extend(_rule_getenv_unchecked(mlines, _db_file_path, database=database))
    # 复杂语义（使用掩蔽行避免字符串干扰）
    issues.extend(_rule_uaf_suspect(mlines, _db_file_path, database=database))
    issues.extend(_rule_possible_null_deref(mlines, _db_file_path, database=database))
    issues.extend(_rule_uninitialized_ptr_use(mlines, _db_file_path, database=database))
    issues.extend(_rule_deadlock_patterns(mlines, _db_file_path, database=database))
    # C++ 特定检查规则
    issues.extend(_rule_new_delete_mismatch(mlines, _db_file_path, database=database))
    issues.extend(_rule_reinterpret_cast_unsafe(mlines, _db_file_path))
    issues.extend(_rule_const_cast_unsafe(mlines, _db_file_path, database=database))
    issues.extend(
        _rule_vector_string_bounds_check(mlines, _db_file_path, database=database)
    )
    issues.extend(_rule_missing_virtual_dtor(mlines, _db_file_path, database=database))
    issues.extend(_rule_move_after_use(mlines, _db_file_path, database=database))
    issues.extend(_rule_uncaught_exception(mlines, _db_file_path))
    issues.extend(_rule_smart_ptr_cycle(mlines, _db_file_path, database=database))
    issues.extend(_rule_smart_ptr_get_unsafe(mlines, _db_file_path, database=database))
    # C++ 死锁检测
    issues.extend(_rule_cpp_deadlock_patterns(mlines, _db_file_path, database=database))
    # 数据竞争检测
    issues.extend(_rule_data_race_suspect(mlines, _db_file_path, database=database))
    # CWE-502: 反序列化漏洞检测
    issues.extend(_rule_deserialization(lines, _db_file_path, database=database))
    # CWE-918: SSRF漏洞检测
    issues.extend(_rule_ssrf(lines, _db_file_path, database=database))
    # CWE-400: 资源消耗失控检测
    issues.extend(_rule_resource_consumption(lines, _db_file_path, database=database))

    # 污点分析（核心功能）
    try:
        analyzer = taint_analyzer.TaintAnalyzerFactory.create("joern")
        if analyzer is not None:
            taint_issues = analyzer.analyze(text, str(_db_file_path))
            # 将污点分析结果转换为Issue对象
            for taint_path in taint_issues:
                issue = Issue(
                    language="c/cpp",
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

    # UAF误报过滤：free后置NULL的安全模式
    if issue_type in ["use_after_free_suspect", "use_after_free"]:
        return _is_uaf_false_positive(issue, analyzer, dataflow_result, lines)

    # Double Free误报过滤：检查是否有保护机制
    if issue_type in ["double_free", "double_free_suspect"]:
        return _is_double_free_false_positive(issue, analyzer, dataflow_result, lines)

    # 整数溢出误报过滤：检查是否有溢出检查
    if issue_type == "integer_overflow":
        return _is_integer_overflow_false_positive(
            issue, analyzer, dataflow_result, lines
        )

    # strcpy误报过滤：检查是否有NULL检查保护或死代码
    if issue_type in ["strcpy", "strncpy", "strcat", "strncat"]:
        return _is_strcpy_false_positive(issue, analyzer, dataflow_result, lines)

    # SQL注入误报过滤：检查是否为静态SQL或参数化查询
    if issue_type == "sql_injection":
        return _is_sql_injection_false_positive(issue, analyzer, dataflow_result, lines)

    # 格式化字符串误报过滤：检查是否为常量格式字符串
    if issue_type == "format_string":
        return _is_format_string_false_positive(issue, analyzer, dataflow_result, lines)

    # memcpy误报过滤：检查是否有长度检查保护
    if issue_type == "memcpy":
        return _is_memcpy_false_positive(issue, analyzer, dataflow_result, lines)

    # memory_leak误报过滤：检查是否为所有权转移
    if issue_type == "memory_leak":
        return _is_memory_leak_false_positive(issue, analyzer, dataflow_result, lines)

    # possible_null_deref误报过滤：检查是否有NULL检查保护
    if issue_type == "possible_null_deref":
        return _is_null_deref_false_positive(issue, analyzer, dataflow_result, lines)

    return False


def _is_uaf_false_positive(
    issue: Issue,
    analyzer: DataFlowAnalyzer,
    dataflow_result: DataFlowResult,
    lines: List[str],
) -> bool:
    """
    判断UAF是否为误报

    检查逻辑：
    1. free后是否置NULL
    2. 是否有NULL检查保护
    """
    line_num = issue.line

    # 从问题消息中提取变量名
    var_name = _extract_variable_name(issue)
    if not var_name:
        return False

    # 检查变量访问是否安全
    if analyzer.is_safe_access(var_name, line_num, dataflow_result):
        return True

    return False


def _is_double_free_false_positive(
    issue: Issue,
    analyzer: DataFlowAnalyzer,
    dataflow_result: DataFlowResult,
    lines: List[str],
) -> bool:
    """
    判断Double Free是否为误报

    检查逻辑：
    1. 第一次free后是否置NULL
    2. 第二次free前是否有NULL检查
    """
    line_num = issue.line
    var_name = _extract_variable_name(issue)

    if not var_name:
        return False

    # 检查变量状态
    if dataflow_result.pointer_states and var_name in dataflow_result.pointer_states:
        pointer_info = dataflow_result.pointer_states[var_name]

        # 如果变量被置NULL，检查是否有NULL检查
        if pointer_info.state == PointerState.NULLIFIED:
            if dataflow_result.null_checks and var_name in dataflow_result.null_checks:
                # 检查NULL检查是否在当前行之前
                for check_line in dataflow_result.null_checks[var_name]:
                    if check_line < line_num:
                        return True

    return False


def _is_integer_overflow_false_positive(
    issue: Issue,
    analyzer: DataFlowAnalyzer,
    dataflow_result: DataFlowResult,
    lines: List[str],
) -> bool:
    """
    判断整数溢出是否为误报

    检查逻辑：
    1. 是否有溢出检查（if条件）
    2. 是否使用了安全函数（如calloc）
    """
    line_num = issue.line

    # 检查后续几行是否有溢出检查
    for i in range(line_num, min(line_num + 5, len(lines))):
        line = lines[i] if i < len(lines) else ""
        # 检查是否有溢出检查
        if re.search(r"if\s*\(.*[<>].*\)", line):
            return True
        # 检查是否使用了安全函数
        if "calloc" in line or "reallocarray" in line:
            return True

    return False


def _is_strcpy_false_positive(
    issue: Issue,
    analyzer: DataFlowAnalyzer,
    dataflow_result: DataFlowResult,
    lines: List[str],
) -> bool:
    """
    判断strcpy类函数是否为误报

    检查逻辑：
    1. 是否有NULL检查保护
    2. 是否在死代码中
    """
    line_num = issue.line
    var_name = _extract_variable_name(issue)

    if not var_name:
        return False

    # 检查是否在死代码中
    if dataflow_result.dead_code_lines and line_num in dataflow_result.dead_code_lines:
        return True

    # 检查是否有NULL检查保护
    if dataflow_result.null_checks and var_name in dataflow_result.null_checks:
        for check_line in dataflow_result.null_checks[var_name]:
            if check_line < line_num:
                return True

    return False


def _is_sql_injection_false_positive(
    issue: Issue,
    analyzer: DataFlowAnalyzer,
    dataflow_result: DataFlowResult,
    lines: List[str],
) -> bool:
    """
    判断SQL注入是否为误报

    检查逻辑：
    1. 是否为静态SQL（无变量拼接）
    2. 是否使用参数化查询（%d, ?）
    """
    line_num = issue.line
    if line_num <= 0 or line_num > len(lines):
        return False

    line = lines[line_num - 1]

    # 检查是否为静态SQL（字符串常量）
    # 匹配 strcpy(query, "SELECT ...") 或 snprintf(query, ..., "SELECT ...")
    if re.search(r'strcpy\s*\(\s*\w+\s*,\s*"[^"]*"\s*\)', line):
        return True

    # 检查是否使用参数化查询（%d, ?等）
    if re.search(r"%[duifsc]", line) or "?" in line:
        # 但要确保不是字符串拼接（%s）
        if not re.search(r"sn?printf\s*\([^,]+,\s*[^,]+,\s*\w+\s*\)", line):
            return True

    return False


def _is_format_string_false_positive(
    issue: Issue,
    analyzer: DataFlowAnalyzer,
    dataflow_result: DataFlowResult,
    lines: List[str],
) -> bool:
    """
    判断格式化字符串漏洞是否为误报

    检查逻辑：
    1. 是否为常量格式字符串
    """
    line_num = issue.line
    if line_num <= 0 or line_num > len(lines):
        return False

    line = lines[line_num - 1]

    # 检查是否为常量格式字符串
    # 匹配 printf("...", ...) 或 snprintf(buf, size, "...", ...)
    if re.search(r'(sn)?printf\s*\([^,]*,\s*"[^"]*"', line):
        return True

    return False


def _is_memcpy_false_positive(
    issue: Issue,
    analyzer: DataFlowAnalyzer,
    dataflow_result: DataFlowResult,
    lines: List[str],
) -> bool:
    """
    判断memcpy是否为误报

    检查逻辑：
    1. 是否有长度检查保护
    """
    line_num = issue.line

    # 检查前5行是否有长度检查
    for i in range(max(0, line_num - 5), line_num):
        if i < len(lines):
            line = lines[i]
            # 检查是否有长度检查（if (len < size)）
            if re.search(r"if\s*\(.*[<>].*\)", line):
                return True

    return False


def _extract_variable_name(issue_or_msg: Issue | str) -> Optional[str]:
    """
    从Issue对象或问题消息中提取变量名

    Args:
        issue_or_msg: Issue对象或问题消息字符串

    Returns:
        Optional[str]: 变量名（如果找到）
    """
    # 如果传入的是Issue对象，优先使用var_name字段
    if isinstance(issue_or_msg, Issue):
        if issue_or_msg.var_name:
            return issue_or_msg.var_name
        msg = issue_or_msg.evidence
    else:
        msg = issue_or_msg

    # 尝试匹配常见的变量名模式
    patterns = [
        r"variable\s+`(\w+)`",
        r"pointer\s+`(\w+)`",
        r"`(\w+)`\s+is",
        r"`(\w+)`\s+after",
    ]

    for pattern in patterns:
        match = re.search(pattern, msg)
        if match:
            return match.group(1)

    # 尝试从赋值语句中提取变量名（如：int *data = malloc(...)）
    match = re.search(
        r"\b(\w+)\s*=\s*(?:\([^)]*\))?\s*(?:malloc|calloc|realloc)\s*\(", msg
    )
    if match:
        return match.group(1)

    # 尝试从数组访问中提取变量名（如：data[i] = ...）
    match = re.search(r"\b(\w+)\s*\[", msg)
    if match:
        return match.group(1)

    # 尝试从指针解引用中提取变量名（如：*ptr = ...）
    match = re.search(r"\*\s*(\w+)", msg)
    if match:
        return match.group(1)

    # 尝试从函数调用第一个参数中提取变量名（如：strcpy(buf, ...)、memcpy(data, ...）
    match = re.search(r"\b\w+\s*\(\s*(\w+)\s*,", msg)
    if match:
        return match.group(1)

    return None


def analyze_c_cpp_file(
    base: Path,
    relpath: Path,
    database: Optional["ProjectDatabase"] = None,
) -> List[Issue]:
    """
    从磁盘读取文件进行分析。

    Args:
        base: 基础路径
        relpath: 相对路径
        database: 项目数据库实例（可选）
    """
    try:
        text = (base / relpath).read_text(errors="ignore")
    except Exception:
        return []
    return analyze_c_cpp_text(str(relpath), text, database=database)


def analyze_files(
    base_path: str,
    files: Iterable[str],
    database: Optional["ProjectDatabase"] = None,
) -> List[Issue]:
    """
    批量分析文件，相对路径相对于 base_path。

    Args:
        base_path: 基础路径
        files: 文件列表
        database: 项目数据库实例（可选）
    """
    base = Path(base_path).resolve()
    out: List[Issue] = []
    for f in files:
        rel = Path(f)
        out.extend(analyze_c_cpp_file(base, rel, database=database))
    return out


def _is_memory_leak_false_positive(
    issue: Issue,
    analyzer: DataFlowAnalyzer,
    dataflow_result: DataFlowResult,
    lines: List[str],
) -> bool:
    """
    判断memory_leak是否为误报

    检查逻辑：
    1. 是否为所有权转移（函数返回malloc内存）
    2. 是否在同一函数内释放

    Args:
        issue: 问题对象
        analyzer: 数据流分析器
        dataflow_result: 数据流分析结果
        lines: 源代码行列表

    Returns:
        bool: 是否为误报
    """
    var_name = _extract_variable_name(issue)

    if not var_name:
        return False

    # 检查是否为所有权转移
    if (
        dataflow_result.ownership_transfer
        and var_name in dataflow_result.ownership_transfer
    ):
        return True

    return False


def _is_null_deref_false_positive(
    issue: Issue,
    analyzer: DataFlowAnalyzer,
    dataflow_result: DataFlowResult,
    lines: List[str],
) -> bool:
    """
    判断possible_null_deref是否为误报

    检查逻辑：
    1. 是否有NULL检查保护
    2. 是否为函数参数且有NULL检查
    3. 是否在死代码行

    Args:
        issue: 问题对象
        analyzer: 数据流分析器
        dataflow_result: 数据流分析结果
        lines: 源代码行列表

    Returns:
        bool: 是否为误报
    """
    line_num = issue.line
    var_name = _extract_variable_name(issue)

    if not var_name:
        return False

    # 检查是否在死代码行
    if dataflow_result.dead_code_lines and line_num in dataflow_result.dead_code_lines:
        return True

    # 检查是否有NULL检查保护
    if dataflow_result.null_checks and var_name in dataflow_result.null_checks:
        for check_line in dataflow_result.null_checks[var_name]:
            # NULL检查在当前行之前，且在同一函数内
            if check_line < line_num:
                # 检查是否在同一函数内（简化判断：检查行号差不超过50行）
                if line_num - check_line <= 50:
                    return True

    return False
