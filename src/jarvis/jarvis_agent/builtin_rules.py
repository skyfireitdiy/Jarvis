# -*- coding: utf-8 -*-
"""Jarvis Agent 内置规则模块

提供一些优秀的开发实践规则，如 TDD、代码审查、重构等。
支持使用 jinja2 模板语法在规则文件中使用内置变量。
此模块可供所有 agent 使用。
"""

from pathlib import Path

from jarvis.jarvis_utils.template_utils import _get_builtin_dir, render_rule_template


# 内置规则字典：规则名称 -> 规则内容
# 此字典将在模块加载时通过 _load_builtin_rules() 函数动态填充
BUILTIN_RULES: dict[str, str] = {}


def _load_rules_from_directory(directory: Path, base_dir: Path) -> None:
    """从指定目录加载规则文件，支持jinja2模板渲染

    参数:
        directory: 规则文件所在目录
        base_dir: 基准目录（用于计算相对路径）
    """
    if not directory.exists():
        return

    for rule_file in directory.rglob("*.md"):
        # 计算相对于基准目录的相对路径
        # 例如：architecture_design/clean_code.md → architecture_design:clean_code.md
        try:
            relative_path = rule_file.relative_to(base_dir)
        except ValueError:
            # 如果文件不在基准目录下，使用文件名
            rule_name = rule_file.name
        else:
            # 将路径分隔符替换为冒号
            rule_name = str(relative_path).replace("/", ":").replace("\\", ":")

        try:
            with open(rule_file, "r", encoding="utf-8") as f:
                rule_content = f.read().strip()
                # 使用通用的渲染函数
                rendered_content = render_rule_template(
                    rule_content, rule_file.parent.as_posix()
                )
                if rendered_content:
                    BUILTIN_RULES[rule_name] = rendered_content
        except Exception:
            # 忽略加载失败的文件，不影响其他规则
            continue


def _load_builtin_rules() -> None:
    """加载所有内置规则"""
    # 使用辅助函数查找 builtin 目录
    # 支持从安装后的位置和源码位置查找
    builtin_dir = _get_builtin_dir()
    if builtin_dir is None:
        # 如果找不到 builtin 目录，静默返回（可能是开发环境或安装不完整）
        return

    # 基准目录（用于计算相对路径）
    rules_base_dir = builtin_dir / "rules"

    # 加载通用规则（rules 目录）
    _load_rules_from_directory(rules_base_dir, rules_base_dir)

    # 加载测试规则（testing 目录）
    _load_rules_from_directory(rules_base_dir / "testing", rules_base_dir)


# 在模块加载时自动加载所有规则
_load_builtin_rules()


def get_builtin_rule(rule_name: str) -> str | None:
    """获取内置规则

    参数:
        rule_name: 规则名称（不区分大小写）

    返回:
        str: 规则内容，如果未找到则返回 None
    """
    return BUILTIN_RULES.get(rule_name.lower())


def list_builtin_rules() -> list[str]:
    """列出所有可用的内置规则名称

    返回:
        list[str]: 规则名称列表
    """
    return list(BUILTIN_RULES.keys())


def get_builtin_rule_path(rule_name: str) -> str | None:
    """获取内置规则的文件路径

    参数:
        rule_name: 规则名称（新格式，如 architecture_design:clean_code.md）

    返回:
        str | None: 规则文件的绝对路径，如果未找到则返回 None
    """
    builtin_dir = _get_builtin_dir()
    if builtin_dir is None:
        return None

    # 规则名称在 BUILTIN_RULES 中以小写存储
    rule_name_lower = rule_name.lower()

    # 从新格式规则名称解析路径
    # architecture_design:clean_code.md → architecture_design/clean_code.md
    path_parts = rule_name_lower.replace(":", "/")

    # 在通用规则目录中查找
    general_rules_dir = builtin_dir / "rules"
    rule_file = general_rules_dir / path_parts
    if rule_file.exists() and rule_file.is_file():
        return str(rule_file.absolute())

    # 未找到
    return None
