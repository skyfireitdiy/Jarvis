"""
统计模块命令行接口

使用 typer 提供友好的命令行交互
"""

from datetime import datetime, timedelta
from typing import Optional, List
import typer
from rich.console import Console
from rich.table import Table
from rich import print as rprint
from pathlib import Path

from .stats import StatsManager
from jarvis.jarvis_utils.utils import init_env
from jarvis.jarvis_utils.config import get_data_dir

app = typer.Typer(help="Jarvis 统计模块命令行工具")
console = Console()

# 全局变量，存储是否已初始化
_initialized = False
_stats_dir = None


def _get_stats_dir():
    """获取统计数据目录"""
    global _initialized, _stats_dir
    if not _initialized:
        _stats_dir = Path(get_data_dir()) / "stats"
        _initialized = True
    return str(_stats_dir)


@app.command()
def add(
    metric: str = typer.Argument(..., help="指标名称"),
    value: float = typer.Argument(..., help="指标值"),
    unit: Optional[str] = typer.Option(None, "--unit", "-u", help="单位"),
    tags: Optional[List[str]] = typer.Option(
        None, "--tag", "-t", help="标签，格式: key=value"
    ),
):
    """添加统计数据"""
    stats = StatsManager(_get_stats_dir())

    # 解析标签
    tag_dict = {}
    if tags:
        for tag in tags:
            if "=" in tag:
                key, val = tag.split("=", 1)
                tag_dict[key] = val

    stats.increment(metric, amount=value, unit=unit, tags=tag_dict if tag_dict else None)

    rprint(f"[green]✓[/green] 已添加数据: {metric}={value}" + (f" {unit}" if unit else ""))
    if tag_dict:
        rprint(f"  标签: {tag_dict}")


@app.command()
def inc(
    metric: str = typer.Argument(..., help="指标名称"),
    amount: int = typer.Option(1, "--amount", "-a", help="增加的数量"),
    tags: Optional[List[str]] = typer.Option(
        None, "--tag", "-t", help="标签，格式: key=value"
    ),
):
    """增加计数型指标"""
    stats = StatsManager(_get_stats_dir())

    # 解析标签
    tag_dict = {}
    if tags:
        for tag in tags:
            if "=" in tag:
                key, val = tag.split("=", 1)
                tag_dict[key] = val

    stats.increment(metric, amount=amount, tags=tag_dict if tag_dict else None)

    rprint(f"[green]✓[/green] 已增加计数: {metric} +{amount}")
    if tag_dict:
        rprint(f"  标签: {tag_dict}")


@app.command()
def show(
    metric: Optional[str] = typer.Argument(None, help="指标名称，不指定则显示所有"),
    last_hours: Optional[int] = typer.Option(None, "--hours", "-h", help="最近N小时"),
    last_days: Optional[int] = typer.Option(None, "--days", "-d", help="最近N天"),
    format: str = typer.Option(
        "table", "--format", "-f", help="显示格式: table/chart/summary"
    ),
    aggregation: str = typer.Option("hourly", "--agg", "-a", help="聚合方式: hourly/daily"),
    tags: Optional[List[str]] = typer.Option(
        None, "--tag", "-t", help="标签过滤，格式: key=value"
    ),
):
    """显示统计数据"""
    stats = StatsManager(_get_stats_dir())

    # 解析标签
    tag_dict = {}
    if tags:
        for tag in tags:
            if "=" in tag:
                key, val = tag.split("=", 1)
                tag_dict[key] = val

    stats.show(
        metric_name=metric,
        last_hours=last_hours,
        last_days=last_days,
        format=format,
        aggregation=aggregation,
        tags=tag_dict if tag_dict else None,
    )


@app.command()
def plot(
    metric: str = typer.Argument(..., help="指标名称"),
    last_hours: Optional[int] = typer.Option(None, "--hours", "-h", help="最近N小时"),
    last_days: Optional[int] = typer.Option(None, "--days", "-d", help="最近N天"),
    aggregation: str = typer.Option("hourly", "--agg", "-a", help="聚合方式: hourly/daily"),
    width: Optional[int] = typer.Option(None, "--width", "-w", help="图表宽度"),
    height: Optional[int] = typer.Option(None, "--height", "-H", help="图表高度"),
    tags: Optional[List[str]] = typer.Option(
        None, "--tag", "-t", help="标签过滤，格式: key=value"
    ),
):
    """绘制指标折线图"""
    stats = StatsManager(_get_stats_dir())

    # 解析标签
    tag_dict = {}
    if tags:
        for tag in tags:
            if "=" in tag:
                key, val = tag.split("=", 1)
                tag_dict[key] = val

    stats.plot(
        metric_name=metric,
        last_hours=last_hours,
        last_days=last_days,
        aggregation=aggregation,
        width=width,
        height=height,
        tags=tag_dict if tag_dict else None,
    )


