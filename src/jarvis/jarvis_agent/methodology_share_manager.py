# -*- coding: utf-8 -*-
"""方法论分享管理模块"""
import os
import glob
import json
import shutil
from typing import List, Dict, Any

import typer

from jarvis.jarvis_agent import OutputType, PrettyOutput, user_confirm
from jarvis.jarvis_agent.share_manager import ShareManager
from jarvis.jarvis_utils.config import (
    get_central_methodology_repo,
    get_methodology_dirs,
)


class MethodologyShareManager(ShareManager):
    """方法论分享管理器"""

    def __init__(self):
        central_repo = get_central_methodology_repo()
        if not central_repo:
            PrettyOutput.print(
                "错误：未配置中心方法论仓库（JARVIS_CENTRAL_METHODOLOGY_REPO）",
                OutputType.ERROR,
            )
            PrettyOutput.print(
                "请在配置文件中设置中心方法论仓库的Git地址", OutputType.INFO
            )
            raise typer.Exit(code=1)

        super().__init__(central_repo, "central_methodology_repo")

    def get_resource_type(self) -> str:
        """获取资源类型名称"""
        return "方法论"

    def format_resource_display(self, resource: Dict[str, Any]) -> str:
        """格式化资源显示"""
        dir_name = os.path.basename(resource["directory"])
        return f"{resource['problem_type']} (来自: {dir_name})"

    def get_existing_resources(self) -> Dict[str, str]:
        """获取中心仓库中已有的方法论"""
        existing_methodologies = {}  # 存储 problem_type -> content 的映射
        for filepath in glob.glob(os.path.join(self.repo_path, "*.json")):
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    methodology = json.load(f)
                    problem_type = methodology.get("problem_type", "")
                    content = methodology.get("content", "")
                    if problem_type and content:
                        existing_methodologies[problem_type] = content
            except Exception:
                pass
        return existing_methodologies

    def get_local_resources(self) -> List[Dict[str, Any]]:
        """获取本地方法论"""
        # 获取中心仓库中已有的方法论
        existing_methodologies = self.get_existing_resources()

        # 获取所有方法论目录
        from jarvis.jarvis_utils.methodology import _get_methodology_directory

        methodology_dirs = [_get_methodology_directory()] + get_methodology_dirs()

        # 收集所有方法论文件（排除中心仓库目录和已存在的方法论）
        methodology_files = []
        seen_problem_types = set()  # 用于去重

        for directory in set(methodology_dirs):
            # 跳过中心仓库目录
            if os.path.abspath(directory) == os.path.abspath(self.repo_path):
                continue

            if not os.path.isdir(directory):
                continue

            for filepath in glob.glob(os.path.join(directory, "*.json")):
                try:
                    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                        methodology = json.load(f)
                        problem_type = methodology.get("problem_type", "")
                        content = methodology.get("content", "")

                        # 基于内容判断是否已存在于中心仓库
                        is_duplicate = False
                        if problem_type in existing_methodologies:
                            # 如果problem_type相同，比较内容
                            if (
                                content.strip()
                                == existing_methodologies[problem_type].strip()
                            ):
                                is_duplicate = True

                        # 排除已存在于中心仓库的方法论（基于内容），以及本地重复的方法论
                        if (
                            problem_type
                            and content
                            and not is_duplicate
                            and problem_type not in seen_problem_types
                        ):
                            methodology_files.append(
                                {
                                    "path": filepath,
                                    "problem_type": problem_type,
                                    "directory": directory,
                                    "methodology": methodology,
                                }
                            )
                            seen_problem_types.add(problem_type)
                except Exception:
                    pass

        return methodology_files

    def share_resources(self, resources: List[Dict[str, Any]]) -> List[str]:
        """分享方法论到中心仓库"""
        # 确认操作
        share_list = ["\n将要分享以下方法论到中心仓库："]
        for meth in resources:
            share_list.append(f"- {meth['problem_type']}")
        PrettyOutput.print("\n".join(share_list), OutputType.INFO)

        if not user_confirm("确认分享这些方法论吗？"):
            return []

        # 复制选中的方法论到中心仓库
        copied_list = []
        for meth in resources:
            src_file = meth["path"]
            dst_file = os.path.join(self.repo_path, os.path.basename(src_file))
            shutil.copy2(src_file, dst_file)
            copied_list.append(f"已复制: {meth['problem_type']}")

        return copied_list

    def run(self) -> None:
        """执行方法论分享流程"""
        try:
            # 更新中心仓库
            self.update_central_repo()

            # 获取本地资源
            local_resources = self.get_local_resources()
            if not local_resources:
                PrettyOutput.print(
                    "没有找到新的方法论文件（所有方法论可能已存在于中心仓库）",
                    OutputType.WARNING,
                )
                return

            # 选择要分享的资源
            selected_resources = self.select_resources(local_resources)
            if not selected_resources:
                return

            # 分享资源
            copied_list = self.share_resources(selected_resources)
            if copied_list:
                # 一次性显示所有复制结果
                PrettyOutput.print("\n".join(copied_list), OutputType.SUCCESS)

                # 提交并推送
                self.commit_and_push(len(selected_resources))

                PrettyOutput.print("\n方法论已成功分享到中心仓库！", OutputType.SUCCESS)

        except Exception as e:
            PrettyOutput.print(f"分享方法论时出错: {str(e)}", OutputType.ERROR)
            raise typer.Exit(code=1)
