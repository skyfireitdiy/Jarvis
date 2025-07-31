"""
统计数据可视化模块

提供终端图形化展示功能
"""

import os
import io
from typing import Dict, List, Optional, Any
from collections import OrderedDict
import plotext as plt
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box


class StatsVisualizer:
    """统计数据可视化类"""

    def __init__(self, width: Optional[int] = None, height: Optional[int] = None):
        """
        初始化可视化器

        Args:
            width: 图表宽度，默认为终端宽度-10
            height: 图表高度，默认为20
        """
        self.width = width or self._get_terminal_width() - 10
        self.height = height or 20

        # 确保最小尺寸
        self.width = max(self.width, 40)
        self.height = max(self.height, 10)

        # 初始化Rich Console
        self.console = Console()

    def _get_terminal_width(self) -> int:
        """获取终端宽度"""
        try:
            columns = os.get_terminal_size().columns
            return columns
        except:
            return 80

    def plot_line_chart(
        self,
        data: Dict[str, float],
        title: str = "",
        unit: Optional[str] = None,
        show_values: bool = True,
    ) -> str:
        """
        使用 plotext 绘制折线图
        """
        if not data:
            return "无数据可显示"

        sorted_data = OrderedDict(sorted(data.items()))
        labels = list(sorted_data.keys())
        values = list(sorted_data.values())

        plt.clf()
        plt.plotsize(self.width, self.height)
        plt.plot(values)
        plt.xticks(range(len(labels)), labels)
        if title:
            plt.title(title)
        if unit:
            plt.ylabel(unit)

        chart = plt.build()

        if show_values and values:
            min_val = min(values)
            max_val = max(values)
            avg_val = sum(values) / len(values)
            stats_info_text = (
                f"最小值: {min_val:.2f}, 最大值: {max_val:.2f}, 平均值: {avg_val:.2f}"
            )

            # 使用StringIO捕获Panel输出
            string_io = io.StringIO()
            temp_console = Console(file=string_io, width=self.width)
            temp_console.print(
                Panel(
                    stats_info_text,
                    title="[bold]数据统计[/bold]",
                    expand=False,
                    style="dim",
                    border_style="blue",
                )
            )
            stats_panel_str = string_io.getvalue()

            return chart + "\n" + stats_panel_str.strip()
        return chart

    def plot_bar_chart(
        self,
        data: Dict[str, float],
        title: str = "",
        unit: Optional[str] = None,
        horizontal: bool = False,
    ) -> str:
        """
        使用 plotext 绘制柱状图
        """
        if not data:
            return "无数据可显示"

        labels = list(data.keys())
        values = list(data.values())

        plt.clf()
        plt.plotsize(self.width, self.height)

        if horizontal:
            plt.bar(labels, values, orientation="horizontal")
        else:
            plt.bar(labels, values)
        if title:
            plt.title(title)
        if unit:
            plt.ylabel(unit)

        return plt.build()

    def show_summary(
        self,
        aggregated_data: Dict[str, Dict[str, Any]],
        metric_name: str,
        unit: Optional[str] = None,
        tags_filter: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        显示数据摘要

        Args:
            aggregated_data: 聚合后的数据
            metric_name: 指标名称
            unit: 单位
            tags_filter: 标签过滤条件

        Returns:
            摘要字符串（用于兼容性，实际会直接打印）
        """
        if not aggregated_data:
            self.console.print("[yellow]无数据可显示[/yellow]")
            return "无数据可显示"

        # 创建表格
        table = Table(title=f"{metric_name} 统计摘要", box=box.ROUNDED)

        # 添加列
        table.add_column("时间", justify="center", style="cyan")
        table.add_column("计数", justify="right", style="green")
        table.add_column("总和", justify="right", style="yellow")
        table.add_column("平均", justify="right", style="yellow")
        table.add_column("最小", justify="right", style="blue")
        table.add_column("最大", justify="right", style="red")

        # 添加数据行
        for time_key, stats in sorted(aggregated_data.items()):
            table.add_row(
                time_key,
                str(stats["count"]),
                f"{stats['sum']:.2f}",
                f"{stats['avg']:.2f}",
                f"{stats['min']:.2f}",
                f"{stats['max']:.2f}",
            )

        # 显示表格
        self.console.print(table)

        # 显示单位信息
        if unit:
            self.console.print(f"\n[dim]单位: {unit}[/dim]")

        # 显示过滤条件
        if tags_filter:
            filter_str = ", ".join([f"{k}={v}" for k, v in tags_filter.items()])
            self.console.print(f"[dim]过滤条件: {filter_str}[/dim]")

        return ""  # 返回空字符串，实际输出已经通过console打印

    def show_table(
        self,
        records: List[Dict[str, Any]],
        metric_name: str,
        unit: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        tags_filter: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        使用Rich Table显示数据记录

        Args:
            records: 数据记录列表
            metric_name: 指标名称
            unit: 单位
            start_time: 开始时间
            end_time: 结束时间
            tags_filter: 标签过滤条件

        Returns:
            空字符串（实际通过console打印）
        """
        if not records:
            self.console.print(f"[yellow]没有找到指标 '{metric_name}' 的数据[/yellow]")
            return ""

        # 创建表格
        table = Table(title=f"指标: {metric_name}", box=box.ROUNDED)

        # 添加列
        table.add_column("时间", style="cyan", no_wrap=True)
        table.add_column("值", justify="right", style="yellow")
        table.add_column("标签", style="dim")

        # 只显示最近的20条记录
        display_records = records[-20:] if len(records) > 20 else records

        # 添加数据行
        from datetime import datetime

        for record in display_records:
            timestamp = datetime.fromisoformat(record["timestamp"])
            time_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
            value = f"{record['value']:.2f}"
            tags_str = ", ".join(f"{k}={v}" for k, v in record.get("tags", {}).items())

            table.add_row(time_str, value, tags_str)

        # 显示表格
        self.console.print(table)

        # 显示元信息
        info_items = []
        if unit:
            info_items.append(f"单位: {unit}")
        if start_time and end_time:
            info_items.append(f"时间范围: [cyan]{start_time}[/] ~ [cyan]{end_time}[/]")
        if tags_filter:
            filter_str = ", ".join([f"{k}={v}" for k, v in tags_filter.items()])
            info_items.append(f"过滤条件: {filter_str}")

        if info_items:
            self.console.print(
                Panel(
                    " | ".join(info_items),
                    title="[bold]查询详情[/bold]",
                    expand=False,
                    style="dim",
                    border_style="green",
                )
            )

        # 统计信息
        if len(records) > 0:
            values = [r["value"] for r in records]
            stats_info_text = (
                f"总记录数: {len(records)} | "
                f"显示: {len(display_records)} | "
                f"最小值: {min(values):.2f} | "
                f"最大值: {max(values):.2f} | "
                f"平均值: {sum(values)/len(values):.2f}"
            )
            self.console.print(
                Panel(
                    stats_info_text,
                    title="[bold]数据统计[/bold]",
                    expand=False,
                    style="dim",
                    border_style="blue",
                )
            )

        return ""
