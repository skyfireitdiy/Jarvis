# -*- coding: utf-8 -*-
"""服务后端抽象基类与 Windows 计划任务后端实现。"""

import shutil
import subprocess
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Tuple

from jarvis.jarvis_service.service_types import (
    ServiceConfig,
    ServiceStatus,
)


class ServiceBackend(ABC):
    """Jarvis服务后端的抽象基类。

    定义跨平台统一的服务管理接口，由具体平台实现。
    """

    @abstractmethod
    def install(self, config: ServiceConfig) -> Tuple[bool, str]:
        """安装服务（创建自启动机制）。

        Args:
            config: 服务配置

        Returns:
            (success, message): 成功标志和描述信息
        """
        pass

    @abstractmethod
    def uninstall(self, mode: Optional[str]) -> Tuple[bool, str]:
        """卸载服务（删除自启动机制）。

        Args:
            mode: 服务模式（"master"或"child"），None表示当前模式

        Returns:
            (success, message): 成功标志和描述信息
        """
        pass

    @abstractmethod
    def start(self, config: ServiceConfig) -> Tuple[bool, str]:
        """启动服务。

        Args:
            config: 服务配置

        Returns:
            (success, message): 成功标志和描述信息
        """
        pass

    @abstractmethod
    def stop(self, mode: Optional[str]) -> Tuple[bool, str]:
        """停止服务。

        Args:
            mode: 服务模式（"master"或"child"），None表示当前模式

        Returns:
            (success, message): 成功标志和描述信息
        """
        pass

    @abstractmethod
    def restart(self, config: ServiceConfig) -> Tuple[bool, str]:
        """重启服务。

        Args:
            config: 服务配置

        Returns:
            (success, message): 成功标志和描述信息
        """
        pass

    @abstractmethod
    def status(self, mode: Optional[str]) -> ServiceStatus:
        """查询服务状态。

        Args:
            mode: 服务模式（"master"或"child"），None表示查询所有模式

        Returns:
            ServiceStatus: 服务状态信息
        """
        pass

    @abstractmethod
    def switch_mode(self, target_mode: str, config: ServiceConfig) -> Tuple[bool, str]:
        """切换服务模式。

        Args:
            target_mode: 目标模式（"master"或"child"）
            config: 服务配置

        Returns:
            (success, message): 成功标志和描述信息
        """
        pass

    @abstractmethod
    def is_current_mode(self, mode: str) -> bool:
        """检查当前运行的服务模式。

        Args:
            mode: 要检查的模式

        Returns:
            bool: 当前是否运行指定模式
        """
        pass


