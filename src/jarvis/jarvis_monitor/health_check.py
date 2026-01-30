"""
健康检查模块

提供系统和服务健康状态检查功能。
"""

import psutil
import time
from typing import Dict, Any
import importlib.util
import logging

logger = logging.getLogger(__name__)


def check_system_health() -> Dict[str, Any]:
    """
    检查系统健康状态

    Returns:
        包含CPU、内存、磁盘使用率的字典
    """
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        return {
            "cpu_usage": cpu_percent,
            "memory_usage": memory.percent,
            "disk_usage": disk.percent,
            "memory_total_gb": memory.total / (1024**3),
            "memory_available_gb": memory.available / (1024**3),
            "disk_total_gb": disk.total / (1024**3),
            "disk_free_gb": disk.free / (1024**3),
            "status": "healthy"
            if cpu_percent < 90 and memory.percent < 90
            else "warning",
            "timestamp": time.time(),
        }
    except Exception as e:
        logger.error(f"Error checking system health: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": time.time(),
        }


def check_service_health() -> Dict[str, Any]:
    """
    检查服务健康状态

    Returns:
        包含各服务状态的字典
    """
    services_status = {
        "agent_status": "unknown",
        "code_agent_status": "unknown",
        "memory_organizer_status": "unknown",
        "timestamp": time.time(),
    }

    try:
        # 检查主要服务是否可导入
        spec = importlib.util.find_spec("jarvis.jarvis_agent")
        if spec is not None:
            services_status["agent_status"] = "running"
        else:
            services_status["agent_status"] = "stopped"
    except Exception as e:
        services_status["agent_status"] = f"error: {str(e)}"

    try:
        spec = importlib.util.find_spec("jarvis.jarvis_code_agent")
        if spec is not None:
            services_status["code_agent_status"] = "running"
        else:
            services_status["code_agent_status"] = "stopped"
    except Exception as e:
        services_status["code_agent_status"] = f"error: {str(e)}"

    try:
        spec = importlib.util.find_spec("jarvis.jarvis_memory_organizer")
        if spec is not None:
            services_status["memory_organizer_status"] = "running"
        else:
            services_status["memory_organizer_status"] = "stopped"
    except Exception as e:
        services_status["memory_organizer_status"] = f"error: {str(e)}"

    # 判断整体状态
    all_running = all(
        status == "running"
        for key, status in services_status.items()
        if "status" in key
    )
    services_status["overall_status"] = "healthy" if all_running else "degraded"

    return services_status


def get_health_summary() -> Dict[str, Any]:
    """
    获取健康状态摘要

    Returns:
        包含系统和服务健康状态的摘要
    """
    system_health = check_system_health()
    service_health = check_service_health()

    return {
        "system": system_health,
        "services": service_health,
        "overall_status": (
            "healthy"
            if system_health.get("status") == "healthy"
            and service_health.get("overall_status") == "healthy"
            else "warning"
        ),
        "timestamp": time.time(),
    }
