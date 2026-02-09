# -*- coding: utf-8 -*-
"""
Agent工厂模块

提供Agent和CodeAgent的创建工厂函数，解耦对具体实现的依赖。
默认使用Jarvis的Agent实现，支持未来切换到其他实现。
"""

from typing import Any
from typing import Optional

from jarvis.jarvis_c2rust.agent_protocol import AgentType
from jarvis.jarvis_c2rust.agent_protocol import CodeAgentType


# 默认使用Jarvis的Agent实现
# 导入放在函数中，避免模块加载时的循环依赖


def create_agent(
    system_prompt: str,
    name: str = "Jarvis",
    non_interactive: bool = True,
    use_methodology: bool = False,
    use_analysis: bool = False,
    need_summary: bool = False,
    rule_names: Optional[str] = None,
    **kwargs: Any,
) -> AgentType:
    """
    创建Agent实例

    参数:
        system_prompt: 系统提示词
        name: Agent名称
        non_interactive: 非交互模式
        use_methodology: 是否使用方法论
        use_analysis: 是否使用代码分析
        need_summary: 是否需要总结
        rule_names: 规则名称
        **kwargs: 其他参数

    返回:
        AgentProtocol兼容的Agent实例

    示例:
        >>> agent = create_agent(
        ...     system_prompt="You are a code reviewer",
        ...     name="Reviewer",
        ...     non_interactive=True
        ... )
        >>> result = agent.run("Review this code")
    """
    # 延迟导入，避免循环依赖
    from jarvis.jarvis_agent import Agent

    return Agent(  # type: ignore[return-value]
        system_prompt=system_prompt,
        name=name,
        non_interactive=non_interactive,
        use_methodology=use_methodology,
        use_analysis=use_analysis,
        need_summary=need_summary,
        rule_names=rule_names,
        **kwargs,
    )


def create_code_agent(
    name: str = "CodeAgent",
    non_interactive: bool = True,
    need_summary: bool = False,
    summary_prompt: Optional[str] = None,
    append_tools: Optional[str] = None,
    use_methodology: bool = True,
    use_analysis: bool = True,
    disable_review: bool = False,
    enable_task_list_manager: bool = False,
    force_save_memory: bool = False,
    tool_group: Optional[str] = None,
    rule_names: Optional[str] = None,
    **kwargs: Any,
) -> CodeAgentType:
    """
    创建CodeAgent实例

    参数:
        name: Agent名称
        non_interactive: 非交互模式
        need_summary: 是否需要总结
        summary_prompt: 总结提示词
        append_tools: 要追加的工具列表（逗号分隔）
        use_methodology: 是否使用方法论
        use_analysis: 是否使用代码分析
        disable_review: 是否禁用代码审查
        enable_task_list_manager: 是否启用任务列表管理器
        force_save_memory: 是否强制保存记忆
        tool_group: 工具组配置
        rule_names: 规则名称
        **kwargs: 其他参数

    返回:
        CodeAgentProtocol兼容的CodeAgent实例

    示例:
        >>> agent = create_code_agent(
        ...     name="C2Rust-GenerationAgent",
        ...     non_interactive=True,
        ...     append_tools="read_symbols",
        ...     use_methodology=True
        ... )
        >>> result = agent.run("Generate Rust code for this C function")
    """
    # 延迟导入，避免循环依赖
    from jarvis.jarvis_code_agent.code_agent import CodeAgent

    return CodeAgent(  # type: ignore[return-value]
        name=name,
        non_interactive=non_interactive,
        need_summary=need_summary,
        summary_prompt=summary_prompt,
        append_tools=append_tools,
        use_methodology=use_methodology,
        use_analysis=use_analysis,
        disable_review=disable_review,
        enable_task_list_manager=enable_task_list_manager,
        force_save_memory=force_save_memory,
        tool_group=tool_group,
        rule_names=rule_names,
        **kwargs,
    )
