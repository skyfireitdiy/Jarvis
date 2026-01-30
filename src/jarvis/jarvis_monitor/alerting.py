"""
告警通知模块

提供告警通知和阈值检查功能。
"""

import logging
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)

# 告警历史
_alert_history: List[Dict[str, Any]] = []

# 阈值配置
THRESHOLDS = {
    "cpu_usage": 80.0,
    "memory_usage": 85.0,
    "disk_usage": 90.0,
    "error_rate": 0.1,
}


def send_alert(alert: Dict[str, Any]) -> bool:
    """
    发送告警通知

    Args:
        alert: 告警信息字典

    Returns:
        是否发送成功
    """
    alert["timestamp"] = datetime.now().isoformat()
    _alert_history.append(alert)

    # 限制历史记录数量
    if len(_alert_history) > 1000:
        _alert_history.pop(0)

    # 记录告警
    logger.error(
        f"Alert: {alert.get('summary', 'Unknown')} - "
        f"Severity: {alert.get('severity', 'info')} - "
        f"Value: {alert.get('value', 'N/A')}"
    )

    return True


def check_thresholds(metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    检查指标是否超过阈值

    Args:
        metrics: 系统指标字典

    Returns:
        超过阈值的告警列表
    """
    alerts = []

    # 检查CPU使用率
    cpu_usage = metrics.get("cpu_usage", 0)
    if cpu_usage > THRESHOLDS["cpu_usage"]:
        alerts.append(
            {
                "type": "cpu_high",
                "summary": "High CPU usage detected",
                "value": cpu_usage,
                "threshold": THRESHOLDS["cpu_usage"],
                "severity": "warning" if cpu_usage < 90 else "critical",
            }
        )

    # 检查内存使用率
    memory_usage = metrics.get("memory_usage", 0)
    if memory_usage > THRESHOLDS["memory_usage"]:
        alerts.append(
            {
                "type": "memory_high",
                "summary": "High memory usage detected",
                "value": memory_usage,
                "threshold": THRESHOLDS["memory_usage"],
                "severity": "warning" if memory_usage < 95 else "critical",
            }
        )

    # 检查磁盘使用率
    disk_usage = metrics.get("disk_usage", 0)
    if disk_usage > THRESHOLDS["disk_usage"]:
        alerts.append(
            {
                "type": "disk_high",
                "summary": "High disk usage detected",
                "value": disk_usage,
                "threshold": THRESHOLDS["disk_usage"],
                "severity": "warning",
            }
        )

    # 发送告警
    for alert in alerts:
        send_alert(alert)

    return alerts


def get_alert_history(limit: int = 100) -> List[Dict[str, Any]]:
    """
    获取告警历史

    Args:
        limit: 返回的最大数量

    Returns:
        告警历史列表
    """
    return _alert_history[-limit:]


def clear_alert_history():
    """
    清空告警历史
    """
    global _alert_history
    _alert_history = []
    logger.info("Alert history cleared")


def set_threshold(threshold_name: str, value: float):
    """
    设置阈值

    Args:
        threshold_name: 阈值名称
        value: 阈值
    """
    if threshold_name in THRESHOLDS:
        THRESHOLDS[threshold_name] = value
        logger.info(f"Threshold {threshold_name} set to {value}")
    else:
        logger.warning(f"Unknown threshold: {threshold_name}")


def get_thresholds() -> Dict[str, float]:
    """
    获取所有阈值

    Returns:
        阈值字典
    """
    return THRESHOLDS.copy()
