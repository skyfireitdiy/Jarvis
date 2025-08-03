# -*- coding: utf-8 -*-
"""StatsManager 单元测试"""

import os
import tempfile
import shutil
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import pytest

from jarvis.jarvis_stats.stats import StatsManager


class TestStatsManager:
    """StatsManager 类的测试"""

    @pytest.fixture
    def temp_storage_dir(self):
        """创建临时存储目录"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        # 清理临时目录
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def stats_manager(self, temp_storage_dir):
        """创建测试用的 StatsManager 实例"""
        # 重置类级别的存储实例
        StatsManager._storage = None
        StatsManager._visualizer = None
        return StatsManager(storage_dir=temp_storage_dir)

    def test_init(self, temp_storage_dir):
        """测试初始化"""
        manager = StatsManager(storage_dir=temp_storage_dir)
        assert manager is not None
        # 验证存储目录已创建
        assert os.path.exists(temp_storage_dir)

    def test_increment_basic(self, stats_manager):
        """测试基本的计数增加"""
        # 增加计数
        StatsManager.increment("test_metric")

        # 验证数据已保存
        metrics = StatsManager.list_metrics()
        assert "test_metric" in metrics

    def test_increment_with_amount(self, stats_manager):
        """测试带数量的计数增加"""
        # 增加指定数量
        StatsManager.increment("downloads", amount=5)

        # 获取统计数据
        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=1)
        stats = StatsManager.get_stats(
            "downloads", start_time=start_time, end_time=end_time
        )

        assert stats["total"] == 5.0

    def test_increment_with_tags(self, stats_manager):
        """测试带标签的计数增加"""
        # 使用标签
        StatsManager.increment(
            "api_calls", tags={"endpoint": "/users", "method": "GET"}
        )

        # 验证标签过滤
        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=1)
        stats = StatsManager.get_stats(
            "api_calls",
            start_time=start_time,
            end_time=end_time,
            tags={"endpoint": "/users"},
        )
        assert stats["count"] == 1

    def test_increment_with_group(self, stats_manager):
        """测试带分组的计数增加"""
        # 使用分组
        StatsManager.increment("execute_script", group="tool")

        # 验证分组标签
        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=1)
        stats = StatsManager.get_stats(
            "execute_script",
            start_time=start_time,
            end_time=end_time,
            tags={"group": "tool"},
        )
        assert stats["count"] == 1

    def test_increment_with_unit(self, stats_manager):
        """测试带单位的计数增加"""
        # 使用单位
        StatsManager.increment("response_time", amount=0.123, unit="seconds")

        # 验证数据
        metrics = StatsManager.list_metrics()
        assert "response_time" in metrics

    def test_list_metrics(self, stats_manager):
        """测试列出所有指标"""
        # 添加多个指标
        StatsManager.increment("metric1")
        StatsManager.increment("metric2", amount=2)
        StatsManager.increment("metric3", amount=3)

        # 列出所有指标
        metrics = StatsManager.list_metrics()
        assert len(metrics) >= 3
        assert "metric1" in metrics
        assert "metric2" in metrics
        assert "metric3" in metrics

    def test_get_stats_basic(self, stats_manager):
        """测试获取基本统计数据"""
        # 添加数据
        StatsManager.increment("page_views", amount=10)
        StatsManager.increment("page_views", amount=20)

        # 获取统计数据
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=1)
        stats = StatsManager.get_stats(
            "page_views", start_time=start_time, end_time=end_time
        )

        assert stats["total"] == 30.0
        assert stats["count"] == 2
        assert stats["average"] == 15.0
        assert stats["min"] == 10.0
        assert stats["max"] == 20.0

    def test_get_stats_with_time_range(self, stats_manager):
        """测试指定时间范围的统计数据"""
        # 获取最近24小时的数据
        stats = StatsManager.get_stats("test_metric", last_hours=24)
        assert isinstance(stats, dict)

        # 获取最近7天的数据
        stats = StatsManager.get_stats("test_metric", last_days=7)
        assert isinstance(stats, dict)

    def test_get_stats_with_aggregation(self, stats_manager):
        """测试聚合统计数据"""
        # 添加数据
        now = datetime.now()
        for i in range(5):
            StatsManager.increment("requests", amount=i + 1)

        # 获取聚合数据
        stats = StatsManager.get_stats("requests", last_hours=1, aggregation="hourly")
        assert isinstance(stats, dict)
        assert "intervals" in stats

    @patch("jarvis.jarvis_stats.stats.StatsManager._show_table")
    def test_show_table_format(self, mock_show_table, stats_manager):
        """测试表格格式显示"""
        # 调用显示方法
        StatsManager.show("test_metric", format="table")

        # 验证调用了正确的方法
        mock_show_table.assert_called_once()

    @patch("jarvis.jarvis_stats.stats.StatsManager._show_chart")
    def test_show_chart_format(self, mock_show_chart, stats_manager):
        """测试图表格式显示"""
        # 调用显示方法
        StatsManager.show("test_metric", format="chart")

        # 验证调用了正确的方法
        mock_show_chart.assert_called_once()

    @patch("jarvis.jarvis_stats.stats.StatsManager._show_summary")
    def test_show_summary_format(self, mock_show_summary, stats_manager):
        """测试摘要格式显示"""
        # 调用显示方法
        StatsManager.show("test_metric", format="summary")

        # 验证调用了正确的方法
        mock_show_summary.assert_called_once()

    @patch("jarvis.jarvis_stats.stats.StatsManager._show_metrics_summary")
    def test_show_all_metrics_summary(self, mock_show_metrics_summary, stats_manager):
        """测试显示所有指标摘要"""
        # 不指定metric_name时显示所有指标摘要
        StatsManager.show()

        # 验证调用了正确的方法
        mock_show_metrics_summary.assert_called_once()

    @patch("jarvis.jarvis_stats.stats.StatsManager._show_chart")
    def test_plot_single_metric(self, mock_show_chart, stats_manager):
        """测试绘制单个指标图表"""
        # 绘制单个指标
        StatsManager.plot("response_time", last_hours=24)

        # 验证调用了正确的方法
        mock_show_chart.assert_called_once()

    @patch("jarvis.jarvis_stats.stats.StatsManager._show_multiple_charts")
    def test_plot_multiple_metrics(self, mock_show_multiple_charts, stats_manager):
        """测试绘制多个指标图表"""
        # 不指定metric_name时绘制多个图表
        StatsManager.plot(tags={"service": "api"}, last_days=7)

        # 验证调用了正确的方法
        mock_show_multiple_charts.assert_called_once()

    def test_clear_metrics(self, stats_manager):
        """测试清除指标"""
        # 添加数据
        StatsManager.increment("temp_metric")

        # 清除指标
        StatsManager.clear_metrics(["temp_metric"])

        # 验证指标已清除
        metrics = StatsManager.list_metrics()
        assert "temp_metric" not in metrics

    def test_analyze_basic(self, stats_manager):
        """测试基本分析功能"""
        # 添加测试数据
        for i in range(10):
            StatsManager.increment("test_analysis", amount=i)

        # 执行分析
        result = StatsManager.analyze("test_analysis", last_hours=1)

        assert result is not None
        assert "summary" in result
        assert "trend" in result

    def test_export_import(self, stats_manager, temp_storage_dir):
        """测试数据导出和导入"""
        # 添加测试数据
        StatsManager.increment("export_test", amount=100)

        # 导出数据
        export_file = os.path.join(temp_storage_dir, "export.json")
        StatsManager.export_stats(
            output_file=export_file, metric_names=["export_test"], last_days=1
        )

        # 验证导出文件存在
        assert os.path.exists(export_file)

        # 创建新的管理器并导入数据
        new_dir = tempfile.mkdtemp()
        try:
            new_manager = StatsManager(storage_dir=new_dir)
            StatsManager.import_stats(export_file)

            # 验证数据已导入
            metrics = StatsManager.list_metrics()
            assert "export_test" in metrics
        finally:
            shutil.rmtree(new_dir, ignore_errors=True)

    def test_concurrent_increment(self, stats_manager):
        """测试并发增加计数"""
        import threading

        def increment_worker():
            for _ in range(10):
                StatsManager.increment("concurrent_test")

        # 创建多个线程并发写入
        threads = []
        for _ in range(5):
            t = threading.Thread(target=increment_worker)
            threads.append(t)
            t.start()

        # 等待所有线程完成
        for t in threads:
            t.join()

        # 验证数据完整性
        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=1)
        stats = StatsManager.get_stats(
            "concurrent_test", start_time=start_time, end_time=end_time
        )
        assert stats["count"] == 50  # 5线程 * 10次

    def test_error_handling(self, stats_manager):
        """测试错误处理"""
        # 测试无效的指标名称
        with pytest.raises(ValueError):
            StatsManager.increment("")

        # 测试无效的时间范围
        end_time = datetime.now()
        start_time = end_time + timedelta(days=1)  # 开始时间晚于结束时间
        result = StatsManager.get_stats(
            "test_metric", start_time=start_time, end_time=end_time
        )
        assert result["count"] == 0  # 应该返回空结果而不是报错
