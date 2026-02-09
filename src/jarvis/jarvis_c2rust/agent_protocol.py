# -*- coding: utf-8 -*-
"""
Agent和CodeAgent的抽象协议接口

使用typing.Protocol定义接口规范，解耦对具体Agent实现的依赖。
支持未来迁移到其他Agent实现（如其他LLM平台的Agent）。
"""

from typing import Any
from typing import Callable
from typing import Optional
from typing import Protocol
from typing import runtime_checkable


@runtime_checkable
class EventBusProtocol(Protocol):
    """事件总线协议"""

    def subscribe(self, event: str, callback: Callable[..., Any]) -> None:
        """订阅事件"""
        ...

    def emit(self, event: str, **kwargs: Any) -> None:
        """触发事件"""
        ...


@runtime_checkable
class SessionProtocol(Protocol):
    """会话管理协议"""

    prompt: str

    def clear_history(self) -> None:
        """清除历史记录"""
        ...


@runtime_checkable
class AgentProtocol(Protocol):
    """
    Agent基础协议

    定义Agent必须实现的接口，包括核心属性和方法。
    任何实现此协议的Agent都可以被jc2r使用。

    注意：Protocol使用结构子类型，只要实现包含所需属性和方法即可。
    实际的Agent/CodeAgent类可能包含更多属性，这里只定义jc2r需要的核心接口。
    """

    # 核心属性（使用更宽松的类型以兼容不同实现）
    event_bus: Any  # 实际是EventBus，但用Any避免类型冲突
    session: Any  # 实际是SessionManager，但用Any避免类型冲突
    name: str
    non_interactive: Optional[bool]  # 允许None以兼容实际实现

    def run(self, user_input: str, **kwargs: Any) -> Any:
        """
        运行Agent处理用户输入

        参数:
            user_input: 用户输入文本
            **kwargs: 额外参数（如prefix、suffix等）

        返回:
            Agent的执行结果
        """
        ...

    def clear_history(self) -> None:
        """清除会话历史"""
        ...

    def get_user_origin_input(self) -> str:
        """获取原始用户输入"""
        ...


@runtime_checkable
class CodeAgentProtocol(AgentProtocol, Protocol):
    """
    CodeAgent扩展协议

    继承AgentProtocol，添加代码Agent特有的接口。
    主要用于代码生成、修复和优化等场景。
    """

    # CodeAgent特有属性
    root_dir: str
    tool_group: Optional[str]
    disable_review: bool
    review_max_iterations: int
    prefix: str
    suffix: str
    start_commit: Optional[str]

    def get_user_data(self, key: str) -> Any:
        """
        获取用户数据

        参数:
            key: 数据键

        返回:
            存储的用户数据
        """
        ...


# 类型别名，用于类型注解
AgentType = AgentProtocol
CodeAgentType = CodeAgentProtocol
