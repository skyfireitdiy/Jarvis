# -*- coding: utf-8 -*-
"""工具分享管理模块"""
import os
import glob
import shutil
from typing import List, Dict, Any, Set

import typer

from jarvis.jarvis_agent import OutputType, PrettyOutput, user_confirm
from jarvis.jarvis_agent.share_manager import ShareManager
from jarvis.jarvis_utils.config import get_central_tool_repo, get_data_dir


class ToolShareManager(ShareManager):
    """工具分享管理器"""

    def __init__(self):
        central_repo = get_central_tool_repo()
        if not central_repo:
            PrettyOutput.print(
                "错误：未配置中心工具仓库（JARVIS_CENTRAL_TOOL_REPO）",
                OutputType.ERROR,
            )
            PrettyOutput.print(
                "请在配置文件中设置中心工具仓库的Git地址", OutputType.INFO
            )
            raise typer.Exit(code=1)

        super().__init__(central_repo, "central_tool_repo")

    def get_resource_type(self) -> str:
        """获取资源类型名称"""
        return "工具"

    def format_resource_display(self, resource: Dict[str, Any]) -> str:
        """格式化资源显示"""
        return f"{resource['tool_name']} ({resource['filename']})"

    def get_existing_resources(self) -> Set[str]:
        """获取中心仓库中已有的工具文件名"""
        existing_tools = set()
        for filepath in glob.glob(os.path.join(self.repo_path, "*.py")):
            existing_tools.add(os.path.basename(filepath))
        return existing_tools

    def get_local_resources(self) -> List[Dict[str, Any]]:
        """获取本地工具"""
        # 获取中心仓库中已有的工具文件名
        existing_tools = self.get_existing_resources()

        # 只从数据目录的tools目录获取工具
        local_tools_dir = os.path.join(get_data_dir(), "tools")
        if not os.path.exists(local_tools_dir):
            PrettyOutput.print(
                f"本地工具目录不存在: {local_tools_dir}",
                OutputType.WARNING,
            )
            return []

        # 收集本地工具文件（排除已存在的）
        tool_files = []
        for filepath in glob.glob(os.path.join(local_tools_dir, "*.py")):
            filename = os.path.basename(filepath)
            # 跳过__init__.py和已存在的文件
            if filename == "__init__.py" or filename in existing_tools:
                continue

            # 尝试获取工具名称（通过简单解析）
            tool_name = filename[:-3]  # 移除.py后缀
            tool_files.append(
                {
                    "path": filepath,
                    "filename": filename,
                    "tool_name": tool_name,
                }
            )

        return tool_files

    def share_resources(self, resources: List[Dict[str, Any]]) -> List[str]:
        """分享工具到中心仓库"""
        # 确认操作
        share_list = ["\n将要分享以下工具到中心仓库（注意：文件将被移动而非复制）："]
        for tool in resources:
            share_list.append(f"- {tool['tool_name']} ({tool['filename']})")
        PrettyOutput.print("\n".join(share_list), OutputType.WARNING)

        if not user_confirm("确认移动这些工具到中心仓库吗？（原文件将被删除）"):
            return []

        # 移动选中的工具到中心仓库
        moved_list = []
        for tool in resources:
            src_file = tool["path"]
            dst_file = os.path.join(self.repo_path, tool["filename"])
            shutil.move(src_file, dst_file)  # 使用move而不是copy
            moved_list.append(f"已移动: {tool['tool_name']}")

        return moved_list

    def run(self) -> None:
        """执行工具分享流程"""
        try:
            # 更新中心仓库
            self.update_central_repo()

            # 获取本地资源
            local_resources = self.get_local_resources()
            if not local_resources:
                PrettyOutput.print(
                    "没有找到新的工具文件（所有工具可能已存在于中心仓库）",
                    OutputType.WARNING,
                )
                return

            # 选择要分享的资源
            selected_resources = self.select_resources(local_resources)
            if not selected_resources:
                return

            # 分享资源
            moved_list = self.share_resources(selected_resources)
            if moved_list:
                # 一次性显示所有移动结果
                PrettyOutput.print("\n".join(moved_list), OutputType.SUCCESS)

                # 提交并推送
                self.commit_and_push(len(selected_resources))

                PrettyOutput.print("\n工具已成功分享到中心仓库！", OutputType.SUCCESS)
                PrettyOutput.print(
                    f"原文件已从 {os.path.join(get_data_dir(), 'tools')} 移动到中心仓库",
                    OutputType.INFO,
                )

        except Exception as e:
            PrettyOutput.print(f"分享工具时出错: {str(e)}", OutputType.ERROR)
            raise typer.Exit(code=1)
