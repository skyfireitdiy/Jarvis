# -*- coding: utf-8 -*-
"""Web Gateway CLI 入口。"""

from typing import Optional

import typer
from rich import print as rprint

from .app import run

app = typer.Typer(help="Jarvis Web Gateway 服务")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="监听地址"),
    port: int = typer.Option(8000, "--port", "-p", help="监听端口"),
    gateway_password: Optional[str] = typer.Option(
        None, "--gateway-password", help="Web Gateway 密码（如未设置将禁用密码认证）"
    ),
) -> None:
    """启动 Web Gateway 服务。"""

    rprint("\n[bold cyan]🚀 启动 Jarvis Web Gateway[/bold cyan]\n")
    rprint(f"  [dim]地址:[/dim] {host}")
    rprint(f"  [dim]端口:[/dim] {port}")
    if gateway_password:
        rprint("  [dim]密码:[/dim] [green]已设置[/green]\n")
    else:
        rprint("  [dim]密码:[/dim] [yellow]未设置[/yellow]\n")
    run(host=host, port=port, password=gateway_password)


def main(argv: Optional[list[str]] = None) -> None:
    app(standalone_mode=True)
