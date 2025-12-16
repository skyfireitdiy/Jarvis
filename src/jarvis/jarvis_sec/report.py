# -*- coding: utf-8 -*-
"""
安全分析套件 —— 报告聚合与评分模块

目标：
- 将启发式检查器输出的结构化问题列表进行聚合与评分，生成统一的 JSON 与 Markdown 报告。
- 与 workflow.direct_scan / 多Agent Aggregator 保持输出结构一致，便于评测解析与专家审阅。

输出结构（JSON示例）：
{
  "summary": {
    "total": 0,
    "by_language": {"c/cpp": 0, "rust": 0},
    "by_category": {
      "buffer_overflow": 0, "unsafe_api": 0, "memory_mgmt": 0, "error_handling": 0,
      "unsafe_usage": 0, "concurrency": 0, "ffi": 0
    },
    "top_risk_files": ["path1", "path2"]
  },
  "issues": [
    {
      "id": "C001",
      "language": "c/cpp",
      "category": "unsafe_api",
      "pattern": "strcpy",
      "file": "src/foo.c",
      "line": 123,
      "evidence": "strcpy(dst, src);",
      "preconditions": "N/A",
      "trigger_path": "函数 foobar 调用 strcpy 时，其输入 src 来自于未经校验的网络数据包",
      "consequences": "可能导致缓冲区溢出",
      "suggestions": "使用 strncpy_s 或其他安全函数替代",
      "confidence": 0.85,
      "severity": "high | medium | low",
      "score": 2.55
    }
  ]
}

提供的函数：
- aggregate_issues(issues: List[Union[Issue, Dict]], scanned_root: Optional[str] = None, scanned_files: Optional[int] = None) -> Dict
- format_markdown_report(report_json: Dict) -> str
- format_csv_report(report_json: Dict) -> str
- build_json_and_markdown(issues: List[Union[Issue, Dict]], scanned_root: Optional[str] = None, scanned_files: Optional[int] = None, output_file: Optional[str] = None) -> str
  - 如果 output_file 后缀为 .csv，则输出 CSV 格式；否则输出 Markdown 格式
"""

from __future__ import annotations

import csv
import hashlib
import io
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Union

# 依赖 Issue 结构，但本模块不直接导入 dataclass，接受 dict/Issue 两种形态
try:
    from jarvis.jarvis_sec.types import Issue  # 类型提示用，避免循环依赖
except Exception:
    Issue = Dict[str, Any]  # type: ignore


# ---------------------------
# 内部工具
# ---------------------------

_CATEGORY_ORDER = [
    "unsafe_api",
    "buffer_overflow",
    "memory_mgmt",
    "error_handling",
    "unsafe_usage",
    "concurrency",
    "ffi",
]

_SEVERITY_WEIGHT = {
    "high": 3.0,
    "medium": 2.0,
    "low": 1.0,
}


def _as_dict(item: Union[Issue, Dict[str, Any]]) -> Dict[str, Any]:
    """
    将 Issue/dataclass 或 dict 统一为 dict。
    """
    if isinstance(item, dict):
        return item
    # dataclass: 尝试属性访问
    d: Dict[str, Any] = {}
    for k in (
        "language",
        "category",
        "pattern",
        "file",
        "line",
        "evidence",
        "preconditions",
        "trigger_path",
        "consequences",
        "suggestions",
        "confidence",
        "severity",
    ):
        v = getattr(item, k, None)
        if v is not None:
            d[k] = v
    return d


def _normalize_issue(i: Dict[str, Any]) -> Dict[str, Any]:
    """
    归一化字段并补充缺省值。
    """
    j = {
        "language": i.get(
            "language",
            "c/cpp"
            if str(i.get("file", "")).endswith((".c", ".cpp", ".h", ".hpp"))
            else "rust",
        ),
        "category": i.get("category", "error_handling"),
        "pattern": i.get("pattern", ""),
        "file": i.get("file", ""),
        "line": int(i.get("line", 0) or 0),
        "evidence": i.get("evidence", ""),
        "preconditions": i.get("preconditions", ""),
        "trigger_path": i.get("trigger_path", ""),
        "consequences": i.get("consequences", ""),
        "suggestions": i.get("suggestions", ""),
        "confidence": float(i.get("confidence", 0.6)),
        "severity": i.get("severity", "medium"),
    }
    # 计算稳定ID（基于文件/行/类别/模式哈希）
    base = f"{j['file']}:{j['line']}:{j['category']}:{j['pattern']}"
    j["id"] = _make_issue_id(base, j["language"])
    # 评分：confidence * severity_weight
    j["score"] = round(j["confidence"] * _SEVERITY_WEIGHT.get(j["severity"], 1.0), 2)
    return j


def _make_issue_id(base: str, lang: str) -> str:
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()[:6]
    prefix = "C" if lang.startswith("c") else "R"
    return f"{prefix}{h.upper()}"


# ---------------------------
# 聚合与评分
# ---------------------------


