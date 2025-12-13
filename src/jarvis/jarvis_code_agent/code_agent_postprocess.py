"""CodeAgent 后处理模块"""

import os
import subprocess

from jarvis.jarvis_utils.output import PrettyOutput

# -*- coding: utf-8 -*-
from typing import List

from jarvis.jarvis_code_agent.after_change import get_after_change_commands_for_files


class PostProcessManager:
    """后处理管理器"""

    def __init__(self, root_dir: str):
        self.root_dir = root_dir

    def post_process_modified_files(self, modified_files: List[str]) -> None:
        """文件后处理（包括格式化、自动修复等）

        Args:
            modified_files: 修改的文件列表
        """
        # 获取变更后处理命令
        after_change_commands = get_after_change_commands_for_files(
            modified_files, self.root_dir
        )
        if not after_change_commands:
            return

        # 执行变更后处理命令
        processed_files = set()
        for file_path, command in after_change_commands:
            # 从命令中提取工具名（第一个单词）用于日志
            tool_name = command.split()[0] if command.split() else "unknown"
            try:
                # 检查文件是否存在
                abs_file_path = (
                    os.path.join(self.root_dir, file_path)
                    if not os.path.isabs(file_path)
                    else file_path
                )
                if not os.path.exists(abs_file_path):
                    continue

                # 执行变更后处理命令
                result = subprocess.run(
                    command,
                    shell=True,
                    cwd=self.root_dir,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=300,  # 300秒超时
                )

                if result.returncode == 0:
                    processed_files.add(file_path)
                    PrettyOutput.auto_print(
                        f"✅ 已处理: {os.path.basename(file_path)} ({tool_name})"
                    )
                else:
                    # 处理失败，记录但不中断流程
                    error_msg = (result.stderr or result.stdout or "").strip()
                    if error_msg:
                        PrettyOutput.auto_print(
                            f"⚠️ 处理失败 ({os.path.basename(file_path)}, {tool_name}): {error_msg[:200]}"
                        )
            except subprocess.TimeoutExpired:
                PrettyOutput.auto_print(
                    f"⚠️ 处理超时: {os.path.basename(file_path)} ({tool_name})"
                )
            except FileNotFoundError:
                # 工具未安装，跳过
                continue
            except Exception as e:
                # 其他错误，记录但继续
                PrettyOutput.auto_print(
                    f"⚠️ 处理失败 ({os.path.basename(file_path)}, {tool_name}): {str(e)[:100]}"
                )
                continue

        if processed_files:
            PrettyOutput.auto_print(f"✅ 已处理 {len(processed_files)} 个文件")
            # 暂存处理后的文件
            try:
                for file_path in processed_files:
                    abs_file_path = (
                        os.path.join(self.root_dir, file_path)
                        if not os.path.isabs(file_path)
                        else file_path
                    )
                    if os.path.exists(abs_file_path):
                        subprocess.run(
                            ["git", "add", file_path],
                            cwd=self.root_dir,
                            check=False,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
            except Exception:
                pass
