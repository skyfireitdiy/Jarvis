# -*- coding: utf-8 -*-
"""MemoryTool 用户记忆（memory_type=user + user_name）单测

覆盖：user 类型按 user_name 区分存储、save/retrieve/clear 全流程、
user 类型缺失 user_name 时的报错、以及现有三层记忆（project/global/short_term）无回归。
"""

import json

from jarvis.jarvis_tools.memory import MemoryTool


def _make_tool(tmp_path):
    """构造 MemoryTool 实例并把存储目录指到临时目录，避免污染真实数据"""
    tool = MemoryTool()
    tool.global_memory_dir = tmp_path / "global_memory"
    tool.project_memory_dir = tmp_path / "project_memory"
    return tool


def _save_user(tool, user_name, content, tags=None):
    tool.execute(
        {
            "action": "save",
            "memories": [
                {
                    "memory_type": "user",
                    "nature": "long_term",
                    "tags": tags or ["pref"],
                    "content": content,
                    "user_name": user_name,
                    "importance": "high",  # 显式 importance 绕过写时价值过滤
                }
            ],
        }
    )


class TestUserMemorySave:
    """user 类型保存"""

    def test_save_user_memory_requires_user_name(self, tmp_path):
        """memory_type=user 但未提供 user_name 时保存失败"""
        tool = _make_tool(tmp_path)
        result = tool.execute(
            {
                "action": "save",
                "memories": [
                    {
                        "memory_type": "user",
                        "nature": "long_term",
                        "tags": ["pref"],
                        "content": "用户喜欢简洁的代码",
                    }
                ],
            }
        )
        assert result["success"] is True
        data = json.loads(result["stdout"])
        assert data["success"] == 0
        assert data["failed"] == 1
        assert "user_name" in data["results"][0]["error"]

    def test_save_user_memory_with_user_name(self, tmp_path):
        """提供 user_name 后 user 记忆保存到 users/<user_name>/ 目录"""
        tool = _make_tool(tmp_path)
        result = tool.execute(
            {
                "action": "save",
                "memories": [
                    {
                        "memory_type": "user",
                        "nature": "long_term",
                        "tags": ["pref"],
                        "content": "用户喜欢简洁的代码",
                        "user_name": "alice",
                        "importance": "high",
                    }
                ],
            }
        )
        assert result["success"] is True
        data = json.loads(result["stdout"])
        assert data["success"] == 1
        assert data["failed"] == 0
        # 保存到 users/alice/attributes/ 下（long_term -> attributes）
        user_dir = tmp_path / "global_memory" / "users" / "alice" / "attributes"
        files = list(user_dir.glob("*.json"))
        assert len(files) == 1
        saved = json.loads(files[0].read_text(encoding="utf-8"))
        assert saved["memory_type"] == "user"
        assert saved["user_name"] == "alice"


class TestUserMemoryRetrieve:
    """user 类型检索"""

    def test_retrieve_user_requires_user_name(self, tmp_path):
        """memory_types 含 user 但未提供 user_name 时返回错误"""
        tool = _make_tool(tmp_path)
        result = tool.execute(
            {"action": "retrieve", "memory_types": ["user"]}
        )
        assert result["success"] is False
        assert "user_name" in result["stderr"]

    def test_retrieve_user_by_user_name(self, tmp_path):
        """按 user_name 检索只返回该用户的记忆"""
        tool = _make_tool(tmp_path)
        _save_user(tool, "alice", "喜欢简洁代码", ["pref"])
        _save_user(tool, "bob", "喜欢详细注释", ["pref"])

        result = tool.execute(
            {
                "action": "retrieve",
                "memory_types": ["user"],
                "user_name": "alice",
            }
        )
        assert result["success"] is True
        assert "喜欢简洁代码" in result["stdout"]
        assert "喜欢详细注释" not in result["stdout"]

    def test_user_memory_isolated_from_global(self, tmp_path):
        """user 记忆不混入 global 检索结果"""
        tool = _make_tool(tmp_path)
        # 存一条 global 记忆
        tool.execute(
            {
                "action": "save",
                "memories": [
                    {
                        "memory_type": "global",
                        "nature": "long_term",
                        "tags": ["tip"],
                        "content": "全局通用技巧",
                        "importance": "high",
                    }
                ],
            }
        )
        # 存一条 user 记忆
        _save_user(tool, "alice", "用户专属偏好", ["pref"])

        # 检索 global 不应出现 user 记忆
        result = tool.execute({"action": "retrieve", "memory_types": ["global"]})
        assert "用户专属偏好" not in result["stdout"]
        assert "全局通用技巧" in result["stdout"]

        # 检索 user 不应出现 global 记忆
        result = tool.execute(
            {"action": "retrieve", "memory_types": ["user"], "user_name": "alice"}
        )
        assert "全局通用技巧" not in result["stdout"]
        assert "用户专属偏好" in result["stdout"]


class TestUserMemoryClear:
    """user 类型清除"""

    def test_clear_user_requires_user_name(self, tmp_path):
        """清除 user 记忆但未提供 user_name 时返回错误"""
        tool = _make_tool(tmp_path)
        result = tool.execute(
            {
                "action": "clear",
                "memory_types": ["user"],
                "confirm": True,
            }
        )
        assert result["success"] is False
        assert "user_name" in result["stderr"]

    def test_clear_user_by_user_name(self, tmp_path):
        """按 user_name 清除只清除该用户的记忆"""
        tool = _make_tool(tmp_path)
        _save_user(tool, "alice", "alice 的记忆", ["pref"])
        _save_user(tool, "bob", "bob 的记忆", ["pref"])

        result = tool.execute(
            {
                "action": "clear",
                "memory_types": ["user"],
                "user_name": "alice",
                "confirm": True,
            }
        )
        assert result["success"] is True
        assert "1" in result["stdout"]  # 清除了 1 条

        # alice 的目录已清空
        alice_dir = tmp_path / "global_memory" / "users" / "alice" / "attributes"
        assert list(alice_dir.glob("*.json")) == []
        # bob 的记忆仍在
        bob_dir = tmp_path / "global_memory" / "users" / "bob" / "attributes"
        assert len(list(bob_dir.glob("*.json"))) == 1


class TestExistingLayersNoRegression:
    """现有三层记忆（project/global/short_term）行为不变"""

    def test_project_global_short_term_save_retrieve(self, tmp_path):
        """project/global/short_term 仍可正常保存与检索"""
        tool = _make_tool(tmp_path)
        for mt in ["project", "global", "short_term"]:
            result = tool.execute(
                {
                    "action": "save",
                    "memories": [
                        {
                            "memory_type": mt,
                            "nature": "long_term",
                            "tags": ["t"],
                            "content": f"{mt} 记忆内容",
                            "importance": "high",
                        }
                    ],
                }
            )
            assert result["success"] is True
            data = json.loads(result["stdout"])
            assert data["success"] == 1, f"{mt} 保存失败: {data}"

        # 默认检索（all）应能取到 project/global 记忆
        result = tool.execute({"action": "retrieve"})
        assert result["success"] is True
        assert "project 记忆内容" in result["stdout"]
        assert "global 记忆内容" in result["stdout"]
