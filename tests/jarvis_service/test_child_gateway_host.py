"""子节点网关监听地址限制的测试。

子节点本地无 auth 数据、不独立做权限判定，网关必须只监听回环地址，
否则会把节点暴露为无认证入口。
"""

import pytest

from jarvis.jarvis_service.cli import build_service_config


@pytest.mark.parametrize(
    "requested_host",
    ["0.0.0.0", "192.168.1.5", "10.0.0.1", "example.com"],
)
def test_child_gateway_host_forced_to_loopback(requested_host: str) -> None:
    """子节点请求非回环地址时，应强制回退到 127.0.0.1。"""
    config = build_service_config(
        node_mode="child", node_id="n1", gateway_host=requested_host
    )
    assert config.gateway_host == "127.0.0.1"


@pytest.mark.parametrize("loopback_host", ["127.0.0.1", "localhost", "::1"])
def test_child_gateway_host_keeps_loopback(loopback_host: str) -> None:
    """子节点请求回环地址时，应保持原值。"""
    config = build_service_config(
        node_mode="child", node_id="n1", gateway_host=loopback_host
    )
    assert config.gateway_host == loopback_host


def test_master_gateway_host_not_restricted() -> None:
    """master 节点不受限制，仍需支持对外监听。"""
    config = build_service_config(node_mode="master", gateway_host="0.0.0.0")
    assert config.gateway_host == "0.0.0.0"