def aggregate_issues(
    issues: List[Union[Issue, Dict[str, Any]]],
    scanned_root: Optional[str] = None,
    scanned_files: Optional[int] = None,
) -> Dict[str, Any]:
    """
    聚合问题列表并生成 JSON 报告。
    """
    # 归一化所有 issues
    normalized_items = [_normalize_issue(_as_dict(it)) for it in issues]

    # 去重：通过 gid 去重（如果存在），否则通过 file:line:category:pattern 去重
    # 保留第一个出现的 issue（因为 load_analysis_results 已经保留了最新的）
    seen_items: Dict[str, Dict[str, Any]] = {}
    for item in normalized_items:
        # 优先使用 gid 作为唯一标识
        gid = item.get("gid")
        if gid:
            key = f"gid:{gid}"
        else:
            # 如果没有 gid，使用 file:line:category:pattern 作为唯一标识
            key = f"{item.get('file')}:{item.get('line')}:{item.get('category')}:{item.get('pattern')}"

        if key not in seen_items:
            seen_items[key] = item

    items = list(seen_items.values())

    summary: Dict[str, Any] = {
        "total": len(items),
        "by_language": {"c/cpp": 0, "rust": 0},
        "by_category": {k: 0 for k in _CATEGORY_ORDER},
        "top_risk_files": [],
    }
    if scanned_root is not None:
        summary["scanned_root"] = scanned_root
    if scanned_files is not None:
        summary["scanned_files"] = scanned_files

    file_score: Dict[str, float] = {}
    for it in items:
        lang = it["language"]
        summary["by_language"][lang] = summary["by_language"].get(lang, 0) + 1
        cat = it["category"]
        summary["by_category"][cat] = summary["by_category"].get(cat, 0) + 1
        file_score[it["file"]] = file_score.get(it["file"], 0.0) + it["score"]

    # Top 风险文件按累计分排序，更稳定、可解释
    summary["top_risk_files"] = [
        f for f, _ in sorted(file_score.items(), key=lambda x: x[1], reverse=True)[:10]
    ]

    report = {
        "summary": summary,
        "issues": items,
    }
    return report


# ---------------------------
# Markdown 渲染
# ---------------------------


def format_markdown_report(report_json: Dict[str, Any]) -> str:
    """
    将聚合后的 JSON 报告渲染为 Markdown。
    """
    s = report_json.get("summary", {})
    issues: List[Dict[str, Any]] = report_json.get("issues", [])
    lines: List[str] = []

    lines.append("# 安全问题分析报告（聚合）")
    lines.append("")
    if "scanned_root" in s:
        lines.append(f"- 扫描根目录: {s.get('scanned_root')}")
    if "scanned_files" in s:
        lines.append(f"- 扫描文件数: {s.get('scanned_files')}")
    lines.append(f"- 检出问题总数: {s.get('total', 0)}")
    lines.append("")

    # 概览
    lines.append("## 统计概览")
    by_lang = s.get("by_language", {})
    lines.append(
        f"- 按语言: c/cpp={by_lang.get('c/cpp', 0)}, rust={by_lang.get('rust', 0)}"
    )
    lines.append("- 按类别：")
    by_cat = s.get("by_category", {})
    for k in _CATEGORY_ORDER:
        v = by_cat.get(k, 0)
        lines.append(f"  - {k}: {v}")
    if s.get("top_risk_files"):
        lines.append("- Top 风险文件：")
        for f in s["top_risk_files"]:
            lines.append(f"  - {f}")
    lines.append("")

    # 详细问题
    lines.append("## 详细问题")
    for i, it in enumerate(issues, start=1):
        lines.append(
            f"### [{i}] {it.get('file')}:{it.get('line')} ({it.get('language')}, {it.get('category')})"
        )
        lines.append(f"- 模式: {it.get('pattern')}")
        lines.append(f"- 证据: `{it.get('evidence')}`")
        lines.append(f"- 前置条件: {it.get('preconditions')}")
        lines.append(f"- 触发路径: {it.get('trigger_path')}")
        lines.append(f"- 后果: {it.get('consequences')}")
        lines.append(f"- 建议: {it.get('suggestions')}")
        lines.append(
            f"- 置信度: {it.get('confidence')}, 严重性: {it.get('severity')}, 评分: {it.get('score')}"
        )
        lines.append("")

    return "\n".join(lines)


def format_csv_report(report_json: Dict[str, Any]) -> str:
    """
    将聚合后的 JSON 报告渲染为 CSV 格式。
    """
    issues: List[Dict[str, Any]] = report_json.get("issues", [])

    # 定义 CSV 列
    fieldnames = [
        "id",
        "language",
        "category",
        "pattern",
        "file",
        "line",
        "evidence",
        "preconditions",
        "trigger_path",
        "consequences",
        "suggestions",
        "confidence",
        "severity",
        "score",
    ]

    # 使用 StringIO 来构建 CSV 字符串
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")

    # 写入表头
    writer.writeheader()

    # 写入数据行
    for it in issues:
        row = {field: str(it.get(field, "")) for field in fieldnames}
        writer.writerow(row)

    return output.getvalue()


def build_json_and_markdown(
    issues: List[Union[Issue, Dict[str, Any]]],
    scanned_root: Optional[str] = None,
    scanned_files: Optional[int] = None,
    meta: Optional[List[Dict[str, Any]]] = None,
    output_file: Optional[str] = None,
) -> str:
    """
    一次性生成报告文本。
    如果 output_file 后缀为 .csv，则输出 CSV 格式；否则输出 Markdown 格式。

    Args:
        issues: 问题列表
        scanned_root: 扫描根目录
        scanned_files: 扫描文件数
        meta: 可选元数据
        output_file: 输出文件名（可选），用于判断输出格式

    Returns:
        报告文本（Markdown 或 CSV 格式）
    """
    report = aggregate_issues(
        issues, scanned_root=scanned_root, scanned_files=scanned_files
    )
    if meta is not None:
        try:
            report["meta"] = (
                meta  # 注入可选审计信息（仅用于JSON时保留，为兼容未来需要）
            )
        except Exception:
            pass

    # 根据输出文件名后缀选择格式
    if output_file and output_file.lower().endswith(".csv"):
        return format_csv_report(report)
    else:
        return format_markdown_report(report)


__all__ = [
    "aggregate_issues",
    "format_markdown_report",
    "format_csv_report",
    "build_json_and_markdown",
]
