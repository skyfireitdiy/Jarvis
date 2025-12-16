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

        from jarvis.jarvis_code_agent.code_agent_rules import RulesManager

        # 使用当前工作目录作为root_dir
        rules_manager = RulesManager(root_dir=os.getcwd())
        return rules_manager.get_named_rule(rule_name)
    except ImportError:
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

    # 检查是否包含Pin标记（需要最后处理）
    has_pin = "Pin" in special_tags

    # 获取替换映射表
    replace_map = get_replace_map()
    processed_tag = set()
    add_on_prompt = ""

    # 处理所有非Pin标记
    modified_input = user_input

    for tag in special_tags:
        # 优先处理会立即返回的特殊标记（不包含Pin）
        if tag == "Summary":
            summary = agent._summarize_and_clear_history()
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
            return "", False
        elif tag == "ReloadConfig":
            from jarvis.jarvis_utils.utils import load_config

            load_config()
            return "", True
        elif tag == "SaveSession":
            if agent.save_session():
                PrettyOutput.auto_print("✅ 会话已成功保存。正在退出...")
                sys.exit(0)
            else:
                PrettyOutput.auto_print("❌ 保存会话失败。")
            return "", True
        elif tag == "Quiet":
            agent.set_non_interactive(True)
            PrettyOutput.auto_print("🔇 已切换到静默模式（非交互模式）")
            modified_input = modified_input.replace("'<Quiet>'", "")
            continue
        elif tag == "Pin":
            # Pin标记最后处理，跳过此处
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
            rule_name = tag[5:]  # 去掉 "rule:" 前缀
            rule_content = _get_rule_content(rule_name)
            if rule_content:
                # 记录运行时加载的规则到CodeAgent
                try:
                    if agent is not None and hasattr(agent, "add_runtime_rule"):
                        agent.add_runtime_rule(rule_name)
                except Exception:
                    # 静默处理任何错误，不影响正常功能
                    pass

                separator = "\n" + "=" * 50 + "\n"
                modified_input = modified_input.replace(
                    f"'<{tag}>'", f"<rule>\n{rule_content}\n</rule>{separator}"
                )

    # 最后处理Pin标记
    if has_pin:
        # 移除所有Pin标记后的处理内容，追加到pin_content
        processed_content = modified_input.replace("'<Pin>'", "").strip()
        if processed_content:
            if agent.pin_content:
                agent.pin_content += "\n" + processed_content
            else:
                agent.pin_content = processed_content
            PrettyOutput.auto_print(f"📌 已固定内容: {processed_content[:50]}...")

        # 返回处理后的内容（移除了Pin标记）
        agent.set_addon_prompt(add_on_prompt)
        return processed_content, False

    # 设置附加提示词
    agent.set_addon_prompt(add_on_prompt)
    return modified_input, False
