# -*- coding: utf-8 -*-
import os
from functools import lru_cache
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import cast

from jarvis.jarvis_utils.builtin_replace_map import BUILTIN_REPLACE_MAP
from jarvis.jarvis_utils.collections import CaseInsensitiveDict

# 全局环境变量存储

GLOBAL_CONFIG_DATA: CaseInsensitiveDict = CaseInsensitiveDict()


# 上下文长度限制常量
MAX_CONTEXT_LENGTH = 64 * 1024  # 64k token绝对上限


def calculate_token_limit(remaining_tokens: int) -> int:
    """
    计算token限制：取剩余token的2/3与MAX_CONTEXT_LENGTH的最小值

    Args:
        remaining_tokens: 剩余token数量

    Returns:
        int: 允许的最大token数（剩余token的2/3或64k，取较小值）
    """
    if remaining_tokens <= 0:
        return 0
    return min(int(remaining_tokens * 2 / 3), MAX_CONTEXT_LENGTH)


def set_global_config_data(env_data: Dict[str, Any]) -> None:
    """设置全局环境变量数据"""
    global GLOBAL_CONFIG_DATA
    GLOBAL_CONFIG_DATA = CaseInsensitiveDict(env_data)


def set_config(key: str, value: Any) -> None:
    """设置配置"""
    GLOBAL_CONFIG_DATA[key] = value


def get_llm_group() -> Optional[str]:
    """获取当前模型组名称

    返回:
        Optional[str]: 模型组名称，如果未设置则返回None
    """
    value = GLOBAL_CONFIG_DATA.get("llm_group")
    return cast(Optional[str], value)


def set_llm_group(llm_group: Optional[str]) -> None:
    """设置当前模型组

    参数:
        llm_group: 模型组名称，如果为 None 则不修改现有配置
    """
    # 只有当 llm_group 不为 None 时才设置，避免覆盖配置文件中的 llm_group
    if llm_group is not None:
        GLOBAL_CONFIG_DATA["llm_group"] = llm_group


"""配置管理模块。

该模块提供了获取Jarvis系统各种配置设置的函数。
所有配置都从环境变量中读取，带有回退默认值。
"""


def get_git_commit_prompt() -> str:
    """
    获取Git提交提示模板

    返回:
        str: Git提交信息生成提示模板，如果未配置则返回空字符串
    """
    return cast(str, GLOBAL_CONFIG_DATA.get("git_commit_prompt", ""))


def get_jarvis_github_url() -> str:
    """
    获取Jarvis的GitHub仓库地址

    返回:
        str: GitHub仓库地址，如果未配置则返回默认值
    """
    return cast(
        str,
        GLOBAL_CONFIG_DATA.get(
            "jarvis_github_url", "https://github.com/skyfireitdiy/Jarvis.git"
        ),
    )


def get_jarvis_gitee_url() -> str:
    """
    获取Jarvis的Gitee仓库地址

    返回:
        str: Gitee仓库地址，如果未配置则返回默认值
    """
    return cast(
        str,
        GLOBAL_CONFIG_DATA.get(
            "jarvis_gitee_url", "https://gitee.com/skyfireitdiy/Jarvis.git"
        ),
    )


@lru_cache(maxsize=None)
def get_replace_map() -> Dict[str, Any]:
    """
    获取替换映射表。

    优先使用GLOBAL_CONFIG_DATA['replace_map']的配置，
    如果未配置则返回内置替换映射表。

    返回:
        dict: 合并后的替换映射表字典(内置+配置中的映射表)
    """
    if "replace_map" in GLOBAL_CONFIG_DATA:
        return {**BUILTIN_REPLACE_MAP, **GLOBAL_CONFIG_DATA["replace_map"]}

    return BUILTIN_REPLACE_MAP.copy()


def get_max_input_token_count() -> int:
    """
    获取模型允许的最大输入token数量。

    返回:
        int: 模型能处理的最大输入token数量。
    """
    config = _get_resolved_model_config()
    return int(config.get("max_input_token_count", "128000"))


