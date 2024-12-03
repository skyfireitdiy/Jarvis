# -*- coding: utf-8 -*-
"""
Jarvis 配置工具命令行接口

使用 typer 提供友好的命令行交互
"""

import webbrowser
from pathlib import Path
from typing import Optional

import typer
import uvicorn
from rich import print as rprint

from .schema_parser import SchemaParser
from .web_app import create_app

# 获取 jarvis_data 目录路径
from importlib import resources
from jarvis.jarvis_utils.utils import init_env

app = typer.Typer(help="Jarvis 配置工具 - 基于 JSON Schema 动态生成配置页面")


@app.command()
def web(
    schema_file: Optional[Path] = typer.Option(
        None,
        "--schema",
        "-s",
        help="JSON Schema 文件路径 (默认: jarvis 的 config_schema.json)",
    ),
    output_file: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="输出的配置文件路径 (默认: ~/.jarvis/config.yaml)",
    ),
    port: int = typer.Option(
        8080,
        "--port",
        "-p",
        help="Web 服务端口",
    ),
    open_browser: bool = typer.Option(
        True,
        "--no-browser",
        "/nb",
        help="启动后自动打开浏览器",
    ),
) -> None:
    """启动 Web 配置界面

    根据指定的 JSON Schema 文件生成配置页面，
    用户填写后自动保存到指定的输出文件。

    示例:
        jarvis-config
        jarvis-config --schema custom.json --output custom.yaml
        jarvis-config --port 3000 --no-browser
        jarvis-config -s schema.json -o output.yaml -p 8080
    """

    init_env("")

    # 设置默认值
    if schema_file is None:
        # 使用 jarvis 的默认 config_schema.json
        try:
            jarvis_data_dir = resources.files("jarvis.jarvis_data")
            schema_file = Path(str(jarvis_data_dir / "config_schema.json"))
        except Exception:
            # 如果找不到，尝试相对路径
            schema_file = (
                Path(__file__).parent.parent / "jarvis_data" / "config_schema.json"
            )

    if output_file is None:
        # 使用默认的 ~/.jarvis/config.yaml
        jarvis_dir = Path.home() / ".jarvis"
        output_file = jarvis_dir / "config.yaml"

    try:
        # 显示启动信息
        rprint("\n[bold cyan]🚀 启动 Jarvis 配置工具[/bold cyan]\n")
        rprint(f"  [dim]Schema 文件:[/dim] {schema_file}")
        rprint(f"  [dim]输出文件:[/dim] {output_file}")
        rprint(f"  [dim]服务端口:[/dim] {port}")
        rprint()

        # 验证 schema 文件
        try:
            parser = SchemaParser(schema_file)
            rprint(f"[green]✓[/green] Schema 加载成功: {parser.get_title()}")
        except Exception as e:
            rprint(f"[red]✗[/red] Schema 加载失败: {e}")
            raise typer.Exit(code=1)

        # 确保 output_file 的父目录存在
        try:
            output_file.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            rprint(f"[red]✗[/red] 无法创建输出目录: {e}")
            raise typer.Exit(code=1)

        # 创建 FastAPI 应用
        try:
            fastapi_app = create_app(schema_file, output_file)
        except Exception as e:
            rprint(f"[red]✗[/red] 创建应用失败: {e}")
            raise typer.Exit(code=1)

        # 启动信息
        url = f"http://localhost:{port}"
        rprint("\n[bold green]✓ 服务已启动！[/bold green]")
        rprint(f"  [dim]访问地址:[/dim] [link]{url}[/link]")
        rprint("  [dim]按 Ctrl+C 停止服务[/dim]\n")

        # 自动打开浏览器
        if open_browser:
            try:
                webbrowser.open(url)
                rprint("[dim]已自动打开浏览器...[/dim]\n")
            except Exception:
                rprint(f"[yellow]⚠[/yellow] 无法自动打开浏览器，请手动访问: {url}\n")

        # 启动 uvicorn 服务
        uvicorn.run(
            fastapi_app,
            host="0.0.0.0",
            port=port,
            log_level="info",
            timeout_graceful_shutdown=30,  # 优雅关闭：给30秒时间处理现有请求
        )

    except KeyboardInterrupt:
        rprint("\n[yellow]\n⚠ 服务已停止[/yellow]")
        raise typer.Exit(code=0)
    except typer.Exit:
        raise  # 重新抛出 typer.Exit
    except Exception as e:
        rprint(f"\n[red]✗ 发生错误: {e}[/red]")
        raise typer.Exit(code=1)
