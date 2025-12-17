"""规则分享管理模块"""

import glob
import os

from jarvis.jarvis_utils.output import PrettyOutput

# -*- coding: utf-8 -*-
import shutil
from typing import Any
from typing import Dict
from typing import List
from typing import Set

import typer

from jarvis.jarvis_agent import user_confirm
from jarvis.jarvis_agent.share_manager import ShareManager
from jarvis.jarvis_utils.config import get_central_rules_repo
from jarvis.jarvis_utils.config import get_data_dir


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
        return f"{resource['rule_name']} ({resource['filename']})"

    def get_existing_resources(self) -> Set[str]:
        """获取中心仓库中已有的规则文件名"""
        existing_rules = set()
        # 检查 rules 目录中的文件
        rules_dir = os.path.join(self.repo_path, "rules")
        if os.path.exists(rules_dir):
            for filepath in glob.glob(os.path.join(rules_dir, "*")):
                if os.path.isfile(filepath):
                    existing_rules.add(os.path.basename(filepath))
        # 检查根目录下的文件（作为规则文件）
        for filepath in glob.glob(os.path.join(self.repo_path, "*")):
            if os.path.isfile(filepath) and not filepath.endswith(".yaml"):
                existing_rules.add(os.path.basename(filepath))
        return existing_rules

    def get_local_resources(self) -> List[Dict[str, Any]]:
        """获取本地规则

        注意：只能共享默认rules目录（get_data_dir()/rules）中的规则，
        不能共享配置的rules目录和项目rules目录中的规则。
        """
        # 获取中心仓库中已有的规则文件名
        existing_rules = self.get_existing_resources()

        # 只从默认数据目录的 rules 目录获取规则（不能共享配置的目录和项目rules）
        local_rules_dir = os.path.join(get_data_dir(), "rules")
        if not os.path.exists(local_rules_dir):
            PrettyOutput.auto_print(f"⚠️ 本地规则目录不存在: {local_rules_dir}")
            return []

        # 收集本地规则文件（排除已存在的）
        rule_files = []
        for filepath in glob.glob(os.path.join(local_rules_dir, "*")):
            if not os.path.isfile(filepath):
                continue
            filename = os.path.basename(filepath)
            # 跳过已存在的文件
            if filename in existing_rules:
                continue

            # 规则名称就是文件名
            rule_name = filename
            rule_files.append(
                {
                    "path": filepath,
                    "filename": filename,
                    "rule_name": rule_name,
                }
            )

        return rule_files

    def share_resources(self, resources: List[Dict[str, Any]]) -> List[str]:
        """分享规则到中心仓库"""
        # 确认操作
        share_list = ["\n将要分享以下规则到中心仓库（注意：文件将被移动而非复制）："]
        for rule in resources:
            share_list.append(f"- {rule['rule_name']} ({rule['filename']})")
        joined_list = "\n".join(share_list)
        PrettyOutput.auto_print(f"⚠️ {joined_list}")

        if not user_confirm("确认移动这些规则到中心仓库吗？（原文件将被删除）"):
            return []

        # 确保中心仓库有 rules 目录
        rules_dir = os.path.join(self.repo_path, "rules")
        if not os.path.exists(rules_dir):
            os.makedirs(rules_dir, exist_ok=True)

        # 移动选中的规则到中心仓库
        moved_list = []
        for rule in resources:
            src_file = rule["path"]
            dst_file = os.path.join(rules_dir, rule["filename"])
            shutil.move(src_file, dst_file)  # 使用move而不是copy
            moved_list.append(f"已移动: {rule['rule_name']}")

        return moved_list

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
            moved_list = self.share_resources(selected_resources)
            if moved_list:
                # 一次性显示所有移动结果
                joined_moved = "\n".join(moved_list)
                PrettyOutput.auto_print(f"✅ {joined_moved}")

                # 提交并推送
                self.commit_and_push(len(selected_resources))

                PrettyOutput.auto_print("✅ 规则已成功分享到中心仓库！")
                PrettyOutput.auto_print(
                    f"ℹ️ 原文件已从 {os.path.join(get_data_dir(), 'rules')} 移动到中心仓库"
                )

        except Exception as e:
            PrettyOutput.auto_print(f"❌ 分享规则时出错: {str(e)}")
            raise typer.Exit(code=1)
