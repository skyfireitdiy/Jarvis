# -*- coding: utf-8 -*-
"""
Jarvis 安全演进套件 —— 命令行入口（Typer 版本）

用法示例：
- Agent模式（单Agent，逐条子任务分析）
  python -m jarvis.jarvis_sec.cli agent --path ./target_project
  python -m jarvis.jarvis_sec.cli agent  # 默认分析当前目录

可选参数：

- --path, -p: 待分析的根目录（默认当前目录）
- --output, -o: 最终报告输出路径（默认 ./report.md）。如果后缀为 .csv，则输出 CSV 格式；否则输出 Markdown 格式
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from typing import Dict
from typing import Optional

import typer

from jarvis.jarvis_sec.report import aggregate_issues
from jarvis.jarvis_sec.report import format_csv_report
from jarvis.jarvis_utils.output import PrettyOutput

# removed: set_config import（避免全局覆盖模型组配置）
from jarvis.jarvis_sec.workflow import direct_scan
from jarvis.jarvis_sec.workflow import (
    format_markdown_report as format_markdown_report_workflow,
)
from jarvis.jarvis_sec.workflow import run_with_agent
from jarvis.jarvis_utils.utils import init_env


# ---------------------------
# 常量定义
# ---------------------------

JSEC_DIRNAME = "sec"
CONFIG_JSON = "config.json"


# ---------------------------
# 配置文件管理
# ---------------------------


def _get_config_path() -> Path:
    """获取配置文件路径"""
    return Path(".") / ".jarvis" / JSEC_DIRNAME / CONFIG_JSON


def _load_config() -> Dict[str, Any]:
    """
    从配置文件加载配置。
    返回包含所有配置项的字典，如果文件不存在或读取失败则返回默认配置。
    """
    import json

    config_path = _get_config_path()
    default_config = {
        "target": ".",
        "exclude_dirs": [
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
        ],
        "output": {"format": "markdown", "file": "report.md"},
        "analysis": {
            "cluster_limit": 50,
            "enable_verification": True,
            "force_save_memory": False,
        },
        "runtime": {"llm_group": None},
    }

    if not config_path.exists():
        return default_config

    try:
        with config_path.open("r", encoding="utf-8") as f:
            config = json.load(f)
            if not isinstance(config, dict):
                return default_config
            # 合并默认配置，确保所有必需的键都存在
            return {
                "target": config.get("target", default_config["target"]),
                "languages": config.get("languages", default_config["languages"]),
                "exclude_dirs": config.get(
                    "exclude_dirs", default_config["exclude_dirs"]
                ),
                "output": config.get("output", default_config["output"]),
                "analysis": config.get("analysis", default_config["analysis"]),
                "runtime": config.get("runtime", default_config["runtime"]),
            }
    except Exception:
        return default_config


def _save_config(config: Dict[str, Any]) -> None:
    """保存配置到文件"""
    import json

    config_path = _get_config_path()
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        PrettyOutput.auto_print(f"❌ [jsec-config] 保存配置失败: {e}")
        raise


def _filter_result_by_file(result: Dict[str, Any], target_file: str) -> Dict[str, Any]:
    """过滤扫描结果，只保留指定文件的问题"""
    target_file_normalized = str(Path(target_file).resolve())

    # 过滤 issues
    issues = result.get("issues", [])
    filtered_issues = [
        issue
        for issue in issues
        if str(Path(issue.get("file", "")).resolve()) == target_file_normalized
    ]

    # 更新统计
    result["issues"] = filtered_issues
    result["summary"]["total"] = len(filtered_issues)

    # 更新 top_risk_files（如果有的话）
    if filtered_issues:
        result["summary"]["top_risk_files"] = [target_file_normalized]
    else:
        result["summary"]["top_risk_files"] = []

    return result


app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Jarvis 安全演进套件（命令行工具）",
)


@app.command("config")
def config(
    target: Optional[str] = typer.Option(
        None, "--target", help="扫描目标（文件路径或目录路径）"
    ),
    languages: Optional[str] = typer.Option(
        None, "--languages", help="语言过滤（逗号分隔，如 c,cpp,rust）"
    ),
    exclude_dirs: Optional[str] = typer.Option(
        None, "--exclude-dirs", help="排除目录（逗号分隔）"
    ),
    output_format: Optional[str] = typer.Option(
        None, "--output-format", help="输出格式（csv/markdown）"
    ),
    output_file: Optional[str] = typer.Option(
        None, "--output-file", help="输出文件路径"
    ),
    cluster_limit: Optional[int] = typer.Option(
        None, "--cluster-limit", help="聚类限制（每批最多处理的告警数）"
    ),
    enable_verification: Optional[bool] = typer.Option(
        None,
        "--enable-verification/--no-verification",
        help="是否启用二次验证",
    ),
    force_save_memory: Optional[bool] = typer.Option(
        None,
        "--force-save-memory/--no-force-save-memory",
        help="是否强制使用记忆",
    ),
    llm_group: Optional[str] = typer.Option(None, "--llm-group", help="模型组"),
    show: bool = typer.Option(False, "--show", help="显示当前配置"),
    clear: bool = typer.Option(False, "--clear", help="清空配置"),
) -> None:
    """
    管理安全扫描配置文件（.jarvis/sec/config.json）。

    可以设置扫描目标（文件或目录）、语言过滤、排除目录、输出格式、分析参数等。
    这些配置会被 scan 命令自动读取和使用。

    示例:
      # 设置扫描目标为当前目录
      jsec config --target .

      # 设置扫描目标为指定文件
      jsec config --target ./src/main.c

      # 设置语言过滤和输出格式
      jsec config --languages c,cpp,rust --output-format csv

      # 设置分析参数
      jsec config --cluster-limit 30 --enable-verification

      # 查看当前配置
      jsec config --show

      # 清空配置
      jsec config --clear
    """
    # 读取现有配置
    current_config = _load_config()

    # 如果只是查看配置
    if show:
        import json

        PrettyOutput.auto_print(f"📋 [jsec-config] 当前配置文件: {_get_config_path()}")
        PrettyOutput.auto_print(
            json.dumps(current_config, ensure_ascii=False, indent=2)
        )
        return

    # 如果清空配置
    if clear:
        import json

        default_config = {
            "target": ".",
            "languages": ["c", "cpp", "h", "hpp", "rs"],
            "exclude_dirs": [],
            "output": {"format": "markdown", "file": "report.md"},
            "analysis": {
                "cluster_limit": 50,
                "enable_verification": True,
                "force_save_memory": False,
            },
            "runtime": {"llm_group": None},
        }
        _save_config(default_config)
        PrettyOutput.auto_print(f"✅ [jsec-config] 配置已清空: {_get_config_path()}")
        PrettyOutput.auto_print(
            json.dumps(default_config, ensure_ascii=False, indent=2)
        )
        return

    # 更新配置
    updated = False

    # 更新扫描目标
    if target is not None:
        current_config["target"] = target
        updated = True
        PrettyOutput.auto_print(f"✅ [jsec-config] 已设置扫描目标: {target}")

    # 更新语言过滤
    if languages is not None:
        lang_list = [s.strip() for s in languages.split(",") if s.strip()]
        if lang_list:
            current_config["languages"] = lang_list
            updated = True
            PrettyOutput.auto_print(
                f"✅ [jsec-config] 已设置语言过滤: {', '.join(lang_list)}"
            )

    # 更新排除目录
    if exclude_dirs is not None:
        exclude_list = [s.strip() for s in exclude_dirs.split(",") if s.strip()]
        if exclude_list:
            current_config["exclude_dirs"] = exclude_list
            updated = True
            PrettyOutput.auto_print(
                f"✅ [jsec-config] 已设置排除目录: {', '.join(exclude_list)}"
            )

    # 更新输出格式
    if output_format is not None:
        if output_format not in ["csv", "markdown"]:
            PrettyOutput.auto_print(
                f"❌ [jsec-config] 无效的 output-format: {output_format}，必须是 csv/markdown 之一"
            )
            raise typer.Exit(code=1)
        current_config["output"]["format"] = output_format
        updated = True
        PrettyOutput.auto_print(f"✅ [jsec-config] 已设置输出格式: {output_format}")

    if output_file is not None:
        current_config["output"]["file"] = output_file
        updated = True
        PrettyOutput.auto_print(f"✅ [jsec-config] 已设置输出文件: {output_file}")

    # 更新分析参数
    if cluster_limit is not None:
        current_config["analysis"]["cluster_limit"] = cluster_limit
        updated = True
        PrettyOutput.auto_print(f"✅ [jsec-config] 已设置聚类限制: {cluster_limit}")

    if enable_verification is not None:
        current_config["analysis"]["enable_verification"] = enable_verification
        updated = True
        status = "启用" if enable_verification else "禁用"
        PrettyOutput.auto_print(f"✅ [jsec-config] 已{status}二次验证")

    if force_save_memory is not None:
        current_config["analysis"]["force_save_memory"] = force_save_memory
        updated = True
        status = "启用" if force_save_memory else "禁用"
        PrettyOutput.auto_print(f"✅ [jsec-config] 已{status}强制记忆")

    # 更新运行时配置
    if llm_group is not None:
        current_config["runtime"]["llm_group"] = llm_group
        updated = True
        PrettyOutput.auto_print(f"✅ [jsec-config] 已设置模型组: {llm_group}")

    # 如果没有提供任何参数，提示用户
    if (
        not updated
        and target is None
        and languages is None
        and exclude_dirs is None
        and output_format is None
        and output_file is None
        and cluster_limit is None
        and enable_verification is None
        and force_save_memory is None
        and llm_group is None
    ):
        PrettyOutput.auto_print(
            "⚠️ [jsec-config] 未提供任何参数，使用 --show 查看当前配置，或使用 --help 查看帮助"
        )
        return

    # 保存配置
    if updated:
        import json

        _save_config(current_config)
        PrettyOutput.auto_print(f"✅ [jsec-config] 配置已保存: {_get_config_path()}")
        PrettyOutput.auto_print(
            json.dumps(current_config, ensure_ascii=False, indent=2)
        )


@app.command("analyze", help="从外部JSON文件分析安全问题")
def analyze(
    input: str = typer.Argument(..., help="外部JSON文件路径（安全问题列表）"),
    output_format: Optional[str] = typer.Option(
        None, "--output-format", help="输出格式（csv/markdown）"
    ),
    output_file: Optional[str] = typer.Option(
        None, "--output-file", help="输出文件路径"
    ),
    cluster_limit: Optional[int] = typer.Option(
        None, "--cluster-limit", help="聚类限制（每批最多处理的告警数）"
    ),
    enable_verification: Optional[bool] = typer.Option(
        None,
        "--enable-verification/--no-verification",
        help="是否启用二次验证",
    ),
    force_save_memory: Optional[bool] = typer.Option(
        None,
        "--force-save-memory/--no-force-save-memory",
        help="是否强制使用记忆",
    ),
) -> None:
    """
    从外部JSON文件分析安全问题。

    支持两种模式：
    1. 标准格式：直接分析
    2. 非标准格式：自动创建Agent学习格式并转换

    标准格式示例：
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

    示例:
      # 分析标准格式文件
      jsec analyze external_issues.json

      # 分析非标准格式文件（自动转换）
      jsec analyze custom_tool_output.json

      # 指定输出格式
      jsec analyze issues.json --output-format csv --output-file report.csv
    """
    # 初始化环境
    try:
        init_env()
    except Exception:
        pass

    from jarvis.jarvis_sec.workflow import analyze_from_json

    # 设置默认值
    if cluster_limit is None:
        cluster_limit = 50
    if enable_verification is None:
        enable_verification = True
    if force_save_memory is None:
        force_save_memory = False

    PrettyOutput.auto_print(f"📂 [jsec-analyze] 输入文件: {input}")

    try:
        # 执行分析
        result = analyze_from_json(
            input_file=input,
            cluster_limit=cluster_limit,
            enable_verification=enable_verification,
            force_save_memory=force_save_memory,
            output_file=output_file,
        )

        # 输出结果
        if output_file:
            PrettyOutput.auto_print(
                f"✅ [jsec-analyze] 分析完成，报告已保存到: {output_file}"
            )
        else:
            PrettyOutput.auto_print(result)

    except FileNotFoundError as e:
        PrettyOutput.auto_print(f"❌ [jsec-analyze] 文件不存在: {e}")
        raise typer.Exit(code=1)
    except RuntimeError as e:
        PrettyOutput.auto_print(f"❌ [jsec-analyze] 分析失败: {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        PrettyOutput.auto_print(f"❌ [jsec-analyze] 未知错误: {e}")
        raise typer.Exit(code=1)


@app.command("scan", help="执行安全扫描（从配置文件读取）")
def scan() -> None:
    """
    执行安全扫描，从配置文件（.jarvis/sec/config.json）读取所有配置。

    如果配置文件不存在，会给出友好提示引导用户使用 config 命令。

    支持扫描指定文件或目录：
    - 文件：扫描该文件所在目录，然后过滤只保留该文件的问题
    - 目录：扫描该目录下的所有文件

    示例:
      # 首次使用：先设置配置
      jsec config --target ./src

      # 执行扫描
      jsec scan

      # 扫描单个文件
      jsec config --target ./src/main.c
      jsec scan
    """
    # 初始化环境
    try:
        init_env()
    except Exception:
        # 环境初始化失败不应阻塞CLI基础功能，继续后续流程
        pass

    # 加载配置
    config = _load_config()
    config_path = _get_config_path()

    # 检查配置文件是否存在（使用默认值说明文件不存在）
    if not config_path.exists():
        PrettyOutput.auto_print(f"❌ [jsec-scan] 未找到配置文件: {config_path}")
        PrettyOutput.auto_print(
            "💡 [jsec-scan] 请先使用 'jsec config' 命令设置扫描配置"
        )
        PrettyOutput.auto_print(
            "💡 [jsec-scan] 示例: jsec config --scope-type directory --target ./src"
        )
        raise typer.Exit(code=1)

    # 读取配置参数
    target = config.get("target", ".")
    languages = config.get("languages", None)
    exclude_dirs = config.get("exclude_dirs", None)
    output_config = config.get("output", {})
    output_format = output_config.get("format", "markdown")
    output_file = output_config.get("file", "report.md")
    analysis = config.get("analysis", {})
    cluster_limit = analysis.get("cluster_limit", 50)
    enable_verification = analysis.get("enable_verification", True)
    force_save_memory = analysis.get("force_save_memory", False)
    runtime = config.get("runtime", {})
    llm_group = runtime.get("llm_group", None)

    # 判断 target 是文件还是目录
    target_path = Path(target)
    if target_path.exists() and target_path.is_file():
        # 目标是文件：扫描文件所在目录，然后过滤
        scan_dir = str(target_path.parent)
        filter_file = str(target_path.resolve())
        PrettyOutput.auto_print(f"📄 [jsec-scan] 扫描文件: {filter_file}")
    elif target_path.exists() and target_path.is_dir():
        # 目标是目录：扫描该目录
        scan_dir = str(target_path)
        filter_file = None
        PrettyOutput.auto_print(f"📁 [jsec-scan] 扫描目录: {scan_dir}")
    else:
        # 默认：扫描当前目录
        scan_dir = "."
        filter_file = None
        PrettyOutput.auto_print(f"📁 [jsec-scan] 扫描目录: {scan_dir}")

    # 根据输出格式调整 output_file 后缀
    if output_format == "csv" and not output_file.lower().endswith(".csv"):
        output_file = (
            output_file.rsplit(".", 1)[0] + ".csv"
            if "." in output_file
            else output_file + ".csv"
        )
    elif output_format == "markdown" and output_file.lower().endswith(".csv"):
        output_file = (
            output_file.rsplit(".", 1)[0] + ".md"
            if "." in output_file
            else output_file + ".md"
        )

    # 设置模型组（如果指定）
    if llm_group:
        from jarvis.jarvis_utils.config import set_llm_group

        set_llm_group(llm_group)

    # 执行扫描
    text: Optional[str] = None
    try:
        text = run_with_agent(
            scan_dir,
            languages=languages,
            cluster_limit=cluster_limit,
            enable_verification=enable_verification,
            force_save_memory=force_save_memory,
            exclude_dirs=exclude_dirs,
            output_file=output_file,
        )
    except Exception as e:
        try:
            PrettyOutput.auto_print(
                f"⚠️ [jsec-scan] Agent 分析过程出错，将回退到直扫基线（fast）：{e}"
            )
        except Exception:
            pass
        text = None

    if not text or not str(text).strip():
        try:
            PrettyOutput.auto_print(
                "⚠️ [jsec-scan] Agent 无输出，回退到直扫基线（fast）。"
            )
        except Exception:
            pass
        result = direct_scan(scan_dir, languages=languages, exclude_dirs=exclude_dirs)
        # 如果指定了文件过滤，过滤结果
        if filter_file:
            result = _filter_result_by_file(result, filter_file)
        # 根据输出文件后缀选择格式
        if output_file and output_file.lower().endswith(".csv"):
            # 使用 report.py 中的函数来格式化 CSV
            report_json = aggregate_issues(
                result.get("issues", []),
                scanned_root=result.get("summary", {}).get("scanned_root"),
                scanned_files=result.get("summary", {}).get("scanned_files"),
            )
            text = format_csv_report(report_json)
        else:
            # 使用 workflow.py 中的 format_markdown_report（与 direct_scan 返回结构匹配）
            text = format_markdown_report_workflow(result)

    if output_file:
        try:
            md_text = text or ""
            try:
                lines = (text or "").splitlines()
                idx = -1
                for i, ln in enumerate(lines):
                    if ln.strip().startswith("# Jarvis 安全问题分析报告"):
                        idx = i
                        break
                if idx >= 0:
                    md_text = "\n".join(lines[idx:])
            except Exception:
                md_text = text or ""
            p = Path(output_file)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(md_text, encoding="utf-8")
            try:
                PrettyOutput.auto_print(f"✅ [jsec-scan] 报告已写入: {p}")
            except Exception:
                pass
        except Exception as e:
            try:
                PrettyOutput.auto_print(f"❌ [jsec-scan] 写入报告失败: {e}")
            except Exception:
                pass
    PrettyOutput.auto_print(text)


def main() -> int:
    app()
    return 0


if __name__ == "__main__":
    sys.exit(main())
