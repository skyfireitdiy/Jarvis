"""Core functionality for rules index CLI.

This module provides functions to retrieve and format rules index data.
"""

import os

from jarvis.jarvis_agent.rules_manager import RulesManager
from jarvis.jarvis_agent.builtin_rules import get_builtin_rule_path
from jarvis.jarvis_utils.output import PrettyOutput


def get_rules_index() -> dict:
    """Get all available rules index.

    Returns:
        A dictionary containing all rules grouped by source, or empty dict if failed.
    """
    try:
        # 使用当前工作目录作为项目根目录，以便正确识别项目规则
        root_dir = os.getcwd()
        manager = RulesManager(root_dir=root_dir)
        all_rules = manager.get_all_available_rule_names()
        return all_rules
    except Exception as e:
        PrettyOutput.auto_print(f"⚠️  获取规则索引失败: {e}")
        return {}


def get_rules_index_formatted(as_json: bool = False) -> str:
    """Get formatted rules index.

    Args:
        as_json: Whether to format as JSON.

    Returns:
        Formatted output string.
    """
    try:
        root_dir = os.getcwd()
        manager = RulesManager(root_dir=root_dir)
        result = manager._get_all_rules_index()
        return result if result else "❌ 未找到任何规则"
    except Exception as e:
        PrettyOutput.auto_print(f"⚠️  获取规则索引失败: {e}")
        return "❌ 获取规则索引失败"


def _extract_rule_description(rule_path: str) -> str:
    """Extract description from a rule file's YAML Front Matter.

    Args:
        rule_path: Absolute path to the rule file.

    Returns:
        Description string, or empty string if not found.
    """
    try:
        if not os.path.exists(rule_path):
            return ""
        with open(rule_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        # 提取 YAML Front Matter 中的 description
        if content.startswith("---"):
            lines = content.split("\n")
            for i, line in enumerate(lines[1:], 1):
                if line.strip() == "---":
                    break
                if line.startswith("description:"):
                    description = line.split(":", 1)[1].strip()
                    return description
        return ""
    except Exception:
        return ""


def format_rules_index(index: dict, as_json: bool = False) -> str:
    """Format the rules index for output.

    Args:
        index: The rules index dictionary (from get_rules_index).
        as_json: Whether to format as JSON.

    Returns:
        Formatted output string.
    """
    if not index:
        return "❌ 未找到任何规则"

    if as_json:
        import json

        return json.dumps(index, ensure_ascii=False, indent=2)

    # 格式化为 Markdown 输出
    output_lines = ["# Jarvis 规则索引\n"]

    # 内置规则
    if index.get("builtin"):
        output_lines.append("## 📦 内置规则 (builtin)\n")
        for rule_name in index["builtin"]:
            # 去掉 builtin: 前缀
            name = rule_name.split(":", 1)[1] if ":" in rule_name else rule_name
            # 获取内置规则路径
            rule_path = get_builtin_rule_path(name)
            description = _extract_rule_description(rule_path) if rule_path else ""
            if description:
                output_lines.append(f"- [{description}]({rule_path})")
            else:
                # 即使没有描述，也要显示路径或名称
                if rule_path:
                    output_lines.append(f"- {rule_path}")
                else:
                    # 如果路径获取失败，显示规则名称
                    output_lines.append(f"- builtin:{name}")
        output_lines.append("")

    # 文件规则（项目、全局、中心库等）
    if index.get("files"):
        output_lines.append("## 📁 规则文件 (files)\n")
        # 按来源分组，同时存储完整路径
        by_source: dict[str, list[tuple[str, str]]] = {}
        for rule_name in index["files"]:
            if ":" in rule_name:
                prefix = rule_name.split(":", 1)[0]
                name = rule_name.split(":", 1)[1]
            else:
                prefix = "unknown"
                name = rule_name

            source_labels = {
                "project": "项目",
                "global": "全局",
                "central": "中心库",
                "config0": "配置目录",
            }
            label = source_labels.get(prefix, prefix)
            if label not in by_source:
                by_source[label] = []
            # 存储完整路径以便提取描述
            by_source[label].append((rule_name, name))

        # 按来源输出
        for source, rules_list in sorted(by_source.items()):
            output_lines.append(f"### {source}\n")
            for full_name, rel_name in sorted(rules_list, key=lambda x: x[1]):
                # 根据前缀确定实际文件路径
                rule_path = ""
                if full_name.startswith("project:"):
                    rule_path = os.path.join(os.getcwd(), ".jarvis", "rules", rel_name)
                elif full_name.startswith("global:"):
                    rule_path = os.path.join(
                        os.path.expanduser("~"), ".jarvis", "rules", rel_name
                    )
                elif full_name.startswith("central:"):
                    # 中心库路径，暂时不处理
                    rule_path = ""
                elif full_name.startswith("config0:"):
                    rule_path = os.path.join(os.getcwd(), rel_name)

                description = _extract_rule_description(rule_path) if rule_path else ""
                if description:
                    output_lines.append(f"- [{description}]({rule_path})")
                else:
                    # 即使没有描述，也要显示绝对路径
                    output_lines.append(f"- {rule_path}")
            output_lines.append("")

    # YAML 规则
    if index.get("yaml"):
        output_lines.append("## 📝 YAML 规则\n")
        # 按来源分组
        by_source_yaml: dict[str, list[str]] = {}
        for rule_name in index["yaml"]:
            if ":" in rule_name:
                prefix = rule_name.split(":", 1)[0]
                name = rule_name.split(":", 1)[1]
            else:
                prefix = "unknown"
                name = rule_name

            source_labels = {
                "central_yaml": "中心库",
                "project_yaml": "项目",
                "global_yaml": "全局",
            }
            label = source_labels.get(prefix, prefix)
            if label not in by_source_yaml:
                by_source_yaml[label] = []
            by_source_yaml[label].append(name)

        # 按来源输出
        for source, rules in sorted(by_source_yaml.items()):
            output_lines.append(f"### {source}\n")
            for rule in sorted(rules):
                output_lines.append(f"- `{rule}`")
            output_lines.append("")

    return "\n".join(output_lines)
