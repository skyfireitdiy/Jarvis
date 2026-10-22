# -*- coding: utf-8 -*-
"""插件安装/升级/卸载后网关免重启生效的集成测试（Issue #234）。

验证：插件管理操作（install/uninstall/upgrade）完成后，重新扫描 plugins
目录并合并扩展点到全局配置（reload_plugin_configs），使 getter
（get_tool_load_dirs 等）立即返回新插件配置，无需重启网关进程。
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


@pytest.fixture()
def loaded_config(isolated_data_dir, monkeypatch):
    """模拟网关启动时已加载基础配置（不含插件扩展点）。

    真实场景中网关启动会调用 load_config()，它通过 cache_base_config 缓存
    不含插件扩展点的基础配置。测试里直接调用 cache_base_config 模拟该状态，
    使 reload_plugin_configs 有可用的基础配置基准。
    """
    from jarvis.jarvis_utils.utils import cache_base_config

    cache_base_config(
        {"project_name": "test", "data_dir": str(isolated_data_dir)},
        str(isolated_data_dir),
    )
    return isolated_data_dir


def _auth_headers(token: str = TEST_AUTH_TOKEN):
    return {"Authorization": f"Bearer {token}"}


def _make_plugin(
    plugin_dir: Path, name: str, version: str = "1.0.0", tool_dirs=None
) -> Path:
    """构造一个最小插件目录（含 config.yaml + tools 目录）。"""
    plugin_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "name": name,
        "version": version,
        "description": "test plugin",
    }
    if tool_dirs is not None:
        config["tool_load_dirs"] = tool_dirs
    (plugin_dir / "config.yaml").write_text(json.dumps(config), encoding="utf-8")
    if tool_dirs:
        for d in tool_dirs:
            (plugin_dir / d.replace("{{plugin_dir}}/", "")).mkdir(
                parents=True, exist_ok=True
            )
    return plugin_dir


def _make_git_plugin_repo(
    plugin_dir: Path, name: str, version: str = "1.0.0", tool_dirs=None
) -> Path:
    """创建一个本地 git 仓库插件源，返回仓库目录路径（用于 git 安装）。"""
    import subprocess

    _make_plugin(plugin_dir, name, version, tool_dirs)

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


def test_install_plugin_takes_effect_without_restart(
    client, isolated_data_dir, loaded_config
):
    """安装插件后 get_tool_load_dirs 立即返回新插件扩展点（免重启）。"""
    from jarvis.jarvis_utils.config import get_tool_load_dirs

    data_dir = Path(isolated_data_dir)
    source = _make_git_plugin_repo(
        data_dir / "src-hot",
        "hot-plugin",
        "1.0.0",
        tool_dirs=["{{plugin_dir}}/tools"],
    )
    # 安装前 getter 不含该插件
    assert all("hot-plugin" not in p for p in get_tool_load_dirs())

    resp = _install(client, f"file://{source}")
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # 免重启：getter 立即返回新插件扩展点
    tool_dirs = get_tool_load_dirs()
    assert any("hot-plugin" in p for p in tool_dirs), (
        f"安装后 get_tool_load_dirs 未包含新插件: {tool_dirs}"
    )


def test_uninstall_plugin_removes_effect_without_restart(
    client, isolated_data_dir, loaded_config
):
    """卸载插件后 get_tool_load_dirs 立即移除其扩展点（免重启）。"""
    from jarvis.jarvis_utils.config import get_tool_load_dirs

    data_dir = Path(isolated_data_dir)
    plugins_dir = data_dir / "plugins"
    _make_plugin(
        plugins_dir / "to-remove",
        "to-remove",
        "1.0.0",
        tool_dirs=["{{plugin_dir}}/tools"],
    )
    # 手动重载一次，模拟该插件已生效
    from jarvis.jarvis_utils.utils import reload_plugin_configs

    assert reload_plugin_configs() is True
    assert any("to-remove" in p for p in get_tool_load_dirs())

    resp = _uninstall(client, "to-remove")
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # 免重启：getter 立即移除该插件扩展点
    assert all("to-remove" not in p for p in get_tool_load_dirs())


def test_upgrade_plugin_updates_effect_without_restart(
    client, isolated_data_dir, loaded_config
):
    """升级插件后 get_tool_load_dirs 立即反映新配置（免重启）。"""
    import subprocess

    from jarvis.jarvis_utils.config import get_tool_load_dirs

    data_dir = Path(isolated_data_dir)
    source = _make_git_plugin_repo(
        data_dir / "src-up",
        "up-plugin",
        "1.0.0",
        tool_dirs=["{{plugin_dir}}/tools"],
    )
    resp = _install(client, f"file://{source}")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert any("up-plugin" in p for p in get_tool_load_dirs())

    # 更新源仓库：config.yaml 新增第二个 tools 目录并提交
    (source / "tools2").mkdir(exist_ok=True)
    import yaml

    cfg_path = source / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    cfg["tool_load_dirs"] = ["{{plugin_dir}}/tools", "{{plugin_dir}}/tools2"]
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    git_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(
        ["git", "add", "-A"],
        cwd=str(source),
        capture_output=True,
        text=True,
        env=git_env,
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "add tools2"],
        cwd=str(source),
        capture_output=True,
        text=True,
        env=git_env,
    )
    resp = _upgrade(client, "up-plugin")
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # 免重启：getter 反映升级后的配置
    tool_dirs = get_tool_load_dirs()
    assert any("up-plugin" in p and "tools2" in p for p in tool_dirs), (
        f"升级后 get_tool_load_dirs 未反映新配置: {tool_dirs}"
    )


def test_reload_no_duplicate_accumulation(client, isolated_data_dir, loaded_config):
    """多次重载不重复累积插件扩展点（基于基础配置缓存重建）。"""
    from jarvis.jarvis_utils.config import get_tool_load_dirs
    from jarvis.jarvis_utils.utils import reload_plugin_configs

    data_dir = Path(isolated_data_dir)
    plugins_dir = data_dir / "plugins"
    _make_plugin(
        plugins_dir / "dup-plugin",
        "dup-plugin",
        "1.0.0",
        tool_dirs=["{{plugin_dir}}/tools"],
    )
    assert reload_plugin_configs() is True
    first = [p for p in get_tool_load_dirs() if "dup-plugin" in p]
    assert len(first) == 1, f"首次重载应恰好 1 条: {first}"

    # 再次重载（模拟另一次插件变更），不应重复累积
    assert reload_plugin_configs() is True
    second = [p for p in get_tool_load_dirs() if "dup-plugin" in p]
    assert len(second) == 1, f"重复重载导致累积: {second}"


def test_install_plugin_lsp_takes_effect_without_restart(
    client, isolated_data_dir, loaded_config
):
    """安装声明 lsp 扩展点的插件后，全局 lsp.languages 立即生效（免重启）。"""
    from jarvis.jarvis_utils.config import get_global_config_data

    data_dir = Path(isolated_data_dir)
    source = _make_git_plugin_repo(
        data_dir / "src-lsp", "lsp-plugin", "1.0.0", tool_dirs=None
    )
    # 给插件 config.yaml 加 lsp 扩展点
    import yaml

    cfg_path = source / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    cfg["lsp"] = {
        "languages": {
            "python": {
                "command": "pyright-langserver",
                "args": ["--stdio"],
                "file_extensions": [".py"],
            }
        }
    }
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    git_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    import subprocess

    subprocess.run(
        ["git", "add", "-A"], cwd=str(source), capture_output=True, text=True, env=git_env
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "add lsp"],
        cwd=str(source),
        capture_output=True,
        text=True,
        env=git_env,
    )

    # 安装前全局 lsp.languages 不含该插件语言
    assert "python" not in (get_global_config_data().get("lsp") or {}).get(
        "languages", {}
    )

    resp = _install(client, f"file://{source}")
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # 免重启：全局 lsp.languages 立即包含插件声明的语言
    languages = (get_global_config_data().get("lsp") or {}).get("languages", {})
    assert "python" in languages
    assert languages["python"]["command"] == "pyright-langserver"


def test_uninstall_plugin_lsp_reversible_without_restart(
    client, isolated_data_dir, loaded_config
):
    """卸载声明 lsp 扩展点的插件后，其语言项自动撤销（可逆效应，免重启）。"""
    from jarvis.jarvis_utils.config import get_global_config_data
    from jarvis.jarvis_utils.utils import reload_plugin_configs

    data_dir = Path(isolated_data_dir)
    plugins_dir = data_dir / "plugins"
    plugin_dir = plugins_dir / "lsp-remove"
    _make_plugin(plugin_dir, "lsp-remove", "1.0.0", tool_dirs=None)
    import yaml

    cfg_path = plugin_dir / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    cfg["lsp"] = {
        "languages": {
            "go": {"command": "gopls", "file_extensions": [".go"]}
        }
    }
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    # 手动重载一次，模拟该插件已生效
    assert reload_plugin_configs() is True
    languages = (get_global_config_data().get("lsp") or {}).get("languages", {})
    assert "go" in languages

    resp = _uninstall(client, "lsp-remove")
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # 免重启：插件声明的语言项被撤销
    languages = (get_global_config_data().get("lsp") or {}).get("languages", {})
    assert "go" not in languages


def test_upgrade_plugin_clears_update_flag_cache(
    client, isolated_data_dir, loaded_config
):
    """升级插件后清除 plugin_updates.json 中的更新标记（Issue: 更新按钮不消失）。

    回归测试：升级前缓存标记该插件 hasUpdate=True（模拟定时任务检测到远端有新版本），
    升级后本地 HEAD 已等于远端，应把缓存中该插件的标记清除为 False，
    使前端「更新」按钮立即消失，无需等定时任务每小时刷新。
    """
    from jarvis.jarvis_agent.utils import (
        _load_plugin_updates_cache,
        _save_plugin_updates_cache,
    )

    data_dir = Path(isolated_data_dir)
    source = _make_git_plugin_repo(
        data_dir / "src-upflag",
        "upflag-plugin",
        "1.0.0",
        tool_dirs=["{{plugin_dir}}/tools"],
    )
    resp = _install(client, f"file://{source}")
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # 模拟定时任务检测到该插件有新版本：写入缓存标记 hasUpdate=True
    _save_plugin_updates_cache({"upflag-plugin": True})
    assert _load_plugin_updates_cache().get("upflag-plugin") is True

    # 升级插件（此时本地 HEAD 与远端一致，升级本身无内容变化但走完整流程）
    resp = _upgrade(client, "upflag-plugin")
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # 修复生效：升级后缓存中该插件更新标记被清除为 False
    cache = _load_plugin_updates_cache()
    assert cache.get("upflag-plugin") is False, (
        f"升级后更新标记未清除: {cache}"
    )
