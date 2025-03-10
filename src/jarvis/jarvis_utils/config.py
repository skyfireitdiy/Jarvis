import os
def get_max_token_count():
    return int(os.getenv('JARVIS_MAX_TOKEN_COUNT', '131072'))  # 默认128k
    
def get_thread_count():
    return int(os.getenv('JARVIS_THREAD_COUNT', '1'))  
def dont_use_local_model():
    return os.getenv('JARVIS_DONT_USE_LOCAL_MODEL', 'false') == 'true'
    
def is_auto_complete() -> bool:
    return os.getenv('JARVIS_AUTO_COMPLETE', 'false') == 'true'
    
def is_use_methodology() -> bool:
    return os.getenv('JARVIS_USE_METHODOLOGY', 'true') == 'true'
def is_record_methodology() -> bool:
    return os.getenv('JARVIS_RECORD_METHODOLOGY', 'true') == 'true'
def is_need_summary() -> bool:
    return os.getenv('JARVIS_NEED_SUMMARY', 'true') == 'true'
def get_min_paragraph_length() -> int:
    return int(os.getenv('JARVIS_MIN_PARAGRAPH_LENGTH', '50'))
def get_max_paragraph_length() -> int:
    return int(os.getenv('JARVIS_MAX_PARAGRAPH_LENGTH', '12800'))
def get_shell_name() -> str:
    return os.getenv('SHELL', 'bash')
def get_normal_platform_name() -> str:
    return os.getenv('JARVIS_PLATFORM', 'kimi')
def get_normal_model_name() -> str:
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
    return os.getenv('JARVIS_EXECUTE_TOOL_CONFIRM', 'false') == 'true'
def is_confirm_before_apply_patch() -> bool:
    return os.getenv('JARVIS_CONFIRM_BEFORE_APPLY_PATCH', 'false') == 'true'