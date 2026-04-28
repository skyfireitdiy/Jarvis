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
from jarvis.jarvis_utils.input import get_single_line_input
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
    - report_file: JSONL 报告文件路径（可选，透传）
    - cluster_limit: 聚类时每批次最多处理的告警数（默认 50），当单个文件告警过多时按批次进行聚类
    - exclude_dirs: 要排除的目录列表（可选），默认已包含构建产物（build, out, target, dist, bin, obj）、依赖目录（third_party, vendor, deps, dependencies, libs, libraries, external, node_modules）、测试目录（test, tests, __tests__, spec, testsuite, testdata）、性能测试目录（benchmark, benchmarks, perf, performance, bench, benches, profiling, profiler）、示例目录（example, examples）、临时/缓存（tmp, temp, cache, .cache）、文档（docs, doc, documentation）、生成代码（generated, gen）和其他（mocks, fixtures, samples, sample, playground, sandbox）
    - enable_verification: 是否启用二次验证（默认 True），关闭后分析Agent确认的问题将直接写入报告
    """
    from jarvis.jarvis_sec import run_security_analysis  # 延迟导入，避免循环

    return run_security_analysis(
        entry_path,
        languages=languages,
        report_file=report_file,
        cluster_limit=cluster_limit,
        exclude_dirs=exclude_dirs,
        enable_verification=enable_verification,
        force_save_memory=force_save_memory,
        output_file=output_file,
    )


# ---------------------------
# 外部格式分析支持
# ---------------------------


def _validate_format(data: Any) -> bool:
    """
    验证外部数据是否符合标准 Issue 格式。

    标准格式：
    {
        "issues": [
            {
                "language": "c",
                "category": "memory",
                "pattern": "strcpy",
                "file": "src/main.c",
                "line": 42,
                "evidence": "strcpy(dest, src)",
                "description": "Unsafe string copy",
                "suggestion": "Use strncpy instead",
                "confidence": 0.8,
                "severity": "high"
            }
        ]
    }

    或者直接是一个数组：[Issue, ...]
    """
    if isinstance(data, list):
        # 直接是数组格式
        if not data:
            return False
        item = data[0]
        return isinstance(item, dict) and all(
            k in item
            for k in [
                "language",
                "category",
                "pattern",
                "file",
                "line",
                "evidence",
                "description",
                "suggestion",
                "confidence",
            ]
        )
    elif isinstance(data, dict):
        # 对象格式，检查是否有 "issues" 字段
        if "issues" not in data:
            return False
        issues = data["issues"]
        if not isinstance(issues, list) or not issues:
            return False
        item = issues[0]
        return isinstance(item, dict) and all(
            k in item
            for k in [
                "language",
                "category",
                "pattern",
                "file",
                "line",
                "evidence",
                "description",
                "suggestion",
                "confidence",
            ]
        )
    return False


def _create_conversion_agent(
    input_file: str,
    output_file: str,
) -> Any:
    """
    创建转换 Agent，学习外部文件格式并生成转换脚本。

    参数：
    - input_file: 外部 JSON 文件路径
    - output_file: 输出标准格式 JSON 文件路径

    返回：
    - 转换后的标准格式数据（字典）

    异常：
    - 转换失败时抛出 RuntimeError
    """
    import json
    import tempfile

    from jarvis.jarvis_agent import Agent
    from jarvis.jarvis_utils.output import PrettyOutput

    # 读取外部文件样本
    input_path = Path(input_file)
    if not input_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {input_file}")

    with input_path.open("r", encoding="utf-8") as f:
        external_data = json.load(f)

    # 构建转换提示词
    conversion_prompt = f"""# 任务：格式转换脚本生成

## 目标
你需要分析外部扫描工具的 JSON 格式，并编写一个 Python 脚本将其转换为标准的安全问题格式。

## 外部数据样本
```json
{json.dumps(external_data, indent=2, ensure_ascii=False)[:5000]}
```

## 标准格式
```json
{{
    "issues": [
        {{
            "language": "c",
            "category": "memory",
            "pattern": "strcpy",
            "file": "src/main.c",
            "line": 42,
            "evidence": "strcpy(dest, src)",
            "description": "Unsafe string copy",
            "suggestion": "Use strncpy instead",
            "confidence": 0.8,
            "severity": "high"
        }}
    ]
}}
```

