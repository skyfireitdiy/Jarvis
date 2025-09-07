# -*- coding: utf-8 -*-
"""
AgentConfig: 聚合 Agent 的初始化配置并提供默认值解析。

目标（阶段一，最小变更）：
- 提供独立的配置承载类，封装 __init__ 中的配置项
- 支持从全局配置与上下文推导默认值
- 暂不强制替换 Agent 的现有参数与流程，后续逐步接入
"""
from dataclasses import dataclass, field
from typing import List, Optional

from jarvis.jarvis_agent.prompts import DEFAULT_SUMMARY_PROMPT
from jarvis.jarvis_utils.config import (
    get_max_token_count,
    is_execute_tool_confirm,
    is_force_save_memory,
    is_use_analysis,
    is_use_methodology,
)


@dataclass
class AgentConfig:
    # 核心身份与系统参数
    system_prompt: str
    name: str = "Jarvis"
    description: str = ""
    model_group: Optional[str] = None

    # 运行行为
    auto_complete: bool = False
    need_summary: bool = True

    # 可选配置（None 表示使用默认策略解析）
    summary_prompt: Optional[str] = None
    execute_tool_confirm: Optional[bool] = None
    use_methodology: Optional[bool] = None
    use_analysis: Optional[bool] = None
    force_save_memory: Optional[bool] = None
    files: Optional[List[str]] = field(default_factory=list)
    max_token_count: Optional[int] = None

    def resolve_defaults(self) -> "AgentConfig":
        """
        解析并填充默认值，返回新的 AgentConfig 实例，不修改原对象。
        策略与 Agent._init_config 中的逻辑保持一致，确保兼容。
        """
        # 复制当前实例的浅拷贝数据
        cfg = AgentConfig(
            system_prompt=self.system_prompt,
            name=self.name,
            description=self.description,
            model_group=self.model_group,
            auto_complete=self.auto_complete,
            need_summary=self.need_summary,
            summary_prompt=self.summary_prompt,
            execute_tool_confirm=self.execute_tool_confirm,
            use_methodology=self.use_methodology,
            use_analysis=self.use_analysis,
            force_save_memory=self.force_save_memory,
            files=list(self.files or []),
            max_token_count=self.max_token_count,
        )

        # use_methodology: 若存在上传文件则禁用；否则按照外部传入或全局默认
        if cfg.files:
            cfg.use_methodology = False
        elif cfg.use_methodology is None:
            cfg.use_methodology = is_use_methodology()

        # use_analysis
        if cfg.use_analysis is None:
            cfg.use_analysis = is_use_analysis()

        # execute_tool_confirm
        if cfg.execute_tool_confirm is None:
            cfg.execute_tool_confirm = is_execute_tool_confirm()

        # summary_prompt
        if cfg.summary_prompt is None:
            cfg.summary_prompt = DEFAULT_SUMMARY_PROMPT

        # max_token_count
        if cfg.max_token_count is None:
            cfg.max_token_count = get_max_token_count(cfg.model_group)

        # force_save_memory
        if cfg.force_save_memory is None:
            cfg.force_save_memory = is_force_save_memory()

        return cfg
