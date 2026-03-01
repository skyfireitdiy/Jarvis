"""Command-line interface for Jarvis Rules Index.

This module provides a typer-based CLI for viewing and managing
Jarvis built-in rules index.
"""

import typer

from jarvis.jarvis_rules_index.core import get_rules_index_formatted
from jarvis.jarvis_utils.output import PrettyOutput

app = typer.Typer(help="Jarvis 规则索引命令行工具")


@app.command()
def show(
    as_json: bool = typer.Option(False, "--json", help="以JSON格式输出"),
    raw: bool = typer.Option(False, "--raw", help="原始输出（无格式化）"),
) -> None:
    """显示所有可用规则索引

    列出所有可用的Jarvis规则及其描述，包括内置规则、项目规则、全局规则等。
    """
    formatted_output = get_rules_index_formatted(as_json=as_json)

    if raw:
        # 原始输出，不使用PrettyOutput格式化
        print(formatted_output)
    else:
        # 使用PrettyOutput美化输出
        PrettyOutput.auto_print("📋 " + formatted_output, lang="markdown")


def cli() -> None:
    """Main entry point for the CLI."""
    app()


def main() -> None:
    """Main entry point for the script."""
    cli()


if __name__ == "__main__":
    main()