def calculate_content_token_limit(agent: Any = None) -> int:
    """
    基于当前模型配置动态计算内容长度限制（token数）

    参数:
        agent: Agent实例，用于获取模型和剩余token数量

    返回:
        int: 允许的最大token数（基于剩余token计算，保留安全余量）
    """
    try:
        # 优先使用剩余token数量
        if agent and hasattr(agent, "model"):
            try:
                remaining_tokens = agent.model.get_remaining_token_count()
                # 使用剩余token的2/3作为限制，保留1/3作为安全余量
                return calculate_token_limit(remaining_tokens)
            except Exception:
                pass

        # 回退方案：使用输入窗口的2/3
        max_input_tokens = get_max_input_token_count()
        # 计算2/3限制的token数
        return int(max_input_tokens * 2 / 3)
    except Exception:
        # 如果所有方法都失败，返回默认值500 token
        return 500


def get_cheap_max_input_token_count() -> int:
    """
    获取廉价模型允许的最大输入token数量。

    返回:
        int: 模型能处理的最大输入token数量，如果未配置则回退到正常配置
    """
    config = _get_resolved_model_config()
    cheap_max_token = config.get("cheap_max_input_token_count")
    if cheap_max_token:
        return int(cheap_max_token)
    return get_max_input_token_count()


def get_smart_max_input_token_count() -> int:
    """
    获取智能模型允许的最大输入token数量。

    返回:
        int: 模型能处理的最大输入token数量，如果未配置则回退到正常配置
    """
    config = _get_resolved_model_config()
    smart_max_token = config.get("smart_max_input_token_count")
    if smart_max_token:
        return int(smart_max_token)
    return get_max_input_token_count()


def get_shell_name() -> str:
    """
    获取系统shell名称。

    返回：
        str: Shell名称（例如bash, zsh, fish），默认为bash
    """
    shell_path = os.getenv("SHELL", "/bin/bash")
    return os.path.basename(shell_path).lower()


def _apply_llm_config_to_env(resolved_config: Dict[str, Any]) -> None:
    """
    将 resolved_config 中的 llm_config 应用到环境变量。

    参数:
        resolved_config: 解析后的模型配置字典
    """
    # 处理 normal_llm 的 llm_config
    if "llm_config" in resolved_config and isinstance(
        resolved_config["llm_config"], dict
    ):
        for key, value in resolved_config["llm_config"].items():
            if value is not None:
                # 将配置键转换为环境变量格式（大写，下划线分隔）
                env_key = str(key).upper()
                os.environ[env_key] = str(value)

    # 处理 cheap_llm 的 llm_config
    if "cheap_llm_config" in resolved_config and isinstance(
        resolved_config["cheap_llm_config"], dict
    ):
        for key, value in resolved_config["cheap_llm_config"].items():
            if value is not None:
                env_key = str(key).upper()
                os.environ[env_key] = str(value)

    # 处理 smart_llm 的 llm_config
    if "smart_llm_config" in resolved_config and isinstance(
        resolved_config["smart_llm_config"], dict
    ):
        for key, value in resolved_config["smart_llm_config"].items():
            if value is not None:
                env_key = str(key).upper()
                os.environ[env_key] = str(value)


def _resolve_llm_reference(llm_name: str) -> Dict[str, Any]:
    """
    从 llms 配置中解析引用的LLM配置。

    参数:
        llm_name: llms 中定义的LLM配置名称

    返回:
        Dict[str, Any]: 解析后的LLM配置字典，包含 platform, model, max_input_token_count, llm_config
    """
    from jarvis.jarvis_utils.output import PrettyOutput

    llms = GLOBAL_CONFIG_DATA.get("llms", {})
    if not isinstance(llms, dict):
        return {}

    llm_config = llms.get(llm_name)
    if not isinstance(llm_config, dict):
        PrettyOutput.auto_print(f"⚠️ 警告：llms 中未找到名为 '{llm_name}' 的配置")
        return {}

    return llm_config.copy()