## 字段映射说明
- language: 编程语言（c/cpp/rust 等）
- category: 问题类别（memory/buffer/error_handling 等）
- pattern: 检测模式（函数名、API调用等）
- file: 源代码文件路径
- line: 代码行号（整数）
- evidence: 问题证据（代码片段）
- description: 问题描述
- suggestion: 修复建议
- confidence: 置信度（0-1 的浮点数）
- severity: 严重程度（low/medium/high/critical，可选，默认 medium）

## 要求
1. 编写一个 Python 脚本，读取 `{input_file}`，转换为标准格式，输出到 `{output_file}`
2. 脚本必须使用 json 库处理 JSON 文件
3. 如果外部数据中缺少某些字段，使用合理的默认值：
   - severity: "medium"
   - confidence: 0.5
   - language: 从文件扩展名推断（.c/.h -> c, .cpp/.hpp -> cpp, .rs -> rust）
4. 脚本必须有错误处理（try-except）
5. 输出完整的可执行 Python 脚本代码，不要包含任何解释文字

## 输出格式
只输出 Python 脚本代码，不要包含 markdown 标记或其他说明。
"""

    PrettyOutput.auto_print("📝 [jarvis-sec] 正在学习外部文件格式并生成转换脚本...")

    # 创建 Agent
    agent = Agent(
        system_prompt="""你是一个安全扫描格式转换专家。
