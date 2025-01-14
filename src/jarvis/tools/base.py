from typing import Dict, Any, Callable
import json



class Tool:
    def __init__(self, name: str, description: str, parameters: Dict, func: Callable):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.func = func

    def to_dict(self) -> Dict:
        """转换为工具格式"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": json.dumps(self.parameters, ensure_ascii=False)
        }

    def execute(self, arguments: Dict) -> Dict[str, Any]:
        """执行工具函数"""
        return self.func(arguments)
