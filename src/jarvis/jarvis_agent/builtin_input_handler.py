# -*- coding: utf-8 -*-
import os
import re
from datetime import datetime
from typing import Any
from typing import List
from typing import Optional
from typing import Tuple

import yaml

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_platform_manager.main import chat_with_model
from jarvis.jarvis_utils.config import (
    get_replace_map,
    get_llm_group,
    set_llm_group,
    get_global_config_data,
)
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.input import (
    add_additional_completion_dir,
    get_choice,
    get_single_line_input,
)
from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_utils.utils import load_config

from jarvis.jarvis_agent.rules_manager import RulesManager
from jarvis.jarvis_agent.utils import build_fix_prompt
from jarvis.jarvis_code_agent.diff_visualizer import visualize_diff_enhanced
from jarvis.jarvis_utils.git_utils import (
    get_latest_commit_hash,
    get_diff_between_commits,
)


def _print_markdown_table(
    title: str,
    headers: List[str],
    rows: List[List[str]],
    header_styles: Optional[List[str]] = None,
) -> None:
    """输出 markdown 表格，兼容终端和前端。"""
    # 构建表头行
    header_row = "| " + " | ".join(headers) + " |"
    # 构建分隔行
    separator_row = "| " + " | ".join(["---"] * len(headers)) + " |"
    # 构建数据行
    data_rows = ["| " + " | ".join(row) + "|" for row in rows]
    # 组合 markdown 内容
    md_content = (
        f"## {title}\n\n"
        + header_row
        + "\n"
        + separator_row
        + "\n"
        + "\n".join(data_rows)
    )
    PrettyOutput.print_markdown(md_content)


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
            load_config()
            return "", True
        elif tag == "PrintConfig":
            config = get_global_config_data()
            PrettyOutput.auto_print("=== 全局配置 (YAML 格式) ===")
            try:
                # 转换为普通字典以便 YAML 序列化
                config_dict = dict(config)
                yaml_output = yaml.safe_dump(
                    config_dict,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                )
                PrettyOutput.auto_print(yaml_output)
            except Exception as e:
                PrettyOutput.auto_print(f"⚠️  YAML 序列化失败：{e}")
                PrettyOutput.auto_print(f"降级输出（字符串格式）:\n{config}")
            return "", True

        elif tag == "SetConfig":
            tag_marker = "'<SetConfig>'"
            tag_index = modified_input.find(tag_marker)
            if tag_index == -1:
                PrettyOutput.auto_print("❌ SetConfig 命令格式错误")
                return "", True

            # 提取标签后的参数部分
            arg_str = modified_input[tag_index + len(tag_marker) :].strip()

            if not arg_str:
                PrettyOutput.auto_print(
                    "❌ 用法：'<SetConfig>' key.path = value\n"
                    "示例：\n"
                    "  '<SetConfig>' llm_group = \"nebulacoder_v8_0\"\n"
                    "  '<SetConfig>' ENV.http_proxy = \"http://proxy:8080\"\n"
                    "  '<SetConfig>' build_validation_timeout = 60\n"
                    "  '<SetConfig>' TEMP_KEY delete"
                )
                return "", True

            config = get_global_config_data()

            try:
                # 检查是否是 delete 操作
                if arg_str.rstrip().endswith(" delete"):
                    key_path = arg_str.rsplit(" delete", 1)[0].strip()
                    if not key_path:
                        PrettyOutput.auto_print("❌ 错误：delete 操作需要指定 key 路径")
                        return "", True

                    # 删除嵌套键
                    success, message = _delete_nested_config(config, key_path)
                    if success:
                        PrettyOutput.auto_print(f"✅ 已删除配置：{key_path}")
                    else:
                        PrettyOutput.auto_print(f"❌ {message}")
                    return "", True

                # 解析 key = value 格式（只分割第一个 '='）
                if "=" not in arg_str:
                    PrettyOutput.auto_print(
                        "❌ 错误：缺少 '=' 分隔符，正确格式：key.path = value"
                    )
                    return "", True

                key_part, value_part = arg_str.split("=", 1)
                key_path = key_part.strip()
                value_str = value_part.strip()

                if not key_path:
                    PrettyOutput.auto_print("❌ 错误：key 不能为空")
                    return "", True

                # 安全解析值
                value = _safe_parse_value(value_str)

                # 设置嵌套键
                success, message = _set_nested_config(config, key_path, value)
                if success:
                    PrettyOutput.auto_print(
                        f"✅ 已设置配置：{key_path} = {repr(value)}"
                    )
                else:
                    PrettyOutput.auto_print(f"❌ {message}")

            except Exception as e:
                PrettyOutput.auto_print(f"❌ 解析错误：{e}")

            return "", True
        elif tag == "QuickConfig":
            from jarvis.jarvis_utils.quick_config import run_quick_config

            try:
                run_quick_config()
            except Exception as e:
                PrettyOutput.auto_print(f"❌ 快速配置失败: {e}")
            return "", True
        elif tag == "LLMAdd":
            from jarvis.jarvis_platform_manager.main import llm_add

            try:
                llm_add()
            except Exception as e:
                if "Exit" not in str(type(e).__name__):
                    PrettyOutput.auto_print(f"❌ 添加LLM配置失败: {e}")
            return "", True
        elif tag == "LLMDelete":
            from jarvis.jarvis_platform_manager.main import llm_delete

            try:
                llm_delete(name=None)
            except Exception as e:
                if "Exit" not in str(type(e).__name__):
                    PrettyOutput.auto_print(f"❌ 删除LLM配置失败: {e}")
            return "", True
        elif tag == "LLMUpdate":
            from jarvis.jarvis_platform_manager.main import llm_update

            try:
                llm_update(name=None)
            except Exception as e:
                if "Exit" not in str(type(e).__name__):
                    PrettyOutput.auto_print(f"❌ 更新LLM配置失败: {e}")
            return "", True
        elif tag == "LLMGroupAdd":
            from jarvis.jarvis_platform_manager.main import group_add

            try:
                group_add(name=None)
            except Exception as e:
                if "Exit" not in str(type(e).__name__):
                    PrettyOutput.auto_print(f"❌ 添加模型组失败: {e}")
            return "", True
        elif tag == "LLMGroupDelete":
            from jarvis.jarvis_platform_manager.main import group_delete

            try:
                group_delete(name=None)
            except Exception as e:
                if "Exit" not in str(type(e).__name__):
                    PrettyOutput.auto_print(f"❌ 删除模型组失败: {e}")
            return "", True
        elif tag == "LLMGroupUpdate":
            from jarvis.jarvis_platform_manager.main import group_update

            try:
                group_update(name=None)
            except Exception as e:
                if "Exit" not in str(type(e).__name__):
                    PrettyOutput.auto_print(f"❌ 更新模型组失败: {e}")
            return "", True
        elif tag == "LLMGroupSet":
            from jarvis.jarvis_platform_manager.main import group_set

            try:
                group_set(name=None)
            except Exception as e:
                if "Exit" not in str(type(e).__name__):
                    PrettyOutput.auto_print(f"❌ 设置模型组失败: {e}")
            return "", True
        elif tag == "Shell":
            # 生成 shell 命令（与 Alt+T 功能相同）
            from jarvis.jarvis_utils.input import _gen_shell_cmd_for_terminal

            return _gen_shell_cmd_for_terminal() + " # JARVIS-NOCONFIRM", True
        elif tag == "AddDir":
            tag_marker = "'<AddDir>'"
            tag_index = modified_input.find(tag_marker)
            inline_arg = ""
            if tag_index != -1:
                inline_arg = modified_input[tag_index + len(tag_marker) :].strip()
            if not inline_arg:
                PrettyOutput.auto_print(
                    "❌ AddDir 仅支持内联参数形式，例如：'<AddDir>' /path/to/dir"
                )
                return "", True
            target_dir = inline_arg.strip().strip('"').strip("'")
            if add_additional_completion_dir(target_dir):
                PrettyOutput.auto_print(f"✅ 已添加附加补全目录: {target_dir}")
            else:
                PrettyOutput.auto_print(f"❌ 目录不存在或不可用: {target_dir}")
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
                # 构建 markdown 表格
                headers = ["规则名称", "内容预览", "文件路径", "状态"]
                rows = []
                for rule_name, preview, is_loaded, file_path in rules_info:
                    if len(file_path) > 37:
                        file_path = file_path[:37] + "..."
                    status = "✅ 已激活" if is_loaded else "🔴 未激活"
                    rows.append([rule_name, preview, file_path, status])

                _print_markdown_table("📋 所有可用规则", headers, rows)
                PrettyOutput.auto_print(
                    f"总计: {len(rules_info)} 个规则", timestamp=False
                )

            return "", True
        elif tag == "UnloadRule":
            # 卸载已加载的规则
            loaded_rules = list(agent.rules_manager.loaded_rules)
            if not loaded_rules:
                _print_markdown_table(
                    "📋 已加载的规则", ["序号", "规则名称"], [["-", "无"]]
                )
                PrettyOutput.auto_print("⚠️  没有已加载的规则")
                return "", True

            # 构建表格数据
            rows = []
            for i, rule in enumerate(loaded_rules, 1):
                rows.append([str(i), rule])

            _print_markdown_table("📋 已加载的规则", ["序号", "规则名称"], rows)

            # 获取用户选择的序号
            idx_str = get_single_line_input(
                "请输入要卸载的规则序号（多个用逗号分隔，如 1,3,5）："
            )
            if not idx_str.strip():
                PrettyOutput.auto_print("❌ 未输入序号，操作已取消")
                return "", True

            # 解析并卸载
            try:
                indices = [int(x.strip()) for x in idx_str.split(",")]
                unloaded = []
                for idx in indices:
                    if 1 <= idx <= len(loaded_rules):
                        rule_to_unload = loaded_rules[idx - 1]
                        agent.rules_manager.unload_rule(rule_to_unload)
                        unloaded.append(rule_to_unload)
                    else:
                        PrettyOutput.auto_print(f"⚠️  无效序号：{idx}")

                if unloaded:
                    PrettyOutput.auto_print(
                        f"✅ 已卸载 {len(unloaded)} 个规则：{', '.join(unloaded)}"
                    )
                else:
                    PrettyOutput.auto_print("❌ 没有成功卸载任何规则")
            except ValueError:
                PrettyOutput.auto_print("❌ 输入格式错误，请输入数字序号")

            return "", True
        elif tag == "ClearRules":
            # 清空所有已加载的规则（保留默认规则）
            loaded_rules = list(agent.rules_manager.loaded_rules)
            if not loaded_rules:
                PrettyOutput.auto_print("📋 没有已加载的规则")
                return "", True

            # 遍历卸载所有规则
            count = 0
            for rule in loaded_rules:
                agent.rules_manager.unload_rule(rule)
                count += 1

            PrettyOutput.auto_print(f"✅ 已清空 {count} 个规则")
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

            sessions = agent.session._parse_session_files()

            if not sessions:
                PrettyOutput.auto_print("📋 未找到已保存的会话文件。")
            else:
                PrettyOutput.auto_print(f"📋 找到 {len(sessions)} 个会话文件：")
                for idx, (file_path, timestamp, session_name, _) in enumerate(
                    sessions, 1
                ):
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

            # 获取工具使用说明
            tool_usage = agent.get_tool_usage_prompt()

            # 构造修复提示词
            fix_prompt = build_fix_prompt(
                agent._last_response_content, error_msg, tool_usage
            )

            return fix_prompt, False
        elif tag == "SwitchModelGroup":
            # 处理切换模型组命令（仅在主 agent 中可用）
            if not getattr(agent, "allow_savesession", False):
                PrettyOutput.auto_print("⚠️ SwitchModel 命令仅在 jvs/jca 主程序中可用。")
                return "", True

            if switch_model_group(agent):
                PrettyOutput.auto_print("✅ 模型组切换成功。")
            else:
                PrettyOutput.auto_print("❌ 模型组切换失败或已取消。")
            return "", True
        elif tag == "SwitchModel":
            # 处理切换模型命令（在当前模型组的三个模型之间切换）
            if not getattr(agent, "allow_savesession", False):
                PrettyOutput.auto_print("⚠️ SwitchModel 命令仅在 jvs/jca 主程序中可用。")
                return "", True

            if switch_model(agent):
                PrettyOutput.auto_print("✅ 模型切换成功。")
            else:
                PrettyOutput.auto_print("❌ 模型切换失败或已取消。")
            return "", True
        elif tag == "SubAgent":
            # 启动子Agent执行任务，执行完毕后询问用户是否将结果反馈给当前Agent
            try:
                from jarvis.jarvis_agent.sub_agent import SubAgentTool
                from jarvis.jarvis_utils.input import get_multiline_input

                tag_marker = "'<SubAgent>'"
                tag_index = modified_input.find(tag_marker)
                if tag_index == -1:
                    PrettyOutput.auto_print("❌ Agent 命令格式错误")
                    return "", True

                # 调用多行输入获取任务描述
                PrettyOutput.auto_print(
                    "🤖 启动子Agent，请输入任务描述（Ctrl+C 取消）："
                )
                try:
                    task_desc = get_multiline_input("请输入子Agent的任务描述")
                    if not task_desc:
                        PrettyOutput.auto_print("⚠️  未输入任务描述，已取消")
                        return "", True
                except KeyboardInterrupt:
                    PrettyOutput.auto_print("⚠️  用户取消输入")
                    return "", True

                PrettyOutput.auto_print(f"🤖 启动子Agent执行任务：{task_desc[:50]}...")

                # 使用 SubAgentTool 创建子Agent
                sub_agent_tool = SubAgentTool()
                result = sub_agent_tool.execute(
                    {
                        "task": task_desc,
                        "name": "UserSubAgent",
                        "background": f"用户通过 @Agent 命令启动子任务。当前工作目录: {os.getcwd()}",
                        "agent": agent,
                    }
                )

                if result.get("success"):
                    stdout = result.get("stdout", "任务执行完成")
                    PrettyOutput.auto_print("✅ 子Agent任务执行完成")
                    PrettyOutput.auto_print(
                        f"📋 执行结果:\n{stdout[:500]}"
                        + ("..." if len(stdout) > 500 else "")
                    )

                    # 询问用户是否将结果反馈给当前Agent
                    from jarvis.jarvis_utils.input import user_confirm

                    if user_confirm(
                        "是否将子Agent的结果反馈给当前Agent？",
                        default=False,
                    ):
                        # 将结果作为提示词返回给当前Agent处理
                        return (
                            f"\n\n用户使用子Agent执行了任务：{task_desc}\n\n子Agent返回的结果是：\n{stdout}",
                            False,
                        )
                    else:
                        PrettyOutput.auto_print("ℹ️ 子Agent结果未反馈给当前Agent")
                        return "", True
                else:
                    stderr = result.get("stderr", "未知错误")
                    PrettyOutput.auto_print(f"❌ 子Agent执行失败: {stderr}")
                    return "", True

            except Exception as exc:
                PrettyOutput.auto_print(f"❌ 启动子Agent失败: {str(exc)}")
                return "", True
        elif tag == "Init":
            # 启动子Agent分析项目并生成.jarvis/rule.md项目综述文件
            try:
                from jarvis.jarvis_agent.sub_agent import SubAgentTool

                PrettyOutput.auto_print("🚀 启动子Agent分析项目并生成项目综述...")

                # 使用 SubAgentTool 创建子Agent
                sub_agent_tool = SubAgentTool()
                result = sub_agent_tool.execute(
                    {
                        "task": "你是一个项目分析专家。请严格按照以下内置规则中的原则和操作步骤执行：\n'<rule:builtin:development_workflow/init_project.md>'\n\n你的任务是深入分析当前项目，生成一份结构化的项目综述文件，并使用 edit_file 工具将其写入 .jarvis/rule.md 文件。\n\n具体要求：分析当前项目的目录结构、技术栈、架构设计、核心模块、构建方式、测试方式等，生成一份项目综述文件，写入到 .jarvis/rule.md 文件中。综述应包含：项目概述、技术栈、目录结构说明、核心模块说明、构建与运行方式、测试方式、关键配置等。请使用 edit_file 工具将内容写入 .jarvis/rule.md 文件。",
                        "name": "InitProjectAgent",
                        "background": f"用户通过 @Init 命令启动项目综述生成。当前工作目录: {os.getcwd()}",
                        "agent": agent,
                    }
                )

                if result.get("success"):
                    stdout = result.get("stdout", "项目综述生成完成")
                    PrettyOutput.auto_print("✅ 项目综述生成完成")
                    PrettyOutput.auto_print(
                        f"📋 执行结果:\n{stdout[:500]}"
                        + ("..." if len(stdout) > 500 else "")
                    )
                else:
                    stderr = result.get("stderr", "未知错误")
                    PrettyOutput.auto_print(f"❌ 项目综述生成失败: {stderr}")

            except Exception as exc:
                PrettyOutput.auto_print(f"❌ 启动项目综述Agent失败: {str(exc)}")

            return "", True
        elif tag == "TestCase":
            # 启动子Agent分析项目需求并生成文本化测试用例
            try:
                from jarvis.jarvis_agent.sub_agent import SubAgentTool

                PrettyOutput.auto_print("🚀 启动子Agent分析项目需求并生成测试用例...")

                # 使用 SubAgentTool 创建子Agent
                sub_agent_tool = SubAgentTool()
                result = sub_agent_tool.execute(
                    {
                        "task": "你是一个测试用例设计专家。请严格按照以下内置规则中的原则和操作步骤执行：\n'<rule:builtin:development_workflow/generate_testcase.md>'\n\n你的任务是深入分析当前项目的需求文档和代码接口，生成结构化的文本化测试用例，用于指导后续集成测试开发。\n\n具体要求：分析当前项目的需求文档、Spec文件（.jarvis/rules/spec/目录下）、代码接口定义，生成一份文本化测试用例文件，用于指导后续集成测试开发。测试用例应覆盖：功能测试、边界条件测试、异常处理测试、接口兼容性测试。每个测试用例需包含：用例编号、用例名称、前置条件、测试步骤、预期结果、优先级。请使用 edit_file 工具将测试用例写入 .jarvis/rules/spec/test_cases.md 文件。",
                        "name": "TestCaseAgent",
                        "background": f"用户通过 @TestCase 命令启动测试用例生成。当前工作目录: {os.getcwd()}",
                        "agent": agent,
                    }
                )

                if result.get("success"):
                    stdout = result.get("stdout", "测试用例生成完成")
                    PrettyOutput.auto_print("✅ 测试用例生成完成")
                    PrettyOutput.auto_print(
                        f"📋 执行结果:\n{stdout[:500]}"
                        + ("..." if len(stdout) > 500 else "")
                    )
                else:
                    stderr = result.get("stderr", "未知错误")
                    PrettyOutput.auto_print(f"❌ 测试用例生成失败：{stderr}")

            except Exception as exc:
                PrettyOutput.auto_print(f"❌ 启动测试用例Agent失败：{str(exc)}")

            return "", True
        elif tag == "SubCodeAgent":
            # 启动子CodeAgent执行代码任务，执行完毕后询问用户是否将结果反馈给当前Agent
            try:
                from jarvis.jarvis_code_agent.sub_code_agent import SubCodeAgentTool
                from jarvis.jarvis_utils.input import get_multiline_input

                tag_marker = "'<SubCodeAgent>'"
                tag_index = modified_input.find(tag_marker)
                if tag_index == -1:
                    PrettyOutput.auto_print("❌ SubCodeAgent 命令格式错误")
                    return "", True

                # 调用多行输入获取任务描述
                PrettyOutput.auto_print(
                    "💻 启动子CodeAgent，请输入任务描述（Ctrl+C 取消）："
                )
                try:
                    task_desc = get_multiline_input("请输入子CodeAgent的任务描述")
                    if not task_desc:
                        PrettyOutput.auto_print("⚠️  未输入任务描述，已取消")
                        return "", True
                except KeyboardInterrupt:
                    PrettyOutput.auto_print("⚠️  用户取消输入")
                    return "", True

                # 使用 SubCodeAgentTool 创建子CodeAgent
                sub_code_agent_tool = SubCodeAgentTool()
                result = sub_code_agent_tool.execute(
                    {
                        "task": task_desc,
                        "name": "UserSubCodeAgent",
                        "background": f"用户通过 @SubCodeAgent 命令启动子代码任务。当前工作目录: {os.getcwd()}",
                        "agent": agent,
                    }
                )

                if result.get("success"):
                    stdout = result.get("stdout", "任务执行完成")
                    PrettyOutput.auto_print("✅ 子CodeAgent任务执行完成")
                    PrettyOutput.auto_print(
                        f"📋 执行结果:\n{stdout[:500]}"
                        + ("..." if len(stdout) > 500 else "")
                    )

                    # 询问用户是否将结果反馈给当前Agent
                    from jarvis.jarvis_utils.input import user_confirm

                    if user_confirm(
                        "是否将子CodeAgent的结果反馈给当前Agent？",
                        default=False,
                    ):
                        # 将结果作为提示词返回给当前Agent处理
                        return (
                            f"\n\n用户使用子CodeAgent执行了任务：{task_desc}\n\n子CodeAgent返回的结果是：\n{stdout}",
                            False,
                        )
                    else:
                        PrettyOutput.auto_print("ℹ️ 子CodeAgent结果未反馈给当前Agent")
                        return "", True
                else:
                    stderr = result.get("stderr", "未知错误")
                    PrettyOutput.auto_print(f"❌ 子CodeAgent执行失败: {stderr}")
                    return "", True

            except Exception as exc:
                PrettyOutput.auto_print(f"❌ 启动子CodeAgent失败: {str(exc)}")
                return "", True
        elif tag == "Btw":
            # 处理临时聊天命令，不干扰主 agent 上下文
            try:
                PrettyOutput.auto_print("💬 进入临时聊天模式（输入 /bye 或空行退出）")
                chat_with_model("")
                PrettyOutput.auto_print("✅ 已返回主 Agent")
            except Exception as exc:
                PrettyOutput.auto_print(f"❌ 聊天失败: {str(exc)}")
            return "", True
        elif tag == "Commit":
            # 处理代码提交命令（仅在 code agent 中可用）
            if not hasattr(agent, "git_manager"):
                PrettyOutput.auto_print("⚠️ Commit 命令仅在 code agent 中可用。")
                return "", True

            PrettyOutput.auto_print("📝 正在提交代码...")

            # 获取当前的 end commit
            end_commit = get_latest_commit_hash()

            # 获取提交历史
            commits = agent.git_manager.show_commit_between(
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
                post_process_func=agent.post_process_manager.post_process_modified_files,  # type: ignore[attr-defined]
                skip_confirm=True,
            )

            # 提交完成后自动保存会话
            if getattr(agent, "allow_savesession", False):
                if agent.save_session():
                    PrettyOutput.auto_print("✅ 会话已成功保存。")
                else:
                    PrettyOutput.auto_print("❌ 保存会话失败。")

            # 返回提示信息，将追加到 addon_prompt
            return (
                "\n\n**🔖 代码已提交**：之前的任务目标已完成，代码已成功提交。\n\n**⚠️ 重要提示**：\n- 之前的目标已经完成，不用再关注\n- 代码走查时不用走查之前的修改\n- 请根据用户的新需求开始新的任务目标\n",
                True,
            )

        elif tag == "Pin":
            # Pin标记已在前面处理，跳过
            continue
        elif tag == "Diff":
            # 处理Diff命令，显示从start_commit到当前的变更

            # 检查agent是否有start_commit属性
            if not hasattr(agent, "start_commit"):
                PrettyOutput.auto_print("⚠️ 当前Agent没有start_commit属性，无法显示变更")
                return "", True

            start_commit = agent.start_commit
            if not start_commit:
                PrettyOutput.auto_print("⚠️ start_commit为空，无法显示变更")
                return "", True

            # 获取当前commit
            end_commit = get_latest_commit_hash()
            if not end_commit:
                PrettyOutput.auto_print("⚠️ 无法获取当前commit")
                return "", True

            # 获取diff
            PrettyOutput.auto_print(
                f"📊 正在获取从 {start_commit[:8]} 到 {end_commit[:8]} 的变更..."
            )
            diff_text = get_diff_between_commits(start_commit, end_commit)

            if not diff_text:
                PrettyOutput.auto_print("✅ 没有变更")
                return "", True

            # 显示diff
            PrettyOutput.auto_print("📝 变更内容:")
            visualize_diff_enhanced(diff_text, mode="side_by_side")
            return "", True

        elif tag == "InstallSkill":
            import subprocess

            tag_marker = "'<InstallSkill>'"
            tag_index = modified_input.find(tag_marker)
            inline_arg = ""
            if tag_index != -1:
                inline_arg = modified_input[tag_index + len(tag_marker) :].strip()
            if not inline_arg:
                PrettyOutput.auto_print(
                    "❌ InstallSkill 需要参数，用法：\n"
                    "  '<InstallSkill>' https://github.com/user/repo  # 从远程仓库安装\n"
                    "  '<InstallSkill>' /path/to/local/skill        # 从本地路径安装（软链接）"
                )
                return "", True

            skill_path = inline_arg.strip().strip('"').strip("'")
            skills_dir = os.path.join(
                os.path.expanduser("~"), ".jarvis", "rules", "skills"
            )
            os.makedirs(skills_dir, exist_ok=True)

            # 判断是远程链接还是本地路径
            if skill_path.startswith(("http://", "https://", "git@", "ssh://")):
                # 远程仓库：git clone
                # 从URL提取仓库名作为目录名
                repo_name = skill_path.rstrip("/").split("/")[-1]
                if repo_name.endswith(".git"):
                    repo_name = repo_name[:-4]
                target_dir = os.path.join(skills_dir, repo_name)

                if os.path.exists(target_dir):
                    PrettyOutput.auto_print(f"❌ Skill 目录已存在: {target_dir}")
                    return "", True

                try:
                    PrettyOutput.auto_print(
                        f"📦 正在从远程仓库安装 Skill: {skill_path}"
                    )
                    result = subprocess.run(
                        ["git", "clone", skill_path, target_dir],
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )
                    if result.returncode == 0:
                        PrettyOutput.auto_print(f"✅ Skill 安装成功: {target_dir}")
                    else:
                        # clone 失败时清理目录
                        if os.path.exists(target_dir):
                            import shutil

                            shutil.rmtree(target_dir, ignore_errors=True)
                        PrettyOutput.auto_print(
                            f"❌ git clone 失败: {result.stderr.strip()}"
                        )
                except subprocess.TimeoutExpired:
                    if os.path.exists(target_dir):
                        import shutil

                        shutil.rmtree(target_dir, ignore_errors=True)
                    PrettyOutput.auto_print("❌ git clone 超时（120秒）")
                except Exception as e:
                    if os.path.exists(target_dir):
                        import shutil

                        shutil.rmtree(target_dir, ignore_errors=True)
                    PrettyOutput.auto_print(f"❌ 安装失败: {e}")
            elif (
                os.path.isabs(skill_path)
                or skill_path.startswith("./")
                or skill_path.startswith("../")
            ):
                # 本地路径：创建软链接
                if not os.path.exists(skill_path):
                    PrettyOutput.auto_print(f"❌ 本地路径不存在: {skill_path}")
                    return "", True

                # 获取链接名（使用路径最后一段目录名）
                link_name = os.path.basename(os.path.normpath(skill_path))
                link_path = os.path.join(skills_dir, link_name)

                if os.path.exists(link_path) or os.path.islink(link_path):
                    PrettyOutput.auto_print(f"❌ Skill 链接已存在: {link_path}")
                    return "", True

                try:
                    abs_skill_path = os.path.abspath(skill_path)
                    if os.name == "nt":
                        # Windows: use copy instead of symlink
                        import shutil

                        if os.path.isdir(abs_skill_path):
                            shutil.copytree(abs_skill_path, link_path)
                        else:
                            shutil.copy2(abs_skill_path, link_path)
                        PrettyOutput.auto_print(
                            f"✅ Skill 文件复制成功: {link_path} <- {abs_skill_path}"
                        )
                    else:
                        os.symlink(abs_skill_path, link_path)
                        PrettyOutput.auto_print(
                            f"✅ Skill 软链接创建成功: {link_path} -> {abs_skill_path}"
                        )
                except Exception as e:
                    PrettyOutput.auto_print(f"❌ 创建链接/复制失败: {e}")
            else:
                PrettyOutput.auto_print(
                    "❌ 无效的参数，请提供远程仓库链接（http/https/ssh）或本地绝对路径"
                )

            return "", True
        elif tag == "Review":
            # 处理Review命令，执行单次代码审查
            # 检查是否为CodeAgent
            agent_type = getattr(agent, "_agent_type", "normal")
            if agent_type != "code_agent":
                PrettyOutput.auto_print(
                    "⚠ Review 命令仅支持 CodeAgent，当前 Agent 不支持代码审查"
                )
                return "", True

            # 创建 CodeReviewer 并执行单次审查
            from jarvis.jarvis_code_agent.code_reviewer import CodeReviewer

            reviewer = CodeReviewer(
                model=agent.model,
                start_commit=agent.start_commit
                if hasattr(agent, "start_commit")
                else None,
                non_interactive=agent.non_interactive
                if hasattr(agent, "non_interactive")
                else True,
                quick_mode=agent.quick_mode if hasattr(agent, "quick_mode") else False,
            )
            result = reviewer.run_single_review()

            # 审查通过，直接返回
            if result.get("ok", True):
                return "", True

            # 审查有问题，询问用户是否将问题反馈到下一轮对话
            issues = result.get("issues", [])
            if not issues:
                return "", True

            from jarvis.jarvis_utils.input import user_confirm

            if user_confirm(
                "是否将审查发现的问题反馈到下一轮对话进行修复？",
                default=True,
            ):
                # 使用CodeReviewer构建修复prompt
                review_prompt = CodeReviewer.build_review_fix_prompt(result)
                return review_prompt, False
            else:
                PrettyOutput.auto_print("ℹ️ 用户选择不反馈审查问题")
                return "", True

        elif tag == "SetMaxToken":
            # 处理SetMaxToken命令，设置最大输入Token数
            from jarvis.jarvis_utils.input import get_single_line_input

            value_str = get_single_line_input(
                "请输入最大输入Token数（<200000则设为200000，0则删除限制）："
            )
            if value_str is None:
                return "", True
            try:
                value = int(value_str.strip())
            except ValueError:
                PrettyOutput.auto_print("❌ 无效的输入，请输入一个整数")
                return "", True
            if value == 0:
                os.environ.pop("JARVIS_MAX_INPUT_TOKEN_COUNT", None)
                PrettyOutput.auto_print("✅ 已删除最大输入Token数限制")
            else:
                if value < 200000:
                    value = 200000
                    PrettyOutput.auto_print("⚠ 输入值小于200000，已自动设置为200000")
                os.environ["JARVIS_MAX_INPUT_TOKEN_COUNT"] = str(value)
                PrettyOutput.auto_print(f"✅ 最大输入Token数已设置为 {value}")
            return "", True
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
                processed_tag.add(tag)

                # 加载规则：调用 RulesManager.load_rule()
                # 使用 Agent 已有的 rules_manager 实例，而不是创建新的
                # Agent 一定存在 rules_manager 属性，直接使用
                rules_manager = agent.rules_manager
                loaded = rules_manager.load_rule(rule_name)

                if loaded:
                    # 将加载的规则添加到 agent.loaded_rule_names
                    if not hasattr(agent, "loaded_rule_names"):
                        agent.loaded_rule_names = set()
                    agent.loaded_rule_names.add(rule_name)
                    PrettyOutput.auto_print(f"🟢 已加载规则: {rule_name}")

                    # 从已加载的规则缓存中获取内容
                    rule_content = rules_manager._loaded_rules.get(rule_name)
                    if rule_content:
                        separator = "\n" + "=" * 50 + "\n"
                        modified_input = modified_input.replace(
                            f"'<{tag}>'", f"<rule>\n{rule_content}\n</rule>{separator}"
                        )

    # 设置附加提示词并返回处理后的内容
    agent.set_addon_prompt(add_on_prompt)
    return modified_input, False


