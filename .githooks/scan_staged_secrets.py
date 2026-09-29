#!/usr/bin/env python3
"""扫描 Git 暂存区，拦截疑似真实凭据的提交。

设计原则：
- 只检查本次暂存的「新增行」（diff 的 + 行），不检查整库历史，保证快速。
- 命中真实凭据模式即退出码 1，中止提交，并打印文件/行号/脱敏后的片段。
- 已知的测试样本与占位符会被白名单过滤，避免误报（例如安全扫描器的
  漏洞数据集里故意硬编码的假 key）。
- 绝不打印完整凭据：一律脱敏（保留首尾少量字符）。

用法：由 .githooks/pre-commit 调用，无需手动执行。
"""

from __future__ import annotations

import re
import subprocess
import sys
from typing import List, Tuple

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
    ("私钥文件内容", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----")),
    # 通用「赋值型」密钥：key/secret/token/password = 长随机串
    (
        "疑似硬编码密钥/口令",
        re.compile(
            r"""(?ix)
            \b(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|
                 private[_-]?key|client[_-]?secret|passwd|password)\b
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
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip",
    ".gz", ".tar", ".jar", ".woff", ".woff2", ".ttf", ".eot", ".mp4",
    ".mp3", ".wasm", ".so", ".dll", ".dylib", ".exe", ".bin", ".db",
)


def _mask(value: str) -> str:
    """脱敏：只保留首尾少量字符，绝不输出完整凭据。"""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}(len={len(value)})"


def _is_whitelisted(line: str) -> bool:
    return any(p.search(line) for p in WHITELIST_PATTERNS)


def _staged_diff() -> str:
    """获取暂存区相对 HEAD 的 diff（含新增行）。"""
    result = subprocess.run(
        ["git", "diff", "--cached", "--unified=0", "--no-color", "--no-ext-diff"],
        capture_output=True,
        text=True,
        errors="replace",
    )
    if result.returncode != 0:
        print(f"[scan-secrets] git diff 失败：{result.stderr}", file=sys.stderr)
        return ""
    return result.stdout


def scan() -> int:
    diff = _staged_diff()
    if not diff:
        return 0

    findings: List[str] = []
    current_file = ""
    current_line_no = 0

    for raw in diff.splitlines():
        if raw.startswith("+++ b/"):
            current_file = raw[len("+++ b/"):]
            continue
        if raw.startswith("+++ "):
            current_file = raw[6:]
            continue
        if raw.startswith("@@"):
            # 解析 hunk 头 @@ -a,b +c,d @@，取新增侧起始行号
            m = re.search(r"\+(\d+)", raw)
            current_line_no = int(m.group(1)) if m else 0
            continue
        if not raw.startswith("+"):
            continue
        if current_file.lower().endswith(SKIP_SUFFIXES):
            continue

        line = raw[1:]
        line_no = current_line_no
        current_line_no += 1

        if _is_whitelisted(line):
            continue

        for name, pattern in SECRET_PATTERNS:
            m = pattern.search(line)
            if m:
                snippet = m.group(0)
                findings.append(
                    f"  {current_file}:{line_no}  [{name}]  {_mask(snippet)}"
                )

    if not findings:
        return 0

    print("", file=sys.stderr)
    print("=" * 72, file=sys.stderr)
    print("❌ 提交被拦截：暂存区中发现疑似真实凭据", file=sys.stderr)
    print("=" * 72, file=sys.stderr)
    for f in findings:
        print(f, file=sys.stderr)
    print("", file=sys.stderr)
    print("处理方式：", file=sys.stderr)
    print("  1. 确认是真实凭据 → 从代码中移除，改用环境变量/配置文件（勿入库）", file=sys.stderr)
    print("  2. 确认是测试样本/占位符 → 加入 .githooks/scan_staged_secrets.py 白名单", file=sys.stderr)
    print("  3. 确需提交（如安全测试数据）→ JARVIS_ALLOW_SECRETS=1 git commit ...", file=sys.stderr)
    print("", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(scan())
