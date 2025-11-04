# -*- coding: utf-8 -*-
"""
OpenHarmony 安全演进套件 —— 命令行入口（Typer 版本）

用法示例：
- Agent模式（单Agent，逐条子任务分析）
  python -m jarvis.jarvis_sec.cli agent --path ./target_project

可选参数：

- --output: 最终Markdown报告输出路径（默认 ./report.md）
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from jarvis.jarvis_utils.utils import init_env
# removed: set_config import（避免全局覆盖模型组配置）
from jarvis.jarvis_sec.workflow import run_with_agent, run_security_analysis_fast

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="OpenHarmony 安全演进套件（单Agent逐条子任务分析）",
)




@app.command("agent", help="Agent模式（单Agent逐条子任务分析）")
def agent(
    path: str = typer.Option(..., "--path", "-p", help="待分析的根目录"),

    llm_group: Optional[str] = typer.Option(
        None, "--llm-group", "-g", help="使用的模型组（仅对本次运行生效，不修改全局配置）"
    ),
    output: Optional[str] = typer.Option(
        "report.md", "--output", "-o", help="最终Markdown报告输出路径（默认 ./report.md）"
    ),
    batch_limit: int = typer.Option(
        10, "--batch-limit", "-n", help="批量处理条数（一次最多处理一个文件的n条告警）"
    ),
) -> None:
    # 初始化环境，确保平台/模型等全局配置就绪（避免 NoneType 平台）
    try:
        init_env("欢迎使用 Jarvis-OpenHarmony 安全套件！", None)
    except Exception:
        # 环境初始化失败不应阻塞CLI基础功能，继续后续流程
        pass

    # 若指定了模型组：仅对本次运行生效，透传给 Agent；不修改全局配置（无需 set_config）


    text: Optional[str] = None
    try:
        text = run_with_agent(
            path,
            llm_group=llm_group,
            batch_limit=batch_limit,
        )
    except Exception as e:
        try:
            typer.secho(f"[jarvis_sec] Agent 分析过程出错，将回退到直扫基线（fast）：{e}", fg=typer.colors.YELLOW, err=True)
        except Exception:
            pass
        text = None

    if not text or not str(text).strip():
        try:
            typer.secho("[jarvis_sec] Agent 无输出，回退到直扫基线（fast）。", fg=typer.colors.YELLOW, err=True)
        except Exception:
            pass
        text = run_security_analysis_fast(path)

    if output:
        try:
            md_text = text or ""
            try:
                lines = (text or "").splitlines()
                idx = -1
                for i, ln in enumerate(lines):
                    if ln.strip().startswith("# OpenHarmony 安全问题分析报告"):
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
                typer.secho(f"[jarvis_sec] Markdown 报告已写入: {p}", fg=typer.colors.GREEN)
            except Exception:
                pass
        except Exception as e:
            try:
                typer.secho(f"[jarvis_sec] 写入Markdown报告失败: {e}", fg=typer.colors.RED, err=True)
            except Exception:
                pass
    typer.echo(text)


def main() -> int:
    app()
    return 0


if __name__ == "__main__":
    sys.exit(main())