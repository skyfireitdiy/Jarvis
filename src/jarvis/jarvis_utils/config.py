# -*- coding: utf-8 -*-
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional, cast

import yaml  # type: ignore[import-untyped]

from jarvis.jarvis_utils.builtin_replace_map import BUILTIN_REPLACE_MAP
from jarvis.jarvis_utils.collections import CaseInsensitiveDict

# 全局环境变量存储

GLOBAL_CONFIG_DATA: CaseInsensitiveDict = CaseInsensitiveDict()


def set_global_env_data(env_data: Dict[str, Any]) -> None:
    """设置全局环境变量数据

    如果配置中有以 JARVIS_ 开头的键，会自动创建去掉前缀的小写键。
    例如：JARVIS_PLATFORM 会自动创建 platform 键（如果不存在）。
    """
    global GLOBAL_CONFIG_DATA
    # 创建配置字典的副本，避免修改原始数据
    processed_data = dict(env_data)

    # 遍历所有键，为 JARVIS_ 开头的键创建去掉前缀的小写副本
    for key in list(processed_data.keys()):
        key_upper = key.upper()
        if key_upper.startswith("JARVIS_"):
            # 去掉 JARVIS_ 前缀，转换为小写
            short_key = key_upper[7:].lower()  # 去掉 "JARVIS_" (7个字符) 并转为小写
            # 只有当短键不存在时才创建，避免覆盖用户显式设置的配置
            # 使用大小写不敏感检查
            short_key_exists = any(
                k.upper() == short_key.upper() for k in processed_data.keys()
            )
            if not short_key_exists:
                processed_data[short_key] = processed_data[key]

    GLOBAL_CONFIG_DATA = CaseInsensitiveDict(processed_data)


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
def get_replace_map() -> dict:
    """
    获取替换映射表。

    优先使用GLOBAL_CONFIG_DATA['replace_map']的配置，
    如果没有则从数据目录下的replace_map.yaml文件中读取替换映射表，
    如果文件不存在则返回内置替换映射表。

    返回:
        dict: 合并后的替换映射表字典(内置+文件中的映射表)
    """
    if "replace_map" in GLOBAL_CONFIG_DATA:
        return {**BUILTIN_REPLACE_MAP, **GLOBAL_CONFIG_DATA["replace_map"]}

    replace_map_path = os.path.join(get_data_dir(), "replace_map.yaml")
    if not os.path.exists(replace_map_path):
        return BUILTIN_REPLACE_MAP.copy()

    print(
        "⚠️ 警告：使用replace_map.yaml进行配置的方式已被弃用，将在未来版本中移除。请迁移到使用GLOBAL_CONFIG_DATA中的replace_map配置。"
    )

    with open(replace_map_path, "r", encoding="utf-8", errors="ignore") as file:
        file_map = yaml.safe_load(file) or {}
        return {**BUILTIN_REPLACE_MAP, **file_map}


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


def _apply_llm_group_env_override(group_config: Dict[str, Any]) -> None:
    """如果模型组配置中包含ENV，则应用环境变量覆盖"""
    if "ENV" in group_config and isinstance(group_config["ENV"], dict):
        os.environ.update(
            {str(k): str(v) for k, v in group_config["ENV"].items() if v is not None}
        )


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
    llms = GLOBAL_CONFIG_DATA.get("llms", {})
    if not isinstance(llms, dict):
        return {}

    llm_config = llms.get(llm_name)
    if not isinstance(llm_config, dict):
        print(f"⚠️ 警告：llms 中未找到名为 '{llm_name}' 的配置")
        return {}

    return llm_config.copy()


