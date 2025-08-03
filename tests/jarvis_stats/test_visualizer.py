# -*- coding: utf-8 -*-
"""StatsVisualizer 单元测试"""

import os
import sys
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock, call
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
        visualizer.plot_metrics(
            metric_name="test_metric", metrics=sample_metrics_data, unit="count"
        )

        # 验证调用了绘图函数
        mock_clear.assert_called_once()
        mock_plot.assert_called_once()
        mock_title.assert_called_once_with("test_metric")
        mock_xlabel.assert_called_once_with("Time")
        mock_ylabel.assert_called_once_with("Value (count)")
        mock_show.assert_called_once()

    @patch("plotext.plot")
    @patch("plotext.show")
    @patch("plotext.plotsize")
    def test_plot_metrics_with_size(
        self, mock_plotsize, mock_show, mock_plot, visualizer, sample_metrics_data
    ):
        """测试指定大小的指标绘图"""
        visualizer.plot_metrics(
            metric_name="test_metric", metrics=sample_metrics_data, width=100, height=30
        )

        # 验证设置了图表大小
        mock_plotsize.assert_called_once_with(100, 30)

    @patch("plotext.bar")
    @patch("plotext.show")
    @patch("plotext.clear_data")
    def test_plot_aggregated_metrics(
        self, mock_clear, mock_show, mock_bar, visualizer, sample_aggregated_data
    ):
        """测试聚合数据绘图"""
        visualizer.plot_aggregated_metrics(
            metric_name="test_metric",
            aggregated_data=sample_aggregated_data,
            aggregation="hourly",
            unit="ms",
        )

        # 验证调用了柱状图函数
        mock_clear.assert_called_once()
        mock_bar.assert_called()
        mock_show.assert_called_once()

    @patch("rich.console.Console.print")
    def test_display_summary(self, mock_print, visualizer, sample_summary_data):
        """测试显示摘要信息"""
        visualizer.display_summary(sample_summary_data)

        # 验证打印了表格
        mock_print.assert_called()
        # 检查是否包含关键信息
        call_args = str(mock_print.call_args)
        assert "test_metric" in call_args or "Summary" in call_args

    @patch("rich.console.Console.print")
    def test_display_metrics_table_basic(
        self, mock_print, visualizer, sample_metrics_data
    ):
        """测试显示基本指标表格"""
        visualizer.display_metrics_table(
            metric_name="test_metric", metrics=sample_metrics_data
        )

        # 验证打印了表格
        mock_print.assert_called()

    @patch("rich.console.Console.print")
    def test_display_metrics_table_with_tags(self, mock_print, visualizer):
        """测试显示带标签的指标表格"""
        metrics_with_tags = [
            {
                "timestamp": datetime.now(),
                "value": 10,
                "tags": {"service": "api", "endpoint": "/users"},
            }
        ]

        visualizer.display_metrics_table(
            metric_name="api_calls", metrics=metrics_with_tags, unit="requests"
        )

        # 验证打印了表格
        mock_print.assert_called()

    @patch("rich.console.Console.print")
    def test_display_multiple_metrics_summary(self, mock_print, visualizer):
        """测试显示多个指标摘要"""
        summaries = {
            "metric1": {
                "count": 100,
                "total": 1000,
                "average": 10,
                "min": 1,
                "max": 50,
                "unit": "ms",
            },
            "metric2": {
                "count": 200,
                "total": 2000,
                "average": 10,
                "min": 5,
                "max": 20,
                "unit": "count",
            },
        }

        visualizer.display_multiple_metrics_summary(summaries)

        # 验证打印了表格
        mock_print.assert_called()

    def test_plot_metrics_empty_data(self, visualizer):
        """测试空数据时的处理"""
        # 不应该抛出异常
        visualizer.plot_metrics(metric_name="empty_metric", metrics=[])

    @patch("plotext.plot")
    def test_plot_metrics_single_point(self, mock_plot, visualizer):
        """测试单个数据点的绘图"""
        single_point = [{"timestamp": datetime.now(), "value": 42}]

        visualizer.plot_metrics(metric_name="single_point", metrics=single_point)

        # 应该仍然调用绘图函数
        mock_plot.assert_called()

    @patch("plotext.bar")
    @patch("plotext.xticks")
    def test_plot_aggregated_with_rotation(
        self, mock_xticks, mock_bar, visualizer, sample_aggregated_data
    ):
        """测试带标签旋转的聚合数据绘图"""
        # 添加更多的时间间隔以触发标签旋转
        many_intervals = sample_aggregated_data.copy()
        for i in range(20):
            many_intervals["intervals"].append(
                {
                    "interval": f"2024-01-{i+1:02d} 00:00",
                    "count": 10,
                    "sum": 100,
                    "average": 10,
                }
            )

        visualizer.plot_aggregated_metrics(
            metric_name="test_metric",
            aggregated_data=many_intervals,
            aggregation="daily",
        )

        # 验证设置了x轴标签旋转
        mock_xticks.assert_called()

    def test_format_value(self, visualizer):
        """测试值格式化"""
        # 测试整数
        assert visualizer._format_value(100.0) == "100"

        # 测试小数
        assert visualizer._format_value(10.123) == "10.12"

        # 测试科学记数法
        assert visualizer._format_value(0.0001234) == "1.23e-04"

    def test_terminal_compatibility(self, visualizer):
        """测试终端兼容性处理"""
        # 模拟不同的终端环境
        original_platform = sys.platform

        try:
            # 测试Windows环境
            sys.platform = "win32"
            # 不应该抛出异常
            visualizer.plot_metrics("test", [])

            # 测试Linux环境
            sys.platform = "linux"
            visualizer.plot_metrics("test", [])

        finally:
            sys.platform = original_platform

    @patch("rich.console.Console.print")
    def test_display_error_handling(self, mock_print, visualizer):
        """测试显示错误处理"""
        # 传入无效数据
        invalid_summary = {
            "metric_name": "test",
            # 缺少必要字段
        }

        # 不应该崩溃
        visualizer.display_summary(invalid_summary)

        # 应该有某种形式的输出
        assert mock_print.called

    @patch("plotext.theme")
    def test_plot_theme_setting(self, mock_theme, visualizer):
        """测试图表主题设置"""
        visualizer.plot_metrics(
            metric_name="test", metrics=[{"timestamp": datetime.now(), "value": 1}]
        )

        # 验证设置了主题
        mock_theme.assert_called()

    def test_aggregate_data_validation(self, visualizer):
        """测试聚合数据验证"""
        # 无效的聚合数据结构
        invalid_data = {"intervals": "not_a_list"}  # 应该是列表

        # 不应该崩溃
        visualizer.plot_aggregated_metrics(
            metric_name="test", aggregated_data=invalid_data, aggregation="hourly"
        )
