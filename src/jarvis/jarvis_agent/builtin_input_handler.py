# -*- coding: utf-8 -*-
import io
import re
from typing import Any
from typing import List
from typing import Optional
from typing import Tuple

from jarvis.jarvis_utils.config import get_replace_map
from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_utils.input import get_single_line_input
from rich.table import Table
from rich.console import Console

# 模型组切换相关导入
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.config import get_llm_group
from jarvis.jarvis_utils.config import set_llm_group
from jarvis.jarvis_utils.config import get_global_config_data
from jarvis.jarvis_utils.embedding import get_context_token_count


def _print_table_for_terminal_or_frontend(table: Table) -> None:
    """根据运行环境选择终端富样式或前端纯文本输出表格。"""
    try:
        from jarvis.jarvis_gateway.manager import get_current_gateway

        has_gateway = get_current_gateway() is not None
    except Exception:
        has_gateway = False

    if has_gateway:
        string_io = io.StringIO()
        console_plain = Console(
            file=string_io,
            force_terminal=False,
            no_color=True,
            legacy_windows=False,
            width=100,
        )
        console_plain.print(table)
        PrettyOutput.auto_print(string_io.getvalue(), timestamp=False)
        return

    Console().print(table)


# 辅助函数：获取全局配置数据（避免导入时绑定问题）
def _get_global_config() -> Any:
    """获取全局配置数据的辅助函数

    使用函数调用而不是直接导入，避免在 set_global_config_data()
    重新赋值后使用旧引用。
    """
    return get_global_config_data()


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
        elif tag == "ListRule":
            # 列出所有规则及其状态
            # 使用 agent 的 rules_manager 实例，而不是创建新实例
            # 这样可以正确获取已加载的规则状态
            rules_manager = agent.rules_manager
            rules_info = rules_manager.get_all_rules_with_status()

            if not rules_info:
                PrettyOutput.auto_print("📋 未找到任何规则")
            else:
                table = Table(
                    title="📋 所有可用规则",
                    show_header=True,
                    header_style="bold magenta",
                    expand=True,
                )

                table.add_column("规则名称", style="cyan", no_wrap=False)
                table.add_column("内容预览", style="green")
                table.add_column("文件路径", style="yellow", no_wrap=False)
                table.add_column("状态", justify="center")

                for rule_name, preview, is_loaded, file_path in rules_info:
                    if len(file_path) > 37:
                        file_path = file_path[:37] + "..."
                    status = "✅ 已激活" if is_loaded else "🔴 未激活"
                    table.add_row(rule_name, preview, file_path, status)

                _print_table_for_terminal_or_frontend(table)
                PrettyOutput.auto_print(
                    f"总计: {len(rules_info)} 个规则", timestamp=False
                )

            return "", True
        elif tag == "SaveSession":
            # 检查是否允许使用SaveSession命令
            if not getattr(agent, "allow_savesession", False):
                PrettyOutput.auto_print("⚠️ SaveSession 命令仅在 jvs/jca 主程序中可用。")
                return "", True
            if agent.save_session():
                PrettyOutput.auto_print("✅ 会话已成功保存。")
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
                for idx, (file_path, timestamp, session_name) in enumerate(sessions, 1):
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
        elif tag == "AutoComplete":
            agent.set_non_interactive(True)
            agent.return_control_on_auto_complete = True
            PrettyOutput.auto_print(
                "🤖 已切换到自动完成模式：Agent 完成后将恢复交互并把控制权交还给用户"
            )
            modified_input = modified_input.replace("'<AutoComplete>'", "")
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
        elif tag == "SwitchModel":
            # 处理切换模型组命令（仅在主 agent 中可用）
            if not getattr(agent, "allow_savesession", False):
                PrettyOutput.auto_print("⚠️ SwitchModel 命令仅在 jvs/jca 主程序中可用。")
                return "", True

            if switch_model_group(agent):
                PrettyOutput.auto_print("✅ 模型组切换成功。")
            else:
                PrettyOutput.auto_print("❌ 模型组切换失败或已取消。")
            return "", True
        elif tag == "Commit":
            # 处理代码提交命令（仅在 code agent 中可用）
            if not hasattr(agent, "git_manager"):
                PrettyOutput.auto_print("⚠️ Commit 命令仅在 code agent 中可用。")
                return "", True

            from jarvis.jarvis_utils.git_utils import get_latest_commit_hash

            PrettyOutput.auto_print("📝 正在提交代码...")

            # 获取当前的 end commit
            end_commit = get_latest_commit_hash()

            # 获取提交历史
            commits = agent.git_manager.show_commit_history(
                agent.start_commit, end_commit
            )

            # 调用 handle_commit_confirmation 处理提交确认
            # 使用 agent 中存储的 prefix/suffix，不需要额外的后处理函数
            agent.git_manager.handle_commit_confirmation(
                commits,
                agent.start_commit,
                prefix=agent.prefix,
                suffix=agent.suffix,
                agent=agent,
                post_process_func=lambda files: None,  # 简化实现，不需要后处理
            )

            return "", True

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

                # 获取规则内容
                rule_content = _get_rule_content(rule_name)
                processed_tag.add(tag)

                if rule_content:
                    # 激活规则：调用 RulesManager.activate_rule()
                    # 使用 Agent 已有的 rules_manager 实例，而不是创建新的
                    # Agent 一定存在 rules_manager 属性，直接使用
                    rules_manager = agent.rules_manager
                    activated = rules_manager.activate_rule(rule_name)

                    # 将激活的规则添加到 agent.loaded_rule_names
                    if activated:
                        if not hasattr(agent, "loaded_rule_names"):
                            agent.loaded_rule_names = set()
                        agent.loaded_rule_names.add(rule_name)
                        PrettyOutput.auto_print(f"🟢 已激活规则: {rule_name}")

                    separator = "\n" + "=" * 50 + "\n"
                    modified_input = modified_input.replace(
                        f"'<{tag}>'", f"<rule>\n{rule_content}\n</rule>{separator}"
                    )

    # 设置附加提示词并返回处理后的内容
    agent.set_addon_prompt(add_on_prompt)
    return modified_input, False


