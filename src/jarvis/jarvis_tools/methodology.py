# -*- coding: utf-8 -*-
import hashlib
import json
import os
from typing import Any
from typing import Dict

from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.methodology import _get_project_methodology_directory
from jarvis.jarvis_utils.output import PrettyOutput


class MethodologyTool:
    """方法论管理工具

    支持项目级和全局级方法论管理：
    - 项目级方法论：存储在Git仓库的.jarvis/methodologies目录中，仅供当前项目使用
    - 全局级方法论：存储在用户数据目录中，可在所有项目中共享

    通过scope参数（global/project）选择作用域，默认为global。
    """

    name = "methodology"
    description = "管理问题解决方法论，支持项目级和全局级，支持添加、更新和删除操作"
    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": "操作类型（delete/update/add）",
                "enum": ["delete", "update", "add"],
            },
            "problem_type": {
                "type": "string",
                "description": "问题类型，例如：部署开源项目、生成提交信息",
            },
            "content": {
                "type": "string",
                "description": "方法论内容（更新和添加时必填）",
                "optional": True,
            },
            "scope": {
                "type": "string",
                "description": "方法论作用域：global（全局）或project（项目级），默认为global",
                "enum": ["global", "project"],
            },
        },
        "required": ["operation", "problem_type"],
    }

    def __init__(self) -> None:
        """初始化经验管理工具"""
        self.methodology_dir: str = os.path.join(get_data_dir(), "methodologies")

    def _get_methodology_dir(self, scope: str) -> str:
        """根据scope获取方法论目录

        Args:
            scope: 方法论作用域，'global'或'project'

        Returns:
            str: 方法论目录路径

        Raises:
            ValueError: 当scope='project'且无法获取项目级目录时
        """
        if scope == "project":
            project_dir = _get_project_methodology_directory()
            if not project_dir:
                error_msg = "无法获取项目级方法论目录，请确保在Git仓库中"
                PrettyOutput.auto_print(f"❌ {error_msg}")
                raise ValueError(error_msg)
            return project_dir
        else:
            return os.path.join(get_data_dir(), "methodologies")

    def _ensure_dir_exists(self, directory: str) -> None:
        """确保指定目录存在

        Args:
            directory: 目录路径
        """
        if not os.path.exists(directory):
            try:
                os.makedirs(directory, exist_ok=True)
            except Exception as e:
                PrettyOutput.auto_print(f"❌ 创建方法论目录失败：{str(e)}")

    def _get_methodology_file_path(self, problem_type: str, scope: str) -> str:
        """
        根据问题类型和scope获取对应的方法论文件路径

        参数:
            problem_type: 问题类型
            scope: 方法论作用域

        返回:
            str: 方法论文件路径
        """
        methodology_dir = self._get_methodology_dir(scope)
        # 使用MD5哈希作为文件名，避免文件名中的特殊字符
        safe_filename = hashlib.md5(problem_type.encode("utf-8")).hexdigest()
        return os.path.join(methodology_dir, f"{safe_filename}.json")

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行管理方法论的操作

        Args:
            args: 包含操作参数的字典
                - operation: 操作类型 (delete/update/add)
                - problem_type: 问题类型
                - content: 方法论内容 (更新和添加时必填)
                - scope: 方法论作用域，'global'或'project'，默认为'global'

        Returns:
            Dict[str, Any]: 包含执行结果的字典
        """
        operation = args.get("operation", "").strip()
        problem_type = args.get("problem_type", "").strip()
        content = args.get("content", "").strip()
        scope = args.get("scope", "global").strip()

        # 验证scope参数
        if scope not in ["global", "project"]:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"无效的scope参数: {scope}，必须是'global'或'project'",
            }

        if not operation or not problem_type:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少必要参数: operation和problem_type",
            }

        try:
            if operation == "delete":
                # 获取方法论文件路径
                file_path = self._get_methodology_file_path(problem_type, scope)

                # 检查文件是否存在
                if os.path.exists(file_path):
                    os.remove(file_path)
                    return {
                        "success": True,
                        "stdout": f"已删除{scope}方法论：{problem_type}",
                        "stderr": "",
                    }
                else:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": f"未找到{scope}方法论：{problem_type}",
                    }

            elif operation in ["update", "add"]:
                if not content:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "需要提供方法论内容",
                    }

                # 获取方法论目录并确保存在
                methodology_dir = self._get_methodology_dir(scope)
                self._ensure_dir_exists(methodology_dir)

                # 获取方法论文件路径
                file_path = self._get_methodology_file_path(problem_type, scope)

                # 保存方法论到单独的文件
                with open(file_path, "w", encoding="utf-8", errors="ignore") as f:
                    json.dump(
                        {
                            "problem_type": problem_type,
                            "content": content,
                            "scope": scope,
                        },
                        f,
                        ensure_ascii=False,
                        indent=2,
                    )

                # 根据scope区分显示项目方法论或全局方法论
                methodology_type = "项目" if scope == "project" else "全局"
                PrettyOutput.auto_print(
                    f"ℹ️ 已保存{methodology_type}方法论到 {file_path}"
                )

                action = "更新" if os.path.exists(file_path) else "添加"
                return {
                    "success": True,
                    "stdout": f"{action}{scope}方法论：{problem_type}",
                    "stderr": "",
                }

            else:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"不支持的操作类型: {operation}",
                }

        except Exception as e:
            return {"success": False, "stdout": "", "stderr": f"执行失败: {str(e)}"}
