# -*- coding: utf-8 -*-
"""Web Gateway CLI 入口。"""

from typing import Optional

import typer
from rich import print as rprint

from jarvis.jarvis_utils.utils import init_env
from .app import run
from .node_config import build_node_runtime_config

app = typer.Typer(help="Jarvis Web Gateway 服务")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="监听地址"),
    port: int = typer.Option(8000, "--port", "-p", help="监听端口"),
    gateway_password: Optional[str] = typer.Option(
        None, "--gateway-password", help="Web Gateway 密码（如未设置将禁用密码认证）"
    ),
    node_mode: str = typer.Option(
        "master", "--node-mode", help="节点模式：master 或 child"
    ),
    node_id: Optional[str] = typer.Option(
        None, "--node-id", help="当前节点 ID（child 模式必填）"
    ),
    master_url: Optional[str] = typer.Option(
        None, "--master-url", help="主节点 URL（child 模式必填）"
    ),
    node_secret: Optional[str] = typer.Option(
        None, "--node-secret", help="节点共享密钥（child 模式必填）"
    ),
) -> None:
    """启动 Web Gateway 服务。"""

    rprint("\n[bold cyan]🚀 启动 Jarvis Web Gateway[/bold cyan]\n")
    rprint(f"  [dim]地址:[/dim] {host}")
    rprint(f"  [dim]端口:[/dim] {port}")
    if gateway_password:
        rprint("  [dim]密码:[/dim] [green]已设置[/green]")
    else:
        rprint("  [dim]密码:[/dim] [yellow]未设置[/yellow]")

    node_config = build_node_runtime_config(
        node_mode=node_mode,
        node_id=node_id,
        master_url=master_url,
        node_secret=node_secret,
    )
    rprint(f"  [dim]节点模式:[/dim] {node_config.node_mode}")
    rprint(f"  [dim]节点ID:[/dim] {node_config.effective_node_id}")
    if node_config.node_secret:
        rprint("  [dim]节点密钥:[/dim] [green]已设置[/green]")
    else:
        rprint("  [dim]节点密钥:[/dim] [yellow]未设置[/yellow]")
    rprint()
    run(host=host, port=port, password=gateway_password, node_config=node_config)


def main(argv: Optional[list[str]] = None) -> None:
    init_env("")
    app(standalone_mode=True)
