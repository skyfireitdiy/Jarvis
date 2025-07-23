# -*- coding: utf-8 -*-
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional

import yaml  # type: ignore

from jarvis.jarvis_utils.builtin_replace_map import BUILTIN_REPLACE_MAP

# 全局环境变量存储

GLOBAL_CONFIG_DATA: Dict[str, Any] = {}


def set_global_env_data(env_data: Dict[str, Any]) -> None:
    """设置全局环境变量数据"""
    global GLOBAL_CONFIG_DATA
    GLOBAL_CONFIG_DATA = env_data


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
    return GLOBAL_CONFIG_DATA.get("JARVIS_GIT_COMMIT_PROMPT", "")


# 输出窗口预留大小
INPUT_WINDOW_REVERSE_SIZE = 2048


@lru_cache(maxsize=None)
def get_replace_map() -> dict:
    """
    获取替换映射表。

    优先使用GLOBAL_CONFIG_DATA['JARVIS_REPLACE_MAP']的配置，
    如果没有则从数据目录下的replace_map.yaml文件中读取替换映射表，
    如果文件不存在则返回内置替换映射表。

    返回:
        dict: 合并后的替换映射表字典(内置+文件中的映射表)
    """
    if "JARVIS_REPLACE_MAP" in GLOBAL_CONFIG_DATA:
        return {**BUILTIN_REPLACE_MAP, **GLOBAL_CONFIG_DATA["JARVIS_REPLACE_MAP"]}

    replace_map_path = os.path.join(get_data_dir(), "replace_map.yaml")
    if not os.path.exists(replace_map_path):
        return BUILTIN_REPLACE_MAP.copy()

    from jarvis.jarvis_utils.output import OutputType, PrettyOutput

    PrettyOutput.print(
        "警告：使用replace_map.yaml进行配置的方式已被弃用，将在未来版本中移除。"
        "请迁移到使用GLOBAL_CONFIG_DATA中的JARVIS_REPLACE_MAP配置。",
        output_type=OutputType.WARNING,
    )

    with open(replace_map_path, "r", encoding="utf-8", errors="ignore") as file:
        file_map = yaml.safe_load(file) or {}
        return {**BUILTIN_REPLACE_MAP, **file_map}


def get_max_token_count() -> int:
    """
    获取模型允许的最大token数量。

    返回:
        int: 模型能处理的最大token数量。
    """
    return int(GLOBAL_CONFIG_DATA.get("JARVIS_MAX_TOKEN_COUNT", "960000"))


def get_max_input_token_count() -> int:
    """
    获取模型允许的最大输入token数量。

    返回:
        int: 模型能处理的最大输入token数量。
    """
    return int(GLOBAL_CONFIG_DATA.get("JARVIS_MAX_INPUT_TOKEN_COUNT", "32000"))


def get_shell_name() -> str:
    """
    获取系统shell名称。

    返回：
        str: Shell名称（例如bash, zsh, fish），默认为bash

    获取顺序：
    1. 先从GLOBAL_CONFIG_DATA中获取JARVIS_SHELL配置
    2. 再从GLOBAL_CONFIG_DATA中获取SHELL配置
    3. 最后从环境变量SHELL获取
    4. 如果都未配置，则默认返回bash
    """
    shell_path = GLOBAL_CONFIG_DATA.get("SHELL", os.getenv("SHELL", "/bin/bash"))
    return os.path.basename(shell_path).lower()


def _get_resolved_model_config(model_group_override: Optional[str] = None) -> Dict[str, Any]:
    """
    解析并合并模型配置，处理模型组。

    优先级顺序:
    1. 单独的环境变量 (JARVIS_PLATFORM, JARVIS_MODEL, etc.)
    2. MODEL_GROUP 中定义的组配置
    3. 代码中的默认值

    返回:
        Dict[str, Any]: 解析后的模型配置字典
    """
    group_config = {}
    model_group_name = model_group_override or GLOBAL_CONFIG_DATA.get("MODEL_GROUP")
    # The format is a list of single-key dicts: [{'group_name': {...}}, ...]
    model_groups = GLOBAL_CONFIG_DATA.get("JARVIS_MODEL_GROUPS", [])

    if model_group_name and isinstance(model_groups, list):
        for group_item in model_groups:
            if isinstance(group_item, dict) and model_group_name in group_item:
                group_config = group_item[model_group_name]
                break

    # Start with group config
    resolved_config = group_config.copy()

    # Override with specific settings from GLOBAL_CONFIG_DATA
    for key in [
        "JARVIS_PLATFORM",
        "JARVIS_MODEL",
        "JARVIS_THINKING_PLATFORM",
        "JARVIS_THINKING_MODEL",
    ]:
        if key in GLOBAL_CONFIG_DATA:
            resolved_config[key] = GLOBAL_CONFIG_DATA[key]

    return resolved_config


def get_normal_platform_name(model_group_override: Optional[str] = None) -> str:
    """
    获取正常操作的平台名称。

    返回：
        str: 平台名称，默认为'yuanbao'
    """
    config = _get_resolved_model_config(model_group_override)
    return config.get("JARVIS_PLATFORM", "yuanbao")


