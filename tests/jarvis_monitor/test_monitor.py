"""
测试监控告警系统
"""

import pytest
from jarvis.jarvis_monitor import (
    check_system_health,
    check_service_health,
    get_health_summary,
    send_alert,
    check_thresholds,
    get_alert_history,
    get_thresholds,
    set_threshold,
)

# Metrics functions imported directly
from jarvis.jarvis_monitor.metrics import (
    increment_counter,
    set_gauge,
    observe_histogram,
    get_metrics_summary,
)


class TestHealthCheck:
    """测试健康检查功能"""

    @pytest.mark.monitoring
    def test_system_health_check(self):
        """测试系统健康检查"""
        health = check_system_health()

        assert health is not None
        assert "cpu_usage" in health
        assert "memory_usage" in health
        assert "disk_usage" in health
        assert "timestamp" in health
        assert "status" in health

        # 验证值在合理范围内
        assert 0 <= health["cpu_usage"] <= 100
        assert 0 <= health["memory_usage"] <= 100
        assert 0 <= health["disk_usage"] <= 100

    @pytest.mark.monitoring
    def test_service_health_check(self):
        """测试服务健康检查"""
        health = check_service_health()

        assert health is not None
        assert "agent_status" in health
        assert "code_agent_status" in health
        assert "memory_organizer_status" in health
        assert "overall_status" in health
        assert "timestamp" in health

        # 验证状态值
        assert health["overall_status"] in ["healthy", "degraded"]

    @pytest.mark.monitoring
    def test_health_summary(self):
        """测试健康状态摘要"""
        summary = get_health_summary()

        assert summary is not None
        assert "system" in summary
        assert "services" in summary
        assert "overall_status" in summary
        assert "timestamp" in summary


class TestMetrics:
    """测试指标收集功能"""

    def setup_method(self):
        """每个测试前重置指标"""
        from jarvis.jarvis_monitor.metrics import reset_metrics

        reset_metrics()

    @pytest.mark.monitoring
    def test_increment_counter(self):
        """测试计数器递增"""
        initial = get_metrics_summary()["counters"]["requests_total"]

        increment_counter("requests")

        summary = get_metrics_summary()
        assert summary["counters"]["requests_total"] == initial + 1

    @pytest.mark.monitoring
    def test_set_gauge(self):
        """测试仪表盘设置"""
        set_gauge("system_cpu", 75.5)

        summary = get_metrics_summary()
        assert summary["gauges"]["system_cpu_percent"] == 75.5

    @pytest.mark.monitoring
    def test_observe_histogram(self):
        """测试直方图观测"""
        observe_histogram("request_latency", 0.5)
        observe_histogram("request_latency", 1.0)

        summary = get_metrics_summary()
        latency = summary["histograms"]["request_latency_seconds"]

        assert latency["count"] == 2
        assert latency["min"] == 0.5
        assert latency["max"] == 1.0

    @pytest.mark.monitoring
    def test_metrics_summary(self):
        """测试指标摘要"""
        increment_counter("requests")
        set_gauge("system_cpu", 50.0)
        observe_histogram("request_latency", 0.3)

        summary = get_metrics_summary()

        assert "counters" in summary
        assert "gauges" in summary
        assert "histograms" in summary
        assert summary["counters"]["requests_total"] >= 0
        assert summary["gauges"]["system_cpu_percent"] >= 0


class TestAlerting:
    """测试告警功能"""

    def setup_method(self):
        """每个测试前清空告警历史"""
        from jarvis.jarvis_monitor.alerting import clear_alert_history

        clear_alert_history()

    @pytest.mark.monitoring
    def test_send_alert(self):
        """测试发送告警"""
        alert = {
            "summary": "Test alert",
            "severity": "warning",
            "value": 80.0,
        }

        result = send_alert(alert)

        assert result is True
        assert "timestamp" in alert

        history = get_alert_history()
        assert len(history) >= 1
        assert history[-1]["summary"] == "Test alert"

    @pytest.mark.monitoring
    def test_check_thresholds_normal(self):
        """测试阈值检查（正常情况）"""
        metrics = {
            "cpu_usage": 50.0,
            "memory_usage": 60.0,
            "disk_usage": 70.0,
        }

        alerts = check_thresholds(metrics)

        assert len(alerts) == 0

    @pytest.mark.monitoring
    def test_check_thresholds_high_cpu(self):
        """测试阈值检查（CPU高）"""
        metrics = {
            "cpu_usage": 85.0,
            "memory_usage": 60.0,
            "disk_usage": 70.0,
        }

        alerts = check_thresholds(metrics)

        assert len(alerts) == 1
        assert alerts[0]["type"] == "cpu_high"
        assert alerts[0]["value"] == 85.0

    @pytest.mark.monitoring
    def test_get_thresholds(self):
        """测试获取阈值"""
        thresholds = get_thresholds()

        assert "cpu_usage" in thresholds
        assert "memory_usage" in thresholds
        assert "disk_usage" in thresholds
        assert thresholds["cpu_usage"] == 80.0

    @pytest.mark.monitoring
    def test_set_threshold(self):
        """测试设置阈值"""
        set_threshold("cpu_usage", 90.0)

        thresholds = get_thresholds()
        assert thresholds["cpu_usage"] == 90.0
