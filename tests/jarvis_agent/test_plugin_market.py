# -*- coding: utf-8 -*-
"""list_market_plugins 插件市场清单解析测试。

验证从市场仓库解析插件清单的逻辑：
- 正确解析 plugins/*.yaml 为结构化插件列表
- 跳过 `_` 开头的模板/占位文件（如 _example.yaml）
- 仓库不可达时跳过该源，不阻断整体返回
- 单个 yaml 解析失败时跳过该条目，不阻断其他条目
"""

import shutil

import pytest
import yaml

from jarvis.jarvis_agent import utils as agent_utils
import jarvis.jarvis_utils.config as config


def _patch_market(monkeypatch, market_dir, data_dir):
    """把 list_market_plugins 的依赖替换为临时目录 + 假 git。"""
    monkeypatch.setattr(
        config,
        "get_plugin_market_repos",
        lambda: ["https://github.com/skyfireitdiy/plugin-market"],
    )
    monkeypatch.setattr(config, "get_data_dir", lambda: str(data_dir))

    def fake_clone(url, branch, dest):
        shutil.copytree(str(market_dir), str(dest))

    monkeypatch.setattr(agent_utils, "_git_clone_plugin", fake_clone)

    class FakeProc:
        returncode = 0

    monkeypatch.setattr(agent_utils, "_git_run", lambda *a, **k: FakeProc())


@pytest.fixture
def market_repo(tmp_path):
    """构造一个临时市场仓库（含 plugins/ 结构）。"""
    repo = tmp_path / "repo"
    plugins_dir = repo / "plugins"
    plugins_dir.mkdir(parents=True)
    (plugins_dir / "foo.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "foo",
                "name": "Foo 插件",
                "description": "测试插件",
                "repo": "https://github.com/owner/foo",
                "branch": "main",
                "author": "作者甲",
                "license": "MIT",
                "categories": ["工具", "效率"],
            }
        ),
        encoding="utf-8",
    )
    # 模板文件，应被跳过
    (plugins_dir / "_example.yaml").write_text(
        yaml.safe_dump({"id": "example", "name": "示例"}),
        encoding="utf-8",
    )
    return repo


def test_list_market_plugins_parses_and_skips_template(
    tmp_path, monkeypatch, market_repo
):
    data_dir = tmp_path / "data"
    _patch_market(monkeypatch, market_repo, data_dir)

    plugins = agent_utils.list_market_plugins()

    assert len(plugins) == 1
    p = plugins[0]
    assert p["id"] == "foo"
    assert p["name"] == "Foo 插件"
    assert p["description"] == "测试插件"
    assert p["repo"] == "https://github.com/owner/foo"
    assert p["branch"] == "main"
    assert p["author"] == "作者甲"
    assert p["license"] == "MIT"
    assert p["categories"] == ["工具", "效率"]
    assert p["market_repo"] == "https://github.com/skyfireitdiy/plugin-market"


def test_list_market_plugins_skips_bad_yaml(tmp_path, monkeypatch, market_repo):
    (market_repo / "plugins" / "bad.yaml").write_text(
        "::: 非法 yaml :::", encoding="utf-8"
    )
    data_dir = tmp_path / "data"
    _patch_market(monkeypatch, market_repo, data_dir)

    plugins = agent_utils.list_market_plugins()

    # 非法 yaml 被跳过，但 foo 仍被解析
    ids = [p["id"] for p in plugins]
    assert "foo" in ids
    assert "bad" not in ids


def test_list_market_plugins_unreachable_repo_skipped(
    tmp_path, monkeypatch, market_repo
):
    """仓库不可达时跳过该源，不阻断整体返回（返回空列表而非抛异常）。"""
    data_dir = tmp_path / "data"

    def fake_clone_fail(url, branch, dest):
        raise RuntimeError("repo unreachable")

    monkeypatch.setattr(
        config, "get_plugin_market_repos", lambda: ["https://x.invalid/repo"]
    )
    monkeypatch.setattr(config, "get_data_dir", lambda: str(data_dir))
    monkeypatch.setattr(agent_utils, "_git_clone_plugin", fake_clone_fail)
    monkeypatch.setattr(agent_utils, "_git_run", lambda *a, **k: None)

    plugins = agent_utils.list_market_plugins()
    assert plugins == []


def test_list_market_plugins_same_name_different_owner_uses_distinct_cache(
    tmp_path, monkeypatch, market_repo
):
    """不同组织的同名市场仓库使用互不冲突的缓存目录（Issue #243）。

    两个 URL 最后一段都是 ``market``，但属于不同组织，应各自 clone 到独立
    缓存目录，而不是互相覆盖。
    """
    data_dir = tmp_path / "data"
    clone_dests = []

    def fake_clone(url, branch, dest):
        clone_dests.append(str(dest))
        shutil.copytree(str(market_repo), str(dest))

    class FakeProc:
        returncode = 0

    monkeypatch.setattr(
        config,
        "get_plugin_market_repos",
        lambda: [
            "https://github.com/orgA/market",
            "https://github.com/orgB/market",
        ],
    )
    monkeypatch.setattr(config, "get_data_dir", lambda: str(data_dir))
    monkeypatch.setattr(agent_utils, "_git_clone_plugin", fake_clone)
    monkeypatch.setattr(agent_utils, "_git_run", lambda *a, **k: FakeProc())

    plugins = agent_utils.list_market_plugins()

    # 两个源都被 clone 到不同缓存目录
    assert len(clone_dests) == 2
    assert len(set(clone_dests)) == 2
    assert (data_dir / "plugin_market" / "orgA__market").exists()
    assert (data_dir / "plugin_market" / "orgB__market").exists()
    # 两个源的插件都被解析（market_repo 来源标记正确区分）
    assert len(plugins) == 2
    assert {p["market_repo"] for p in plugins} == {
        "https://github.com/orgA/market",
        "https://github.com/orgB/market",
    }


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/orgA/market", "orgA__market"),
        ("https://github.com/orgB/market", "orgB__market"),
        ("https://github.com/orgA/market.git", "orgA__market"),
        ("git@github.com:orgA/market.git", "orgA__market"),
        ("ssh://git@host:2222/orgA/market", "orgA__market"),
        ("https://github.com/orgA/market#dev", "orgA__market"),
        ("https://github.com/orgA/market/", "orgA__market"),
        ("https://github.com/plugin-market", "plugin-market"),
        ("market", "market"),
        ("", "market"),
    ],
)
def test_market_cache_dir_name(url, expected):
    """缓存目录名唯一化：owner/repo 拼接，兼容多种 URL 形态。"""
    assert agent_utils._market_cache_dir_name(url) == expected
