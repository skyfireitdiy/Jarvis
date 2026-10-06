"""
生成 holdout scenarios（保留验收场景）的工具。

用途:
- 为黑灯工厂流水线生成隐藏的验收场景，供独立评估器测试产出代码。
- 生成的场景标记为"编码侧不可见"，严格与编码 agent 隔离。

参数:
- feature (str): 功能描述。
- count (int): 要生成的场景数量（默认 5，范围 1-20）。

返回:
- success (bool)
- stdout (str): JSON 文本，包含场景列表（每个含 id/描述/验证方式/hidden 标记）
- stderr (str)
"""

import json
from typing import Any
from typing import Dict
from typing import List


class HoldoutGeneratorTool:
    # 文件名必须与工具名一致，便于注册表自动加载
    name = "holdout_generator"
    description = "生成 holdout scenarios（保留验收场景），标记为编码侧不可见，供独立评估器测试产出。"
    parameters = {
        "type": "object",
        "properties": {
            "feature": {
                "type": "string",
                "description": "功能描述，用于生成针对性的验收场景",
            },
            "count": {
                "type": "integer",
                "description": "要生成的场景数量（默认 5，范围 1-20）",
            },
        },
        "required": ["feature"],
    }

    # 场景类型模板，覆盖功能/边界/异常/性能/安全
    _SCENARIO_TEMPLATES = [
        "验证 {feature} 的核心功能在正常输入下正确工作",
        "验证 {feature} 在边界输入（空值/极值/最大长度）下行为正确",
        "验证 {feature} 在非法输入下能优雅报错，不崩溃",
        "验证 {feature} 的接口契约（参数类型/返回结构/错误码）符合 spec",
        "验证 {feature} 在并发/重复调用下保持一致性",
        "验证 {feature} 的性能满足 spec 约束（响应时间/吞吐量）",
        "验证 {feature} 的安全性（无注入/越权/密钥泄露）",
        "验证 {feature} 与既有模块的兼容性，不引入回归",
    ]

    @staticmethod
    def check() -> bool:
        """工具始终可用（纯逻辑生成，无外部依赖）。"""
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

            count = args.get("count", 5)
            if not isinstance(count, int):
                count = 5
            count = max(1, min(count, 20))

            scenarios: List[Dict[str, Any]] = []
            for i in range(count):
                template = self._SCENARIO_TEMPLATES[i % len(self._SCENARIO_TEMPLATES)]
                scenarios.append(
                    {
                        "id": i + 1,
                        "description": template.format(feature=feature),
                        "verification": "由独立评估器 agent 执行该场景，记录 pass/fail",
                        "hidden": True,  # 编码侧不可见标记
                    }
                )

            output = {
                "feature": feature,
                "count": len(scenarios),
                "hidden": True,
                "warning": "这些场景是 holdout scenarios，编码 agent 不得看到。仅供独立评估器使用。",
                "scenarios": scenarios,
            }
            return {
                "success": True,
                "stdout": json.dumps(output, ensure_ascii=False, indent=2),
                "stderr": "",
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"holdout_generator 执行异常: {e}",
            }
