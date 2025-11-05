# -*- coding: utf-8 -*-
"""
Jarvis 安全分析套件 —— Workflow（含可复现直扫基线）

目标：
- 识别指定模块的安全问题（内存管理、缓冲区操作、错误处理等），检出率≥60% 为目标。
- 在不依赖外部服务的前提下，提供一个“可复现、可离线”的直扫基线（direct scan）。
- 当前采用“先直扫拆分子任务，再由单Agent逐条分析”的模式；保留接口便于后续切换。

本模块提供：
- direct_scan(entry_path, languages=None, exclude_dirs=None) -> Dict：纯Python+正则/命令行辅助扫描，生成结构化结果
- format_markdown_report(result_json: Dict) -> str：将结构化结果转为可读的 Markdown

- run_with_agent(entry_path, languages=None) -> str：使用单Agent逐条子任务分析模式（复用 jarvis.jarvis_sec.__init__ 的实现）
"""

import os
import re
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, cast
from jarvis.jarvis_sec.checkers import analyze_c_files, analyze_rust_files

from jarvis.jarvis_sec.types import Issue


# ---------------------------
# 数据结构
# ---------------------------

# Issue dataclass is provided by jarvis.jarvis_sec.types to avoid circular imports


# ---------------------------
# 工具函数
# ---------------------------

def _rg_available() -> bool:
    return shutil.which("rg") is not None


def _iter_source_files(
    entry_path: str,
    languages: Optional[List[str]] = None,
    exclude_dirs: Optional[List[str]] = None,
) -> Iterable[Path]:
    """
    递归枚举源文件，支持按扩展名过滤与目录排除。
    默认语言扩展：c, cpp, h, hpp, rs
    """
    entry = Path(entry_path)
    if not entry.exists():
        return

    exts = set((languages or ["c", "cpp", "h", "hpp", "rs"]))
    excludes = set(exclude_dirs or [".git", "build", "out", "target", "third_party", "vendor"])

    for p in entry.rglob("*"):
        if not p.is_file():
            continue
        # 目录排除（任意祖先包含即排除）
        skip = False
        for parent in p.parents:
            if parent.name in excludes:
                skip = True
                break
        if skip:
            continue

        suf = p.suffix.lstrip(".").lower()
        if suf in exts:
            yield p.relative_to(entry)


def _try_rg_search(pattern: str, files: List[Path], cwd: Path) -> List[Tuple[Path, int, str]]:
    """
    使用 rg -n PATTERN file1 file2 ... 搜索，返回 (file, line, text)。
    若 rg 不可用或失败，返回空列表。
    """
    if not files:
        return []
    if not _rg_available():
        return []

    # rg 命令长度有限，分批执行
    results: List[Tuple[Path, int, str]] = []
    batch_size = 200
    for i in range(0, len(files), batch_size):
        batch = files[i : i + batch_size]
        cmd = ["rg", "-n", pattern] + [str(cwd / f) for f in batch]
        try:
            proc = subprocess.run(
                cmd, cwd=str(cwd), capture_output=True, text=True, check=False
            )
            if proc.returncode in (0, 1):  # 0: 有匹配；1: 无匹配
                out = proc.stdout.splitlines()
                for line in out:
                    # 解析: path:lineno:content
                    # 注意: Windows 路径中可能含冒号，这里采用从右侧第一次冒号分割两次的方案
                    parts = line.split(":", 2)
                    if len(parts) < 3:
                        continue
                    fpath = Path(parts[0])
                    try:
                        lineno = int(parts[1])
                    except ValueError:
                        continue
                    text = parts[2]
                    try:
                        rel = fpath.relative_to(cwd)
                    except Exception:
                        # 回退：将绝对路径转相对路径
                        try:
                            rel = Path(os.path.relpath(fpath, cwd))
                        except Exception:
                            rel = fpath
                    results.append((rel, lineno, text))
        except Exception:
            # 忽略 rg 错误，交由纯Python扫描兜底
            return []
    return results


# ---------------------------
# 汇总与报告
# ---------------------------

