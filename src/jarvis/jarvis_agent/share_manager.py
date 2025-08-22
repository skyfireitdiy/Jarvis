# -*- coding: utf-8 -*-
"""分享管理模块，负责工具和方法论的分享功能"""
import os
import subprocess
from typing import List, Dict, Any, Set
from abc import ABC, abstractmethod

from prompt_toolkit import prompt

from jarvis.jarvis_agent import OutputType, PrettyOutput, user_confirm
from jarvis.jarvis_utils.config import get_data_dir


def parse_selection(selection_str: str, max_value: int) -> List[int]:
    """解析用户输入的选择字符串，支持逗号分隔和范围选择

    例如: "1,2,3,4-9,20" -> [1, 2, 3, 4, 5, 6, 7, 8, 9, 20]
    """
    selected: Set[int] = set()
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
        self.repo_path = os.path.join(get_data_dir(), repo_name)

    def update_central_repo(self) -> None:
        """克隆或更新中心仓库"""
        if not os.path.exists(self.repo_path):
            PrettyOutput.print(
                f"正在克隆中心{self.get_resource_type()}仓库...", OutputType.INFO
            )
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
            PrettyOutput.print(
                f"正在更新中心{self.get_resource_type()}仓库...", OutputType.INFO
            )
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
                            PrettyOutput.print(
                                f"跳过更新 '{self.repo_name}' 以保留未提交的更改。",
                                OutputType.INFO,
                            )
                            return
                    subprocess.run(["git", "pull"], cwd=self.repo_path, check=True)
                else:
                    PrettyOutput.print(
                        f"中心{self.get_resource_type()}仓库是空的，将初始化为新仓库",
                        OutputType.INFO,
                    )
            except subprocess.CalledProcessError:
                # 如果命令失败，可能是网络问题或其他错误
                PrettyOutput.print("无法连接到远程仓库，将跳过更新", OutputType.WARNING)

    def commit_and_push(self, count: int) -> None:
        """提交并推送更改"""
        PrettyOutput.print("\n正在提交更改...", OutputType.INFO)
        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)

        commit_msg = f"Add {count} {self.get_resource_type()}(s) from local collection"
        subprocess.run(
            ["git", "commit", "-m", commit_msg], cwd=self.repo_path, check=True
        )

        PrettyOutput.print("正在推送到远程仓库...", OutputType.INFO)
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

    def select_resources(self, resources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """让用户选择要分享的资源"""
        # 显示可选的资源
        resource_list = [
            f"\n可分享的{self.get_resource_type()}（已排除中心仓库中已有的）："
        ]
        for i, resource in enumerate(resources, 1):
            resource_list.append(f"[{i}] {self.format_resource_display(resource)}")

        # 一次性打印所有资源
        PrettyOutput.print("\n".join(resource_list), OutputType.INFO)

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
                        PrettyOutput.print("无效的选择", OutputType.WARNING)
                        continue
                    return [resources[i - 1] for i in selected_indices]

            except ValueError:
                PrettyOutput.print("请输入有效的数字", OutputType.WARNING)

    @abstractmethod
    def get_resource_type(self) -> str:
        """获取资源类型名称"""
        pass

    @abstractmethod
    def format_resource_display(self, resource: Dict[str, Any]) -> str:
        """格式化资源显示"""
        pass

    @abstractmethod
    def get_existing_resources(self) -> Any:
        """获取中心仓库中已有的资源"""
        pass

    @abstractmethod
    def get_local_resources(self) -> List[Dict[str, Any]]:
        """获取本地资源"""
        pass

    @abstractmethod
    def share_resources(self, resources: List[Dict[str, Any]]) -> List[str]:
        """分享资源到中心仓库"""
        pass