def get_platform_type_from_agent(agent: Any) -> str:
    """根据 Agent 的 _model_type 属性返回平台类型

    参数:
        agent: Agent 实例

    返回:
        str: 平台类型，'smart'、'normal' 或 'cheap'
    """
    return getattr(agent, "_model_type", "normal")


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
        token_limit = 200000

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


def switch_platform_type(
    agent: Any, platform_type: str, preserve_model_group: bool = True
) -> bool:
    """切换平台类型（smart/normal/cheap），保持或更新模型组

    参数:
        agent: Agent 实例
        platform_type: 平台类型 ('smart', 'normal', 或 'cheap')
        preserve_model_group: 是否保持当前模型组不变（默认True）

    返回:
        bool: 是否切换成功
    """
    try:
        # 保存旧模型的消息
        old_messages = agent.model.get_messages()

        # 重新创建模型
        platform_registry = PlatformRegistry()
        if platform_type == "smart":
            agent.model = platform_registry.get_smart_platform()
        elif platform_type == "cheap":
            agent.model = platform_registry.get_cheap_platform()
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
        PrettyOutput.auto_print(f"❌ 切换平台类型失败: {e}")
        return False


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
        # 更新全局配置
        set_llm_group(new_model_group)

        # 使用通用的平台类型切换函数
        result = switch_platform_type(agent, platform_type, preserve_model_group=False)
        if result:
            agent._model_type = platform_type
        return result
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

    # 检查fzf是否可用
    import shutil

    fzf_available = shutil.which("fzf") is not None

    # 显示模型组列表（仅在fzf不可用时打印markdown表格）
    if not fzf_available:
        headers = ["编号", "模型组名称", "Smart", "Normal", "Cheap"]
        rows = []
        for idx, (group_name, smart_model, normal_model, cheap_model) in enumerate(
            groups, 1
        ):
            rows.append([str(idx), group_name, smart_model, normal_model, cheap_model])
        _print_markdown_table("📋 可用模型组", headers, rows)
        PrettyOutput.auto_print("")
    # 用户选择（使用交互式选择器）
    # 在fzf模式下显示详细信息，单行输入模式下显示简单名称
    if fzf_available:
        # fzf模式下显示详细信息
        choice_names = [
            f"{group_name} (Smart: {smart_model}, Normal: {normal_model}, Cheap: {cheap_model})"
            for group_name, smart_model, normal_model, cheap_model in groups
        ]
    else:
        # 单行输入模式下显示简单名称
        choice_names = [group_name for group_name, _, _, _ in groups]

    selected = get_choice("请选择模型组:", choice_names)

    # 处理取消情况（fzf按Esc或输入空字符串）
    if not selected:
        PrettyOutput.auto_print("🚫 已取消切换")
        return False

    # 提取选择的模型组名称（移除fzf模式下的详细信息）
    if fzf_available:
        # 从详细字符串中提取模型组名称
        selected_group_name = selected.split(" (")[0]
    else:
        selected_group_name = selected

    # 查找选择的模型组索引
    choice_idx = -1
    for idx, (group_name, _, _, _) in enumerate(groups):
        if group_name == selected_group_name:
            choice_idx = idx
            break

    if choice_idx == -1:
        PrettyOutput.auto_print("❌ 选择无效")
        return False

    new_group = groups[choice_idx][0]

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


