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

# 输出窗口预留大小
INPUT_WINDOW_REVERSE_SIZE = 2048

def get_max_token_count() -> int:
    """
    获取模型允许的最大token数量。

    返回:
        int: 模型能处理的最大token数量。
    """
    return int(os.getenv('JARVIS_MAX_TOKEN_COUNT', '102400000'))

def get_max_input_token_count() -> int:
    """
    获取模型允许的最大输入token数量。

    返回:
        int: 模型能处理的最大输入token数量。
    """
    return int(os.getenv('JARVIS_MAX_INPUT_TOKEN_COUNT', '32000'))

def get_thread_count() -> int:
    """
    获取用于并行处理的线程数。

    返回：
        int: 线程数，默认为1
    """
    return int(os.getenv('JARVIS_THREAD_COUNT', '1'))

def is_auto_complete() -> bool:
    """
    检查是否启用了自动补全功能。

    返回：
        bool: 如果启用了自动补全则返回True，默认为False
    """
    return os.getenv('JARVIS_AUTO_COMPLETE', 'false') == 'true'


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
        str: 平台名称，默认为'yuanbao'
    """
    return os.getenv('JARVIS_PLATFORM', 'yuanbao')
def get_normal_model_name() -> str:
    """
    获取正常操作的模型名称。

    返回：
        str: 模型名称，默认为'deep_seek'
    """
    return os.getenv('JARVIS_MODEL', 'deep_seek_v3')


def get_thinking_platform_name() -> str:
    """
    获取思考操作的平台名称。

    返回：
        str: 平台名称，默认为'yuanbao'
    """
    return os.getenv('JARVIS_THINKING_PLATFORM', os.getenv('JARVIS_PLATFORM', 'yuanbao'))
def get_thinking_model_name() -> str:
    """
    获取思考操作的模型名称。

    返回：
        str: 模型名称，默认为'deep_seek'
    """
    return os.getenv('JARVIS_THINKING_MODEL', os.getenv('JARVIS_MODEL', 'deep_seek'))

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

def get_max_tool_call_count() -> int:
    """
    获取最大工具调用次数。

    返回：
        int: 最大连续工具调用次数，默认为20
    """
    return int(os.getenv('JARVIS_MAX_TOOL_CALL_COUNT', '20'))
