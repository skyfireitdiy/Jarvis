# -*- coding: utf-8 -*-
"""auto_select_rule 工具模块

提供根据任务描述自动选择并加载规则的功能。
该工具接收用户意图字符串，输出选择的规则内容。
"""

from typing import Any, Dict

from jarvis.jarvis_utils.output import PrettyOutput


class AutoSelectRuleTool:
    """根据任务描述自动选择并加载规则"""

    name = "auto_select_rule"
    description = (
        "根据任务描述自动选择最合适的规则（最多 5 个），并返回规则内容。"
        "该工具会分析任务意图，从可用规则中选择最相关的规则，加载并返回规则内容。"
        "适用于需要根据任务类型自动匹配最佳实践和规范的场景。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "task_description": {
                "type": "string",
                "description": "任务描述或用户意图字符串，用于匹配最合适的规则",
            }
        },
        "required": ["task_description"],
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行自动规则选择和加载

        参数:
            args (Dict): 包含 task_description 参数的字典，可通过 agent 获取 RulesManager

        返回:
            Dict[str, Any]: 包含成功状态、选中规则内容和错误信息的字典
        """
        try:
            task_description = args.get("task_description", "").strip()
            if not task_description:
                return {"success": False, "stdout": "", "stderr": "任务描述不能为空"}

            agent = args.get("agent")
            if not agent:
                return {"success": False, "stdout": "", "stderr": "无法获取 agent 实例"}

            rules_manager = getattr(agent, "rules_manager", None)
            if not rules_manager:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "agent 没有 rules_manager 属性",
                }

            # 使用 match_rules_to_task 支持本地+远程搜索
            selected_rules = rules_manager.match_rules_to_task(task_description)

            if not selected_rules:
                return {
                    "success": True,
                    "stdout": "未找到与任务相关的规则",
                    "stderr": "",
                    "selected_rules": [],
                }

            if selected_rules == ["__NO_RULES_NEEDED__"]:
                return {
                    "success": True,
                    "stdout": "任务简单，无需特定规则即可完成",
                    "stderr": "",
                    "selected_rules": [],
                    "no_rules_needed": True,
                }

            rule_contents = []
            for rule_name in selected_rules:
                # 使用 load_rule() 方法来加载规则，这会更新 loaded_rules 状态
                success = rules_manager.load_rule(rule_name)
                if success:
                    # 从缓存中获取已加载的规则内容
                    rule_content = rules_manager._loaded_rules.get(rule_name)
                    if rule_content:
                        rule_contents.append({"name": rule_name, "content": rule_content})

            output_lines = [f"已为任务选择 {len(rule_contents)} 个规则：", ""]
            for rule_info in rule_contents:
                output_lines.append(f"## 规则：{rule_info['name']}")
                output_lines.append("")
                output_lines.append(rule_info["content"])
                output_lines.append("")
                output_lines.append("---")
                output_lines.append("")

            return {
                "success": True,
                "stdout": "\n".join(output_lines),
                "stderr": "",
                "selected_rules": [r["name"] for r in rule_contents],
                "rule_contents": rule_contents,
            }

        except Exception as e:
            PrettyOutput.auto_print(f"自动规则选择失败：{str(e)}")
            return {
                "success": False,
                "stdout": "",
                "stderr": f"自动规则选择失败：{str(e)}",
            }
