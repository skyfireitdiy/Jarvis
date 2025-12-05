# -*- coding: utf-8 -*-
"""CodeAgent 规则管理模块"""

import os
from typing import List, Optional

import yaml

from jarvis.jarvis_utils.config import get_data_dir


class RulesManager:
    """规则管理器，负责加载和管理各种规则"""

    def __init__(self, root_dir: str):
        self.root_dir = root_dir

    def read_project_rules(self) -> Optional[str]:
        """读取 .jarvis/rules 内容，如果存在则返回字符串，否则返回 None"""
        try:
            rules_path = os.path.join(self.root_dir, ".jarvis", "rule")
            if os.path.exists(rules_path) and os.path.isfile(rules_path):
                with open(rules_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read().strip()
                return content if content else None
        except Exception:
            # 读取规则失败时忽略，不影响主流程
            pass
        return None

    def read_global_rules(self) -> Optional[str]:
        """读取数据目录 rules 内容，如果存在则返回字符串，否则返回 None"""
        try:
            rules_path = os.path.join(get_data_dir(), "rule")
            if os.path.exists(rules_path) and os.path.isfile(rules_path):
                with open(rules_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read().strip()
                return content if content else None
        except Exception:
            # 读取规则失败时忽略，不影响主流程
            pass
        return None

    def _read_rule_from_dir(self, rules_dir: str, rule_name: str) -> Optional[str]:
        """从 rules 目录中读取指定名称的规则文件

        参数:
            rules_dir: rules 目录路径
            rule_name: 规则名称（文件名）

        返回:
            str: 规则内容，如果未找到则返回 None
        """
        try:
            rule_file_path = os.path.join(rules_dir, rule_name)
            if os.path.exists(rule_file_path) and os.path.isfile(rule_file_path):
                with open(rule_file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read().strip()
                return content if content else None
        except Exception:
            # 读取规则失败时忽略，不影响主流程
            pass
        return None

    def get_named_rule(self, rule_name: str) -> Optional[str]:
        """从 rules.yaml 文件和 rules 目录中获取指定名称的规则

        查找优先级（从高到低）:
        1. 项目 rules 目录中的文件
        2. 项目 rules.yaml 文件
        3. 全局 rules 目录中的文件
        4. 全局 rules.yaml 文件

        参数:
            rule_name: 规则名称

        返回:
            str: 规则内容，如果未找到则返回 None
        """
        try:
            # 优先级 1: 从项目 rules 目录读取
            project_rules_dir = os.path.join(self.root_dir, "rules")
            if os.path.exists(project_rules_dir) and os.path.isdir(project_rules_dir):
                rule_content = self._read_rule_from_dir(project_rules_dir, rule_name)
                if rule_content:
                    return rule_content

            # 优先级 2: 从项目 rules.yaml 读取
            project_rules_yaml_path = os.path.join(self.root_dir, "rules.yaml")
            project_rules = {}
            if os.path.exists(project_rules_yaml_path) and os.path.isfile(
                project_rules_yaml_path
            ):
                with open(
                    project_rules_yaml_path, "r", encoding="utf-8", errors="replace"
                ) as f:
                    project_rules = yaml.safe_load(f) or {}
                if rule_name in project_rules:
                    rule_value = project_rules[rule_name]
                    if isinstance(rule_value, str):
                        content = rule_value.strip()
                    else:
                        content = str(rule_value).strip()
                    if content:
                        return content

            # 优先级 3: 从全局 rules 目录读取
            global_rules_dir = os.path.join(get_data_dir(), "rules")
            if os.path.exists(global_rules_dir) and os.path.isdir(global_rules_dir):
                rule_content = self._read_rule_from_dir(global_rules_dir, rule_name)
                if rule_content:
                    return rule_content

            # 优先级 4: 从全局 rules.yaml 读取
            global_rules_yaml_path = os.path.join(get_data_dir(), "rules.yaml")
            global_rules = {}
            if os.path.exists(global_rules_yaml_path) and os.path.isfile(
                global_rules_yaml_path
            ):
                with open(
                    global_rules_yaml_path, "r", encoding="utf-8", errors="replace"
                ) as f:
                    global_rules = yaml.safe_load(f) or {}
                if rule_name in global_rules:
                    rule_value = global_rules[rule_name]
                    if isinstance(rule_value, str):
                        content = rule_value.strip()
                    else:
                        content = str(rule_value).strip()
                    if content:
                        return content

            return None
        except Exception as e:
            # 读取规则失败时忽略，不影响主流程
            print(f"⚠️ 读取规则失败: {e}")
            return None

    def load_all_rules(self, rule_names: Optional[str] = None) -> tuple[str, List[str]]:
        """加载所有规则并合并

        参数:
            rule_names: 规则名称列表（逗号分隔）

        返回:
            (merged_rules, loaded_rule_names): 合并后的规则字符串和已加载的规则名称列表
        """
        combined_parts: List[str] = []
        loaded_rule_names: List[str] = []

        global_rules = self.read_global_rules()
        project_rules = self.read_project_rules()

        if global_rules:
            combined_parts.append(global_rules)
            loaded_rule_names.append("global_rule")
        if project_rules:
            combined_parts.append(project_rules)
            loaded_rule_names.append("project_rule")

        # 如果指定了 rule_names，从 rules.yaml 文件中读取并添加多个规则
        if rule_names:
            rule_list = [name.strip() for name in rule_names.split(",") if name.strip()]
            for rule_name in rule_list:
                named_rule = self.get_named_rule(rule_name)
                if named_rule:
                    combined_parts.append(named_rule)
                    loaded_rule_names.append(rule_name)

        if combined_parts:
            merged_rules = "\n\n".join(combined_parts)
            return merged_rules, loaded_rule_names
        return "", []
