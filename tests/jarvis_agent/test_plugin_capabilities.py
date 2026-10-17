# -*- coding: utf-8 -*-
"""_build_plugin_capabilities 插件能力清单构建测试。

覆盖：
- 既有字段（rules/tools/agents/orchestration/frontend/replace_map/custom）不受影响
- Issue #257：mcpserver 扩展点声明的 MCP 服务应纳入能力清单（type=mcp）
"""

from jarvis.jarvis_agent.utils import _build_plugin_capabilities


def _build(config):
    """调用被测函数，返回 capabilities 列表。"""
    return _build_plugin_capabilities(config)


def test_empty_config_returns_empty_list():
    """空配置返回空能力清单。"""
    assert _build({}) == []


def test_mcpserver_append_mcp_capability():
    """插件声明 mcpserver 时，能力清单包含 type=mcp 的能力项。"""
    caps = _build(
        {
            "mcpserver": [
                {
                    "type": "stdio",
                    "name": "filesystem",
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem"],
                }
            ]
        }
    )
    mcp_caps = [c for c in caps if c["type"] == "mcp"]
    assert len(mcp_caps) == 1
    assert mcp_caps[0]["name"] == "MCP：filesystem"
    assert "stdio" in mcp_caps[0]["description"]


def test_mcpserver_multiple_and_description():
    """多个 MCP server 各自生成能力项，description 透传插件声明。"""
    caps = _build(
        {
            "mcpserver": [
                {
                    "type": "sse",
                    "name": "mcp-a",
                    "base_url": "http://a",
                    "description": "服务 A",
                },
                {"type": "streamable", "name": "mcp-b", "base_url": "http://b"},
            ]
        }
    )
    mcp_caps = [c for c in caps if c["type"] == "mcp"]
    assert [c["name"] for c in mcp_caps] == ["MCP：mcp-a", "MCP：mcp-b"]
    assert "服务 A" in mcp_caps[0]["description"]
    assert "streamable" in mcp_caps[1]["description"]


def test_mcpserver_disabled_skipped():
    """enable=false 的 MCP server 不进入能力清单。"""
    caps = _build(
        {
            "mcpserver": [
                {"type": "stdio", "name": "enabled", "command": "cmd"},
                {
                    "type": "stdio",
                    "name": "disabled",
                    "command": "cmd",
                    "enable": False,
                },
            ]
        }
    )
    mcp_caps = [c for c in caps if c["type"] == "mcp"]
    assert [c["name"] for c in mcp_caps] == ["MCP：enabled"]


def test_mcpserver_missing_name_skipped():
    """缺少 name 的 MCP server 项被跳过，不崩溃。"""
    caps = _build({"mcpserver": [{"type": "stdio", "command": "cmd"}, "not-a-dict"]})
    assert all(c["type"] != "mcp" for c in caps)


def test_existing_fields_still_work():
    """既有能力字段（rules/tools/frontend/replace_map/custom）不受影响。"""
    caps = _build(
        {
            "rules_load_dirs": ["rules"],
            "tool_load_dirs": ["tools"],
            "frontend": {"sidebar_views": [{"id": "s1"}]},
            "replace_map": {"greet": {"description": "打招呼"}},
            "capabilities": [{"name": "事件钩子", "description": "监听事件"}],
            "mcpserver": [{"type": "stdio", "name": "mcp-x", "command": "cmd"}],
        }
    )
    types = [c["type"] for c in caps]
    assert "rules" in types
    assert "tools" in types
    assert "frontend" in types
    assert "replace_map" in types
    assert "custom" in types
    assert "mcp" in types
    # mcpserver 能力项存在
    mcp_caps = [c for c in caps if c["type"] == "mcp"]
    assert mcp_caps[0]["name"] == "MCP：mcp-x"


def test_lsp_append_lsp_capability():
    """插件声明 lsp.languages 时，能力清单包含 type=lsp 的能力项。"""
    caps = _build(
        {
            "lsp": {
                "languages": {
                    "python": {
                        "command": "pyright-langserver",
                        "args": ["--stdio"],
                        "file_extensions": [".py"],
                    }
                }
            }
        }
    )
    lsp_caps = [c for c in caps if c["type"] == "lsp"]
    assert len(lsp_caps) == 1
    assert lsp_caps[0]["name"] == "LSP：python"
    assert "pyright-langserver" in lsp_caps[0]["description"]
    # 安全提示：command 会执行外部程序
    assert "外部程序" in lsp_caps[0]["description"]


def test_lsp_multiple_languages_and_description():
    """多个语言各自生成能力项，description 透传插件声明。"""
    caps = _build(
        {
            "lsp": {
                "languages": {
                    "python": {
                        "command": "pyright-langserver",
                        "description": "Python 语言服务",
                    },
                    "rust": {"command": "rust-analyzer"},
                }
            }
        }
    )
    lsp_caps = [c for c in caps if c["type"] == "lsp"]
    assert [c["name"] for c in lsp_caps] == ["LSP：python", "LSP：rust"]
    assert "Python 语言服务" in lsp_caps[0]["description"]


def test_lsp_disabled_skipped():
    """enable=false 的语言服务不进入能力清单。"""
    caps = _build(
        {
            "lsp": {
                "languages": {
                    "python": {"command": "pyright-langserver"},
                    "rust": {"command": "rust-analyzer", "enable": False},
                }
            }
        }
    )
    lsp_caps = [c for c in caps if c["type"] == "lsp"]
    assert [c["name"] for c in lsp_caps] == ["LSP：python"]


def test_lsp_missing_command_still_shown():
    """缺少 command 的语言项仍展示（含安全提示），不崩溃。"""
    caps = _build({"lsp": {"languages": {"python": {"description": "无命令"}}}})
    lsp_caps = [c for c in caps if c["type"] == "lsp"]
    assert len(lsp_caps) == 1
    assert "无命令" in lsp_caps[0]["description"]
    assert "外部程序" in lsp_caps[0]["description"]
