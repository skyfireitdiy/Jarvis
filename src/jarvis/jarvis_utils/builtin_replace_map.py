# -*- coding: utf-8 -*-
"""内置替换映射表模块。

该模块定义了Jarvis系统内置的默认替换映射表。
格式: {"标记名": {"template": "替换模板", "description": "描述信息"}}
"""

from jarvis.jarvis_utils.tag import ct, ot

BUILTIN_REPLACE_MAP = {
    "Web": {
        "append": True,
        "template": f"""
请使用search_web工具进行网页搜索，必须严格遵守以下工具调用格式：

{ot("TOOL_CALL")}
want: 想要从执行结果中获取到的信息
name: search_web
arguments:
    query: "xxx技术的最新发展是什么？"
{ct("TOOL_CALL")}

可以使用的提问格式包括：
1. xxx技术的最新发展是什么？
2. xxx框架的官方文档在哪里？
3. xxx库的GitHub仓库地址是什么？
4. xxx问题的解决方案有哪些？
5. xxx概念的详细解释是什么？
""",
        "description": "网页搜索",
    },
    "FindRelatedFiles": {
        "append": False,
        "template": f"""
请使用工具在当前目录下查找与以下功能相关的文件：
""",
    },
    "Dev": {
        "append": False,
        "template": f"""
请调用create_code_agent开发以下需求：
""",
    },
    "Fix": {
        "append": False,
        "template": f"""
请修复以下问题：
""",
    },
    "Check": {
        "append": True,
        "template": f"""
请使用静态检查工具检查当前代码，必须严格遵守工具调用格式。

检查要求：
1. 如果发现致命错误，必须立即修复
2. 如果发现警告或风格问题，应询问用户是否需要修复
3. 检查完成后应报告结果
4. 确保使用项目对应的静态检查工具
""",
        "description": "执行静态代码检查",
    },
}
