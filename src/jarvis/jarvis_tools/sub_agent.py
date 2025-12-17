"""
sub_agent 工具
将子任务交给通用 Agent 执行，并返回执行结果。

约定：
- 必填参数：task, name, system_prompt, summary_prompt
- 可选参数：background
- 工具集：默认使用系统工具集（无需传入 use_tools）
- 继承父 Agent 的部分配置：model_group、input_handler、execute_tool_confirm、multiline_inputer、non_interactive、use_methodology、use_analysis；其他参数需显式提供
- 子Agent必须自动完成(auto_complete=True)且需要summary(need_summary=True)
"""

import json
from typing import Any, Dict

from jarvis.jarvis_utils.output import PrettyOutput

# -*- coding: utf-8 -*-

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_utils.globals import get_global_model_group


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
                "description": "子Agent名称（必填）",
            },
            "background": {
                "type": "string",
                "description": "任务背景与已知信息（可选，将与任务一并提供给子Agent）",
            },
            "system_prompt": {
                "type": "string",
                "description": "覆盖子Agent的系统提示词（必填）",
            },
            "summary_prompt": {
                "type": "string",
                "description": "覆盖子Agent的总结提示词（必填）",
            },
            "non_interactive": {
                "type": "boolean",
                "description": "是否启用无交互模式（可选，默认继承父Agent或系统默认）",
            },
        },
        "required": [
            "task",
            "name",
            "system_prompt",
            "summary_prompt",
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
            enhanced_task = (
                f"背景信息:\n{background}\n\n任务:\n{task}" if background else task
            )

            # 不继承父Agent，所有关键参数必须由调用方显式提供
            need_summary = True

            # 读取并校验必填参数
            system_prompt = str(args.get("system_prompt", "")).strip()
            summary_prompt = str(args.get("summary_prompt", "")).strip()
            agent_name = str(args.get("name", "")).strip()

            errors = []
            if not system_prompt:
                errors.append("system_prompt 不能为空")
            if not summary_prompt:
                errors.append("summary_prompt 不能为空")
            if not agent_name:
                errors.append("name 不能为空")
            if not background:
                errors.append("background 不能为空")

            if errors:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "; ".join(errors),
                }

            # 基于父Agent（如有）继承部分配置后创建子Agent
            parent_agent = args.get("agent", None)
            # 使用全局模型组（不再从 parent_agent 继承）
            parent_model_group = get_global_model_group()
            parent_execute_tool_confirm = None
            parent_multiline_inputer = None
            parent_use_methodology = None
            parent_use_analysis = None
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
            except Exception:
                # 安全兜底：无法从父Agent获取配置则保持为None，使用系统默认
                pass

            agent = Agent(
                system_prompt=system_prompt,
                name=agent_name,
                description="Temporary sub agent for executing a subtask",
                model_group=parent_model_group,
                summary_prompt=summary_prompt,
                auto_complete=True,
                use_tools=None,
                execute_tool_confirm=parent_execute_tool_confirm,
                need_summary=need_summary,
                multiline_inputer=parent_multiline_inputer,
                use_methodology=parent_use_methodology,
                use_analysis=parent_use_analysis,
                force_save_memory=None,
                files=None,
                non_interactive=True,
            )

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

            # 校验子Agent所用模型是否有效，必要时回退到平台可用模型
            try:
                platform = getattr(agent, "model", None)
                if platform:
                    available_models = platform.get_model_list()
                    if available_models:
                        available_names = [m for m, _ in available_models]
                        current_model_name = platform.name()
                        if current_model_name not in available_names:
                            PrettyOutput.auto_print(
                                f"⚠️ 检测到子Agent模型 {current_model_name} 不存在于平台 {platform.platform_name()} 的可用模型列表，将回退到 {available_names[0]}"
                            )
                            platform.set_model_name(available_names[0])
            except Exception:
                # 获取模型列表或设置模型失败时，保持原设置并继续，交由底层报错处理
                pass

            # 执行任务
            result = agent.run(enhanced_task)

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
