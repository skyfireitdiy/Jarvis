from typing import Any
from typing import Protocol
from typing import Tuple
from typing import runtime_checkable


@runtime_checkable
class OutputHandlerProtocol(Protocol):
    """
    定义输出处理器的接口，该处理器负责处理模型的响应，通常用于执行工具。
    """

    def name(self) -> str:
        """返回处理器的名称。"""
        ...

    def can_handle(self, response: str) -> bool:
        """判断此处理器能否处理给定的响应。"""
        ...

    def prompt(self) -> str:
        """返回描述处理器功能的提示片段。"""
        ...

    def handle(self, response: str, agent: Any) -> Tuple[bool, Any]:
        """
        处理响应，执行相关逻辑。

        返回：
            一个元组，包含一个布尔值（是否返回）和结果。
        """
        ...
