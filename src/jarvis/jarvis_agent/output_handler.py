# -*- coding: utf-8 -*-
from abc import ABC, abstractmethod
from typing import Any, Tuple


class OutputHandler(ABC):
    @abstractmethod
    def handle(self, response: str, agent: Any) -> Tuple[bool, Any]:
        """处理响应数据

        Args:
            response: 需要处理的响应字符串
            agent: 执行处理的agent实例

        Returns:
            Tuple[bool, Any]: 返回处理结果元组，第一个元素表示是否处理成功，第二个元素为处理后的数据
        """
        pass

    @abstractmethod
    def can_handle(self, response: str) -> bool:
        """判断是否能处理给定的响应

        Args:
            response: 需要判断的响应字符串

        Returns:
            bool: 返回是否能处理该响应
        """
        pass

    @abstractmethod
    def prompt(self) -> str:
        """获取处理器的提示信息

        Returns:
            str: 返回处理器的提示字符串
        """
        pass

    @abstractmethod
    def name(self) -> str:
        """获取处理器的名称

        Returns:
            str: 返回处理器的名称字符串
        """
        pass
