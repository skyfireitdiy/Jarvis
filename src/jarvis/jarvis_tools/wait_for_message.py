# -*- coding: utf-8 -*-
"""等待消息工具

显式等待其他 Agent 或用户输入的多行消息，且忽略 auto_complete 自动补全。
用于多 Agent 编排全自动运行时，在流程中间阻塞等待其他 Agent 发来的消息，
避免被 auto_complete 自动补 !!!COMPLETE!!! 提前结束。
"""

from typing import Any, Dict

from jarvis.jarvis_utils.input import get_multiline_input

_DEFAULT_TIP = "等待消息（输入完成后按提交键确认）"


class WaitForMessageTool:
    """等待消息工具

    调用 get_multiline_input 并设置 ignore_auto_complete=True，
    使等待过程跳过非交互模式的自动补全分支（不补 !!!COMPLETE!!!），
    真正阻塞等待多行输入（Gateway 模式等待前端/其他 Agent 注入消息，CLI 模式等待 stdin）。
    """

    name = "wait_for_message"
    description = (
        "等待消息（等多行输入），忽略 auto_complete 自动补全。"
        "用于多 Agent 编排中阻塞等待其他 Agent 发来的消息，"
        "即使当前处于非交互模式也不会自动补 !!!COMPLETE!!!。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "tip": {
                "type": "string",
                "description": "等待提示文本（可选），默认：等待消息（输入完成后按提交键确认）",
            },
            "timeout": {
                "type": "number",
                "description": "等待超时秒数（可选），默认无限等待；仅 Gateway 模式生效，超时返回空字符串",
            },
        },
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行等待消息操作"""
        tip = args.get("tip") or _DEFAULT_TIP
        timeout = args.get("timeout")
        try:
            user_input = get_multiline_input(
                tip,
                print_on_empty=False,
                ignore_auto_complete=True,
                timeout=timeout,
            )
            return {
                "success": True,
                "stdout": user_input,
                "stderr": "",
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"等待消息失败: {str(e)}",
            }
