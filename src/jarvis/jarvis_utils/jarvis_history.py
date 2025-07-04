import glob
import os
from datetime import datetime
from typing import Dict, List, Optional

import yaml  # type: ignore


class JarvisHistory:
    def __init__(self):
        self.records: List[Dict[str, str]] = []
        self.current_file: Optional[str] = None

    def start_record(self, data_dir: str) -> None:
        """启动一个新的记录会话，使用带时间戳的文件名"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_file = os.path.join(data_dir, f"history_{timestamp}.yaml")
        self.records = []

    def append_msg(self, role: str, msg: str) -> None:
        """向当前记录会话添加一条消息"""
        if not self.current_file:
            raise RuntimeError("Recording not started. Call start_record first.")
        self.records.append({"role": role, "message": msg})

    def save_history(self, filename: str) -> None:
        """将记录的消息保存到YAML文件"""

        # 如果记录为空则跳过保存
        if not self.records:
            return

        # 确保目录存在
        os.makedirs(os.path.dirname(filename), exist_ok=True)

        with open(filename, "w") as f:
            yaml.safe_dump({"conversation": self.records}, f, allow_unicode=True)

    def stop_record(self) -> None:
        """停止记录会话并保存消息"""
        if not self.current_file:
            return

        if self.records:  # 仅在对话不为空时保存
            self.save_history(self.current_file)
        self.current_file = None
        self.records = []

    @staticmethod
    def export_history_to_markdown(
        input_dir: str, output_file: str, max_files: Optional[int] = None
    ) -> None:
        """
        将目录中的所有历史文件导出为单个markdown文件

        参数:
            input_dir: 包含历史YAML文件的目录
            output_file: 输出markdown文件的路径
            max_files: 要导出的历史文件最大数量(None表示全部)
        """
        # 查找目录中的所有历史文件
        history_files = glob.glob(os.path.join(input_dir, "history_*.yaml"))

        if not history_files:
            return

        # 按修改时间排序(最新的在前)并限制最大文件数
        history_files.sort(key=os.path.getmtime, reverse=True)
        if max_files is not None:
            history_files = history_files[:max_files]

        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        with open(output_file, "w", encoding="utf-8") as md_file:
            md_file.write("# Jarvis Conversation History\n\n")

            for history_file in sorted(history_files):
                # 读取YAML文件
                with open(history_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                if not data or "conversation" not in data:
                    continue

                # 从文件名中提取时间戳并写入文件头
                timestamp = os.path.basename(history_file)[
                    8:-5
                ]  # 从"history_YYYYMMDD_HHMMSS.yaml"中提取时间戳
                md_file.write(
                    f"## Conversation at {timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]} "
                    f"{timestamp[9:11]}:{timestamp[11:13]}:{timestamp[13:15]}\n\n"
                )

                # 写入对话消息
                for msg in data["conversation"]:
                    md_file.write(f"**{msg['role']}**: {msg['message']}\n\n")

                md_file.write("\n---\n\n")
