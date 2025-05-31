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
        "description": "网页搜索"
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
    },
    "ToolHelp": {
        "append": False,
        "template": """
<tool_system_guide>
<introduction>
# 🛠️ 工具使用系统
您正在使用一个需要精确格式和严格规则的工具执行系统。
</introduction>

<format>
# 📋 工具调用格式
{ot("TOOL_CALL")}
want: 想要从执行结果中获取到的信息，如果工具输出内容过长，会根据此字段尝试提取有效信息
name: 工具名称
arguments:
  param1: 值1
  param2: 值2
{ct("TOOL_CALL")}
</format>

<rules>
# ❗ 关键规则
<rule>
### 1. 每次只使用一个工具
- 一次只执行一个工具
- 等待结果后再进行下一步
</rule>

<rule>
### 2. 严格遵守格式
- 完全按照上述格式
- 使用正确的YAML格式，2个空格作为缩进
- 包含所有必需参数
</rule>

<rule>
### 3. 结果处理
- 等待执行结果
- 不要假设结果
- 不要创建虚假响应
- 不要想象对话
</rule>

<rule>
### 4. 信息管理
- 如果信息不足，询问用户
- 跳过不必要的步骤
- 如果卡住，请求指导
- 不要在没有完整信息的情况下继续
</rule>
</rules>

<string_format>
# 📝 字符串参数格式
始终使用 |2 语法表示字符串参数，防止多行字符串行首空格引起歧义：

{ot("TOOL_CALL")}
want: 当前的git状态，期望获取xxx的提交记录
name: execute_script
arguments:
  interpreter: bash
  script_cotent: |2
    git status --porcelain
{ct("TOOL_CALL")}
</string_format>

<best_practices>
# 💡 最佳实践
- 准备好后立即开始执行
- 无需请求许可即可开始
- 使用正确的字符串格式
- 监控进度并调整
- 遇到困难时请求帮助
</best_practices>

<common_errors>
# ⚠️ 常见错误
- 同时调用多个工具
- 字符串参数缺少 |2
- 假设工具结果
- 创建虚构对话
- 在没有所需信息的情况下继续
- yaml 格式错误
</common_errors>
</tool_system_guide>
""",
        "description": "工具使用系统"
    }
}