# -*- coding: utf-8 -*-
"""
OpenHarmony 安全分析套件 —— 报告聚合与评分模块

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
      "description": "使用不安全API，缺少长度检查。",
      "suggestion": "替换为安全API或增加长度验证。",
      "confidence": 0.85,
      "severity": "high | medium | low",
      "score": 2.55
    }
  ]
}

提供的函数：
- aggregate_issues(issues: List[Union[Issue, Dict]], scanned_root: Optional[str] = None, scanned_files: Optional[int] = None) -> Dict
- format_markdown_report(report_json: Dict) -> str
- build_json_and_markdown(issues: List[Union[Issue, Dict]], scanned_root: Optional[str] = None, scanned_files: Optional[int] = None) -> str
"""

from __future__ import annotations

import hashlib
from typing import Dict, Iterable, List, Optional, Union

# 依赖 Issue 结构，但本模块不直接导入 dataclass，接受 dict/Issue 两种形态
try:
    from jarvis.jarvis_sec.types import Issue  # 类型提示用，避免循环依赖
except Exception:
    Issue = dict  # type: ignore


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

def _as_dict(item: Union[Issue, Dict]) -> Dict:
    """
    将 Issue/dataclass 或 dict 统一为 dict。
    """
    if isinstance(item, dict):
        return item
    # dataclass: 尝试属性访问
    d: Dict = {}
    for k in (
        "language",
        "category",
        "pattern",
        "file",
        "line",
        "evidence",
        "description",
        "suggestion",
        "confidence",
        "severity",
    ):
        v = getattr(item, k, None)
        if v is not None:
            d[k] = v
    return d


def _normalize_issue(i: Dict) -> Dict:
    """
    归一化字段并补充缺省值。
    """
    j = {
        "language": i.get("language", "c/cpp" if str(i.get("file", "")).endswith((".c", ".cpp", ".h", ".hpp")) else "rust"),
        "category": i.get("category", "error_handling"),
        "pattern": i.get("pattern", ""),
        "file": i.get("file", ""),
        "line": int(i.get("line", 0) or 0),
        "evidence": i.get("evidence", ""),
        "description": i.get("description", ""),
        "suggestion": i.get("suggestion", ""),
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
    issues: List[Union[Issue, Dict]],
    scanned_root: Optional[str] = None,
    scanned_files: Optional[int] = None,
) -> Dict:
    """
    聚合问题列表并生成 JSON 报告。
    """
    items = [_normalize_issue(_as_dict(it)) for it in issues]

    summary: Dict = {
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

def format_markdown_report(report_json: Dict) -> str:
    """
    将聚合后的 JSON 报告渲染为 Markdown。
    """
    s = report_json.get("summary", {})
    issues: List[Dict] = report_json.get("issues", [])
    lines: List[str] = []

    lines.append("# OpenHarmony 安全问题分析报告（聚合）")
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
    lines.append(f"- 按语言: c/cpp={by_lang.get('c/cpp', 0)}, rust={by_lang.get('rust', 0)}")
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
        lines.append(f"### [{i}] {it.get('file')}:{it.get('line')} ({it.get('language')}, {it.get('category')})")
        lines.append(f"- 模式: {it.get('pattern')}")
        lines.append(f"- 证据: `{it.get('evidence')}`")
        lines.append(f"- 描述: {it.get('description')}")
        lines.append(f"- 建议: {it.get('suggestion')}")
        lines.append(f"- 置信度: {it.get('confidence')}, 严重性: {it.get('severity')}, 评分: {it.get('score')}")
        lines.append("")

    # 建议与后续计划
    lines.append("## 建议与后续计划")
    lines.append("- 对高风险文件优先进行加固与测试覆盖提升（边界检查、错误处理路径）。")
    lines.append("- 对不安全API统一替换/封装，审计 sprintf/scanf 等使用场景。")
    lines.append("- 对内存管理路径进行生命周期审查，避免 realloc 覆盖与 UAF。")
    lines.append("- 将关键模块迁移至 Rust（内存安全优先），对 FFI 边界进行条件约束与安全封装。")

    return "\n".join(lines)


def build_json_and_markdown(
    issues: List[Union[Issue, Dict]],
    scanned_root: Optional[str] = None,
    scanned_files: Optional[int] = None,
    meta: Optional[List[Dict]] = None,
) -> str:
    """
    一次性生成 JSON + Markdown 文本，便于直接输出与评测。
    - meta: 可选的审计信息（例如每个子任务的触发逻辑、工具使用等），将以 "meta" 字段注入到最终 JSON 顶层。
    """
    import json
    report = aggregate_issues(issues, scanned_root=scanned_root, scanned_files=scanned_files)
    if meta is not None:
        try:
            report["meta"] = meta  # 注入可选审计信息
        except Exception:
            pass
    json_text = json.dumps(report, ensure_ascii=False, indent=2)
    md_text = format_markdown_report(report)
    return f"{json_text}\n\n{md_text}"


__all__ = [
    "aggregate_issues",
    "format_markdown_report",
    "build_json_and_markdown",
]