def get_normal_model_name(model_group_override: Optional[str] = None) -> str:
    """
    获取正常操作的模型名称。

    返回：
        str: 模型名称，默认为'deep_seek_v3'
    """
    config = _get_resolved_model_config(model_group_override)
    return config.get("JARVIS_MODEL", "deep_seek_v3")


def get_thinking_platform_name(model_group_override: Optional[str] = None) -> str:
    """
    获取思考操作的平台名称。

    返回：
        str: 平台名称，默认为正常操作平台
    """
    config = _get_resolved_model_config(model_group_override)
    # Fallback to normal platform if thinking platform is not specified
    return config.get(
        "JARVIS_THINKING_PLATFORM", get_normal_platform_name(model_group_override)
    )


def get_thinking_model_name(model_group_override: Optional[str] = None) -> str:
    """
    获取思考操作的模型名称。

    返回：
        str: 模型名称，默认为正常操作模型
    """
    config = _get_resolved_model_config(model_group_override)
    # Fallback to normal model if thinking model is not specified
    return config.get("JARVIS_THINKING_MODEL", get_normal_model_name(model_group_override))


def is_execute_tool_confirm() -> bool:
    """
    检查工具执行是否需要确认。

    返回：
        bool: 如果需要确认则返回True，默认为False
    """
    return GLOBAL_CONFIG_DATA.get("JARVIS_EXECUTE_TOOL_CONFIRM", False) == True


def is_confirm_before_apply_patch() -> bool:
    """
    检查应用补丁前是否需要确认。

    返回：
        bool: 如果需要确认则返回True，默认为False
    """
    return GLOBAL_CONFIG_DATA.get("JARVIS_CONFIRM_BEFORE_APPLY_PATCH", False) == True


def get_data_dir() -> str:
    """
    获取Jarvis数据存储目录路径。

    返回:
        str: 数据目录路径，优先从JARVIS_DATA_PATH环境变量获取，
             如果未设置或为空，则使用~/.jarvis作为默认值
    """
    return os.path.expanduser(
        GLOBAL_CONFIG_DATA.get("JARVIS_DATA_PATH", "~/.jarvis").strip()
    )


def get_max_big_content_size() -> int:
    """
    获取最大大内容大小。

    返回：
        int: 最大大内容大小
    """
    return int(GLOBAL_CONFIG_DATA.get("JARVIS_MAX_BIG_CONTENT_SIZE", "160000"))


def get_pretty_output() -> bool:
    """
    获取是否启用PrettyOutput。

    返回：
        bool: 如果启用PrettyOutput则返回True，默认为True
    """
    return GLOBAL_CONFIG_DATA.get("JARVIS_PRETTY_OUTPUT", False) == True


def is_use_methodology() -> bool:
    """
    获取是否启用方法论。

    返回：
        bool: 如果启用方法论则返回True，默认为True
    """
    return GLOBAL_CONFIG_DATA.get("JARVIS_USE_METHODOLOGY", True) == True


def is_use_analysis() -> bool:
    """
    获取是否启用任务分析。

    返回：
        bool: 如果启用任务分析则返回True，默认为True
    """
    return GLOBAL_CONFIG_DATA.get("JARVIS_USE_ANALYSIS", True) == True


def get_tool_load_dirs() -> List[str]:
    """
    获取工具加载目录。

    返回:
        List[str]: 工具加载目录列表
    """
    return GLOBAL_CONFIG_DATA.get("JARVIS_TOOL_LOAD_DIRS", [])


def get_methodology_dirs() -> List[str]:
    """
    获取方法论加载目录。

    返回:
        List[str]: 方法论加载目录列表
    """
    return GLOBAL_CONFIG_DATA.get("JARVIS_METHODOLOGY_DIRS", [])


def is_print_prompt() -> bool:
    """
    获取是否打印提示。

    返回：
        bool: 如果打印提示则返回True，默认为True
    """
    return GLOBAL_CONFIG_DATA.get("JARVIS_PRINT_PROMPT", False) == True


def is_enable_static_analysis() -> bool:
    """
    获取是否启用静态代码分析。

    返回：
        bool: 如果启用静态代码分析则返回True，默认为True
    """
    return GLOBAL_CONFIG_DATA.get("JARVIS_ENABLE_STATIC_ANALYSIS", True) is True


def get_mcp_config() -> List[Dict[str, Any]]:
    """
    获取MCP配置列表。

    返回:
        List[Dict[str, Any]]: MCP配置项列表，如果未配置则返回空列表
    """
    return GLOBAL_CONFIG_DATA.get("JARVIS_MCP", [])


# ==============================================================================
# RAG Framework Configuration
# ==============================================================================


def get_rag_config() -> Dict[str, Any]:
    """
    获取RAG框架的配置。

    返回:
        Dict[str, Any]: RAG配置字典
    """
    return GLOBAL_CONFIG_DATA.get("JARVIS_RAG", {})


def get_rag_embedding_model() -> str:
    """
    获取RAG嵌入模型的名称。

    返回:
        str: 嵌入模型的名称
    """
    return get_rag_config().get("embedding_model", "BAAI/bge-base-zh-v1.5")


def get_rag_rerank_model() -> str:
    """
    获取RAG rerank模型的名称。

    返回:
        str: rerank模型的名称
    """
    return get_rag_config().get("rerank_model", "BAAI/bge-reranker-base")


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
