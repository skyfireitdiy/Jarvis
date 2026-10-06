"""
评估门禁计算的工具。

用途:
- 根据各 holdout scenario 的 pass/fail 结果，计算门禁指标：场景通过率、假阳性率、人类推翻率。
- 判断是否达到门禁标准（场景通过率 >= 90%）。

参数:
- results (List[Dict]): 各场景评估结果，形如 [{"id": 1, "pass": true}, ...]。
- false_positives (int, 可选): 评估器误判为通过但实际有问题的场景数。
- human_overrides (int, 可选): 人类推翻评估器判断的次数。
- total_human_reviews (int, 可选): 人类审批总次数（用于计算推翻率）。

返回:
- success (bool)
- stdout (str): JSON 文本，包含各指标、是否达标与建议
- stderr (str)
"""

import json
from typing import Any
from typing import Dict


class GateCalculatorTool:
    # 文件名必须与工具名一致，便于注册表自动加载
    name = "gate_calculator"
    description = "计算黑灯工厂评估门禁指标（场景通过率/假阳性率/人类推翻率）并判断是否达标（>=90%）。"
    parameters = {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {"type": "object"},
                "description": '各场景评估结果，形如 [{"id": 1, "pass": true}, ...]',
            },
            "false_positives": {
                "type": "integer",
                "description": "评估器误判为通过但实际有问题的场景数（默认 0）",
            },
            "human_overrides": {
                "type": "integer",
                "description": "人类推翻评估器判断的次数（默认 0）",
            },
            "total_human_reviews": {
                "type": "integer",
                "description": "人类审批总次数（默认 0，用于计算推翻率）",
            },
        },
        "required": ["results"],
    }

    _PASS_THRESHOLD = 0.9  # 场景通过率门禁标准

    @staticmethod
    def check() -> bool:
        """工具始终可用（纯计算，无外部依赖）。"""
        return True

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            results = args.get("results")
            if not isinstance(results, list) or not results:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": '参数错误：results 必须是非空列表，形如 [{"id": 1, "pass": true}]',
                }

            total = len(results)
            passed = sum(1 for r in results if isinstance(r, dict) and r.get("pass"))
            pass_rate = passed / total

            false_positives = args.get("false_positives", 0) or 0
            human_overrides = args.get("human_overrides", 0) or 0
            total_human_reviews = args.get("total_human_reviews", 0) or 0

            false_positive_rate = false_positives / passed if passed > 0 else 0.0
            human_override_rate = (
                human_overrides / total_human_reviews
                if total_human_reviews > 0
                else None
            )

            meets_threshold = pass_rate >= self._PASS_THRESHOLD
            # 假阳性率过高或人类推翻率过高时，即使通过率达标也建议人工介入
            caution = false_positive_rate >= 0.05 or (
                human_override_rate is not None and human_override_rate >= 0.10
            )

            if meets_threshold and not caution:
                decision = "建议通过门禁（场景通过率达标且无高假阳性/高推翻率）。"
            elif meets_threshold and caution:
                decision = (
                    "通过率达标，但存在高假阳性或高人类推翻率，建议人工审批复核。"
                )
            else:
                decision = "未达门禁标准（场景通过率 < 90%），建议重试或交人工审批。"
                if not meets_threshold:
                    decision += " 参考 holdout_discipline 规则：<90% 视为未达标。"

            output = {
                "total_scenarios": total,
                "passed": passed,
                "failed": total - passed,
                "pass_rate": round(pass_rate, 4),
                "pass_threshold": self._PASS_THRESHOLD,
                "meets_threshold": meets_threshold,
                "false_positive_rate": round(false_positive_rate, 4),
                "human_override_rate": (
                    round(human_override_rate, 4)
                    if human_override_rate is not None
                    else None
                ),
                "caution": caution,
                "decision": decision,
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
                "stderr": f"gate_calculator 执行异常: {e}",
            }
