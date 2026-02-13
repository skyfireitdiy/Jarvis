"""CLI 接口模块

该模块提供 jarvis-lsp 和 jlsp 命令行工具的接口。
"""

import asyncio
import json
import os
from typing import Optional

import typer

from jarvis.jarvis_lsp import __version__
from jarvis.jarvis_lsp.client import LocationInfo, SymbolInfo
from jarvis.jarvis_lsp.config import LSPConfigReader
from jarvis.jarvis_lsp.daemon_client import LSPDaemonClient
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


@app.command("document_symbols")
def document_symbols_command(
    file_path: str = typer.Argument(..., help="目标文件路径"),
    language: Optional[str] = typer.Option(
        None,
        "--language",
        "-l",
        help="指定语言（如 python, rust, javascript）",
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
    """列出文件中的文档符号

    列出指定文件中的函数、类、变量等符号信息。

    注意：此功能依赖于 LSP 守护进程和 LSP 服务器的 document/symbol 功能。
    如果服务器不支持此功能或响应超时，命令会失败。
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
        PrettyOutput.auto_print(f"❌ 错误: 未找到语言 '{language}' 的配置")
        PrettyOutput.auto_print(
            "请在 ~/.jarvis/config.yaml 的 lsp.languages 节中添加配置"
        )
        raise typer.Exit(code=1)

    project_path = os.getcwd()
    client = LSPDaemonClient()

    # 运行异步任务（使用守护进程）
    async def run() -> list[SymbolInfo]:
        # 通过守护进程获取文档符号
        symbols = await client.document_symbol(language, project_path, file_path)
        return symbols

    try:
        symbols = asyncio.run(run())
    except RuntimeError as e:
        PrettyOutput.auto_print(f"❌ 错误: {e}")
        raise typer.Exit(code=1)

    # 过滤符号类型
    if kind:
        symbols = [s for s in symbols if s.kind.lower() == kind.lower()]

    # 输出结果
    if as_json:
        PrettyOutput.auto_print(format_symbols_json(symbols, file_path))
    else:
        PrettyOutput.auto_print(format_symbols_human(symbols, file_path))


@app.command("symbol")
def symbol_command(
    query: str = typer.Argument(..., help="搜索查询字符串"),
    language: Optional[str] = typer.Option(
        None,
        "--language",
        "-l",
        help="指定语言（如 python, rust, javascript）",
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
    """在工作区中搜索符号

    在工作区中搜索匹配查询字符串的函数、类、变量等符号信息。

    注意：此功能依赖于 LSP 守护进程和 LSP 服务器的 workspace/symbol 功能。
    如果服务器不支持此功能或响应超时，命令会失败。
    """
    # 如果没有指定语言，默认使用 python
    if language is None:
        language = "python"

    project_path = os.getcwd()
    client = LSPDaemonClient()

    async def run() -> list[SymbolInfo]:
        # 通过守护进程获取符号
        symbols = await client.workspace_symbol(language, project_path, query)
        return symbols

    try:
        symbols = asyncio.run(run())
    except RuntimeError as e:
        PrettyOutput.auto_print(f"❌ 错误: {e}")
        raise typer.Exit(code=1)

    # 过滤符号类型
    if kind:
        symbols = [s for s in symbols if s.kind.lower() == kind.lower()]

    # 输出结果（使用空字符串作为文件路径，因为符号可能来自多个文件）
    if as_json:
        PrettyOutput.auto_print(format_symbols_json(symbols, ""))
    else:
        PrettyOutput.auto_print(format_symbols_human(symbols, ""))


def format_location_human(locations: list[LocationInfo]) -> str:
    """格式化位置列表为人类可读格式

    Args:
        locations: 位置列表

    Returns:
        格式化后的字符串
    """
    if not locations:
        return "\U0001f50d 未找到匹配的位置"

    lines = [f"\U0001f50d 找到 {len(locations)} 个位置", ""]

    for i, loc in enumerate(locations, 1):
        lines.append(f"# {i}. {loc.context}")
        if loc.code_snippet:
            lines.append("\n代码片段:")
            lines.append(loc.code_snippet)
        lines.append("")

    return "\n".join(lines)


def format_location_json(locations: list[LocationInfo]) -> str:
    """格式化位置列表为 JSON 格式

    Args:
        locations: 位置列表

    Returns:
        JSON 字符串
    """
    data = {
        "count": len(locations),
        "locations": [
            {
                "file_path": loc.file_path,
                "line": loc.line,
                "column": loc.column,
                "uri": loc.uri,
                "symbol_name": loc.symbol_name,
                "context": loc.context,
                "code_snippet": loc.code_snippet,
            }
            for loc in locations
        ],
    }
    return json.dumps(data, indent=2, ensure_ascii=False)


@app.command("definition")
def definition_command(
    file_path: str = typer.Argument(..., help="目标文件路径"),
    line: int = typer.Argument(..., help="行号（从1开始）"),
    column: int = typer.Argument(1, help="列号（从0开始，默认为1）"),
    language: Optional[str] = typer.Option(
        None,
        "--language",
        "-l",
        help="指定语言（如 python, rust, javascript）",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="以 JSON 格式输出",
    ),
) -> None:
    """跳转到定义

    在指定位置查找符号的定义位置。

    注意：此功能依赖于 LSP 守护进程和 LSP 服务器的 textDocument/definition 功能。
    如果服务器不支持此功能或响应超时，命令会失败。
    """
    # 如果没有指定语言，默认使用 python
    if language is None:
        language = "python"

    project_path = os.getcwd()
    client = LSPDaemonClient()

    async def run() -> LocationInfo | None:
        # 通过守护进程获取定义
        location = await client.definition(
            language, project_path, file_path, line - 1, column
        )
        return location

    try:
        location = asyncio.run(run())
    except RuntimeError as e:
        PrettyOutput.auto_print(f"❌ 错误: {e}")
        raise typer.Exit(code=1)

    # 输出结果（daemon_client 返回单个位置或 None）
    if as_json:
        if location is None:
            PrettyOutput.auto_print("[]")
        else:
            PrettyOutput.auto_print(format_location_json([location]))
    else:
        if location is None:
            PrettyOutput.auto_print("\U0001f50d 未找到定义")
        else:
            PrettyOutput.auto_print(format_location_human([location]))


@app.command("references")
def references_command(
    file_path: str = typer.Argument(..., help="目标文件路径"),
    line: int = typer.Argument(..., help="行号（从1开始）"),
    column: int = typer.Argument(1, help="列号（从0开始，默认为1）"),
    language: Optional[str] = typer.Option(
        None,
        "--language",
        "-l",
        help="指定语言（如 python, rust, javascript）",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="以 JSON 格式输出",
    ),
) -> None:
    """查找所有引用

    查找指定位置符号的所有引用位置。

    注意：此功能依赖于 LSP 守护进程和 LSP 服务器的 textDocument/references 功能。
    如果服务器不支持此功能或响应超时，命令会失败。
    """
    # 如果没有指定语言，默认使用 python
    if language is None:
        language = "python"

    project_path = os.getcwd()
    client = LSPDaemonClient()

    async def run() -> list[LocationInfo]:
        # 通过守护进程获取引用
        locations = await client.references(
            language, project_path, file_path, line - 1, column
        )
        return locations

    try:
        locations = asyncio.run(run())
    except RuntimeError as e:
        PrettyOutput.auto_print(f"❌ 错误: {e}")
        raise typer.Exit(code=1)

    # 输出结果
    if as_json:
        PrettyOutput.auto_print(format_location_json(locations))
    else:
        PrettyOutput.auto_print(format_location_human(locations))


@app.command("implementation")
def implementation_command(
    file_path: str = typer.Argument(..., help="目标文件路径"),
    line: int = typer.Argument(..., help="行号（从1开始）"),
    column: int = typer.Argument(1, help="列号（从0开始，默认为1）"),
    language: Optional[str] = typer.Option(
        None,
        "--language",
        "-l",
        help="指定语言（如 python, rust, javascript）",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="以 JSON 格式输出",
    ),
) -> None:
    """查找实现

    查找指定接口或抽象方法的所有实现位置。

    注意：此功能依赖于 LSP 守护进程和 LSP 服务器的 textDocument/implementation 功能。
    如果服务器不支持此功能或响应超时，命令会失败。
    """
    # 如果没有指定语言，默认使用 python
    if language is None:
        language = "python"

    project_path = os.getcwd()
    client = LSPDaemonClient()

    async def run() -> list[LocationInfo]:
        # 通过守护进程获取实现
        locations = await client.implementation(
            language, project_path, file_path, line - 1, column
        )
        return locations

    try:
        locations = asyncio.run(run())
    except RuntimeError as e:
        PrettyOutput.auto_print(f"❌ 错误: {e}")
        raise typer.Exit(code=1)

    # 输出结果
    if as_json:
        PrettyOutput.auto_print(format_location_json(locations))
    else:
        PrettyOutput.auto_print(format_location_human(locations))


@app.command("type_definition")
def type_definition_command(
    file_path: str = typer.Argument(..., help="目标文件路径"),
    line: int = typer.Argument(..., help="行号（从1开始）"),
    column: int = typer.Argument(1, help="列号（从0开始，默认为1）"),
    language: Optional[str] = typer.Option(
        None,
        "--language",
        "-l",
        help="指定语言（如 python, rust, javascript）",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="以 JSON 格式输出",
    ),
) -> None:
    """查找类型定义

    查找指定位置符号的类型定义位置。

    注意：此功能依赖于 LSP 守护进程和 LSP 服务器的 textDocument/typeDefinition 功能。
    如果服务器不支持此功能或响应超时，命令会失败。
    """
    # 如果没有指定语言，默认使用 python
    if language is None:
        language = "python"

    project_path = os.getcwd()
    client = LSPDaemonClient()

    async def run() -> LocationInfo | None:
        # 通过守护进程获取类型定义
        location = await client.type_definition(
            language, project_path, file_path, line - 1, column
        )
        return location

    try:
        location = asyncio.run(run())
    except RuntimeError as e:
        PrettyOutput.auto_print(f"❌ 错误: {e}")
        raise typer.Exit(code=1)

    # 输出结果（daemon_client 返回单个位置或 None）
    if as_json:
        if location is None:
            PrettyOutput.auto_print("[]")
        else:
            PrettyOutput.auto_print(format_location_json([location]))
    else:
        if location is None:
            PrettyOutput.auto_print("\U0001f50d 未找到类型定义")
        else:
            PrettyOutput.auto_print(format_location_human([location]))


@app.command("def-at")
def definition_at_line_command(
    file_path: str = typer.Argument(..., help="目标文件路径"),
    line: int = typer.Argument(..., help="行号（从1开始）"),
    symbol_name: str = typer.Argument(
        ..., help="符号名称（必填，用于精确匹配）"
    ),
    language: Optional[str] = typer.Option(
        None,
        "--language",
        "-l",
        help="指定语言（如 python, rust, javascript）",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="以 JSON 格式输出",
    ),
) -> None:
    """通过行号查找定义（自动查找该行的符号列号）

    在文件的指定行查找符号的定义位置，不需要精确的列号。
    如果该行有多个符号，可以指定符号名称进行精确匹配。

    注意：此功能依赖于 LSP 守护进程和 LSP 服务器的 document/symbol 和 textDocument/definition 功能。
    如果服务器不支持此功能或响应超时，命令会失败。
    """
    if language is None:
        language = "python"

    project_path = os.getcwd()
    client = LSPDaemonClient()

    async def run() -> LocationInfo | None:
        location = await client.definition_at_line(
            language, project_path, file_path, line - 1, symbol_name
        )
        return location

    try:
        location = asyncio.run(run())
    except RuntimeError as e:
        PrettyOutput.auto_print(f"❌ 错误: {e}")
        raise typer.Exit(code=1)

    if as_json:
        if location is None:
            PrettyOutput.auto_print("[]")
        else:
            PrettyOutput.auto_print(format_location_json([location]))
    else:
        if location is None:
            PrettyOutput.auto_print("🔍 未找到定义")
        else:
            PrettyOutput.auto_print(format_location_human([location]))


@app.command("def-name")
def definition_by_name_command(
    file_path: str = typer.Argument(..., help="目标文件路径"),
    symbol_name: str = typer.Argument(..., help="符号名称"),
    language: Optional[str] = typer.Option(
        None,
        "--language",
        "-l",
        help="指定语言（如 python, rust, javascript）",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="以 JSON 格式输出",
    ),
) -> None:
    """通过符号名查找定义

    在文件中查找指定符号的定义位置。

    注意：此功能依赖于 LSP 守护进程和 LSP 服务器的 document/symbol 和 textDocument/definition 功能。
    如果服务器不支持此功能或响应超时，命令会失败。
    """
    if language is None:
        language = "python"

    project_path = os.getcwd()
    client = LSPDaemonClient()

    async def run() -> LocationInfo | None:
        location = await client.definition_by_name(
            language, project_path, file_path, symbol_name
        )
        return location

    try:
        location = asyncio.run(run())
    except RuntimeError as e:
        PrettyOutput.auto_print(f"❌ 错误: {e}")
        raise typer.Exit(code=1)

    if as_json:
        if location is None:
            PrettyOutput.auto_print("[]")
        else:
            PrettyOutput.auto_print(format_location_json([location]))
    else:
        if location is None:
            PrettyOutput.auto_print("🔍 未找到定义")
        else:
            PrettyOutput.auto_print(format_location_human([location]))


@app.command("ref-name")
def references_by_name_command(
    file_path: str = typer.Argument(..., help="目标文件路径"),
    symbol_name: str = typer.Argument(..., help="符号名称"),
    language: Optional[str] = typer.Option(
        None,
        "--language",
        "-l",
        help="指定语言（如 python, rust, javascript）",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="以 JSON 格式输出",
    ),
) -> None:
    """通过符号名查找引用

    在文件中查找指定符号的所有引用位置。

    注意：此功能依赖于 LSP 守护进程和 LSP 服务器的 document/symbol 和 textDocument/references 功能。
    如果服务器不支持此功能或响应超时，命令会失败。
    """
    if language is None:
        language = "python"

    project_path = os.getcwd()
    client = LSPDaemonClient()

    async def run() -> list[LocationInfo]:
        locations = await client.references_by_name(
            language, project_path, file_path, symbol_name
        )
        return locations

    try:
        locations = asyncio.run(run())
    except RuntimeError as e:
        PrettyOutput.auto_print(f"❌ 错误: {e}")
        raise typer.Exit(code=1)

    if as_json:
        PrettyOutput.auto_print(format_location_json(locations))
    else:
        PrettyOutput.auto_print(format_location_human(locations))


@app.command("impl-name")
def implementation_by_name_command(
    file_path: str = typer.Argument(..., help="目标文件路径"),
    symbol_name: str = typer.Argument(..., help="符号名称"),
    language: Optional[str] = typer.Option(
        None,
        "--language",
        "-l",
        help="指定语言（如 python, rust, javascript）",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="以 JSON 格式输出",
    ),
) -> None:
    """通过符号名查找实现

    在文件中查找指定接口或抽象方法的所有实现位置。

    注意：此功能依赖于 LSP 守护进程和 LSP 服务器的 document/symbol 和 textDocument/implementation 功能。
    如果服务器不支持此功能或响应超时，命令会失败。
    """
    if language is None:
        language = "python"

    project_path = os.getcwd()
    client = LSPDaemonClient()

    async def run() -> list[LocationInfo]:
        locations = await client.implementation_by_name(
            language, project_path, file_path, symbol_name
        )
        return locations

    try:
        locations = asyncio.run(run())
    except RuntimeError as e:
        PrettyOutput.auto_print(f"❌ 错误: {e}")
        raise typer.Exit(code=1)

    if as_json:
        PrettyOutput.auto_print(format_location_json(locations))
    else:
        PrettyOutput.auto_print(format_location_human(locations))


@app.command("type-def-name")
def type_definition_by_name_command(
    file_path: str = typer.Argument(..., help="文件路径"),
    symbol_name: str = typer.Argument(..., help="符号名称"),
    language: Optional[str] = typer.Option(
        None, "--language", "-l", help="编程语言 (默认自动检测)"
    ),
    as_json: bool = typer.Option(False, "--json", "-j", help="输出 JSON 格式"),
) -> None:
    """通过符号名查找类型定义（类型定义）

    示例:
    ```
    jlsp type-def-name src/main.py MyClass
    jlsp type-def-name src/main.py "MyClass" --json
    ```

    注意:
    - 需要先使用 `jlsp symbols <file>` 查看文件中的符号列表
    - symbol_name 必须是文件中存在的符号名称
    - pylsp 可能不支持类型定义查询，会显示友好错误
    """
    # 自动检测语言
    if language is None:
        language = "python"

    project_path = os.getcwd()
    client = LSPDaemonClient()

    async def run() -> LocationInfo | None:
        location = await client.type_definition_by_name(
            language, project_path, file_path, symbol_name
        )
        return location

    try:
        location = asyncio.run(run())
    except RuntimeError as e:
        PrettyOutput.auto_print(f"❌ 错误: {e}")
        raise typer.Exit(code=1)

    if location is None:
        PrettyOutput.auto_print("⚠️  未找到类型定义")
    elif as_json:
        PrettyOutput.auto_print(format_location_json([location]))
    else:
        PrettyOutput.auto_print(format_location_human([location]))


@app.command("version")
def version_command() -> None:
    """显示版本信息"""
    PrettyOutput.auto_print(f"jarvis-lsp version {__version__}")


daemon_app = typer.Typer(help="守护进程管理命令")

# 注册守护进程子应用到主应用
app.add_typer(daemon_app, name="daemon", help="守护进程管理命令")


@daemon_app.command("stop")
def daemon_stop() -> None:
    """停止 LSP 守护进程"""
    from jarvis.jarvis_lsp.daemon_client import LSPDaemonClient

    client = LSPDaemonClient()

    try:
        # 发送 shutdown 请求
        import socket
        import json

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(client.socket_path)

        request = {"id": 1, "method": "shutdown", "params": {}}

        message = json.dumps(request)
        sock.sendall(f"Content-Length: {len(message)}\r\n\r\n{message}".encode())
        sock.close()

        PrettyOutput.auto_print("✅ LSP 守护进程已停止")
    except (FileNotFoundError, ConnectionRefusedError):
        PrettyOutput.auto_print("⚠️  守护进程未运行")
    except Exception as e:
        PrettyOutput.auto_print(f"❌ 错误: {e}")
        raise typer.Exit(code=1)


@daemon_app.command("status")
def daemon_status() -> None:
    """查看 LSP 守护进程状态

    守护进程会在第一次使用任何 LSP 命令时自动启动。
    """
    import asyncio
    from jarvis.jarvis_lsp.daemon_client import LSPDaemonClient

    async def run() -> None:
        client = LSPDaemonClient()

        try:
            status = await client.status()

            PrettyOutput.auto_print("📊 LSP 守护进程状态:")
            PrettyOutput.auto_print("\n   ✅ 守护进程运行中")
            PrettyOutput.auto_print(f"   Socket: {client.socket_path}")

            # 移除 success 字段，只保留服务器信息
            servers = {k: v for k, v in status.items() if k != "success"}

            if not servers:
                PrettyOutput.auto_print("\n   📌 没有运行中的 LSP 服务器")
                return

            PrettyOutput.auto_print("\n   📌 LSP 服务器列表:")
            for server_key, server_info in servers.items():
                PrettyOutput.auto_print(
                    f"\n     • {server_key}"
                    f"\n       进程 ID: {server_info['pid']}"
                    f"\n       启动时间: {server_info['start_time']}"
                    f"\n       活跃: {'是' if server_info['is_alive'] else '否'}"
                )
        except (FileNotFoundError, ConnectionRefusedError):
            PrettyOutput.auto_print("📊 LSP 守护进程状态:")
            PrettyOutput.auto_print("\n   ❌ 守护进程未运行")
            PrettyOutput.auto_print(f"\n   Socket: {client.socket_path}")
            PrettyOutput.auto_print("\n   ℹ️  守护进程会在第一次使用 LSP 命令时自动启动")
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 错误: {e}")
            raise typer.Exit(code=1)

    asyncio.run(run())


def main() -> None:
    """主入口函数"""
    app()


def jlsp_main() -> None:
    """jlsp 命令入口函数"""
    app()


if __name__ == "__main__":
    main()