def direct_scan(
    entry_path: str,
    languages: Optional[List[str]] = None,
    exclude_dirs: Optional[List[str]] = None,
) -> Dict:
    """
    直扫基线：对 C/C++/Rust 进行启发式扫描，输出结构化 JSON。
    - 改进：委派至模块化检查器（oh_sec.checkers），统一规则与置信度模型。
    """
    base = Path(entry_path).resolve()
    files = list(_iter_source_files(entry_path, languages, exclude_dirs))

    # 按语言分组
    c_like_exts = {".c", ".cpp", ".h", ".hpp"}
    rust_exts = {".rs"}
    c_files: List[Path] = [p for p in files if p.suffix.lower() in c_like_exts]
    r_files: List[Path] = [p for p in files if p.suffix.lower() in rust_exts]

    # 调用检查器（保持相对路径，基于 base_path 解析）
    issues_c = analyze_c_files(str(base), [str(p) for p in c_files]) if c_files else []
    issues_r = analyze_rust_files(str(base), [str(p) for p in r_files]) if r_files else []
    issues: List[Issue] = issues_c + issues_r


    summary: Dict[str, Any] = {
        "total": len(issues),
        "by_language": {"c/cpp": 0, "rust": 0},
        "by_category": {},
        "top_risk_files": [],
        "scanned_files": len(files),
        "scanned_root": str(base),
    }
    file_score: Dict[str, int] = {}
    # Safely update language/category counts with explicit typing
    lang_counts = cast(Dict[str, int], summary["by_language"])
    cat_counts = cast(Dict[str, int], summary["by_category"])
    for it in issues:
        lang_counts[it.language] = lang_counts.get(it.language, 0) + 1
        cat_counts[it.category] = cat_counts.get(it.category, 0) + 1
        file_score[it.file] = file_score.get(it.file, 0) + 1
    # Top 风险文件
    summary["top_risk_files"] = [f for f, _ in sorted(file_score.items(), key=lambda x: x[1], reverse=True)[:10]]

    result = {
        "summary": summary,
        "issues": [asdict(i) for i in issues],
    }
    return result


def format_markdown_report(result_json: Dict) -> str:
    """
    将结构化 JSON 转为 Markdown 可读报告。
    """
    s = result_json.get("summary", {})
    issues: List[Dict] = result_json.get("issues", [])
    md: List[str] = []
    md.append("# Jarvis 安全问题分析报告（直扫基线）")
    md.append("")
    md.append(f"- 扫描根目录: {s.get('scanned_root', '')}")
    md.append(f"- 扫描文件数: {s.get('scanned_files', 0)}")
    md.append(f"- 检出问题总数: {s.get('total', 0)}")
    md.append("")
    md.append("## 统计概览")
    by_lang = s.get("by_language", {})
    md.append(f"- 按语言: c/cpp={by_lang.get('c/cpp', 0)}, rust={by_lang.get('rust', 0)}")
    md.append("- 按类别:")
    for k, v in s.get("by_category", {}).items():
        md.append(f"  - {k}: {v}")
    if s.get("top_risk_files"):
        md.append("- Top 风险文件:")
        for f in s["top_risk_files"]:
            md.append(f"  - {f}")
    md.append("")
    md.append("## 详细问题")
    for i, it in enumerate(issues, start=1):
        md.append(f"### [{i}] {it.get('file')}:{it.get('line')} ({it.get('language')}, {it.get('category')})")
        md.append(f"- 模式: {it.get('pattern')}")
        md.append(f"- 证据: `{it.get('evidence')}`")
        md.append(f"- 描述: {it.get('description')}")
        md.append(f"- 建议: {it.get('suggestion')}")
        md.append(f"- 置信度: {it.get('confidence')}, 严重性: {it.get('severity')}")
        md.append("")
    return "\n".join(md)


def run_with_agent(
    entry_path: str,
    languages: Optional[List[str]] = None,
    llm_group: Optional[str] = None,
    report_file: Optional[str] = None,
    cluster_limit: int = 50,
) -> str:
    """
    使用单Agent逐条子任务分析模式运行（与 jarvis.jarvis_sec.__init__ 中保持一致）。
    - 先执行本地直扫，生成候选问题
    - 为每条候选创建一次普通Agent任务进行分析与验证
    - 聚合为最终报告（JSON + Markdown）返回

    其他：
    - llm_group: 本次分析使用的模型组（仅透传给 Agent，不修改全局配置）
    - report_file: JSONL 报告文件路径（可选，透传）
    - cluster_limit: 聚类时每批次最多处理的告警数（默认 50），当单个文件告警过多时按批次进行聚类
    """
    from jarvis.jarvis_sec import run_security_analysis  # 延迟导入，避免循环
    return run_security_analysis(
        entry_path,
        languages=languages,
        llm_group=llm_group,
        report_file=report_file,
        cluster_limit=cluster_limit,
    )


__all__ = [
    "Issue",
    "direct_scan",
    "format_markdown_report",
    "run_with_agent",
]