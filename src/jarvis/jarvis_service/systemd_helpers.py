# -*- coding: utf-8 -*-
"""systemd 服务操作辅助函数。"""

import subprocess
from typing import Optional

from jarvis.jarvis_utils.output import PrettyOutput


def _get_service_name(node_mode: Optional[str]) -> str:
    """根据节点模式返回systemd服务文件名。

    Args:
        node_mode: 节点模式（"master"或"child"），None时默认为"master"

    Returns:
        服务文件名（如"jarvis-master.service"或"jarvis-child.service"）
    """
    mode = (node_mode or "master").lower()
    if mode == "master":
        return "jarvis-master.service"
    elif mode == "child":
        return "jarvis-child.service"
    else:
        # 未知模式，回退到master
        return "jarvis-master.service"


def _run_systemctl_action(action: str, node_mode: Optional[str]) -> bool:
    """执行systemctl命令（start/stop/is-active）。

    Args:
        action: systemctl动作（"start", "stop", "is-active"）
        node_mode: 节点模式（"master"或"child"）

    Returns:
        对于is-active：True表示正在运行，False表示未运行
        对于start/stop：True表示成功，False表示失败
    """
    service_name = _get_service_name(node_mode)
    try:
        result = subprocess.run(
            ["systemctl", "--user", action, service_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if action == "is-active":
            return result.returncode == 0 and result.stdout.strip() == "active"
        else:
            if result.returncode == 0:
                return True
            else:
                PrettyOutput.auto_print(
                    f"⚠ {action} {service_name}失败: {result.stderr.strip()}"
                )
                return False
    except Exception as e:
        PrettyOutput.auto_print(f"⚠ 执行systemctl {action} {service_name}异常: {e}")
        return False


def _run_systemctl_enable_disable(action: str, node_mode: Optional[str]) -> bool:
    """执行systemctl enable/disable命令。

    Args:
        action: systemctl动作（"enable"或"disable"）
        node_mode: 节点模式（"master"或"child"）

    Returns:
        True表示成功，False表示失败
    """
    service_name = _get_service_name(node_mode)
    try:
        result = subprocess.run(
            ["systemctl", "--user", action, service_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return True
        else:
            PrettyOutput.auto_print(
                f"⚠ {action} {service_name}失败: {result.stderr.strip()}"
            )
            return False
    except Exception as e:
        PrettyOutput.auto_print(f"⚠ 执行systemctl {action} {service_name}异常: {e}")
        return False
