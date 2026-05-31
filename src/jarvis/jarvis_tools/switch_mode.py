# -*- coding: utf-8 -*-
"""ARCHER 工作流模式切换工具"""

from typing import Any
from typing import Dict

from jarvis.jarvis_tools.base import tool
from jarvis.jarvis_utils.output import PrettyOutput


@tool(
    name="switch_mode",
    description="切换 ARCHER 工作流模式，系统会自动切换到对应的模型并继续执行。\n\n"
    "模式说明：\n"
    "- ANALYZE：分析需求和问题（normal 模型）\n"
    "- RULE：加载规则和最佳实践（cheap 模型）\n"
    "- COLLECT：收集信息和代码（cheap 模型）\n"
    "- HYPOTHESIZE：设计方案和决策（smart 模型）\n"
    "- EXECUTE：执行操作和修改（normal 模型）\n"
    "- REVIEW：审查和验证（smart 模型）",
    parameters={
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "ANALYZE",
                    "RULE",
                    "COLLECT",
                    "HYPOTHESIZE",
                    "EXECUTE",
                    "REVIEW",
                ],
                "description": "要切换到的工作流模式",
            },
            "reason": {
                "type": "string",
                "description": "切换原因的简短说明（可选）",
            },
        },
        "required": ["mode"],
    },
)
def switch_mode(mode: str, reason: str = "", agent: Any = None) -> Dict[str, Any]:
    """切换 ARCHER 工作流模式

    参数:
        mode: 要切换到的模式
        reason: 切换原因（可选）
        agent: Agent 实例（由系统自动传入）

    返回:
        Dict[str, Any]: 包含切换结果的字典
    """
    try:
        # 验证模式
        valid_modes = ["ANALYZE", "RULE", "COLLECT", "HYPOTHESIZE", "EXECUTE", "REVIEW"]
        if mode not in valid_modes:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"❌ 无效的模式: {mode}，有效模式: {', '.join(valid_modes)}",
            }

        # 获取 AgentRunLoop 实例
        if not agent or not hasattr(agent, "_agent_run_loop"):
            return {
                "success": False,
                "stdout": "",
                "stderr": "❌ 无法获取 AgentRunLoop 实例",
            }

        agent_run_loop = agent._agent_run_loop

        # 检查是否需要切换
        if (
            hasattr(agent_run_loop, "_current_mode")
            and agent_run_loop._current_mode == mode
        ):
            reason_text = f"（{reason}）" if reason else ""
            return {
                "success": True,
                "stdout": f"✅ 已经处于 {mode} 模式{reason_text}，无需切换",
                "stderr": "",
            }

        # 获取目标模型类型
        mode_to_model = {
            "ANALYZE": "normal",
            "RULE": "cheap",
            "COLLECT": "cheap",
            "HYPOTHESIZE": "smart",
            "EXECUTE": "normal",
            "REVIEW": "smart",
        }
        target_model_type = mode_to_model[mode]

        # 获取当前模型类型
        from jarvis.jarvis_agent.builtin_input_handler import (
            get_platform_type_from_agent,
            _check_context_and_compress_if_needed,
        )
        from jarvis.jarvis_platform import PlatformRegistry

        current_model_type = get_platform_type_from_agent(agent)

        # 如果模型类型相同，只更新状态
        if current_model_type == target_model_type:
            agent_run_loop._current_mode = mode
            reason_text = f"（{reason}）" if reason else ""
            return {
                "success": True,
                "stdout": f"✅ 已切换到 {mode} 模式{reason_text}（模型类型未变：{target_model_type}）",
                "stderr": "",
            }

        # 检查上下文限制，必要时触发压缩
        if not _check_context_and_compress_if_needed(agent, target_model_type):
            return {
                "success": False,
                "stdout": "",
                "stderr": "❌ 上下文检查失败，无法切换模型",
            }

        # 保存旧模型的消息
        old_messages = agent.model.get_messages()

        # 重新创建模型
        platform_registry = PlatformRegistry()
        if target_model_type == "smart":
            agent.model = platform_registry.get_smart_platform()
            agent._agent_type = "code_agent"
        elif target_model_type == "cheap":
            agent.model = platform_registry.get_cheap_platform()
            agent._agent_type = "normal"
        else:  # normal
            agent.model = platform_registry.get_normal_platform()
            agent._agent_type = "normal"

        agent.model.set_suppress_output(False)
        agent.model.agent = agent

        # 将旧消息设置到新模型
        if old_messages:
            agent.model.set_messages(old_messages)

        # 将新模型设置到现有的 session 中
        agent.session.model = agent.model

        # 更新当前 MODE 状态
        agent_run_loop._current_mode = mode

        # 构建返回消息
        model_type_display = {
            "smart": "Smart",
            "normal": "Normal",
            "cheap": "Cheap",
        }.get(target_model_type, target_model_type)

        reason_text = f"（{reason}）" if reason else ""
        success_msg = (
            f"✅ 已切换到 {mode} 模式{reason_text}，使用 {model_type_display} 模型"
        )

        return {
            "success": True,
            "stdout": success_msg,
            "stderr": "",
        }

    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"❌ 切换失败: {str(e)}",
        }
