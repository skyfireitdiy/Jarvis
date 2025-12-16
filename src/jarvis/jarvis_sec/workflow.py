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

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, cast

from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_sec.checkers import analyze_c_files
from jarvis.jarvis_sec.checkers import analyze_rust_files
from jarvis.jarvis_sec.types import Issue

# ---------------------------
# 数据结构
# ---------------------------

# Issue dataclass is provided by jarvis.jarvis_sec.types to avoid circular imports


# ---------------------------
# 工具函数
# ---------------------------


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
    excludes = set(
        exclude_dirs
        or [
            ".git",
            "build",
            "out",
            "target",
            "dist",
            "bin",
            "obj",
            "third_party",
            "vendor",
            "deps",
            "dependencies",
            "libs",
            "libraries",
            "external",
            "node_modules",
            "test",
            "tests",
            "__tests__",
            "spec",
            "testsuite",
            "testdata",
            "benchmark",
            "benchmarks",
            "perf",
            "performance",
            "bench",
            "benches",
            "profiling",
            "profiler",
            "example",
            "examples",
            "tmp",
            "temp",
            "cache",
            ".cache",
            "docs",
            "doc",
            "documentation",
            "generated",
            "gen",
            "mocks",
            "fixtures",
            "samples",
            "sample",
            "playground",
            "sandbox",
        ]
    )

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


# ---------------------------
# 汇总与报告
# ---------------------------


def direct_scan(
    entry_path: str,
    languages: Optional[List[str]] = None,
    exclude_dirs: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    直扫基线：对 C/C++/Rust 进行启发式扫描，输出结构化 JSON。
    - 改进：委派至模块化检查器（oh_sec.checkers），统一规则与置信度模型。
    """
    base = Path(entry_path).resolve()
    # 计算实际使用的排除目录列表
    default_excludes = [
        ".git",
        "build",
        "out",
        "target",
        "dist",
        "bin",
        "obj",
        "third_party",
        "vendor",
        "deps",
        "dependencies",
        "libs",
        "libraries",
        "external",
        "node_modules",
        "test",
        "tests",
        "__tests__",
        "spec",
        "testsuite",
        "testdata",
        "benchmark",
        "benchmarks",
        "perf",
        "performance",
        "bench",
        "benches",
        "profiling",
        "profiler",
        "example",
        "examples",
        "tmp",
        "temp",
        "cache",
        ".cache",
        "docs",
        "doc",
        "documentation",
        "generated",
        "gen",
        "mocks",
        "fixtures",
        "samples",
        "sample",
        "playground",
        "sandbox",
    ]
    actual_excludes = exclude_dirs if exclude_dirs is not None else default_excludes

    # 检查代码库中实际存在的排除目录
    excludes_set = set(actual_excludes)
    actual_excluded_dirs = []
    for item in base.rglob("*"):
        if item.is_dir() and item.name in excludes_set:
            rel_path = item.relative_to(base)
            if str(rel_path) not in actual_excluded_dirs:
                actual_excluded_dirs.append(str(rel_path))

    if actual_excluded_dirs:
        PrettyOutput.auto_print("[jarvis-sec] 实际排除的目录:")
        for dir_path in sorted(actual_excluded_dirs):
            PrettyOutput.auto_print(f"  - {dir_path}")
    else:
        PrettyOutput.auto_print(
            f"[jarvis-sec] 未发现需要排除的目录（配置的排除目录: {', '.join(sorted(actual_excludes))}）"
        )

    files = list(_iter_source_files(entry_path, languages, exclude_dirs))

    # 按语言分组
    c_like_exts = {".c", ".cpp", ".h", ".hpp"}
    rust_exts = {".rs"}
    c_files: List[Path] = [p for p in files if p.suffix.lower() in c_like_exts]
    r_files: List[Path] = [p for p in files if p.suffix.lower() in rust_exts]

    # 调用检查器（保持相对路径，基于 base_path 解析）
    issues_c = analyze_c_files(str(base), [str(p) for p in c_files]) if c_files else []
    issues_r = (
        analyze_rust_files(str(base), [str(p) for p in r_files]) if r_files else []
    )
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
    summary["top_risk_files"] = [
        f for f, _ in sorted(file_score.items(), key=lambda x: x[1], reverse=True)[:10]
    ]

    result = {
        "summary": summary,
        "issues": [asdict(i) for i in issues],
    }
    return result


def format_markdown_report(result_json: Dict[str, Any]) -> str:
    """
    将结构化 JSON 转为 Markdown 可读报告。
    """
    s = result_json.get("summary", {})
    issues: List[Dict[str, Any]] = result_json.get("issues", [])
    md: List[str] = []
    md.append("# Jarvis 安全问题分析报告（直扫基线）")
    md.append("")
    md.append(f"- 扫描根目录: {s.get('scanned_root', '')}")
    md.append(f"- 扫描文件数: {s.get('scanned_files', 0)}")
    md.append(f"- 检出问题总数: {s.get('total', 0)}")
    md.append("")
    md.append("## 统计概览")
    by_lang = s.get("by_language", {})
    md.append(
        f"- 按语言: c/cpp={by_lang.get('c/cpp', 0)}, rust={by_lang.get('rust', 0)}"
    )
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
        md.append(
            f"### [{i}] {it.get('file')}:{it.get('line')} ({it.get('language')}, {it.get('category')})"
        )
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
    exclude_dirs: Optional[List[str]] = None,
    enable_verification: bool = True,
    force_save_memory: bool = False,
    output_file: Optional[str] = None,
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
    - exclude_dirs: 要排除的目录列表（可选），默认已包含构建产物（build, out, target, dist, bin, obj）、依赖目录（third_party, vendor, deps, dependencies, libs, libraries, external, node_modules）、测试目录（test, tests, __tests__, spec, testsuite, testdata）、性能测试目录（benchmark, benchmarks, perf, performance, bench, benches, profiling, profiler）、示例目录（example, examples）、临时/缓存（tmp, temp, cache, .cache）、文档（docs, doc, documentation）、生成代码（generated, gen）和其他（mocks, fixtures, samples, sample, playground, sandbox）
    - enable_verification: 是否启用二次验证（默认 True），关闭后分析Agent确认的问题将直接写入报告
    """
    from jarvis.jarvis_sec import run_security_analysis  # 延迟导入，避免循环

    return run_security_analysis(
        entry_path,
        languages=languages,
        llm_group=llm_group,
        report_file=report_file,
        cluster_limit=cluster_limit,
        exclude_dirs=exclude_dirs,
        enable_verification=enable_verification,
        force_save_memory=force_save_memory,
        output_file=output_file,
    )


__all__ = [
    "Issue",
    "direct_scan",
    "format_markdown_report",
    "run_with_agent",
]
