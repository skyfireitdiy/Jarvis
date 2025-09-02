# -*- coding: utf-8 -*-
"""
sub_agent 工具
将子任务交给通用 Agent 执行，并返回执行结果。

约定：
- 必填参数：task, background, system_prompt, summary_prompt, use_tools
- 不继承父 Agent 的任何配置，所有参数必须显式提供
- 子Agent必须自动完成(auto_complete=True)且需要summary(need_summary=True)
"""
from typing import Any, Dict, Optional
import json

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_utils.globals import delete_agent
from jarvis.jarvis_tools.registry import ToolRegistry


class SubAgentTool:
    """
    临时创建一个通用 Agent 执行子任务，执行完立即清理。
    - 不注册至全局
    - 使用系统默认/全局配置
    - 启用自动完成与总结
    """

    # 必须与文件名一致，供 ToolRegistry 自动注册
    name = "sub_agent"
    description = "将子任务交给通用 Agent 执行，并返回执行结果（不继承父Agent配置，参数需显式提供，自动完成并生成总结）。"
    parameters = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "要执行的子任务内容（必填）",
            },
            "background": {
                "type": "string",
                "description": "任务背景与已知信息（必填，将与任务一并提供给子Agent）",
            },
            "system_prompt": {
                "type": "string",
                "description": "覆盖子Agent的系统提示词（必填）",
            },
            "summary_prompt": {
                "type": "string",
                "description": "覆盖子Agent的总结提示词（必填）",
            },
            "use_tools": {
                "type": "array",
                "items": {"type": "string"},
                "description": "限制子Agent可用的工具名称列表（必填）。兼容以逗号分隔的字符串输入。可用的工具列表："
                + "\n".join(
                    [
                        t["name"] + ": " + t["description"]
                        for t in ToolRegistry().get_all_tools()
                    ]
                ),
            },
        },
        "required": [
            "task",
            "background",
            "system_prompt",
            "summary_prompt",
            "use_tools",
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
            auto_complete = True

            # 读取并校验必填参数
            system_prompt = str(args.get("system_prompt", "")).strip()
            summary_prompt = str(args.get("summary_prompt", "")).strip()

            # 解析可用工具列表（支持数组或以逗号分隔的字符串）
            _use_tools = args.get("use_tools", None)
            use_tools: list[str] = []
            if isinstance(_use_tools, list):
                use_tools = [str(x).strip() for x in _use_tools if str(x).strip()]
            elif isinstance(_use_tools, str):
                use_tools = [s.strip() for s in _use_tools.split(",") if s.strip()]
            else:
                use_tools = []

            errors = []
            if not system_prompt:
                errors.append("system_prompt 不能为空")
            if not summary_prompt:
                errors.append("summary_prompt 不能为空")
            if not use_tools:
                errors.append("use_tools 不能为空")
            if not background:
                errors.append("background 不能为空")

            if errors:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "; ".join(errors),
                }

            # 创建子Agent（不继承父Agent配置）
            agent = Agent(
                system_prompt=system_prompt,
                name="SubAgent",
                description="Temporary sub agent for executing a subtask",
                model_group=None,
                summary_prompt=summary_prompt,
                auto_complete=auto_complete,
                output_handler=None,
                use_tools=None,
                input_handler=None,
                execute_tool_confirm=None,
                need_summary=need_summary,
                multiline_inputer=None,
                use_methodology=None,
                use_analysis=None,
                force_save_memory=None,
                files=None,
            )

            # 设置可用工具列表
            try:
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
