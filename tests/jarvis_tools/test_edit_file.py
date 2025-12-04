# -*- coding: utf-8 -*-
"""jarvis_tools.edit_file_structed 模块单元测试"""

import os
import tempfile
import time
from unittest.mock import MagicMock

import pytest

from jarvis.jarvis_tools.edit_file_structed import EditFileTool


class TestEditFileTool:
    """测试 EditFileTool 类"""

    @pytest.fixture
    def tool(self):
        """创建测试用的 EditFileTool 实例"""
        return EditFileTool()

    @pytest.fixture
    def mock_agent(self):
        """创建模拟的 Agent 实例"""
        agent = MagicMock()
        # 使用字典存储用户数据
        agent._user_data = {}

        # 显式设置 model_group 为 None，避免 MagicMock 自动创建属性
        agent.model_group = None

        def get_user_data(key):
            return agent._user_data.get(key)

        def set_user_data(key, value):
            agent._user_data[key] = value

        agent.get_user_data = MagicMock(side_effect=get_user_data)
        agent.set_user_data = MagicMock(side_effect=set_user_data)
        return agent

    @pytest.fixture
    def sample_file(self):
        """创建示例文件"""
        content = """def hello():
    print("Hello, World!")

def add(a, b):
    return a + b

class Calculator:
    def __init__(self):
        self.value = 0
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(content)
            filepath = f.name

        yield filepath

        # 清理
        if os.path.exists(filepath):
            os.unlink(filepath)
        if os.path.exists(filepath + ".bak"):
            os.unlink(filepath + ".bak")

    @pytest.fixture
    def sample_file_with_cache(self, sample_file, mock_agent):
        """创建带缓存的示例文件"""
        abs_path = os.path.abspath(sample_file)
        file_mtime = os.path.getmtime(abs_path)

        # 创建有效缓存（新格式：id_list 和 blocks）
        cache = {
            abs_path: {
                "id_list": ["block-1", "block-2", "block-3"],
                "blocks": {
                    "block-1": {
                        "content": 'def hello():\n    print("Hello, World!")\n'
                    },
                    "block-2": {"content": "\ndef add(a, b):\n    return a + b\n"},
                    "block-3": {
                        "content": "\nclass Calculator:\n    def __init__(self):\n        self.value = 0\n"
                    },
                },
                "total_lines": 10,
                "read_time": time.time(),
                "file_mtime": file_mtime,
            }
        }

        # 设置 get_user_data 的返回值
        def get_user_data_side_effect(key):
            if key == "read_code_cache":
                return cache
            return None

        mock_agent.get_user_data.side_effect = get_user_data_side_effect

        return sample_file, mock_agent

    def test_replace_block(self, tool, sample_file_with_cache):
        """测试替换块"""
        sample_file, mock_agent = sample_file_with_cache

        result = tool.execute(
            {
                "files": [
                    {
                        "file_path": sample_file,
                        "diffs": [
                            {
                                "block_id": "block-1",
                                "action": "replace",
                                "content": "def hello():\n    print('Hi!')\n",
                            }
                        ],
                    }
                ],
                "agent": mock_agent,
            }
        )

        assert result["success"] is True

        # 验证文件内容已更新
        with open(sample_file, "r") as f:
            content = f.read()
            assert "Hi!" in content

    def test_delete_block(self, tool, sample_file_with_cache):
        """测试删除块（清空内容）"""
        sample_file, mock_agent = sample_file_with_cache

        result = tool.execute(
            {
                "files": [
                    {
                        "file_path": sample_file,
                        "diffs": [{"block_id": "block-1", "action": "delete"}],
                    }
                ],
                "agent": mock_agent,
            }
        )

        assert result["success"] is True

        # 验证缓存中的块内容已清空
        cache = mock_agent.get_user_data("read_code_cache")
        if cache:
            abs_path = os.path.abspath(sample_file)
            if abs_path in cache:
                blocks = cache[abs_path]["blocks"]
                block = blocks.get("block-1")
                if block:
                    assert block["content"] == ""

    def test_insert_before(self, tool, sample_file_with_cache):
        """测试在块前插入"""
        sample_file, mock_agent = sample_file_with_cache

        result = tool.execute(
            {
                "files": [
                    {
                        "file_path": sample_file,
                        "diffs": [
                            {
                                "block_id": "block-2",
                                "action": "insert_before",
                                "content": "# New comment\n",
                            }
                        ],
                    }
                ],
                "agent": mock_agent,
            }
        )

        assert result["success"] is True

        # 验证文件内容已更新
        with open(sample_file, "r") as f:
            content = f.read()
            assert "# New comment" in content

    def test_insert_after(self, tool, sample_file_with_cache):
        """测试在块后插入"""
        sample_file, mock_agent = sample_file_with_cache

        result = tool.execute(
            {
                "files": [
                    {
                        "file_path": sample_file,
                        "diffs": [
                            {
                                "block_id": "block-2",
                                "action": "insert_after",
                                "content": "# After comment\n",
                            }
                        ],
                    }
                ],
                "agent": mock_agent,
            }
        )

        assert result["success"] is True

        # 验证文件内容已更新
        with open(sample_file, "r") as f:
            content = f.read()
            assert "# After comment" in content

    def test_edit_without_cache(self, tool, sample_file, mock_agent):
        """测试在没有缓存的情况下编辑"""
        result = tool.execute(
            {
                "files": [
                    {
                        "file_path": sample_file,
                        "diffs": [
                            {
                                "block_id": "block-1",
                                "action": "replace",
                                "content": "new content",
                            }
                        ],
                    }
                ],
                "agent": mock_agent,
            }
        )

        # 应该失败，提示需要先读取文件
        assert result["success"] is False
        error_msg = result.get("stdout", "") + result.get("stderr", "")
        assert "缓存" in error_msg or "read_code" in error_msg.lower()

    def test_edit_with_invalid_block_id(self, tool, sample_file_with_cache):
        """测试使用无效的块id"""
        sample_file, mock_agent = sample_file_with_cache

        result = tool.execute(
            {
                "files": [
                    {
                        "file_path": sample_file,
                        "diffs": [
                            {
                                "block_id": "block-999",
                                "action": "replace",
                                "content": "new content",
                            }
                        ],
                    }
                ],
                "agent": mock_agent,
            }
        )

        assert result["success"] is False
        error_msg = result.get("stdout", "") + result.get("stderr", "")
        assert "未找到" in error_msg or "not found" in error_msg.lower()

    def test_edit_multiple_operations(self, tool, sample_file_with_cache):
        """测试多个编辑操作"""
        sample_file, mock_agent = sample_file_with_cache

        result = tool.execute(
            {
                "files": [
                    {
                        "file_path": sample_file,
                        "diffs": [
                            {
                                "block_id": "block-1",
                                "action": "replace",
                                "content": "def hello():\n    print('Modified')\n",
                            },
                            {
                                "block_id": "block-2",
                                "action": "insert_before",
                                "content": "# Before add\n",
                            },
                        ],
                    }
                ],
                "agent": mock_agent,
            }
        )

        assert result["success"] is True

        # 验证两个操作都生效
        with open(sample_file, "r") as f:
            content = f.read()
            assert "Modified" in content
            assert "# Before add" in content

    def test_edit_with_missing_content(self, tool, sample_file_with_cache):
        """测试缺少content参数"""
        sample_file, mock_agent = sample_file_with_cache

        result = tool.execute(
            {
                "files": [
                    {
                        "file_path": sample_file,
                        "diffs": [{"block_id": "block-1", "action": "replace"}],
                    }
                ],
                "agent": mock_agent,
            }
        )

        assert result["success"] is False
        error_msg = result.get("stdout", "") + result.get("stderr", "")
        assert "content" in error_msg.lower()

    def test_edit_with_invalid_action(self, tool, sample_file_with_cache):
        """测试无效的操作类型"""
        sample_file, mock_agent = sample_file_with_cache

        result = tool.execute(
            {
                "files": [
                    {
                        "file_path": sample_file,
                        "diffs": [
                            {
                                "block_id": "block-1",
                                "action": "invalid_action",
                                "content": "content",
                            }
                        ],
                    }
                ],
                "agent": mock_agent,
            }
        )

        assert result["success"] is False
        error_msg = result.get("stdout", "") + result.get("stderr", "")
        assert "action" in error_msg.lower()

    def test_edit_nonexistent_file(self, tool, mock_agent):
        """测试编辑不存在的文件"""
        # 创建无效缓存（新格式）
        cache = {
            "/nonexistent/file.py": {
                "id_list": ["block-1"],
                "blocks": {"block-1": {"content": "content"}},
                "total_lines": 1,
                "read_time": time.time(),
                "file_mtime": time.time(),
            }
        }
        mock_agent.get_user_data.return_value = cache

        result = tool.execute(
            {
                "files": [
                    {
                        "file_path": "/nonexistent/file.py",
                        "diffs": [
                            {
                                "block_id": "block-1",
                                "action": "replace",
                                "content": "new content",
                            }
                        ],
                    }
                ],
                "agent": mock_agent,
            }
        )

        # 应该失败，因为缓存无效
        assert result["success"] is False

    def test_cache_invalid_after_external_file_modification(
        self, tool, sample_file, mock_agent
    ):
        """测试外部修改文件后缓存失效（实际修改文件）"""
        abs_path = os.path.abspath(sample_file)

        # 创建原始文件内容
        original_content = """def hello():
    print("Hello, World!")