def get_platform_type_from_agent(agent: Any) -> str:
    """根据 Agent 类型返回平台类型

    参数:
        agent: Agent 实例

    返回:
        str: 平台类型，'normal' 或 'smart'
    """
    agent_type = getattr(agent, "_agent_type", "normal")
    return "smart" if agent_type == "code_agent" else "normal"


def list_model_groups() -> Optional[List[Tuple[str, str, str, str]]]:
    """列出所有可用的模型组

    返回:
        Optional[List[Tuple[str, str, str, str]]]: 模型组列表，每个元素为 (group_name, smart_model, normal_model, cheap_model)
    """

    model_groups = _get_global_config().get("llm_groups", {})
    if not isinstance(model_groups, dict) or not model_groups:
        PrettyOutput.auto_print("📋 未找到任何模型组配置")
        return None

    groups = []
    for group_name, group_config in model_groups.items():
        if isinstance(group_config, dict):
            # 获取各平台的模型名称
            smart_model = group_config.get("smart_llm", "-")
            normal_model = group_config.get("normal_llm", "-")
            cheap_model = group_config.get("cheap_llm", "-")
            groups.append((group_name, smart_model, normal_model, cheap_model))

    return groups


def check_context_limit(
    agent: Any, new_model_group: str, platform_type: str = "normal"
) -> Tuple[bool, str]:
    """检查当前对话是否超出新模型的上下文限制

    参数:
        agent: Agent 实例
        new_model_group: 新模型组名称
        platform_type: 平台类型 ('normal' 或 'smart')

    返回:
        Tuple[bool, str]: (是否可以切换, 原因说明)
    """
    model_groups = _get_global_config().get("llm_groups", {})
    if not isinstance(model_groups, dict):
        return False, "模型组配置不存在"

    group_config = model_groups.get(new_model_group)
    if not isinstance(group_config, dict):
        return False, f"模型组 '{new_model_group}' 不存在"

    # 获取当前对话的 token 数
    current_tokens = 0
    if hasattr(agent, "model"):
        # 从 model 获取所有消息并计算 token
        try:
            messages_text = str(agent.model.get_messages())
            current_tokens = get_context_token_count(messages_text)
        except Exception:
            # 如果无法计算，使用粗略估计
            current_tokens = 0

    # 根据平台类型获取对应的 token 限制
    if platform_type == "smart":
        token_limit_key = "smart_max_input_token_count"
    else:
        token_limit_key = "max_input_token_count"

    # 从模型组配置中获取 token 限制
    token_limit = group_config.get(token_limit_key)
    if token_limit is None:
        # 尝试从 llms 引用中获取
        normal_llm = group_config.get("normal_llm")
        if normal_llm:
            llms = _get_global_config().get("llms", {})
            llm_config = llms.get(normal_llm, {})
            token_limit = llm_config.get("max_input_token_count")

    if token_limit is None:
        # 使用默认限制
        token_limit = 128000

    # 检查是否超出限制（留出 10% 的余量）
    if current_tokens > token_limit * 0.9:
        return (
            False,
            f"当前对话 ({current_tokens} tokens) 超出新模型限制 ({token_limit} tokens) 的 90%",
        )

    return (
        True,
        f"当前对话 ({current_tokens} tokens) 在新模型限制 ({token_limit} tokens) 范围内",
    )


