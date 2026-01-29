# -*- coding: utf-8 -*-
"""CodeAgent 系统提示词模块"""

from pathlib import Path
from typing import Dict

import yaml

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.output import PrettyOutput


# 提示词文件目录
_PROMPTS_DIR = (
    Path(__file__).parent.parent.parent.parent
    / "builtin"
    / "prompts"
    / "code_agent_system"
)
_SCENARIOS_FILE = _PROMPTS_DIR / "scenarios.yaml"


def _load_scenario_types() -> Dict[str, Dict[str, str]]:
    """从文件加载场景类型定义

    返回:
        Dict[str, Dict[str, str]]: 场景类型字典，格式为 {scenario_id: {"name": "...", "description": "..."}}

    异常:
        FileNotFoundError: 如果文件不存在
        IOError: 如果文件读取失败
        ValueError: 如果文件格式不正确
    """
    if not _SCENARIOS_FILE.exists():
        raise FileNotFoundError(
            f"场景类型定义文件不存在: {_SCENARIOS_FILE}。请确保文件存在于 {_PROMPTS_DIR} 目录下。"
        )

    try:
        with open(_SCENARIOS_FILE, "r", encoding="utf-8") as f:
            scenarios = yaml.safe_load(f)
            if not isinstance(scenarios, dict):
                raise ValueError(f"场景类型定义文件格式不正确: {_SCENARIOS_FILE}")

            # 验证每个场景都有 name 和 description
            for scenario_id, scenario_info in scenarios.items():
                if not isinstance(scenario_info, dict):
                    raise ValueError(
                        f"场景 '{scenario_id}' 的定义格式不正确，应为字典格式"
                    )
                if "name" not in scenario_info or "description" not in scenario_info:
                    raise ValueError(
                        f"场景 '{scenario_id}' 缺少必需的字段 'name' 或 'description'"
                    )

            return scenarios
    except yaml.YAMLError as e:
        raise IOError(f"解析场景类型定义文件失败 ({_SCENARIOS_FILE}): {e}") from e
    except Exception as e:
        raise IOError(f"加载场景类型定义文件失败 ({_SCENARIOS_FILE}): {e}") from e


def _get_scenario_types() -> Dict[str, str]:
    """获取场景类型名称字典（向后兼容）

    返回:
        Dict[str, str]: {scenario_id: scenario_name}
    """
    scenarios = _load_scenario_types()
    return {
        scenario_id: scenario_info["name"]
        for scenario_id, scenario_info in scenarios.items()
    }


# 场景类型定义（向后兼容，实际从文件加载）
SCENARIO_TYPES = _get_scenario_types()


def classify_user_request(user_input: str) -> str:
    """使用 normal_llm 对用户需求进行分类

    参数:
        user_input: 用户输入的需求描述

    返回:
        str: 场景类型（performance/bug_fix/warning/refactor/feature/default）
    """
    try:
        # 获取 normal_llm 平台
        platform = PlatformRegistry().get_normal_platform()

        # 从文件加载场景类型定义
        scenarios = _load_scenario_types()

        # 构建分类提示词
        scenarios_list = []
        scenario_ids = []
        for idx, (scenario_id, scenario_info) in enumerate(scenarios.items(), 1):
            scenario_name = scenario_info["name"]
            scenario_desc = scenario_info["description"]
            scenarios_list.append(
                f"{idx}. {scenario_id}（{scenario_name}）：{scenario_desc}"
            )
            scenario_ids.append(scenario_id)

        scenarios_text = "\n".join(scenarios_list)
        scenario_ids_text = "/".join(scenario_ids)

        classification_prompt = f"""请分析以下用户需求，判断其属于哪个开发场景类型。

用户需求：
{user_input}

可选场景类型：
{scenarios_text}

请只返回场景类型的英文标识（{scenario_ids_text}），不要包含其他内容。
如果无法明确判断，返回 default。
"""

        # 使用 normal_llm 进行分类
        response = platform.chat_until_success(classification_prompt)

        # 解析响应，提取场景类型
        response = response.strip().lower()

        # 检查响应是否包含有效的场景类型
        for scenario_type in SCENARIO_TYPES.keys():
            if scenario_type in response or response == scenario_type:
                PrettyOutput.auto_print(
                    f"📋 需求分类结果: {SCENARIO_TYPES[scenario_type]} ({scenario_type})"
                )
                return scenario_type

        # 如果无法识别，返回默认类型
        PrettyOutput.auto_print("📋 需求分类结果: 通用开发 (default)")
        return "default"

    except Exception as e:
        # 分类失败时返回默认类型
        PrettyOutput.auto_print(f"⚠️ 需求分类失败: {e}，使用默认场景")
        return "default"


def _load_prompt_from_file(scenario: str) -> str:
    """从文件加载提示词

    参数:
        scenario: 场景类型

    返回:
        str: 提示词内容

    异常:
        FileNotFoundError: 如果文件不存在
        IOError: 如果文件读取失败
    """
    prompt_file = _PROMPTS_DIR / f"{scenario}.md"
    if not prompt_file.exists():
        raise FileNotFoundError(
            f"提示词文件不存在: {prompt_file}。请确保文件存在于 {_PROMPTS_DIR} 目录下。"
        )

    try:
        with open(prompt_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                raise ValueError(f"提示词文件为空: {prompt_file}")
            return content
    except Exception as e:
        raise IOError(f"加载提示词文件失败 ({prompt_file}): {e}") from e


def get_system_prompt(scenario: str = "default") -> str:
    """根据场景类型获取对应的系统提示词

    从文件加载完整的提示词。每个场景的提示词文件都包含完整的提示词内容，
    包括基础的 ARCHER 流程和场景特定的指导，可以根据场景调整 ARCHER 流程的要求。

    参数:
        scenario: 场景类型（performance/bug_fix/warning/refactor/feature/code_analysis/troubleshooting/deployment/config_modification/default）

    返回:
        str: 对应场景的完整系统提示词

    异常:
        FileNotFoundError: 如果提示词文件不存在
        IOError: 如果文件读取失败
    """
    # 直接从文件加载完整的提示词
    return _load_prompt_from_file(scenario)
