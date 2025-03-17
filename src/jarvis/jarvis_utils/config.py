import os
"""
配置管理模块
该模块提供了获取Jarvis系统各种配置设置的函数。
所有配置都从环境变量中读取，带有回退默认值。
该模块组织为以下几个类别：
- 系统配置
- 模型配置
- 执行配置
- 文本处理配置
"""
def get_max_token_count() -> int:
    """
    获取API请求的最大token数量。
    
    返回：
        int: 最大token数量，默认为131072（128k）
    """
    return int(os.getenv('JARVIS_MAX_TOKEN_COUNT', '131072'))  # 默认128k
    
def get_thread_count() -> int:
    """
    获取用于并行处理的线程数。
    
    返回：
        int: 线程数，默认为1
    """
    return int(os.getenv('JARVIS_THREAD_COUNT', '1'))  
def dont_use_local_model() -> bool:
    """
    检查是否应避免使用本地模型。
    
    返回：
        bool: 如果不使用本地模型则返回True，默认为False
    """
    return os.getenv('JARVIS_DONT_USE_LOCAL_MODEL', 'false') == 'true'
    
def is_auto_complete() -> bool:
    """
    检查是否启用了自动补全功能。
    
    返回：
        bool: 如果启用了自动补全则返回True，默认为False
    """
    return os.getenv('JARVIS_AUTO_COMPLETE', 'false') == 'true'
    
def is_use_methodology() -> bool:
    """
    检查是否应使用方法论。
    
    返回：
        bool: 如果使用方法论则返回True，默认为True
    """
    return os.getenv('JARVIS_USE_METHODOLOGY', 'true') == 'true'
def is_record_methodology() -> bool:
    """
    检查是否应记录方法论。
    
    返回：
        bool: 如果记录方法论则返回True，默认为True
    """
    return os.getenv('JARVIS_RECORD_METHODOLOGY', 'true') == 'true'
def is_need_summary() -> bool:
    """
    检查是否需要生成摘要。
    
    返回：
        bool: 如果需要摘要则返回True，默认为True
    """
    return os.getenv('JARVIS_NEED_SUMMARY', 'true') == 'true'
def get_min_paragraph_length() -> int:
    """
    获取文本处理的最小段落长度。
    
    返回：
        int: 最小字符长度，默认为50
    """
    return int(os.getenv('JARVIS_MIN_PARAGRAPH_LENGTH', '50'))
def get_max_paragraph_length() -> int:
    """
    获取文本处理的最大段落长度。
    
    返回：
        int: 最大字符长度，默认为12800
    """
    return int(os.getenv('JARVIS_MAX_PARAGRAPH_LENGTH', '12800'))
def get_shell_name() -> str:
    """
    获取系统shell名称。
    
    返回：
        str: Shell名称（例如bash, zsh），默认为bash
    """
    return os.getenv('SHELL', 'bash')
def get_normal_platform_name() -> str:
    """
    获取正常操作的平台名称。
    
    返回：
        str: 平台名称，默认为'kimi'
    """
    return os.getenv('JARVIS_PLATFORM', 'kimi')
def get_normal_model_name() -> str:
    """
    获取正常操作的模型名称。
    
    返回：
        str: 模型名称，默认为'kimi'
    """
    return os.getenv('JARVIS_MODEL', 'kimi')
def get_codegen_platform_name() -> str:
    """
    获取代码生成的平台名称。
    
    返回：
        str: 平台名称，默认为'kimi'
    """
    return os.getenv('JARVIS_CODEGEN_PLATFORM', os.getenv('JARVIS_PLATFORM', 'kimi'))
def get_codegen_model_name() -> str:
    """
    获取代码生成的模型名称。
    
    返回：
        str: 模型名称，默认为'kimi'
    """
    return os.getenv('JARVIS_CODEGEN_MODEL', os.getenv('JARVIS_MODEL', 'kimi'))
def get_thinking_platform_name() -> str:
    """
    获取思考操作的平台名称。
    
    返回：
        str: 平台名称，默认为'kimi'
    """
    return os.getenv('JARVIS_THINKING_PLATFORM', os.getenv('JARVIS_PLATFORM', 'kimi'))
def get_thinking_model_name() -> str:
    """
    获取思考操作的模型名称。
    
    返回：
        str: 模型名称，默认为'kimi'
    """
    return os.getenv('JARVIS_THINKING_MODEL', os.getenv('JARVIS_MODEL', 'kimi'))
def get_cheap_platform_name() -> str:
    """
    获取低成本操作的平台名称。
    
    返回：
        str: 平台名称，默认为'kimi'
    """
    return os.getenv('JARVIS_CHEAP_PLATFORM', os.getenv('JARVIS_PLATFORM', 'kimi'))
def get_cheap_model_name() -> str:
    """
    获取低成本操作的模型名称。
    
    返回：
        str: 模型名称，默认为'kimi'
    """
    return os.getenv('JARVIS_CHEAP_MODEL', os.getenv('JARVIS_MODEL', 'kimi'))
def is_execute_tool_confirm() -> bool:
    """
    检查工具执行是否需要确认。
    
    返回：
        bool: 如果需要确认则返回True，默认为False
    """
    return os.getenv('JARVIS_EXECUTE_TOOL_CONFIRM', 'false') == 'true'
def is_confirm_before_apply_patch() -> bool:
    """
    检查应用补丁前是否需要确认。
    
    返回：
        bool: 如果需要确认则返回True，默认为False
    """
    return os.getenv('JARVIS_CONFIRM_BEFORE_APPLY_PATCH', 'true') == 'true'
