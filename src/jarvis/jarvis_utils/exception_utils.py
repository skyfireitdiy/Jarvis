# -*- coding: utf-8 -*-
"""异常记录工具模块。

提供统一的异常信息记录功能，将异常详情保存到 ~/.jarvis/exceptions/ 目录，
用于后续分析和优化。保存失败时静默忽略，不影响主流程。
"""

import os


def save_exception(
    exception: Exception,
    context: str = "",
    module: str = "",
    function: str = "",
) -> None:
    """将异常信息记录到数据目录，用于后续分析和优化。

    异常记录保存在 ~/.jarvis/exceptions/ 目录下，
    文件名格式为 {YYYYMMDD_HHMMSS}_{module}_{function}.json。
    保存失败时静默忽略，不影响主流程。

    参数:
        exception: 捕获的异常对象
        context: 可选的上下文描述，说明异常发生时的业务场景
        module: 可选的模块名称，如 "jarvis_tools"
        function: 可选的函数名称，如 "_extract_tool_calls"
    """
    try:
        import json
        import re
        import time
        import traceback

        from jarvis.jarvis_utils.config import get_data_dir

        # 创建保存目录
        exception_dir = os.path.join(get_data_dir(), "exceptions")
        os.makedirs(exception_dir, exist_ok=True)

        # 获取异常的traceback信息
        tb_str = traceback.format_exception(
            type(exception), exception, exception.__traceback__
        )
        tb_text = "".join(tb_str)

        # 脱敏：移除可能的API key等敏感信息
        safe_tb = tb_text
        safe_context = context or ""
        sensitive_patterns = [
            r"sk-[a-zA-Z0-9]{20,}",
            r'key["\s:=]+["\']?[a-zA-Z0-9]{20,}["\']?',
            r'token["\s:=]+["\']?[a-zA-Z0-9]{20,}["\']?',
            r'password["\s:=]+["\']?[a-zA-Z0-9]{20,}["\']?',
        ]
        for pattern in sensitive_patterns:
            safe_tb = re.sub(pattern, "[REDACTED]", safe_tb)
            safe_context = re.sub(pattern, "[REDACTED]", safe_context)

        # 构建保存数据
        error_data = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "exception_type": type(exception).__name__,
            "exception_msg": str(exception),
            "traceback": safe_tb,
            "context": safe_context,
            "module": module,
            "function": function,
        }

        # 保存文件：时间戳_模块_函数.json
        safe_module = (
            module.replace("/", "_").replace("\\", "_") if module else "unknown"
        )
        safe_function = (
            function.replace("/", "_").replace("\\", "_") if function else "unknown"
        )
        filename = (
            f"{time.strftime('%Y%m%d_%H%M%S')}_{safe_module}_{safe_function}.json"
        )
        filepath = os.path.join(exception_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(error_data, f, ensure_ascii=False, indent=2)
    except Exception:
        # 保存失败不影响主流程，静默忽略
        pass
