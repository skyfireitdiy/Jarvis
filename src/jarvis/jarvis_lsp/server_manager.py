"""
LSP 服务器管理器 - 实现持久化 LSP 服务器管理。

本模块提供 LSP 服务器的持久化管理功能，包括：
- 服务器进程的启动、监控、重启、关闭
- 服务器实例的缓存和复用
- 按语言和项目区分的服务器实例
- 超时自动关闭机制

Author: Jarvis
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from jarvis.jarvis_lsp.config import LSPConfigReader
from jarvis.jarvis_lsp.client import LSPClient


@dataclass
class LSPServerInstance:
    """
    LSP 服务器实例，封装单个 LSP 服务器的进程和通信。

    Attributes:
        language: 服务器支持的语言（如 'python', 'rust'）
        project_path: 项目路径，用于区分不同项目
        process: LSP 服务器子进程
        client: LSP 客户端实例
        status: 服务器状态（starting/running/shutting_down/stopped）
        last_activity: 最后活跃时间戳
        initialize_timeout: 初始化超时时间（秒）
    """

    language: str
    project_path: str
    process: Optional[asyncio.subprocess.Process] = field(default=None)
    client: Optional[LSPClient] = field(default=None)
    status: str = field(default="stopped")
    last_activity: float = field(default_factory=time.time)
    initialize_timeout: int = field(default=30)

    async def start(self, config_reader: LSPConfigReader) -> None:
        """
        启动 LSP 服务器实例。

        Args:
            config_reader: 配置读取器，用于获取 LSP 服务器配置

        Raises:
            RuntimeError: 如果服务器启动失败或初始化超时
        """
        if self.status in ("starting", "running"):
            return

        self.status = "starting"

        try:
            # 获取 LSP 服务器配置
            config = config_reader.get_language_config(self.language)
            if config is None:
                raise RuntimeError(
                    f"No LSP server configuration found for language: {self.language}"
                )

            command = [config.command] + config.args

            # 在持久化模式下，移除 --check-parent-process 参数
            # 否则当父进程退出时，LSP 服务器也会跟着退出
            command = [arg for arg in command if arg != "--check-parent-process"]

            # 使用 asyncio 启动 LSP 服务器进程（独立于父进程）
            self.process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.project_path,  # 设置工作目录为项目路径
                start_new_session=True,  # 让进程独立，避免被父进程杀死
            )

            if (
                not self.process
                or not self.process.stdout
                or not self.process.stdin
                or not self.process.stderr
            ):
                raise RuntimeError("Failed to start LSP server process")

            # 等待一小段时间确保进程启动
            await asyncio.sleep(0.2)

            # 检查进程是否立即退出
            if self.process.returncode is not None:
                if self.process.stderr:
                    stderr_output = await self.process.stderr.read()
                    error_msg = stderr_output.decode("utf-8", errors="ignore")
                    raise RuntimeError(
                        f"LSP server '{' '.join(command)}' failed to start\n"
                        f"Exit code: {self.process.returncode}\n"
                        f"Error: {error_msg}"
                    )
                else:
                    raise RuntimeError(
                        f"LSP server '{config.command}' exited with code {self.process.returncode}"
                    )

            # 创建 LSP 客户端（复用已有进程，使用持久化模式）
            self.client = LSPClient(
                command=config.command,
                args=config.args,
                mode="persistent",
            )

            # 注入已有进程和读写器
            self.client.process = self.process
            self.client.reader = self.process.stdout
            self.client.writer = self.process.stdin

            # 初始化 LSP 服务器
            await asyncio.wait_for(
                self.client.initialize(),
                timeout=self.initialize_timeout,
            )

            self.status = "running"
            self.last_activity = time.time()

        except asyncio.TimeoutError:
            self.status = "stopped"
            await self._cleanup()
            raise RuntimeError(
                f"LSP server initialization timeout after {self.initialize_timeout}s"
            )
        except Exception as e:
            self.status = "stopped"
            await self._cleanup()
            raise RuntimeError(f"Failed to start LSP server: {e}")

    async def shutdown(self) -> None:
        """
        优雅关闭 LSP 服务器实例。

        先发送 shutdown 和 exit 通知，如果超时则强制关闭进程。
        """
        if self.status in ("stopped", "shutting_down"):
            return

        self.status = "shutting_down"

        try:
            if self.client:
                try:
                    await asyncio.wait_for(self.client.shutdown(), timeout=5.0)
                except Exception:
                    pass  # 忽略 shutdown 错误
        except Exception:
            pass
        finally:
            await self._cleanup()
            self.status = "stopped"

    async def _cleanup(self) -> None:
        """清理资源：关闭进程和客户端。"""
        if self.process:
            try:
                self.process.terminate()
                # asyncio.subprocess.Process.wait() 不支持 timeout
                # 使用 asyncio.wait_for 实现
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    self.process.kill()
                    await asyncio.wait_for(self.process.wait(), timeout=2.0)
            except Exception:
                pass
            finally:
                self.process = None

        self.client = None

    def update_activity(self) -> None:
        """更新最后活跃时间。"""
        self.last_activity = time.time()

    def is_expired(self, timeout: float) -> bool:
        """
        检查服务器实例是否已超时。

        Args:
            timeout: 超时时间（秒）

        Returns:
            如果超时返回 True，否则返回 False
        """
        if self.status != "running":
            return False
        return (time.time() - self.last_activity) > timeout

    def is_alive(self) -> bool:
        """检查服务器进程是否存活。"""
        if not self.process:
            return False
        # asyncio.subprocess.Process 没有 poll() 方法
        # 使用 returncode 判断，None 表示进程仍在运行
        return self.process.returncode is None


class LSPServerManager:
    """
    LSP 服务器管理器（单例模式）。

    负责管理多个 LSP 服务器实例，提供服务器获取、启动、停止、监控等功能。

    Attributes:
        _instance: 单例实例
        _servers: 服务器实例字典，键为 {language}:{project_path}
        _lock: 并发访问锁
        _config_reader: 配置读取器
        _default_timeout: 默认超时时间（秒）
        _monitor_task: 监控任务
        _initialized: 初始化标志
    """

    _instance: Optional[LSPServerManager] = None
    _servers: Dict[str, LSPServerInstance]
    _lock: asyncio.Lock
    _config_reader: LSPConfigReader
    _default_timeout: float
    _monitor_task: Optional[asyncio.Task[None]]
    _initialized: bool
    _state_file: Path  # 进程状态文件

    def __new__(cls) -> LSPServerManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # 初始化类属性
            cls._instance._servers = {}
            cls._instance._lock = asyncio.Lock()
            cls._instance._config_reader = LSPConfigReader()
            cls._instance._default_timeout = 1800.0  # 默认 30 分钟
            cls._instance._monitor_task = None
            cls._instance._initialized = True
            cls._instance._state_file = Path.home() / ".jarvis" / "lsp_servers.json"
        return cls._instance

    def __init__(self) -> None:
        # 单例模式，__init__ 只会被调用一次
        pass

    def _get_server_key(self, language: str, project_path: str) -> str:
        """生成服务器实例的缓存键。"""
        return f"{language}:{project_path}"

    def _save_server_state(self, key: str, pid: int) -> None:
        """保存服务器进程信息到文件。

        Args:
            key: 服务器键值
            pid: 进程 ID
        """
        try:
            # 确保目录存在
            self._state_file.parent.mkdir(parents=True, exist_ok=True)

            # 读取现有状态
            state: Dict[str, Dict[str, Any]] = {}
            if self._state_file.exists():
                with open(self._state_file, "r") as f:
                    state = json.load(f)

            # 更新状态
            state[key] = {
                "pid": pid,
                "language": key.split(":")[0],
                "project_path": key.split(":", 1)[1] if ":" in key else ".",
                "start_time": time.time(),
            }

            # 保存状态
            with open(self._state_file, "w") as f:
                json.dump(state, f, indent=2)
        except Exception:
            pass  # 忽略保存错误

    def _remove_server_state(self, key: str) -> None:
        """移除服务器进程信息。

        Args:
            key: 服务器键值
        """
        try:
            if self._state_file.exists():
                with open(self._state_file, "r") as f:
                    state = json.load(f)

                if key in state:
                    del state[key]

                    with open(self._state_file, "w") as f:
                        json.dump(state, f, indent=2)
        except Exception:
            pass  # 忽略删除错误

    async def get_server(self, language: str, project_path: str) -> LSPServerInstance:
        """
        获取或创建 LSP 服务器实例。

        如果服务器实例已存在且运行正常，直接返回；否则创建新实例。

        Args:
            language: LSP 服务器支持的语言
            project_path: 项目路径

        Returns:
            LSP 服务器实例

        Raises:
            RuntimeError: 如果服务器启动失败
        """
        async with self._lock:
            key = self._get_server_key(language, project_path)

            # 检查是否已有运行中的服务器
            if key in self._servers:
                server = self._servers[key]
                if server.is_alive() and server.status == "running":
                    server.update_activity()
                    return server
                else:
                    # 服务器已失效，清理并重新创建
                    await server.shutdown()
                    del self._servers[key]

            # 创建新服务器实例
            server = LSPServerInstance(language=language, project_path=project_path)
            await server.start(self._config_reader)
            self._servers[key] = server

            # 保存进程信息
            if server.process:
                self._save_server_state(key, server.process.pid)

            return server

    async def start_server(self, language: str, project_path: str) -> LSPServerInstance:
        """
        启动 LSP 服务器实例。

        Args:
            language: LSP 服务器支持的语言
            project_path: 项目路径

        Returns:
            LSP 服务器实例

        Raises:
            RuntimeError: 如果服务器启动失败
        """
        return await self.get_server(language, project_path)

    async def stop_server(self, language: str, project_path: str) -> None:
        """
        停止指定语言和项目的 LSP 服务器实例。

        也会停止后台守护进程。

        Args:
            language: LSP 服务器支持的语言
            project_path: 项目路径
        """
        async with self._lock:
            key = self._get_server_key(language, project_path)

            # 停止服务器
            if key in self._servers:
                server = self._servers[key]
                await server.shutdown()
                del self._servers[key]

            # 移除进程信息
            self._remove_server_state(key)

            # 查找并停止守护进程
            try:
                # 状态文件已经被移除，但我们需要找到守护进程
                # 通过查找运行中的守护进程来停止它
                import subprocess

                # 查找所有包含当前项目和语言的守护进程
                result = subprocess.run(
                    [
                        "pgrep",
                        "-f",
                        f'keep_server_alive.*"{language}".*"{project_path}"',
                    ],
                    capture_output=True,
                    text=True,
                )

                if result.returncode == 0:
                    for pid in result.stdout.strip().split("\n"):
                        if pid:
                            try:
                                os.kill(int(pid), 9)  # 强制杀死守护进程
                            except (ProcessLookupError, ValueError):
                                pass
            except Exception:
                pass  # 忽略守护进程停止错误

    async def stop_all(self) -> None:
        """停止所有 LSP 服务器实例。"""
        async with self._lock:
            tasks = [server.shutdown() for server in self._servers.values()]
            await asyncio.gather(*tasks, return_exceptions=True)
            self._servers.clear()
            # 清空进程信息
            try:
                if self._state_file.exists():
                    self._state_file.unlink()
            except Exception:
                pass

    def get_status(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有服务器实例的状态。

        Returns:
            状态字典，键为 {language}:{project_path}，值为服务器状态信息
        """
        status = {}

        # 读取内存中的服务器状态
        for key, server in self._servers.items():
            status[key] = {
                "language": server.language,
                "project_path": server.project_path,
                "status": server.status,
                "is_alive": server.is_alive(),
                "last_activity": server.last_activity,
                "idle_time": time.time() - server.last_activity,
            }

        # 读取持久化的服务器状态
        try:
            if self._state_file.exists():
                with open(self._state_file, "r") as f:
                    saved_state = json.load(f)

                # 检查持久化的进程是否还在运行
                for key, info in saved_state.items():
                    # 如果已经在内存中，跳过
                    if key in status:
                        continue

                    # 检查进程是否还在运行
                    try:
                        # 使用 os.kill(pid, 0) 检查进程是否存在
                        os.kill(info["pid"], 0)
                    except ProcessLookupError:
                        # 进程不存在，从持久化文件中移除
                        self._remove_server_state(key)
                    except PermissionError:
                        # 进程存在但没有权限访问，添加到状态中
                        status[key] = {
                            "language": info["language"],
                            "project_path": info["project_path"],
                            "status": "running",
                            "is_alive": True,
                            "last_activity": info.get("start_time", time.time()),
                            "idle_time": time.time()
                            - info.get("start_time", time.time()),
                            "pid": info["pid"],
                        }
                    else:
                        # 进程还在运行，添加到状态中
                        status[key] = {
                            "language": info["language"],
                            "project_path": info["project_path"],
                            "status": "running",
                            "is_alive": True,
                            "last_activity": info.get("start_time", time.time()),
                            "idle_time": time.time()
                            - info.get("start_time", time.time()),
                            "pid": info["pid"],
                        }
        except Exception:
            pass  # 忽略读取错误

        return status

    async def start_monitor(self, check_interval: float = 30.0) -> None:
        """
        启动服务器监控任务。

        定期检查服务器状态，清理失效的服务器实例，关闭超时的实例。

        Args:
            check_interval: 检查间隔（秒），默认 30 秒
        """
        if self._monitor_task and not self._monitor_task.done():
            return  # 监控任务已在运行

        async def _monitor() -> None:
            while True:
                try:
                    await asyncio.sleep(check_interval)
                    await self._cleanup_expired_servers()
                except asyncio.CancelledError:
                    break
                except Exception:
                    pass  # 忽略监控错误，继续运行

        self._monitor_task = asyncio.create_task(_monitor())

    async def stop_monitor(self) -> None:
        """停止服务器监控任务。"""
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

    async def _cleanup_expired_servers(self) -> None:
        """清理超时的服务器实例。"""
        async with self._lock:
            expired_keys = []
            for key, server in self._servers.items():
                if not server.is_alive():
                    expired_keys.append(key)
                elif server.is_expired(self._default_timeout):
                    await server.shutdown()
                    expired_keys.append(key)

            for key in expired_keys:
                if key in self._servers:
                    del self._servers[key]

    async def __aenter__(self) -> LSPServerManager:
        await self.start_monitor()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.stop_monitor()
        await self.stop_all()
