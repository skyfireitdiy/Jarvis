# -*- coding: utf-8 -*-
import re
import sys
from typing import Any
from typing import Tuple

from jarvis.jarvis_utils.config import get_replace_map
from jarvis.jarvis_utils.output import PrettyOutput


def _get_rule_content(rule_name: str) -> str | None:
    """获取规则内容

    参数:
        rule_name: 规则名称

    返回:
        str | None: 规则内容，如果未找到则返回 None
    """
    try:
        import os

        from jarvis.jarvis_agent.rules_manager import RulesManager

        # 使用当前工作目录作为root_dir
        rules_manager = RulesManager(root_dir=os.getcwd())
        rule_content = rules_manager.get_named_rule(rule_name)

        if rule_content:
            # 尝试查找规则文件路径
            rule_file_path = _find_rule_file_path(rules_manager, rule_name)
            if rule_file_path:
                # 在规则内容前添加路径注释
                path_comment = f"<!-- 规则文件路径: {rule_file_path} -->\n"
                return path_comment + rule_content

        return rule_content
    except ImportError:
        return None


def _find_rule_file_path(rules_manager: Any, rule_name: str) -> str | None:
    """查找规则文件的绝对路径

    参数:
        rules_manager: RulesManager 实例
        rule_name: 规则名称

    返回:
        str | None: 规则文件绝对路径，如果未找到则返回 None
    """
    import os

    try:
        # 按优先级查找规则文件
        # 优先级 1: 项目 rules.yaml 文件
        project_rules_yaml = os.path.join(
            rules_manager.root_dir, ".jarvis", "rules.yaml"
        )
        if os.path.exists(project_rules_yaml):
            import yaml

            with open(project_rules_yaml, "r", encoding="utf-8") as f:
                rules = yaml.safe_load(f) or {}
            if rule_name in rules:
                # 从 rules.yaml 读取的规则，文件路径就是 yaml 文件路径
                return os.path.abspath(project_rules_yaml)

        # 优先级 2: 项目 rules 目录
        project_rules_dir = os.path.join(rules_manager.root_dir, ".jarvis", "rules")
        if os.path.exists(project_rules_dir) and os.path.isdir(project_rules_dir):
            rule_file = os.path.join(project_rules_dir, rule_name + ".md")
            if os.path.exists(rule_file):
                return os.path.abspath(rule_file)

        # 优先级 3: 全局 rules.yaml 文件
        from jarvis.jarvis_utils.config import get_data_dir

        global_rules_yaml = os.path.join(get_data_dir(), "rules.yaml")
        if os.path.exists(global_rules_yaml):
            import yaml

            with open(global_rules_yaml, "r", encoding="utf-8") as f:
                rules = yaml.safe_load(f) or {}
            if rule_name in rules:
                return os.path.abspath(global_rules_yaml)

        # 优先级 4: 全局 rules 目录
        global_rules_dir = os.path.join(get_data_dir(), "rules")
        if os.path.exists(global_rules_dir) and os.path.isdir(global_rules_dir):
            rule_file = os.path.join(global_rules_dir, rule_name + ".md")
            if os.path.exists(rule_file):
                return os.path.abspath(rule_file)

        # 优先级 5: 中心规则仓库
        if rules_manager.central_repo_path and os.path.exists(
            rules_manager.central_repo_path
        ):
            central_rules_dir = os.path.join(rules_manager.central_repo_path, "rules")
            if os.path.exists(central_rules_dir) and os.path.isdir(central_rules_dir):
                rule_file = os.path.join(central_rules_dir, rule_name + ".md")
                if os.path.exists(rule_file):
                    return os.path.abspath(rule_file)
            else:
                rule_file = os.path.join(
                    rules_manager.central_repo_path, rule_name + ".md"
                )
                if os.path.exists(rule_file):
                    return os.path.abspath(rule_file)

        # 优先级 6: 内置规则
        from jarvis.jarvis_utils.template_utils import _get_builtin_dir

        builtin_dir = _get_builtin_dir()
        if builtin_dir:
            # 在 builtin/rules 目录中查找
            from pathlib import Path

            builtin_rules_dir = builtin_dir / "rules"
            if builtin_rules_dir.exists() and builtin_rules_dir.is_dir():
                builtin_rule_file: Path = builtin_rules_dir / (rule_name + ".md")
                if builtin_rule_file.exists() and builtin_rule_file.is_file():
                    return str(builtin_rule_file.absolute())

            # 在 builtin/rules/testing 目录中查找
            testing_rules_dir = builtin_rules_dir / "testing"
            if testing_rules_dir.exists() and testing_rules_dir.is_dir():
                builtin_rule_file = testing_rules_dir / (rule_name + ".md")
                if builtin_rule_file.exists() and builtin_rule_file.is_file():
                    return str(builtin_rule_file.absolute())

        return None
    except Exception:
        return None


