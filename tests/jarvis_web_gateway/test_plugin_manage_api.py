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


def _make_plugin(plugin_dir: Path, name: str, version: str = "1.0.0") -> Path:
    """构造一个最小插件目录（含 config.yaml + 前端资源），返回目录路径。"""
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
    return plugin_dir


def _make_git_plugin_repo(plugin_dir: Path, name: str, version: str = "1.0.0") -> Path:
    """创建一个本地 git 仓库插件源，返回仓库目录路径（用于 git 安装）。"""
    import subprocess

    _make_plugin(plugin_dir, name, version)

    def _git(*args):
        return subprocess.run(
            ["git", *args],
            cwd=str(plugin_dir),
            capture_output=True,
            text=True,
            env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                 "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
        )

    _git("init", "-q")
    _git("checkout", "-q", "-b", "main")
    _git("add", "-A")
    _git("commit", "-q", "-m", "init")
    return plugin_dir


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
    """install 从 git 仓库安装插件。"""
    source = _make_git_plugin_repo(
        Path(isolated_data_dir) / "src-plugin", "installed-plugin", "1.0.0"
    )
    source_url = f"file://{source}"

    resp = client.post(
        "/api/plugins/install",
        json={"node_id": "master", "source": source_url},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True

    installed = Path(isolated_data_dir) / "plugins" / "installed-plugin"
    assert installed.exists()
    assert (installed / "config.yaml").exists()
    assert (installed / ".git").exists()


def test_install_plugin_from_local_directory(client, isolated_data_dir):
    """install 从本地目录安装插件（软链接，Issue #213）。"""
    source = _make_plugin(
        Path(isolated_data_dir) / "local-src", "local-installed", "1.0.0"
    )

    resp = client.post(
        "/api/plugins/install",
        json={"node_id": "master", "source": str(source)},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True

    installed = Path(isolated_data_dir) / "plugins" / "local-installed"
    assert installed.exists()
    assert installed.is_symlink()
    assert (installed / "config.yaml").exists()


def test_install_plugin_from_zip(client, isolated_data_dir):
    """install 从压缩文件安装插件（解压复制，Issue #213）。"""
    import zipfile

    source = _make_plugin(
        Path(isolated_data_dir) / "zip-src", "zip-installed", "1.0.0"
    )
    zip_file = Path(isolated_data_dir) / "plugin.zip"
    with zipfile.ZipFile(zip_file, "w") as zf:
        zf.write(source / "config.yaml", "config.yaml")
        zf.write(source / "admin.js", "admin.js")

    resp = client.post(
        "/api/plugins/install",
        json={"node_id": "master", "source": str(zip_file)},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True

    installed = Path(isolated_data_dir) / "plugins" / "zip-installed"
    assert installed.exists()
    assert not installed.is_symlink()
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


def _make_plugin_with_api(plugin_dir: Path, name: str) -> None:
    """构造一个含 plugin/api.py 私有功能层的插件。"""
    _make_plugin(plugin_dir, name)
    api_dir = plugin_dir / "plugin"
    api_dir.mkdir(parents=True, exist_ok=True)
    (api_dir / "api.py").write_text(
        """def hello(name="world"):
    return {"success": True, "message": f"hello {name}"}

def secret():
    return {"success": True, "message": "secret"}

PUBLIC_FUNCTIONS = ["hello"]
""",
        encoding="utf-8",
    )


def test_list_plugin_functions(client, isolated_data_dir):
    """列出插件私有功能（PUBLIC_FUNCTIONS 白名单）。"""
    plugins_dir = Path(isolated_data_dir) / "plugins"
    _make_plugin_with_api(plugins_dir / "fn-plugin", "fn-plugin")

    resp = client.get("/api/plugins/master/functions", headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    plugins = body["data"]["plugins"]
    fn_plugin = next((p for p in plugins if p["plugin"] == "fn-plugin"), None)
    assert fn_plugin is not None
    assert "hello" in fn_plugin["functions"]
    assert "secret" not in fn_plugin["functions"]


def test_call_plugin_function(client, isolated_data_dir):
    """调用插件私有功能（白名单内）。"""
    plugins_dir = Path(isolated_data_dir) / "plugins"
    _make_plugin_with_api(plugins_dir / "fn-plugin", "fn-plugin")

    resp = client.post(
        "/api/plugins/master/function-call",
        json={
            "plugin": "fn-plugin",
            "function": "hello",
            "arguments": {"name": "jarvis"},
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["result"]["success"] is True
    assert body["result"]["message"] == "hello jarvis"


def test_call_plugin_function_not_in_whitelist(client, isolated_data_dir):
    """调用不在白名单内的函数被拒绝。"""
    plugins_dir = Path(isolated_data_dir) / "plugins"
    _make_plugin_with_api(plugins_dir / "fn-plugin", "fn-plugin")

    resp = client.post(
        "/api/plugins/master/function-call",
        json={
            "plugin": "fn-plugin",
            "function": "secret",
            "arguments": {},
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "FUNCTION_NOT_ALLOWED"


def test_call_plugin_function_plugin_not_found(client, isolated_data_dir):
    """调用不存在插件的功能返回失败。"""
    resp = client.post(
        "/api/plugins/master/function-call",
        json={
            "plugin": "no-such-plugin",
            "function": "hello",
            "arguments": {},
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "FUNCTION_API_NOT_FOUND"


def test_list_market_plugins_api(client, monkeypatch):
    """市场浏览 API 返回解析后的市场插件列表。"""
    import jarvis.jarvis_agent.utils as agent_utils

    fake_plugins = [
        {
            "id": "market-p",
            "name": "市场插件",
            "description": "来自市场的插件",
            "repo": "https://github.com/owner/market-p",
            "branch": "main",
            "author": "作者甲",
            "license": "MIT",
            "logo": "",
            "categories": ["工具"],
            "market_repo": "https://github.com/skyfireitdiy/plugin-market",
        }
    ]
    monkeypatch.setattr(agent_utils, "list_market_plugins", lambda: fake_plugins)

    resp = client.get("/api/plugins/market", headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    plugins = body["data"]["plugins"]
    assert len(plugins) == 1
    assert plugins[0]["id"] == "market-p"
    assert plugins[0]["name"] == "市场插件"
    assert plugins[0]["repo"] == "https://github.com/owner/market-p"
    assert plugins[0]["branch"] == "main"


def test_list_market_plugins_api_pagination_and_filters(client, monkeypatch):
    """市场浏览 API 支持分页与搜索过滤参数（Issue #247）。"""
    import jarvis.jarvis_agent.utils as agent_utils

    fake_plugins = [
        {
            "id": f"p{i}",
            "name": f"插件{i}",
            "description": f"第{i}个插件",
            "repo": f"https://github.com/owner/p{i}",
            "branch": "main",
            "author": "作者甲" if i % 2 == 0 else "作者乙",
            "license": "MIT",
            "logo": "",
            "categories": ["工具"] if i % 2 == 0 else ["集成"],
            "market_repo": "https://github.com/skyfireitdiy/plugin-market",
        }
        for i in range(5)
    ]
    monkeypatch.setattr(agent_utils, "list_market_plugins", lambda: fake_plugins)

    # 默认返回全部（无分页参数时 page_size=20 一页装下）
    resp = client.get("/api/plugins/market", headers=_auth_headers())
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["total"] == 5
    assert len(data["plugins"]) == 5
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert data["total_pages"] == 1
    assert data["filters"]["categories"] == ["工具", "集成"]

    # 分页：page_size=2 取第一页
    resp = client.get(
        "/api/plugins/market?page=1&page_size=2", headers=_auth_headers()
    )
    data = resp.json()["data"]
    assert data["total"] == 5
    assert data["total_pages"] == 3
    assert [p["id"] for p in data["plugins"]] == ["p0", "p1"]

    # 分页第二页
    resp = client.get(
        "/api/plugins/market?page=2&page_size=2", headers=_auth_headers()
    )
    data = resp.json()["data"]
    assert [p["id"] for p in data["plugins"]] == ["p2", "p3"]

    # 搜索关键字（匹配 name/description/author）
    resp = client.get(
        "/api/plugins/market?keyword=作者乙", headers=_auth_headers()
    )
    data = resp.json()["data"]
    assert data["total"] == 2
    assert {p["id"] for p in data["plugins"]} == {"p1", "p3"}

    # 按分类过滤
    resp = client.get(
        "/api/plugins/market?category=工具", headers=_auth_headers()
    )
    data = resp.json()["data"]
    assert data["total"] == 3
    assert {p["id"] for p in data["plugins"]} == {"p0", "p2", "p4"}

    # 按来源市场仓库过滤（不匹配返回空）
    resp = client.get(
        "/api/plugins/market?market_repo=https://github.com/other/market",
        headers=_auth_headers(),
    )
    data = resp.json()["data"]
    assert data["total"] == 0
    assert data["plugins"] == []

    # 按已安装过滤：installed_names + installed=true（installed_names 传插件 id）
    resp = client.get(
        "/api/plugins/market?installed=true&installed_names=p0,p2",
        headers=_auth_headers(),
    )
    data = resp.json()["data"]
    assert data["total"] == 2
    assert {p["id"] for p in data["plugins"]} == {"p0", "p2"}

    # 非法分页参数回退默认
    resp = client.get(
        "/api/plugins/market?page=abc&page_size=xyz", headers=_auth_headers()
    )
    data = resp.json()["data"]
    assert data["page"] == 1
    assert data["page_size"] == 20