def _check_context_and_compress_if_needed(
    agent: Any, target_platform_type: str
) -> bool:
    """检查切换到目标模型时是否会超出上下文限制，如果会则触发压缩

    参数:
        agent: Agent 实例
        target_platform_type: 目标模型类型（smart/normal/cheap）

    返回:
        bool: 如果上下文检查通过（或压缩成功）返回True，否则返回False
    """
    try:
        from jarvis.jarvis_utils.config import (
            get_max_input_token_count,
            get_smart_max_input_token_count,
            get_cheap_max_input_token_count,
        )

        # 获取目标模型的上下文限制
        if target_platform_type == "smart":
            target_max_tokens = get_smart_max_input_token_count()
        elif target_platform_type == "cheap":
            target_max_tokens = get_cheap_max_input_token_count()
        else:  # normal
            target_max_tokens = get_max_input_token_count()

        # 获取当前使用的 token 数
        current_used_tokens = agent.model.get_used_token_count()

        # 如果当前使用的 token 数超过目标模型的限制，触发压缩
        if current_used_tokens > target_max_tokens:
            PrettyOutput.auto_print(
                f"⚠️ 当前上下文 ({current_used_tokens} tokens) 超出目标模型限制 ({target_max_tokens} tokens)"
            )
            PrettyOutput.auto_print("🔄 正在触发上下文压缩...")

            # 触发压缩
            compression_success = agent._adaptive_compression()
            if not compression_success:
                PrettyOutput.auto_print("❌ 上下文压缩失败，无法切换到目标模型")
                return False

            # 压缩后重新检查
            new_used_tokens = agent.model.get_used_token_count()
            if new_used_tokens > target_max_tokens:
                PrettyOutput.auto_print(
                    f"❌ 压缩后上下文 ({new_used_tokens} tokens) 仍超出目标模型限制 ({target_max_tokens} tokens)"
                )
                return False

            PrettyOutput.auto_print(
                f"✅ 压缩成功，当前上下文: {new_used_tokens} tokens"
            )

        return True
    except Exception as e:
        PrettyOutput.auto_print(f"⚠️ 上下文检查失败: {e}")
        # 检查失败时允许继续切换（保持原有行为）
        return True