def add(a, b):
    return a + b
"""
        with open(abs_path, "w") as f:
            f.write(original_content)

        # 等待一小段时间，确保文件时间戳稳定
        time.sleep(0.2)

        # 建立缓存
        file_mtime = os.path.getmtime(abs_path)
        cache = {
            abs_path: {
                "id_list": ["block-1", "block-2"],
                "blocks": {
                    "block-1": {
                        "content": 'def hello():\n    print("Hello, World!")\n'
                    },
                    "block-2": {"content": "\ndef add(a, b):\n    return a + b\n"},
                },
                "total_lines": 5,
                "read_time": time.time(),
                "file_mtime": file_mtime,
            }
        }

        def get_user_data_side_effect(key):
            if key == "read_code_cache":
                return cache
            return None

        mock_agent.get_user_data.side_effect = get_user_data_side_effect

        # 验证缓存有效
        cache_info = EditFileTool._get_file_cache(mock_agent, abs_path)
        is_valid_before = EditFileTool._is_cache_valid(cache_info, abs_path)
        assert is_valid_before is True

        # 外部修改文件（模拟外部编辑器修改）
        modified_content = """def hello():
    print("Hello, Modified World!")

def add(a, b):
    return a + b

def multiply(a, b):
    return a * b
"""
        with open(abs_path, "w") as f:
            f.write(modified_content)

        # 等待一小段时间，确保文件时间戳更新
        time.sleep(0.2)

        # 验证缓存失效
        cache_info_after = EditFileTool._get_file_cache(mock_agent, abs_path)
        is_valid_after = EditFileTool._is_cache_valid(cache_info_after, abs_path)
        assert is_valid_after is False, "文件被外部修改后，缓存应该失效"

        # 尝试编辑文件，应该失败并提示缓存无效
        result = tool.execute(
            {
                "files": [
                    {
                        "file_path": sample_file,
                        "diffs": [
                            {
                                "block_id": "block-1",
                                "action": "replace",
                                "content": "new content\n",
                            }
                        ],
                    }
                ],
                "agent": mock_agent,
            }
        )

        # 应该失败，因为缓存无效
        assert result["success"] is False
        # 验证错误信息包含缓存无效的提示
        error_msg = result.get("stderr", "") + result.get("stdout", "")
        assert (
            "缓存无效" in error_msg
            or "文件已被外部修改" in error_msg
            or "重新读取文件" in error_msg
        )

    def test_cache_update_after_edit(self, tool, sample_file, mock_agent):
        """测试编辑后缓存更新"""
        abs_path = os.path.abspath(sample_file)

        # 设置缓存，使其可以被修改（新格式）
        cache = {
            abs_path: {
                "id_list": ["block-1", "block-2"],
                "blocks": {
                    "block-1": {"content": "original content"},
                    "block-2": {"content": "other content"},
                },
                "total_lines": 2,
                "read_time": time.time(),
                "file_mtime": os.path.getmtime(abs_path),
            }
        }

        # 设置 get_user_data 的返回值
        def get_user_data_side_effect(key):
            if key == "read_code_cache":
                return cache
            return None

        mock_agent.get_user_data.side_effect = get_user_data_side_effect

        result = tool.execute(
            {
                "files": [
                    {
                        "file_path": sample_file,
                        "diffs": [
                            {
                                "block_id": "block-1",
                                "action": "replace",
                                "content": "new content\n",
                            }
                        ],
                    }
                ],
                "agent": mock_agent,
            }
        )

        assert result["success"] is True

        # 验证缓存已更新
        assert mock_agent.set_user_data.called
        # 检查缓存中的内容是否已更新
        final_cache = cache[abs_path]
        blocks = final_cache["blocks"]
        block = blocks.get("block-1")
        assert block is not None
        assert "new content" in block["content"]

    def test_apply_structured_edit_to_cache(self, tool):
        """测试直接在缓存中应用编辑"""
        cache_info = {
            "id_list": ["block-1", "block-2"],
            "blocks": {
                "block-1": {"content": "original content"},
                "block-2": {"content": "other content"},
            },
            "total_lines": 2,
        }

        # 测试替换
        success, error, error_type = EditFileTool._apply_structured_edit_to_cache(
            cache_info, "block-1", "replace", "new content"
        )
        assert success is True
        assert cache_info["blocks"]["block-1"]["content"] == "new content"

        # 测试删除（清空）
        success, error, error_type = EditFileTool._apply_structured_edit_to_cache(
            cache_info, "block-2", "delete", None
        )
        assert success is True
        assert cache_info["blocks"]["block-2"]["content"] == ""

        # 测试插入前
        success, error, error_type = EditFileTool._apply_structured_edit_to_cache(
            cache_info, "block-1", "insert_before", "prefix "
        )
        assert success is True
        assert cache_info["blocks"]["block-1"]["content"].startswith("prefix ")

        # 测试插入后
        success, error, error_type = EditFileTool._apply_structured_edit_to_cache(
            cache_info, "block-1", "insert_after", " suffix"
        )
        assert success is True
        assert cache_info["blocks"]["block-1"]["content"].endswith(" suffix")

    def test_restore_file_from_cache_with_newline_insertion(self, tool):
        """测试从缓存恢复文件内容时，块之间自动插入换行符"""
        cache_info = {
            "id_list": ["block-1", "block-2"],
            "blocks": {
                "block-1": {
                    "content": "pub fn test() {\n}\n\n#[cfg(test)]"
                },  # 不以换行符结尾
                "block-2": {"content": "mod tests {"},  # 不以换行符开头
            },
            "file_ends_with_newline": False,
        }

        recovered = EditFileTool._restore_file_from_cache(cache_info)

        # 应该自动在块之间插入换行符（新逻辑：总是在块之间插入换行符）
        assert "#[cfg(test)]\nmod tests {" in recovered
        assert "#[cfg(test)]mod tests {" not in recovered  # 不应该没有换行

    def test_restore_file_from_cache_no_duplicate_newline(self, tool):
        """测试块之间换行符的插入（新逻辑：总是在块之间插入换行符）"""
        cache_info = {
            "id_list": ["block-1", "block-2"],
            "blocks": {
                "block-1": {
                    "content": "pub fn test() {\n}\n\n#[cfg(test)]\n"
                },  # 以换行符结尾
                "block-2": {"content": "mod tests {"},  # 不以换行符开头
            },
            "file_ends_with_newline": False,
        }

        recovered = EditFileTool._restore_file_from_cache(cache_info)

        # 新逻辑：总是在块之间插入换行符，所以会有两个换行符（block-1末尾的\n + 块之间的\n）
        assert "#[cfg(test)]\n\nmod tests {" in recovered
        # 验证块之间确实有换行符分隔
        assert "mod tests {" in recovered

    def test_restore_file_from_cache_block_starts_with_newline(self, tool):
        """测试当前块以换行符开头时的处理（新逻辑：总是在块之间插入换行符）"""
        cache_info = {
            "id_list": ["block-1", "block-2"],
            "blocks": {
                "block-1": {
                    "content": "pub fn test() {\n}\n\n#[cfg(test)]"
                },  # 不以换行符结尾
                "block-2": {"content": "\nmod tests {"},  # 以换行符开头
            },
            "file_ends_with_newline": False,
        }

        recovered = EditFileTool._restore_file_from_cache(cache_info)

        # 新逻辑：总是在块之间插入换行符，所以会有两个换行符（块之间的\n + block-2开头的\n）
        assert "#[cfg(test)]\n\nmod tests {" in recovered
        # 验证块之间确实有换行符分隔
        assert "mod tests {" in recovered

    def test_restore_file_from_cache_multiple_blocks(self, tool):
        """测试多个块连续时，正确插入换行符（新逻辑：总是在块之间插入换行符）"""
        cache_info = {
            "id_list": ["block-1", "block-2", "block-3", "block-4"],
            "blocks": {
                "block-1": {"content": "first"},  # 不以换行符结尾
                "block-2": {"content": "second"},  # 不以换行符开头或结尾
                "block-3": {"content": "third\n"},  # 以换行符结尾
                "block-4": {"content": "fourth"},  # 不以换行符开头
            },
            "file_ends_with_newline": False,
        }

        recovered = EditFileTool._restore_file_from_cache(cache_info)

        # block-1 和 block-2 之间应该插入换行
        assert "first\nsecond" in recovered
        # block-2 和 block-3 之间应该插入换行
        assert "second\nthird" in recovered
        # block-3 和 block-4 之间也应该插入换行（新逻辑：总是在块之间插入）
        # block-3以\n结尾，块之间插入\n，所以是\n\n
        assert "third\n\nfourth" in recovered

    def test_restore_file_from_cache_empty_blocks(self, tool):
        """测试空块的处理"""
        cache_info = {
            "id_list": ["block-1", "block-2", "block-3"],
            "blocks": {
                "block-1": {"content": "first"},
                "block-2": {"content": ""},  # 空块
                "block-3": {"content": "third"},
            },
            "file_ends_with_newline": False,
        }

        recovered = EditFileTool._restore_file_from_cache(cache_info)

        # 空块应该被跳过（不添加到结果中，因为content为空）
        assert "first" in recovered
        assert "third" in recovered
        # first 和 third 之间应该插入换行（新逻辑：总是在块之间插入换行符）
        assert "first\nthird" in recovered

    def test_restore_file_from_cache_all_blocks_with_newlines(self, tool):
        """测试所有块都以换行符结尾时的处理（新逻辑：总是在块之间插入换行符）"""
        cache_info = {
            "id_list": ["block-1", "block-2"],
            "blocks": {
                "block-1": {"content": "first\n"},  # 以换行符结尾
                "block-2": {"content": "second\n"},  # 以换行符结尾
            },
            "file_ends_with_newline": True,  # 文件以换行符结尾
        }

        recovered = EditFileTool._restore_file_from_cache(cache_info)

        # 新逻辑：总是在块之间插入换行符，所以block-1的\n + 块之间的\n = \n\n
        assert "first\n\nsecond" in recovered
        # 验证最后有换行符（因为file_ends_with_newline=True）
        assert recovered.endswith("\n")

    def test_restore_file_from_cache(self, tool):
        """测试从缓存恢复文件"""
        cache_info = {
            "id_list": ["block-1", "block-2", "block-3"],
            "blocks": {
                "block-1": {"content": "first"},
                "block-2": {"content": "second"},
                "block-3": {"content": "third"},
            },
            "file_ends_with_newline": False,
        }

        result = EditFileTool._restore_file_from_cache(cache_info)

        # 应该按id_list顺序拼接
        assert "first" in result
        assert "second" in result
        assert "third" in result
        # 验证顺序
        assert result.index("first") < result.index("second")
        assert result.index("second") < result.index("third")
        # 验证块之间有换行符
        assert "first\nsecond" in result
        assert "second\nthird" in result

    def test_validate_structured_diff(self, tool):
        """测试验证结构化diff"""
        # 有效的diff
        error, patch = EditFileTool._validate_structured(
            {"block_id": "block-1", "action": "replace", "content": "new content"}, 0
        )

        assert error is None
        assert patch is not None
        assert patch["STRUCTURED_BLOCK_ID"] == "block-1"
        assert patch["STRUCTURED_ACTION"] == "replace"

        # 缺少block_id
        error, patch = EditFileTool._validate_structured(
            {"action": "replace", "content": "content"}, 0
        )

        assert error is not None
        assert "block_id" in error["stderr"]

        # 无效的action
        error, patch = EditFileTool._validate_structured(
            {"block_id": "block-1", "action": "invalid", "content": "content"}, 0
        )

        assert error is not None
        assert "action" in error["stderr"]

    def test_edit_with_empty_diffs(self, tool, sample_file_with_cache):
        """测试空的diffs列表"""
        sample_file, mock_agent = sample_file_with_cache

        result = tool.execute(
            {"files": [{"file_path": sample_file, "diffs": []}], "agent": mock_agent}
        )

        assert result["success"] is False
        assert "diffs" in result["stderr"].lower()

    def test_edit_file_validation(self, tool):
        """测试文件编辑参数验证"""
        # 缺少 files
        result = tool.execute(
            {
                "diffs": [
                    {"block_id": "block-1", "action": "replace", "content": "content"}
                ]
            }
        )
        assert result["success"] is False
        assert "files" in result["stderr"].lower()

    def test_restore_empty_cache(self, tool):
        """测试恢复空缓存"""
        cache_info = {"id_list": [], "blocks": {}}
        result = EditFileTool._restore_file_from_cache(cache_info)
        assert result == ""

        # 测试 None 缓存
        result = EditFileTool._restore_file_from_cache(None)
        assert result == ""

        # 测试缺少 id_list 和 blocks 的缓存
        result = EditFileTool._restore_file_from_cache({})
        assert result == ""

    def test_edit_python_file_with_cache(self, tool, mock_agent):
        """测试编辑Python文件（带缓存）"""
        python_content = """def func1():
    return 1