def perform_switch(
    agent: Any, new_model_group: str, platform_type: str = "normal"
) -> bool:
    """执行模型组切换

    参数:
        agent: Agent 实例
        new_model_group: 新模型组名称
        platform_type: 平台类型 ('normal' 或 'smart')

    返回:
        bool: 是否切换成功
    """
    try:
        # 保存旧模型的消息
        old_messages = agent.model.get_messages()

        # 更新全局配置
        set_llm_group(new_model_group)

        # 重新创建模型
        platform_registry = PlatformRegistry()
        if platform_type == "smart":
            agent.model = platform_registry.get_smart_platform()
        else:
            agent.model = platform_registry.get_normal_platform()

        agent.model.set_suppress_output(False)
        agent.model.agent = agent

        # 将旧消息设置到新模型
        if old_messages:
            agent.model.set_messages(old_messages)

        # 将新模型设置到现有的 session 中
        agent.session.model = agent.model

        return True
    except Exception as e:
        PrettyOutput.auto_print(f"❌ 切换模型组失败: {e}")
        return False


def switch_model_group(agent: Any) -> bool:
    """切换模型组的主函数

    参数:
        agent: Agent 实例

    返回:
        bool: 是否切换成功
    """
    # 获取当前模型组
    current_group = get_llm_group() or "(未设置)"
    PrettyOutput.auto_print(f"📌 当前模型组: {current_group}")

    # 列出所有模型组
    groups = list_model_groups()
    if not groups:
        return False

    # 显示模型组列表
    table = Table(
        title="📋 可用模型组",
        show_header=True,
        header_style="bold magenta",
        expand=True,
    )
    table.add_column("编号", style="cyan", justify="center")
    table.add_column("模型组名称", style="green")
    table.add_column("Smart", style="cyan", justify="center")
    table.add_column("Normal", style="magenta", justify="center")
    table.add_column("Cheap", style="yellow", justify="center")

    for idx, (group_name, smart_model, normal_model, cheap_model) in enumerate(
        groups, 1
    ):
        table.add_row(str(idx), group_name, smart_model, normal_model, cheap_model)

    _print_table_for_terminal_or_frontend(table)

    # 用户选择（循环直到输入有效）
    PrettyOutput.auto_print("")
    while True:
        choice = get_single_line_input("请输入模型组编号 (0 取消): ").strip()

        if choice == "0":
            PrettyOutput.auto_print("🚫 已取消切换")
            return False

        try:
            choice_idx = int(choice) - 1
            if choice_idx < 0 or choice_idx >= len(groups):
                PrettyOutput.auto_print(f"❌ 无效的编号: {choice}，请重新输入")
                continue

            new_group = groups[choice_idx][0]
            break
        except ValueError:
            PrettyOutput.auto_print(f"❌ 无效的输入: {choice}，请输入数字")
            continue

    # 执行切换逻辑
    try:
        # 检查是否与当前模型组相同
        if new_group == current_group:
            PrettyOutput.auto_print("⚠️ 当前已使用该模型组")
            return False

        # 获取平台类型
        platform_type = get_platform_type_from_agent(agent)

        # 检查上下文限制
        can_switch, reason = check_context_limit(agent, new_group, platform_type)
        if not can_switch:
            PrettyOutput.auto_print(f"⚠️ {reason}")
            PrettyOutput.auto_print("🚫 已取消切换")
            return False
        else:
            PrettyOutput.auto_print(f"✅ {reason}")

        # 执行切换
        PrettyOutput.auto_print(f"🔄 正在切换到模型组 '{new_group}'...")
        if perform_switch(agent, new_group, platform_type):
            PrettyOutput.auto_print(f"✅ 已成功切换到模型组 '{new_group}'")
            return True
        else:
            return False
    except Exception as e:
        PrettyOutput.auto_print(f"❌ 切换失败: {e}")
        return False
