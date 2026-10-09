# -*- coding: utf-8 -*-
"""MemoryTool 存储前压缩（_compress_memory_content）单测"""

from unittest.mock import patch

from jarvis.jarvis_tools.memory import MemoryTool


def _make_tool():
    return MemoryTool()


class TestCompressMemoryContent:
    """测试 _compress_memory_content 的规则式摘要压缩"""

    def _call(self, content):
        return _make_tool()._compress_memory_content(content)

    def test_short_content_unchanged(self):
        """未超阈值内容原样返回"""
        content = "这是一个不算太长的记忆内容，用于测试压缩逻辑是否正常工作。"
        with patch(
            "jarvis.jarvis_utils.config.get_memory_compress_threshold",
            return_value=2000,
        ):
            assert self._call(content) == content

    def test_empty_content(self):
        """空内容原样返回（纯空白会被 strip）"""
        assert self._call("") == ""
        assert self._call("   ") == ""

    def test_long_content_compressed(self):
        """超长内容被压缩，且保留关键信号句"""
        # 构造超过阈值的长内容
        filler = "这是一段无关紧要的填充文本，用来把内容撑长到超过压缩阈值，本身没有太多信息量。"
        long_content = filler * 100
        # 加入高信号句子
        signal = "重要决策：采用双字段正交的记忆维度设计，不兼容旧数据。"
        content = long_content + signal + long_content

        with patch(
            "jarvis.jarvis_utils.config.get_memory_compress_threshold", return_value=10
        ):
            result = self._call(content)

        # 压缩后应包含高信号句子
        assert "重要决策" in result
        assert "双字段正交" in result
        # 压缩后应比原文短
        assert len(result) < len(content)

    def test_compress_keeps_head_and_tail(self):
        """压缩保留开头与结尾句子"""
        head = "开头背景：本次任务目标是增强记忆系统。"
        tail = "结尾结论：方案可行，待实施。"
        filler = "中间填充内容，没有太多信息量。" * 50
        content = head + filler + tail

        with patch(
            "jarvis.jarvis_utils.config.get_memory_compress_threshold", return_value=10
        ):
            result = self._call(content)

        assert "开头背景" in result
        assert "结尾结论" in result


class TestSaveSingleMemoryCompress:
    """测试 _save_single_memory 接入压缩后的行为"""

    def _call(self, memory_data):
        return _make_tool()._save_single_memory(memory_data)

    def test_long_content_compressed_with_original(self):
        """超长内容压缩后存储，且保留 original_content"""
        filler = "这是一段无关紧要的填充文本，用来把内容撑长到超过压缩阈值，本身没有太多信息量。"
        content = filler * 100 + "关键结论：压缩功能已验证。"

        with (
            patch(
                "jarvis.jarvis_utils.config.is_enable_memory_compress",
                return_value=True,
            ),
            patch(
                "jarvis.jarvis_utils.config.get_memory_compress_threshold",
                return_value=10,
            ),
        ):
            result = self._call(
                {
                    "memory_type": "project",
                    "nature": "long_term",
                    "content": content,
                }
            )

        assert result["memory_id"] is not None
        # 读回文件确认 original_content 保留
        import json
        from pathlib import Path

        file_path = Path(result["file_path"])
        saved = json.loads(file_path.read_text(encoding="utf-8"))
        assert saved["original_content"] == content
        assert len(saved["content"]) < len(content)
        assert "关键结论" in saved["content"]

    def test_compress_disabled_no_original(self):
        """压缩关闭时内容原样存储，无 original_content"""
        filler = "填充内容。" * 100
        content = filler

        with (
            patch(
                "jarvis.jarvis_utils.config.is_enable_memory_compress",
                return_value=False,
            ),
        ):
            result = self._call(
                {
                    "memory_type": "project",
                    "nature": "long_term",
                    "content": content,
                }
            )

        import json
        from pathlib import Path

        file_path = Path(result["file_path"])
        saved = json.loads(file_path.read_text(encoding="utf-8"))
        assert "original_content" not in saved
        assert saved["content"] == content
