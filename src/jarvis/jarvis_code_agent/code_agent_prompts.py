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
    """以 normal_llm 分类用户需求

    参数:
        user_input: 用户所请之述（纯文本或多模态皆可）

    返回:
        Tuple[str, str]: (场景类型, 难度等级)
    """
    return _classify_user_request_impl(
        user_input,
        scenario_subdir=_SCENARIO_SUBDIR,
        default_scenario_name="通用开发",
        classification_context="开发场类",
        difficulty_descriptions={
            "easy": "单文件之改、简配置之调、明小之动",
            "medium": "多文件之改、须明业务之逻、涉一定之繁",
            "hard": "架构级之改、复重构、须深析细设",
        },
    )


def get_system_prompt(scenario: str = "default") -> str:
    """据场景取对应系统提示词

    参数:
        scenario: 场景类型

    返回:
        str: 对应场景之完整系统提示词
    """
    return _get_system_prompt_impl(scenario, scenario_subdir=_SCENARIO_SUBDIR)
