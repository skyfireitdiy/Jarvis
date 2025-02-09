import os
import yaml
from typing import Dict, Optional, Any
from jarvis.utils import OutputType, PrettyOutput


class MethodologyTool:
    """Experience management tool"""
    
    name = "methodology"
    description = "Manage problem-solving methodologies, supporting add, update, and delete operations"
    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": "Operation type (delete/update/add)",
                "enum": ["delete", "update", "add"]
            },
            "problem_type": {
                "type": "string",
                "description": "Problem type, e.g., code_review, bug_fix, etc."
            },
            "content": {
                "type": "string",
                "description": "Methodology content (required for update/add)",
                "optional": True
            }
        },
        "required": ["operation", "problem_type"]
    }
    
    def __init__(self):
        """Initialize the experience management tool"""
        self.methodology_file = os.path.expanduser("~/.jarvis/methodology")
        self._ensure_file_exists()
            
    def _ensure_file_exists(self):
        """Ensure the methodology file exists"""
        if not os.path.exists(self.methodology_file):
            try:
                with open(self.methodology_file, 'w', encoding='utf-8') as f:
                    yaml.safe_dump({}, f, allow_unicode=True)
            except Exception as e:
                PrettyOutput.print(f"Failed to create methodology file: {str(e)}", OutputType.ERROR)
                
    def _load_methodologies(self) -> Dict:
        """Load all methodologies"""
        try:
            with open(self.methodology_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            PrettyOutput.print(f"Failed to load methodologies: {str(e)}", OutputType.ERROR)
            return {}
            
    def _save_methodologies(self, methodologies: Dict):
        """Save all methodologies"""
        try:
            with open(self.methodology_file, 'w', encoding='utf-8') as f:
                yaml.safe_dump(methodologies, f, allow_unicode=True)
        except Exception as e:
            PrettyOutput.print(f"Failed to save methodologies: {str(e)}", OutputType.ERROR)
            
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the operation of managing methodologies
        
        Args:
            args: A dictionary containing the operation parameters
                - operation: The operation type (delete/update/add)
                - problem_type: The problem type
                - content: The methodology content (required for update/add)
            
        Returns:
            Dict[str, Any]: A dictionary containing the execution result
        """
        operation = args.get("operation")
        problem_type = args.get("problem_type")
        content = args.get("content")
        
        if not operation or not problem_type:
            return {
                "success": False,
                "error": "Missing required parameters: operation and problem_type"
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
                        "error": f"Methodology for problem type '{problem_type}' not found"
                    }
                    
            elif operation in ["update", "add"]:
                if not content:
                    return {
                        "success": False,
                        "error": "Need to provide methodology content"
                    }
                    
                methodologies[problem_type] = content
                self._save_methodologies(methodologies)
                
                action = "Update" if problem_type in methodologies else "Add"
                return {
                    "success": True,
                    "stdout": f"{action} methodology for problem type '{problem_type}'"
                }
                
            else:
                return {
                    "success": False,
                    "error": f"Unsupported operation type: {operation}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Execution failed: {str(e)}"
            }
            
    def get_methodology(self, problem_type: str) -> Optional[str]:
        """Get the methodology for a specific problem type
        
        Args:
            problem_type: The problem type
            
        Returns:
            Optional[str]: The methodology content, or None if it does not exist
        """
        methodologies = self._load_methodologies()
        return methodologies.get(problem_type) 