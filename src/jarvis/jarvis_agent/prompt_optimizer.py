# -*- coding: utf-8 -*-
"""系统提示词优化模块

此模块供依用户需求自动优化系统提示词之能。
"""

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.output import PrettyOutput


def optimize_system_prompt(
    current_system_prompt: str,
    user_requirement: str,
) -> str:
    """依用户需求优化系统提示词

    参数:
        current_system_prompt: 当前之系统提示词
        user_requirement: 用户需求之描述

    返回:
        str: 优化后之系统提示词
    """
    try:
        PrettyOutput.auto_print("🔄 正在优化系统提示词...")

        # 获取 smart_llm 平台（使用智能模型进行优化）
        # get_smart_platform 内部已经设置了 model_name 和 llm_group，无需再次设置
        platform = PlatformRegistry().get_normal_platform()

        platform.set_suppress_output(False)

        # 构建优化提示词
        optimization_prompt = f"""汝乃专业之系统提示词优化专家。请依当前之系统提示词与用户需求，有针对性地优化系统提示词。

<current_system_prompt>
{current_system_prompt}
</current_system_prompt>

<user_requirement>
{user_requirement}
</user_requirement>

【优化要求】
1. 保持原有系统提示词之核心功能与架构不变
2. 依用户需求，有针对性地增强或调整相关部分之描述
3. 确保优化后之提示词更加贴合用户之具体任务场景
4. 保持提示词之结构清晰、逻辑完整
5. 若用户需求涉及特定领域（如代码开发、数据分析等），可适当强调相关之最佳实践与注意事项
6. 优化后之提示词应能助AI更好地理解并执行用户之具体需求

请直出优化后之完整系统提示词，勿含任何解释或说明文字。"""

        # 调用大模型进行优化
        optimized_prompt = platform.chat_until_success(optimization_prompt)

        if optimized_prompt and optimized_prompt.strip():
            PrettyOutput.auto_print("✅ 系统提示词优化完成")
            return optimized_prompt.strip()
        else:
            PrettyOutput.auto_print("⚠️ 优化结果为空，使用原始系统提示词")
            return current_system_prompt

    except Exception as e:
        PrettyOutput.auto_print(f"⚠️ 系统提示词优化失败: {str(e)}，使用原始系统提示词")
        return current_system_prompt
