#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对话记录器单元测试

测试DialogueRecorder类的所有公共方法和功能
"""

import json
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from src.jarvis.jarvis_utils.dialogue_recorder import DialogueRecorder


class TestDialogueRecorder:
    """DialogueRecorder类的测试套件"""

    @pytest.fixture
    def temp_data_dir(self):
        """创建临时数据目录"""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def recorder(self, temp_data_dir):
        """创建带有临时数据目录的DialogueRecorder实例"""
        with patch(
            "src.jarvis.jarvis_utils.dialogue_recorder.get_data_dir"
        ) as mock_get_data_dir:
            mock_get_data_dir.return_value = str(temp_data_dir)
            yield DialogueRecorder()

    def test_init_without_session_id(self, temp_data_dir):
        """测试无会话ID时的初始化"""
        with patch(
            "src.jarvis.jarvis_utils.dialogue_recorder.get_data_dir"
        ) as mock_get_data_dir:
            mock_get_data_dir.return_value = str(temp_data_dir)
            recorder = DialogueRecorder()

            assert recorder.session_id is not None
            assert len(recorder.session_id) > 0
            assert (temp_data_dir / "dialogues").exists()

    def test_init_with_session_id(self, temp_data_dir):
        """测试指定会话ID时的初始化"""
        session_id = "test-session-123"
        with patch(
            "src.jarvis.jarvis_utils.dialogue_recorder.get_data_dir"
        ) as mock_get_data_dir:
            mock_get_data_dir.return_value = str(temp_data_dir)
            recorder = DialogueRecorder(session_id=session_id)

            assert recorder.session_id == session_id
            assert (temp_data_dir / "dialogues").exists()

    def test_start_recording(self, recorder):
        """测试开始新的对话记录"""
        new_session_id = recorder.start_recording()

        assert new_session_id is not None
        assert len(new_session_id) > 0
        # 验证是有效的UUID格式
        try:
            uuid.UUID(new_session_id)
        except ValueError:
            pytest.fail("start_recording should return a valid UUID")

    def test_record_message(self, recorder, temp_data_dir):
        """测试记录消息"""
        role = "user"
        content = "Hello, world!"
        metadata = {"test": True, "version": "1.0"}

        recorder.record_message(role, content, metadata)

        # 验证文件被创建
        session_file = temp_data_dir / "dialogues" / f"{recorder.session_id}.jsonl"
        assert session_file.exists()

        # 验证内容
        with open(session_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            assert len(lines) == 1

            record = json.loads(lines[0])
            assert record["role"] == role
            assert record["content"] == content
            assert record["metadata"] == metadata
            assert "timestamp" in record
            assert isinstance(record["timestamp"], str)

    def test_record_message_without_metadata(self, recorder, temp_data_dir):
        """测试记录消息（无元数据）"""
        role = "assistant"
        content = "How can I help you?"

        recorder.record_message(role, content)

        session_file = temp_data_dir / "dialogues" / f"{recorder.session_id}.jsonl"
        with open(session_file, "r", encoding="utf-8") as f:
            record = json.loads(f.readline())
            assert record["role"] == role
            assert record["content"] == content
            assert record["metadata"] == {}

    def test_get_session_file_path(self, recorder, temp_data_dir):
        """测试获取会话文件路径"""
        expected_path = str(
            temp_data_dir / "dialogues" / f"{recorder.session_id}.jsonl"
        )
        actual_path = recorder.get_session_file_path()

        assert actual_path == expected_path

    def test_get_all_sessions_empty(self, recorder):
        """测试获取所有会话（空）"""
        sessions = recorder.get_all_sessions()
        assert sessions == []

    def test_get_all_sessions_with_files(self, recorder, temp_data_dir):
        """测试获取所有会话（有文件）"""
        # 创建测试会话文件
        dialogues_dir = temp_data_dir / "dialogues"
        dialogues_dir.mkdir(exist_ok=True)

        session_ids = ["session1", "session2", "session3"]
        for session_id in session_ids:
            file_path = dialogues_dir / f"{session_id}.jsonl"
            file_path.touch()

        sessions = recorder.get_all_sessions()
        assert len(sessions) == 3
        assert set(sessions) == set(session_ids)

    def test_read_session_empty(self, recorder):
        """测试读取空会话"""
        non_existent_session = "non-existent-session"
        messages = recorder.read_session(non_existent_session)
        assert messages == []

    def test_read_session_with_content(self, recorder, temp_data_dir):
        """测试读取有内容的会话"""
        # 创建测试数据
        test_messages = [
            {
                "timestamp": "2024-01-01T00:00:00",
                "role": "user",
                "content": "Hi",
                "metadata": {},
            },
            {
                "timestamp": "2024-01-01T00:00:01",
                "role": "assistant",
                "content": "Hello",
                "metadata": {"type": "greeting"},
            },
        ]

        session_file = temp_data_dir / "dialogues" / f"{recorder.session_id}.jsonl"
        with open(session_file, "w", encoding="utf-8") as f:
            for msg in test_messages:
                json.dump(msg, f)
                f.write("\n")

        messages = recorder.read_session(recorder.session_id)
        assert len(messages) == 2
        assert messages == test_messages

    def test_read_session_with_invalid_json(self, recorder, temp_data_dir):
        """测试读取包含无效JSON的会话"""
        session_file = temp_data_dir / "dialogues" / f"{recorder.session_id}.jsonl"
        with open(session_file, "w", encoding="utf-8") as f:
            f.write('{"valid": "json"}\n')
            f.write("invalid json line\n")
            f.write('{"another": "valid"}\n')

        messages = recorder.read_session(recorder.session_id)
        assert len(messages) == 2  # 只有有效的JSON行被读取

    def test_cleanup_session(self, recorder, temp_data_dir):
        """测试清理指定会话"""
        # 创建会话文件
        session_file = temp_data_dir / "dialogues" / f"{recorder.session_id}.jsonl"
        session_file.touch()
        assert session_file.exists()

        recorder.cleanup_session()
        assert not session_file.exists()

    def test_cleanup_session_specific(self, recorder, temp_data_dir):
        """测试清理特定会话"""
        target_session = "specific-session"
        target_file = temp_data_dir / "dialogues" / f"{target_session}.jsonl"
        target_file.touch()
        assert target_file.exists()

        # 创建其他会话文件
        other_file = temp_data_dir / "dialogues" / "other-session.jsonl"
        other_file.touch()

        recorder.cleanup_session(target_session)
        assert not target_file.exists()
        assert other_file.exists()  # 其他文件不受影响

    def test_cleanup_all_sessions(self, recorder, temp_data_dir):
        """测试清理所有会话"""
        # 创建多个会话文件
        dialogues_dir = temp_data_dir / "dialogues"
        dialogues_dir.mkdir(exist_ok=True)

        session_files = [
            dialogues_dir / "session1.jsonl",
            dialogues_dir / "session2.jsonl",
            dialogues_dir / "session3.jsonl",
        ]

        for file_path in session_files:
            file_path.touch()
            assert file_path.exists()

        recorder.cleanup_all_sessions()

        for file_path in session_files:
            assert not file_path.exists()

    def test_get_session_count_empty(self, recorder):
        """测试获取会话数量（空）"""
        assert recorder.get_session_count() == 0

    def test_get_session_count_with_sessions(self, recorder, temp_data_dir):
        """测试获取会话数量（有会话）"""
        # 创建测试会话文件
        dialogues_dir = temp_data_dir / "dialogues"
        dialogues_dir.mkdir(exist_ok=True)

        for i in range(3):
            (dialogues_dir / f"session{i}.jsonl").touch()

        assert recorder.get_session_count() == 3

    def test_multiple_messages_in_session(self, recorder, temp_data_dir):
        """测试一个会话中的多条消息"""
        messages = [
            ("user", "Hello"),
            ("assistant", "Hi there!"),
            ("user", "How are you?"),
            ("assistant", "I'm doing well, thank you!"),
        ]

        for role, content in messages:
            recorder.record_message(role, content)

        session_file = temp_data_dir / "dialogues" / f"{recorder.session_id}.jsonl"
        with open(session_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            assert len(lines) == 4

            for i, line in enumerate(lines):
                record = json.loads(line)
                expected_role, expected_content = messages[i]
                assert record["role"] == expected_role
                assert record["content"] == expected_content

    def test_session_persistence(self, temp_data_dir):
        """测试会话持久化"""
        session_id = "persistent-session"

        # 第一个记录器记录消息
        with patch(
            "src.jarvis.jarvis_utils.dialogue_recorder.get_data_dir"
        ) as mock_get_data_dir:
            mock_get_data_dir.return_value = str(temp_data_dir)
            recorder1 = DialogueRecorder(session_id)
            recorder1.record_message("user", "Persistent message")

        # 第二个记录器读取消息
        with patch(
            "src.jarvis.jarvis_utils.dialogue_recorder.get_data_dir"
        ) as mock_get_data_dir:
            mock_get_data_dir.return_value = str(temp_data_dir)
            recorder2 = DialogueRecorder(session_id)
            messages = recorder2.read_session(session_id)

        assert len(messages) == 1
        assert messages[0]["content"] == "Persistent message"

    def test_unicode_content(self, recorder, temp_data_dir):
        """测试Unicode内容处理"""
        unicode_content = "你好，世界！🌍 こんにちは 세계"

        recorder.record_message("user", unicode_content)

        session_file = temp_data_dir / "dialogues" / f"{recorder.session_id}.jsonl"
        with open(session_file, "r", encoding="utf-8") as f:
            record = json.loads(f.readline())
            assert record["content"] == unicode_content

    def test_large_metadata(self, recorder, temp_data_dir):
        """测试大元数据处理"""
        large_metadata = {
            "nested": {"deep": {"very": {"deep": "structure"}}},
            "list": [1, 2, 3, "string", {"nested": True}],
            "null_value": None,
            "boolean": True,
        }

        recorder.record_message("system", "Test", large_metadata)

        session_file = temp_data_dir / "dialogues" / f"{recorder.session_id}.jsonl"
        with open(session_file, "r", encoding="utf-8") as f:
            record = json.loads(f.readline())
            assert record["metadata"] == large_metadata

    def test_cleanup_hook_registration(self, temp_data_dir):
        """测试清理钩子的注册"""

        with patch(
            "src.jarvis.jarvis_utils.dialogue_recorder.get_data_dir"
        ) as mock_get_data_dir:
            mock_get_data_dir.return_value = str(temp_data_dir)

            # 创建记录器实例
            recorder = DialogueRecorder()

            # 验证清理钩子已注册
            assert hasattr(recorder, "_cleanup_registered")
            assert recorder._cleanup_registered is True

    def test_cleanup_on_exit(self, temp_data_dir):
        """测试进程退出时的清理功能"""
        session_id = "cleanup-test-session"

        with patch(
            "src.jarvis.jarvis_utils.dialogue_recorder.get_data_dir"
        ) as mock_get_data_dir:
            mock_get_data_dir.return_value = str(temp_data_dir)

            # 创建记录器并记录消息
            recorder = DialogueRecorder(session_id)
            recorder.record_message("user", "test message")

            # 验证文件已创建
            session_file = temp_data_dir / "dialogues" / f"{session_id}.jsonl"
            assert session_file.exists()

            # 手动调用清理函数（模拟进程退出）
            recorder._cleanup_on_exit()

            # 验证文件已被清理
            assert not session_file.exists()

    def test_cleanup_error_handling(self, temp_data_dir):
        """测试清理过程中的异常处理"""
        import io
        import sys

        session_id = "exception-test-session"

        with patch(
            "src.jarvis.jarvis_utils.dialogue_recorder.get_data_dir"
        ) as mock_get_data_dir:
            mock_get_data_dir.return_value = str(temp_data_dir)

            recorder = DialogueRecorder(session_id)

            # 重定向stdout以捕获错误消息
            captured_output = io.StringIO()
            sys_stdout_backup = sys.stdout
            sys.stdout = captured_output

            try:
                # 创建会话文件
                session_file = temp_data_dir / "dialogues" / f"{session_id}.jsonl"
                session_file.touch()
                assert session_file.exists()

                # 手动调用清理函数，应该正常处理
                recorder._cleanup_on_exit()

                # 恢复stdout
                sys.stdout = sys_stdout_backup

                # 验证文件已被清理
                assert not session_file.exists()

            finally:
                # 确保stdout被恢复
                sys.stdout = sys_stdout_backup
