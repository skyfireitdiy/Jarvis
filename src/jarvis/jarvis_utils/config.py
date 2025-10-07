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


def get_max_token_count(model_group_override: Optional[str] = None) -> int:
    """
    获取模型允许的最大token数量。

    返回:
        int: 模型能处理的最大token数量，为最大输入token数量的100倍。
    """
    max_input_tokens = get_max_input_token_count(model_group_override)
    return max_input_tokens * 100


def get_max_input_token_count(model_group_override: Optional[str] = None) -> int:
    """
    获取模型允许的最大输入token数量。

    返回:
        int: 模型能处理的最大输入token数量。
    """
    config = _get_resolved_model_config(model_group_override)
    return int(config.get("JARVIS_MAX_INPUT_TOKEN_COUNT", "32000"))


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


def _apply_llm_group_env_override(group_config: Dict[str, Any]) -> None:
    """如果模型组配置中包含ENV，则应用环境变量覆盖"""
    if "ENV" in group_config and isinstance(group_config["ENV"], dict):
        os.environ.update(
            {str(k): str(v) for k, v in group_config["ENV"].items() if v is not None}
        )


def _get_resolved_model_config(
    model_group_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    解析并合并模型配置，处理模型组。

    优先级顺序:
    - 当通过 model_group_override（例如命令行 -g/--llm-group）指定组时：
        1. JARVIS_LLM_GROUP 中定义的组配置
        2. 仅当组未提供对应键时，回退到顶层环境变量 (JARVIS_PLATFORM, JARVIS_MODEL, JARVIS_MAX_INPUT_TOKEN_COUNT)
        3. 代码中的默认值
    - 当未显式指定组时（使用默认组或未设置）：
        1. 顶层环境变量 (JARVIS_PLATFORM, JARVIS_MODEL, JARVIS_MAX_INPUT_TOKEN_COUNT)
        2. JARVIS_LLM_GROUP 中定义的组配置
        3. 代码中的默认值

    返回:
        Dict[str, Any]: 解析后的模型配置字典
    """
    group_config = {}
    model_group_name = model_group_override or GLOBAL_CONFIG_DATA.get(
        "JARVIS_LLM_GROUP"
    )
    # The format is a list of single-key dicts: [{'group_name': {...}}, ...]
    model_groups = GLOBAL_CONFIG_DATA.get("JARVIS_LLM_GROUPS", [])

    if model_group_name and isinstance(model_groups, list):
        for group_item in model_groups:
            if isinstance(group_item, dict) and model_group_name in group_item:
                group_config = group_item[model_group_name]
                break
    
    _apply_llm_group_env_override(group_config)

    # Start with group config
    resolved_config = group_config.copy()

    # 覆盖策略：
    # - 若通过 CLI 传入了 model_group_override，则优先使用组内配置；
    #   仅当组未提供对应键时，才回落到顶层 GLOBAL_CONFIG_DATA。
    # - 若未传入 override（即使用默认组），保持原有行为：由顶层键覆盖组配置。
    override_keys = [
        "JARVIS_PLATFORM",
        "JARVIS_MODEL",
        "JARVIS_MAX_INPUT_TOKEN_COUNT",
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


def is_execute_tool_confirm() -> bool:
    """
    检查工具执行是否需要确认。

    返回：
        bool: 如果需要确认则返回True，默认为False
    """
    return GLOBAL_CONFIG_DATA.get("JARVIS_EXECUTE_TOOL_CONFIRM", False)


def is_confirm_before_apply_patch() -> bool:
    """
    检查应用补丁前是否需要确认。

    返回：
        bool: 如果需要确认则返回True，默认为False
    """
    return GLOBAL_CONFIG_DATA.get("JARVIS_CONFIRM_BEFORE_APPLY_PATCH", False)


def get_patch_format() -> str:
    """
    获取补丁格式。

    - "search": 仅使用精确匹配的 `SEARCH` 模式。此模式对能力较弱的模型更稳定，因为它要求代码片段完全匹配。
    - "search_range": 仅使用 `SEARCH_START` 和 `SEARCH_END` 的范围匹配模式。此模式对能力较强的模型更灵活，因为它允许在代码块内部进行修改，而不要求整个块完全匹配。
    - "all": 同时支持以上两种模式（默认）。

    返回:
        str: "all", "search", or "search_range"
    """
    mode = GLOBAL_CONFIG_DATA.get("JARVIS_PATCH_FORMAT", "all")
    if mode in ["all", "search", "search_range"]:
        return mode
    return "all"


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

    return GLOBAL_CONFIG_DATA.get("JARVIS_PRETTY_OUTPUT", True)


def is_use_methodology() -> bool:
    """
    获取是否启用方法论。

    返回：
        bool: 如果启用方法论则返回True，默认为True
    """
    return GLOBAL_CONFIG_DATA.get("JARVIS_USE_METHODOLOGY", True)


def is_use_analysis() -> bool:
    """
    获取是否启用任务分析。

    返回：
        bool: 如果启用任务分析则返回True，默认为True
    """
    return GLOBAL_CONFIG_DATA.get("JARVIS_USE_ANALYSIS", True)


def get_tool_load_dirs() -> List[str]:
    """
    获取工具加载目录。

    返回:
        List[str]: 工具加载目录列表
    """
    return [
        os.path.expanduser(os.path.expandvars(str(p)))
        for p in GLOBAL_CONFIG_DATA.get("JARVIS_TOOL_LOAD_DIRS", [])
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
        for p in GLOBAL_CONFIG_DATA.get("JARVIS_METHODOLOGY_DIRS", [])
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
        for p in GLOBAL_CONFIG_DATA.get("JARVIS_AGENT_DEFINITION_DIRS", [])
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
        for p in GLOBAL_CONFIG_DATA.get("JARVIS_MULTI_AGENT_DIRS", [])
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
        for p in GLOBAL_CONFIG_DATA.get("JARVIS_ROLES_DIRS", [])
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
        for p in GLOBAL_CONFIG_DATA.get("JARVIS_AFTER_TOOL_CALL_CB_DIRS", [])
        if p
    ]


def get_central_methodology_repo() -> str:
    """
    获取中心方法论Git仓库地址。

    返回:
        str: 中心方法论Git仓库地址，如果未配置则返回空字符串
    """
    return GLOBAL_CONFIG_DATA.get("JARVIS_CENTRAL_METHODOLOGY_REPO", "")


def get_central_tool_repo() -> str:
    """
    获取中心工具Git仓库地址。

    返回:
        str: 中心工具Git仓库地址，如果未配置则返回空字符串
    """
    return GLOBAL_CONFIG_DATA.get("JARVIS_CENTRAL_TOOL_REPO", "")


def is_print_prompt() -> bool:
    """
    获取是否打印提示。

    返回：
        bool: 如果打印提示则返回True，默认为True
    """
    return GLOBAL_CONFIG_DATA.get("JARVIS_PRINT_PROMPT", False)


def is_print_error_traceback() -> bool:
    """
    获取是否在错误输出时打印回溯调用链。

    返回：
        bool: 如果打印回溯则返回True，默认为False（不打印）
    """
    return GLOBAL_CONFIG_DATA.get("JARVIS_PRINT_ERROR_TRACEBACK", False) is True


def is_force_save_memory() -> bool:
    """
    获取是否强制保存记忆。

    返回：
        bool: 如果强制保存记忆则返回True，默认为False
    """
    return GLOBAL_CONFIG_DATA.get("JARVIS_FORCE_SAVE_MEMORY", False) is True


def is_enable_static_analysis() -> bool:
    """
    获取是否启用静态代码分析。

    返回：
        bool: 如果启用静态代码分析则返回True，默认为True
    """
    return GLOBAL_CONFIG_DATA.get("JARVIS_ENABLE_STATIC_ANALYSIS", True) is True


def get_git_check_mode() -> str:
    """
    获取Git校验模式。

    返回:
        str: "strict" 或 "warn"，默认为 "strict"
    """
    mode = GLOBAL_CONFIG_DATA.get("JARVIS_GIT_CHECK_MODE", "strict")
    try:
        return str(mode)
    except Exception:
        return "strict"


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


DEFAULT_RAG_GROUPS = [
    {
        "text": {
            "embedding_model": "BAAI/bge-m3",
            "rerank_model": "BAAI/bge-reranker-v2-m3",
            "use_bm25": True,
            "use_rerank": True,
        }
    },
    {
        "code": {
            "embedding_model": "Qodo/Qodo-Embed-1-1.5B",
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
    1. JARVIS_RAG 中的顶级设置 (embedding_model, etc.)
    2. JARVIS_RAG_GROUP 中定义的组配置
    3. 代码中的默认值

    返回:
        Dict[str, Any]: 解析后的RAG配置字典
    """
    group_config = {}
    rag_group_name = rag_group_override or GLOBAL_CONFIG_DATA.get("JARVIS_RAG_GROUP")
    rag_groups = GLOBAL_CONFIG_DATA.get("JARVIS_RAG_GROUPS", DEFAULT_RAG_GROUPS)

    if rag_group_name and isinstance(rag_groups, list):
        for group_item in rag_groups:
            if isinstance(group_item, dict) and rag_group_name in group_item:
                group_config = group_item[rag_group_name]
                break

    # Start with group config
    resolved_config = group_config.copy()

    # Override with specific settings from the top-level JARVIS_RAG dict
    top_level_rag_config = GLOBAL_CONFIG_DATA.get("JARVIS_RAG", {})
    if isinstance(top_level_rag_config, dict):
        for key in [
            "embedding_model",
            "rerank_model",
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
    return config.get("embedding_model", "BAAI/bge-m3")


def get_rag_rerank_model() -> str:
    """
    获取RAG rerank模型的名称。

    返回:
        str: rerank模型的名称
    """
    config = _get_resolved_rag_config()
    return config.get("rerank_model", "BAAI/bge-reranker-v2-m3")


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


# ==============================================================================
# Web Search Configuration
# ==============================================================================


def get_web_search_platform_name() -> Optional[str]:
    """
    获取Web搜索使用的平台名称。

    返回:
        Optional[str]: 平台名称，如果未配置则返回None
    """
    return GLOBAL_CONFIG_DATA.get("JARVIS_WEB_SEARCH_PLATFORM")


def get_web_search_model_name() -> Optional[str]:
    """
    获取Web搜索使用的模型名称。

    返回:
        Optional[str]: 模型名称，如果未配置则返回None
    """
    return GLOBAL_CONFIG_DATA.get("JARVIS_WEB_SEARCH_MODEL")


# ==============================================================================
# Tool Configuration
# ==============================================================================


def _get_resolved_tool_config(
    tool_group_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    解析并合并工具配置，处理工具组。

    优先级顺序:
    1. JARVIS_TOOL_GROUP 中定义的组配置
    2. 默认配置（所有工具都启用）

    返回:
        Dict[str, Any]: 解析后的工具配置字典，包含 'use' 和 'dont_use' 列表
    """
    group_config = {}
    tool_group_name = tool_group_override or GLOBAL_CONFIG_DATA.get("JARVIS_TOOL_GROUP")
    tool_groups = GLOBAL_CONFIG_DATA.get("JARVIS_TOOL_GROUPS", [])

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
    return config.get("use", [])


def get_tool_dont_use_list() -> List[str]:
    """
    获取不使用的工具列表。

    返回:
        List[str]: 不使用的工具名称列表
    """
    config = _get_resolved_tool_config()
    return config.get("dont_use", [])


def get_tool_filter_threshold() -> int:
    """
    获取AI工具筛选的阈值。

    返回:
        int: 当工具数量超过此阈值时，触发AI筛选。默认为30
    """
    return int(GLOBAL_CONFIG_DATA.get("JARVIS_TOOL_FILTER_THRESHOLD", 30))


def get_script_execution_timeout() -> int:
    """
    获取脚本执行的超时时间（秒）。

    返回:
        int: 超时时间，默认为300秒（5分钟）
    """
    return int(GLOBAL_CONFIG_DATA.get("JARVIS_SCRIPT_EXECUTION_TIMEOUT", 300))


def is_enable_git_repo_jca_switch() -> bool:
    """
    是否启用：在初始化环境前检测Git仓库并提示可切换到代码开发模式（jca）
    默认关闭
    """
    return GLOBAL_CONFIG_DATA.get("JARVIS_ENABLE_GIT_JCA_SWITCH", False) is True


def is_enable_builtin_config_selector() -> bool:
    """
    是否启用：在进入默认通用代理前，列出可用配置（agent/multi_agent/roles）供选择
    默认关闭
    """
    return (
        GLOBAL_CONFIG_DATA.get("JARVIS_ENABLE_STARTUP_CONFIG_SELECTOR", False) is True
    )


def is_save_session_history() -> bool:
    """
    是否保存会话记录。

    返回:
        bool: 如果要保存会话记录则返回True, 默认为False
    """
    return GLOBAL_CONFIG_DATA.get("JARVIS_SAVE_SESSION_HISTORY", False) is True


def is_immediate_abort() -> bool:
    """
    是否启用立即中断：当在对话过程中检测到用户中断信号时，立即停止输出并返回。
    默认关闭
    """
    return GLOBAL_CONFIG_DATA.get("JARVIS_IMMEDIATE_ABORT", False) is True


def is_non_interactive() -> bool:
    """
    获取是否启用非交互模式。
    
    返回：
        bool: 如果启用非交互模式则返回True，默认为False
    """
    # 优先读取环境变量，确保 CLI 标志生效且不被配置覆盖
    try:
        import os
        v = os.getenv("JARVIS_NON_INTERACTIVE")
        if v is not None:
            val = str(v).strip().lower()
            if val in ("1", "true", "yes", "on"):
                return True
            if val in ("0", "false", "no", "off"):
                return False
    except Exception:
        # 忽略环境变量解析异常，回退到配置
        pass
    return GLOBAL_CONFIG_DATA.get("JARVIS_NON_INTERACTIVE", False) is True
