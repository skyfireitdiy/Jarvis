# -*- coding: utf-8 -*-
"""规则分享管理模块"""

import glob
import os
import shutil
from typing import Any
from typing import Dict
from typing import List

import typer

from jarvis.jarvis_agent import user_confirm
from jarvis.jarvis_agent.share_manager import ShareManager
from jarvis.jarvis_utils.config import get_central_rules_repo
from jarvis.jarvis_utils.config import get_rules_load_dirs
from jarvis.jarvis_utils.output import PrettyOutput


class RuleShareManager(ShareManager):
    """规则分享管理器"""

    def __init__(self) -> None:
        central_repo = get_central_rules_repo()
        if not central_repo:
            PrettyOutput.auto_print("❌ 错误：未配置中心规则仓库（central_rules_repo）")
            PrettyOutput.auto_print("ℹ️ 请在配置文件中设置中心规则仓库的Git地址")
            raise typer.Exit(code=1)

        super().__init__(central_repo, "central_rules_repo")

    def get_resource_type(self) -> str:
        """获取资源类型名称"""
        return "规则"

    def format_resource_display(self, resource: Dict[str, Any]) -> str:
        """格式化资源显示"""
        dir_name = os.path.basename(resource["directory"])
        return f"{resource['rule_name']} (来自: {dir_name})"

    def get_existing_resources(self) -> Dict[str, str]:
        """获取中心仓库中已有的规则"""
        existing_rules = {}  # 存储 rule_name -> content 的映射
        for filepath in glob.glob(
            os.path.join(self.repo_path, "**", "*.md"), recursive=True
        ):
            try:
                # 获取相对于 repo_path 的路径作为规则标识
                rel_path = os.path.relpath(filepath, self.repo_path)
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    if content:
                        existing_rules[rel_path] = content
            except Exception:
                pass
        return existing_rules

    def get_local_resources(self) -> List[Dict[str, Any]]:
        """获取本地规则"""
        # 获取中心仓库中已有的规则
        existing_rules = self.get_existing_resources()

        # 获取所有规则目录
        from jarvis.jarvis_utils.template_utils import _get_builtin_dir, _get_git_root

        git_root = _get_git_root()
        rule_dirs = [
            os.path.join(git_root, ".jarvis", "rules"),
        ] + get_rules_load_dirs()

        # 添加 builtin 目录（如果存在）
        builtin_dir = _get_builtin_dir()
        if builtin_dir is not None:
            builtin_rules_dir = builtin_dir / "rules"
            if builtin_rules_dir.exists() and builtin_rules_dir.is_dir():
                rule_dirs.append(str(builtin_rules_dir))

        # 收集所有规则文件（排除中心仓库目录和已存在的规则）
        rule_files = []
        seen_rule_names = set()  # 用于去重

        for directory in set(rule_dirs):
            # 跳过中心仓库目录
            if os.path.abspath(directory) == os.path.abspath(self.repo_path):
                continue

            if not os.path.isdir(directory):
                continue

            for filepath in glob.glob(
                os.path.join(directory, "**", "*.md"), recursive=True
            ):
                try:
                    # 获取相对于 directory 的路径作为规则标识
                    rel_path = os.path.relpath(filepath, directory)

                    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()

                    # 基于内容判断是否已存在于中心仓库
                    is_duplicate = False
                    if rel_path in existing_rules:
                        # 如果路径相同，比较内容
                        if content.strip() == existing_rules[rel_path].strip():
                            is_duplicate = True

                    # 排除已存在于中心仓库的规则（基于内容），以及本地重复的规则
                    if content and not is_duplicate and rel_path not in seen_rule_names:
                        rule_files.append(
                            {
                                "path": filepath,
                                "rule_name": rel_path,
                                "directory": directory,
                            }
                        )
                        seen_rule_names.add(rel_path)
                except Exception:
                    pass

        return rule_files

    def share_resources(self, resources: List[Dict[str, Any]]) -> List[str]:
        """分享规则到中心仓库"""
        # 确认操作
        share_list = ["\n将要分享以下规则到中心仓库："]
        for rule in resources:
            share_list.append(f"- {rule['rule_name']}")
        joined_list = "\n".join(share_list)
        PrettyOutput.auto_print(f"ℹ️ {joined_list}")

        if not user_confirm("确认分享这些规则吗？"):
            return []

        # 复制选中的规则到中心仓库
        copied_list = []
        for rule in resources:
            src_file = rule["path"]
            # 保持相对路径结构
            dst_file = os.path.join(self.repo_path, rule["rule_name"])
            dst_dir = os.path.dirname(dst_file)

            # 创建目标目录（如果不存在）
            os.makedirs(dst_dir, exist_ok=True)

            shutil.copy2(src_file, dst_file)
            copied_list.append(f"已复制: {rule['rule_name']}")

        return copied_list

    def run(self) -> None:
        """执行规则分享流程"""
        try:
            # 更新中心仓库
            self.update_central_repo()

            # 获取本地资源
            local_resources = self.get_local_resources()
            if not local_resources:
                PrettyOutput.auto_print(
                    "⚠️ 没有找到新的规则文件（所有规则可能已存在于中心仓库）"
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
                joined_copied = "\n".join(copied_list)
                PrettyOutput.auto_print(f"✅ {joined_copied}")

                # 提交并推送
                self.commit_and_push(len(selected_resources))

                PrettyOutput.auto_print("✅ 规则已成功分享到中心仓库！")

        except Exception as e:
            PrettyOutput.auto_print(f"❌ 分享规则时出错: {str(e)}")
            raise typer.Exit(code=1)