你的任务是分析外部扫描工具的JSON格式，并生成Python转换脚本，将其转换为标准的安全问题格式。
""",
        name="format_converter",
        description="安全扫描格式转换专家",
        use_tools=["read_code", "execute_script"],
    )

    # 执行转换
    try:
        response = agent.run(conversion_prompt)

        # 提取脚本代码（移除可能的 markdown 标记）
        script = response.strip()
        if script.startswith("```python"):
            script = script[9:]
        if script.startswith("```"):
            script = script[3:]
        if script.endswith("```"):
            script = script[:-3]
        script = script.strip()

        # 保存转换脚本到临时文件
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            script_file = f.name
            f.write(script)

        PrettyOutput.auto_print(f"🔧 [jarvis-sec] 转换脚本已生成: {script_file}")

        # 执行转换脚本
        import subprocess

        result = subprocess.run(
            ["python3", script_file],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # 清理临时脚本文件
        try:
            Path(script_file).unlink()
        except Exception:
            pass

        if result.returncode != 0:
            raise RuntimeError(f"转换脚本执行失败: {result.stderr}")

        PrettyOutput.auto_print(f"✅ [jarvis-sec] 格式转换成功: {output_file}")

        # 读取转换后的数据
        output_path = Path(output_file)
        with output_path.open("r", encoding="utf-8") as f:
            converted_data = json.load(f)

        return converted_data

    except Exception as e:
        raise RuntimeError(f"格式转换失败: {e}") from e


def analyze_from_json(
    input_file: str,
    cluster_limit: int = 50,
    enable_verification: bool = True,
    force_save_memory: bool = False,
    output_file: Optional[str] = None,
) -> str:
    """
    从外部 JSON 文件分析安全问题。

    支持两种模式：
    1. 标准格式：直接分析
    2. 非标准格式：自动创建 Agent 学习格式并转换

    参数：
    - input_file: 外部 JSON 文件路径
    - cluster_limit: 聚类时每批次最多处理的告警数（默认 50）
    - enable_verification: 是否启用二次验证（默认 True）
    - force_save_memory: 是否强制保存记忆（默认 False）
    - output_file: 输出报告文件路径（可选）
    - max_retries: 格式转换最大重试次数（默认 3）

    返回：
    - 最终报告（字符串）

    异常：
    - 转换失败超过最大重试次数时抛出 RuntimeError
    """
    import json
    import tempfile

    from jarvis.jarvis_utils.output import PrettyOutput

    input_path = Path(input_file)
    if not input_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {input_file}")

    # 读取外部数据
    with input_path.open("r", encoding="utf-8") as f:
        external_data = json.load(f)

    # 检查格式
    if _validate_format(external_data):
        PrettyOutput.auto_print("✅ [jarvis-sec] 检测到标准格式，直接分析")
        candidates = (
            external_data
            if isinstance(external_data, list)
            else external_data["issues"]
        )
    else:
        PrettyOutput.auto_print("⚠️  [jarvis-sec] 检测到非标准格式，启动智能转换")

        # 尝试格式转换（无限重试直到用户取消）
        retries = 0
        converted_data = None

        while True:
            try:
                # 创建临时输出文件
                temp_output = ""
                with tempfile.NamedTemporaryFile(  # type: ignore[assignment]
                    mode="w", suffix=".json", delete=False, encoding="utf-8"
                ) as f:
                    temp_output = f.name

                # 执行转换
                converted_data = _create_conversion_agent(str(input_path), temp_output)

                # 验证转换结果
                if not _validate_format(converted_data):
                    raise RuntimeError("转换后的格式仍然不符合标准")

                # 提取 candidates 列表
                if isinstance(converted_data, list):
                    candidates = converted_data
                else:
                    candidates = converted_data.get("issues", [])

                # 保存转换后的文件用于后续使用
                converted_output = (
                    input_path.parent / f"{input_path.stem}_converted.json"
                )
                with Path(converted_output).open("w", encoding="utf-8") as f:
                    json.dump(converted_data, f, indent=2, ensure_ascii=False)
                PrettyOutput.auto_print(
                    f"💾 [jarvis-sec] 转换结果已保存: {converted_output}"
                )

                break

            except Exception as e:
                retries += 1
                PrettyOutput.auto_print(
                    f"❌ [jarvis-sec] 格式转换失败 (第 {retries} 次尝试): {e}"
                )

                # 询问用户是否重试
                PrettyOutput.auto_print(
                    "\n🤔 [jarvis-sec] 格式转换失败，是否继续重试？"
                )
                user_input = get_single_line_input(
                    "请输入 'y' 继续重试，或其他键取消: "
                )

                if user_input.lower() != "y":
                    PrettyOutput.auto_print("❌ [jarvis-sec] 用户取消操作")
                    raise RuntimeError("用户取消格式转换") from e

                PrettyOutput.auto_print("🔄 [jarvis-sec] 正在重试...")

    # 导入必要的模块
    from jarvis.jarvis_sec.utils import prepare_candidates as _prepare_candidates
    from jarvis.jarvis_sec.clustering import (  # type: ignore[attr-defined]
        process_clustering_phase as _process_clustering_phase,
    )
    from jarvis.jarvis_sec.verification import (
        process_verification_phase as _process_verification_phase,
    )
    from jarvis.jarvis_sec.file_manager import save_candidates
    from jarvis.jarvis_sec.report import build_json_and_markdown

    # 创建临时分析目录
    with tempfile.TemporaryDirectory() as temp_dir:
        sec_dir = Path(temp_dir)

        # 保存候选到 candidates.jsonl
        compact_candidates = _prepare_candidates(candidates)
        save_candidates(sec_dir, compact_candidates)

        PrettyOutput.auto_print(
            f"📊 [jarvis-sec] 已加载 {len(compact_candidates)} 个安全问题"
        )

        # 创建状态管理器（空实现）
        class DummyStatusManager:
            def update_clustering(self, **kwargs: Any) -> None:
                pass

            def update_verification(self, **kwargs: Any) -> None:
                pass

        status_mgr = DummyStatusManager()

        # 进度回调（空实现）
        def _progress_append(event: Any) -> None:
            pass

        # 创建报告写入函数
        def _append_report(record: Any) -> None:
            pass

        # 聚类阶段
        cluster_batches, invalid_clusters = _process_clustering_phase(
            compact_candidates,
            ".",  # entry_path（可以不是真实路径）
            [],  # languages
            cluster_limit,
            sec_dir,
            status_mgr,
            _progress_append,
            force_save_memory=force_save_memory,
        )

        # 验证阶段
        all_issues = _process_verification_phase(
            cluster_batches,
            ".",
            [],
            sec_dir,
            status_mgr,
            _progress_append,
            _append_report,
            enable_verification=enable_verification,
            force_save_memory=force_save_memory,
        )

        # 生成最终报告
        result = build_json_and_markdown(all_issues, str(sec_dir))  # type: ignore[arg-type]

        # 保存到输出文件（如果指定）
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("w", encoding="utf-8") as f:
                f.write(result)
            PrettyOutput.auto_print(f"📄 [jarvis-sec] 报告已保存: {output_file}")

        return result


__all__ = [
    "Issue",
    "direct_scan",
    "format_markdown_report",
    "run_with_agent",
    "analyze_from_json",
]
