"""CodeAgent 规则管理模块"""

import os
import subprocess

from jarvis.jarvis_utils.output import PrettyOutput

# -*- coding: utf-8 -*-
from typing import List
from typing import Optional
from typing import Set
from typing import Tuple

import yaml

from jarvis.jarvis_code_agent.builtin_rules import get_builtin_rule
from jarvis.jarvis_utils.config import get_central_rules_repo
from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.config import get_rules_load_dirs
from jarvis.jarvis_utils.utils import daily_check_git_updates


class RulesManager:
    """规则管理器，负责加载和管理各种规则"""

    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        # 初始化规则目录列表
        self._init_rules_dirs()

    def _init_rules_dirs(self) -> None:
        """初始化规则目录列表，包括配置的目录和中心库"""
        # 基础目录：全局数据目录下的 rules 目录
        self.rules_dirs: List[str] = [os.path.join(get_data_dir(), "rules")]

        # 添加配置的规则加载目录
        self.rules_dirs.extend(get_rules_load_dirs())

        # 中心规则仓库路径（单独存储，优先级最高）
        self.central_repo_path: Optional[str] = None
        central_repo = get_central_rules_repo()
        if central_repo:
            # 支持本地目录路径或Git仓库URL
            expanded = os.path.expanduser(os.path.expandvars(central_repo))
            if os.path.isdir(expanded):
                # 直接使用本地目录（支持Git仓库的子目录）
                self.central_repo_path = expanded
            else:
                # 中心规则仓库存储在数据目录下的特定位置
                self.central_repo_path = os.path.join(
                    get_data_dir(), "central_rules_repo"
                )

                # 确保中心规则仓库被克隆/更新
                if not os.path.exists(self.central_repo_path):
                    try:
                        PrettyOutput.auto_print(
                            f"ℹ️ 正在克隆中心规则仓库: {central_repo}"
                        )
                        subprocess.run(
                            ["git", "clone", central_repo, self.central_repo_path],
                            check=True,
                        )
                    except Exception as e:
                        PrettyOutput.auto_print(f"❌ 克隆中心规则仓库失败: {str(e)}")

        # 执行每日更新检查（包括中心库）
        all_dirs_for_update = self.rules_dirs.copy()
        if self.central_repo_path:
            all_dirs_for_update.append(self.central_repo_path)
        daily_check_git_updates(all_dirs_for_update, "rules")

    def read_project_rule(self) -> Optional[str]:
        """读取 .jarvis/rule 文件内容，如果存在则返回字符串，否则返回 None"""
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

    def _get_all_rules_dirs(self) -> List[str]:
        """获取所有规则目录（包括项目目录和配置的目录）

        返回:
            List[str]: 规则目录列表，按优先级排序（中心库 > 项目 > 配置目录）
        """
        all_dirs = []
        # 优先级 1: 中心规则仓库（如果有同名规则，以中心仓库为准）
        if (
            self.central_repo_path
            and os.path.exists(self.central_repo_path)
            and os.path.isdir(self.central_repo_path)
        ):
            # 检查中心仓库中是否有 rules 子目录
            central_rules_dir = os.path.join(self.central_repo_path, "rules")
            if os.path.exists(central_rules_dir) and os.path.isdir(central_rules_dir):
                all_dirs.append(central_rules_dir)
            else:
                # 如果没有 rules 子目录，直接使用中心仓库根目录
                all_dirs.append(self.central_repo_path)
        # 优先级 2: 项目 rules 目录
        project_rules_dir = os.path.join(self.root_dir, ".jarvis", "rules")
        if os.path.exists(project_rules_dir) and os.path.isdir(project_rules_dir):
            all_dirs.append(project_rules_dir)
        # 优先级 3-N: 配置的规则目录（不包括中心库）
        all_dirs.extend(self.rules_dirs)
        return all_dirs

    def _get_all_rules_yaml_files(self) -> List[tuple[str, str]]:
        """获取所有 rules.yaml 文件路径（描述，文件路径）

        返回:
            List[tuple[str, str]]: (描述, 文件路径) 列表，按优先级排序（中心库 > 项目 > 全局）
        """
        yaml_files = []
        # 优先级 1: 中心规则仓库的 rules.yaml（如果有同名规则，以中心仓库为准）
        if self.central_repo_path and os.path.exists(self.central_repo_path):
            central_rules_yaml = os.path.join(self.central_repo_path, "rules.yaml")
            if os.path.exists(central_rules_yaml) and os.path.isfile(
                central_rules_yaml
            ):
                yaml_files.append(("中心库", central_rules_yaml))
        # 优先级 2: 项目 rules.yaml
        project_rules_yaml = os.path.join(self.root_dir, ".jarvis", "rules.yaml")
        if os.path.exists(project_rules_yaml) and os.path.isfile(project_rules_yaml):
            yaml_files.append(("项目", project_rules_yaml))
        # 优先级 3: 全局 rules.yaml
        global_rules_yaml = os.path.join(get_data_dir(), "rules.yaml")
        if os.path.exists(global_rules_yaml) and os.path.isfile(global_rules_yaml):
            yaml_files.append(("全局", global_rules_yaml))
        return yaml_files

    def get_named_rule(self, rule_name: str) -> Optional[str]:
        """从 rules.yaml 文件和 rules 目录中获取指定名称的规则

        查找优先级（从高到低）:
        1. 中心规则仓库中的文件（如果有同名规则，以中心仓库为准）
        2. 项目 rules 目录中的文件
        3. 项目 rules.yaml 文件
        4. 配置的规则目录中的文件（按配置顺序，不包括中心库）
        5. 全局 rules.yaml 文件
        6. 内置规则（最低优先级，作为后备）

        参数:
            rule_name: 规则名称

        返回:
            str: 规则内容，如果未找到则返回 None
        """
        try:
            # 优先级 1: 从所有规则目录读取（中心库 > 项目 > 配置目录）
            for rules_dir in self._get_all_rules_dirs():
                if os.path.exists(rules_dir) and os.path.isdir(rules_dir):
                    rule_content = self._read_rule_from_dir(rules_dir, rule_name)
                    if rule_content:
                        return rule_content

            # 优先级 2: 从所有 rules.yaml 文件读取（中心库 > 项目 > 全局）
            for desc, yaml_path in self._get_all_rules_yaml_files():
                if os.path.exists(yaml_path) and os.path.isfile(yaml_path):
                    try:
                        with open(
                            yaml_path, "r", encoding="utf-8", errors="replace"
                        ) as f:
                            rules = yaml.safe_load(f) or {}
                        if rule_name in rules:
                            rule_value = rules[rule_name]
                            if isinstance(rule_value, str):
                                content = rule_value.strip()
                            else:
                                content = str(rule_value).strip()
                            if content:
                                return content
                    except Exception:
                        # 单个文件读取失败不影响其他文件
                        continue

            # 优先级 3: 从内置规则中查找（最低优先级，作为后备）
            builtin_rule = get_builtin_rule(rule_name)
            if builtin_rule:
                return builtin_rule

            return None
        except Exception as e:
            # 读取规则失败时忽略，不影响主流程
            PrettyOutput.auto_print(f"⚠️ 读取规则失败: {e}")
            return None

    def get_all_available_rule_names(self) -> dict[str, List[str]]:
        """获取所有可用的规则名称，按来源分类

        返回:
            dict[str, List[str]]: 按来源分类的规则名称字典
                - "builtin": 内置规则列表
                - "files": 规则目录中的文件规则列表
                - "yaml": rules.yaml 文件中的规则列表
        """
        from jarvis.jarvis_code_agent.builtin_rules import list_builtin_rules

        result = {
            "builtin": list_builtin_rules(),
            "files": [],
            "yaml": [],
        }

        # 收集规则目录中的文件规则
        for rules_dir in self._get_all_rules_dirs():
            if os.path.exists(rules_dir) and os.path.isdir(rules_dir):
                try:
                    for filename in os.listdir(rules_dir):
                        file_path = os.path.join(rules_dir, filename)
                        if os.path.isfile(file_path):
                            # 规则名称就是文件名
                            if filename not in result["files"]:
                                result["files"].append(filename)
                except Exception:
                    continue

        # 收集 rules.yaml 文件中的规则
        for desc, yaml_path in self._get_all_rules_yaml_files():
            if os.path.exists(yaml_path) and os.path.isfile(yaml_path):
                try:
                    with open(yaml_path, "r", encoding="utf-8", errors="replace") as f:
                        rules = yaml.safe_load(f) or {}
                        if isinstance(rules, dict):
                            for rule_name in rules.keys():
                                if rule_name not in result["yaml"]:
                                    result["yaml"].append(rule_name)
                except Exception:
                    continue

        return result

    def load_all_rules(self, rule_names: Optional[str] = None) -> Tuple[str, Set[str]]:
        """加载所有规则并合并

        参数:
            rule_names: 规则名称列表（逗号分隔）

        返回:
            (merged_rules, loaded_rule_names): 合并后的规则字符串和已加载的规则名称列表
        """
        combined_parts: List[str] = []
        loaded_rule_names: Set[str] = set()

        global_rules = self.read_global_rules()
        project_rules = self.read_project_rule()

        if global_rules:
            combined_parts.append(global_rules)
            loaded_rule_names.add("global_rule")
        if project_rules:
            combined_parts.append(project_rules)
            loaded_rule_names.add("project_rule")

        # 如果指定了 rule_names，从 rules.yaml 文件中读取并添加多个规则
        if rule_names:
            rule_list = [name.strip() for name in rule_names.split(",") if name.strip()]
            for rule_name in rule_list:
                named_rule = self.get_named_rule(rule_name)
                if named_rule:
                    combined_parts.append(named_rule)
                    loaded_rule_names.add(rule_name)

        if combined_parts:
            merged_rules = "\n\n".join(combined_parts)
            return merged_rules, loaded_rule_names
        return "", set()
