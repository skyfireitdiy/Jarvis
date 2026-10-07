# -*- coding: utf-8 -*-
"""插件管理 HTTP API 集成测试（master 本地节点）。"""

import json
import os
from pathlib import Path

# 必须在导入 jarvis 模块之前设置环境变量，避免触发交互式配置
os.environ["JARVIS_SKIP_INTERACTIVE_CONFIG"] = "1"

import pytest
from fastapi.testclient import TestClient

from jarvis.jarvis_web_gateway.app import create_app

TEST_AUTH_TOKEN = "test-token-for-unit-tests"
os.environ["JARVIS_AUTH_TOKEN"] = TEST_AUTH_TOKEN


@pytest.fixture()
def isolated_data_dir(tmp_path, monkeypatch):
    """把 JARVIS_DATA_DIR 指向临时目录，隔离插件安装副作用。"""
    data_dir = tmp_path / "jarvis-data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("JARVIS_DATA_DIR", str(data_dir))
    return data_dir


@pytest.fixture()
def client(isolated_data_dir):
    app = create_app()
    return TestClient(app)


def _auth_headers(token: str = TEST_AUTH_TOKEN):
    return {"Authorization": f"Bearer {token}"}


def _make_plugin(plugin_dir: Path, name: str, version: str = "1.0.0") -> None:
    """构造一个最小插件目录（含 config.yaml + 前端资源）。"""
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "config.yaml").write_text(
        json.dumps(
            {
                "name": name,
                "version": version,
                "description": "test plugin",
                "frontend": {
                    "admin_tabs": [
                        {
                            "id": "my-tab",
                            "label": "My Tab",
                            "entry": "admin.js",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    (plugin_dir / "admin.js").write_text(
        "window.__pluginTest__ = true;", encoding="utf-8"
    )


def test_list_plugins_empty(client):
    """无外部插件时 list 只返回内置插件（builtin 均为 True）。"""
    resp = client.get("/api/plugins", headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    plugins = body["data"]["plugins"]
    assert len(plugins) >= 1
    assert all(p["builtin"] is True for p in plugins)


def test_list_plugins_with_installed(client, isolated_data_dir):
    """已安装插件时 list 返回结构化信息（含内置插件）。"""
    plugins_dir = Path(isolated_data_dir) / "plugins"
    _make_plugin(plugins_dir / "my-plugin", "my-plugin", "2.1.0")

    resp = client.get("/api/plugins", headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    plugins = {p["name"]: p for p in body["data"]["plugins"]}
    assert plugins["my-plugin"]["name"] == "my-plugin"
    assert plugins["my-plugin"]["version"] == "2.1.0"
    assert plugins["my-plugin"]["installed"] is True
    assert plugins["my-plugin"]["builtin"] is False
    assert plugins["my-plugin"]["frontend"]["admin_tabs"][0]["id"] == "my-tab"


def test_list_plugins_node_id_query(client, isolated_data_dir):
    """list 支持 node_id 查询参数（master 本地节点）。"""
    plugins_dir = Path(isolated_data_dir) / "plugins"
    _make_plugin(plugins_dir / "p1", "p1")

    resp = client.get("/api/plugins?node_id=master", headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["node_id"] == "master"
    names = {p["name"] for p in body["data"]["plugins"]}
    assert "p1" in names


def test_install_plugin(client, isolated_data_dir):
    """install 从本地目录安装插件。"""
    source = Path(isolated_data_dir) / "src-plugin"
    _make_plugin(source, "installed-plugin", "1.0.0")

    resp = client.post(
        "/api/plugins/install",
        json={"node_id": "master", "source": str(source)},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True

    installed = Path(isolated_data_dir) / "plugins" / "installed-plugin"
    assert installed.exists()
    assert (installed / "config.yaml").exists()


def test_install_plugin_missing_source(client):
    """install 缺少 source 时返回 INVALID_REQUEST。"""
    resp = client.post(
        "/api/plugins/install",
        json={"node_id": "master", "source": ""},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "INVALID_REQUEST"


def test_uninstall_plugin(client, isolated_data_dir):
    """uninstall 卸载已安装插件。"""
    plugins_dir = Path(isolated_data_dir) / "plugins"
    _make_plugin(plugins_dir / "to-remove", "to-remove")

    resp = client.post(
        "/api/plugins/to-remove/uninstall",
        json={"node_id": "master"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert not (plugins_dir / "to-remove").exists()


def test_uninstall_nonexistent_plugin(client):
    """卸载不存在的插件返回失败。"""
    resp = client.post(
        "/api/plugins/nope/uninstall",
        json={"node_id": "master"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False


def test_serve_plugin_frontend(client, isolated_data_dir):
    """serve_frontend 读取插件前端资源。"""
    plugins_dir = Path(isolated_data_dir) / "plugins"
    _make_plugin(plugins_dir / "fe-plugin", "fe-plugin")

    resp = client.get(
        "/api/plugins/master/fe-plugin/frontend/admin.js",
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["content"] == "window.__pluginTest__ = true;"
    assert body["data"]["content_type"] == "application/javascript"


def test_serve_plugin_frontend_not_found(client, isolated_data_dir):
    """serve_frontend 请求不存在的文件返回失败。"""
    plugins_dir = Path(isolated_data_dir) / "plugins"
    _make_plugin(plugins_dir / "fe-plugin", "fe-plugin")

    resp = client.get(
        "/api/plugins/master/fe-plugin/frontend/missing.js",
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False


def test_permission_denied_for_non_admin(client, isolated_data_dir):
    """非 admin 用户访问插件管理 API 被拒绝。"""
    resp = client.get("/api/plugins", headers=_auth_headers("wrong-token"))
    assert resp.status_code == 401


def _make_builtin_plugin(plugin_dir: Path, name: str) -> None:
    """构造一个内置插件目录（config.yaml 含 builtin: true + capabilities）。"""
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "config.yaml").write_text(
        json.dumps(
            {
                "name": name,
                "version": "1.0.0",
                "description": "builtin plugin",
                "builtin": True,
                "rules_load_dirs": ["{{plugin_dir}}/rules"],
                "capabilities": [
                    {"name": "事件钩子 on_task_start", "description": "任务开始触发"},
                    {"name": "@mycmd", "description": "内置命令"},
                ],
            }
        ),
        encoding="utf-8",
    )


def test_list_plugins_builtin_flag(client, isolated_data_dir):
    """list 返回 builtin 标记与 capabilities 能力清单。"""
    plugins_dir = Path(isolated_data_dir) / "plugins"
    _make_plugin(plugins_dir / "normal", "normal")
    _make_builtin_plugin(plugins_dir / "builtin-p", "builtin-p")

    resp = client.get("/api/plugins", headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    plugins = {p["name"]: p for p in body["data"]["plugins"]}

    assert plugins["normal"]["builtin"] is False
    assert plugins["builtin-p"]["builtin"] is True
    caps = plugins["builtin-p"]["capabilities"]
    assert any(c["type"] == "rules" for c in caps)
    assert any(c["type"] == "custom" and c["name"] == "@mycmd" for c in caps)


def test_uninstall_builtin_plugin_rejected(client, isolated_data_dir):
    """卸载内置插件被拒绝，目录保留。"""
    plugins_dir = Path(isolated_data_dir) / "plugins"
    _make_builtin_plugin(plugins_dir / "builtin-p", "builtin-p")

    resp = client.post(
        "/api/plugins/builtin-p/uninstall",
        json={"node_id": "master"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert (plugins_dir / "builtin-p").exists()


def test_upgrade_builtin_plugin_rejected(client, isolated_data_dir):
    """升级内置插件被拒绝。"""
    plugins_dir = Path(isolated_data_dir) / "plugins"
    _make_builtin_plugin(plugins_dir / "builtin-p", "builtin-p")

    resp = client.post(
        "/api/plugins/builtin-p/upgrade",
        json={"node_id": "master"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert (plugins_dir / "builtin-p").exists()
