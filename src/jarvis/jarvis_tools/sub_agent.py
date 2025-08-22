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
            }
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
            enhanced_task = f"背景信息:\n{background}\n\n任务:\n{task}" if background else task

            # 无需依赖父Agent：直接使用系统默认/全局配置
            system_prompt = origin_agent_system_prompt
            need_summary = True
            auto_complete = True

            # 为避免交互阻塞：提供自动确认与空输入处理器
            def _auto_confirm(tip: str, default: bool = True) -> bool:
                return default

            def _no_input(tip: str, print_on_empty: bool = False) -> str:
                return ""

            # 创建子Agent（其余配置使用默认/全局）
            agent = Agent(
                system_prompt=system_prompt,
                name="SubAgent",
                description="Temporary sub agent for executing a subtask",
                llm_type="normal",  # 使用默认模型类型
                model_group=None,  # 使用默认模型组
                summary_prompt=None,
                auto_complete=auto_complete,
                output_handler=None,  # 默认 ToolRegistry
                use_tools=None,  # 默认工具集
                input_handler=None,  # 避免交互
                execute_tool_confirm=None,  # 使用全局配置
                need_summary=need_summary,
                multiline_inputer=None,  # 允许用户进行多行输入（使用系统默认输入器）
                use_methodology=None,  # 使用全局配置
                use_analysis=False,  # 使用全局配置
                force_save_memory=None,  # 使用全局配置
                files=None,
                confirm_callback=_auto_confirm,  # 自动确认
            )

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
            return {"success": False, "stdout": "", "stderr": f"执行子任务失败: {str(e)}"}
