"""LSP 服务器管理器测试"""

import asyncio
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

from jarvis.jarvis_lsp.server_manager import LSPServerManager, LSPServerInstance
import pytest


@pytest.mark.asyncio
async def test_server_instance_creation():
    """测试服务器实例创建"""
    project_path = os.getcwd()
    server = LSPServerInstance(language="python", project_path=project_path)

    assert server.language == "python"
    assert server.project_path == project_path
    assert server.status == "stopped"
    assert server.process is None
    assert server.client is None


@pytest.mark.asyncio
async def test_server_manager_singleton():
    """测试服务器管理器单例模式"""
    manager1 = LSPServerManager()
    manager2 = LSPServerManager()

    assert manager1 is manager2


@pytest.mark.asyncio
async def test_server_start():
    """测试服务器启动"""
    project_path = os.getcwd()
    manager = LSPServerManager()

    server = await manager.get_server("python", project_path)

    assert server.status == "running"
    assert server.is_alive()
    assert server.process is not None
    assert server.client is not None
    assert server.process.pid > 0

    # 清理
    await manager.stop_all()


@pytest.mark.asyncio
async def test_server_reuse():
    """测试服务器复用"""
    project_path = os.getcwd()
    manager = LSPServerManager()

    # 第一次获取
    server1 = await manager.get_server("python", project_path)
    pid1 = server1.process.pid

    # 第二次获取（应该复用）
    server2 = await manager.get_server("python", project_path)
    pid2 = server2.process.pid

    assert server1 is server2
    assert pid1 == pid2

    # 清理
    await manager.stop_all()


@pytest.mark.asyncio
async def test_server_stop():
    """测试服务器停止"""
    project_path = os.getcwd()
    manager = LSPServerManager()

    # 启动服务器
    server = await manager.get_server("python", project_path)

    # 停止服务器
    await manager.stop_server("python", project_path)

    # 验证服务器已停止
    assert not server.is_alive()
    assert server.status == "stopped"


@pytest.mark.asyncio
async def test_stop_all():
    """测试停止所有服务器"""
    project_path = os.getcwd()
    manager = LSPServerManager()

    # 启动服务器
    await manager.get_server("python", project_path)

    # 停止所有
    await manager.stop_all()

    # 验证所有服务器已停止
    status = manager.get_status()
    assert len(status) == 0


@pytest.mark.asyncio
async def test_get_status():
    """测试获取状态"""
    project_path = os.getcwd()
    manager = LSPServerManager()

    # 初始状态
    status = manager.get_status()
    assert len(status) == 0

    # 启动服务器
    await manager.get_server("python", project_path)

    # 获取状态
    status = manager.get_status()
    assert len(status) == 1
    key = "python:" + project_path
    assert key in status
    assert status[key]["language"] == "python"
    assert status[key]["status"] == "running"
    assert status[key]["is_alive"] is True

    # 清理
    await manager.stop_all()


@pytest.mark.asyncio
async def test_different_projects():
    """测试不同项目使用不同服务器"""
    project_path1 = os.getcwd()
    project_path2 = "/tmp"
    manager = LSPServerManager()

    # 启动两个不同项目的服务器
    server1 = await manager.get_server("python", project_path1)
    server2 = await manager.get_server("python", project_path2)

    # 验证是不同的实例
    assert server1 is not server2
    assert server1.process.pid != server2.process.pid

    # 清理
    await manager.stop_all()


@pytest.mark.asyncio
async def test_update_activity():
    """测试活跃时间更新"""
    project_path = os.getcwd()
    manager = LSPServerManager()

    server = await manager.get_server("python", project_path)

    # 获取初始活跃时间
    initial_activity = server.last_activity

    # 等待一小段时间
    await asyncio.sleep(0.1)

    # 更新活跃时间
    await manager.get_server("python", project_path)

    # 验证活跃时间已更新
    assert server.last_activity > initial_activity

    # 清理
    await manager.stop_all()


@pytest.mark.asyncio
async def test_is_expired():
    """测试超时检查"""
    server = LSPServerInstance(language="python", project_path=".")

    # 初始状态（stopped 状态不算超时）
    assert not server.is_expired(timeout=30.0)

    # 设置为 running 状态
    server.status = "running"

    # 修改活跃时间为过去
    import time

    server.last_activity = time.time() - 100

    # 检查超时
    assert server.is_expired(timeout=30.0)
    assert not server.is_expired(timeout=200.0)


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])
