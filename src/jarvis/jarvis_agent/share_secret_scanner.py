# -*- coding: utf-8 -*-
"""敏感凭据扫描器（共享模块）。

本模块是「凭据检测规则」的唯一来源，供以下两处复用，避免规则漂移：
- Git 提交前钩子：.githooks/scan_staged_secrets.py（扫描暂存区新增行）
- 分享前闸门：jarvis_agent/share_manager.py 的 commit_and_push（扫描待共享文件）

设计原则：
- 只保留「高置信度、低误报」的真实凭据形态。
- 已知测试样本/占位符走白名单，避免误报。
- 绝不输出完整凭据：一律脱敏（保留首尾少量字符）。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Iterable
from typing import List
from typing import Tuple

# ---------------------------------------------------------------------------
# 检测规则：(名称, 正则)
# 只保留「高置信度、低误报」的真实凭据形态。
# ---------------------------------------------------------------------------
SECRET_PATTERNS: List[Tuple[str, re.Pattern]] = [
    # OpenAI / 类 OpenAI 的 sk- 密钥（真实长度远大于示例）
    ("OpenAI/通用 sk- 密钥", re.compile(r"\bsk-[A-Za-z0-9_-]{32,}\b")),
    # GitHub token
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("GitHub fine-grained PAT", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{60,}\b")),
    # AWS Access Key（真实 AKIA 后跟 16 位大写字母数字；排除官方示例）
    ("AWS Access Key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    # Slack token
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    # Google API key
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    # 私钥块
    (
        "私钥文件内容",
        re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
    ),
    # 通用「赋值型」密钥：key/secret/token/password = 长随机串
    # 注意：前缀边界用 (?<![A-Za-z0-9]) 而非 \b——下划线属于 \w，若用 \b，
    # db_password / DB_PASSWORD / my_api_key 等常见命名会因「_ 与 p 之间无词边界」而漏检。
    (
        "疑似硬编码密钥/口令",
        re.compile(
            r"""(?ix)
            (?<![A-Za-z0-9])
            (?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|
               private[_-]?key|client[_-]?secret|passwd|password)
            \b
            \s*[:=]\s*
            ["']([A-Za-z0-9_\-/+=]{20,})["']
            """
        ),
    ),
]

# ---------------------------------------------------------------------------
# 白名单：明确是测试样本/占位符的片段，命中则忽略该行。
# 每个条目是正则，匹配到即视为安全。
# ---------------------------------------------------------------------------
WHITELIST_PATTERNS: List[re.Pattern] = [
    re.compile(r"AKIAIOSFODNN7EXAMPLE"),  # AWS 官方文档示例
    re.compile(r"wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"),  # AWS 示例 secret
    re.compile(r"sk-1234567890abcdef"),  # 明显假值
    re.compile(r"sk-xxx+", re.IGNORECASE),
    re.compile(r"your[-_]?(?:secret|api|token|key)", re.IGNORECASE),
    re.compile(r"placeholder", re.IGNORECASE),
    re.compile(r"example[-_]?(?:key|token|secret)", re.IGNORECASE),
    re.compile(r"<[^>]*(?:key|token|secret|password)[^>]*>", re.IGNORECASE),
    re.compile(r"\$\{[^}]*(?:KEY|TOKEN|SECRET|PASSWORD)[^}]*\}"),  # ${ENV_VAR}
    re.compile(r"os\.environ|getenv|process\.env|System\.getenv"),  # 从环境变量读取
]

# 二进制/资源文件后缀直接跳过，避免误报与性能浪费
SKIP_SUFFIXES = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".tar",
    ".jar",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".mp4",
    ".mp3",
    ".wasm",
    ".so",
    ".dll",
    ".dylib",
    ".exe",
    ".bin",
    ".db",
)


@dataclass
class Finding:
    """一条命中记录（片段已脱敏）。"""

    file: str
    line_no: int
    rule_name: str
    masked_snippet: str


def mask(value: str) -> str:
    """脱敏：只保留首尾少量字符，绝不输出完整凭据。"""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}(len={len(value)})"


def is_whitelisted(line: str) -> bool:
    """判断整行是否命中白名单（测试样本/占位符）。"""
    return any(p.search(line) for p in WHITELIST_PATTERNS)


def scan_text(text: str, file_label: str) -> List[Finding]:
    """逐行扫描文本，返回全部命中记录。

    Args:
        text: 待扫描的文本内容。
        file_label: 报告中展示的文件标识（路径或占位名）。
    """
    findings: List[Finding] = []
    for idx, line in enumerate(text.splitlines(), 1):
        if is_whitelisted(line):
            continue
        for name, pattern in SECRET_PATTERNS:
            m = pattern.search(line)
            if m:
                findings.append(
                    Finding(
                        file=file_label,
                        line_no=idx,
                        rule_name=name,
                        masked_snippet=mask(m.group(0)),
                    )
                )
    return findings


def _should_skip(path: str) -> bool:
    """按后缀判断是否跳过（二进制/资源文件）。"""
    return path.lower().endswith(SKIP_SUFFIXES)


def scan_files(paths: Iterable[str]) -> List[Finding]:
    """扫描给定文件列表，返回全部命中记录。

    文件不存在、无权限、读取失败或为二进制后缀时静默跳过，绝不抛异常。
    """
    findings: List[Finding] = []
    for path in paths:
        if _should_skip(path):
            continue
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except OSError:
            continue
        findings.extend(scan_text(text, path))
    return findings


def format_findings(findings: List[Finding]) -> str:
    """把命中记录格式化为脱敏报告文本（每行一条）。"""
    return "\n".join(
        f"  {f.file}:{f.line_no}  [{f.rule_name}]  {f.masked_snippet}" for f in findings
    )
