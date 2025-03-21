import os
import json
import glob
import hashlib
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
        self.methodology_dir = os.path.expanduser("~/.jarvis/methodologies")
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
                
    def _load_methodologies(self) -> Dict[str, str]:
        """加载所有方法论"""
        all_methodologies = {}
        
        if not os.path.exists(self.methodology_dir):
            return all_methodologies
        
        for filepath in glob.glob(os.path.join(self.methodology_dir, "*.json")):
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    methodology = json.load(f)
                    problem_type = methodology.get("problem_type", "")
                    content = methodology.get("content", "")
                    if problem_type and content:
                        all_methodologies[problem_type] = content
            except Exception as e:
                filename = os.path.basename(filepath)
                PrettyOutput.print(f"加载方法论文件 {filename} 失败: {str(e)}", OutputType.WARNING)
        
        return all_methodologies
            
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
            
        try:
            if operation == "delete":
                # 获取方法论文件路径
                file_path = self._get_methodology_file_path(problem_type)
                
                # 检查文件是否存在
                if os.path.exists(file_path):
                    os.remove(file_path)
                    return {
                        "success": True,
                        "stdout": f"Deleted methodology for problem type '{problem_type}'",
                        "stderr": ""
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
                
                action = "Updated" if os.path.exists(file_path) else "Added"
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
        file_path = self._get_methodology_file_path(problem_type)
        
        if not os.path.exists(file_path):
            return None
        
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                methodology = json.load(f)
                return methodology.get("content")
        except Exception as e:
            PrettyOutput.print(f"读取方法论失败: {str(e)}", OutputType.ERROR)
            return None 