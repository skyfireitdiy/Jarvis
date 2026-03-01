"""Command-line interface for Jarvis Rules Index.

This module provides a typer-based CLI for viewing and managing
Jarvis built-in rules index.
"""

import typer

from jarvis.jarvis_rules_index.core import format_rules_index, get_rules_index
from jarvis.jarvis_utils.output import PrettyOutput

app = typer.Typer(help="Jarvis 规则索引命令行工具")


@app.command()
def show(
    as_json: bool = typer.Option(False, "--json", help="以JSON格式输出"),
    raw: bool = typer.Option(False, "--raw", help="原始输出（无格式化）"),
) -> None:
    """显示所有内置规则索引

    列出所有可用的Jarvis内置规则及其描述。
    """
    index = get_rules_index()
    formatted_output = format_rules_index(index, as_json=as_json)

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
