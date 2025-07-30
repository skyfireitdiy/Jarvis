"""
统计模块命令行接口

使用 typer 提供友好的命令行交互
"""

import builtins
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

    stats.increment(
        metric,
        amount=value,
        unit=unit if unit else "count",
        tags=tag_dict if tag_dict else None,
    )

    rprint(
        f"[green]✓[/green] 已添加数据: {metric}={value}" + (f" {unit}" if unit else "")
    )
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
    aggregation: str = typer.Option(
        "hourly", "--agg", "-a", help="聚合方式: hourly/daily"
    ),
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
    metric: Optional[str] = typer.Argument(
        None, help="指标名称（可选，不指定则根据标签过滤所有匹配的指标）"
    ),
    last_hours: Optional[int] = typer.Option(None, "--hours", "-h", help="最近N小时"),
    last_days: Optional[int] = typer.Option(None, "--days", "-d", help="最近N天"),
    aggregation: str = typer.Option(
        "hourly", "--agg", "-a", help="聚合方式: hourly/daily"
    ),
    width: Optional[int] = typer.Option(None, "--width", "-w", help="图表宽度"),
    height: Optional[int] = typer.Option(None, "--height", "-H", help="图表高度"),
    tags: Optional[List[str]] = typer.Option(
        None, "--tag", "-t", help="标签过滤，格式: key=value"
    ),
):
    """绘制指标折线图，支持根据标签过滤显示多个指标"""
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
    table.add_column("标签", style="blue")

    # 获取每个指标的信息
    end_time = datetime.now()
    start_time = end_time - timedelta(days=7)

    for metric in metrics:
        info = stats._get_storage().get_metric_info(metric)
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

            # 获取数据点数和标签
            records = stats._get_storage().get_metrics(metric, start_time, end_time)
            count = len(records)
            
            # 收集所有唯一的标签
            all_tags = {}
            for record in records:
                tags = record.get("tags", {})
                for k, v in tags.items():
                    if k not in all_tags:
                        all_tags[k] = set()
                    all_tags[k].add(v)
            
            # 格式化标签显示
            tag_str = ""
            if all_tags:
                tag_parts = []
                for k, values in sorted(all_tags.items()):
                    # 使用内置的list函数
                    values_list = sorted(builtins.list(values))
                    if len(values_list) == 1:
                        tag_parts.append(f"{k}={values_list[0]}")
                    else:
                        # 转义方括号以避免Rich markup错误
                        tag_parts.append(f"{k}=\\[{', '.join(values_list)}\\]")
                tag_str = ", ".join(tag_parts)
            else:
                tag_str = "-"

            table.add_row(metric, unit, last_updated, str(count), tag_str)

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
def remove(
    metric: str = typer.Argument(..., help="要删除的指标名称"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
):
    """删除指定的指标及其所有数据"""
    if not yes:
        # 显示指标信息供用户确认
        stats = StatsManager(_get_stats_dir())
        metrics = stats.list_metrics()
        
        if metric not in metrics:
            rprint(f"[red]错误：指标 '{metric}' 不存在[/red]")
            return
            
        # 获取指标的基本信息
        info = stats._get_storage().get_metric_info(metric)
        if info:
            unit = info.get("unit", "-")
            last_updated = info.get("last_updated", "-")
            
            rprint(f"\n[yellow]准备删除指标:[/yellow]")
            rprint(f"  名称: {metric}")
            rprint(f"  单位: {unit}")
            rprint(f"  最后更新: {last_updated}")
            
        confirm = typer.confirm(f"\n确定要删除指标 '{metric}' 及其所有数据吗？")
        if not confirm:
            rprint("[yellow]已取消操作[/yellow]")
            return
    
    stats = StatsManager(_get_stats_dir())
    success = stats.remove_metric(metric)
    
    if success:
        rprint(f"[green]✓[/green] 已成功删除指标: {metric}")
    else:
        rprint(f"[red]✗[/red] 删除失败：指标 '{metric}' 不存在")


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
    init_env("欢迎使用 Jarvis-Stats，您的统计分析工具已准备就绪！", None)
    app()


if __name__ == "__main__":
    main()
