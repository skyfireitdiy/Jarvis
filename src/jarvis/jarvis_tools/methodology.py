import os
import yaml
from typing import Dict, Optional, Any

from jarvis.jarvis_utils.config import is_use_methodology
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
                "description": "问题类型，例如：code_review, bug_fix 等"
            },
            "content": {
                "type": "string",
                "description": "方法论内容（更新和添加时必填）",
                "optional": True
            }
        },
        "required": ["operation", "problem_type"]
    }

    @staticmethod
    def check()->bool:
        """检查是否启用了方法论功能"""
        return is_use_methodology()
    
    def __init__(self):
        """初始化经验管理工具"""
        self.methodology_file = os.path.expanduser("~/.jarvis/methodology")
        self._ensure_file_exists()
            
    def _ensure_file_exists(self):
        """确保方法论文件存在"""
        if not os.path.exists(self.methodology_file):
            try:
                with open(self.methodology_file, 'w', encoding='utf-8', errors="ignore") as f:
                    yaml.safe_dump({}, f, allow_unicode=True)
            except Exception as e:
                PrettyOutput.print(f"创建方法论文件失败：{str(e)}", OutputType.ERROR)
                
    def _load_methodologies(self) -> Dict:
        """加载所有方法论"""
        try:
            with open(self.methodology_file, 'r', encoding='utf-8', errors="ignore") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            PrettyOutput.print(f"加载方法论失败: {str(e)}", OutputType.ERROR)
            return {}
                
    def _save_methodologies(self, methodologies: Dict):
        """保存所有方法论"""
        try:
            with open(self.methodology_file, 'w', encoding='utf-8', errors="ignore") as f:
                yaml.safe_dump(methodologies, f, allow_unicode=True)
        except Exception as e:
            PrettyOutput.print(f"保存方法论失败: {str(e)}", OutputType.ERROR)
            
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
                "stderr": "Missing required parameters: operation and problem_type"
            }
            
        methodologies = self._load_methodologies()
        
        try:
            if operation == "delete":
                if problem_type in methodologies:
                    del methodologies[problem_type]
                    self._save_methodologies(methodologies)
                    return {
                        "success": True,
                        "stdout": f"Deleted methodology for problem type '{problem_type}'"
                    }
                else:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": f"Methodology for problem type '{problem_type}' not found"
                    }
                    
            elif operation in ["update", "add"]:
                if not content:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "Need to provide methodology content"
                    }
                    
                methodologies[problem_type] = content
                self._save_methodologies(methodologies)
                
                action = "Update" if problem_type in methodologies else "Add"
                return {
                    "success": True,
                    "stdout": f"{action} methodology for problem type '{problem_type}'",
                    "stderr": ""
                }
                
            else:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Unsupported operation type: {operation}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Execution failed: {str(e)}"
            }
            
    def get_methodology(self, problem_type: str) -> Optional[str]:
        """获取特定问题类型的方法论
        
        Args:
            problem_type: 问题类型
            
        Returns:
            Optional[str]: 方法论内容，如果不存在则返回 None
        """
        methodologies = self._load_methodologies()
        return methodologies.get(problem_type) 