def _expand_llm_references(group_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    展开 llm_groups 中的 llm 引用（normal_llm, cheap_llm, smart_llm）到对应的配置字段。

    参数:
        group_config: 模型组配置字典

    返回:
        Dict[str, Any]: 展开后的配置字典
    """
    expanded_config = group_config.copy()

    # 处理 normal_llm 引用
    if "normal_llm" in expanded_config:
        llm_ref = _resolve_llm_reference(expanded_config["normal_llm"])
        if llm_ref:
            # 展开到 platform, model, max_input_token_count
            if "platform" not in expanded_config:
                expanded_config["platform"] = llm_ref.get("platform", "openai")
            if "model" not in expanded_config:
                expanded_config["model"] = llm_ref.get("model", "gpt-5")
            if "max_input_token_count" not in expanded_config:
                expanded_config["max_input_token_count"] = llm_ref.get(
                    "max_input_token_count", 32000
                )
            # 合并 llm_config
            if "llm_config" in llm_ref:
                if "llm_config" not in expanded_config:
                    expanded_config["llm_config"] = {}
                expanded_config["llm_config"].update(llm_ref["llm_config"])
        # 移除引用键
        expanded_config.pop("normal_llm", None)

    # 处理 cheap_llm 引用
    if "cheap_llm" in expanded_config:
        llm_ref = _resolve_llm_reference(expanded_config["cheap_llm"])
        if llm_ref:
            if "cheap_platform" not in expanded_config:
                expanded_config["cheap_platform"] = llm_ref.get("platform", "openai")
            if "cheap_model" not in expanded_config:
                expanded_config["cheap_model"] = llm_ref.get("model", "gpt-5")
            if "cheap_max_input_token_count" not in expanded_config:
                expanded_config["cheap_max_input_token_count"] = llm_ref.get(
                    "max_input_token_count", 32000
                )
            # 合并 llm_config（如果 cheap_llm 有独立的 llm_config 需求，可以扩展）
            if "llm_config" in llm_ref:
                if "cheap_llm_config" not in expanded_config:
                    expanded_config["cheap_llm_config"] = {}
                expanded_config["cheap_llm_config"].update(llm_ref["llm_config"])
        expanded_config.pop("cheap_llm", None)

    # 处理 smart_llm 引用
    if "smart_llm" in expanded_config:
        llm_ref = _resolve_llm_reference(expanded_config["smart_llm"])
        if llm_ref:
            if "smart_platform" not in expanded_config:
                expanded_config["smart_platform"] = llm_ref.get("platform", "openai")
            if "smart_model" not in expanded_config:
                expanded_config["smart_model"] = llm_ref.get("model", "gpt-5")
            if "smart_max_input_token_count" not in expanded_config:
                expanded_config["smart_max_input_token_count"] = llm_ref.get(
                    "max_input_token_count", 32000
                )
            # 合并 llm_config
            if "llm_config" in llm_ref:
                if "smart_llm_config" not in expanded_config:
                    expanded_config["smart_llm_config"] = {}
                expanded_config["smart_llm_config"].update(llm_ref["llm_config"])
        expanded_config.pop("smart_llm", None)

    return expanded_config


def _get_resolved_model_config(
    model_group_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    解析并合并模型配置，处理模型组。

    优先级顺序:
    - 当通过 model_group_override（例如命令行 -g/--llm-group）指定组时：
        1. llm_group 中定义的组配置
        2. 仅当组未提供对应键时，回退到顶层环境变量 (platform, model, max_input_token_count)
        3. 代码中的默认值
    - 当未显式指定组时（使用默认组或未设置）：
        1. 顶层环境变量 (platform, model, max_input_token_count)
        2. llm_group 中定义的组配置
        3. 代码中的默认值

    返回:
        Dict[str, Any]: 解析后的模型配置字典
    """
    group_config = {}
    model_group_name = model_group_override or GLOBAL_CONFIG_DATA.get("llm_group")
    # The format is a list of single-key dicts: [{'group_name': {...}}, ...]
    model_groups = GLOBAL_CONFIG_DATA.get("llm_groups", [])

    if model_group_name and isinstance(model_groups, list):
        found = False
        for group_item in model_groups:
            if isinstance(group_item, dict) and model_group_name in group_item:
                group_config = group_item[model_group_name]
                found = True
                break

        # 当显式指定了模型组但未找到时，报错并退出
        if model_group_override and not found:
            print(f"❌ 错误：指定的模型组 '{model_group_name}' 不存在于配置中。")
            print(
                "ℹ️ 可用的模型组: "
                + ", ".join(
                    list(group.keys())[0]
                    for group in model_groups
                    if isinstance(group, dict)
                )
                if model_groups
                else "无可用模型组"
            )
            import sys

            sys.exit(1)

    # 展开 llm 引用（normal_llm, cheap_llm, smart_llm）
    group_config = _expand_llm_references(group_config)

    _apply_llm_group_env_override(group_config)

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

    # 应用 llm_config 到环境变量
    _apply_llm_config_to_env(resolved_config)

    return resolved_config


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


def _deprecated_platform_name_v1(model_group_override: Optional[str] = None) -> str:
    """
    获取思考操作的平台名称。

    返回：
        str: 平台名称，默认为正常操作平台
    """
    _get_resolved_model_config(model_group_override)
    # Fallback to normal platform if thinking platform is not specified
    return get_normal_platform_name(model_group_override)


def _deprecated_model_name_v1(model_group_override: Optional[str] = None) -> str:
    """
    获取思考操作的模型名称。

    返回：
        str: 模型名称，默认为正常操作模型
    """
    _get_resolved_model_config(model_group_override)
    # Fallback to normal model if thinking model is not specified
    return get_normal_model_name(model_group_override)


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


DEFAULT_RAG_GROUPS = [
    {
        "text": {
            "embedding_model": "BAAI/bge-m3",
            "embedding_type": "LocalEmbeddingModel",  # 模型实现类型
            "embedding_max_length": 512,  # 嵌入模型最大输入长度（token数）
            "rerank_model": "BAAI/bge-reranker-v2-m3",
            "reranker_type": "LocalReranker",  # 模型实现类型
            "reranker_max_length": 512,  # 重排模型最大输入长度（token数）
            "use_bm25": True,
            "use_rerank": True,
        }
    },
    {
        "code": {
            "embedding_model": "Qodo/Qodo-Embed-1-1.5B",
            "embedding_type": "LocalEmbeddingModel",
            "embedding_max_length": 512,
            "use_bm25": False,
            "use_rerank": False,
        }
    },
]


def _get_resolved_rag_config(
    rag_group_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    解析并合并RAG配置，处理RAG组。

    优先级顺序:
    1. rag 中的顶级设置 (embedding_model, etc.)
    2. rag_group 中定义的组配置
    3. 代码中的默认值

    返回:
        Dict[str, Any]: 解析后的RAG配置字典
    """
    group_config = {}
    rag_group_name = rag_group_override or GLOBAL_CONFIG_DATA.get("rag_group")
    rag_groups = GLOBAL_CONFIG_DATA.get("rag_groups", DEFAULT_RAG_GROUPS)

    if rag_group_name and isinstance(rag_groups, list):
        for group_item in rag_groups:
            if isinstance(group_item, dict) and rag_group_name in group_item:
                group_config = group_item[rag_group_name]
                break

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
    return config.get("embedding_config", {})


def get_rag_reranker_config() -> Dict[str, Any]:
    """
    获取RAG重排模型的额外配置参数。

    返回:
        Dict[str, Any]: 重排模型的配置参数字典，如果未配置则返回空字典
    """
    config = _get_resolved_rag_config()
    return config.get("reranker_config", {})


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
    return GLOBAL_CONFIG_DATA.get("web_search_platform")


def get_web_search_model_name() -> Optional[str]:
    """
    获取Web搜索使用的模型名称。

    返回:
        Optional[str]: 模型名称，如果未配置则返回None
    """
    return GLOBAL_CONFIG_DATA.get("web_search_model")


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