def func2():
    return 2
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(python_content)
            filepath = f.name

        try:
            abs_path = os.path.abspath(filepath)
            file_mtime = os.path.getmtime(abs_path)

            # 创建缓存（新格式）
            cache = {
                abs_path: {
                    "id_list": ["block-1", "block-2"],
                    "blocks": {
                        "block-1": {"content": "def func1():\n    return 1\n"},
                        "block-2": {"content": "\ndef func2():\n    return 2\n"},
                    },
                    "total_lines": 6,
                    "read_time": time.time(),
                    "file_mtime": file_mtime,
                }
            }

            def get_user_data_side_effect(key):
                if key == "read_code_cache":
                    return cache
                return None

            mock_agent.get_user_data.side_effect = get_user_data_side_effect

            # 编辑文件
            result = tool.execute(
                {
                    "files": [
                        {
                            "file_path": filepath,
                            "diffs": [
                                {
                                    "block_id": "block-1",
                                    "action": "replace",
                                    "content": "def func1():\n    return 100\n",
                                }
                            ],
                        }
                    ],
                    "agent": mock_agent,
                }
            )

            assert result["success"] is True

            # 验证文件已更新
            with open(filepath, "r") as f:
                content = f.read()
                assert "return 100" in content
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)
            if os.path.exists(filepath + ".bak"):
                os.unlink(filepath + ".bak")

    def test_edit_c_file_with_cache(self, tool, mock_agent):
        """测试编辑C文件（带缓存）"""
        c_content = """#include <stdio.h>

void func1() {
    printf("1");
}

void func2() {
    printf("2");
}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".c", delete=False) as f:
            f.write(c_content)
            filepath = f.name

        try:
            abs_path = os.path.abspath(filepath)
            file_mtime = os.path.getmtime(abs_path)

            # 创建缓存（新格式）
            cache = {
                abs_path: {
                    "id_list": ["block-1", "block-2", "block-3"],
                    "blocks": {
                        "block-1": {"content": "#include <stdio.h>\n\n"},
                        "block-2": {
                            "content": 'void func1() {\n    printf("1");\n}\n\n'
                        },
                        "block-3": {"content": 'void func2() {\n    printf("2");\n}\n'},
                    },
                    "total_lines": 10,
                    "read_time": time.time(),
                    "file_mtime": file_mtime,
                }
            }

            def get_user_data_side_effect(key):
                if key == "read_code_cache":
                    return cache
                return None

            mock_agent.get_user_data.side_effect = get_user_data_side_effect

            # 编辑文件
            result = tool.execute(
                {
                    "files": [
                        {
                            "file_path": filepath,
                            "diffs": [
                                {
                                    "block_id": "block-2",
                                    "action": "replace",
                                    "content": 'void func1() {\n    printf("modified");\n}\n\n',
                                }
                            ],
                        }
                    ],
                    "agent": mock_agent,
                }
            )

            assert result["success"] is True

            # 验证文件已更新
            with open(filepath, "r") as f:
                content = f.read()
                assert "modified" in content
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)
            if os.path.exists(filepath + ".bak"):
                os.unlink(filepath + ".bak")

    def test_edit_java_file_with_cache(self, tool, mock_agent):
        """测试编辑Java文件（带缓存）"""
        java_content = """public class Main {
    public void method1() {
    }
    
    public void method2() {
    }
}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(java_content)
            filepath = f.name

        try:
            abs_path = os.path.abspath(filepath)
            file_mtime = os.path.getmtime(abs_path)

            # 创建缓存（新格式）
            cache = {
                abs_path: {
                    "id_list": ["block-1", "block-2", "block-3", "block-4"],
                    "blocks": {
                        "block-1": {"content": "public class Main {\n"},
                        "block-2": {"content": "    public void method1() {\n    }\n"},
                        "block-3": {
                            "content": "    \n    public void method2() {\n    }\n"
                        },
                        "block-4": {"content": "}\n"},
                    },
                    "total_lines": 7,
                    "read_time": time.time(),
                    "file_mtime": file_mtime,
                }
            }

            def get_user_data_side_effect(key):
                if key == "read_code_cache":
                    return cache
                return None

            mock_agent.get_user_data.side_effect = get_user_data_side_effect

            # 编辑文件
            result = tool.execute(
                {
                    "files": [
                        {
                            "file_path": filepath,
                            "diffs": [
                                {
                                    "block_id": "block-2",
                                    "action": "insert_before",
                                    "content": "    // New comment\n",
                                }
                            ],
                        }
                    ],
                    "agent": mock_agent,
                }
            )

            assert result["success"] is True

            # 验证文件已更新
            with open(filepath, "r") as f:
                content = f.read()
                assert "// New comment" in content
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)
            if os.path.exists(filepath + ".bak"):
                os.unlink(filepath + ".bak")

    def test_edit_rust_file_with_cache(self, tool, mock_agent):
        """测试编辑Rust文件（带缓存）"""
        rust_content = """fn main() {
    println!("Hello");
}

struct Point {
    x: i32,
    y: i32,
}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".rs", delete=False) as f:
            f.write(rust_content)
            filepath = f.name

        try:
            abs_path = os.path.abspath(filepath)
            file_mtime = os.path.getmtime(abs_path)

            # 创建缓存（新格式）
            cache = {
                abs_path: {
                    "id_list": ["block-1", "block-2"],
                    "blocks": {
                        "block-1": {
                            "content": 'fn main() {\n    println!("Hello");\n}\n\n'
                        },
                        "block-2": {
                            "content": "struct Point {\n    x: i32,\n    y: i32,\n}\n"
                        },
                    },
                    "total_lines": 8,
                    "read_time": time.time(),
                    "file_mtime": file_mtime,
                }
            }

            def get_user_data_side_effect(key):
                if key == "read_code_cache":
                    return cache
                return None

            mock_agent.get_user_data.side_effect = get_user_data_side_effect

            # 编辑文件
            result = tool.execute(
                {
                    "files": [
                        {
                            "file_path": filepath,
                            "diffs": [{"block_id": "block-1", "action": "delete"}],
                        }
                    ],
                    "agent": mock_agent,
                }
            )

            assert result["success"] is True

            # 验证缓存中的块内容已清空
            final_cache = cache[abs_path]
            blocks = final_cache["blocks"]
            block = blocks.get("block-1")
            assert block is not None
            assert block["content"] == ""
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)
            if os.path.exists(filepath + ".bak"):
                os.unlink(filepath + ".bak")

    def test_edit_go_file_with_cache(self, tool, mock_agent):
        """测试编辑Go文件（带缓存）"""
        go_content = """package main

