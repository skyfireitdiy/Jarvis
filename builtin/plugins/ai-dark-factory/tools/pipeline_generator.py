"""
生成 sw-controller 风格多 Agent 流水线编排 YAML 的工具。

用途:
- 为黑灯工厂流水线生成一份可被 @OrganizeAgents 加载的编排 YAML。
- 编排体现四层架构：planner（规划）→ generator（生成）→ validator（验证）→ orchestrator（门禁+人工审批关口）。

参数:
- feature (str): 功能描述，注入各 agent 的任务上下文。
- working_dir (str, 可选): agent 工作目录（默认 "."）。

返回:
- success (bool)
- stdout (str): 编排 YAML 文本
- stderr (str)
"""

from typing import Any
from typing import Dict


class PipelineGeneratorTool:
    # 文件名必须与工具名一致，便于注册表自动加载
    name = "pipeline_generator"
    description = "生成 sw-controller 风格多 Agent 流水线编排 YAML（planner/generator/validator/orchestrator，含人工审批关口）。"
    parameters = {
        "type": "object",
        "properties": {
            "feature": {
                "type": "string",
                "description": "功能描述，注入各 agent 的任务上下文",
            },
            "working_dir": {
                "type": "string",
                "description": "agent 工作目录（默认 '.'）",
            },
        },
        "required": ["feature"],
    }

    @staticmethod
    def check() -> bool:
        """工具始终可用（纯文本生成，无外部依赖）。"""
        return True

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            feature = args.get("feature")
            if not feature or not isinstance(feature, str):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "参数错误：feature 必须是非空字符串",
                }

            working_dir = args.get("working_dir", ".")
            if not isinstance(working_dir, str) or not working_dir:
                working_dir = "."

            yaml_text = self._build_pipeline_yaml(feature, working_dir)
            return {
                "success": True,
                "stdout": yaml_text,
                "stderr": "",
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"pipeline_generator 执行异常: {e}",
            }

    def _build_pipeline_yaml(self, feature: str, working_dir: str) -> str:
        """构建黑灯工厂流水线编排 YAML。"""
        return f"""---
# AI 黑灯工厂流水线编排（由 pipeline_generator 生成）
# 功能: {feature}
# 架构: planner -> generator -> validator -> orchestrator(人工审批关口)
agents:
  - name: "df_planner"
    type: "agent"
    working_dir: "{working_dir}"
    task: |
      你是黑灯工厂流水线的规划器（Planner）。
      读取 spec，把功能拆解为实现计划，明确每个生成器的任务边界。
      当前功能: {feature}
      只规划，不写代码。输出实现计划供生成器执行。

  - name: "df_generator"
    type: "agent"
    working_dir: "{working_dir}"
    task: |
      你是黑灯工厂流水线的生成器（Generator）。
      依据规划器的实现计划与 spec，用 TDD 铁律写代码：先写测试，再写实现。
      当前功能: {feature}
      遵守 spec_writing / tdd_iron_rule 规则。产出可验证的代码与测试。

  - name: "df_validator"
    type: "agent"
    working_dir: "{working_dir}"
    task: |
      你是黑灯工厂流水线的验证器（Validator）。
      持有 holdout scenarios（编码侧不可见），用它们独立评估生成器的产出。
      当前功能: {feature}
      遵守 holdout_discipline 规则。输出各场景 pass/fail 报告。

  - name: "df_orchestrator"
    type: "agent"
    working_dir: "{working_dir}"
    task: |
      你是黑灯工厂流水线的编排器（Orchestrator），只协调不执行。
      汇总验证器的 pass/fail 报告，用 gate_calculator 计算门禁指标。
      当前功能: {feature}
      遵守 orchestration 规则：不自动合并，输出结构化审批报告交人工审批关口。
"""
