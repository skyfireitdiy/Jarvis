from typing import Dict, Any
from yaspin import yaspin

from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.methodology import load_methodology

class FindMethodologyTool:
    name = "find_methodology"
    description = "方法论查找工具，用于在执行过程中查看历史方法论辅助决策"
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "要搜索的查询文本"
            }
        },
        "required": ["query"]
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行方法论查找操作

        Args:
            args (Dict): 包含查询文本的参数字典

        Returns:
            Dict[str, Any]: 包含成功状态、输出内容和错误信息的字典
        """
        try:
            if "query" not in args:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "参数中必须包含查询文本"
                }

            with yaspin(text="搜索相关方法论...", color="cyan") as spinner:
                with spinner.hidden():
                    methodology_prompt = load_methodology(args["query"])

                if methodology_prompt:
                    spinner.text = "找到相关方法论"
                    spinner.ok("✅")
                    PrettyOutput.print(methodology_prompt, OutputType.INFO)
                    return {
                        "success": True,
                        "stdout": methodology_prompt,
                        "stderr": ""
                    }
                else:
                    spinner.text = "未找到相关方法论"
                    spinner.fail("❌")
                    return {
                        "success": True,
                        "stdout": "未找到相关的方法论",
                        "stderr": ""
                    }

        except Exception as e:
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"方法论查找失败: {str(e)}"
            }