def _expand_llm_references(group_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    展开 llm_groups 中的 llm 引用（normal_llm, cheap_llm, smart_llm）到对应的配置字段。

    注意：llm_groups 中不再支持直接定义 platform、model 等参数，只能通过引用 llms 中的配置。

    参数:
        group_config: 模型组配置字典

    返回:
        Dict[str, Any]: 展开后的配置字典

    异常:
        如果组配置中直接定义了 platform、model 等参数，会抛出 ValueError
    """
    expanded_config = group_config.copy()

    # 检查是否直接定义了不允许的参数
    forbidden_keys = [
        "platform",
        "model",
        "max_input_token_count",
        "cheap_platform",
        "cheap_model",
        "cheap_max_input_token_count",
        "smart_platform",
        "smart_model",
        "smart_max_input_token_count",
    ]
    found_forbidden = [key for key in forbidden_keys if key in expanded_config]
    if found_forbidden:
        raise ValueError(
            f"❌ 错误：llm_groups 中不再支持直接定义以下参数: {', '.join(found_forbidden)}。"
            f"请使用 normal_llm、cheap_llm、smart_llm 引用 llms 中定义的配置。"
        )

    # 验证至少需要 normal_llm 引用
    if "normal_llm" not in expanded_config:
        raise ValueError(
            "❌ 错误：llm_groups 中必须至少定义 normal_llm 引用。"
            "请使用 normal_llm 引用 llms 中定义的配置。"
        )

    # 处理 normal_llm 引用
    llm_ref = _resolve_llm_reference(expanded_config["normal_llm"])
    if not llm_ref:
        raise ValueError(
            f"❌ 错误：normal_llm 引用的 '{expanded_config['normal_llm']}' 在 llms 中不存在。"
        )
    # 直接使用引用的值，不再检查是否已存在
    expanded_config["platform"] = llm_ref.get("platform", "openai")
    expanded_config["model"] = llm_ref.get("model", "gpt-5")
    expanded_config["max_input_token_count"] = llm_ref.get(
        "max_input_token_count", 128000
    )
    # 合并 llm_config
    if "llm_config" in llm_ref:
        expanded_config["llm_config"] = llm_ref["llm_config"].copy()
    # 移除引用键
    expanded_config.pop("normal_llm", None)

    # 处理 cheap_llm 引用
    if "cheap_llm" in expanded_config:
        # 跳过空值（空字符串或 None）
        if not expanded_config.get("cheap_llm"):
            expanded_config.pop("cheap_llm", None)
        else:
            llm_ref = _resolve_llm_reference(expanded_config["cheap_llm"])
            if not llm_ref:
                raise ValueError(
                    f"❌ 错误：cheap_llm 引用的 '{expanded_config['cheap_llm']}' 在 llms 中不存在。"
                )
            # 直接使用引用的值
            expanded_config["cheap_platform"] = llm_ref.get("platform", "openai")
            expanded_config["cheap_model"] = llm_ref.get("model", "gpt-5")
            expanded_config["cheap_max_input_token_count"] = llm_ref.get(
                "max_input_token_count", 128000
            )
            # 合并 llm_config
            if "llm_config" in llm_ref:
                expanded_config["cheap_llm_config"] = llm_ref["llm_config"].copy()
            expanded_config.pop("cheap_llm", None)

    # 处理 smart_llm 引用
    if "smart_llm" in expanded_config:
        # 跳过空值（空字符串或 None）
        if not expanded_config.get("smart_llm"):
            expanded_config.pop("smart_llm", None)
        else:
            llm_ref = _resolve_llm_reference(expanded_config["smart_llm"])
            if not llm_ref:
                raise ValueError(
                    f"❌ 错误：smart_llm 引用的 '{expanded_config['smart_llm']}' 在 llms 中不存在。"
                )
            # 直接使用引用的值
            expanded_config["smart_platform"] = llm_ref.get("platform", "openai")
            expanded_config["smart_model"] = llm_ref.get("model", "gpt-5")
            expanded_config["smart_max_input_token_count"] = llm_ref.get(
                "max_input_token_count", 128000
            )
            # 合并 llm_config
            if "llm_config" in llm_ref:
                expanded_config["smart_llm_config"] = llm_ref["llm_config"].copy()
            expanded_config.pop("smart_llm", None)

    return expanded_config


def _get_resolved_model_config() -> Dict[str, Any]:
    """
    解析并合并模型配置，处理模型组。

    注意：
    - llm_groups 格式为对象：{'group_name': {...}, ...}，使用组名作为 key
    - llm_groups 中不再支持直接定义 platform、model 等参数，只能通过 normal_llm、cheap_llm、smart_llm 引用 llms 中定义的配置

    优先级顺序:
    - 当未显式指定组时（使用默认组或未设置）：
        1. 顶层环境变量 (platform, model, max_input_token_count)
        2. llm_group 中通过引用展开的配置
        3. 代码中的默认值

    返回:
        Dict[str, Any]: 解析后的模型配置字典

    异常:
        如果 llm_groups 中直接定义了 platform、model 等参数，或缺少必需的引用，会抛出 ValueError
    """

    group_config = {}
    model_group_name = get_llm_group()
    # The format is an object: {'group_name': {...}, ...}
    model_groups = GLOBAL_CONFIG_DATA.get("llm_groups", {})

    if model_group_name and isinstance(model_groups, dict):
        if model_group_name in model_groups:
            group_config = model_groups[model_group_name]

    # 展开 llm 引用（normal_llm, cheap_llm, smart_llm）
    # 只有当 group_config 不为空时才展开引用（说明使用了 llm_groups）
    if group_config:
        group_config = _expand_llm_references(group_config)

    # Start with group config
    resolved_config = group_config.copy()

    # 覆盖策略：
    # - 保留顶层配置键（platform, model, max_input_token_count）用于直接配置
    # - 必须通过 llms + llm_groups 配置模型
    # - 保留 llm_config 相关键的回退处理（用于 llm_groups 展开后的内部配置）
    override_keys = [
        "platform",
        "model",
        "max_input_token_count",
        "llm_config",
        "cheap_llm_config",
        "smart_llm_config",
    ]
    for key in override_keys:
        if key in GLOBAL_CONFIG_DATA:
            # 未显式指定组：顶层覆盖组
            resolved_config[key] = GLOBAL_CONFIG_DATA[key]

    # 不再将 llm_config 应用到环境变量，所有配置通过 llm_config 参数直接传递给 platform
    # _apply_llm_config_to_env(resolved_config)

    return resolved_config


def get_llm_config(platform_type: str = "normal") -> Dict[str, Any]:
    """
    获取指定平台类型的 llm_config 配置。

    参数:
        platform_type: 平台类型，可选值为 'normal'、'cheap' 或 'smart'

    返回:
        Dict[str, Any]: llm_config 配置字典
    """
    # 不应用配置到环境变量，避免不同 llm 类型的配置互相覆盖
    # 配置会通过 llm_config 参数直接传递给 platform，不依赖环境变量
    config = _get_resolved_model_config()

    if platform_type == "cheap":
        llm_config = dict(config.get("cheap_llm_config", {}))
        # 如果 cheap_llm_config 为空，回退到 normal_llm_config
        if not llm_config:
            llm_config = dict(config.get("llm_config", {}))
        return llm_config
    elif platform_type == "smart":
        llm_config = dict(config.get("smart_llm_config", {}))
        # 如果 smart_llm_config 为空，回退到 normal_llm_config（与 get_smart_platform_name 的回退逻辑一致）
        if not llm_config:
            llm_config = dict(config.get("llm_config", {}))
        return llm_config
    else:
        return dict(config.get("llm_config", {}))


def get_normal_platform_name() -> str:
    """
    获取正常操作的平台名称。

    返回：
        str: 平台名称，默认为'openai'
    """
    config = _get_resolved_model_config()
    return cast(str, config.get("platform", "openai"))


def get_normal_model_name() -> str:
    """
    获取正常操作的模型名称。

    返回：
        str: 模型名称，默认为'gpt-5'
    """
    config = _get_resolved_model_config()
    return cast(str, config.get("model", "gpt-5"))


def get_cheap_platform_name() -> str:
    """
    获取廉价操作的平台名称。

    返回：
        str: 平台名称，如果未配置则回退到正常操作平台
    """
    config = _get_resolved_model_config()
    cheap_platform = config.get("cheap_platform")
    if cheap_platform:
        return cast(str, cheap_platform)
    return get_normal_platform_name()


def get_cheap_model_name() -> str:
    """
    获取廉价操作的模型名称。

    返回：
        str: 模型名称，如果未配置则回退到正常操作模型
    """
    config = _get_resolved_model_config()
    cheap_model = config.get("cheap_model")
    if cheap_model:
        return cast(str, cheap_model)
    return get_normal_model_name()


def get_smart_platform_name() -> str:
    """
    获取智能操作的平台名称。

    返回：
        str: 平台名称，如果未配置则回退到正常操作平台
    """
    config = _get_resolved_model_config()
    smart_platform = config.get("smart_platform")
    if smart_platform:
        return cast(str, smart_platform)
    return get_normal_platform_name()


def get_smart_model_name() -> str:
    """
    获取智能操作的模型名称。

    返回：
        str: 模型名称，如果未配置则回退到正常操作模型
    """
    config = _get_resolved_model_config()
    smart_model = config.get("smart_model")
    if smart_model:
        return cast(str, smart_model)
    return get_normal_model_name()


def is_execute_tool_confirm() -> bool:
    """
    检查工具执行是否需要确认。

    返回：
        bool: 如果需要确认则返回True，默认为False
    """
    return cast(bool, GLOBAL_CONFIG_DATA.get("execute_tool_confirm", False))


def is_confirm_before_apply_patch() -> bool:
    """
    检查应用补丁前是否需要确认。

    返回：
        bool: 如果需要确认则返回True，默认为False
    """
    return False


def get_data_dir() -> str:
    """
    获取Jarvis数据存储目录路径。

    返回:
        str: 数据目录路径，默认为 ~/.jarvis
    """
    return os.path.expanduser("~/.jarvis")


def get_continuous_learning_dir() -> str:
    """
    获取持续学习数据存储目录路径。

    返回:
        str: 持续学习数据目录路径，为 ~/.jarvis/continuous_learning
    """
    cl_dir = os.path.join(os.path.expanduser("~/.jarvis"), "continuous_learning")
    # 确保目录存在
    os.makedirs(cl_dir, exist_ok=True)
    return cl_dir


def get_pretty_output() -> bool:
    """
    获取是否启用PrettyOutput。

    返回：
        bool: 如果启用PrettyOutput则返回True，默认为True
    """
    return True


def is_use_methodology() -> bool:
    """
    获取是否启用方法论。

    返回：
        bool: 如果启用方法论则返回True，默认为True
    """
    return True


def is_use_analysis() -> bool:
    """
    获取是否启用任务分析。

    返回：
        bool: 如果启用任务分析则返回True，默认为True
    """
    return True


def get_tool_load_dirs() -> List[str]:
    """
    获取工具加载目录。

    返回:
        List[str]: 工具加载目录列表
    """
    return [
        os.path.expanduser(os.path.expandvars(str(p)))
        for p in GLOBAL_CONFIG_DATA.get("tool_load_dirs", [])
        if p
    ]


def get_methodology_dirs() -> List[str]:
    """
    获取方法论加载目录。

    返回:
        List[str]: 方法论加载目录列表
    """
    return [
        os.path.expanduser(os.path.expandvars(str(p)))
        for p in GLOBAL_CONFIG_DATA.get("methodology_dirs", [])
        if p
    ]


def get_agent_definition_dirs() -> List[str]:
    """
    获取 agent 定义的加载目录。

    返回:
        List[str]: agent 定义加载目录列表
    """
    return [
        os.path.expanduser(os.path.expandvars(str(p)))
        for p in GLOBAL_CONFIG_DATA.get("agent_definition_dirs", [])
        if p
    ]


def get_multi_agent_dirs() -> List[str]:
    """
    获取 multi_agent 的加载目录。

    返回:
        List[str]: multi_agent 加载目录列表
    """
    return [
        os.path.expanduser(os.path.expandvars(str(p)))
        for p in GLOBAL_CONFIG_DATA.get("multi_agent_dirs", [])
        if p
    ]


def get_roles_dirs() -> List[str]:
    """
    获取 roles 的加载目录。

    返回:
        List[str]: roles 加载目录列表
    """
    return [
        os.path.expanduser(os.path.expandvars(str(p)))
        for p in GLOBAL_CONFIG_DATA.get("roles_dirs", [])
        if p
    ]


def get_after_tool_call_cb_dirs() -> List[str]:
    """
    获取工具调用后回调函数实现目录。

    返回:
        List[str]: 工具调用后回调函数实现目录列表
    """
    return [
        os.path.expanduser(os.path.expandvars(str(p)))
        for p in GLOBAL_CONFIG_DATA.get("after_tool_call_cb_dirs", [])
        if p
    ]


def get_central_methodology_repo() -> str:
    """
    获取中心方法论Git仓库地址。

    返回:
        str: 中心方法论Git仓库地址，如果未配置则返回空字符串
    """
    return cast(str, GLOBAL_CONFIG_DATA.get("central_methodology_repo", ""))


def get_central_tool_repo() -> str:
    """
    获取中心工具Git仓库地址。

    返回:
        str: 中心工具Git仓库地址，如果未配置则返回空字符串
    """
    return cast(str, GLOBAL_CONFIG_DATA.get("central_tool_repo", ""))


def get_rules_load_dirs() -> List[str]:
    """
    获取规则加载目录。

    返回:
        List[str]: 规则加载目录列表
    """
    return [
        os.path.expanduser(os.path.expandvars(str(p)))
        for p in GLOBAL_CONFIG_DATA.get("rules_load_dirs", [])
        if p
    ]


def get_central_rules_repo() -> str:
    """
    获取中心规则Git仓库地址。

    返回:
        str: 中心规则Git仓库地址，如果未配置则返回空字符串
    """
    return cast(str, GLOBAL_CONFIG_DATA.get("central_rules_repo", ""))


def is_print_prompt() -> bool:
    """
    获取是否打印提示。

    返回：
        bool: 如果打印提示则返回True，默认为True
    """
    return cast(bool, GLOBAL_CONFIG_DATA.get("print_prompt", False))


def is_print_error_traceback() -> bool:
    """
    获取是否在错误输出时打印回溯调用链。

    返回：
        bool: 如果打印回溯则返回True，默认为False（不打印）
    """
    return False


def is_force_save_memory() -> bool:
    """
    获取是否强制保存记忆。

    返回：
        bool: 如果强制保存记忆则返回True，默认为False
    """
    return False


def is_enable_static_analysis() -> bool:
    """
    获取是否启用静态代码分析。

    返回：
        bool: 如果启用静态代码分析则返回True，默认为True
    """
    return True


def is_enable_build_validation() -> bool:
    """
    获取是否启用构建验证。

    返回：
        bool: 如果启用构建验证则返回True，默认为True
    """
    return True


def is_enable_impact_analysis() -> bool:
    """
    获取是否启用编辑影响范围分析。

    返回：
        bool: 如果启用影响范围分析则返回True，默认为True
    """
    return True


def is_enable_auto_methodology_extraction() -> bool:
    """
    获取是否启用方法论自动提取。

    当启用时，任务完成后会自动从任务执行过程中提取方法论并保存。
    默认关闭，可通过配置文件设置 auto_methodology_extraction: true 启用。

    返回：
        bool: 如果启用方法论自动提取则返回True，默认为False
    """
    return bool(GLOBAL_CONFIG_DATA.get("auto_methodology_extraction", False))


def get_build_validation_timeout() -> int:
    """
    获取构建验证的超时时间（秒）。

    返回：
        int: 超时时间，默认为30秒
    """
    return int(GLOBAL_CONFIG_DATA.get("build_validation_timeout", 30))


def get_mcp_config() -> List[Dict[str, Any]]:
    """
    获取MCP配置列表。

    返回:
        List[Dict[str, Any]]: MCP配置项列表，如果未配置则返回空列表
    """
    return cast(List[Dict[str, Any]], GLOBAL_CONFIG_DATA.get("mcp", []))


# ==============================================================================
# Web Search Configuration
# ==============================================================================


def get_web_search_platform_name() -> Optional[str]:
    """
    获取Web搜索使用的平台名称。

    使用 normal_llm 的平台配置。

    返回:
        Optional[str]: 平台名称，如果未配置则返回None
    """
    return get_normal_platform_name()


def get_web_search_model_name() -> Optional[str]:
    """
    获取Web搜索使用的模型名称。

    使用 normal_llm 的模型配置。

    返回:
        Optional[str]: 模型名称，如果未配置则返回None
    """
    return get_normal_model_name()


# ==============================================================================
# Tool Configuration
# ==============================================================================


def _get_resolved_tool_config(
    tool_group_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    解析并合并工具配置，处理工具组。

    优先级顺序:
    1. tool_group 中定义的组配置
    2. 默认配置（所有工具都启用）

    返回:
        Dict[str, Any]: 解析后的工具配置字典，包含 'use' 和 'dont_use' 列表
    """
    group_config = {}
    tool_group_name = tool_group_override or GLOBAL_CONFIG_DATA.get("tool_group")
    tool_groups = GLOBAL_CONFIG_DATA.get("tool_groups", [])

    if tool_group_name and isinstance(tool_groups, list):
        for group_item in tool_groups:
            if isinstance(group_item, dict) and tool_group_name in group_item:
                group_config = group_item[tool_group_name]
                break

    # 如果没有找到配置组，返回默认配置（空列表表示使用所有工具）
    return group_config.copy() if group_config else {"use": [], "dont_use": []}


def get_tool_use_list() -> List[str]:
    """
    获取要使用的工具列表。

    返回:
        List[str]: 要使用的工具名称列表，空列表表示使用所有工具
    """
    config = _get_resolved_tool_config()
    return cast(List[str], config.get("use", []))


def get_tool_dont_use_list() -> List[str]:
    """
    获取不使用的工具列表。

    返回:
        List[str]: 不使用的工具名称列表
    """
    config = _get_resolved_tool_config()
    return cast(List[str], config.get("dont_use", []))


def get_tool_filter_threshold() -> int:
    """
    获取AI工具筛选的阈值。

    返回:
        int: 当工具数量超过此阈值时，触发AI筛选。默认为30
    """
    return 30


def get_script_execution_timeout() -> int:
    """
    获取脚本执行的超时时间（秒）。

    返回:
        int: 超时时间（300秒/5分钟）
    """
    return 300


def is_enable_git_repo_jca_switch() -> bool:
    """
    是否启用：在初始化环境前检测Git仓库并提示可切换到代码开发模式（jca）
    默认开启
    """
    return GLOBAL_CONFIG_DATA.get("enable_git_jca_switch", True) is True


def is_enable_builtin_config_selector() -> bool:
    """
    是否启用：在进入默认通用代理前，列出可用配置（agent/multi_agent/roles）供选择
    默认开启
    """
    return GLOBAL_CONFIG_DATA.get("enable_startup_config_selector", True) is True


def is_save_session_history() -> bool:
    """
    是否保存会话记录。

    返回:
        bool: 如果要保存会话记录则返回True, 默认为False
    """
    return GLOBAL_CONFIG_DATA.get("save_session_history", False) is True


def is_immediate_abort() -> bool:
    """
    是否启用立即中断：当在对话过程中检测到用户中断信号时，立即停止输出并返回。
    默认关闭
    """
    return True


def is_non_interactive() -> bool:
    """
    获取是否启用非交互模式。

    返回：
        bool: 如果启用非交互模式则返回True，默认为False
    """
    try:
        # 优先基于当前激活的 Agent 状态判断，避免跨 Agent 互相污染
        from jarvis.jarvis_utils import globals as _g

        current_agent_name = _g.get_current_agent_name()
        if current_agent_name:
            agent = _g.get_agent(current_agent_name)
            if agent is not None and hasattr(agent, "non_interactive"):
                try:
                    return bool(getattr(agent, "non_interactive"))
                except Exception:
                    return False
    except Exception:
        # 防御式兜底，保持返回 False 不影响主流程
        return False
    # 无当前 Agent 时默认返回 False，避免依赖全局配置或环境变量
    return False


def is_skip_predefined_tasks() -> bool:
    """
    是否跳过预定义任务加载。

    返回：
        bool: 如果跳过预定义任务加载则返回True，默认为False
    """
    return GLOBAL_CONFIG_DATA.get("skip_predefined_tasks", False) is True


def get_addon_prompt_threshold() -> int:
    """
    获取附加提示的触发阈值（字符数）。

    当消息长度超过此阈值时，会自动添加默认的附加提示。

    返回:
        int: 触发阈值，默认为1024
    """
    return 1024


def is_enable_intent_recognition() -> bool:
    """
    获取是否启用意图识别功能。

    返回:
        bool: 是否启用意图识别，默认为True（可通过 GLOBAL_CONFIG_DATA['enable_intent_recognition'] 配置）
    """
    return True


def is_enable_memory_organizer() -> bool:
    """
    获取是否启用自动记忆整理功能。

    返回:
        bool: 是否启用自动记忆整理，默认为False（可通过 GLOBAL_CONFIG_DATA['enable_memory_organizer'] 配置）
    """
    return False


def is_enable_autonomous() -> bool:
    """
    获取是否启用智能增强功能（情绪识别、歧义检测、对话管理、主动交互）。

    返回:
        bool: 是否启用智能增强功能，默认为False
    """
    return GLOBAL_CONFIG_DATA.get("enable_autonomous", False) is True


def get_conversation_turn_threshold() -> int:
    """
    获取对话轮次阈值，用于触发总结。

    返回:
        int: 对话轮次阈值（200轮）
    """
    return 200


def get_sliding_window_size() -> int:
    """
    获取滑动窗口大小，用于滑动窗口压缩策略。

    返回:
        int: 滑动窗口大小（保留最近的用户/工具消息4条和助手消息5条，共9条，奇数以避免连续的同role消息）
    """
    return 5


def get_importance_score_threshold() -> float:
    """
    获取重要性评分阈值，用于重要性评分压缩策略。

    返回:
        float: 重要性评分阈值（低于此阈值的消息将被压缩，默认3.0）
    """
    return 3.0


def get_incremental_summary_chunk_size() -> int:
    """
    获取增量摘要的chunk大小，用于增量摘要压缩策略。

    返回:
        int: chunk大小（每个chunk包含的对话轮数，默认20轮）
    """
    return 20


def get_diff_visualization_mode() -> str:
    """
    获取 diff 可视化模式

    返回:
        str: diff 可视化模式，可选值: "unified", "syntax", "compact", "side_by_side", "default"
        默认为 "unified"
    """
    return "side_by_side"


def get_diff_show_line_numbers() -> bool:
    """
    获取是否在 diff 中显示行号

    返回:
        bool: 是否显示行号，默认为 True
    """
    return True


def get_diff_large_file_threshold() -> int:
    """
    获取大文件阈值（超过此行数只显示统计）

    返回:
        int: 大文件阈值，默认为 300
    """
    return 300
