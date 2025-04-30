"""内置替换映射表模块。

该模块定义了Jarvis系统内置的默认替换映射表。
格式: {"标记名": {"template": "替换模板", "description": "描述信息"}}
"""

from jarvis.jarvis_utils.tag import ot, ct

BUILTIN_REPLACE_MAP = {
    "CodeBase": {
        "append": True,
        "template": f"""
请使用ask_codebase工具查询代码库，必须严格遵守以下工具调用格式：

{ot("TOOL_CALL")}
want: 想要从执行结果中获取到的信息
name: ask_codebase
arguments:
    question: "与xxx功能相关的文件有哪些？"
{ct("TOOL_CALL")}

可以使用的提问格式包括：
1. 与xxx功能相关的文件有哪些？
2. 要实现xxx，应该要修改哪些文件？
3. xxx功能是怎么实现的？
4. xxx模块的入口函数是什么？
5. xxx功能的测试用例在哪里？
""",
        "description": "查询代码库"
    },
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
        "description": "网页搜索"
    },
    "Methodology": {
        "append": True,
        "template": f"""
请使用find_methodology工具查找相关方法论，必须严格遵守以下工具调用格式：

{ot("TOOL_CALL")}
want: 想要从执行结果中获取到的信息
name: find_methodology
arguments:
    query: "关于xxx的方法论有哪些？"
{ct("TOOL_CALL")}

可以使用的提问格式包括：
1. 关于xxx的方法论有哪些？
2. 如何解决xxx问题？
3. xxx的最佳实践是什么？
4. 处理xxx的标准流程是什么？
5. 实现xxx的参考方案有哪些？
""",
        "description": "查找相关方法论"
    },
    "Plan": {
        "append": True,
        "template": f"""
请使用code_plan工具生成代码修改计划，必须严格遵守以下工具调用格式：

{ot("TOOL_CALL")}
want: 想要从执行结果中获取到的信息
name: code_plan
arguments:
    requirement: "需要实现用户登录功能，包括用户名密码验证和JWT生成"
{ct("TOOL_CALL")}

请提供详细的需求描述和完整上下文信息：

必须包含的上下文信息：
1. 当前会话状态 - 当前正在处理的任务和进度
2. 用户历史请求 - 与本任务相关的历史请求
3. 系统状态 - 相关的系统配置和环境状态
4. 已确定的相关文件 - 已经分析出的需要修改的文件列表

示例：
1. 需要实现用户登录功能，包括用户名密码验证和JWT生成
2. 重构订单处理模块以提高性能
3. 优化数据库查询性能，减少响应时间
4. 添加支付网关集成功能
5. 修改用户权限管理系统

code_plan工具将：
1. 分析项目结构确定相关文件
2. 理解需求后制定详细修改步骤
3. 按功能模块分组修改内容
4. 评估修改影响范围
5. 生成可执行的开发计划
""",
        "description": "生成代码修改计划"
    },
    "FindRelatedFiles": {
        "append": False,
        "template": f"""
请使用工具在当前目录下查找与以下功能相关的文件：
"""
    },
    "FindMethodology": {
        "append": False,
        "template": f"""
请使用find_methodology工具查找相关方法论：
"""
    },
    "Dev": {
        "append": False,
        "template": f"""
请调用create_code_agent开发以下需求：
"""
    },
    "Fix": {
        "append": False,
        "template": f"""
请修复以下问题：
"""
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
        "description": "执行静态代码检查"
    }
}