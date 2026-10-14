# -*- coding: utf-8 -*-
"""插件生命周期钩子（hooks）集成测试。

覆盖 Issue #239：插件 config.yaml 的 hooks 私有配置字段，
在安装/升级/卸载的前后时机执行 shell 命令。
"""

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


def _make_plugin(
    plugin_dir: Path, name: str, version: str = "1.0.0", hooks: dict | None = None
) -> Path:
    """构造一个最小插件目录（含 config.yaml），可选带 hooks 字段。"""
    plugin_dir.mkdir(parents=True, exist_ok=True)
    config = {
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
    if hooks is not None:
        config["hooks"] = hooks
    (plugin_dir / "config.yaml").write_text(json.dumps(config), encoding="utf-8")
    (plugin_dir / "admin.js").write_text(
        "window.__pluginTest__ = true;", encoding="utf-8"
    )
    return plugin_dir


def _make_git_plugin_repo(
    plugin_dir: Path, name: str, version: str = "1.0.0", hooks: dict | None = None
) -> Path:
    """创建一个本地 git 仓库插件源，返回仓库目录路径（用于 git 安装）。"""
    import subprocess

    _make_plugin(plugin_dir, name, version, hooks)

    def _git(*args):
        return subprocess.run(
            ["git", *args],
            cwd=str(plugin_dir),
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "GIT_AUTHOR_NAME": "t",
                "GIT_AUTHOR_EMAIL": "t@t",
                "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@t",
            },
        )

    _git("init", "-q")
    _git("checkout", "-q", "-b", "main")
    _git("add", "-A")
    _git("commit", "-q", "-m", "init")
    return plugin_dir


def _install(client, source: str):
    return client.post(
        "/api/plugins/install",
        json={"node_id": "master", "source": source},
        headers=_auth_headers(),
    )


def _uninstall(client, name: str):
    return client.post(
        f"/api/plugins/{name}/uninstall",
        json={"node_id": "master"},
        headers=_auth_headers(),
    )


def _upgrade(client, name: str):
    return client.post(
        f"/api/plugins/{name}/upgrade",
        json={"node_id": "master"},
        headers=_auth_headers(),
    )


# ---------- install 钩子 ----------


def test_install_runs_pre_and_post_hooks(client, isolated_data_dir):
    """安装时 pre-install / post-install 钩子按序执行。"""
    data_dir = Path(isolated_data_dir)
    marker_dir = data_dir / "markers"
    marker_dir.mkdir(parents=True, exist_ok=True)
    hooks = {
        "pre-install": [f"touch {marker_dir / 'pre-install'}"],
        "post-install": [f"touch {marker_dir / 'post-install'}"],
    }
    source = _make_git_plugin_repo(
        data_dir / "src-hook", "hook-install", "1.0.0", hooks
    )
    resp = _install(client, f"file://{source}")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert (marker_dir / "pre-install").exists()
    assert (marker_dir / "post-install").exists()


