import os
import json
import hashlib
from typing import Dict, Any

from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.output import OutputType, PrettyOutput



class MethodologyTool:
    """经验管理工具"""

    name = "methodology"
    description = "管理问题解决方法论，支持添加、更新和删除操作"
    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": "操作类型（delete/update/add）",
                "enum": ["delete", "update", "add"]
            },
            "problem_type": {
                "type": "string",
                "description": "问题类型，例如：部署开源项目、生成提交信息"
            },
            "content": {
                "type": "string",
                "description": "方法论内容（更新和添加时必填）",
                "optional": True
            }
        },
        "required": ["operation", "problem_type"]
    }

    def __init__(self):
        """初始化经验管理工具"""
        self.methodology_dir = os.path.join(get_data_dir(), "methodologies")
        self._ensure_dir_exists()

    def _ensure_dir_exists(self):
        """确保方法论目录存在"""
        if not os.path.exists(self.methodology_dir):
            try:
                os.makedirs(self.methodology_dir, exist_ok=True)
            except Exception as e:
                PrettyOutput.print(f"创建方法论目录失败：{str(e)}", OutputType.ERROR)

    def _get_methodology_file_path(self, problem_type: str) -> str:
        """
        根据问题类型获取对应的方法论文件路径

        参数:
            problem_type: 问题类型

        返回:
            str: 方法论文件路径
        """
        # 使用MD5哈希作为文件名，避免文件名中的特殊字符
        safe_filename = hashlib.md5(problem_type.encode('utf-8')).hexdigest()
        return os.path.join(self.methodology_dir, f"{safe_filename}.json")


    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行管理方法论的操作

        Args:
            args: 包含操作参数的字典
                - operation: 操作类型 (delete/update/add)
                - problem_type: 问题类型
                - content: 方法论内容 (更新和添加时必填)

        Returns:
            Dict[str, Any]: 包含执行结果的字典
        """
        operation = args.get("operation", "").strip()
        problem_type = args.get("problem_type", "").strip()
        content = args.get("content", "").strip()

        if not operation or not problem_type:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少必要参数: operation和problem_type"
            }

        try:
            if operation == "delete":
                # 获取方法论文件路径
                file_path = self._get_methodology_file_path(problem_type)

                # 检查文件是否存在
                if os.path.exists(file_path):
                    os.remove(file_path)
                    return {
                        "success": True,
                        "stdout": f"已删除问题类型'{problem_type}'对应的方法论",
                        "stderr": ""
                    }
                else:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": f"未找到问题类型'{problem_type}'对应的方法论"
                    }

            elif operation in ["update", "add"]:
                if not content:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "需要提供方法论内容"
                    }

                # 确保目录存在
                self._ensure_dir_exists()

                # 获取方法论文件路径
                file_path = self._get_methodology_file_path(problem_type)

                # 保存方法论到单独的文件
                with open(file_path, "w", encoding="utf-8", errors="ignore") as f:
                    json.dump({
                        "problem_type": problem_type,
                        "content": content
                    }, f, ensure_ascii=False, indent=2)

                PrettyOutput.print(f"方法论已保存到 {file_path}", OutputType.INFO)

                action = "更新" if os.path.exists(file_path) else "添加"
                return {
                    "success": True,
                    "stdout": f"{action}了问题类型'{problem_type}'对应的方法论",
                    "stderr": ""
                }

            else:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"不支持的操作类型: {operation}"
                }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"执行失败: {str(e)}"
            }

