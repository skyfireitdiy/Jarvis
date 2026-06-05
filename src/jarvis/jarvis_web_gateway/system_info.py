# -*- coding: utf-8 -*-
"""系统信息获取模块。"""

from __future__ import annotations

import logging
import os
import pathlib
import platform
from typing import Any, Dict, Optional

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

logger = logging.getLogger(__name__)


def get_system_info() -> Dict[str, Any]:
    """获取系统信息。

    Returns:
        包含系统信息的字典，包括：
        - os: 操作系统名称
        - os_version: 操作系统版本
        - platform: 平台信息
        - architecture: 系统架构
        - cpu_count: CPU 核心数
        - cpu_percent: CPU 使用率（百分比）
        - memory_total: 总内存（GB）
        - memory_available: 可用内存（GB）
        - memory_percent: 内存使用率（百分比）
        - disk_total: 磁盘总空间（GB）
        - disk_available: 磁盘可用空间（GB）
        - disk_percent: 磁盘使用率（百分比）
    """
    info: Dict[str, Any] = {}

    try:
        # 基础系统信息（不依赖 psutil）
        info["os"] = platform.system()
        info["os_version"] = platform.version()
        info["platform"] = platform.platform()
        info["architecture"] = platform.machine()

        if PSUTIL_AVAILABLE:
            # CPU 信息
            info["cpu_count"] = psutil.cpu_count(logical=True)
            # CPU 使用率（非阻塞模式，返回自上次调用以来的平均值）
            info["cpu_percent"] = psutil.cpu_percent(interval=None)

            # 内存信息
            memory = psutil.virtual_memory()
            info["memory_total"] = round(memory.total / (1024**3), 2)  # GB
            info["memory_available"] = round(memory.available / (1024**3), 2)  # GB
            info["memory_percent"] = memory.percent

            # 磁盘信息（动态获取系统盘）
            try:
                partitions = psutil.disk_partitions(all=False)
                for part in partitions:
                    if part.mountpoint == "/" or (
                        platform.system() == "Windows"
                        and part.device.startswith(("C:", "\\\\?\\\\C:"))
                    ):
                        disk = psutil.disk_usage(part.mountpoint)
                        info["disk_total"] = round(disk.total / (1024**3), 2)  # GB
                        info["disk_available"] = round(disk.free / (1024**3), 2)  # GB
                        info["disk_percent"] = disk.percent
                        break
                else:
                    logger.warning("Could not find system disk partition")
            except Exception as e:
                logger.error(f"Failed to get disk usage: {e}")
        else:
            logger.warning("psutil not available, limited system info")
            info["cpu_count"] = None
            info["cpu_percent"] = None
            info["memory_total"] = None
            info["memory_available"] = None
            info["memory_percent"] = None
            info["disk_total"] = None
            info["disk_available"] = None
            info["disk_percent"] = None
    except Exception as e:
        logger.error(f"Failed to get system info: {e}")

    return info


MAX_DESCRIPTION_SIZE = 10 * 1024  # 10KB


def get_node_description(data_dir: Optional[str] = None) -> str:
    """获取节点描述。

    从数据目录下的 gateway/node_description.md 文件读取节点描述。
    如果文件不存在，返回空字符串。
    超过大小限制时截断并记录警告日志。

    Args:
        data_dir: 数据目录路径，默认为 ~/.jarvis

    Returns:
        节点描述文本
    """
    try:
        if data_dir is None:
            data_dir = os.path.expanduser("~/.jarvis")

        description_file = pathlib.Path(data_dir) / "gateway" / "node_description.md"

        if description_file.exists():
            content = description_file.read_text(encoding="utf-8")
            if len(content) > MAX_DESCRIPTION_SIZE:
                logger.warning(
                    f"Node description file too large ({len(content)} bytes), truncating to {MAX_DESCRIPTION_SIZE} bytes"
                )
                content = content[:MAX_DESCRIPTION_SIZE]
            return content.strip()
    except Exception as e:
        logger.error(f"Failed to read node description: {e}")

    return ""
