# -*- coding: utf-8 -*-
from pathlib import Path
from typing import Any
from typing import Dict

from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.output import PrettyOutput


class generate_new_tool:
    name = "generate_new_tool"
    description = "生成并注册新的Jarvis工具。在用户数据目录下创建工具文件并自动注册。"

    parameters = {
        "type": "object",
        "properties": {
            "tool_name": {
                "type": "string",
                "description": "新工具的名称，将用作文件名和工具类名",
            },
            "function_description": {
                "type": "string",
                "description": "工具的功能描述",
            },
        },
        "required": ["tool_name", "function_description"],
    }

    @staticmethod
    def check() -> bool:
        """检查工具是否可用"""
        # 检查数据目录是否存在
        data_dir = get_data_dir()
        tools_dir = Path(data_dir) / "tools"

        # 如果tools目录不存在，尝试创建
        if not tools_dir.exists():
            try:
                tools_dir.mkdir(parents=True, exist_ok=True)
                return True
            except Exception as e:
                PrettyOutput.auto_print(f"❌ 无法创建工具目录 {tools_dir}: {e}")
                return False

        return True

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成新工具并注册到当前的工具注册表中

        参数:
            args: 包含工具名称和工具代码的字典

        返回:
            Dict: 包含生成结果的字典
        """
        tool_file_path = None
        try:
            from jarvis.jarvis_code_agent.code_agent import CodeAgent

            curr_dir = os.getcwd()
            
            data_dir = get_data_dir()
            tools_dir = Path(data_dir) / "tools"
            tools_dir.mkdir(parents=True, exist_ok=True)
            os.chdir(tools_dir)

            # 从参数中获取工具信息
            tool_name = args["tool_name"]
            function_description = args["function_description"]

            # 验证工具名称
            if not tool_name.isidentifier():
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"工具名称 '{tool_name}' 不是有效的Python标识符",
                }

            prompt = f"请根据用户需求生成一个新的Jarvis工具，工具的名称是：{tool_name}，工具的功能描述是：{function_description}"
            
            # 获取当前脚本所在目录，告诉agent可以参考当前目录下的Jarvis实现，以便于集成
            curr_dir =  Path(__file__).parent.parent.resolve()

            prompt += f"你可以参考{curr_dir}目录下的Jarvis实现，以便于集成"



        finally:
            if curr_dir:
                os.chdir(curr_dir)