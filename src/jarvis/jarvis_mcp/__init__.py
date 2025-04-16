from abc import ABC, abstractmethod
from typing import Any, Dict, List


class McpClient(ABC):
    """MCP客户端抽象基类"""
    
    @abstractmethod
    def get_tool_list(self) -> List[Dict[str, Any]]:
        """获取工具列表
        
        返回:
            List[Dict[str, Any]]: 工具列表，每个工具包含以下字段：
                - name: str - 工具名称
                - description: str - 工具描述
                - parameters: Dict - 工具参数
        """
        pass
    
    @abstractmethod
    def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具
        
        参数:
            tool_name: 工具名称
            arguments: 参数字典，包含工具执行所需的参数
            
        返回:
            Dict[str, Any]: 执行结果，包含以下字段：
                - success: bool - 是否执行成功
                - stdout: str - 标准输出
                - stderr: str - 标准错误
        """
        pass

    @abstractmethod
    def get_resource_list(self) -> List[Dict[str, Any]]:
        """获取资源列表
        
        返回:
            List[Dict[str, Any]]: 资源列表，每个资源包含以下字段：
                - uri: str - 资源的唯一标识符
                - name: str - 资源的名称
                - description: str - 资源的描述（可选）
                - mimeType: str - 资源的MIME类型（可选）
        """
        pass

    @abstractmethod
    def get_resource(self, uri: str) -> Dict[str, Any]:
        """获取指定资源的内容
        
        参数:
            uri: str - 资源的URI标识符
            
        返回:
            Dict[str, Any]: 资源内容，包含以下字段：
                - uri: str - 资源的URI
                - mimeType: str - 资源的MIME类型（可选）
                - text: str - 文本内容（如果是文本资源）
                - blob: str - 二进制内容（如果是二进制资源，base64编码）
        """
        pass


