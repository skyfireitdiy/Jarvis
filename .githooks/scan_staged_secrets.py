#!/usr/bin/env python3
"""扫描 Git 暂存区，拦截疑似真实凭据的提交。

设计原则：
- 只检查本次暂存的「新增行」（diff 的 + 行），不检查整库历史，保证快速。
- 命中真实凭据模式即退出码 1，中止提交，并打印文件/行号/脱敏后的片段。
- 检测规则与分享前扫描共用同一模块（jarvis_agent.share_secret_scanner），
  避免两处规则漂移；白名单过滤测试样本/占位符，减少误报。
- 绝不打印完整凭据：一律脱敏（保留首尾少量字符）。

用法：由 .githooks/pre-commit 调用，无需手动执行。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

# ---------------------------------------------------------------------------
# 复用共享的检测规则模块。
# 本脚本由 pre-commit 以 `python3 .githooks/scan_staged_secrets.py` 直接调用，
# 运行时 sys.path 未必包含 src/，故在此按 __file__ 定位仓库根并注入 src。
# import 失败时明确报错退出（绝不静默放行）。
# ---------------------------------------------------------------------------
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
    print(
        f"[scan-secrets] 无法加载共享扫描规则模块：{_import_err}",
        file=sys.stderr,
    )
    print(
        "[scan-secrets] 请确认仓库 src/ 目录完整，或检查 Python 环境。",
        file=sys.stderr,
    )
    sys.exit(1)


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

        if is_whitelisted(line):
            continue

        for name, pattern in SECRET_PATTERNS:
            m = pattern.search(line)
            if m:
                snippet = m.group(0)
                findings.append(
                    f"  {current_file}:{line_no}  [{name}]  {mask(snippet)}"
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
    print(
        "  1. 确认是真实凭据 → 从代码中移除，改用环境变量/配置文件（勿入库）",
        file=sys.stderr,
    )
    print(
        "  2. 确认是测试样本/占位符 → 加入 share_secret_scanner.py 白名单",
        file=sys.stderr,
    )
    print(
        "  3. 确需提交（如安全测试数据）→ JARVIS_ALLOW_SECRETS=1 git commit ...",
        file=sys.stderr,
    )
    print("", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(scan())