def switch_model(agent: Any) -> bool:
    """在当前模型组的三个模型（smart/normal/cheap）之间切换

    参数:
        agent: Agent 实例

    返回:
        bool: 是否切换成功
    """
    # 获取当前模型组
    current_group = get_llm_group()
    if not current_group:
        PrettyOutput.auto_print("❌ 未设置模型组")
        return False

    PrettyOutput.auto_print(f"📌 当前模型组: {current_group}")

    # 获取当前模型组的配置
    model_groups = _get_global_config().get("llm_groups", {})
    if not isinstance(model_groups, dict):
        PrettyOutput.auto_print("❌ 模型组配置不存在")
        return False

    group_config = model_groups.get(current_group)
    if not isinstance(group_config, dict):
        PrettyOutput.auto_print(f"❌ 模型组 '{current_group}' 配置不存在")
        return False

    # 获取三个模型
    smart_model = group_config.get("smart_llm", "")
    normal_model = group_config.get("normal_llm", "")
    cheap_model = group_config.get("cheap_llm", "")

    # 构建可用模型列表
    available_models = []
    if smart_model:
        available_models.append(("smart", "Smart", smart_model))
    if normal_model:
        available_models.append(("normal", "Normal", normal_model))
    if cheap_model:
        available_models.append(("cheap", "Cheap", cheap_model))

    if not available_models:
        PrettyOutput.auto_print("❌ 当前模型组没有可用的模型")
        return False

    # 获取当前使用的模型类型
    current_platform_type = get_platform_type_from_agent(agent)
    PrettyOutput.auto_print(f"📌 当前模型类型: {current_platform_type}")

    # 检查fzf是否可用
    import shutil

    fzf_available = shutil.which("fzf") is not None

    # 获取全局配置以获取 LLM 详情
    global_config = _get_global_config()
    llms_config = global_config.get("llms", {})

    # 显示模型列表（仅在fzf不可用时打印markdown表格）
    if not fzf_available:
        headers = ["编号", "类型", "模型名称", "多模态", "上下文长度", "状态"]
        rows = []
        for idx, (model_type, type_name, model_name) in enumerate(available_models, 1):
            # 获取 LLM 配置详情
            llm_detail = llms_config.get(model_name, {})
            max_tokens = llm_detail.get("max_input_token_count", "N/A")
            supports_multimodal = llm_detail.get("llm_config", {}).get(
                "supports_multimodal", False
            )
            multimodal_str = "✅" if supports_multimodal else "❌"
            status = "✓ 当前" if model_type == current_platform_type else ""
            rows.append(
                [
                    str(idx),
                    type_name,
                    model_name,
                    multimodal_str,
                    str(max_tokens),
                    status,
                ]
            )
        _print_markdown_table(f"📋 模型组 '{current_group}' 的可用模型", headers, rows)
        PrettyOutput.auto_print("")
    # 用户选择（使用交互式选择器）
    # 在fzf模式下显示详细信息，单行输入模式下显示简单名称
    if fzf_available:
        # fzf模式下显示详细信息
        choice_names = []
        for model_type, type_name, model_name in available_models:
            # 获取 LLM 配置详情
            llm_detail = llms_config.get(model_name, {})
            max_tokens = llm_detail.get("max_input_token_count", "N/A")
            supports_multimodal = llm_detail.get("llm_config", {}).get(
                "supports_multimodal", False
            )
            choice_names.append(
                f"{type_name}: {model_name} (多模态: {'✅' if supports_multimodal else '❌'}, 上下文: {max_tokens})"
            )
    else:
        # 单行输入模式下显示简单名称
        choice_names = [
            f"{type_name}: {model_name}"
            for _, type_name, model_name in available_models
        ]

    selected = get_choice("请选择模型:", choice_names)

    # 处理取消情况（fzf按Esc或输入空字符串）
    if not selected:
        PrettyOutput.auto_print("🚫 已取消切换")
        return False

    # 提取选择的模型类型名称（移除fzf模式下的详细信息）
    if fzf_available:
        # 从详细字符串中提取模型类型名称
        selected_type_name = selected.split(": ")[0]
    else:
        selected_type_name = selected.split(": ")[0]

    # 查找选择的模型索引
    choice_idx = -1
    for idx, (model_type, type_name, model_name) in enumerate(available_models):
        if type_name == selected_type_name:
            choice_idx = idx
            break

    if choice_idx == -1:
        PrettyOutput.auto_print("❌ 选择无效")
        return False

    selected_type, type_name, model_name = available_models[choice_idx]

    # 检查是否与当前模型相同
    if selected_type == current_platform_type:
        PrettyOutput.auto_print("⚠️ 已经在使用该模型")
        return False

    # 检查上下文限制，必要时触发压缩
    if not _check_context_and_compress_if_needed(agent, selected_type):
        PrettyOutput.auto_print("❌ 上下文检查失败，无法切换模型")
        return False

    PrettyOutput.auto_print(f"🔄 正在切换到 {type_name} 模型 '{model_name}'...")

    # 使用通用的平台类型切换函数
    if switch_platform_type(agent, selected_type):
        agent._model_type = selected_type
        PrettyOutput.auto_print(f"✅ 已成功切换到 {type_name} 模型 '{model_name}'")
        return True
    else:
        PrettyOutput.auto_print("❌ 切换模型失败")
        return False


