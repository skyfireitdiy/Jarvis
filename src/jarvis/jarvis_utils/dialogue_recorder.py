#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对话记录器模块

提供对话记录和管理功能，支持多会话、JSONL格式存储、自动清理等功能。
"""

import atexit
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

from .config import get_data_dir

# 全局实例变量
_global_recorder: Optional["DialogueRecorder"] = None


class DialogueRecorder:
    """对话记录器类

    用于记录和管理对话历史，支持多会话、JSONL格式存储。

    特性：
    - 自动生成会话ID
    - JSONL格式存储，每行一个消息记录
    - 支持元数据扩展
    - 自动清理旧会话
    - 进程安全的文件写入
    """

    def __init__(self, session_id: Optional[str] = None):
        """初始化对话记录器

        Args:
            session_id: 会话ID，如果为None则使用当前会话ID
        """
        self.data_dir = Path(get_data_dir()) / "dialogues"
        self._session_id_cache: Optional[str] = None
        self.session_id = session_id or self._get_current_session_id()
        self._ensure_data_dir()
        self._register_cleanup_hook()

    def __del__(self) -> None:
        """析构函数，确保清理资源"""
        if hasattr(self, "_cleanup_registered"):
            self._unregister_cleanup_hook()

    def start_recording(self) -> str:
        """开始新的对话记录

        Returns:
            str: 新生成的会话ID
        """
        new_session_id = str(uuid.uuid4())
        return new_session_id

    def record_message(
        self, role: str, content: str, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """记录消息

        Args:
            role: 消息角色（如'user', 'assistant', 'system'）
            content: 消息内容
            metadata: 可选的元数据
        """
        record = {
            "timestamp": datetime.now().isoformat(),
            "role": role,
            "content": content,
            "metadata": metadata or {},
        }
        self._write_record(record)

    def get_session_file_path(self) -> str:
        """获取当前会话文件路径

        Returns:
            str: 当前会话文件完整路径
        """
        return str(self._get_session_path(self.session_id))

    def get_all_sessions(self) -> List[str]:
        """获取所有会话ID列表

        Returns:
            List[str]: 所有会话ID列表
        """
        if not self.data_dir.exists():
            return []

        session_files = self.data_dir.glob("*.jsonl")
        sessions = []
        for file_path in session_files:
            session_id = file_path.stem
            if file_path.is_file() and session_id:
                sessions.append(session_id)

        return sorted(sessions)

    def read_session(self, session_id: str) -> List[Dict[str, Any]]:
        """读取指定会话内容

        Args:
            session_id: 会话ID

        Returns:
            List[Dict[str, Any]]: 会话消息列表
        """
        file_path = self._get_session_path(session_id)
        if not file_path.exists():
            return []

        messages = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            message = json.loads(line)
                            messages.append(message)
                        except json.JSONDecodeError:
                            continue
        except Exception:
            pass
        return messages

    def cleanup_session(self, session_id: Optional[str] = None) -> None:
        """清理指定会话文件

        Args:
            session_id: 会话ID，如果为None则清理当前会话
        """
        session_to_cleanup = session_id or self.session_id
        file_path = self._get_session_path(session_to_cleanup)

        if file_path.exists():
            try:
                file_path.unlink()
            except Exception:
                pass

    def cleanup_all_sessions(self) -> None:
        """清理所有会话文件"""
        if not self.data_dir.exists():
            return

        session_files = list(self.data_dir.glob("*.jsonl"))
        if not session_files:
            return

        for file_path in session_files:
            try:
                file_path.unlink()
            except Exception:
                pass

    def get_session_count(self) -> int:
        """获取总会话数量

        Returns:
            int: 总会话数量
        """
        return len(self.get_all_sessions())

    def _ensure_data_dir(self) -> None:
        """确保数据目录存在"""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def _get_current_session_id(self) -> str:
        """获取当前会话ID"""
        # 从环境变量或配置中获取当前会话ID
        # 如果没有则生成一个新的
        if self._session_id_cache is not None:
            return self._session_id_cache

        # 检查是否有现有的会话文件
        existing_sessions = self.get_all_sessions()
        if existing_sessions:
            # 使用最新的会话
            session_id = existing_sessions[-1]
            self._session_id_cache = session_id
            return session_id

        # 生成新的会话ID
        new_session_id = str(uuid.uuid4())
        self._session_id_cache = new_session_id
        return new_session_id

    def _write_record(self, record: Dict[str, Any]) -> None:
        """写入单条记录到文件"""
        file_path = self._get_session_path(self.session_id)

        try:
            with open(file_path, "a", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False)
                f.write("\n")
        except Exception:
            pass

    def _get_session_path(self, session_id: str) -> Path:
        """获取会话文件路径"""
        return self.data_dir / f"{session_id}.jsonl"

    def _register_cleanup_hook(self) -> None:
        """注册atexit清理钩子"""
        if not hasattr(self, "_cleanup_registered"):
            atexit.register(self._cleanup_on_exit)
            self._cleanup_registered = True

    def _unregister_cleanup_hook(self) -> None:
        """注销atexit清理钩子"""
        if hasattr(self, "_cleanup_registered"):
            try:
                atexit.unregister(self._cleanup_on_exit)
            except ValueError:
                # 钩子可能已被注销或从未注册
                pass
            del self._cleanup_registered

    def _cleanup_on_exit(self) -> None:
        """进程退出时的清理函数

        确保在进程正常和异常退出时清理当前会话文件
        """
        try:
            # 只清理当前会话，避免影响其他会话
            self.cleanup_session()
        except Exception:
            # 清理失败时不抛出异常，避免影响进程退出
            pass


def get_global_recorder() -> DialogueRecorder:
    """获取全局单例对话记录器

    Returns:
        DialogueRecorder: 全局对话记录器实例
    """
    global _global_recorder
    if _global_recorder is None:
        _global_recorder = DialogueRecorder()
    return _global_recorder


def record_user_message(
    content: str, metadata: Optional[Dict[str, Any]] = None
) -> None:
    """便捷函数：记录用户消息

    Args:
        content: 消息内容
        metadata: 可选元数据
    """
    recorder = get_global_recorder()
    recorder.record_message("user", content, metadata)


def record_assistant_message(
    content: str, metadata: Optional[Dict[str, Any]] = None
) -> None:
    """便捷函数：记录助手消息

    Args:
        content: 消息内容
        metadata: 可选元数据
    """
    recorder = get_global_recorder()
    recorder.record_message("assistant", content, metadata)


def get_current_session_path() -> str:
    """便捷函数：获取当前会话文件路径

    Returns:
        str: 当前会话文件路径
    """
    recorder = get_global_recorder()
    return recorder.get_session_file_path()


# 在模块导入时自动初始化和注册清理钩子
_global_recorder = get_global_recorder()
