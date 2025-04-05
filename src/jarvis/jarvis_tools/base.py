from typing import Dict, Any, Callable
import json
class Tool:
    """工具类，用于封装工具的基本信息和执行方法"""

    def __init__(self, name: str, description: str, parameters: Dict, func: Callable):
        """
        初始化工具对象

        参数:
            name (str): 工具名称
            description (str): 工具描述
            parameters (Dict): 工具参数定义
            func (Callable): 工具执行函数
        """
        self.name = name
        self.description = description
        self.parameters = parameters
        self.func = func
    def to_dict(self) -> Dict:
        """将工具对象转换为字典格式，主要用于序列化"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": json.dumps(self.parameters, ensure_ascii=False)
        }

    def execute(self, arguments: Dict) -> Dict[str, Any]:
        """
        执行工具函数

        参数:
            arguments (Dict): 工具执行所需的参数

        返回:
            Dict[str, Any]: 工具执行结果
        """
        return self.func(arguments)