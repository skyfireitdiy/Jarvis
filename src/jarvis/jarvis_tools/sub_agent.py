# -*- coding: utf-8 -*-
"""
sub_agent 工具
将子任务交给通用 Agent 执行，并返回执行结果。

约定：
- 仅接收一个参数：task
- 不依赖父 Agent，所有配置使用系统默认与全局变量
- 子Agent必须自动完成(auto_complete=True)且需要summary(need_summary=True)
"""
from typing import Any, Dict, Optional
import json

from jarvis.jarvis_agent import Agent, origin_agent_system_prompt
from jarvis.jarvis_utils.globals import delete_agent


class SubAgentTool:
    """
    临时创建一个通用 Agent 执行子任务，执行完立即清理。
    - 不注册至全局
    - 使用系统默认/全局配置
    - 启用自动完成与总结
    """

    # 必须与文件名一致，供 ToolRegistry 自动注册
    name = "sub_agent"
    description = "将子任务交给通用 Agent 执行，并返回执行结果（使用系统默认配置，自动完成并生成总结）。"
    parameters = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "要执行的子任务内容（必填）",
            },
            "background": {
                "type": "string",
                "description": "任务背景与已知信息（可选，将与任务一并提供给子Agent）",
            },
        },
        "required": ["task"],
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

            # 读取背景信息并组合任务
            background: str = str(args.get("background", "")).strip()
            enhanced_task = (
                f"背景信息:\n{background}\n\n任务:\n{task}" if background else task
            )

            # 继承父Agent的运行参数（用于覆盖默认值）；若无父Agent则使用默认/全局配置
            parent_agent = args.get("agent")
            # 如未注入父Agent，尝试从全局获取当前或任一已注册Agent
            if parent_agent is None:
                try:
                    from jarvis.jarvis_utils import globals as G  # 延迟导入避免循环

                    curr = getattr(G, "current_agent_name", "")
                    if curr:
                        parent_agent = getattr(G, "global_agents", {}).get(curr)
                    if parent_agent is None and getattr(G, "global_agents", {}):
                        try:
                            parent_agent = next(iter(G.global_agents.values()))
                        except Exception:
                            parent_agent = None
                except Exception:
                    parent_agent = None
            # 默认/全局
            system_prompt = origin_agent_system_prompt
            need_summary = True
            auto_complete = True

            # 可继承参数
            model_group = None
            summary_prompt = None
            execute_tool_confirm = None
            use_methodology = None
            use_analysis = None
            force_save_memory = None
            use_tools: list[str] = []

            try:
                if parent_agent is not None:
                    # 继承模型组
                    if getattr(parent_agent, "model", None):
                        model_group = getattr(parent_agent.model, "model_group", None)
                    # 继承开关类参数
                    summary_prompt = getattr(parent_agent, "summary_prompt", None)
                    execute_tool_confirm = getattr(
                        parent_agent, "execute_tool_confirm", None
                    )
                    use_methodology = getattr(parent_agent, "use_methodology", None)
                    use_analysis = getattr(parent_agent, "use_analysis", None)
                    force_save_memory = getattr(parent_agent, "force_save_memory", None)
                    # 继承工具使用集（名称列表）
                    parent_registry = parent_agent.get_tool_registry()
                    if parent_registry:
                        for t in parent_registry.get_all_tools():
                            if isinstance(t, dict) and t.get("name"):
                                use_tools.append(str(t["name"]))
            except Exception:
                # 忽略继承失败，退回默认配置
                pass

            # 为避免交互阻塞：提供自动确认与空输入处理器
            def _auto_confirm(tip: str, default: bool = True) -> bool:
                return default

            # 创建子Agent（其余配置使用默认/全局）
            agent = Agent(
                system_prompt=system_prompt,
                name="SubAgent",
                description="Temporary sub agent for executing a subtask",
                llm_type="normal",  # 使用默认模型类型
                model_group=model_group,  # 继承父Agent模型组（如可用）
                summary_prompt=summary_prompt,  # 继承父Agent总结提示词（如可用）
                auto_complete=auto_complete,
                output_handler=None,  # 默认 ToolRegistry
                use_tools=None,  # 初始不限定，稍后同步父Agent工具集
                input_handler=None,  # 允许使用系统默认输入链
                execute_tool_confirm=execute_tool_confirm,  # 继承父Agent（如可用）
                need_summary=need_summary,
                multiline_inputer=None,  # 使用系统默认输入器（允许用户输入）
                use_methodology=use_methodology,  # 继承父Agent（如可用）
                use_analysis=use_analysis,  # 继承父Agent（如可用）
                force_save_memory=force_save_memory,  # 继承父Agent（如可用）
                files=None,
                confirm_callback=_auto_confirm,  # 自动确认
            )

            # 同步父Agent的模型名称与工具使用集（若可用）
            try:
                if (
                    parent_agent is not None
                    and getattr(parent_agent, "model", None)
                    and getattr(agent, "model", None)
                ):
                    try:
                        model_name = parent_agent.model.name()  # type: ignore[attr-defined]
                        if model_name:
                            agent.model.set_model_name(model_name)  # type: ignore[attr-defined]
                    except Exception:
                        pass
                if use_tools:
                    agent.set_use_tools(use_tools)
            except Exception:
                pass

            # 执行任务
            result = agent.run(enhanced_task)

            # 主动清理，避免污染父 Agent 的全局状态
            try:
                delete_agent(agent.name)
            except Exception:
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
