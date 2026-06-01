# -*- coding: utf-8 -*-
"""ARCHER 工作流模式切换工具"""

from typing import Any
from typing import Dict

from jarvis.jarvis_utils.output import PrettyOutput


class SwitchModeTool:
    """ARCHER 工作流模式切换工具"""

    name = "switch_mode"
    description = """切换 ARCHER 工作流模式，系统会自动切换到对应的模型并继续执行。

模式说明：
- ANALYZE：分析需求和问题（normal 模型）
- RULE：加载规则和最佳实践（cheap 模型）
- COLLECT：收集信息和代码（cheap 模型）
- HYPOTHESIZE：设计方案和决策（smart 模型）
- EXECUTE：执行操作和修改（normal 模型）
- REVIEW：审查和验证（smart 模型）

使用方式：
1. 完成当前阶段的工作
2. 调用 switch_mode 工具切换到下一个模式
3. 系统自动切换模型并继续执行

注意：切换后会自动继续执行，无需用户干预。"""

    parameters = {
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
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行模式切换

        参数:
            args: 包含 mode、reason 和 agent 的字典

        返回:
            执行结果字典
        """
        mode = args.get("mode", "").upper()
        reason = args.get("reason", "")
        agent = args.get("agent")

        # 验证模式
        valid_modes = ["ANALYZE", "RULE", "COLLECT", "HYPOTHESIZE", "EXECUTE", "REVIEW"]
        if mode not in valid_modes:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"无效的模式: {mode}。有效模式: {', '.join(valid_modes)}",
            }

        # 验证 agent
        if agent is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少 agent 上下文，无法切换模式",
            }

        # 定义模式到模型类型的映射
        mode_to_model_type = {
            "ANALYZE": "normal",
            "RULE": "cheap",
            "COLLECT": "cheap",
            "HYPOTHESIZE": "smart",
            "EXECUTE": "normal",
            "REVIEW": "smart",
        }

        target_model_type = mode_to_model_type[mode]

        # 获取当前模型类型
        try:
            from jarvis.jarvis_agent.builtin_input_handler import (
                get_platform_type_from_agent,
            )

            current_model_type = get_platform_type_from_agent(agent)
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"获取当前模型类型失败: {str(e)}",
            }

        # 如果当前模型类型与目标模型类型相同，无需切换
        if current_model_type == target_model_type:
            message = f"当前已是 {target_model_type} 模型，无需切换"
            if reason:
                message += f"\n切换原因: {reason}"
            return {
                "success": True,
                "stdout": message,
                "stderr": "",
            }

        # 检查上下文限制，必要时触发压缩
        try:
            from jarvis.jarvis_agent.builtin_input_handler import (
                _check_context_and_compress_if_needed,
            )

            if not _check_context_and_compress_if_needed(agent, target_model_type):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"上下文超出 {target_model_type} 模型限制，且压缩后仍超限，无法切换",
                }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"上下文检查失败: {str(e)}",
            }

        # 执行模型切换
        try:
            from jarvis.jarvis_platform.registry import PlatformRegistry

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

            # 构建成功消息
            model_type_display = {
                "smart": "Smart",
                "normal": "Normal",
                "cheap": "Cheap",
            }.get(target_model_type, target_model_type)

            message = f"🔄 已切换到 {mode} 模式（{model_type_display} 模型）"
            if reason:
                message += f"\n切换原因: {reason}"

            PrettyOutput.auto_print(message)

            return {
                "success": True,
                "stdout": message,
                "stderr": "",
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"模型切换失败: {str(e)}",
            }
