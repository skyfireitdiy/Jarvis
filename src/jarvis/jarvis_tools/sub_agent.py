"""
sub_agent 工具
将子任务交给通用 Agent 执行，并返回执行结果。

约定：
- 必填参数：task, name
- 可选参数：background
- 可选参数：summary_prompt
- 子Agent继承父Agent的对话历史，无需指定system_prompt
- 工具集：默认使用系统工具集（无需传入 use_tools）
- 继承父 Agent 的部分配置：model_group、input_handler、execute_tool_confirm、multiline_inputer、non_interactive、use_methodology、use_analysis；其他参数需显式提供
- 子Agent必须自动完成(auto_complete=True)且需要summary(need_summary=True)
"""

import json
from typing import Any, Dict

# -*- coding: utf-8 -*-

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_utils.config import get_llm_group


class SubAgentTool:
    """
    临时创建一个通用 Agent 执行子任务，执行完立即清理。
    - 不注册至全局
    - 使用系统默认/全局配置
    - 启用自动完成与总结
    """

    # 必须与文件名一致，供 ToolRegistry 自动注册
    name = "sub_agent"
    description = "将子任务交给通用 Agent 执行并返回结果（继承父Agent部分配置，自动完成并生成总结）。"
    parameters = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "要执行的子任务内容（必填）",
            },
            "name": {
                "type": "string",
                "description": "子Agent名称（可选，用于标识和区分不同的子Agent）",
            },
            "background": {
                "type": "string",
                "description": "任务背景与已知信息（可选，将与任务一并提供给子Agent）",
            },
            "goal": {
                "type": "string",
                "description": "子任务的目标描述（可选，用于明确子Agent的执行目标）",
            },
        },
        "required": [
            "task",
        ],
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行子任务并返回结果。
        返回:
          - success: 是否成功
          - stdout: 子 Agent 返回的结果（字符串或JSON字符串）
          - stderr: 错误信息（如有）
        """
        try:
            task: str = str(args.get("task", "")).strip()
            if not task:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "task 不能为空",
                }

            # 读取背景信息并组合任务
            background: str = str(args.get("background", "")).strip()
            goal: str = str(args.get("goal", "")).strip()

            # 组合任务内容
            task_parts = []
            if background:
                task_parts.append(f"背景信息:\n{background}")
            task_parts.append(f"任务:\n{task}")
            if goal:
                task_parts.append(f"目标:\n{goal}")
            enhanced_task = "\n\n".join(task_parts)

            # 不继承父Agent，所有关键参数必须由调用方显式提供
            need_summary = True

            # 读取子Agent名称
            agent_name = str(args.get("name", "")).strip()

            # 如果未提供名称，使用默认名称
            if not agent_name:
                agent_name = "SubAgent"

            # 基于父 Agent（如有）继承部分配置后创建子 Agent
            parent_agent = args.get("agent", None)
            # 获取父 Agent 的对话历史（在创建子 Agent 之前）
            parent_messages = None
            if parent_agent and hasattr(parent_agent, "model"):
                try:
                    all_messages = parent_agent.model.get_messages()
                    # 过滤掉系统消息，只保留对话历史（user/assistant/tool 消息）
                    parent_messages = [
                        msg for msg in all_messages if msg.get("role") != "system"
                    ]
                except Exception:
                    # 获取失败不影响主流程
                    pass
            # 使用当前模型组（不再从 parent_agent 继承）
            get_llm_group()
            parent_execute_tool_confirm = None
            parent_multiline_inputer = None
            parent_use_methodology = None
            parent_use_analysis = None
            parent_non_interactive = None  # 继承父Agent的非交互模式设置
            try:
                if parent_agent is not None:
                    parent_execute_tool_confirm = getattr(
                        parent_agent, "execute_tool_confirm", None
                    )
                    parent_multiline_inputer = getattr(
                        parent_agent, "multiline_inputer", None
                    )
                    parent_use_methodology = getattr(
                        parent_agent, "use_methodology", None
                    )
                    parent_use_analysis = getattr(parent_agent, "use_analysis", None)
                    parent_non_interactive = getattr(
                        parent_agent, "non_interactive", None
                    )
            except Exception:
                # 安全兜底：无法从父Agent获取配置则保持为None，使用系统默认
                pass

            agent = Agent(
                name=agent_name,
                description="Temporary sub agent for executing a subtask",
                auto_complete=True,
                use_tools=None,
                execute_tool_confirm=parent_execute_tool_confirm,
                need_summary=need_summary,
                multiline_inputer=parent_multiline_inputer,
                use_methodology=parent_use_methodology,
                use_analysis=parent_use_analysis,
                force_save_memory=None,
                files=None,
                non_interactive=parent_non_interactive
                if parent_non_interactive is not None
                else True,
            )

            # 设置继承的对话历史到子 Agent（在 Agent 创建后）
            if parent_messages and hasattr(agent, "model"):
                try:
                    # 在第一个用户消息前插入角色切换说明
                    role_switch_note = """【角色切换说明】
你现在是子Agent，已继承父Agent的完整对话历史。
你了解之前的分析过程和发现的问题。

重要说明：
- 任务列表已清空，你不继承父Agent的任务列表
- 专注于完成以下子任务，无需重复已完成的步骤
"""
                    # 找到第一个用户消息，在内容前插入角色切换说明
                    modified_messages = []
                    first_user_inserted = False
                    for msg in parent_messages:
                        if msg.get("role") == "user" and not first_user_inserted:
                            # 第一个用户消息，在内容前插入说明
                            new_msg = msg.copy()
                            new_msg["content"] = (
                                role_switch_note + "\n" + msg.get("content", "")
                            )
                            modified_messages.append(new_msg)
                            first_user_inserted = True
                        else:
                            modified_messages.append(msg)
                    agent.model.set_messages(modified_messages)
                    # 已继承父Agent历史记录，跳过首次运行初始化（规则选择等流程）
                    agent.first = False
                except Exception:
                    # 设置失败不影响主流程
                    pass

            # 禁用 sub_agent 和 sub_code_agent，避免无限递归
            try:
                # 获取当前启用的工具列表
                tool_registry = agent.get_tool_registry()
                if tool_registry:
                    current_tools = [
                        str(t.get("name"))
                        for t in tool_registry.get_all_tools()
                        if isinstance(t, dict) and t.get("name")
                    ]
                    # 过滤掉禁止的工具
                    forbidden_tools = {"sub_agent", "sub_code_agent"}
                    filtered_tools = [
                        t for t in current_tools if t not in forbidden_tools
                    ]
                    if filtered_tools:
                        agent.set_use_tools(filtered_tools)
            except Exception:
                # 如果禁用工具失败，不影响主流程
                pass

            # 执行任务
            result = agent.run(enhanced_task)

            # 合并子 agent 的记忆标签到父 agent
            if parent_agent and hasattr(parent_agent, "add_memory_tags"):
                try:
                    child_tags = agent.get_memory_tags()
                    if child_tags:
                        parent_agent.add_memory_tags(child_tags)
                except Exception:
                    # 合并标签失败不影响主要功能
                    pass

            # 规范化输出
            if isinstance(result, (dict, list)):
                stdout = json.dumps(result, ensure_ascii=False, indent=2)
            else:
                stdout = str(result) if result is not None else "任务执行完成"

            return {
                "success": True,
                "stdout": stdout,
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"执行子任务失败: {str(e)}",
            }