def builtin_input_handler(user_input: str, agent_: Any) -> Tuple[str, bool]:
    """
    处理内置的特殊输入标记，并追加相应的提示词

    参数：
        user_input: 用户输入
        agent: 代理对象

    返回：
        Tuple[str, bool]: 处理后的输入和是否需要进一步处理
    """
    from jarvis.jarvis_agent import Agent

    agent: Agent = agent_
    # 查找特殊标记
    special_tags = re.findall(r"'<([^>]+)>'", user_input)

    if not special_tags:
        return user_input, False

    # 获取替换映射表
    replace_map = get_replace_map()
    processed_tag = set()
    add_on_prompt = ""
    modified_input = user_input

    # 优先处理Pin标记
    if "Pin" in special_tags:
        pin_marker = "'<Pin>'"
        pin_index = modified_input.find(pin_marker)

        if pin_index != -1:
            # 分割为Pin标记前和Pin标记后的内容
            before_pin = modified_input[:pin_index]
            after_pin = modified_input[pin_index + len(pin_marker) :]

            # 将Pin标记之后的内容追加到pin_content
            after_pin_stripped = after_pin.strip()
            if after_pin_stripped:
                if agent.pin_content:
                    agent.pin_content += "\n" + after_pin_stripped
                else:
                    agent.pin_content = after_pin_stripped
                PrettyOutput.auto_print(f"📌 已固定内容: {after_pin_stripped[:50]}...")

            # 移除Pin标记，保留前后内容
            modified_input = before_pin + after_pin

    # 处理其他标记
    for tag in special_tags:
        # 优先处理会立即返回的特殊标记（不包含Pin）
        if tag == "Summary":
            # 直接使用全量总结
            summary = agent._summarize_and_clear_history(trigger_reason="用户指令触发")
            memory_tags_prompt = agent.memory_manager.prepare_memory_tags_prompt()
            prompt = ""
            if summary:
                # 将摘要和记忆标签设置为新会话的初始提示
                prompt = summary + "\n" + memory_tags_prompt
            else:
                # 即使没有摘要，也确保设置记忆标签作为新会话的初始提示
                prompt = memory_tags_prompt
            return prompt, True
        elif tag == "Clear":
            agent.clear_history()
            return "", True
        elif tag == "ToolUsage":
            agent.set_addon_prompt(agent.get_tool_usage_prompt())
            continue
        elif tag == "ReloadConfig":
            from jarvis.jarvis_utils.utils import load_config

            load_config()
            return "", True
        elif tag == "SaveSession":
            # 检查是否允许使用SaveSession命令
            if not getattr(agent, "allow_savesession", False):
                PrettyOutput.auto_print("⚠️ SaveSession 命令仅在 jvs/jca 主程序中可用。")
                return "", True
            if agent.save_session():
                PrettyOutput.auto_print("✅ 会话已成功保存。正在退出...")
                sys.exit(0)
            else:
                PrettyOutput.auto_print("❌ 保存会话失败。")
            return "", True
        elif tag == "RestoreSession":
            # 检查是否允许使用RestoreSession命令
            if not getattr(agent, "allow_savesession", False):
                PrettyOutput.auto_print(
                    "⚠️ RestoreSession 命令仅在 jvs/jca 主程序中可用。"
                )
                return "", True
            if agent.restore_session():
                PrettyOutput.auto_print("✅ 会话已成功恢复。")
            else:
                PrettyOutput.auto_print("❌ 恢复会话失败。")
            return "", True
        elif tag == "ListSessions":
            # 列出所有已保存的会话文件
            import os

            sessions = agent.session._parse_session_files()

            if not sessions:
                PrettyOutput.auto_print("📋 未找到已保存的会话文件。")
            else:
                PrettyOutput.auto_print(f"📋 找到 {len(sessions)} 个会话文件：")
                for idx, (file_path, timestamp) in enumerate(sessions, 1):
                    # 获取文件大小
                    try:
                        file_size = os.path.getsize(file_path)
                        size_str = f"({file_size / 1024:.1f} KB)"
                    except OSError:
                        size_str = "(未知大小)"

                    # 格式化时间戳显示
                    if timestamp:
                        # 时间戳格式：YYYYMMDD_HHMMSS
                        try:
                            from datetime import datetime

                            dt = datetime.strptime(timestamp, "%Y%m%d_%H%M%S")
                            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            time_str = timestamp
                    else:
                        time_str = "(无时间戳)"

                    PrettyOutput.auto_print(f"  {idx}. {os.path.basename(file_path)}")
                    PrettyOutput.auto_print(f"     时间: {time_str}  大小: {size_str}")
            return "", True
        elif tag == "Quiet":
            agent.set_non_interactive(True)
            PrettyOutput.auto_print("🔇 已切换到无人值守模式（非交互模式）")
            modified_input = modified_input.replace("'<Quiet>'", "")
            continue
        elif tag == "FixToolCall":
            # 处理修复工具调用的命令
            if not agent._last_response_content:
                PrettyOutput.auto_print("⚠️ 没有找到需要修复的工具调用内容")
                return "", True

            PrettyOutput.auto_print("🔧 正在构造修复提示词...")
            error_msg = "用户请求手动修复工具调用"

            # 导入提示词构造函数
            from jarvis.jarvis_agent.utils import build_fix_prompt

            # 获取工具使用说明
            tool_usage = agent.get_tool_usage_prompt()

            # 构造修复提示词
            fix_prompt = build_fix_prompt(
                agent._last_response_content, error_msg, tool_usage
            )

            return fix_prompt, False

        elif tag == "Pin":
            # Pin标记已在前面处理，跳过
            continue

        # 处理普通替换标记
        if tag in replace_map:
            processed_tag.add(tag)
            if (
                "append" in replace_map[tag]
                and replace_map[tag]["append"]
                and tag not in processed_tag
            ):
                modified_input = modified_input.replace(f"'<{tag}>'", "")
                add_on_prompt += replace_map[tag]["template"] + "\n"
            else:
                modified_input = modified_input.replace(
                    f"'<{tag}>'", replace_map[tag]["template"]
                )
        elif tag.startswith("rule:"):
            # 处理 rule:xxx 格式的规则标记
            if tag not in processed_tag:
                rule_name = tag[5:]  # 去掉 "rule:" 前缀
                rule_content = _get_rule_content(rule_name)
                processed_tag.add(tag)
                if rule_content:
                    separator = "\n" + "=" * 50 + "\n"
                    modified_input = modified_input.replace(
                        f"'<{tag}>'", f"<rule>\n{rule_content}\n</rule>{separator}"
                    )

    # 设置附加提示词并返回处理后的内容
    agent.set_addon_prompt(add_on_prompt)
    return modified_input, False
