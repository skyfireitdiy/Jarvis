"""CodeAgent 规则管理模块"""

import os
import subprocess

from jarvis.jarvis_utils.output import PrettyOutput

# -*- coding: utf-8 -*-
from typing import Dict
from typing import List
from typing import Optional
from typing import Set
from typing import Tuple

import yaml

from jarvis.jarvis_agent.builtin_rules import get_builtin_rule
from jarvis.jarvis_agent.builtin_rules import get_builtin_rule_path
from jarvis.jarvis_utils.template_utils import render_rule_template
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
        # 跟踪已加载的规则名称（向后兼容）
        self.loaded_rules: Set[str] = set()

        # 私有属性：状态管理
        self._loaded_rules: Dict[
            str, str
        ] = {}  # {rule_name: rule_content} - 已加载的规则内容缓存
        self._active_rules: Set[str] = set()  # 已激活的规则名称集合
        self._merged_rules: str = ""  # 合并后的规则字符串（激活的规则内容）

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
                # 使用jinja2渲染规则模板
                if content:
                    content = render_rule_template(content, os.path.dirname(rules_path))
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
                # 使用jinja2渲染规则模板
                if content:
                    content = render_rule_template(content, os.path.dirname(rules_path))
                return content if content else None
        except Exception:
            # 读取规则失败时忽略，不影响主流程
            pass
        return None

    def _read_rule_from_dir(self, rules_dir: str, rule_name: str) -> Optional[str]:
        """从 rules 目录中读取指定名称的规则文件

        参数:
            rules_dir: rules 目录路径
            rule_name: 规则名称（支持相对路径，如 deployment/version_release.md）

        返回:
            str: 规则内容，如果未找到则返回 None
        """
        try:
            # 只支持 .md 后缀的文件
            if not rule_name.endswith(".md"):
                rule_name = rule_name + ".md"
            # 支持相对路径（如 deployment/version_release.md）
            rule_file_path = os.path.join(rules_dir, rule_name)
            if os.path.exists(rule_file_path) and os.path.isfile(rule_file_path):
                with open(rule_file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read().strip()
                # 使用jinja2渲染规则模板
                if content:
                    # 使用规则文件所在目录作为模板渲染的上下文
                    content = render_rule_template(
                        content, os.path.dirname(rule_file_path)
                    )
                return content if content else None
        except Exception:
            # 读取规则失败时忽略，不影响主流程
            pass
        return None

    def _get_builtin_rules_index(self) -> Optional[str]:
        """读取 rule.md 索引文件的完整内容

        返回:
            str: rule.md 的完整内容，如果未找到则返回 None
        """
        try:
            from jarvis.jarvis_utils.template_utils import _get_builtin_dir

            # 获取 builtin 目录路径
            builtin_dir = _get_builtin_dir()
            if builtin_dir is None:
                return None

            index_file_path = builtin_dir / "rules" / "rule.md"

            # 检查索引文件是否存在
            if not index_file_path.exists() or not index_file_path.is_file():
                return None

            # 读取索引文件内容
            with open(index_file_path, "r", encoding="utf-8", errors="replace") as f:
                index_content = f.read()

            # 使用jinja2渲染规则模板
            if index_content:
                index_content = render_rule_template(
                    index_content, str(index_file_path.parent)
                )

            return index_content if index_content else None

        except Exception as e:
            # 读取失败时忽略，不影响主流程
            PrettyOutput.auto_print(f"⚠️ 读取rule.md失败: {e}")
            return None

    def _get_rule_from_builtin_index(self, rule_name: str) -> Optional[str]:
        """从 rule.md 索引文件中查找并加载指定名称的规则

        该索引文件记录了内置规则的映射关系，格式为：
        - [规则名称]({{ template_var }}/path/to/rule.md)

        参数:
            rule_name: 规则名称

        返回:
            str: 规则内容，如果未找到则返回 None
        """
        try:
            from jarvis.jarvis_utils.template_utils import (
                _get_builtin_dir,
                _get_jarvis_src_dir,
            )

            # 获取 builtin 目录路径
            builtin_dir = _get_builtin_dir()
            if builtin_dir is None:
                return None

            index_file_path = builtin_dir / "rules" / "rule.md"

            # 检查索引文件是否存在
            if not index_file_path.exists() or not index_file_path.is_file():
                return None

            # 读取索引文件内容
            with open(index_file_path, "r", encoding="utf-8", errors="replace") as f:
                index_content = f.read()

            # 解析索引文件，查找匹配的规则
            # 格式: - [规则名称](路径)
            import re

            pattern = rf"-\s*\[{re.escape(rule_name)}\]\(([^)]+)\)"
            match = re.search(pattern, index_content)

            if not match:
                return None

            # 提取规则文件路径
            rule_file_template = match.group(1).strip()

            # 渲染模板变量（支持 {{ jarvis_src_dir }} 和 {{ rule_file_dir }}）
            # 为了向后兼容，仍然提供 jarvis_src_dir（指向 builtin 目录的父目录）
            jarvis_src_dir = (
                str(builtin_dir.parent) if builtin_dir else _get_jarvis_src_dir()
            )
            context = {
                "jarvis_src_dir": jarvis_src_dir,
                "rule_file_dir": str(index_file_path.parent),
            }

            try:
                from jinja2 import Template

                template = Template(rule_file_template)
                rule_file_path = template.render(**context)
            except Exception:
                # 模板渲染失败，直接使用原始路径
                rule_file_path = rule_file_template

            # 检查规则文件是否存在
            if not os.path.exists(rule_file_path) or not os.path.isfile(rule_file_path):
                return None

            # 读取规则文件内容
            with open(rule_file_path, "r", encoding="utf-8", errors="replace") as f:
                rule_content = f.read().strip()

            # 使用jinja2渲染规则模板
            if rule_content:
                rule_content = render_rule_template(
                    rule_content, os.path.dirname(rule_file_path)
                )

            return rule_content if rule_content else None

        except Exception as e:
            # 读取失败时忽略，不影响主流程
            PrettyOutput.auto_print(f"⚠️ 从索引文件加载规则失败: {e}")
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

        规则名称格式：前缀:规则名
        前缀说明：
        - builtin: - 内置规则目录（jarvis源码/builtin/rules）
        - project: - 项目 .jarvis/rules 目录文件
        - global: - 全局 ~/.jarvis/rules 目录文件
        - central: - 中心规则仓库文件
        - config1:, config2: - 配置的规则目录文件
        - central_yaml: - 中心库 rules.yaml
        - project_yaml: - 项目 rules.yaml
        - global_yaml: - 全局 rules.yaml
        - 无前缀 - 内置规则或 rule.md 索引文件中的规则

        参数:
            rule_name: 规则名称（可能包含前缀）

        返回:
            str: 规则内容，如果未找到则返回 None
        """
        PrettyOutput.auto_print(
            f"🔍 [DEBUG] get_named_rule 被调用，rule_name = '{rule_name}'"
        )
        try:
            # 解析前缀
            if ":" in rule_name:
                prefix, actual_name = rule_name.split(":", 1)
                if not actual_name:
                    return None

                # 处理 builtin 前缀
                if prefix == "builtin":
                    PrettyOutput.auto_print(
                        f"🔍 [DEBUG] 检测到 builtin 前缀，actual_name = '{actual_name}'"
                    )
                    try:
                        from jarvis.jarvis_utils.template_utils import _get_builtin_dir

                        builtin_dir = _get_builtin_dir()
                        PrettyOutput.auto_print(
                            f"🔍 [DEBUG] builtin_dir = {builtin_dir}"
                        )
                        if builtin_dir is not None:
                            builtin_rules_dir = builtin_dir / "rules"
                            PrettyOutput.auto_print(
                                f"🔍 [DEBUG] builtin_rules_dir = {builtin_rules_dir}, exists = {builtin_rules_dir.exists()}, is_dir = {builtin_rules_dir.is_dir()}"
                            )
                            if (
                                builtin_rules_dir.exists()
                                and builtin_rules_dir.is_dir()
                            ):
                                rule_content = self._read_rule_from_dir(
                                    str(builtin_rules_dir), actual_name
                                )
                                PrettyOutput.auto_print(
                                    f"🔍 [DEBUG] 从 builtin 目录读取规则结果: {bool(rule_content)}"
                                )
                                return rule_content
                    except Exception as e:
                        PrettyOutput.auto_print(
                            f"🔍 [DEBUG] 处理 builtin 前缀时出错: {e}"
                        )
                        pass
                    PrettyOutput.auto_print(
                        "🔍 [DEBUG] builtin 规则查找失败，返回 None"
                    )
                    return None

                # 处理 project 前缀
                if prefix == "project":
                    project_rules_dir = os.path.join(self.root_dir, ".jarvis", "rules")
                    if os.path.exists(project_rules_dir) and os.path.isdir(
                        project_rules_dir
                    ):
                        return self._read_rule_from_dir(project_rules_dir, actual_name)
                    return None

                # 处理 global 前缀
                if prefix == "global":
                    global_rules_dir = os.path.join(get_data_dir(), "rules")
                    if os.path.exists(global_rules_dir) and os.path.isdir(
                        global_rules_dir
                    ):
                        return self._read_rule_from_dir(global_rules_dir, actual_name)
                    return None

                # 处理 central 和 config 前缀
                if prefix == "central" or prefix.startswith("config"):
                    all_rules_dirs = self._get_all_rules_dirs()
                    target_idx = -1
                    if prefix == "central" and len(all_rules_dirs) > 0:
                        target_idx = 0
                    elif prefix.startswith("config"):
                        try:
                            config_num = int(prefix[6:])
                            target_idx = 2 + config_num
                        except ValueError:
                            pass

                    if 0 <= target_idx < len(all_rules_dirs):
                        rules_dir = all_rules_dirs[target_idx]
                        if os.path.exists(rules_dir) and os.path.isdir(rules_dir):
                            return self._read_rule_from_dir(rules_dir, actual_name)
                    return None

                # 处理 yaml 规则
                elif prefix in ["central_yaml", "project_yaml", "global_yaml"]:
                    for desc, yaml_path in self._get_all_rules_yaml_files():
                        if (prefix == "central_yaml" and desc == "中心库") or (
                            prefix == "project_yaml" and desc == "项目"
                        ):
                            if os.path.exists(yaml_path) and os.path.isfile(yaml_path):
                                try:
                                    with open(
                                        yaml_path,
                                        "r",
                                        encoding="utf-8",
                                        errors="replace",
                                    ) as f:
                                        rules = yaml.safe_load(f) or {}
                                    if actual_name in rules:
                                        rule_value = rules[actual_name]
                                        if isinstance(rule_value, str):
                                            content = rule_value.strip()
                                        else:
                                            content = str(rule_value).strip()
                                        # 使用jinja2渲染规则模板
                                        if content:
                                            content = render_rule_template(
                                                content, os.path.dirname(yaml_path)
                                            )
                                        return content if content else None
                                except Exception:
                                    continue
                        elif prefix == "global_yaml" and desc == "全局":
                            if os.path.exists(yaml_path) and os.path.isfile(yaml_path):
                                try:
                                    with open(
                                        yaml_path,
                                        "r",
                                        encoding="utf-8",
                                        errors="replace",
                                    ) as f:
                                        rules = yaml.safe_load(f) or {}
                                    if actual_name in rules:
                                        rule_value = rules[actual_name]
                                        if isinstance(rule_value, str):
                                            content = rule_value.strip()
                                        else:
                                            content = str(rule_value).strip()
                                        # 使用jinja2渲染规则模板
                                        if content:
                                            content = render_rule_template(
                                                content, os.path.dirname(yaml_path)
                                            )
                                        return content if content else None
                                except Exception:
                                    continue
                    return None

                # 未知前缀
                return None

            # 无前缀：按优先级查找（项目 rules.yaml > 全局 rules.yaml > rule.md > 内置规则）
            # 优先级 1: 从项目 rules.yaml 文件中查找
            for desc, yaml_path in self._get_all_rules_yaml_files():
                if desc == "项目":
                    if os.path.exists(yaml_path) and os.path.isfile(yaml_path):
                        try:
                            with open(
                                yaml_path,
                                "r",
                                encoding="utf-8",
                                errors="replace",
                            ) as f:
                                rules = yaml.safe_load(f) or {}
                            if rule_name in rules:
                                rule_value = rules[rule_name]
                                if isinstance(rule_value, str):
                                    content = rule_value.strip()
                                else:
                                    content = str(rule_value).strip()
                                # 使用jinja2渲染规则模板
                                if content:
                                    content = render_rule_template(
                                        content, os.path.dirname(yaml_path)
                                    )
                                if content:
                                    return content
                        except Exception:
                            continue

            # 优先级 2: 从全局 rules.yaml 文件中查找
            for desc, yaml_path in self._get_all_rules_yaml_files():
                if desc == "全局":
                    if os.path.exists(yaml_path) and os.path.isfile(yaml_path):
                        try:
                            with open(
                                yaml_path,
                                "r",
                                encoding="utf-8",
                                errors="replace",
                            ) as f:
                                rules = yaml.safe_load(f) or {}
                            if rule_name in rules:
                                rule_value = rules[rule_name]
                                if isinstance(rule_value, str):
                                    content = rule_value.strip()
                                else:
                                    content = str(rule_value).strip()
                                # 使用jinja2渲染规则模板
                                if content:
                                    content = render_rule_template(
                                        content, os.path.dirname(yaml_path)
                                    )
                                if content:
                                    return content
                        except Exception:
                            continue

            # 优先级 3: 从 rule.md 索引文件中查找
            indexed_rule = self._get_rule_from_builtin_index(rule_name)
            if indexed_rule:
                return indexed_rule

            # 优先级 4: 从内置规则中查找
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
                - "files": 规则目录中的文件规则列表（带来源前缀）
                - "yaml": rules.yaml 文件中的规则列表（带来源前缀）
        """
        from jarvis.jarvis_agent.builtin_rules import list_builtin_rules

        result = {
            "builtin": [f"builtin:{rule}" for rule in list_builtin_rules()],
            "files": [],
            "yaml": [],
        }

        # 收集规则目录中的文件规则（支持递归遍历子目录）
        all_rules_dirs = self._get_all_rules_dirs()
        for idx, rules_dir in enumerate(all_rules_dirs):
            if os.path.exists(rules_dir) and os.path.isdir(rules_dir):
                # 确定来源前缀（根据实际来源动态判断）
                # 检查是否为中心规则仓库
                is_central = False
                if self.central_repo_path:
                    central_rules_dir = os.path.join(self.central_repo_path, "rules")
                    if (
                        rules_dir == central_rules_dir
                        or rules_dir == self.central_repo_path
                    ):
                        is_central = True

                # 检查是否为项目规则目录
                project_rules_dir = os.path.join(self.root_dir, ".jarvis", "rules")
                is_project = rules_dir == project_rules_dir

                # 根据实际来源分配前缀
                global_rules_dir = os.path.join(get_data_dir(), "rules")

                if is_central:
                    prefix = "central:"
                elif is_project:
                    prefix = "project:"
                elif rules_dir == global_rules_dir:
                    # 全局规则目录
                    prefix = "global:"
                else:
                    # 配置的规则目录
                    prefix = "config0:"

                try:
                    for root, dirs, files in os.walk(rules_dir):
                        for filename in files:
                            if filename.endswith(".md"):
                                file_path = os.path.join(root, filename)
                                if os.path.isfile(file_path):
                                    # 计算相对于规则目录的路径作为规则名称
                                    rel_path = os.path.relpath(file_path, rules_dir)
                                    # 规则名称带来源前缀（如 project:deployment/version_release.md）
                                    prefixed_name = prefix + rel_path
                                    result["files"].append(prefixed_name)
                except Exception:
                    continue

        # 收集 rules.yaml 文件中的规则
        for desc, yaml_path in self._get_all_rules_yaml_files():
            if os.path.exists(yaml_path) and os.path.isfile(yaml_path):
                # 根据描述确定前缀
                if desc == "中心库":
                    prefix = "central_yaml:"
                elif desc == "项目":
                    prefix = "project_yaml:"
                elif desc == "全局":
                    prefix = "global_yaml:"
                else:
                    continue

                try:
                    with open(yaml_path, "r", encoding="utf-8", errors="replace") as f:
                        rules = yaml.safe_load(f) or {}
                        if isinstance(rules, dict):
                            for rule_name in rules.keys():
                                prefixed_name = prefix + rule_name
                                result["yaml"].append(prefixed_name)
                except Exception:
                    continue

        return result

    def load_all_rules(self, rule_names: Optional[str] = None) -> Tuple[str, Set[str]]:
        """加载所有规则并合并

        向后兼容方法：内部使用新的状态管理机制

        参数:
            rule_names: 规则名称列表（逗号分隔）

        返回:
            (merged_rules, loaded_rule_names): 合并后的规则字符串和已加载的规则名称列表
        """
        # 加载默认规则
        self._load_default_rules()

        loaded_rule_names: Set[str] = set()

        # 默认规则已通过 _load_default_rules 加载
        if "global_rule" in self._active_rules:
            loaded_rule_names.add("global_rule")
        if "project_rule" in self._active_rules:
            loaded_rule_names.add("project_rule")
        # 为了向后兼容，同时返回 builtin_rules_index（旧名称）和 builtin_rules（新名称）
        if "builtin_rules" in self._active_rules:
            loaded_rule_names.add("builtin_rules")
            loaded_rule_names.add("builtin_rules_index")  # 向后兼容

        # 如果指定了 rule_names，激活这些规则
        if rule_names:
            rule_list = [name.strip() for name in rule_names.split(",") if name.strip()]
            for rule_name in rule_list:
                if self.activate_rule(rule_name):
                    loaded_rule_names.add(rule_name)

        # 获取合并后的规则内容
        merged_rules = self.get_active_rules_content()

        if merged_rules:
            return merged_rules, loaded_rule_names
        return "", set()

    def activate_rule(self, name: str) -> bool:
        """激活指定名称的规则

        参数:
            name: 规则名称

        返回:
            bool: 是否成功激活
        """
        PrettyOutput.auto_print(f"🔍 [DEBUG] activate_rule 被调用，name = '{name}'")
        # 如果规则已经激活，直接返回True
        if name in self._active_rules:
            PrettyOutput.auto_print(f"🔍 [DEBUG] 规则 '{name}' 已经激活")
            return True

        # 尝试获取规则内容
        rule_content = self.get_named_rule(name)
        PrettyOutput.auto_print(
            f"🔍 [DEBUG] get_named_rule 返回结果: {bool(rule_content)}"
        )
        if rule_content is None:
            PrettyOutput.auto_print(f"🔍 [DEBUG] 规则 '{name}' 未找到，激活失败")
            return False

        # 加载规则到缓存
        self._loaded_rules[name] = rule_content
        # 激活规则
        self._active_rules.add(name)
        # 更新向后兼容的 loaded_rules
        self.loaded_rules.add(name)
        # 重新合并激活的规则
        self._merge_active_rules()
        PrettyOutput.auto_print(
            f"🔍 [DEBUG] 规则 '{name}' 激活成功，当前激活规则: {self._active_rules}"
        )

        return True

    def deactivate_rule(self, name: str) -> bool:
        """停用指定名称的规则

        参数:
            name: 规则名称

        返回:
            bool: 是否成功停用
        """
        # 如果规则未激活，返回False
        if name not in self._active_rules:
            return False

        # 停用规则
        self._active_rules.remove(name)
        # 从向后兼容的 loaded_rules 中移除
        if name in self.loaded_rules:
            self.loaded_rules.remove(name)
        # 重新合并激活的规则
        self._merge_active_rules()

        return True

    def get_active_rules_content(self) -> str:
        """获取所有激活规则的合并内容

        返回:
            str: 合并后的规则内容
        """
        return self._merged_rules

    def get_rule_status(self, name: str) -> str:
        """获取规则的状态

        参数:
            name: 规则名称

        返回:
            str: 规则状态（"active", "loaded", "not_loaded"）
        """
        if name in self._active_rules:
            return "active"
        elif name in self._loaded_rules:
            return "loaded"
        else:
            return "not_loaded"

    def _merge_active_rules(self) -> None:
        """合并所有激活的规则内容"""
        if not self._active_rules:
            self._merged_rules = ""
            return

        combined_parts = []
        for rule_name in sorted(self._active_rules):
            if rule_name in self._loaded_rules:
                combined_parts.append(self._loaded_rules[rule_name])

        if combined_parts:
            self._merged_rules = "\n\n".join(combined_parts)
        else:
            self._merged_rules = ""

    def _load_default_rules(self) -> None:
        """加载默认规则（global_rule 和 project_rule）"""
        # 加载全局规则
        global_rules = self.read_global_rules()
        if global_rules:
            self._loaded_rules["global_rule"] = global_rules
            self._active_rules.add("global_rule")
            self.loaded_rules.add("global_rule")

        # 加载项目规则
        project_rules = self.read_project_rule()
        if project_rules:
            self._loaded_rules["project_rule"] = project_rules
            self._active_rules.add("project_rule")
            self.loaded_rules.add("project_rule")

        # 加载内置规则索引
        builtin_rules_index = self._get_builtin_rules_index()
        if builtin_rules_index:
            # 使用 builtin_rules 作为键名（与 BUILTIN_RULES 字典保持一致）
            self._loaded_rules["builtin_rules"] = builtin_rules_index
            self._active_rules.add("builtin_rules")
            self.loaded_rules.add("builtin_rules")

        # 合并激活的规则
        self._merge_active_rules()

    def get_rule_preview(self, rule_name: str) -> str:
        """获取规则内容的前100个字符作为预览

        参数:
            rule_name: 规则名称

        返回:
            str: 规则内容的前100个字符，如果读取失败则返回 "--"
        """
        try:
            # 优先从缓存中获取
            if rule_name in self._loaded_rules:
                content: str | None = self._loaded_rules[rule_name]
            else:
                # 从文件或内置规则中获取
                content = self.get_named_rule(rule_name)

            if content:
                # 移除换行符和多余空格，保留前100个字符
                preview = content.replace("\n", " ").strip()
                return preview[:100] + "..." if len(preview) > 100 else preview
            return "--"
        except Exception:
            return "--"

    def get_all_rules_with_status(self) -> List[Tuple[str, str, bool, str]]:
        """获取所有规则及其加载状态

        返回:
            List[Tuple[str, str, bool, str]]: (规则名称, 内容预览, 是否已加载, 文件路径) 列表
        """
        import os
        from jarvis.jarvis_utils.config import get_data_dir

        rules_info = []
        available_rules = self.get_all_available_rule_names()

        # 辅助函数：根据规则名称获取文件路径
        def get_rule_file_path(rule_name: str) -> str:
            """获取规则文件的绝对路径"""
            # 处理带前缀的规则名称
            if ":" in rule_name:
                prefix, actual_name = rule_name.split(":", 1)
                if prefix == "project":
                    return os.path.join(self.root_dir, ".jarvis", "rules", actual_name)
                elif prefix == "global":
                    return os.path.join(get_data_dir(), "rules", actual_name)
                elif prefix == "central":
                    if self.central_repo_path:
                        return os.path.join(
                            self.central_repo_path, "rules", actual_name
                        )
                elif prefix.startswith("config"):
                    all_dirs = self._get_all_rules_dirs()
                    try:
                        config_num = int(prefix[6:])
                        if config_num + 2 < len(all_dirs):
                            return os.path.join(all_dirs[config_num + 2], actual_name)
                    except ValueError:
                        pass
                elif prefix.endswith("_yaml"):
                    # YAML规则显示为规则文件路径
                    for desc, yaml_path in self._get_all_rules_yaml_files():
                        if (
                            (prefix == "project_yaml" and desc == "项目")
                            or (prefix == "global_yaml" and desc == "全局")
                            or (prefix == "central_yaml" and desc == "中心库")
                        ):
                            return yaml_path
            return "--"

        # 处理内置规则
        for rule_name in available_rules.get("builtin", []):
            # 从带前缀的名称中提取实际规则名称（去掉 "builtin:" 前缀）
            actual_rule_name = (
                rule_name.split(":", 1)[1] if ":" in rule_name else rule_name
            )
            # 对于内置规则，直接使用 get_builtin_rule() 获取预览
            # 因为新格式的规则名称（如 architecture_design:clean_code.md）
            # 会被 get_named_rule() 误解析为带前缀的规则
            try:
                from jarvis.jarvis_agent.builtin_rules import get_builtin_rule

                rule_content = get_builtin_rule(actual_rule_name)
                if rule_content:
                    # 移除换行符和多余空格，保留前100个字符
                    preview = rule_content.replace("\n", " ").strip()
                    preview = preview[:100] + "..." if len(preview) > 100 else preview
                else:
                    preview = "--"
            except Exception:
                preview = "--"
            # 检查状态：只有明确激活的规则才显示为已激活
            # 同时检查带前缀和不带前缀的名称，向后兼容
            is_loaded = (
                rule_name in self._active_rules
                or actual_rule_name in self._active_rules
            )
            # 向后兼容：也检查旧的 loaded_rules
            is_loaded = (
                is_loaded
                or rule_name in self.loaded_rules
                or actual_rule_name in self.loaded_rules
            )
            # 获取内置规则的实际文件路径
            file_path = get_builtin_rule_path(actual_rule_name) or "内置规则"
            rules_info.append((rule_name, preview, is_loaded, file_path))

        # 处理文件规则
        for rule_name in available_rules.get("files", []):
            preview = self.get_rule_preview(rule_name)
            # 检查状态：只有明确激活的规则才显示为已激活
            is_loaded = rule_name in self._active_rules
            # 向后兼容：也检查旧的 loaded_rules
            is_loaded = is_loaded or rule_name in self.loaded_rules
            file_path = get_rule_file_path(rule_name)
            rules_info.append((rule_name, preview, is_loaded, file_path))

        # 处理YAML规则
        for rule_name in available_rules.get("yaml", []):
            preview = self.get_rule_preview(rule_name)
            # 检查状态：只有明确激活的规则才显示为已激活
            is_loaded = rule_name in self._active_rules
            # 向后兼容：也检查旧的 loaded_rules
            is_loaded = is_loaded or rule_name in self.loaded_rules
            file_path = get_rule_file_path(rule_name)
            rules_info.append((rule_name, preview, is_loaded, file_path))

        # 处理项目单个规则文件 .jarvis/rule
        project_rule_path = os.path.join(self.root_dir, ".jarvis", "rule")
        if os.path.exists(project_rule_path):
            preview = self.get_rule_preview("project_rule")
            # 检查状态：使用新的状态管理机制
            is_loaded = "project_rule" in self._active_rules
            # 向后兼容：也检查旧的 loaded_rules
            is_loaded = is_loaded or "project_rule" in self.loaded_rules
            rules_info.append(("project_rule", preview, is_loaded, project_rule_path))

        # 处理全局单个规则文件 ~/.jarvis/rule
        global_rule_path = os.path.join(get_data_dir(), "rule")
        if os.path.exists(global_rule_path):
            preview = self.get_rule_preview("global_rule")
            # 检查状态：使用新的状态管理机制
            is_loaded = "global_rule" in self._active_rules
            # 向后兼容：也检查旧的 loaded_rules
            is_loaded = is_loaded or "global_rule" in self.loaded_rules
            rules_info.append(("global_rule", preview, is_loaded, global_rule_path))

        # 处理内置规则索引文件 builtin/rules/rule.md
        try:
            from jarvis.jarvis_utils.template_utils import _get_builtin_dir

            builtin_dir = _get_builtin_dir()
            if builtin_dir is not None:
                builtin_rule_path = builtin_dir / "rules" / "rule.md"
                if builtin_rule_path.exists() and builtin_rule_path.is_file():
                    preview = self.get_rule_preview("builtin_rules")
                    # 检查状态：使用新的状态管理机制
                    is_loaded = "builtin_rules" in self._active_rules
                    # 向后兼容：也检查旧的 loaded_rules
                    is_loaded = is_loaded or "builtin_rules" in self.loaded_rules
                    rules_info.append(
                        ("builtin_rules", preview, is_loaded, str(builtin_rule_path))
                    )
        except Exception:
            pass

        # 排序：已激活的规则放在最底部，未激活的规则按目录排序
        # 使用 (is_loaded, rule_name) 作为排序键，确保 False(未激活) 在前，True(已激活) 在后
        rules_info.sort(key=lambda x: (x[2], x[0]))

        return rules_info
