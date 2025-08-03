# -*- coding: utf-8 -*-
"""StatsStorage 单元测试"""

import os
import tempfile
import shutil
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

from jarvis.jarvis_stats.storage import StatsStorage


class TestStatsStorage:
    """StatsStorage 类的测试"""

    @pytest.fixture
    def temp_storage_dir(self):
        """创建临时存储目录"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        # 清理临时目录
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def storage(self, temp_storage_dir):
        """创建测试用的 StatsStorage 实例"""
        return StatsStorage(storage_dir=temp_storage_dir)

    def test_init_default_dir(self):
        """测试使用默认目录初始化"""
        storage = StatsStorage()
        assert storage.storage_dir == Path.home() / ".jarvis" / "stats"

    def test_init_custom_dir(self, temp_storage_dir):
        """测试使用自定义目录初始化"""
        storage = StatsStorage(storage_dir=temp_storage_dir)
        assert str(storage.storage_dir) == temp_storage_dir
        assert storage.storage_dir.exists()
        assert storage.data_dir.exists()
        assert storage.meta_file.exists()

    def test_add_metric_basic(self, storage):
        """测试添加基本指标"""
        timestamp = datetime.now()
        storage.add_metric(
            metric_name="test_metric", value=10.5, unit="count", timestamp=timestamp
        )

        # 验证元数据已更新
        meta = storage._load_json(storage.meta_file)
        assert "test_metric" in meta["metrics"]
        assert meta["metrics"]["test_metric"]["unit"] == "count"

    def test_add_metric_with_tags(self, storage):
        """测试添加带标签的指标"""
        timestamp = datetime.now()
        tags = {"service": "api", "endpoint": "/users"}

        storage.add_metric(
            metric_name="api_calls", value=1, timestamp=timestamp, tags=tags
        )

        # 验证数据文件
        date_key = timestamp.strftime("%Y-%m-%d")
        date_file = storage._get_data_file(date_key)
        data = storage._load_json(date_file)

        assert "api_calls" in data
        # 检查是否存储了标签数据
        hour_key = timestamp.strftime("%H")
        assert hour_key in data["api_calls"]

    def test_add_metric_auto_timestamp(self, storage):
        """测试自动使用当前时间戳"""
        storage.add_metric(metric_name="auto_timestamp", value=5.0)

        # 验证数据已保存
        metrics = storage.list_metrics()
        assert "auto_timestamp" in metrics

    def test_get_metrics_basic(self, storage):
        """测试获取基本指标数据"""
        # 添加测试数据
        now = datetime.now()
        storage.add_metric("test_get", value=10, timestamp=now)
        storage.add_metric("test_get", value=20, timestamp=now)

        # 获取数据
        start_time = now - timedelta(minutes=5)
        end_time = now + timedelta(minutes=5)
        metrics = storage.get_metrics("test_get", start_time, end_time)

        assert len(metrics) == 2
        assert metrics[0]["value"] == 10
        assert metrics[1]["value"] == 20

    def test_get_metrics_with_tags_filter(self, storage):
        """测试使用标签过滤获取数据"""
        now = datetime.now()
        # 添加不同标签的数据
        storage.add_metric(
            "api_calls", value=1, timestamp=now, tags={"endpoint": "/users"}
        )
        storage.add_metric(
            "api_calls", value=2, timestamp=now, tags={"endpoint": "/posts"}
        )
        storage.add_metric(
            "api_calls", value=3, timestamp=now, tags={"endpoint": "/users"}
        )

        # 过滤获取
        start_time = now - timedelta(minutes=5)
        end_time = now + timedelta(minutes=5)
        metrics = storage.get_metrics(
            "api_calls", start_time, end_time, tags={"endpoint": "/users"}
        )

        assert len(metrics) == 2
        assert all(m["value"] in [1, 3] for m in metrics)

    def test_list_metrics(self, storage):
        """测试列出所有指标"""
        # 添加多个指标
        storage.add_metric("metric1", value=1)
        storage.add_metric("metric2", value=2)
        storage.add_metric("metric3", value=3)

        # 列出所有指标
        metrics = storage.list_metrics()
        assert len(metrics) >= 3
        assert "metric1" in metrics
        assert "metric2" in metrics
        assert "metric3" in metrics

    def test_aggregate_metrics_hourly(self, storage):
        """测试按小时聚合"""
        # 添加一小时内的数据
        base_time = datetime.now().replace(minute=0, second=0, microsecond=0)
        for i in range(5):
            timestamp = base_time + timedelta(minutes=i * 10)
            storage.add_metric("hourly_test", value=i + 1, timestamp=timestamp)

        # 聚合数据
        start_time = base_time - timedelta(hours=1)
        end_time = base_time + timedelta(hours=2)
        result = storage.aggregate_metrics(
            "hourly_test", start_time, end_time, "hourly"
        )

        assert "intervals" in result
        assert len(result["intervals"]) > 0
        assert result["total_count"] == 5
        assert result["total_sum"] == 15  # 1+2+3+4+5

    def test_aggregate_metrics_daily(self, storage):
        """测试按天聚合"""
        # 添加多天的数据
        base_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        for day in range(3):
            for hour in range(4):
                timestamp = base_time + timedelta(days=day, hours=hour * 6)
                storage.add_metric("daily_test", value=10, timestamp=timestamp)

        # 聚合数据
        start_time = base_time - timedelta(days=1)
        end_time = base_time + timedelta(days=4)
        result = storage.aggregate_metrics("daily_test", start_time, end_time, "daily")

        assert "intervals" in result
        assert len(result["intervals"]) >= 3  # 至少3天的数据

    def test_clear_metric(self, storage):
        """测试清除单个指标"""
        # 添加数据
        storage.add_metric("to_clear", value=100)

        # 清除指标
        storage.clear_metric("to_clear")

        # 验证已清除
        metrics = storage.list_metrics()
        assert "to_clear" not in metrics

        # 验证元数据已更新
        meta = storage._load_json(storage.meta_file)
        assert "to_clear" not in meta["metrics"]

    def test_clear_all_metrics(self, storage):
        """测试清除所有指标"""
        # 添加多个指标
        storage.add_metric("metric1", value=1)
        storage.add_metric("metric2", value=2)

        # 清除所有
        storage.clear_all_metrics()

        # 验证已清除
        metrics = storage.list_metrics()
        assert len(metrics) == 0

        # 验证数据目录已清空
        data_files = list(storage.data_dir.glob("*.json"))
        assert len(data_files) == 0

    def test_export_data(self, storage, temp_storage_dir):
        """测试导出数据"""
        # 添加测试数据
        now = datetime.now()
        storage.add_metric("export_test", value=50, timestamp=now)

        # 导出数据
        export_file = Path(temp_storage_dir) / "export.json"
        start_time = now - timedelta(days=1)
        end_time = now + timedelta(days=1)

        storage.export_data(
            str(export_file),
            metric_names=["export_test"],
            start_time=start_time,
            end_time=end_time,
        )

        # 验证导出文件
        assert export_file.exists()
        with open(export_file, "r") as f:
            exported = json.load(f)

        assert "metadata" in exported
        assert "data" in exported
        assert "export_test" in exported["data"]

    def test_import_data(self, storage, temp_storage_dir):
        """测试导入数据"""
        # 准备导入数据
        import_data = {
            "metadata": {
                "export_time": datetime.now().isoformat(),
                "metrics": {
                    "imported_metric": {
                        "unit": "count",
                        "created_at": datetime.now().isoformat(),
                    }
                },
            },
            "data": {
                "imported_metric": [
                    {"timestamp": datetime.now().isoformat(), "value": 999, "tags": {}}
                ]
            },
        }

        # 写入导入文件
        import_file = Path(temp_storage_dir) / "import.json"
        with open(import_file, "w") as f:
            json.dump(import_data, f)

        # 导入数据
        storage.import_data(str(import_file))

        # 验证导入成功
        metrics = storage.list_metrics()
        assert "imported_metric" in metrics

    def test_get_metrics_summary(self, storage):
        """测试获取指标摘要"""
        # 添加测试数据
        now = datetime.now()
        for i in range(10):
            storage.add_metric("summary_test", value=i, timestamp=now)

        # 获取摘要
        start_time = now - timedelta(hours=1)
        end_time = now + timedelta(hours=1)
        summary = storage.get_metrics_summary("summary_test", start_time, end_time)

        assert summary["count"] == 10
        assert summary["total"] == 45  # 0+1+2+...+9
        assert summary["average"] == 4.5
        assert summary["min"] == 0
        assert summary["max"] == 9

    def test_concurrent_write(self, storage):
        """测试并发写入"""
        import threading

        def write_worker(worker_id):
            for i in range(10):
                storage.add_metric("concurrent_test", value=worker_id * 10 + i)

        # 创建多个线程并发写入
        threads = []
        for i in range(5):
            t = threading.Thread(target=write_worker, args=(i,))
            threads.append(t)
            t.start()

        # 等待所有线程完成
        for t in threads:
            t.join()

        # 验证数据完整性
        metrics = storage.list_metrics()
        assert "concurrent_test" in metrics

    def test_file_corruption_recovery(self, storage):
        """测试文件损坏时的恢复能力"""
        # 写入损坏的JSON文件
        corrupted_file = storage.data_dir / "stats_2024-01-01.json"
        with open(corrupted_file, "w") as f:
            f.write("{corrupted json")

        # 尝试读取，应该返回空字典而不是崩溃
        data = storage._load_json(corrupted_file)
        assert data == {}

    def test_date_range_query(self, storage):
        """测试跨日期范围查询"""
        # 添加多天的数据
        base_time = datetime.now()
        for days_ago in range(5):
            timestamp = base_time - timedelta(days=days_ago)
            storage.add_metric("date_range_test", value=days_ago, timestamp=timestamp)

        # 查询3天的数据
        start_time = base_time - timedelta(days=3)
        end_time = base_time
        metrics = storage.get_metrics("date_range_test", start_time, end_time)

        # 应该获取到4条数据（0,1,2,3天前的）
        assert len(metrics) >= 4
