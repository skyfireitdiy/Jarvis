#!/usr/bin/env python3
"""CI 用凭据扫描器：扫描指定 git 范围内变更文件的新增行。

与本地提交前钩子 .githooks/scan_staged_secrets.py 复用同一套规则
（jarvis_agent.share_secret_scanner），避免规则漂移：
- 本地钩子扫「暂存区」；
- 本脚本扫「任意 git 范围」（PR / push / 全历史），供 GitHub Actions 调用。

用法：
    python3 scripts/scan_secrets_ci.py <git-range>

    <git-range> 形如 "origin/main..HEAD"、"<sha1>..<sha2>"、"HEAD"（单提交）。
    未提供范围时默认扫描 HEAD 单个提交。

退出码：0=未发现；1=发现疑似凭据（CI 据此失败）。
绝不打印完整凭据：一律脱敏。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

# 复用共享规则模块（与本地钩子同源）。
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_REPO_ROOT, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

try:
    from jarvis.jarvis_agent.share_secret_scanner import (
        SECRET_PATTERNS,
        SKIP_SUFFIXES,
        is_whitelisted,
        mask,
    )
except Exception as _import_err:  # pragma: no cover - 环境异常兜底
    print(f"[scan-secrets-ci] 无法加载共享扫描规则模块：{_import_err}", file=sys.stderr)
    sys.exit(2)


def _diff(git_range: str) -> str:
    """获取指定范围的新增行 diff。"""
    cmd = [
        "git",
        "diff",
        "--unified=0",
        "--no-color",
        "--no-ext-diff",
        git_range,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if result.returncode != 0:
        print(
            f"[scan-secrets-ci] git diff 失败（范围={git_range}）：{result.stderr}",
            file=sys.stderr,
        )
        return ""
    return result.stdout


def scan(git_range: str) -> int:
    diff = _diff(git_range)
    if not diff:
        print(f"[scan-secrets-ci] 范围 {git_range} 无变更，跳过。")
        return 0

    findings: list[str] = []
    current_file = ""
    current_line_no = 0

    for raw in diff.splitlines():
        if raw.startswith("+++ b/"):
            current_file = raw[len("+++ b/") :]
            continue
        if raw.startswith("+++ "):
            current_file = raw[6:]
            continue
        if raw.startswith("@@"):
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

        if is_whitelisted(line):
            continue

        for name, pattern in SECRET_PATTERNS:
            m = pattern.search(line)
            if m:
                findings.append(
                    f"  {current_file}:{line_no}  [{name}]  {mask(m.group(0))}"
                )

    if not findings:
        print(f"[scan-secrets-ci] 范围 {git_range} 未发现疑似凭据。")
        return 0

    print("", file=sys.stderr)
    print("=" * 72, file=sys.stderr)
    print("❌ 凭据扫描失败：变更中发现疑似真实凭据", file=sys.stderr)
    print("=" * 72, file=sys.stderr)
    for f in findings:
        print(f, file=sys.stderr)
    print("", file=sys.stderr)
    print("处理方式：", file=sys.stderr)
    print(
        "  1. 确认是真实凭据 → 从代码中移除，改用环境变量/配置文件（勿入库）",
        file=sys.stderr,
    )
    print(
        "  2. 确认是测试样本/占位符 → 加入 share_secret_scanner.py 白名单",
        file=sys.stderr,
    )
    print("", file=sys.stderr)
    return 1


if __name__ == "__main__":
    rng = sys.argv[1] if len(sys.argv) > 1 else "HEAD"
    sys.exit(scan(rng))
