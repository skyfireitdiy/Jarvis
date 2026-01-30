"""
Prometheus指标导出模块

提供Prometheus指标收集和导出功能。
"""

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# 定义Prometheus指标
# 注意：prometheus_client库可能会很重，这里使用轻量级实现

# Counter计数器
REQUEST_COUNT = 0
ERROR_COUNT = 0

# Histogram直方图（延迟分布）
REQUEST_LATENCY_SAMPLES = []

# Gauge仪表盘（当前值）
SYSTEM_CPU = 0.0
SYSTEM_MEMORY = 0.0
ACTIVE_CONNECTIONS = 0.0

# 线程安全的指标更新
_metrics_lock = threading.Lock()


def increment_counter(counter_name: str, labels: Optional[dict] = None):
    """
    增加计数器

    Args:
        counter_name: 计数器名称
        labels: 标签字典
    """
    global REQUEST_COUNT, ERROR_COUNT
    with _metrics_lock:
        if counter_name == "requests":
            REQUEST_COUNT += 1
        elif counter_name == "errors":
            ERROR_COUNT += 1


def set_gauge(gauge_name: str, value: float, labels: Optional[dict] = None):
    """
    设置仪表盘值

    Args:
        gauge_name: 仪表盘名称
        value: 值
        labels: 标签字典
    """
    global SYSTEM_CPU, SYSTEM_MEMORY, ACTIVE_CONNECTIONS
    with _metrics_lock:
        if gauge_name == "system_cpu":
            SYSTEM_CPU = value
        elif gauge_name == "system_memory":
            SYSTEM_MEMORY = value
        elif gauge_name == "active_connections":
            ACTIVE_CONNECTIONS = value


def observe_histogram(histogram_name: str, value: float, labels: Optional[dict] = None):
    """
    记录直方图观测值

    Args:
        histogram_name: 直方图名称
        value: 观测值
        labels: 标签字典
    """
    global REQUEST_LATENCY_SAMPLES
    with _metrics_lock:
        if histogram_name == "request_latency":
            REQUEST_LATENCY_SAMPLES.append(value)
            # 只保留最近1000个样本
            if len(REQUEST_LATENCY_SAMPLES) > 1000:
                REQUEST_LATENCY_SAMPLES = REQUEST_LATENCY_SAMPLES[-1000:]


def get_metrics_summary() -> dict:
    """
    获取指标摘要

    Returns:
        包含所有指标摘要的字典
    """
    with _metrics_lock:
        latency_summary = {}
        if REQUEST_LATENCY_SAMPLES:
            latency_summary = {
                "count": len(REQUEST_LATENCY_SAMPLES),
                "min": min(REQUEST_LATENCY_SAMPLES),
                "max": max(REQUEST_LATENCY_SAMPLES),
                "avg": sum(REQUEST_LATENCY_SAMPLES) / len(REQUEST_LATENCY_SAMPLES),
            }

        return {
            "counters": {
                "requests_total": REQUEST_COUNT,
                "errors_total": ERROR_COUNT,
            },
            "gauges": {
                "system_cpu_percent": SYSTEM_CPU,
                "system_memory_percent": SYSTEM_MEMORY,
                "active_connections": ACTIVE_CONNECTIONS,
            },
            "histograms": {
                "request_latency_seconds": latency_summary,
            },
        }


def start_metrics_server(port: int = 9090):
    """
    启动指标服务器

    Args:
        port: 端口号

    Returns:
        服务器对象（如适用）
    """
    logger.info(f"Metrics server would start on port {port}")
    logger.info("Note: Full Prometheus server not implemented in lightweight mode")
    logger.info("Use get_metrics_summary() to retrieve metrics programmatically")
    return None


def reset_metrics():
    """
    重置所有指标
    """
    global REQUEST_COUNT, ERROR_COUNT, REQUEST_LATENCY_SAMPLES
    global SYSTEM_CPU, SYSTEM_MEMORY, ACTIVE_CONNECTIONS
    with _metrics_lock:
        REQUEST_COUNT = 0
        ERROR_COUNT = 0
        REQUEST_LATENCY_SAMPLES = []
        SYSTEM_CPU = 0.0
        SYSTEM_MEMORY = 0.0
        ACTIVE_CONNECTIONS = 0