def test_install_pre_hook_failure_aborts(client, isolated_data_dir):
    """pre-install 钩子失败时中止安装（不产生已安装插件）。"""
    data_dir = Path(isolated_data_dir)
    hooks = {"pre-install": ["exit 1"]}
    source = _make_git_plugin_repo(
        data_dir / "src-fail", "hook-install-fail", "1.0.0", hooks
    )
    resp = _install(client, f"file://{source}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert not (data_dir / "plugins" / "hook-install-fail").exists()


def test_install_post_hook_failure_still_succeeds(client, isolated_data_dir):
    """post-install 钩子失败仅警告，安装仍成功。"""
    data_dir = Path(isolated_data_dir)
    hooks = {"post-install": ["exit 1"]}
    source = _make_git_plugin_repo(
        data_dir / "src-post-fail", "hook-install-post-fail", "1.0.0", hooks
    )
    resp = _install(client, f"file://{source}")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert (data_dir / "plugins" / "hook-install-post-fail").exists()


# ---------- uninstall 钩子 ----------


def test_uninstall_runs_pre_and_post_hooks(client, isolated_data_dir):
    """卸载时 pre-uninstall / post-uninstall 钩子按序执行。"""
    data_dir = Path(isolated_data_dir)
    plugins_dir = data_dir / "plugins"
    marker_dir = data_dir / "markers"
    marker_dir.mkdir(parents=True, exist_ok=True)
    hooks = {
        "pre-uninstall": [f"touch {marker_dir / 'pre-uninstall'}"],
        "post-uninstall": [f"touch {marker_dir / 'post-uninstall'}"],
    }
    _make_plugin(plugins_dir / "hook-remove", "hook-remove", "1.0.0", hooks)
    resp = _uninstall(client, "hook-remove")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert not (plugins_dir / "hook-remove").exists()
    assert (marker_dir / "pre-uninstall").exists()
    assert (marker_dir / "post-uninstall").exists()


def test_uninstall_pre_hook_failure_aborts(client, isolated_data_dir):
    """pre-uninstall 钩子失败时中止卸载（插件目录保留）。"""
    data_dir = Path(isolated_data_dir)
    plugins_dir = data_dir / "plugins"
    hooks = {"pre-uninstall": ["exit 1"]}
    _make_plugin(plugins_dir / "hook-remove-fail", "hook-remove-fail", "1.0.0", hooks)
    resp = _uninstall(client, "hook-remove-fail")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert (plugins_dir / "hook-remove-fail").exists()


# ---------- upgrade 钩子 ----------


def test_upgrade_runs_pre_and_post_hooks(client, isolated_data_dir):
    """升级时 pre-update / post-update 钩子按序执行。"""
    import subprocess

    data_dir = Path(isolated_data_dir)
    marker_dir = data_dir / "markers"
    marker_dir.mkdir(parents=True, exist_ok=True)
    hooks = {
        "pre-update": [f"touch {marker_dir / 'pre-update'}"],
        "post-update": [f"touch {marker_dir / 'post-update'}"],
    }
    source = _make_git_plugin_repo(
        data_dir / "src-upgrade", "hook-upgrade", "1.0.0", hooks
    )
    resp = _install(client, f"file://{source}")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    # 更新源仓库（新提交），触发升级
    (source / "admin.js").write_text("window.__pluginTest__ = 'v2';", encoding="utf-8")
    subprocess.run(
        ["git", "add", "-A", "&&", "git", "commit", "-q", "-m", "v2"],
        cwd=str(source),
        shell=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
    )
    resp = _upgrade(client, "hook-upgrade")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert (marker_dir / "pre-update").exists()
    assert (marker_dir / "post-update").exists()


def test_upgrade_pre_hook_failure_aborts(client, isolated_data_dir):
    """pre-update 钩子失败时中止升级（插件保持原版本）。"""
    data_dir = Path(isolated_data_dir)
    hooks = {"pre-update": ["exit 1"]}
    source = _make_git_plugin_repo(
        data_dir / "src-upgrade-fail", "hook-upgrade-fail", "1.0.0", hooks
    )
    resp = _install(client, f"file://{source}")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    resp = _upgrade(client, "hook-upgrade-fail")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert (data_dir / "plugins" / "hook-upgrade-fail").exists()


# ---------- 解析细节 ----------


def test_hooks_string_normalized_to_list(client, isolated_data_dir):
    """hooks 命令为单个字符串时按列表处理。"""
    data_dir = Path(isolated_data_dir)
    marker_dir = data_dir / "markers"
    marker_dir.mkdir(parents=True, exist_ok=True)
    hooks = {"post-install": f"touch {marker_dir / 'string-hook'}"}
    source = _make_git_plugin_repo(
        data_dir / "src-string", "hook-string", "1.0.0", hooks
    )
    resp = _install(client, f"file://{source}")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert (marker_dir / "string-hook").exists()


def test_hooks_invalid_stage_ignored(client, isolated_data_dir):
    """非法时机名被忽略，不影响安装。"""
    data_dir = Path(isolated_data_dir)
    marker_dir = data_dir / "markers"
    marker_dir.mkdir(parents=True, exist_ok=True)
    hooks = {
        "pre-install": [f"touch {marker_dir / 'valid-stage'}"],
        "not-a-stage": [f"touch {marker_dir / 'invalid-stage'}"],
    }
    source = _make_git_plugin_repo(
        data_dir / "src-invalid", "hook-invalid-stage", "1.0.0", hooks
    )
    resp = _install(client, f"file://{source}")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert (marker_dir / "valid-stage").exists()
    assert not (marker_dir / "invalid-stage").exists()
