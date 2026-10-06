"""
校验 NLSpec（自然语言规格）完整性的工具。

用途:
- 检查一份 NLSpec 是否包含黑灯工厂要求的四要素：Goal / Constraints / Interfaces / Non-goals。
- 返回缺失要素与提示，帮助编写合格的 spec。

参数:
- spec (str): 待校验的 NLSpec 文本。

返回:
- success (bool)
- stdout (str): JSON 文本，包含四要素命中情况、缺失项与是否合格
- stderr (str)
"""

import json
from typing import Any
from typing import Dict


class SpecValidatorTool:
    # 文件名必须与工具名一致，便于注册表自动加载
    name = "spec_validator"
    description = "校验 NLSpec（自然语言规格）是否包含 Goal/Constraints/Interfaces/Non-goals 四要素。"
    parameters = {
        "type": "object",
        "properties": {
            "spec": {
                "type": "string",
                "description": "待校验的 NLSpec 文本",
            },
        },
        "required": ["spec"],
    }

    # 四要素的关键词（中英文），用于启发式检测
    _KEYWORDS = {
        "Goal": ["goal", "目标", "目的", "要构建", "构建一个", "实现"],
        "Constraints": [
            "constraint",
            "约束",
            "限制",
            "必须",
            "不得",
            "禁止",
            "技术栈",
            "性能",
        ],
        "Interfaces": [
            "interface",
            "接口",
            "api",
            "函数签名",
            "端点",
            "数据结构",
            "输入输出",
            "返回",
        ],
        "Non-goals": [
            "non-goal",
            "非目标",
            "不做",
            "不包含",
            "不实现",
            "范围外",
            "out of scope",
        ],
    }

    @staticmethod
    def check() -> bool:
        """工具始终可用（纯文本校验，无外部依赖）。"""
        return True

    @staticmethod
    def _detect(text_lower: str, keywords: list) -> bool:
        """检测文本是否命中任一关键词。"""
        return any(kw in text_lower for kw in keywords)

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            spec = args.get("spec")
            if not spec or not isinstance(spec, str):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "参数错误：spec 必须是非空字符串",
                }

            text_lower = spec.lower()
            results = {}
            missing = []
            for element, keywords in self._KEYWORDS.items():
                hit = self._detect(text_lower, keywords)
                results[element] = hit
                if not hit:
                    missing.append(element)

            valid = len(missing) == 0
            output = {
                "valid": valid,
                "elements": results,
                "missing": missing,
                "hint": (
                    "NLSpec 合格，包含全部四要素。"
                    if valid
                    else f"NLSpec 不完整，缺少要素: {', '.join(missing)}。请补充对应章节。"
                ),
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
                "stderr": f"spec_validator 执行异常: {e}",
            }
