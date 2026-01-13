# -*- coding: utf-8 -*-
"""Jarvis Agent 内置规则模块

提供一些优秀的开发实践规则，如 TDD、代码审查、重构等。
支持使用 jinja2 模板语法在规则文件中使用内置变量。
此模块可供所有 agent 使用。
"""

from pathlib import Path

from jarvis.jarvis_utils.template_utils import render_rule_template


# 内置规则字典：规则名称 -> 规则内容
# 此字典将在模块加载时通过 _load_builtin_rules() 函数动态填充
BUILTIN_RULES: dict[str, str] = {}


def _load_rules_from_directory(directory: Path) -> None:
    """从指定目录加载规则文件，支持jinja2模板渲染

    参数:
        directory: 规则文件所在目录
    """
    if not directory.exists():
        return

    for rule_file in directory.rglob("*.md"):
        rule_name = rule_file.stem  # 去掉 .md 后缀
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
    # 获取当前文件所在的项目根目录
    # 从 src/jarvis/jarvis_agent/builtin_rules.py 定位到项目根
    project_root = Path(__file__).parent.parent.parent.parent
    builtin_dir = project_root / "builtin"

    # 加载通用规则（rules 目录）
    _load_rules_from_directory(builtin_dir / "rules")

    # 加载测试规则（testing 目录）
    _load_rules_from_directory(builtin_dir / "rules" / "testing")


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
