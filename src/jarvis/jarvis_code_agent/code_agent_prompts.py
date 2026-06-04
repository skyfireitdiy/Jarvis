# -*- coding: utf-8 -*-
"""CodeAgent 系统提示词模块

场景提示词文件位于 builtin/prompts/code_agent_system/ 目录，
用户扩展文件可放置于 ~/.jarvis/prompts/code_agent_system/ 目录。
"""

from typing import Dict, List, Tuple, Union

from jarvis.jarvis_platform.content_types import ContentBlock
from jarvis.jarvis_utils.scenario_prompts import (
    _get_scenario_types,
    classify_user_request as _classify_user_request_impl,
    get_system_prompt as _get_system_prompt_impl,
)


# 场景子目录名
_SCENARIO_SUBDIR = "code_agent_system"

# 场景类型定义（向后兼容，实际从文件加载）
SCENARIO_TYPES: Dict[str, str] = _get_scenario_types(_SCENARIO_SUBDIR)


def classify_user_request(
    user_input: Union[str, List[ContentBlock]],
) -> Tuple[str, str]:
    """使用 normal_llm 对用户需求进行分类

    参数:
        user_input: 用户输入的需求描述（支持纯文本或多模态内容）

    返回:
        Tuple[str, str]: (场景类型, 难度等级)
    """
    return _classify_user_request_impl(
        user_input,
        scenario_subdir=_SCENARIO_SUBDIR,
        default_scenario_name="通用开发",
        classification_context="开发场景类型",
        difficulty_descriptions={
            "easy": "单文件修改、简单配置调整、明确的小改动",
            "medium": "多文件修改、需要理解业务逻辑、涉及一定复杂度",
            "hard": "架构级改动、复杂重构、需要深入分析和设计",
        },
    )


def get_system_prompt(scenario: str = "default") -> str:
    """根据场景类型获取对应的系统提示词

    参数:
        scenario: 场景类型

    返回:
        str: 对应场景的完整系统提示词
    """
    return _get_system_prompt_impl(scenario, scenario_subdir=_SCENARIO_SUBDIR)
