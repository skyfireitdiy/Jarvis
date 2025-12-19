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


def set_global_env_data(env_data: Dict[str, Any]) -> None:
    """设置全局环境变量数据"""
    global GLOBAL_CONFIG_DATA
    GLOBAL_CONFIG_DATA = CaseInsensitiveDict(env_data)


def set_config(key: str, value: Any) -> None:
    """设置配置"""
    GLOBAL_CONFIG_DATA[key] = value


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


# 输出窗口预留大小
INPUT_WINDOW_REVERSE_SIZE = 2048


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


def get_max_input_token_count(model_group_override: Optional[str] = None) -> int:
    """
    获取模型允许的最大输入token数量。

    返回:
        int: 模型能处理的最大输入token数量。
    """
    config = _get_resolved_model_config(model_group_override)
    return int(config.get("max_input_token_count", "128000"))


def get_cheap_max_input_token_count(model_group_override: Optional[str] = None) -> int:
    """
    获取廉价模型允许的最大输入token数量。

    返回:
        int: 模型能处理的最大输入token数量，如果未配置则回退到正常配置
    """
    config = _get_resolved_model_config(model_group_override)
    cheap_max_token = config.get("cheap_max_input_token_count")
    if cheap_max_token:
        return int(cheap_max_token)
    return get_max_input_token_count(model_group_override)


def get_smart_max_input_token_count(model_group_override: Optional[str] = None) -> int:
    """
    获取智能模型允许的最大输入token数量。

    返回:
        int: 模型能处理的最大输入token数量，如果未配置则回退到正常配置
    """
    config = _get_resolved_model_config(model_group_override)
    smart_max_token = config.get("smart_max_input_token_count")
    if smart_max_token:
        return int(smart_max_token)
    return get_max_input_token_count(model_group_override)


def get_shell_name() -> str:
    """
    获取系统shell名称。

    返回：
        str: Shell名称（例如bash, zsh, fish），默认为bash

    获取顺序：
    1. 先从GLOBAL_CONFIG_DATA中获取shell配置
    2. 再从GLOBAL_CONFIG_DATA中获取SHELL配置
    3. 最后从环境变量SHELL获取
    4. 如果都未配置，则默认返回bash
    """
    shell_path = GLOBAL_CONFIG_DATA.get("SHELL", os.getenv("SHELL", "/bin/bash"))
    return cast(str, os.path.basename(shell_path).lower())


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
        "max_input_token_count", 32000
    )
    # 合并 llm_config
    if "llm_config" in llm_ref:
        expanded_config["llm_config"] = llm_ref["llm_config"].copy()
    # 移除引用键
    expanded_config.pop("normal_llm", None)

    # 处理 cheap_llm 引用
    if "cheap_llm" in expanded_config:
        llm_ref = _resolve_llm_reference(expanded_config["cheap_llm"])
        if not llm_ref:
            raise ValueError(
                f"❌ 错误：cheap_llm 引用的 '{expanded_config['cheap_llm']}' 在 llms 中不存在。"
            )
        # 直接使用引用的值
        expanded_config["cheap_platform"] = llm_ref.get("platform", "openai")
        expanded_config["cheap_model"] = llm_ref.get("model", "gpt-5")
        expanded_config["cheap_max_input_token_count"] = llm_ref.get(
            "max_input_token_count", 32000
        )
        # 合并 llm_config
        if "llm_config" in llm_ref:
            expanded_config["cheap_llm_config"] = llm_ref["llm_config"].copy()
        expanded_config.pop("cheap_llm", None)

    # 处理 smart_llm 引用
    if "smart_llm" in expanded_config:
        llm_ref = _resolve_llm_reference(expanded_config["smart_llm"])
        if not llm_ref:
            raise ValueError(
                f"❌ 错误：smart_llm 引用的 '{expanded_config['smart_llm']}' 在 llms 中不存在。"
            )
        # 直接使用引用的值
        expanded_config["smart_platform"] = llm_ref.get("platform", "openai")
        expanded_config["smart_model"] = llm_ref.get("model", "gpt-5")
        expanded_config["smart_max_input_token_count"] = llm_ref.get(
            "max_input_token_count", 32000
        )
        # 合并 llm_config
        if "llm_config" in llm_ref:
            expanded_config["smart_llm_config"] = llm_ref["llm_config"].copy()
        expanded_config.pop("smart_llm", None)

    return expanded_config


