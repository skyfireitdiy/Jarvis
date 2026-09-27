# -*- coding: utf-8 -*-
"""网关侧 daemon 自更新（T5）回归测试。

守护目标（对应 daemon/docs/daemon-self-update-protocol.md 第 3、4 节）：
1. ``hello_ack`` 在配置了「最新版本」且版本不一致时，携带 ``daemon_update`` 字段；
   未配置最新版本时 **不带** 该键（旧行为完全不变）。
2. 平台/架构解析优先级：``build_info.os/arch`` → ``system_info`` → ``platform``。
3. 版本比对：相同 → available=False；不同 → available=True 且拼出下载链接。
4. 产物命名规则：linux → ``.tar.gz``；windows → ``.zip``；无对应产物 → available=False。
5. ``daemon.update.status`` 单向回执：网关只更新会话字段、**不回复**。

隔离：数据目录由 ``conftest.py`` 的 autouse fixture 重定向到 tmp_path；
全程使用 TestClient（ASGI 内存传输），不监听端口、不访问外网。
配置常量通过 monkeypatch 直接打到模块属性上，保证测试可重复。
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from jarvis.jarvis_web_gateway.app import create_app
from jarvis.jarvis_web_gateway import daemon_capability_manager as dcm
from jarvis.jarvis_web_gateway.daemon_capability_manager import (
    DAEMON_SUBPROTOCOL,
    DaemonCapabilityManager,
)


def _token_subprotocol(token: str) -> list:
    """构造携带 jarvis-token 的 WS 子协议列表。"""
    from urllib.parse import quote

    return [DAEMON_SUBPROTOCOL, "jarvis-token." + quote(token, safe="")]


@pytest.fixture
def client(auth_token):
    """构造隔离后的应用客户端；auth_token 决定 JARVIS_AUTH_TOKEN。"""
    app = create_app()
    with TestClient(app) as c:
        yield c


# ----------------------------------------------------------------------
# 纯函数：平台/架构解析
# ----------------------------------------------------------------------
def test_resolve_platform_prefers_build_info():
    """build_info.os/arch 优先于 system_info / platform。"""
    source = {
        "build_info": {"os": "Linux", "arch": "AMD64"},
        "system_info": {"os_name": "Ubuntu", "arch": "arm64"},
        "platform": "whatever",
    }
    assert dcm._resolve_daemon_platform(source) == ("linux", "amd64")


def test_resolve_platform_falls_back_to_system_info():
    """build_info 缺失时回退 system_info。"""
    source = {"system_info": {"os_name": "Windows", "machine": "x86_64"}}
    # x86_64 归一化为 amd64
    assert dcm._resolve_daemon_platform(source) == ("windows", "amd64")


def test_resolve_platform_falls_back_to_platform_field():
    """连 system_info 都没有时回退顶层 platform 字段。"""
    source = {"platform": "linux"}
    os_name, arch = dcm._resolve_daemon_platform(source)
    assert os_name == "linux"
    assert arch == ""


def test_resolve_platform_missing_returns_empty():
    """完全缺失时返回空串（调用方据此跳过更新判断）。"""
    assert dcm._resolve_daemon_platform({}) == ("", "")
    assert dcm._resolve_daemon_platform(None) == ("", "")


def test_resolve_platform_normalizes_arch_aliases():
    """aarch64 / x64 等别名归一化到 amd64 / arm64。"""
    assert (
        dcm._resolve_daemon_platform({"build_info": {"arch": "aarch64"}})[1] == "arm64"
    )
    assert dcm._resolve_daemon_platform({"build_info": {"arch": "x64"}})[1] == "amd64"


# ----------------------------------------------------------------------
# 纯函数：更新信息构造
# ----------------------------------------------------------------------
def test_build_update_no_latest_returns_none(monkeypatch):
    """未配置最新版本 → None（hello_ack 不携带该键）。"""
    monkeypatch.setattr(dcm, "DAEMON_LATEST_VERSION", "")
    assert dcm._build_daemon_update("v1.0.0", "linux", "amd64") is None


def test_build_update_same_version_not_available(monkeypatch):
    """版本相同 → available=False 并说明已是最新。"""
    monkeypatch.setattr(dcm, "DAEMON_LATEST_VERSION", "v1.2.0")
    info = dcm._build_daemon_update("v1.2.0", "linux", "amd64")
    assert info is not None
    assert info["available"] is False
    assert info["latest_version"] == "v1.2.0"
    assert info["current_version"] == "v1.2.0"
    assert info["note"]  # note 非空


def test_build_update_linux_url(monkeypatch):
    """linux → .tar.gz，URL 形如 base/tag/asset。"""
    monkeypatch.setattr(dcm, "DAEMON_LATEST_VERSION", "v1.2.0")
    monkeypatch.setattr(
        dcm, "DAEMON_RELEASE_BASE_URL", "https://github.com/o/r/releases/download"
    )
    monkeypatch.setattr(dcm, "DAEMON_ASSETS", {})
    info = dcm._build_daemon_update("v1.1.0", "linux", "amd64")
    assert info is not None
    assert info["available"] is True
    assert info["asset"] == "jarvis-daemon_linux_amd64.tar.gz"
    assert (
        info["url"]
        == "https://github.com/o/r/releases/download/v1.2.0/jarvis-daemon_linux_amd64.tar.gz"
    )
    assert info["current_version"] == "v1.1.0"
    assert info["latest_version"] == "v1.2.0"


def test_build_update_windows_url(monkeypatch):
    """windows → .zip。"""
    monkeypatch.setattr(dcm, "DAEMON_LATEST_VERSION", "v2.0.0")
    monkeypatch.setattr(
        dcm, "DAEMON_RELEASE_BASE_URL", "https://github.com/o/r/releases/download"
    )
    monkeypatch.setattr(dcm, "DAEMON_ASSETS", {})
    info = dcm._build_daemon_update("v1.9.0", "windows", "arm64")
    assert info is not None
    assert info["available"] is True
    assert info["asset"] == "jarvis-daemon_windows_arm64.zip"
    assert info["url"].endswith("/v2.0.0/jarvis-daemon_windows_arm64.zip")


def test_build_update_unsupported_platform(monkeypatch):
    """macOS（无产物）→ available=False 且 note 非空。"""
    monkeypatch.setattr(dcm, "DAEMON_LATEST_VERSION", "v1.2.0")
    monkeypatch.setattr(dcm, "DAEMON_ASSETS", {})
    info = dcm._build_daemon_update("v1.1.0", "darwin", "arm64")
    assert info is not None
    assert info["available"] is False
    assert info["note"]


def test_build_update_unknown_arch(monkeypatch):
    """架构为空（平台无法判定）→ None，即不下发更新信息。"""
    monkeypatch.setattr(dcm, "DAEMON_LATEST_VERSION", "v1.2.0")
    monkeypatch.setattr(dcm, "DAEMON_ASSETS", {})
    assert dcm._build_daemon_update("v1.1.0", "linux", "") is None


def test_build_update_unsupported_arch_known_os(monkeypatch):
    """os 已知但 arch 不受支持（如 386）→ available=False 且 note 非空。"""
    monkeypatch.setattr(dcm, "DAEMON_LATEST_VERSION", "v1.2.0")
    monkeypatch.setattr(dcm, "DAEMON_ASSETS", {})
    info = dcm._build_daemon_update("v1.1.0", "linux", "386")
    assert info is not None
    assert info["available"] is False
    assert info["note"]


def test_build_update_explicit_assets_override(monkeypatch):
    """显式 assets 映射优先，并带上 sha256/size。"""
    monkeypatch.setattr(dcm, "DAEMON_LATEST_VERSION", "v1.2.0")
    monkeypatch.setattr(
        dcm, "DAEMON_RELEASE_BASE_URL", "https://github.com/o/r/releases/download"
    )
    monkeypatch.setattr(
        dcm,
        "DAEMON_ASSETS",
        {
            "linux/amd64": {
                "asset": "custom-linux-amd64.tar.gz",
                "sha256": "a" * 64,
                "size": 12345,
            }
        },
    )
    info = dcm._build_daemon_update("v1.1.0", "linux", "amd64")
    assert info is not None
    assert info["available"] is True
    assert info["asset"] == "custom-linux-amd64.tar.gz"
    assert info["sha256"] == "a" * 64
    assert info["size"] == 12345
    assert info["url"].endswith("/v1.2.0/custom-linux-amd64.tar.gz")


def test_build_update_all_fields_present(monkeypatch):
    """返回 dict 字段固定（与设计文档逐字一致）。"""
    monkeypatch.setattr(dcm, "DAEMON_LATEST_VERSION", "v1.2.0")
    monkeypatch.setattr(dcm, "DAEMON_ASSETS", {})
    info = dcm._build_daemon_update("v1.1.0", "linux", "amd64")
    assert info is not None
    assert set(info.keys()) == {
        "available",
        "latest_version",
        "current_version",
        "url",
        "sha256",
        "size",
        "asset",
        "note",
    }


# ----------------------------------------------------------------------
# 端到端：hello_ack 携带 / 不携带 daemon_update
# ----------------------------------------------------------------------
def _hello_payload(**extra):
    payload = {
        "type": "hello",
        "client_id": "daemon-update-test",
        "extension_version": "v1.1.0",
        "build_info": {"os": "linux", "arch": "amd64"},
        "tabs": [],
    }
    payload.update(extra)
    return payload


def test_hello_ack_carries_daemon_update(client, auth_token, monkeypatch):
    """配置了最新版本且版本不同 → hello_ack 携带 daemon_update。"""
    monkeypatch.setattr(dcm, "DAEMON_LATEST_VERSION", "v1.2.0")
    monkeypatch.setattr(
        dcm, "DAEMON_RELEASE_BASE_URL", "https://github.com/o/r/releases/download"
    )
    monkeypatch.setattr(dcm, "DAEMON_ASSETS", {})
    with client.websocket_connect(
        "/api/daemon/ws", subprotocols=_token_subprotocol(auth_token)
    ) as ws:
        ws.send_json(_hello_payload())
        ack = ws.receive_json()
        assert ack["type"] == "hello_ack"
        # 既有字段未受影响
        assert ack["heartbeat_interval"] == 20
        assert ack["session_id"]
        # 新增字段
        upd = ack["daemon_update"]
        assert upd["available"] is True
        assert upd["latest_version"] == "v1.2.0"
        assert upd["current_version"] == "v1.1.0"
        assert upd["asset"] == "jarvis-daemon_linux_amd64.tar.gz"
        assert upd["url"].endswith("/v1.2.0/jarvis-daemon_linux_amd64.tar.gz")


def test_hello_ack_omits_daemon_update_when_unconfigured(
    client, auth_token, monkeypatch
):
    """未配置最新版本 → hello_ack 不含 daemon_update 键（旧行为不变）。"""
    monkeypatch.setattr(dcm, "DAEMON_LATEST_VERSION", "")
    with client.websocket_connect(
        "/api/daemon/ws", subprotocols=_token_subprotocol(auth_token)
    ) as ws:
        ws.send_json(_hello_payload())
        ack = ws.receive_json()
        assert ack["type"] == "hello_ack"
        assert "daemon_update" not in ack


def test_hello_ack_omits_daemon_update_when_platform_unknown(
    client, auth_token, monkeypatch
):
    """平台/架构无法判定（旧版 daemon 无 build_info）→ 不携带 daemon_update。"""
    monkeypatch.setattr(dcm, "DAEMON_LATEST_VERSION", "v1.2.0")
    with client.websocket_connect(
        "/api/daemon/ws", subprotocols=_token_subprotocol(auth_token)
    ) as ws:
        ws.send_json(
            {
                "type": "hello",
                "client_id": "daemon-legacy",
                "extension_version": "v1.0.0",
                "tabs": [],
            }
        )
        ack = ws.receive_json()
        assert ack["type"] == "hello_ack"
        assert "daemon_update" not in ack


# ----------------------------------------------------------------------
# daemon.update.status 单向回执
# ----------------------------------------------------------------------
def test_update_status_updates_session_and_no_reply(client, auth_token, monkeypatch):
    """daemon.update.status 只更新会话字段且不回复。"""
    monkeypatch.setattr(dcm, "DAEMON_LATEST_VERSION", "")
    with client.websocket_connect(
        "/api/daemon/ws", subprotocols=_token_subprotocol(auth_token)
    ) as ws:
        ws.send_json(_hello_payload())
        ack = ws.receive_json()
        session_id = ack["session_id"]
        # 回执：不应收到任何回复
        ws.send_json(
            {
                "type": "daemon.update.status",
                "state": "downloading",
                "version": "v1.2.0",
                "error": "",
            }
        )
        # 用一次 ping/pong 作为同步屏障：若网关错误地回复了 status，
        # 这里收到的就会是别的消息（断言 type == pong）。
        ws.send_json({"type": "ping"})
        pong = ws.receive_json()
        assert pong["type"] == "pong"

        manager = client.app.state.daemon_capability_manager
        session = manager.get_session(session_id)
        assert session is not None
        assert session["update_state"] is not None
        assert session["update_state"]["state"] == "downloading"
        assert session["update_state"]["version"] == "v1.2.0"
        assert session["update_state"]["error"] == ""
        assert session["update_state"]["updated_at"] > 0


def test_update_status_failed_records_error(client, auth_token, monkeypatch):
    """state=failed 时 error 被记录；未知 state 也不报错。"""
    monkeypatch.setattr(dcm, "DAEMON_LATEST_VERSION", "")
    with client.websocket_connect(
        "/api/daemon/ws", subprotocols=_token_subprotocol(auth_token)
    ) as ws:
        ws.send_json(_hello_payload())
        ack = ws.receive_json()
        session_id = ack["session_id"]
        ws.send_json(
            {
                "type": "daemon.update.status",
                "state": "failed",
                "version": "v1.2.0",
                "error": "sha256 mismatch",
            }
        )
        ws.send_json({"type": "daemon.update.status", "state": "weird-state"})
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "pong"

        manager = client.app.state.daemon_capability_manager
        session = manager.get_session(session_id)
        # 最后一次回执（未知 state）被记录，且未抛异常
        assert session["update_state"]["state"] == "weird-state"
        # 会话仍在（未被异常断开）
        assert manager.get_session(session_id) is not None


def test_update_state_default_none(client, auth_token, monkeypatch):
    """新会话 update_state 默认为 None（未收到回执）。"""
    monkeypatch.setattr(dcm, "DAEMON_LATEST_VERSION", "")
    with client.websocket_connect(
        "/api/daemon/ws", subprotocols=_token_subprotocol(auth_token)
    ) as ws:
        ws.send_json(_hello_payload())
        ack = ws.receive_json()
        manager = client.app.state.daemon_capability_manager
        session = manager.get_session(ack["session_id"])
        assert session["update_state"] is None
        # list_sessions 也带该字段
        listed = manager.list_sessions()
        assert listed[0]["update_state"] is None


# ----------------------------------------------------------------------
# 配置解析：JARVIS_DAEMON_ASSETS
# ----------------------------------------------------------------------
def test_load_daemon_assets_parses_json(monkeypatch):
    monkeypatch.setenv(
        "JARVIS_DAEMON_ASSETS",
        '{"linux/amd64": {"asset": "a.tar.gz", "sha256": "b"}}',
    )
    assert dcm._load_daemon_assets() == {
        "linux/amd64": {"asset": "a.tar.gz", "sha256": "b"}
    }


def test_load_daemon_assets_bad_json_returns_empty(monkeypatch):
    """非法 JSON 仅告警，返回空字典（不抛异常）。"""
    monkeypatch.setenv("JARVIS_DAEMON_ASSETS", "{not json")
    assert dcm._load_daemon_assets() == {}


def test_load_daemon_assets_empty(monkeypatch):
    monkeypatch.delenv("JARVIS_DAEMON_ASSETS", raising=False)
    assert dcm._load_daemon_assets() == {}


def test_manager_isolation_no_global_state():
    """Registry/Manager 无全局状态：两个实例互不干扰（对齐 daemon 侧设计）。"""
    m1 = DaemonCapabilityManager()
    m2 = DaemonCapabilityManager()
    assert m1 is not m2
    assert m1._sessions == {}
    assert m2._sessions == {}
