import os
import yaml
from typing import Dict, Optional, Any
from jarvis.utils import OutputType, PrettyOutput


class MethodologyTool:
    """经验管理工具"""
    
    name = "methodology"
    description = "管理问题处理经验总结，支持添加、更新、删除操作"
    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": "操作类型 (delete/update/add)",
                "enum": ["delete", "update", "add"]
            },
            "problem_type": {
                "type": "string",
                "description": "问题类型，例如：code_review, bug_fix 等"
            },
            "content": {
                "type": "string",
                "description": "经验总结内容 (update/add 时必需)",
                "optional": True
            }
        },
        "required": ["operation", "problem_type"]
    }
    
    def __init__(self):
        """初始化经验管理工具"""
        self.methodology_file = os.path.expanduser("~/.jarvis_methodology")
        self._ensure_file_exists()
            
    def _ensure_file_exists(self):
        """确保经验总结文件存在"""
        if not os.path.exists(self.methodology_file):
            try:
                with open(self.methodology_file, 'w', encoding='utf-8') as f:
                    yaml.safe_dump({}, f, allow_unicode=True)
            except Exception as e:
                PrettyOutput.print(f"创建经验总结文件失败: {str(e)}", OutputType.ERROR)
                
    def _load_methodologies(self) -> Dict:
        """加载所有经验总结"""
        try:
            with open(self.methodology_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            PrettyOutput.print(f"加载经验总结失败: {str(e)}", OutputType.ERROR)
            return {}
            
    def _save_methodologies(self, methodologies: Dict):
        """保存所有经验总结"""
        try:
            with open(self.methodology_file, 'w', encoding='utf-8') as f:
                yaml.safe_dump(methodologies, f, allow_unicode=True)
        except Exception as e:
            PrettyOutput.print(f"保存经验总结失败: {str(e)}", OutputType.ERROR)
            
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行经验总结管理操作
        
        Args:
            args: 包含操作参数的字典
                - operation: 操作类型 (delete/update/add)
                - problem_type: 问题类型
                - content: 经验总结内容 (update/add 时必需)
            
        Returns:
            Dict[str, Any]: 包含执行结果的字典
        """
        operation = args.get("operation")
        problem_type = args.get("problem_type")
        content = args.get("content")
        
        if not operation or not problem_type:
            return {
                "success": False,
                "error": "缺少必要参数: operation 和 problem_type"
            }
            
        methodologies = self._load_methodologies()
        
        try:
            if operation == "delete":
                if problem_type in methodologies:
                    del methodologies[problem_type]
                    self._save_methodologies(methodologies)
                    return {
                        "success": True,
                        "stdout": f"已删除问题类型 '{problem_type}' 的经验总结"
                    }
                else:
                    return {
                        "success": False,
                        "error": f"未找到问题类型 '{problem_type}' 的经验总结"
                    }
                    
            elif operation in ["update", "add"]:
                if not content:
                    return {
                        "success": False,
                        "error": "需要提供经验总结内容"
                    }
                    
                methodologies[problem_type] = content
                self._save_methodologies(methodologies)
                
                action = "更新" if problem_type in methodologies else "添加"
                return {
                    "success": True,
                    "stdout": f"已{action}问题类型 '{problem_type}' 的经验总结"
                }
                
            else:
                return {
                    "success": False,
                    "error": f"不支持的操作类型: {operation}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"执行失败: {str(e)}"
            }
            
    def get_methodology(self, problem_type: str) -> Optional[str]:
        """获取指定问题类型的经验总结
        
        Args:
            problem_type: 问题类型
            
        Returns:
            Optional[str]: 经验总结内容，如果不存在则返回 None
        """
        methodologies = self._load_methodologies()
        return methodologies.get(problem_type) 