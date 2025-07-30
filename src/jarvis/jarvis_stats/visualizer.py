"""
统计数据可视化模块

提供终端图形化展示功能
"""

import os

from typing import Dict, List, Optional, Any
from collections import OrderedDict


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
        绘制折线图

        Args:
            data: 数据字典，键为时间标签，值为数值
            title: 图表标题
            unit: 单位
            show_values: 是否显示数值

        Returns:
            图表字符串
        """
        if not data:
            return "无数据可显示"

        # 排序数据
        sorted_data = OrderedDict(sorted(data.items()))

        # 提取值和标签
        labels = list(sorted_data.keys())
        values = list(sorted_data.values())

        # 计算数值范围
        min_val = min(values)
        max_val = max(values)

        # 如果所有值相同，调整范围
        if min_val == max_val:
            if min_val == 0:
                min_val = -1
                max_val = 1
            else:
                min_val = min_val * 0.9
                max_val = max_val * 1.1

        # 创建图表画布
        chart_width = self.width - 10  # 留出y轴标签空间
        chart_height = self.height - 5  # 留出x轴标签空间

        # 初始化画布
        canvas = [[" " for _ in range(chart_width)] for _ in range(chart_height)]

        # 计算缩放因子
        x_scale = (chart_width - 1) / max(len(values) - 1, 1)
        y_scale = (chart_height - 1) / (max_val - min_val)

        # 绘制坐标轴
        for i in range(chart_height):
            canvas[i][0] = "│"
        for j in range(chart_width):
            canvas[chart_height - 1][j] = "─"
        canvas[chart_height - 1][0] = "└"

        # 绘制数据点和连线
        points = []
        for i, value in enumerate(values):
            x = int(i * x_scale) + 1
            y = chart_height - 1 - int((value - min_val) * y_scale)
            y = max(0, min(chart_height - 1, y))  # 确保在范围内

            if 0 <= x < chart_width and 0 <= y < chart_height:
                points.append((x, y, value))
                canvas[y][x] = "●"

        # 连接数据点
        for i in range(len(points) - 1):
            x1, y1, _ = points[i]
            x2, y2, _ = points[i + 1]
            self._draw_line(canvas, x1, y1, x2, y2)

        # 构建输出
        output = []

        # 标题
        if title:
            output.append(f"\n{title.center(self.width)}")
            output.append("=" * self.width)

        # Y轴标签和图表
        y_labels = self._generate_y_labels(min_val, max_val, chart_height)

        for i, row in enumerate(canvas):
            label = y_labels.get(i, "")
            line = f"{label:>8} " + "".join(row)
            output.append(line)

        # X轴标签
        x_labels = self._generate_x_labels(labels, chart_width)
        output.append(" " * 9 + x_labels)

        # 单位
        if unit:
            output.append(f"\n单位: {unit}")

        # 统计信息
        if show_values:
            output.append(
                f"\n最小值: {min_val:.2f}, 最大值: {max_val:.2f}, 平均值: {sum(values)/len(values):.2f}"
            )

        return "\n".join(output)

    def plot_bar_chart(
        self,
        data: Dict[str, float],
        title: str = "",
        unit: Optional[str] = None,
        horizontal: bool = False,
    ) -> str:
        """
        绘制柱状图

        Args:
            data: 数据字典
            title: 图表标题
            unit: 单位
            horizontal: 是否横向

        Returns:
            图表字符串
        """
        if not data:
            return "无数据可显示"

        output = []

        # 标题
        if title:
            output.append(f"\n{title.center(self.width)}")
            output.append("=" * self.width)

        # 找出最大值用于缩放
        max_value = max(data.values()) if data.values() else 1

        if horizontal:
            # 横向柱状图
            max_label_len = max(len(str(k)) for k in data.keys())
            bar_width = self.width - max_label_len - 15

            for label, value in data.items():
                bar_len = int((value / max_value) * bar_width)
                bar = "█" * bar_len
                output.append(f"{str(label):>{max_label_len}} │{bar} {value:.2f}")
        else:
            # 纵向柱状图
            bar_height = self.height - 5
            labels = list(data.keys())
            values = list(data.values())

            # 创建画布
            canvas = [[" " for _ in range(len(labels) * 4)] for _ in range(bar_height)]

            # 绘制柱子
            for i, (label, value) in enumerate(zip(labels, values)):
                height = int((value / max_value) * bar_height)
                x = i * 4 + 1

                for y in range(bar_height - height, bar_height):
                    if y >= 0 and x < len(canvas[0]):
                        canvas[y][x] = "█"
                        if x + 1 < len(canvas[0]):
                            canvas[y][x + 1] = "█"

            # 输出画布
            for row in canvas:
                output.append("".join(row))

            # X轴标签
            label_line = ""
            for i, label in enumerate(labels):
                x = i * 4
                label_line += f"{label[:3]:>4}"
            output.append(label_line)

        # 单位
        if unit:
            output.append(f"\n单位: {unit}")

        return "\n".join(output)

    def show_summary(
        self,
        aggregated_data: Dict[str, Dict[str, Any]],
        metric_name: str,
        unit: Optional[str] = None,
    ) -> str:
        """
        显示数据摘要

        Args:
            aggregated_data: 聚合后的数据
            metric_name: 指标名称
            unit: 单位

        Returns:
            摘要字符串
        """
        if not aggregated_data:
            return "无数据可显示"

        output = []
        output.append(f"\n{metric_name} 统计摘要")
        output.append("=" * self.width)

        # 表头
        header = f"{'时间':^20} | {'计数':>6} | {'总和':>10} | {'平均':>10} | {'最小':>10} | {'最大':>10}"
        output.append(header)
        output.append("-" * len(header))

        # 数据行
        for time_key, stats in sorted(aggregated_data.items()):
            row = f"{time_key:^20} | {stats['count']:>6} | {stats['sum']:>10.2f} | "
            row += (
                f"{stats['avg']:>10.2f} | {stats['min']:>10.2f} | {stats['max']:>10.2f}"
            )
            output.append(row)

        # 单位
        if unit:
            output.append(f"\n单位: {unit}")

        return "\n".join(output)

    def _draw_line(self, canvas: List[List[str]], x1: int, y1: int, x2: int, y2: int):
        """在画布上绘制线条"""
        # 使用Bresenham算法绘制线条
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx - dy

        x, y = x1, y1

        while True:
            if 0 <= x < len(canvas[0]) and 0 <= y < len(canvas):
                if canvas[y][x] == " ":
                    if dx > dy:
                        canvas[y][x] = "─"
                    else:
                        canvas[y][x] = "│"

            if x == x2 and y == y2:
                break

            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy

    def _generate_y_labels(
        self, min_val: float, max_val: float, height: int
    ) -> Dict[int, str]:
        """生成Y轴标签"""
        labels = {}

        # 在顶部、中部和底部放置标签
        positions = [0, height // 2, height - 1]
        values = [max_val, (max_val + min_val) / 2, min_val]

        for pos, val in zip(positions, values):
            labels[pos] = f"{val:.1f}"

        return labels

    def _generate_x_labels(self, labels: List[str], width: int) -> str:
        """生成X轴标签"""
        if not labels:
            return ""

        # 简化标签（如果是时间格式）
        simplified_labels = []
        for label in labels:
            if len(label) > 10:
                # 尝试提取时间部分
                parts = label.split()
                if len(parts) >= 2:
                    simplified_labels.append(parts[1][:5])  # 只取时间
                else:
                    simplified_labels.append(label[:8])
            else:
                simplified_labels.append(label)

        # 根据空间决定显示多少标签
        max_labels = width // 10
        step = max(1, len(simplified_labels) // max_labels)

        label_line = ""
        for i in range(0, len(simplified_labels), step):
            if i < len(simplified_labels):
                label_line += f"{simplified_labels[i]:>10}"

        return label_line
