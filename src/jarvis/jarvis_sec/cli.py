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

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Jarvis 安全演进套件（单Agent逐条子任务分析）",
)


@app.command("agent", help="Agent模式（单Agent逐条子任务分析）")
def agent(
    path: str = typer.Option(
        ".", "--path", "-p", help="待分析的根目录（默认当前目录）"
    ),
    llm_group: Optional[str] = typer.Option(
        None,
        "--llm-group",
        "-g",
        help="使用的模型组（仅对本次运行生效，不修改全局配置）",
    ),
    output: Optional[str] = typer.Option(
        "report.md",
        "--output",
        "-o",
        help="最终报告输出路径（默认 ./report.md）。如果后缀为 .csv，则输出 CSV 格式；否则输出 Markdown 格式",
    ),
    cluster_limit: int = typer.Option(
        50,
        "--cluster-limit",
        "-c",
        help="聚类每批最多处理的告警数（按文件分批聚类，默认50）",
    ),
    enable_verification: bool = typer.Option(
        True,
        "--enable-verification/--no-verification",
        help="是否启用二次验证（默认开启）",
    ),
    force_save_memory: bool = typer.Option(
        False,
        "--force-save-memory/--no-force-save-memory",
        help="强制使用记忆（默认关闭）",
    ),
) -> None:
    # 初始化环境，确保平台/模型等全局配置就绪（避免 NoneType 平台）
    try:
        init_env()
    except Exception:
        # 环境初始化失败不应阻塞CLI基础功能，继续后续流程
        pass

    # 若指定了模型组：仅对本次运行生效，透传给 Agent；不修改全局配置（无需 set_config）

    text: Optional[str] = None
    try:
        text = run_with_agent(
            path,
            llm_group=llm_group,
            cluster_limit=cluster_limit,
            enable_verification=enable_verification,
            force_save_memory=force_save_memory,
            output_file=output,
        )
    except Exception as e:
        try:
            PrettyOutput.auto_print(
                f"⚠️ [jarvis_sec] Agent 分析过程出错，将回退到直扫基线（fast）：{e}"
            )
        except Exception:
            pass
        text = None

    if not text or not str(text).strip():
        try:
            PrettyOutput.auto_print(
                "⚠️ [jarvis_sec] Agent 无输出，回退到直扫基线（fast）。"
            )
        except Exception:
            pass
        result = direct_scan(path)
        # 根据输出文件后缀选择格式
        if output and output.lower().endswith(".csv"):
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

    if output:
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
            p = Path(output)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(md_text, encoding="utf-8")
            try:
                PrettyOutput.auto_print(f"✅ [jarvis_sec] Markdown 报告已写入: {p}")
            except Exception:
                pass
        except Exception as e:
            try:
                PrettyOutput.auto_print(f"❌ [jarvis_sec] 写入Markdown报告失败: {e}")
            except Exception:
                pass
    PrettyOutput.auto_print(text)


def main() -> int:
    app()
    return 0


if __name__ == "__main__":
    sys.exit(main())
