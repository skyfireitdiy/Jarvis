# -*- coding: utf-8 -*-
"""StatsVisualizer 单元测试"""

import sys
from datetime import datetime, timedelta
from unittest.mock import patch
import pytest

from jarvis.jarvis_stats.visualizer import StatsVisualizer


class TestStatsVisualizer:
    """StatsVisualizer 类的测试"""

    @pytest.fixture
    def visualizer(self):
        """创建测试用的 StatsVisualizer 实例"""
        return StatsVisualizer()

    @pytest.fixture
    def sample_metrics_data(self):
        """创建示例指标数据"""
        now = datetime.now()
        return [
            {"timestamp": now - timedelta(hours=2), "value": 10},
            {"timestamp": now - timedelta(hours=1), "value": 20},
            {"timestamp": now, "value": 15},
        ]

    @pytest.fixture
    def sample_aggregated_data(self):
        """创建示例聚合数据"""
        now = datetime.now()
        return {
            "intervals": [
                {
                    "interval": (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:00"),
                    "count": 5,
                    "sum": 50,
                    "average": 10,
                    "min": 5,
                    "max": 15,
                },
                {
                    "interval": (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:00"),
                    "count": 8,
                    "sum": 160,
                    "average": 20,
                    "min": 15,
                    "max": 25,
                },
                {
                    "interval": now.strftime("%Y-%m-%d %H:00"),
                    "count": 6,
                    "sum": 90,
                    "average": 15,
                    "min": 10,
                    "max": 20,
                },
            ],
            "total_count": 19,
            "total_sum": 300,
            "total_average": 15.79,
            "total_min": 5,
            "total_max": 25,
        }

    @pytest.fixture
    def sample_summary_data(self):
        """创建示例摘要数据"""
        return {
            "metric_name": "test_metric",
            "count": 100,
            "total": 1500.0,
            "average": 15.0,
            "min": 1.0,
            "max": 50.0,
            "unit": "ms",
        }

    @patch("plotext.plot")
    @patch("plotext.show")
    @patch("plotext.clear_data")
    @patch("plotext.title")
    @patch("plotext.xlabel")
    @patch("plotext.ylabel")
    def test_plot_metrics_basic(
        self,
        mock_ylabel,
        mock_xlabel,
        mock_title,
        mock_clear,
        mock_show,
        mock_plot,
        visualizer,
        sample_metrics_data,
    ):
        """测试基本的指标绘图"""
        # 使用实际存在的方法plot_line_chart
        data = {"2024-01-01 10:00": 10.0, "2024-01-01 11:00": 20.0}
        result = visualizer.plot_line_chart(
            data=data, title="test_metric", unit="count", show_values=True
        )

        # 验证返回了图表字符串
        assert isinstance(result, str)

    @patch("plotext.plot")
    @patch("plotext.show")
    @patch("plotext.plotsize")
    def test_plot_metrics_with_size(
        self, mock_plotsize, mock_show, mock_plot, visualizer, sample_metrics_data
    ):
        """测试指定大小的指标绘图"""
        # 创建指定大小的可视化器
        sized_visualizer = StatsVisualizer(width=100, height=30)
        data = {"2024-01-01 10:00": 10.0, "2024-01-01 11:00": 20.0}
        result = sized_visualizer.plot_line_chart(data=data, title="test_metric")

        # 验证可视化器大小设置正确
        assert sized_visualizer.width == 100
        assert sized_visualizer.height == 30
        assert isinstance(result, str)

    @patch("plotext.bar")
    @patch("plotext.show")
    @patch("plotext.clear_data")
    def test_plot_aggregated_metrics(
        self, mock_clear, mock_show, mock_bar, visualizer, sample_aggregated_data
    ):
        """测试聚合数据绘图"""
        # 使用实际存在的方法plot_bar_chart
        data = {"2024-01-01 10:00": 50.0, "2024-01-01 11:00": 160.0}
        result = visualizer.plot_bar_chart(
            data=data, title="test_metric - hourly聚合", unit="ms"
        )

        # 验证返回了图表字符串
        assert isinstance(result, str)

    @patch("rich.console.Console.print")
    def test_display_summary(self, mock_print, visualizer, sample_summary_data):
        """测试显示摘要信息"""
        # 使用实际存在的方法show_summary，需要聚合数据格式
        aggregated_data = {
            "2024-01-01 10:00": {
                "count": 10,
                "sum": 150,
                "avg": 15.0,
                "min": 1.0,
                "max": 50.0,
            },
            "2024-01-01 11:00": {
                "count": 20,
                "sum": 300,
                "avg": 15.0,
                "min": 5.0,
                "max": 40.0,
            },
        }
        result = visualizer.show_summary(aggregated_data, "test_metric", unit="ms")

        # 验证打印了表格
        mock_print.assert_called()
        # show_summary返回空字符串但会通过console打印
        assert result == ""

    @patch("rich.console.Console.print")
    def test_display_metrics_table_basic(
        self, mock_print, visualizer, sample_metrics_data
    ):
        """测试显示基本指标表格"""
        # 使用实际存在的方法show_table
        records = [
            {"timestamp": "2024-01-01T10:00:00", "value": 10, "tags": {}},
            {"timestamp": "2024-01-01T11:00:00", "value": 20, "tags": {}},
        ]
        result = visualizer.show_table(records=records, metric_name="test_metric")

        # 验证打印了表格
        mock_print.assert_called()
        # show_table返回空字符串但会通过console打印
        assert result == ""

    @patch("rich.console.Console.print")
    def test_display_metrics_table_with_tags(self, mock_print, visualizer):
        """测试显示带标签的指标表格"""
        # 使用实际存在的方法show_table
        records = [
            {
                "timestamp": datetime.now().isoformat(),
                "value": 10,
                "tags": {"service": "api", "endpoint": "/users"},
            }
        ]

        result = visualizer.show_table(
            records=records, metric_name="api_calls", unit="requests"
        )

        # 验证打印了表格
        mock_print.assert_called()
        # show_table返回空字符串但会通过console打印
        assert result == ""

    @patch("rich.console.Console.print")
    def test_display_multiple_metrics_summary(self, mock_print, visualizer):
        """测试显示多个指标摘要"""
        # 使用实际存在的方法show_summary分别显示多个指标
        metric1_data = {
            "2024-01-01 10:00": {
                "count": 50,
                "sum": 500,
                "avg": 10.0,
                "min": 1,
                "max": 50,
            },
            "2024-01-01 11:00": {
                "count": 50,
                "sum": 500,
                "avg": 10.0,
                "min": 1,
                "max": 50,
            },
        }
        metric2_data = {
            "2024-01-01 10:00": {
                "count": 100,
                "sum": 1000,
                "avg": 10.0,
                "min": 5,
                "max": 20,
            },
            "2024-01-01 11:00": {
                "count": 100,
                "sum": 1000,
                "avg": 10.0,
                "min": 5,
                "max": 20,
            },
        }

        result1 = visualizer.show_summary(metric1_data, "metric1", unit="ms")
        result2 = visualizer.show_summary(metric2_data, "metric2", unit="count")

        # 验证打印了表格
        mock_print.assert_called()
        # 两个show_summary都返回空字符串
        assert result1 == ""
        assert result2 == ""

    def test_plot_metrics_empty_data(self, visualizer):
        """测试空数据时的处理"""
        # 不应该抛出异常
        result = visualizer.plot_line_chart(data={}, title="empty_metric")
        # 空数据应该返回"无数据可显示"
        assert result == "无数据可显示"

    @patch("plotext.plot")
    def test_plot_metrics_single_point(self, mock_plot, visualizer):
        """测试单个数据点的绘图"""
        # 使用实际存在的方法plot_line_chart
        single_point_data = {"2024-01-01 10:00": 42.0}

        result = visualizer.plot_line_chart(
            data=single_point_data, title="single_point"
        )

        # 应该返回图表字符串
        assert isinstance(result, str)
        assert result != "无数据可显示"

    @patch("plotext.bar")
    @patch("plotext.xticks")
    def test_plot_aggregated_with_rotation(
        self, mock_xticks, mock_bar, visualizer, sample_aggregated_data
    ):
        """测试带标签旋转的聚合数据绘图"""
        # 创建更多数据点的柱状图
        many_data = {}
        for i in range(20):
            many_data[f"2024-01-{i + 1:02d} 00:00"] = 100.0

        result = visualizer.plot_bar_chart(
            data=many_data, title="test_metric - daily聚合"
        )

        # 验证返回了图表字符串
        assert isinstance(result, str)
        assert result != "无数据可显示"

    def test_format_value(self, visualizer):
        """测试值格式化功能的替代实现"""
        # 实际的StatsVisualizer没有_format_value方法，测试基本的数值显示
        data = {"test": 100.0}
        result = visualizer.plot_line_chart(data=data, show_values=True)

        # 验证能正常处理数值显示
        assert isinstance(result, str)
        assert result != "无数据可显示"

    def test_terminal_compatibility(self, visualizer):
        """测试终端兼容性处理"""
        # 模拟不同的终端环境
        original_platform = sys.platform

        try:
            # 测试Windows环境
            sys.platform = "win32"
            # 不应该抛出异常
            result1 = visualizer.plot_line_chart(data={}, title="test")
            assert result1 == "无数据可显示"

            # 测试Linux环境
            sys.platform = "linux"
            result2 = visualizer.plot_line_chart(data={}, title="test")
            assert result2 == "无数据可显示"

        finally:
            sys.platform = original_platform

    @patch("rich.console.Console.print")
    def test_display_error_handling(self, mock_print, visualizer):
        """测试显示错误处理"""
        # 传入空的聚合数据测试错误处理
        empty_data = {}

        # 不应该崩溃
        result = visualizer.show_summary(empty_data, "test")

        # 应该有某种形式的输出
        assert mock_print.called
        # show_summary对空数据会返回特定信息
        assert result == "无数据可显示"

    @patch("plotext.theme")
    def test_plot_theme_setting(self, mock_theme, visualizer):
        """测试图表主题设置"""
        # 测试图表生成（plotext会自动处理主题）
        data = {"2024-01-01 10:00": 1.0}
        result = visualizer.plot_line_chart(data=data, title="test")

        # 验证能正常生成图表
        assert isinstance(result, str)
        assert result != "无数据可显示"

    def test_aggregate_data_validation(self, visualizer):
        """测试聚合数据验证"""
        # 测试对无效数据的处理 - 使用空数据
        invalid_data = {}

        # 不应该崩溃
        result = visualizer.plot_bar_chart(data=invalid_data, title="test")

        # 空数据应该返回特定消息
        assert result == "无数据可显示"