class WindowsTaskBackend(ServiceBackend):
    """Windows平台计划任务服务后端实现。

    使用schtasks命令管理自启动（类似systemd的enable/disable），
    使用PID文件跟踪进程状态（类似systemd的start/stop）。
    """

    def __init__(self):
        """初始化Windows后端。"""
        self._pid_dir = Path.home() / ".jarvis" / "pids"
        self._pid_dir.mkdir(parents=True, exist_ok=True)

    def _get_task_name(self, mode: Optional[str]) -> str:
        """获取计划任务名称。

        Args:
            mode: 服务模式（"master"或"child"），None表示当前模式

        Returns:
            计划任务名称（如"Jarvis-Master"或"Jarvis-Child"）
        """
        mode_lower = (mode or "master").lower()
        if mode_lower == "master":
            return "Jarvis-Master"
        elif mode_lower == "child":
            return "Jarvis-Child"
        else:
            return "Jarvis-Master"

    def _get_pid_file(self, mode: str) -> Path:
        """获取PID文件路径。

        Args:
            mode: 服务模式

        Returns:
            PID文件路径
        """
        return self._pid_dir / f"jarvis-{mode.lower()}.pid"

    def _read_pid(self, mode: str) -> Optional[int]:
        """读取PID文件。

        Args:
            mode: 服务模式

        Returns:
            进程ID，如果文件不存在或无效则返回None
        """
        pid_file = self._get_pid_file(mode)
        if not pid_file.exists():
            return None
        try:
            content = pid_file.read_text(encoding="utf-8").strip()
            pid = int(content)
            # 验证进程是否真的存在
            import subprocess

            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and str(pid) in result.stdout:
                return pid
            else:
                # 进程不存在，删除PID文件
                pid_file.unlink(missing_ok=True)
                return None
        except (ValueError, Exception):
            pid_file.unlink(missing_ok=True)
            return None

    def _write_pid(self, mode: str, pid: int) -> None:
        """写入PID文件。

        Args:
            mode: 服务模式
            pid: 进程ID
        """
        pid_file = self._get_pid_file(mode)
        pid_file.write_text(str(pid), encoding="utf-8")

    def _delete_pid(self, mode: str) -> None:
        """删除PID文件。

        Args:
            mode: 服务模式
        """
        pid_file = self._get_pid_file(mode)
        pid_file.unlink(missing_ok=True)

    def install(self, config: ServiceConfig) -> Tuple[bool, str]:
        """安装Windows计划任务（实现开机自启）。

        Args:
            config: 服务配置

        Returns:
            (success, message): 成功标志和描述信息
        """
        try:
            service_executable = shutil.which("jarvis-service.exe")
            if service_executable is None:
                # 尝试不带.exe后缀
                service_executable = shutil.which("jarvis-service")
            if service_executable is None:
                return False, "未找到 jarvis-service 可执行文件"

            task_name = self._get_task_name(config.node_mode)

            # 构建命令
            command = [
                service_executable,
                "run",
                "--gateway-host",
                config.gateway_host,
                "--gateway-port",
                str(config.gateway_port),
                "--frontend-host",
                config.frontend_host,
                "--frontend-port",
                str(config.frontend_port),
            ]
            if config.node_mode:
                command.extend(["--node-mode", config.node_mode])
            if config.node_id:
                command.extend(["--node-id", config.node_id])
            if config.master_url:
                command.extend(["--master-url", config.master_url])
            if config.node_secret:
                command.extend(["--node-secret", config.node_secret])

            # 转换为字符串命令（schtasks需要）
            command_str = " ".join(f'"{arg}"' if " " in arg else arg for arg in command)

            # 创建计划任务（登录时启动）
            schtasks_cmd = [
                "schtasks",
                "/Create",
                "/TN",
                task_name,
                "/TR",
                command_str,
                "/SC",
                "ONLOGON",
                "/RL",
                "HIGHEST",
                "/F",  # 覆盖已存在的任务
            ]

            result = subprocess.run(
                schtasks_cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                return True, f"计划任务已创建：{task_name}"
            else:
                return False, f"创建计划任务失败：{result.stderr.strip()}"
        except Exception as e:
            return False, f"安装失败：{e}"

    def uninstall(self, mode: Optional[str]) -> Tuple[bool, str]:
        """卸载Windows计划任务。

        Args:
            mode: 服务模式（"master"或"child"），None表示当前模式

        Returns:
            (success, message): 成功标志和描述信息
        """
        try:
            task_name = self._get_task_name(mode)

            # 先停止服务
            self.stop(mode)

            # 删除计划任务
            result = subprocess.run(
                ["schtasks", "/Delete", "/TN", task_name, "/F"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                # 删除PID文件
                self._delete_pid((mode or "master").lower())
                return True, f"计划任务已删除：{task_name}"
            else:
                return False, f"删除计划任务失败：{result.stderr.strip()}"
        except Exception as e:
            return False, f"卸载失败：{e}"

    def start(self, config: ServiceConfig) -> Tuple[bool, str]:
        """启动Windows服务（后台进程）。

        Args:
            config: 服务配置

        Returns:
            (success, message): 成功标志和描述信息
        """
        try:
            service_executable = shutil.which("jarvis-service.exe")
            if service_executable is None:
                service_executable = shutil.which("jarvis-service")
            if service_executable is None:
                return False, "未找到 jarvis-service 可执行文件"

            mode_lower = (config.node_mode or "master").lower()

            # 检查是否已经在运行
            if self._read_pid(mode_lower) is not None:
                return False, f"{mode_lower}服务已经在运行"

            # 构建命令
            command = [
                service_executable,
                "run",
                "--gateway-host",
                config.gateway_host,
                "--gateway-port",
                str(config.gateway_port),
                "--frontend-host",
                config.frontend_host,
                "--frontend-port",
                str(config.frontend_port),
            ]
            if config.node_mode:
                command.extend(["--node-mode", config.node_mode])
            if config.node_id:
                command.extend(["--node-id", config.node_id])
            if config.master_url:
                command.extend(["--master-url", config.master_url])
            if config.node_secret:
                command.extend(["--node-secret", config.node_secret])

            # 启动进程（分离模式）
            # Windows特定常量，使用getattr避免类型检查错误
            CREATE_NEW_PROCESS_GROUP = getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200
            )
            DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            process = subprocess.Popen(
                command,
                cwd=config.project_root,
                creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS,
            )
            # 写入PID文件
            self._write_pid(mode_lower, process.pid)
            return True, f"{mode_lower}服务已启动（PID: {process.pid}）"
        except Exception as e:
            return False, f"启动失败：{e}"

    def stop(self, mode: Optional[str]) -> Tuple[bool, str]:
        """停止Windows服务。

        Args:
            mode: 服务模式（"master"或"child"），None表示当前模式

        Returns:
            (success, message): 成功标志和描述信息
        """
        try:
            mode_lower = (mode or "master").lower()
            pid = self._read_pid(mode_lower)

            if pid is None:
                # 这里简化处理，直接认为没有PID就是没运行
                return True, f"{mode_lower}服务未运行"
            # 终止进程
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0 or "not exist" in result.stdout.lower():
                self._delete_pid(mode_lower)
                return True, f"{mode_lower}服务已停止"
            else:
                return False, f"停止服务失败：{result.stderr.strip()}"
        except Exception as e:
            return False, f"停止失败：{e}"

    def restart(self, config: ServiceConfig) -> Tuple[bool, str]:
        """重启Windows服务。

        Args:
            config: 服务配置

        Returns:
            (success, message): 成功标志和描述信息
        """
        mode_lower = (config.node_mode or "master").lower()

        # 先停止
        self.stop(mode_lower)
        time.sleep(2)

        # 再启动
        return self.start(config)

    def status(self, mode: Optional[str]) -> ServiceStatus:
        """查询Windows服务状态。

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

        # 检查PID文件
        pid = self._read_pid(mode_lower)
        is_running = pid is not None

        # 检查计划任务是否存在（相当于is_enabled）
        task_name = self._get_task_name(mode_lower)
        try:
            result = subprocess.run(
                ["schtasks", "/Query", "/TN", task_name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            is_enabled = result.returncode == 0
        except Exception:
            is_enabled = False

        return ServiceStatus(
            is_running=is_running,
            is_enabled=is_enabled,
            pid=pid,
            mode=mode_lower,
            error_message=None,
        )

    def switch_mode(self, target_mode: str, config: ServiceConfig) -> Tuple[bool, str]:
        """切换Windows服务模式。

        Args:
            target_mode: 目标模式（"master"或"child"）
            config: 服务配置

        Returns:
            (success, message): 成功标志和描述信息
        """
        target_mode_lower = target_mode.lower()

        # 停止当前运行的服务
        for mode in ["master", "child"]:
            self.stop(mode)

        # 更新配置中的模式
        config.node_mode = target_mode_lower

        # 启动目标模式
        success, message = self.start(config)
        if not success:
            return False, message

        return True, f"已切换到{target_mode_lower}模式"

    def is_current_mode(self, mode: str) -> bool:
        """检查当前是否运行指定模式。

        Args:
            mode: 要检查的模式

        Returns:
            bool: 当前是否运行指定模式
        """
        pid = self._read_pid(mode.lower())
        return pid is not None


def _detect_platform() -> str:
    """检测当前运行的平台。

    Returns:
        'windows' 或 'linux'
    """
    if sys.platform.startswith("win"):
        return "windows"
    else:
        return "linux"


def create_backend() -> ServiceBackend:
    """根据当前平台创建合适的服务后端。

    Returns:
        ServiceBackend: 对应平台的后端实例
    """
    platform = _detect_platform()
    if platform == "windows":
        return WindowsTaskBackend()
    else:
        # 延迟导入，避免 Windows 平台加载 systemd 相关实现
        from jarvis.jarvis_service.systemd_backend import SystemdBackend

        return SystemdBackend()
