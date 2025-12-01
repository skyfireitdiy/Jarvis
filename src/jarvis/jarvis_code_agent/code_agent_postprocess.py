# -*- coding: utf-8 -*-
"""CodeAgent 后处理模块"""

import os
import subprocess
from typing import List

from jarvis.jarvis_code_agent.lint import get_post_commands_for_files


class PostProcessManager:
    """后处理管理器"""

    def __init__(self, root_dir: str):
        self.root_dir = root_dir

    def post_process_modified_files(self, modified_files: List[str]) -> None:
        """文件后处理（包括格式化、自动修复等）

        Args:
            modified_files: 修改的文件列表
        """
        # 获取格式化命令
        format_commands = get_post_commands_for_files(modified_files, self.root_dir)
        if not format_commands:
            return

        print("🔧 正在格式化代码...")

        # 执行格式化命令
        formatted_files = set()
        for tool_name, file_path, command in format_commands:
            try:
                # 检查文件是否存在
                abs_file_path = (
                    os.path.join(self.root_dir, file_path)
                    if not os.path.isabs(file_path)
                    else file_path
                )
                if not os.path.exists(abs_file_path):
                    continue

                # 执行格式化命令
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
                    formatted_files.add(file_path)
                    print(f"✅ 已格式化: {os.path.basename(file_path)} ({tool_name})")
                else:
                    # 格式化失败，记录但不中断流程
                    error_msg = (result.stderr or result.stdout or "").strip()
                    if error_msg:
                        print(
                            f"⚠️ 格式化失败 ({os.path.basename(file_path)}, {tool_name}): {error_msg[:200]}"
                        )
            except subprocess.TimeoutExpired:
                print(f"⚠️ 格式化超时: {os.path.basename(file_path)} ({tool_name})")
            except FileNotFoundError:
                # 工具未安装，跳过
                continue
            except Exception as e:
                # 其他错误，记录但继续
                print(
                    f"⚠️ 格式化失败 ({os.path.basename(file_path)}, {tool_name}): {str(e)[:100]}"
                )
                continue

        if formatted_files:
            print(f"✅ 已格式化 {len(formatted_files)} 个文件")
            # 暂存格式化后的文件
            try:
                for file_path in formatted_files:
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
