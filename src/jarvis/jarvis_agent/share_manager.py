# -*- coding: utf-8 -*-
"""分享管理模块，负责工具和方法论的分享功能"""

import os
import subprocess
from abc import ABC
from abc import abstractmethod
from typing import Any

from prompt_toolkit import prompt

from jarvis.jarvis_agent import user_confirm
from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.output import PrettyOutput


def parse_selection(selection_str: str, max_value: int) -> list[int]:
    """解析用户输入的选择字符串，支持逗号分隔和范围选择

    例如: "1,2,3,4-9,20" -> [1, 2, 3, 4, 5, 6, 7, 8, 9, 20]
    """
    selected: set[int] = set()
    parts = selection_str.split(",")

    for part in parts:
        part = part.strip()
        if "-" in part:
            # 处理范围选择
            try:
                start_str, end_str = part.split("-")
                start_num = int(start_str.strip())
                end_num = int(end_str.strip())
                if 1 <= start_num <= max_value and 1 <= end_num <= max_value:
                    selected.update(range(start_num, end_num + 1))
            except ValueError:
                continue
        else:
            # 处理单个数字
            try:
                num = int(part)
                if 1 <= num <= max_value:
                    selected.add(num)
            except ValueError:
                continue

    return sorted(list(selected))


class ShareManager(ABC):
    """分享管理器基类"""

    def __init__(self, central_repo_url: str, repo_name: str):
        self.central_repo_url = central_repo_url
        self.repo_name = repo_name
        # 支持将中心仓库配置为本地目录（含git子路径）
        expanded = os.path.expanduser(os.path.expandvars(central_repo_url))
        if os.path.isdir(expanded):
            # 直接使用本地目录作为中心仓库路径（支持git仓库子目录）
            self.repo_path = expanded
        else:
            # 仍按原逻辑使用数据目录中的克隆路径
            self.repo_path = os.path.join(get_data_dir(), repo_name)

    def update_central_repo(self) -> None:
        """克隆或更新中心仓库"""
        if not os.path.exists(self.repo_path):
            PrettyOutput.auto_print(f"ℹ️ 正在克隆中心{self.get_resource_type()}仓库...")
            subprocess.run(
                ["git", "clone", self.central_repo_url, self.repo_path], check=True
            )
            # 检查并添加.gitignore文件
            gitignore_path = os.path.join(self.repo_path, ".gitignore")
            modified = False
            if not os.path.exists(gitignore_path):
                with open(gitignore_path, "w") as f:
                    f.write("__pycache__/\n")
                modified = True
            else:
                with open(gitignore_path, "r+") as f:
                    content = f.read()
                    if "__pycache__" not in content:
                        f.write("\n__pycache__/\n")
                        modified = True

            if modified:
                subprocess.run(
                    ["git", "add", ".gitignore"], cwd=self.repo_path, check=True
                )
                subprocess.run(
                    ["git", "commit", "-m", "chore: add __pycache__ to .gitignore"],
                    cwd=self.repo_path,
                    check=True,
                )
                subprocess.run(["git", "push"], cwd=self.repo_path, check=True)
        else:
            PrettyOutput.auto_print(f"ℹ️ 正在更新中心{self.get_resource_type()}仓库...")
            # 检查是否是空仓库
            try:
                # 先尝试获取远程分支信息
                result = subprocess.run(
                    ["git", "ls-remote", "--heads", "origin"],
                    cwd=self.repo_path,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                # 如果有远程分支，执行pull
                if result.stdout.strip():
                    # 检查是否有未提交的更改
                    status_result = subprocess.run(
                        ["git", "status", "--porcelain"],
                        cwd=self.repo_path,
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    if status_result.stdout:
                        if user_confirm(
                            f"检测到中心{self.get_resource_type()}仓库 '{self.repo_name}' 存在未提交的更改，是否放弃这些更改并更新？"
                        ):
                            subprocess.run(
                                ["git", "checkout", "."], cwd=self.repo_path, check=True
                            )
                        else:
                            PrettyOutput.auto_print(
                                f"ℹ️ 跳过更新 '{self.repo_name}' 以保留未提交的更改。"
                            )
                            return
                    subprocess.run(["git", "pull"], cwd=self.repo_path, check=True)
                else:
                    PrettyOutput.auto_print(
                        f"ℹ️ 中心{self.get_resource_type()}仓库是空的，将初始化为新仓库"
                    )
            except subprocess.CalledProcessError:
                # 如果命令失败，可能是网络问题或其他错误
                PrettyOutput.auto_print("⚠️ 无法连接到远程仓库，将跳过更新")

    def commit_and_push(self, count: int) -> None:
        """提交并推送更改"""
        PrettyOutput.auto_print("ℹ️ 正在提交更改...")
        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)

        commit_msg = f"Add {count} {self.get_resource_type()}(s) from local collection"
        subprocess.run(
            ["git", "commit", "-m", commit_msg], cwd=self.repo_path, check=True
        )

        PrettyOutput.auto_print("ℹ️ 正在推送到远程仓库...")
        # 检查是否需要设置上游分支（空仓库的情况）
        try:
            # 先尝试普通推送
            subprocess.run(["git", "push"], cwd=self.repo_path, check=True)
        except subprocess.CalledProcessError:
            # 如果失败，可能是空仓库，尝试设置上游分支
            try:
                subprocess.run(
                    ["git", "push", "-u", "origin", "main"],
                    cwd=self.repo_path,
                    check=True,
                )
            except subprocess.CalledProcessError:
                # 如果main分支不存在，尝试master分支
                subprocess.run(
                    ["git", "push", "-u", "origin", "master"],
                    cwd=self.repo_path,
                    check=True,
                )

    def select_resources(self, resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """让用户选择要分享的资源"""
        # 显示可选的资源
        resource_list = [
            f"\n可分享的{self.get_resource_type()}（已排除中心仓库中已有的）："
        ]
        for i, resource in enumerate(resources, 1):
            resource_list.append(f"[{i}] {self.format_resource_display(resource)}")

        # 一次性打印所有资源
        joined_resources = "\n".join(resource_list)
        PrettyOutput.auto_print(f"ℹ️ {joined_resources}")

        # 让用户选择
        while True:
            try:
                choice_str = prompt(
                    f"\n请选择要分享的{self.get_resource_type()}编号（支持格式: 1,2,3,4-9,20 或 all）："
                ).strip()
                if choice_str == "0":
                    return []

                if choice_str.lower() == "all":
                    return resources
                else:
                    selected_indices = parse_selection(choice_str, len(resources))
                    if not selected_indices:
                        PrettyOutput.auto_print("⚠️ 无效的选择")
                        continue
                    return [resources[i - 1] for i in selected_indices]

            except ValueError:
                PrettyOutput.auto_print("⚠️ 请输入有效的数字")

    @abstractmethod
    def get_resource_type(self) -> str:
        """获取资源类型名称"""
        pass

    @abstractmethod
    def format_resource_display(self, resource: dict[str, Any]) -> str:
        """格式化资源显示"""
        pass

    @abstractmethod
    def get_existing_resources(self) -> Any:
        """获取中心仓库中已有的资源"""
        pass

    @abstractmethod
    def get_local_resources(self) -> list[dict[str, Any]]:
        """获取本地资源"""
        pass

    @abstractmethod
    def share_resources(self, resources: list[dict[str, Any]]) -> list[str]:
        """分享资源到中心仓库"""
        pass
