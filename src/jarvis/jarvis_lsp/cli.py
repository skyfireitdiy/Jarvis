"""CLI 接口模块

该模块提供 jarvis-lsp 和 jlsp 命令行工具的接口。
"""

import asyncio
import json
from typing import Optional

import typer

from jarvis.jarvis_lsp import __version__
from jarvis.jarvis_lsp.client import LSPClient, SymbolInfo
from jarvis.jarvis_lsp.config import LSPConfigReader
from jarvis.jarvis_utils.output import PrettyOutput

app = typer.Typer(
    help="Jarvis LSP 客户端工具 - 与语言服务器通信的命令行接口",
    no_args_is_help=True,
)


def format_symbols_human(symbols: list[SymbolInfo], file_path: str) -> str:
    """格式化符号列表为人类可读格式

    Args:
        symbols: 符号列表
        file_path: 文件路径

    Returns:
        格式化后的字符串
    """
    lines = [f"📋 符号列表 ({file_path})", ""]

    for symbol in symbols:
        lines.append(f"{symbol.kind.title()}: {symbol.name}")
        lines.append(f"  位置: 第 {symbol.line + 1} 行")
        if symbol.description:
            lines.append(f"  描述: {symbol.description}")
        lines.append("")

    return "\n".join(lines)


def format_symbols_json(symbols: list[SymbolInfo], file_path: str) -> str:
    """格式化符号列表为 JSON 格式

    Args:
        symbols: 符号列表
        file_path: 文件路径

    Returns:
        JSON 字符串
    """
    data = {
        "file": file_path,
        "symbols": [
            {
                "name": s.name,
                "kind": s.kind,
                "line": s.line,
                "column": s.column,
                "description": s.description,
            }
            for s in symbols
        ],
    }
    return json.dumps(data, indent=2, ensure_ascii=False)


@app.command("symbols")
def symbols_command(
    file_path: str = typer.Argument(..., help="目标文件路径"),
    language: Optional[str] = typer.Option(
        None,
        "--language",
        "-l",
        help="指定语言（如 python, rust, javascript）",
    ),
    server_path: Optional[str] = typer.Option(
        None,
        "--server-path",
        help="指定 LSP 服务器可执行文件路径（覆盖配置）",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="以 JSON 格式输出",
    ),
    kind: Optional[str] = typer.Option(
        None,
        "--kind",
        "-k",
        help="过滤符号类型（如 function, class, variable）",
    ),
) -> None:
    """列出文件中的符号

    列出指定文件中的函数、类、变量等符号信息。
    """
    # 读取配置
    config_reader = LSPConfigReader()

    # 检测语言
    if language is None:
        language = config_reader.detect_language(file_path)
        if language is None:
            PrettyOutput.auto_print(
                "❌ 错误: 无法检测文件语言，请使用 --language 参数指定"
            )
            raise typer.Exit(code=1)

    # 获取语言配置
    lang_config = config_reader.get_language_config(language)
    if lang_config is None:
        PrettyOutput.auto_print(
            f"❌ 错误: 未找到语言 '{language}' 的配置"
        )
        PrettyOutput.auto_print(
            "请在 ~/.jarvis/config.yaml 的 lsp.languages 节中添加配置"
        )
        raise typer.Exit(code=1)

    # 覆盖服务器路径
    command = lang_config.command
    args = lang_config.args
    if server_path:
        command = server_path

    # 运行异步任务
    async def run() -> list[SymbolInfo]:
        client = LSPClient(command=command, args=args)
        try:
            await client.initialize()
            symbols = await client.document_symbol(file_path)
            return symbols
        finally:
            await client.shutdown()

    symbols = asyncio.run(run())

    # 过滤符号类型
    if kind:
        symbols = [s for s in symbols if s.kind.lower() == kind.lower()]

    # 输出结果
    if as_json:
        PrettyOutput.auto_print(format_symbols_json(symbols, file_path))
    else:
        PrettyOutput.auto_print(format_symbols_human(symbols, file_path))


@app.command("version")
def version_command() -> None:
    """显示版本信息"""
    PrettyOutput.auto_print(f"jarvis-lsp version {__version__}")


def main() -> None:
    """主入口函数"""
    app()


def jlsp_main() -> None:
    """jlsp 命令入口函数"""
    app()


if __name__ == "__main__":
    main()