func main() {
    fmt.Println("Hello")
}

type Point struct {
    x int
    y int
}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".go", delete=False) as f:
            f.write(go_content)
            filepath = f.name

        try:
            abs_path = os.path.abspath(filepath)
            file_mtime = os.path.getmtime(abs_path)

            # 创建缓存（新格式）
            cache = {
                abs_path: {
                    "id_list": ["block-1", "block-2", "block-3"],
                    "blocks": {
                        "block-1": {"content": "package main\n\n"},
                        "block-2": {
                            "content": 'func main() {\n    fmt.Println("Hello")\n}\n\n'
                        },
                        "block-3": {
                            "content": "type Point struct {\n    x int\n    y int\n}\n"
                        },
                    },
                    "total_lines": 9,
                    "read_time": time.time(),
                    "file_mtime": file_mtime,
                }
            }

            def get_user_data_side_effect(key):
                if key == "read_code_cache":
                    return cache
                return None

            mock_agent.get_user_data.side_effect = get_user_data_side_effect

            # 编辑文件
            result = tool.execute(
                {
                    "files": [
                        {
                            "file_path": filepath,
                            "diffs": [
                                {
                                    "block_id": "block-2",
                                    "action": "insert_after",
                                    "content": '    fmt.Println("World")\n',
                                }
                            ],
                        }
                    ],
                    "agent": mock_agent,
                }
            )

            assert result["success"] is True

            # 验证文件已更新
            with open(filepath, "r") as f:
                content = f.read()
                assert "World" in content
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)
            if os.path.exists(filepath + ".bak"):
                os.unlink(filepath + ".bak")

    def test_edit_restore_from_cache_after_edit(self, tool, mock_agent):
        """测试编辑后从缓存恢复文件"""
        original_content = """def test():
    return 1
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(original_content)
            filepath = f.name

        try:
            abs_path = os.path.abspath(filepath)
            file_mtime = os.path.getmtime(abs_path)

            # 创建初始缓存（新格式）
            cache = {
                abs_path: {
                    "id_list": ["block-1"],
                    "blocks": {
                        "block-1": {"content": "def test():\n    return 1\n"},
                    },
                    "total_lines": 2,
                    "read_time": time.time(),
                    "file_mtime": file_mtime,
                }
            }

            def get_user_data_side_effect(key):
                if key == "read_code_cache":
                    return cache
                return None

            mock_agent.get_user_data.side_effect = get_user_data_side_effect

            # 编辑文件
            result = tool.execute(
                {
                    "files": [
                        {
                            "file_path": filepath,
                            "diffs": [
                                {
                                    "block_id": "block-1",
                                    "action": "replace",
                                    "content": "def test():\n    return 999\n",
                                }
                            ],
                        }
                    ],
                    "agent": mock_agent,
                }
            )

            assert result["success"] is True

            # 从更新后的缓存恢复（缓存会被修改）
            final_cache = cache  # 直接使用被修改的cache字典
            if final_cache and abs_path in final_cache:
                cache_info = final_cache[abs_path]
                restored = EditFileTool._restore_file_from_cache(cache_info)

                # 验证恢复的内容包含修改后的内容
                assert "return 999" in restored
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)
            if os.path.exists(filepath + ".bak"):
                os.unlink(filepath + ".bak")

    def test_edit_multiple_languages_round_trip(self, tool, mock_agent):
        """测试多种语言的完整编辑往返"""
        languages = [
            (
                ".py",
                """def func():
    pass
