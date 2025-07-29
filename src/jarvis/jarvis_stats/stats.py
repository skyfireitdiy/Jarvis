"""
统计管理模块

提供统计数据的增加、查看、分析等功能的主接口
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union, Any

from jarvis.jarvis_stats.storage import StatsStorage
from jarvis.jarvis_stats.visualizer import StatsVisualizer


class StatsManager:
    """统计管理器"""

    def __init__(self, storage_dir: Optional[str] = None):
        """
        初始化统计管理器

        Args:
            storage_dir: 存储目录路径
        """
        self.storage = StatsStorage(storage_dir)
        self.visualizer = StatsVisualizer()

    def increment(
        self,
        metric_name: str,
        amount: Union[int, float] = 1,
        tags: Optional[Dict[str, str]] = None,
        group: Optional[str] = None,
        unit: str = "count",
    ):
        """
        增加计数型指标

        Args:
            metric_name: 指标名称
            amount: 增加的数量，默认为1
            tags: 标签字典
            group: 指标分组，会自动添加到 tags 中
            unit: 计量单位，默认为 "count"

        Examples:
            >>> stats = StatsManager()
            >>> stats.increment("page_views")
            >>> stats.increment("downloads", 5)
            >>> stats.increment("response_time", 0.123, unit="seconds")
            >>> stats.increment("execute_script", 1, group="tool")
        """
        # 如果指定了分组，自动添加到 tags 中
        if group:
            if tags is None:
                tags = {}
            tags["group"] = group

        self.storage.add_metric(
            metric_name=metric_name,
            value=float(amount),
            unit=unit,
            timestamp=datetime.now(),
            tags=tags,
        )

    def list_metrics(self) -> List[str]:
        """
        列出所有指标

        Returns:
            指标名称列表
        """
        return self.storage.list_metrics()

    def show(
        self,
        metric_name: Optional[str] = None,
        last_hours: Optional[int] = None,
        last_days: Optional[int] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        format: str = "table",
        aggregation: str = "hourly",
        tags: Optional[Dict[str, str]] = None,
    ):
        """
        显示统计数据

        Args:
            metric_name: 指标名称，如果不指定则显示所有指标摘要
            last_hours: 最近N小时
            last_days: 最近N天
            start_time: 开始时间
            end_time: 结束时间
            format: 显示格式 (table, chart, summary)
            aggregation: 聚合方式 (hourly, daily)
            tags: 过滤标签

        Examples:
            >>> stats = StatsManager()
            >>> stats.show()  # 显示所有指标摘要
            >>> stats.show("api_calls", last_hours=24)  # 显示最近24小时
            >>> stats.show("response_time", last_days=7, format="chart")  # 图表显示
        """
        # 处理时间范围
        if end_time is None:
            end_time = datetime.now()

        if start_time is None:
            if last_hours:
                start_time = end_time - timedelta(hours=last_hours)
            elif last_days:
                start_time = end_time - timedelta(days=last_days)
            else:
                start_time = end_time - timedelta(days=7)  # 默认7天

        if metric_name is None:
            # 显示所有指标摘要
            self._show_metrics_summary()
        else:
            # 根据格式显示数据
            if format == "chart":
                self._show_chart(metric_name, start_time, end_time, aggregation, tags)
            elif format == "summary":
                self._show_summary(metric_name, start_time, end_time, aggregation, tags)
            else:
                self._show_table(metric_name, start_time, end_time, tags)

    def plot(
        self,
        metric_name: Optional[str] = None,
        last_hours: Optional[int] = None,
        last_days: Optional[int] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        aggregation: str = "hourly",
        tags: Optional[Dict[str, str]] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ):
        """
        绘制指标的折线图

        Args:
            metric_name: 指标名称（可选，不指定则根据标签过滤所有匹配的指标）
            last_hours: 最近N小时
            last_days: 最近N天
            start_time: 开始时间
            end_time: 结束时间
            aggregation: 聚合方式
            tags: 过滤标签
            width: 图表宽度
            height: 图表高度

        Examples:
            >>> stats = StatsManager()
            >>> stats.plot("response_time", last_hours=24)
            >>> stats.plot(tags={"service": "api"}, last_days=7)
        """
        # 处理时间范围
        if end_time is None:
            end_time = datetime.now()

        if start_time is None:
            if last_hours:
                start_time = end_time - timedelta(hours=last_hours)
            elif last_days:
                start_time = end_time - timedelta(days=last_days)
            else:
                start_time = end_time - timedelta(days=7)

        # 如果指定了metric_name，显示单个图表
        if metric_name:
            self._show_chart(
                metric_name, start_time, end_time, aggregation, tags, width, height
            )
        else:
            # 如果没有指定metric_name，根据标签过滤获取所有匹配的指标
            self._show_multiple_charts(
                start_time, end_time, aggregation, tags, width, height
            )

    def get_stats(
        self,
        metric_name: str,
        last_hours: Optional[int] = None,
        last_days: Optional[int] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        aggregation: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        获取统计数据

        Args:
            metric_name: 指标名称
            last_hours: 最近N小时
            last_days: 最近N天
            start_time: 开始时间
            end_time: 结束时间
            aggregation: 聚合方式，如果指定则返回聚合数据
            tags: 过滤标签

        Returns:
            统计数据字典
        """
        # 处理时间范围
        if end_time is None:
            end_time = datetime.now()

        if start_time is None:
            if last_hours:
                start_time = end_time - timedelta(hours=last_hours)
            elif last_days:
                start_time = end_time - timedelta(days=last_days)
            else:
                start_time = end_time - timedelta(days=7)

        if aggregation:
            # 返回聚合数据
            return self.storage.aggregate_metrics(
                metric_name, start_time, end_time, aggregation, tags
            )
        else:
            # 返回原始数据
            records = self.storage.get_metrics(metric_name, start_time, end_time, tags)
            return {
                "metric": metric_name,
                "records": records,
                "count": len(records),
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
            }

    def clean_old_data(self, days_to_keep: int = 30):
        """
        清理旧数据

        Args:
            days_to_keep: 保留最近N天的数据
        """
        self.storage.delete_old_data(days_to_keep)
        print(f"已清理 {days_to_keep} 天前的数据")

    def _show_metrics_summary(self):
        """显示所有指标摘要"""
        from rich.console import Console
        from rich.table import Table

        console = Console()
        metrics = self.storage.list_metrics()

        if not metrics:
            console.print("[yellow]没有找到任何统计指标[/yellow]")
            return

        # 创建表格
        table = Table(title="统计指标摘要")
        table.add_column("指标名称", style="cyan")
        table.add_column("单位", style="green")
        table.add_column("最后更新", style="yellow")
        table.add_column("7天数据点", style="magenta")

        # 获取每个指标的信息
        end_time = datetime.now()
        start_time = end_time - timedelta(days=7)

        for metric in metrics:
            info = self.storage.get_metric_info(metric)
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
                records = self.storage.get_metrics(metric, start_time, end_time)
                count = len(records)

                table.add_row(metric, unit, last_updated, str(count))

        console.print(table)
        console.print(f"\n[green]总计: {len(metrics)} 个指标[/green]")

    def _show_table(
        self,
        metric_name: str,
        start_time: datetime,
        end_time: datetime,
        tags: Optional[Dict[str, str]],
    ):
        """以表格形式显示数据"""
        records = self.storage.get_metrics(metric_name, start_time, end_time, tags)

        # 获取指标信息
        info = self.storage.get_metric_info(metric_name)
        unit = info.get("unit", "") if info else ""

        # 使用visualizer显示表格
        self.visualizer.show_table(
            records=records,
            metric_name=metric_name,
            unit=unit,
            start_time=start_time.strftime("%Y-%m-%d %H:%M"),
            end_time=end_time.strftime("%Y-%m-%d %H:%M"),
            tags_filter=tags,
        )

    def _show_chart(
        self,
        metric_name: str,
        start_time: datetime,
        end_time: datetime,
        aggregation: str,
        tags: Optional[Dict[str, str]],
        width: Optional[int] = None,
        height: Optional[int] = None,
    ):
        """显示图表"""
        # 获取聚合数据
        aggregated = self.storage.aggregate_metrics(
            metric_name, start_time, end_time, aggregation, tags
        )

        if not aggregated:
            print(f"没有找到指标 '{metric_name}' 的数据")
            return

        # 获取指标信息
        info = self.storage.get_metric_info(metric_name)
        unit = info.get("unit", "") if info else ""

        # 准备数据
        data = {k: v["avg"] for k, v in aggregated.items()}

        # 设置可视化器尺寸
        if width or height:
            self.visualizer.width = width or self.visualizer.width
            self.visualizer.height = height or self.visualizer.height

        # 绘制图表
        chart = self.visualizer.plot_line_chart(
            data=data,
            title=f"{metric_name} - {aggregation}聚合",
            unit=unit,
            show_values=True,
        )

        print(chart)

        # 显示时间范围
        print(
            f"\n时间范围: {start_time.strftime('%Y-%m-%d %H:%M')} ~ {end_time.strftime('%Y-%m-%d %H:%M')}"
        )

    def _show_multiple_charts(
        self,
        start_time: datetime,
        end_time: datetime,
        aggregation: str,
        tags: Optional[Dict[str, str]],
        width: Optional[int] = None,
        height: Optional[int] = None,
    ):
        """根据标签过滤显示多个指标的图表"""
        from rich.console import Console

        console = Console()

        # 获取所有指标
        all_metrics = self.list_metrics()

        # 根据标签过滤指标
        matched_metrics = []
        for metric in all_metrics:
            # 获取该指标在时间范围内的数据
            records = self.storage.get_metrics(metric, start_time, end_time, tags)
            if records:  # 如果有匹配标签的数据
                matched_metrics.append(metric)

        if not matched_metrics:
            console.print("[yellow]没有找到匹配标签的指标数据[/yellow]")
            return

        console.print(f"[green]找到 {len(matched_metrics)} 个匹配的指标[/green]")

        # 为每个匹配的指标绘制图表
        for i, metric in enumerate(matched_metrics):
            if i > 0:
                console.print("\n" + "=" * 80 + "\n")  # 分隔符

            self._show_chart(
                metric, start_time, end_time, aggregation, tags, width, height
            )

    def _show_summary(
        self,
        metric_name: str,
        start_time: datetime,
        end_time: datetime,
        aggregation: str,
        tags: Optional[Dict[str, str]],
    ):
        """显示汇总信息"""
        # 获取聚合数据
        aggregated = self.storage.aggregate_metrics(
            metric_name, start_time, end_time, aggregation, tags
        )

        if not aggregated:
            print(f"没有找到指标 '{metric_name}' 的数据")
            return

        # 获取指标信息
        info = self.storage.get_metric_info(metric_name)
        unit = info.get("unit", "") if info else ""

        # 显示汇总
        summary = self.visualizer.show_summary(aggregated, metric_name, unit, tags)
        if summary:  # 如果返回了内容才打印（兼容性）
            print(summary)

        # 显示时间范围
        print(
            f"\n时间范围: {start_time.strftime('%Y-%m-%d %H:%M')} ~ {end_time.strftime('%Y-%m-%d %H:%M')}"
        )
