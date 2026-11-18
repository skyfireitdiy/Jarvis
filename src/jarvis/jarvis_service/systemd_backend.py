# -*- coding: utf-8 -*-
"""Linux 平台 systemd 服务后端实现。"""

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple

from jarvis.jarvis_service.service_backends import ServiceBackend
from jarvis.jarvis_service.service_types import (
    ServiceConfig,
    ServiceStatus,
)
from jarvis.jarvis_service.systemd_helpers import (
    _get_service_name,
    _run_systemctl_action,
    _run_systemctl_enable_disable,
)
from jarvis.jarvis_utils.exception_utils import save_exception


class SystemdBackend(ServiceBackend):
    """Linux平台systemd服务后端实现。"""

    def install(self, config: ServiceConfig) -> Tuple[bool, str]:
        """安装systemd用户服务。

        Args:
            config: 服务配置

        Returns:
            (success, message): 成功标志和描述信息
        """
        try:
            service_executable = shutil.which("jarvis-service")
            if service_executable is None:
                return False, "未找到 jarvis-service 可执行文件"

            # 构建服务文件内容
            current_path = os.environ.get("PATH", "")
            # 确保 PATH 包含 uv tool 安装目录（~/.local/bin）和 jarvis-service 所在目录
            extra_paths = [
                os.path.expanduser("~/.local/bin"),
                os.path.dirname(service_executable),
            ]
            for p in extra_paths:
                if p and p not in current_path.split(":"):
                    current_path = f"{p}:{current_path}" if current_path else p
            proxy_env_vars = []
            for var_name in [
                "http_proxy",
                "HTTP_PROXY",
                "https_proxy",
                "HTTPS_PROXY",
                "no_proxy",
                "NO_PROXY",
                "ftp_proxy",
                "FTP_PROXY",
                "socks_proxy",
                "SOCKS_PROXY",
            ]:
                value = os.environ.get(var_name)
                if value:
                    proxy_env_vars.append(f"Environment={var_name}={value}")

            proxy_env_section = "\n".join(proxy_env_vars) if proxy_env_vars else ""
            service_name = _get_service_name(config.node_mode)
            mode_display = config.node_mode or "master"

            service_content = """[Unit]
Description=Jarvis Service ({mode})
After=network.target

[Service]
Type=simple
Environment=PATH={path}
{proxy_env}
WorkingDirectory={project_root}
ExecStart={service_executable} run --gateway-host {gateway_host} --gateway-port {gateway_port} --frontend-host {frontend_host} --frontend-port {frontend_port}""".format(
                mode=mode_display,
                path=current_path,
                project_root=config.project_root,
                service_executable=service_executable,
                gateway_host=config.gateway_host,
                gateway_port=config.gateway_port,
                frontend_host=config.frontend_host,
                frontend_port=config.frontend_port,
                proxy_env=proxy_env_section,
            )

            # 添加可选参数
            if config.node_mode:
                service_content += " --node-mode {}".format(config.node_mode)
            if config.node_id:
                service_content += " --node-id {}".format(config.node_id)
            if config.master_url:
                service_content += " --master-url {}".format(config.master_url)
            if config.node_secret:
                service_content += " --node-secret {}".format(config.node_secret)

            service_content += """
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
"""

            # 写入服务文件
            systemd_user_dir = Path.home() / ".config" / "systemd" / "user"
            systemd_user_dir.mkdir(parents=True, exist_ok=True)
            service_file_path = systemd_user_dir / service_name
            service_file_path.write_text(service_content, encoding="utf-8")

            # daemon-reload
            subprocess.run(
                ["systemctl", "--user", "daemon-reload"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            return True, f"systemd服务已安装：{service_file_path}"
        except Exception as e:
            return False, f"安装失败：{e}"

    def uninstall(self, mode: Optional[str]) -> Tuple[bool, str]:
        """卸载systemd服务（删除服务文件）。

        Args:
            mode: 服务模式（"master"或"child"），None表示当前模式

        Returns:
            (success, message): 成功标志和描述信息
        """
        try:
            service_name = _get_service_name(mode)
            systemd_user_dir = Path.home() / ".config" / "systemd" / "user"
            service_file_path = systemd_user_dir / service_name

            if not service_file_path.exists():
                return False, f"服务文件不存在：{service_file_path}"

            # 先停止并禁用服务
            _run_systemctl_action("stop", mode)
            _run_systemctl_enable_disable("disable", mode)

            # 删除服务文件
            service_file_path.unlink()

            # daemon-reload
            subprocess.run(
                ["systemctl", "--user", "daemon-reload"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            return True, f"systemd服务已卸载：{service_file_path}"
        except Exception as e:
            return False, f"卸载失败：{e}"

    def start(self, config: ServiceConfig) -> Tuple[bool, str]:
        """启动systemd服务。

        Args:
            config: 服务配置

        Returns:
            (success, message): 成功标志和描述信息
        """
        mode_lower = (config.node_mode or "master").lower()

        if _run_systemctl_action("start", mode_lower):
            return True, f"{mode_lower}服务已启动"
        else:
            return False, f"启动{mode_lower}服务失败"

    def stop(self, mode: Optional[str]) -> Tuple[bool, str]:
        """停止systemd服务。

        Args:
            mode: 服务模式（"master"或"child"），None表示当前模式

        Returns:
            (success, message): 成功标志和描述信息
        """
        mode_lower = (mode or "master").lower()

        if _run_systemctl_action("stop", mode_lower):
            return True, f"{mode_lower}服务已停止"
        else:
            return False, f"停止{mode_lower}服务失败"

    def restart(self, config: ServiceConfig) -> Tuple[bool, str]:
        """重启systemd服务。

        Args:
            config: 服务配置

        Returns:
            (success, message): 成功标志和描述信息
        """
        mode_lower = (config.node_mode or "master").lower()

        # 先停止
        _run_systemctl_action("stop", mode_lower)
        time.sleep(1)

        # 再启动
        if _run_systemctl_action("start", mode_lower):
            return True, f"{mode_lower}服务已重启"
        else:
            return False, f"重启{mode_lower}服务失败"

    def status(self, mode: Optional[str]) -> ServiceStatus:
        """查询systemd服务状态。

        Args:
            mode: 服务模式（"master"或"child"），None表示查询所有模式

        Returns:
            ServiceStatus: 服务状态信息
        """
        if mode is None:
            # 查询所有模式，返回第一个运行的
            for m in ["master", "child"]:
                status = self.status(m)
                if status.is_running:
                    return status
            # 都没运行，返回master的状态
            return self.status("master")

        mode_lower = mode.lower()
        service_name = _get_service_name(mode_lower)

        # 检查是否正在运行
        is_running = _run_systemctl_action("is-active", mode_lower)

        # 检查是否启用
        try:
            result = subprocess.run(
                ["systemctl", "--user", "is-enabled", service_name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            is_enabled = result.returncode == 0
        except Exception:
            is_enabled = False

        # 获取PID
        pid = None
        if is_running:
            try:
                result = subprocess.run(
                    ["systemctl", "--user", "show", service_name, "--property=MainPID"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0 and "=" in result.stdout:
                    pid_str = result.stdout.strip().split("=")[1]
                    pid = (
                        int(pid_str) if pid_str.isdigit() and int(pid_str) > 0 else None
                    )
            except Exception as e:
                save_exception(e, module="jarvis_service.cli", function="status")
                pass

        return ServiceStatus(
            is_running=is_running,
            is_enabled=is_enabled,
            pid=pid,
            mode=mode_lower,
            error_message=None,
        )

    def switch_mode(self, target_mode: str, config: ServiceConfig) -> Tuple[bool, str]:
        """切换systemd服务模式。

        Args:
            target_mode: 目标模式（"master"或"child"）
            config: 服务配置

        Returns:
            (success, message): 成功标志和描述信息
        """
        target_mode_lower = target_mode.lower()
        other_mode = "child" if target_mode_lower == "master" else "master"

        # 停止当前运行的服务
        for mode in ["master", "child"]:
            if _run_systemctl_action("is-active", mode):
                _run_systemctl_action("stop", mode)

        # 启动目标模式
        if not _run_systemctl_action("start", target_mode_lower):
            return False, f"启动{target_mode_lower}服务失败"

        # 启用目标模式，禁用另一个
        _run_systemctl_enable_disable("enable", target_mode_lower)
        _run_systemctl_enable_disable("disable", other_mode)

        return True, f"已切换到{target_mode_lower}模式"

    def is_current_mode(self, mode: str) -> bool:
        """检查当前是否运行指定模式。

        Args:
            mode: 要检查的模式

        Returns:
            bool: 当前是否运行指定模式
        """
        return _run_systemctl_action("is-active", mode.lower())