def _safe_parse_value(value_str: str):
    """
    安全解析配置值，支持 YAML 兼容语法。

    解析策略：
    1. 尝试使用 yaml.safe_load() 解析（支持字符串、数字、布尔值、列表、字典）
    2. 如果解析失败，原样返回为字符串
    3. 绝对不使用 eval()，确保安全性

    Args:
        value_str: 值的字符串表示

    Returns:
        解析后的值（可能是任何 YAML 兼容类型）
    """

    value_str = value_str.strip()

    # 空字符串
    if not value_str:
        return ""

    # 尝试 YAML 解析
    try:
        parsed = yaml.safe_load(value_str)
        # yaml.safe_load 会将无引号的字符串解析为对应的类型
        # 如果是 None（如输入 "null"），返回原始字符串
        if parsed is None and value_str.lower() != "null":
            return value_str
        return parsed
    except yaml.YAMLError:
        # 解析失败，原样返回为字符串
        return value_str


def _set_nested_config(config, key_path: str, value) -> tuple[bool, str]:
    """
    设置嵌套配置键值。

    Args:
        config: 配置字典对象（CaseInsensitiveDict 或普通 dict）
        key_path: 点号分隔的键路径（如 "ENV.http_proxy"）
        value: 要设置的值

    Returns:
        (success: bool, message: str): 成功标志和消息
    """
    keys = key_path.split(".")

    if not keys or not keys[0]:
        return False, "key 路径不能为空"

    # 遍历到倒数第二个键，创建中间节点（如果需要）
    current = config
    for i, key in enumerate(keys[:-1]):
        if key not in current:
            # 自动创建中间的字典节点
            current[key] = {}
        elif not isinstance(current[key], (dict, type(config))):
            return False, f"路径冲突：'{key}' 已存在但不是字典类型（无法继续嵌套）"
        current = current[key]

    # 设置最后一个键的值
    final_key = keys[-1]
    try:
        current[final_key] = value
        return True, ""
    except Exception as e:
        return False, f"设置失败：{e}"


def _delete_nested_config(config, key_path: str) -> tuple[bool, str]:
    """
    删除嵌套配置键。

    Args:
        config: 配置字典对象
        key_path: 点号分隔的键路径

    Returns:
        (success: bool, message: str): 成功标志和消息
    """
    keys = key_path.split(".")

    if not keys or not keys[0]:
        return False, "key 路径不能为空"

    # 遍历到倒数第二个键
    current = config
    for i, key in enumerate(keys[:-1]):
        if key not in current:
            return False, f"路径不存在：'{key}' 在层级 {i + 1}"
        elif not isinstance(current[key], (dict, type(config))):
            return False, f"路径无效：'{key}' 不是字典类型，无法继续访问嵌套键"
        current = current[key]

    # 删除最后一个键
    final_key = keys[-1]
    if final_key not in current:
        return False, f"配置项不存在：{key_path}"

    try:
        del current[final_key]
        return True, ""
    except Exception as e:
        return False, f"删除失败：{e}"
