"""内置替换映射表模块。

该模块定义了Jarvis系统内置的默认替换映射表。
"""

BUILTIN_REPLACE_MAP = {
    # 内置默认替换规则
    # 格式: {"原始文本": "替换文本"}
    "example": "demo",
    "sample": "template",
    "CodeBase": """
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
    "Web": """
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
    "Methodology": """
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
    "Plan": """
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
"""
}