""",
            ),
            (
                ".c",
                """void func() {
}
""",
            ),
            (
                ".java",
                """public void func() {
}
""",
            ),
            (
                ".rs",
                """fn func() {
}
""",
            ),
            (
                ".go",
                """func func() {
}
""",
            ),
        ]

        for suffix, content in languages:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=suffix, delete=False
            ) as f:
                f.write(content)
                filepath = f.name

            try:
                abs_path = os.path.abspath(filepath)
                file_mtime = os.path.getmtime(abs_path)

                # 创建缓存（新格式）
                cache = {
                    abs_path: {
                        "id_list": ["block-1"],
                        "blocks": {
                            "block-1": {"content": content},
                        },
                        "total_lines": len(content.split("\n")),
                        "read_time": time.time(),
                        "file_mtime": file_mtime,
                    }
                }

                def get_user_data_side_effect(key):
                    if key == "read_code_cache":
                        return cache
                    return None

                mock_agent.get_user_data.side_effect = get_user_data_side_effect

                # 编辑文件
                result = tool.execute(
                    {
                        "files": [
                            {
                                "file_path": filepath,
                                "diffs": [
                                    {
                                        "block_id": "block-1",
                                        "action": "replace",
                                        "content": content.replace(
                                            "func", "modified_func"
                                        ),
                                    }
                                ],
                            }
                        ],
                        "agent": mock_agent,
                    }
                )

                assert result["success"] is True

                # 验证文件已更新
                with open(filepath, "r") as f:
                    file_content = f.read()
                    assert "modified_func" in file_content
            finally:
                if os.path.exists(filepath):
                    os.unlink(filepath)
                if os.path.exists(filepath + ".bak"):
                    os.unlink(filepath + ".bak")

    def test_restore_file_from_cache_with_file_ends_with_newline(self, tool):
        """测试从缓存恢复文件时，正确处理file_ends_with_newline标志（文件以换行符结尾）"""
        cache_info = {
            "id_list": ["block-1", "block-2"],
            "blocks": {
                "block-1": {"content": "def func1():\n    return 1\n"},
                "block-2": {"content": "\ndef func2():\n    return 2\n"},
            },
            "file_ends_with_newline": True,  # 文件以换行符结尾
        }

        restored = EditFileTool._restore_file_from_cache(cache_info)

        # 验证恢复的内容以换行符结尾
        assert restored.endswith("\n"), (
            "文件以换行符结尾时，恢复的内容也应该以换行符结尾"
        )
        # 验证块之间的换行符正确（block-1以\n结尾，块之间插入\n，block-2以\n开头，所以是\n\n）
        assert (
            "return 1\n\n\ndef func2()" in restored
            or "return 1\n\ndef func2()" in restored
        )
        # 验证最后有换行符
        assert restored[-1] == "\n"

    def test_restore_file_from_cache_without_file_ends_with_newline(self, tool):
        """测试从缓存恢复文件时，正确处理file_ends_with_newline标志（文件不以换行符结尾）"""
        cache_info = {
            "id_list": ["block-1", "block-2"],
            "blocks": {
                "block-1": {"content": "def func1():\n    return 1\n"},
                "block-2": {
                    "content": "\ndef func2():\n    return 2"
                },  # 注意：最后没有换行符
            },
            "file_ends_with_newline": False,  # 文件不以换行符结尾
        }

        restored = EditFileTool._restore_file_from_cache(cache_info)

        # 验证恢复的内容不以换行符结尾
        assert not restored.endswith("\n"), (
            "文件不以换行符结尾时，恢复的内容也不应该以换行符结尾"
        )
        # 验证块之间的换行符正确（block-1以\n结尾，块之间插入\n，block-2以\n开头，所以是\n\n）
        assert (
            "return 1\n\n\ndef func2()" in restored
            or "return 1\n\ndef func2()" in restored
        )
        # 验证最后没有换行符
        assert restored[-1] != "\n"
        assert restored.endswith("return 2")

    def test_restore_file_from_cache_blocks_with_newlines(self, tool):
        """测试从缓存恢复文件时，块之间正确插入换行符"""
        cache_info = {
            "id_list": ["block-1", "block-2", "block-3"],
            "blocks": {
                "block-1": {"content": "first block"},
                "block-2": {"content": "second block"},
                "block-3": {"content": "third block"},
            },
            "file_ends_with_newline": True,
        }

        restored = EditFileTool._restore_file_from_cache(cache_info)

        # 验证块之间都有换行符
        assert "first block\nsecond block" in restored
        assert "second block\nthird block" in restored
        # 验证最后有换行符
        assert restored.endswith("\n")

    def test_restore_file_from_cache_single_block_with_newline(self, tool):
        """测试单个块时，根据file_ends_with_newline决定是否添加换行符"""
        # 文件以换行符结尾
        cache_info1 = {
            "id_list": ["block-1"],
            "blocks": {
                "block-1": {"content": "single block content"},
            },
            "file_ends_with_newline": True,
        }
        restored1 = EditFileTool._restore_file_from_cache(cache_info1)
        assert restored1.endswith("\n")
        assert restored1 == "single block content\n"

        # 文件不以换行符结尾
        cache_info2 = {
            "id_list": ["block-1"],
            "blocks": {
                "block-1": {"content": "single block content"},
            },
            "file_ends_with_newline": False,
        }
        restored2 = EditFileTool._restore_file_from_cache(cache_info2)
        assert not restored2.endswith("\n")
        assert restored2 == "single block content"

    def test_restore_file_from_cache_preserves_newlines_after_edit(
        self, tool, mock_agent
    ):
        """测试编辑后从缓存恢复时，换行符应该正确保留"""
        original_content = "def func1():\n    return 1\n\ndef func2():\n    return 2\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(original_content)
            filepath = f.name

        try:
            abs_path = os.path.abspath(filepath)
            file_mtime = os.path.getmtime(abs_path)

            # 创建缓存，包含file_ends_with_newline标志
            cache = {
                abs_path: {
                    "id_list": ["block-1", "block-2"],
                    "blocks": {
                        "block-1": {"content": "def func1():\n    return 1\n"},
                        "block-2": {"content": "\ndef func2():\n    return 2\n"},
                    },
                    "total_lines": 6,
                    "read_time": time.time(),
                    "file_mtime": file_mtime,
                    "file_ends_with_newline": True,  # 文件以换行符结尾
                }
            }

            def get_user_data_side_effect(key):
                if key == "read_code_cache":
                    return cache
                return None

            mock_agent.get_user_data.side_effect = get_user_data_side_effect

            # 编辑文件
            result = tool.execute(
                {
                    "files": [
                        {
                            "file_path": filepath,
                            "diffs": [
                                {
                                    "block_id": "block-1",
                                    "action": "replace",
                                    "content": "def func1():\n    return 999\n",
                                }
                            ],
                        }
                    ],
                    "agent": mock_agent,
                }
            )

            assert result["success"] is True

            # 从更新后的缓存恢复
            final_cache = cache[abs_path]
            restored = EditFileTool._restore_file_from_cache(final_cache)

            # 验证恢复的内容以换行符结尾
            assert restored.endswith("\n"), "编辑后恢复的内容应该保留文件末尾的换行符"
            # 验证块之间的换行符正确（block-1以\n结尾，块之间插入\n，block-2以\n开头，所以是\n\n）
            assert (
                "return 999\n\n\ndef func2()" in restored
                or "return 999\n\ndef func2()" in restored
            )
            # 验证修改后的内容存在
            assert "return 999" in restored

        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)
            if os.path.exists(filepath + ".bak"):
                os.unlink(filepath + ".bak")

    def test_restore_file_from_cache_without_file_ends_with_newline_flag(self, tool):
        """测试缓存中没有file_ends_with_newline标志时的默认行为（向后兼容）"""
        # 旧格式的缓存（没有file_ends_with_newline字段）
        cache_info = {
            "id_list": ["block-1", "block-2"],
            "blocks": {
                "block-1": {"content": "first block"},
                "block-2": {"content": "second block"},
            },
            # 没有 file_ends_with_newline 字段
        }

        restored = EditFileTool._restore_file_from_cache(cache_info)

        # 默认行为：非最后一个块之间添加换行符，最后一个块不添加换行符
        assert "first block\nsecond block" in restored
        assert not restored.endswith("\n"), (
            "没有file_ends_with_newline标志时，默认不以换行符结尾"
        )

    def test_restore_file_from_cache_complex_newline_scenarios(self, tool):
        """测试复杂的换行符场景"""
        # 场景1：多个块，文件以换行符结尾
        cache_info1 = {
            "id_list": ["block-1", "block-2", "block-3"],
            "blocks": {
                "block-1": {"content": "line1\nline2"},
                "block-2": {"content": "\nline3\nline4"},
                "block-3": {"content": "\nline5\nline6"},
            },
            "file_ends_with_newline": True,
        }
        restored1 = EditFileTool._restore_file_from_cache(cache_info1)
        assert restored1.endswith("\n")
        assert "line2\n\nline3" in restored1  # 块之间应该有换行符
        assert "line4\n\nline5" in restored1
        assert "line6\n" in restored1  # 最后应该有换行符

        # 场景2：多个块，文件不以换行符结尾
        cache_info2 = {
            "id_list": ["block-1", "block-2"],
            "blocks": {
                "block-1": {"content": "line1\nline2"},
                "block-2": {"content": "\nline3\nline4"},  # 最后没有换行符
            },
            "file_ends_with_newline": False,
        }
        restored2 = EditFileTool._restore_file_from_cache(cache_info2)
        assert not restored2.endswith("\n")
        assert "line2\n\nline3" in restored2
        assert restored2.endswith("line4")

    def test_cache_copy_includes_file_ends_with_newline(self, tool, mock_agent):
        """测试创建缓存副本时，file_ends_with_newline字段被正确复制"""
        original_content = "def test():\n    pass\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(original_content)
            filepath = f.name

        try:
            abs_path = os.path.abspath(filepath)
            file_mtime = os.path.getmtime(abs_path)

            # 创建包含file_ends_with_newline的缓存
            cache = {
                abs_path: {
                    "id_list": ["block-1"],
                    "blocks": {
                        "block-1": {"content": "def test():\n    pass\n"},
                    },
                    "total_lines": 2,
                    "read_time": time.time(),
                    "file_mtime": file_mtime,
                    "file_ends_with_newline": True,
                }
            }

            def get_user_data_side_effect(key):
                if key == "read_code_cache":
                    return cache
                return None

            mock_agent.get_user_data.side_effect = get_user_data_side_effect

            # 执行编辑操作（这会创建缓存副本）
            result = tool.execute(
                {
                    "files": [
                        {
                            "file_path": filepath,
                            "diffs": [
                                {
                                    "block_id": "block-1",
                                    "action": "replace",
                                    "content": "def test():\n    return 42\n",
                                }
                            ],
                        }
                    ],
                    "agent": mock_agent,
                }
            )

            assert result["success"] is True

            # 验证更新后的缓存包含file_ends_with_newline字段
            final_cache = mock_agent.get_user_data("read_code_cache")
            if final_cache and abs_path in final_cache:
                cache_info = final_cache[abs_path]
                # 验证file_ends_with_newline字段存在
                assert "file_ends_with_newline" in cache_info
                # 验证值被正确保留
                assert cache_info["file_ends_with_newline"] is True

                # 验证恢复的内容正确
                restored = EditFileTool._restore_file_from_cache(cache_info)
                assert restored.endswith("\n"), "恢复的内容应该保留换行符"

        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)
            if os.path.exists(filepath + ".bak"):
                os.unlink(filepath + ".bak")
