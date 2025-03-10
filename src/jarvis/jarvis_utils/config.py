import os
"""
Configuration Management Module
This module provides functions to retrieve various configuration settings for the Jarvis system.
All configurations are read from environment variables with fallback default values.
The module is organized into several categories:
- System Configuration
- Model Configuration
- Execution Configuration
- Text Processing Configuration
"""
def get_max_token_count() -> int:
    """
    Get the maximum token count for API requests.
    
    Returns:
        int: Maximum token count, default is 131072 (128k)
    """
    return int(os.getenv('JARVIS_MAX_TOKEN_COUNT', '131072'))  # 默认128k
    
def get_thread_count() -> int:
    """
    Get the number of threads to use for parallel processing.
    
    Returns:
        int: Thread count, default is 1
    """
    return int(os.getenv('JARVIS_THREAD_COUNT', '1'))  
def dont_use_local_model() -> bool:
    """
    Check if local models should be avoided.
    
    Returns:
        bool: True if local models should not be used, default is False
    """
    return os.getenv('JARVIS_DONT_USE_LOCAL_MODEL', 'false') == 'true'
    
def is_auto_complete() -> bool:
    """
    Check if auto-completion is enabled.
    
    Returns:
        bool: True if auto-completion is enabled, default is False
    """
    return os.getenv('JARVIS_AUTO_COMPLETE', 'false') == 'true'
    
def is_use_methodology() -> bool:
    """
    Check if methodology should be used.
    
    Returns:
        bool: True if methodology should be used, default is True
    """
    return os.getenv('JARVIS_USE_METHODOLOGY', 'true') == 'true'
def is_record_methodology() -> bool:
    """
    Check if methodology should be recorded.
    
    Returns:
        bool: True if methodology should be recorded, default is True
    """
    return os.getenv('JARVIS_RECORD_METHODOLOGY', 'true') == 'true'
def is_need_summary() -> bool:
    """
    Check if summary generation is required.
    
    Returns:
        bool: True if summary is needed, default is True
    """
    return os.getenv('JARVIS_NEED_SUMMARY', 'true') == 'true'
def get_min_paragraph_length() -> int:
    """
    Get the minimum paragraph length for text processing.
    
    Returns:
        int: Minimum length in characters, default is 50
    """
    return int(os.getenv('JARVIS_MIN_PARAGRAPH_LENGTH', '50'))
def get_max_paragraph_length() -> int:
    """
    Get the maximum paragraph length for text processing.
    
    Returns:
        int: Maximum length in characters, default is 12800
    """
    return int(os.getenv('JARVIS_MAX_PARAGRAPH_LENGTH', '12800'))
def get_shell_name() -> str:
    """
    Get the system shell name.
    
    Returns:
        str: Shell name (e.g., bash, zsh), default is bash
    """
    return os.getenv('SHELL', 'bash')
def get_normal_platform_name() -> str:
    """
    Get the platform name for normal operations.
    
    Returns:
        str: Platform name, default is 'kimi'
    """
    return os.getenv('JARVIS_PLATFORM', 'kimi')
def get_normal_model_name() -> str:
    """
    Get the model name for normal operations.
    
    Returns:
        str: Model name, default is 'kimi'
    """
    return os.getenv('JARVIS_MODEL', 'kimi')
def get_codegen_platform_name() -> str:
    return os.getenv('JARVIS_CODEGEN_PLATFORM', os.getenv('JARVIS_PLATFORM', 'kimi'))
def get_codegen_model_name() -> str:
    return os.getenv('JARVIS_CODEGEN_MODEL', os.getenv('JARVIS_MODEL', 'kimi'))
def get_thinking_platform_name() -> str:
    return os.getenv('JARVIS_THINKING_PLATFORM', os.getenv('JARVIS_PLATFORM', 'kimi'))
def get_thinking_model_name() -> str:
    return os.getenv('JARVIS_THINKING_MODEL', os.getenv('JARVIS_MODEL', 'kimi'))
def get_cheap_platform_name() -> str:
    return os.getenv('JARVIS_CHEAP_PLATFORM', os.getenv('JARVIS_PLATFORM', 'kimi'))
def get_cheap_model_name() -> str:
    return os.getenv('JARVIS_CHEAP_MODEL', os.getenv('JARVIS_MODEL', 'kimi'))
def is_execute_tool_confirm() -> bool:
    """
    Check if tool execution requires confirmation.
    
    Returns:
        bool: True if confirmation is required, default is False
    """
    return os.getenv('JARVIS_EXECUTE_TOOL_CONFIRM', 'false') == 'true'
def is_confirm_before_apply_patch() -> bool:
    """
    Check if patch application requires confirmation.
    
    Returns:
        bool: True if confirmation is required, default is False
    """
    return os.getenv('JARVIS_CONFIRM_BEFORE_APPLY_PATCH', 'false') == 'true'