@app.command()
def list():
    """列出所有指标"""
    stats = StatsManager(_get_stats_dir())
    metrics = stats.list_metrics()

    if not metrics:
        rprint("[yellow]没有找到任何指标[/yellow]")
        return

    # 创建表格
    table = Table(title="统计指标列表")
    table.add_column("指标名称", style="cyan")
    table.add_column("单位", style="green")
    table.add_column("最后更新", style="yellow")
    table.add_column("7天数据点", style="magenta")

    # 获取每个指标的信息
    end_time = datetime.now()
    start_time = end_time - timedelta(days=7)

    for metric in metrics:
        info = stats.storage.get_metric_info(metric)
        if info:
            unit = info.get("unit", "-")
            last_updated = info.get("last_updated", "-")

            # 格式化时间
            if last_updated != "-":
                try:
                    dt = datetime.fromisoformat(last_updated)
                    last_updated = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    pass

            # 获取数据点数
            records = stats.storage.get_metrics(metric, start_time, end_time)
            count = len(records)

            table.add_row(metric, unit, last_updated, str(count))

    console.print(table)
    rprint(f"\n[green]总计: {len(metrics)} 个指标[/green]")


@app.command()
def clean(
    days: int = typer.Option(30, "--days", "-d", help="保留最近N天的数据"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
):
    """清理旧数据"""
    if not yes:
        confirm = typer.confirm(f"确定要删除 {days} 天前的数据吗？")
        if not confirm:
            rprint("[yellow]已取消操作[/yellow]")
            return

    stats = StatsManager(_get_stats_dir())
    stats.clean_old_data(days_to_keep=days)
    rprint(f"[green]✓[/green] 已清理 {days} 天前的数据")


@app.command()
def export(
    metric: str = typer.Argument(..., help="指标名称"),
    output: str = typer.Option("csv", "--format", "-f", help="输出格式: csv/json"),
    last_hours: Optional[int] = typer.Option(None, "--hours", "-h", help="最近N小时"),
    last_days: Optional[int] = typer.Option(None, "--days", "-d", help="最近N天"),
    tags: Optional[List[str]] = typer.Option(
        None, "--tag", "-t", help="标签过滤，格式: key=value"
    ),
):
    """导出统计数据"""
    import json
    import csv
    import sys

    stats = StatsManager(_get_stats_dir())

    # 解析标签
    tag_dict = {}
    if tags:
        for tag in tags:
            if "=" in tag:
                key, val = tag.split("=", 1)
                tag_dict[key] = val

    # 获取数据
    data = stats.get_stats(
        metric_name=metric,
        last_hours=last_hours,
        last_days=last_days,
        tags=tag_dict if tag_dict else None,
    )

    if output == "json":
        # JSON格式输出
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        # CSV格式输出
        records = data.get("records", [])
        if records:
            writer = csv.writer(sys.stdout)
            writer.writerow(["timestamp", "value", "tags"])
            for record in records:
                tags_str = json.dumps(record.get("tags", {}))
                writer.writerow([record["timestamp"], record["value"], tags_str])
        else:
            rprint("[yellow]没有找到数据[/yellow]", file=sys.stderr)


@app.command()
def demo():
    """运行演示，展示统计模块的功能"""
    import random
    import time

    console.print("[bold cyan]Jarvis 统计模块演示[/bold cyan]\n")

    stats = StatsManager(_get_stats_dir())

    # 添加演示数据
    with console.status("[bold green]正在生成演示数据...") as status:
        # API响应时间
        for i in range(20):
            response_time = random.uniform(0.1, 2.0)
            status_code = random.choice(["200", "404", "500"])
            stats.increment(
                "demo_response_time",
                amount=response_time,
                unit="seconds",
                tags={"status": status_code},
            )
            time.sleep(0.05)

        # 访问计数
        for i in range(30):
            endpoint = random.choice(["/api/users", "/api/posts", "/api/admin"])
            stats.increment("demo_api_calls", tags={"endpoint": endpoint})
            time.sleep(0.05)

    rprint("[green]✓[/green] 演示数据生成完成\n")

    # 显示数据
    console.rule("[bold blue]指标列表")
    stats.show()

    console.rule("[bold blue]响应时间详情")
    stats.show("demo_response_time", last_hours=1)

    console.rule("[bold blue]API调用折线图")
    stats.plot("demo_api_calls", last_hours=1, height=10)

    console.rule("[bold blue]响应时间汇总")
    stats.show("demo_response_time", last_hours=1, format="summary")

    rprint("\n[green]✓[/green] 演示完成！")


def main():
    """主入口函数"""
    # 初始化环境，防止设置初始化太迟
    init_env("", None)
    app()


if __name__ == "__main__":
    main()