def _get_resolved_model_config(
    model_group_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    解析并合并模型配置，处理模型组。

    注意：
    - llm_groups 格式为对象：{'group_name': {...}, ...}，使用组名作为 key
    - llm_groups 中不再支持直接定义 platform、model 等参数，只能通过 normal_llm、cheap_llm、smart_llm 引用 llms 中定义的配置

    优先级顺序:
    - 当通过 model_group_override（例如命令行 -g/--llm-group）指定组时：
        1. llm_group 中通过引用展开的配置
        2. 仅当组未提供对应键时，回退到顶层环境变量 (platform, model, max_input_token_count)
        3. 代码中的默认值
    - 当未显式指定组时（使用默认组或未设置）：
        1. 顶层环境变量 (platform, model, max_input_token_count)
        2. llm_group 中通过引用展开的配置
        3. 代码中的默认值

    参数:
        model_group_override: 模型组覆盖

    返回:
        Dict[str, Any]: 解析后的模型配置字典

    异常:
        如果 llm_groups 中直接定义了 platform、model 等参数，或缺少必需的引用，会抛出 ValueError
    """
    from jarvis.jarvis_utils.output import PrettyOutput

    group_config = {}
    model_group_name = model_group_override or GLOBAL_CONFIG_DATA.get("llm_group")
    # The format is an object: {'group_name': {...}, ...}
    model_groups = GLOBAL_CONFIG_DATA.get("llm_groups", {})

    if model_group_name and isinstance(model_groups, dict):
        if model_group_name in model_groups:
            group_config = model_groups[model_group_name]
        elif model_group_override:
            # 当显式指定了模型组但未找到时，报错并退出
            PrettyOutput.auto_print(
                f"❌ 错误：指定的模型组 '{model_group_name}' 不存在于配置中。"
            )
            PrettyOutput.auto_print(
                "ℹ️ 可用的模型组: " + ", ".join(model_groups.keys())
                if model_groups
                else "无可用模型组"
            )
            import sys

            sys.exit(1)

    # 展开 llm 引用（normal_llm, cheap_llm, smart_llm）
    # 只有当 group_config 不为空时才展开引用（说明使用了 llm_groups）
    if group_config:
        group_config = _expand_llm_references(group_config)

    # Start with group config
    resolved_config = group_config.copy()

    # 覆盖策略：
    # - 若通过 CLI 传入了 model_group_override，则优先使用组内配置；
    #   仅当组未提供对应键时，才回落到顶层 GLOBAL_CONFIG_DATA。
    # - 若未传入 override（即使用默认组），保持原有行为：由顶层键覆盖组配置。
    override_keys = [
        "platform",
        "model",
        "max_input_token_count",
        "cheap_platform",
        "cheap_model",
        "cheap_max_input_token_count",
        "smart_platform",
        "smart_model",
        "smart_max_input_token_count",
        "llm_config",
        "cheap_llm_config",
        "smart_llm_config",
    ]
    for key in override_keys:
        if key in GLOBAL_CONFIG_DATA:
            if model_group_override is None:
                # 未显式指定组：顶层覆盖组
                resolved_config[key] = GLOBAL_CONFIG_DATA[key]
            else:
                # 显式指定组：仅在组未定义该键时回退到顶层
                if key not in resolved_config:
                    resolved_config[key] = GLOBAL_CONFIG_DATA[key]

    # 不再将 llm_config 应用到环境变量，所有配置通过 llm_config 参数直接传递给 platform
    # _apply_llm_config_to_env(resolved_config)

    return resolved_config


def get_llm_config(
    platform_type: str = "normal", model_group_override: Optional[str] = None
) -> Dict[str, Any]:
    """
    获取指定平台类型的 llm_config 配置。

    参数:
        platform_type: 平台类型，可选值为 'normal'、'cheap' 或 'smart'
        model_group_override: 模型组覆盖

    返回:
        Dict[str, Any]: llm_config 配置字典
    """
    # 不应用配置到环境变量，避免不同 llm 类型的配置互相覆盖
    # 配置会通过 llm_config 参数直接传递给 platform，不依赖环境变量
    config = _get_resolved_model_config(model_group_override)

    if platform_type == "cheap":
        return dict(config.get("cheap_llm_config", {}))
    elif platform_type == "smart":
        return dict(config.get("smart_llm_config", {}))
    else:
        return dict(config.get("llm_config", {}))


def get_normal_platform_name(model_group_override: Optional[str] = None) -> str:
    """
    获取正常操作的平台名称。

    返回：
        str: 平台名称，默认为'openai'
    """
    config = _get_resolved_model_config(model_group_override)
    return cast(str, config.get("platform", "openai"))


def get_normal_model_name(model_group_override: Optional[str] = None) -> str:
    """
    获取正常操作的模型名称。

    返回：
        str: 模型名称，默认为'gpt-5'
    """
    config = _get_resolved_model_config(model_group_override)
    return cast(str, config.get("model", "gpt-5"))


def get_cheap_platform_name(model_group_override: Optional[str] = None) -> str:
    """
    获取廉价操作的平台名称。

    返回：
        str: 平台名称，如果未配置则回退到正常操作平台
    """
    config = _get_resolved_model_config(model_group_override)
    cheap_platform = config.get("cheap_platform")
    if cheap_platform:
        return cast(str, cheap_platform)
    return get_normal_platform_name(model_group_override)


def get_cheap_model_name(model_group_override: Optional[str] = None) -> str:
    """
    获取廉价操作的模型名称。

    返回：
        str: 模型名称，如果未配置则回退到正常操作模型
    """
    config = _get_resolved_model_config(model_group_override)
    cheap_model = config.get("cheap_model")
    if cheap_model:
        return cast(str, cheap_model)
    return get_normal_model_name(model_group_override)


def get_smart_platform_name(model_group_override: Optional[str] = None) -> str:
    """
    获取智能操作的平台名称。

    返回：
        str: 平台名称，如果未配置则回退到正常操作平台
    """
    config = _get_resolved_model_config(model_group_override)
    smart_platform = config.get("smart_platform")
    if smart_platform:
        return cast(str, smart_platform)
    return get_normal_platform_name(model_group_override)


def get_smart_model_name(model_group_override: Optional[str] = None) -> str:
    """
    获取智能操作的模型名称。

    返回：
        str: 模型名称，如果未配置则回退到正常操作模型
    """
    config = _get_resolved_model_config(model_group_override)
    smart_model = config.get("smart_model")
    if smart_model:
        return cast(str, smart_model)
    return get_normal_model_name(model_group_override)


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
    return cast(bool, GLOBAL_CONFIG_DATA.get("confirm_before_apply_patch", False))


def get_data_dir() -> str:
    """
    获取Jarvis数据存储目录路径。

    返回:
        str: 数据目录路径，优先从data_path环境变量获取，
             如果未设置或为空，则使用~/.jarvis作为默认值
    """
    return os.path.expanduser(
        cast(str, GLOBAL_CONFIG_DATA.get("data_path", "~/.jarvis")).strip()
    )


def get_max_big_content_size(model_group_override: Optional[str] = None) -> int:
    """
    获取最大大内容大小。

    返回：
        int: 最大大内容大小，为最大输入token数量的5倍
    """
    max_input_tokens = get_max_input_token_count(model_group_override)
    return max_input_tokens * 5


def get_pretty_output() -> bool:
    """
    获取是否启用PrettyOutput。

    返回：
        bool: 如果启用PrettyOutput则返回True，默认为True
    """
    import platform

    # Windows系统强制设置为False
    if platform.system() == "Windows":
        return False

    return cast(bool, GLOBAL_CONFIG_DATA.get("pretty_output", True))


def is_use_methodology() -> bool:
    """
    获取是否启用方法论。

    返回：
        bool: 如果启用方法论则返回True，默认为True
    """
    return cast(bool, GLOBAL_CONFIG_DATA.get("use_methodology", True))


def is_use_analysis() -> bool:
    """
    获取是否启用任务分析。

    返回：
        bool: 如果启用任务分析则返回True，默认为True
    """
    return cast(bool, GLOBAL_CONFIG_DATA.get("use_analysis", True))


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
    return GLOBAL_CONFIG_DATA.get("print_error_traceback", False) is True


def is_force_save_memory() -> bool:
    """
    获取是否强制保存记忆。

    返回：
        bool: 如果强制保存记忆则返回True，默认为False
    """
    return GLOBAL_CONFIG_DATA.get("force_save_memory", False) is True


def is_enable_static_analysis() -> bool:
    """
    获取是否启用静态代码分析。

    返回：
        bool: 如果启用静态代码分析则返回True，默认为True
    """
    return GLOBAL_CONFIG_DATA.get("enable_static_analysis", True) is True


def is_enable_build_validation() -> bool:
    """
    获取是否启用构建验证。

    返回：
        bool: 如果启用构建验证则返回True，默认为True
    """
    return GLOBAL_CONFIG_DATA.get("enable_build_validation", True) is True


def is_enable_impact_analysis() -> bool:
    """
    获取是否启用编辑影响范围分析。

    返回：
        bool: 如果启用影响范围分析则返回True，默认为True
    """
    return GLOBAL_CONFIG_DATA.get("enable_impact_analysis", True) is True


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
# RAG Framework Configuration
# ==============================================================================


DEFAULT_RAG_GROUPS = {
    "text": {
        "embedding": "default-text-embedding",
        "reranker": "default-text-reranker",
        "use_bm25": True,
        "use_rerank": True,
    },
    "code": {
        "embedding": "default-code-embedding",
        "use_bm25": False,
        "use_rerank": False,
    },
}

# 默认的 embeddings 配置（如果用户未定义）
DEFAULT_EMBEDDINGS = {
    "default-text-embedding": {
        "embedding_model": "BAAI/bge-m3",
        "embedding_type": "LocalEmbeddingModel",
        "embedding_max_length": 512,
    },
    "default-code-embedding": {
        "embedding_model": "Qodo/Qodo-Embed-1-1.5B",
        "embedding_type": "LocalEmbeddingModel",
        "embedding_max_length": 512,
    },
}

# 默认的 rerankers 配置（如果用户未定义）
DEFAULT_RERANKERS = {
    "default-text-reranker": {
        "rerank_model": "BAAI/bge-reranker-v2-m3",
        "reranker_type": "LocalReranker",
        "reranker_max_length": 512,
    },
}


def _resolve_embedding_reference(embedding_name: str) -> Dict[str, Any]:
    """
    从 embeddings 配置中解析引用的嵌入模型配置。

    参数:
        embedding_name: embeddings 中定义的嵌入模型配置名称

    返回:
        Dict[str, Any]: 解析后的嵌入模型配置字典，包含 embedding_model, embedding_type, embedding_max_length, embedding_config
    """
    from jarvis.jarvis_utils.output import PrettyOutput

    embeddings = GLOBAL_CONFIG_DATA.get("embeddings", {})
    if not isinstance(embeddings, dict):
        embeddings = {}

    # 如果用户配置中没有，尝试使用默认配置
    if embedding_name not in embeddings:
        embeddings = {**DEFAULT_EMBEDDINGS, **embeddings}

    embedding_config = embeddings.get(embedding_name)
    if not isinstance(embedding_config, dict):
        PrettyOutput.auto_print(
            f"⚠️ 警告：embeddings 中未找到名为 '{embedding_name}' 的配置"
        )
        return {}

    return embedding_config.copy()


def _resolve_reranker_reference(reranker_name: str) -> Dict[str, Any]:
    """
    从 rerankers 配置中解析引用的重排模型配置。

    参数:
        reranker_name: rerankers 中定义的重排模型配置名称

    返回:
        Dict[str, Any]: 解析后的重排模型配置字典，包含 rerank_model, reranker_type, reranker_max_length, reranker_config
    """
    from jarvis.jarvis_utils.output import PrettyOutput

    rerankers = GLOBAL_CONFIG_DATA.get("rerankers", {})
    if not isinstance(rerankers, dict):
        rerankers = {}

    # 如果用户配置中没有，尝试使用默认配置
    if reranker_name not in rerankers:
        rerankers = {**DEFAULT_RERANKERS, **rerankers}

    reranker_config = rerankers.get(reranker_name)
    if not isinstance(reranker_config, dict):
        PrettyOutput.auto_print(
            f"⚠️ 警告：rerankers 中未找到名为 '{reranker_name}' 的配置"
        )
        return {}

    return reranker_config.copy()


def _expand_rag_references(group_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    展开 rag_groups 中的 embedding 和 reranker 引用到对应的配置字段。

    注意：rag_groups 中不再支持直接定义 embedding_model、embedding_type 等参数，只能通过引用 embeddings 和 rerankers 中的配置。

    参数:
        group_config: RAG组配置字典

    返回:
        Dict[str, Any]: 展开后的配置字典

    异常:
        如果组配置中直接定义了 embedding_model、embedding_type 等参数，会抛出 ValueError
    """
    expanded_config = group_config.copy()

    # 检查是否直接定义了不允许的参数
    forbidden_keys = [
        "embedding_model",
        "embedding_type",
        "embedding_max_length",
        "embedding_config",
        "rerank_model",
        "reranker_type",
        "reranker_max_length",
        "reranker_config",
    ]
    found_forbidden = [key for key in forbidden_keys if key in expanded_config]
    if found_forbidden:
        raise ValueError(
            f"❌ 错误：rag_groups 中不再支持直接定义以下参数: {', '.join(found_forbidden)}。"
            f"请使用 embedding 和 reranker 引用 embeddings 和 rerankers 中定义的配置。"
        )

    # 处理 embedding 引用（必需）
    if "embedding" not in expanded_config:
        raise ValueError(
            "❌ 错误：rag_groups 中必须定义 embedding 引用。"
            "请使用 embedding 引用 embeddings 中定义的配置。"
        )

    embedding_ref = _resolve_embedding_reference(expanded_config["embedding"])
    if not embedding_ref:
        raise ValueError(
            f"❌ 错误：embedding 引用的 '{expanded_config['embedding']}' 在 embeddings 中不存在。"
        )
    # 直接使用引用的值
    expanded_config["embedding_model"] = embedding_ref.get(
        "embedding_model", "BAAI/bge-m3"
    )
    expanded_config["embedding_type"] = embedding_ref.get(
        "embedding_type", "LocalEmbeddingModel"
    )
    expanded_config["embedding_max_length"] = embedding_ref.get(
        "embedding_max_length", 512
    )
    # 合并 embedding_config
    if "embedding_config" in embedding_ref:
        expanded_config["embedding_config"] = embedding_ref["embedding_config"].copy()
    # 移除引用键
    expanded_config.pop("embedding", None)

    # 处理 reranker 引用（可选）
    if "reranker" in expanded_config:
        reranker_ref = _resolve_reranker_reference(expanded_config["reranker"])
        if not reranker_ref:
            raise ValueError(
                f"❌ 错误：reranker 引用的 '{expanded_config['reranker']}' 在 rerankers 中不存在。"
            )
        # 直接使用引用的值
        expanded_config["rerank_model"] = reranker_ref.get(
            "rerank_model", "BAAI/bge-reranker-v2-m3"
        )
        expanded_config["reranker_type"] = reranker_ref.get(
            "reranker_type", "LocalReranker"
        )
        expanded_config["reranker_max_length"] = reranker_ref.get(
            "reranker_max_length", 512
        )
        # 合并 reranker_config
        if "reranker_config" in reranker_ref:
            expanded_config["reranker_config"] = reranker_ref["reranker_config"].copy()
        # 移除引用键
        expanded_config.pop("reranker", None)

    return expanded_config


def _get_resolved_rag_config(
    rag_group_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    解析并合并RAG配置，处理RAG组。

    注意：
    - rag_groups 格式为对象：{'group_name': {...}, ...}，使用组名作为 key
    - rag_groups 中不再支持直接定义 embedding_model、embedding_type 等参数，只能通过 embedding 和 reranker 引用 embeddings 和 rerankers 中定义的配置

    优先级顺序:
    1. rag 中的顶级设置 (embedding_model, etc.)
    2. rag_group 中通过引用展开的组配置
    3. 代码中的默认值

    返回:
        Dict[str, Any]: 解析后的RAG配置字典

    异常:
        如果 rag_groups 中直接定义了 embedding_model、embedding_type 等参数，或缺少必需的引用，会抛出 ValueError
    """
    group_config = {}
    rag_group_name = rag_group_override or GLOBAL_CONFIG_DATA.get("rag_group")
    # The format is an object: {'group_name': {...}, ...}
    rag_groups = GLOBAL_CONFIG_DATA.get("rag_groups", DEFAULT_RAG_GROUPS)

    # 兼容旧格式：如果是列表，转换为对象格式
    if isinstance(rag_groups, list):
        converted_groups = {}
        for group_item in rag_groups:
            if isinstance(group_item, dict):
                for group_name, group_config_item in group_item.items():
                    converted_groups[group_name] = group_config_item
        rag_groups = converted_groups
        # 更新全局配置（仅用于兼容，不持久化）
        GLOBAL_CONFIG_DATA["rag_groups"] = converted_groups

    if rag_group_name and isinstance(rag_groups, dict):
        if rag_group_name in rag_groups:
            group_config = rag_groups[rag_group_name]

    # 展开 embedding 和 reranker 引用
    # 只有当 group_config 不为空时才展开引用（说明使用了 rag_groups）
    if group_config:
        group_config = _expand_rag_references(group_config)

    # Start with group config
    resolved_config = group_config.copy()

    # Override with specific settings from the top-level rag dict
    top_level_rag_config = GLOBAL_CONFIG_DATA.get("rag", {})
    if isinstance(top_level_rag_config, dict):
        for key in [
            "embedding_model",
            "embedding_type",
            "embedding_max_length",  # 嵌入模型最大输入长度
            "embedding_config",  # 额外的嵌入模型配置参数
            "rerank_model",
            "reranker_type",
            "reranker_max_length",  # 重排模型最大输入长度
            "reranker_config",  # 额外的重排模型配置参数
            "use_bm25",
            "use_rerank",
        ]:
            if key in top_level_rag_config:
                resolved_config[key] = top_level_rag_config[key]

    return resolved_config


def get_rag_embedding_model() -> str:
    """
    获取RAG嵌入模型的名称。

    返回:
        str: 嵌入模型的名称
    """
    config = _get_resolved_rag_config()
    return cast(str, config.get("embedding_model", "BAAI/bge-m3"))


def get_rag_rerank_model() -> str:
    """
    获取RAG rerank模型的名称。

    返回:
        str: rerank模型的名称
    """
    config = _get_resolved_rag_config()
    return cast(str, config.get("rerank_model", "BAAI/bge-reranker-v2-m3"))


def get_rag_embedding_cache_path() -> str:
    """
    获取RAG嵌入缓存的路径。

    返回:
        str: 缓存路径
    """
    return ".jarvis/rag/embeddings"


def get_rag_vector_db_path() -> str:
    """
    获取RAG向量数据库的路径。

    返回:
        str: 数据库路径
    """
    return ".jarvis/rag/vectordb"


def get_rag_use_bm25() -> bool:
    """
    获取RAG是否使用BM25。

    返回:
        bool: 如果使用BM25则返回True，默认为True
    """
    config = _get_resolved_rag_config()
    return config.get("use_bm25", True) is True


def get_rag_use_rerank() -> bool:
    """
    获取RAG是否使用rerank。

    返回:
        bool: 如果使用rerank则返回True，默认为True
    """
    config = _get_resolved_rag_config()
    return config.get("use_rerank", True) is True


def get_rag_embedding_type() -> str:
    """
    获取RAG嵌入模型的实现类型。

    返回:
        str: 嵌入模型类型（如 'LocalEmbeddingModel', 'OpenAIEmbeddingModel' 等），默认为 'LocalEmbeddingModel'
    """
    config = _get_resolved_rag_config()
    return cast(str, config.get("embedding_type", "LocalEmbeddingModel"))


def get_rag_reranker_type() -> str:
    """
    获取RAG重排模型的实现类型。

    返回:
        str: 重排模型类型（如 'LocalReranker', 'CohereReranker' 等），默认为 'LocalReranker'
    """
    config = _get_resolved_rag_config()
    return cast(str, config.get("reranker_type", "LocalReranker"))


def get_rag_embedding_config() -> Dict[str, Any]:
    """
    获取RAG嵌入模型的额外配置参数。

    返回:
        Dict[str, Any]: 嵌入模型的配置参数字典，如果未配置则返回空字典
    """
    config = _get_resolved_rag_config()
    return dict(config.get("embedding_config", {}))


def get_rag_reranker_config() -> Dict[str, Any]:
    """
    获取RAG重排模型的额外配置参数。

    返回:
        Dict[str, Any]: 重排模型的配置参数字典，如果未配置则返回空字典
    """
    config = _get_resolved_rag_config()
    return dict(config.get("reranker_config", {}))


def get_rag_embedding_max_length() -> int:
    """
    获取RAG嵌入模型的最大输入长度（token数）。

    返回:
        int: 嵌入模型的最大输入token数，默认为512
    """
    config = _get_resolved_rag_config()
    return int(config.get("embedding_max_length", 512))


def get_rag_reranker_max_length() -> int:
    """
    获取RAG重排模型的最大输入长度（token数）。

    返回:
        int: 重排模型的最大输入token数，默认为512
    """
    config = _get_resolved_rag_config()
    return int(config.get("reranker_max_length", 512))


# ==============================================================================
# Web Search Configuration
# ==============================================================================


def get_web_search_platform_name() -> Optional[str]:
    """
    获取Web搜索使用的平台名称。

    返回:
        Optional[str]: 平台名称，如果未配置则返回None
    """
    return (
        str(GLOBAL_CONFIG_DATA.get("web_search_platform"))
        if GLOBAL_CONFIG_DATA.get("web_search_platform") is not None
        else None
    )


def get_web_search_model_name() -> Optional[str]:
    """
    获取Web搜索使用的模型名称。

    返回:
        Optional[str]: 模型名称，如果未配置则返回None
    """
    return (
        str(GLOBAL_CONFIG_DATA.get("web_search_model"))
        if GLOBAL_CONFIG_DATA.get("web_search_model") is not None
        else None
    )


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
    return int(GLOBAL_CONFIG_DATA.get("tool_filter_threshold", 30))


def get_script_execution_timeout() -> int:
    """
    获取脚本执行的超时时间（秒）。

    返回:
        int: 超时时间，默认为300秒（5分钟）
    """
    return int(GLOBAL_CONFIG_DATA.get("script_execution_timeout", 300))


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
    return GLOBAL_CONFIG_DATA.get("immediate_abort", False) is True


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
    try:
        return int(GLOBAL_CONFIG_DATA.get("addon_prompt_threshold", 1024))
    except Exception:
        return 1024


def is_enable_intent_recognition() -> bool:
    """
    获取是否启用意图识别功能。

    返回:
        bool: 是否启用意图识别，默认为True（可通过 GLOBAL_CONFIG_DATA['enable_intent_recognition'] 配置）
    """
    return GLOBAL_CONFIG_DATA.get("enable_intent_recognition", True) is True


def is_enable_memory_organizer() -> bool:
    """
    获取是否启用自动记忆整理功能。

    返回:
        bool: 是否启用自动记忆整理，默认为False（可通过 GLOBAL_CONFIG_DATA['enable_memory_organizer'] 配置）
    """
    return GLOBAL_CONFIG_DATA.get("enable_memory_organizer", False) is True


def get_conversation_turn_threshold() -> int:
    """
    获取对话轮次阈值，用于触发总结。

    返回:
        int: 对话轮次阈值，默认为50
    """
    return int(GLOBAL_CONFIG_DATA.get("conversation_turn_threshold", 50))


def get_diff_visualization_mode() -> str:
    """
    获取 diff 可视化模式

    返回:
        str: diff 可视化模式，可选值: "unified", "syntax", "compact", "side_by_side", "default"
        默认为 "unified"
    """
    return cast(str, GLOBAL_CONFIG_DATA.get("diff_visualization_mode", "side_by_side"))


def get_diff_show_line_numbers() -> bool:
    """
    获取是否在 diff 中显示行号

    返回:
        bool: 是否显示行号，默认为 True
    """
    return cast(bool, GLOBAL_CONFIG_DATA.get("diff_show_line_numbers", True))


def get_diff_large_file_threshold() -> int:
    """
    获取大文件阈值（超过此行数只显示统计）

    返回:
        int: 大文件阈值，默认为 300
    """
    return int(GLOBAL_CONFIG_DATA.get("diff_large_file_threshold", 300))
