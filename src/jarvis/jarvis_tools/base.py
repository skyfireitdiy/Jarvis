# -*- coding: utf-8 -*-
import inspect
import json
from typing import Any
from typing import Callable
from typing import Dict


def _accepts_kwargs(func: Callable[..., Any]) -> bool:
    """判断函数是否接受以关键字形式传入任意参数。

    判定为 True 的情形：
    - 签名含 VAR_KEYWORD（`**kwargs`）；
    - 签名无法解析（内置函数、C 扩展等），保守按关键字调用尝试。

    参数:
        func: 待判断的可调用对象

    返回:
        bool: 可以用 `func(**arguments)` 调用时返回 True
    """
    try:
        params = inspect.signature(func).parameters.values()
    except (TypeError, ValueError):
        return True
    return any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params)


class Tool:
    """工具类，用于封装工具的基本信息和执行方法"""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        func: Callable[[Dict[str, Any]], Dict[str, Any]],
        protocol_version: str = "1.0",
        interactive: bool = False,
    ) -> None:
        """
        初始化工具对象

        参数:
            name (str): 工具名称
            description (str): 工具描述
            parameters (Dict[str, Any]): 工具参数定义
            func (Callable): 工具执行函数
            protocol_version (str): 工具协议版本，默认"1.0"；支持"1.0"或"2.0"
            interactive (bool): 是否可交互/独占。True 表示该工具与用户/终端有交互
                （如 execute_script、virtual_tty），原生并行调用时整批降级为串行。
        """
        self.name = name
        self.description = description
        self.parameters = parameters
        self.func = func
        self.protocol_version = protocol_version
        self.interactive = interactive

    def to_dict(self) -> Dict[str, Any]:
        """将工具对象转换为字典格式，主要用于序列化"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": json.dumps(self.parameters, ensure_ascii=False),
        }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行工具函数

        参数:
            arguments (Dict): 工具执行所需的参数

        返回:
            Dict[str, Any]: 工具执行结果
        """
        try:
            # func 可能是两种签名风格：
            #   1) 位置参数风格 func(arguments) —— 传统 Tool 用法
            #   2) 关键字参数风格 func(**kwargs) —— 独立类工具的 execute 方法
            #       （如 browser_ext_sessions / daemon_sessions 的 execute(self, **kwargs)）
            # 按签名静态判定，不能用 TypeError 兜底：那会把工具内部真实的 TypeError
            # 误判为"签名不匹配"，从而用位置参数再调一次，掩盖错误且可能以错误参数执行。
            if isinstance(arguments, dict) and _accepts_kwargs(self.func):
                # func 可能是 **kwargs 风格，类型标注按位置参数，属误报
                return self.func(**arguments)  # ty: ignore[missing-argument]
            return self.func(arguments)
        except Exception as e:
            return {
                "success": False,
                "stderr": f"工具 {self.name} 执行失败: {str(e)}",
                "stdout": "",
            }
