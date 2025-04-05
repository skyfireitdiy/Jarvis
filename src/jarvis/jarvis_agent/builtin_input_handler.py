import re
from typing import Any, Tuple
from jarvis.jarvis_utils.utils import ot, ct



def builtin_input_handler(user_input: str, agent: Any) -> Tuple[str, bool]:
    """
    处理内置的特殊输入标记，并追加相应的提示词

    参数：
        user_input: 用户输入
        agent: 代理对象

    返回：
        Tuple[str, bool]: 处理后的输入和是否需要进一步处理
    """
    # 查找特殊标记
    special_tags = re.findall(r"'<([^>]+)>'", user_input)

    if not special_tags:
        return user_input, False

    # 使用集合去重
    processed_tags = set()
    # 处理每个标记
    for tag in special_tags:
        if tag in processed_tags:
            continue
        processed_tags.add(tag)

        if tag == "CodeBase":
            user_input = user_input.replace(f"'<{tag}>'", "")
            user_input += f"""
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
"""
        elif tag == "Web":
            user_input = user_input.replace(f"'<{tag}>'", "")
            agent.set_addon_prompt(f"""
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
""")
        elif tag == "Summary":
            user_input = user_input.replace(f"'<{tag}>'", "")
            agent._summarize_and_clear_history()
            if not user_input.strip():
                return "", True
        elif tag == "Clear":
            user_input = user_input.replace(f"'<{tag}>'", "")
            agent.clear()
            if not user_input.strip():
                return "", True
        elif tag == "Methodology":
            user_input = user_input.replace(f"'<{tag}>'", "")
            agent.set_addon_prompt(f"""
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
""")
        elif tag == "Plan":
            user_input = user_input.replace(f"'<{tag}>'", "")
            agent.set_addon_prompt(f"""
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
""")
        # 移除对未知标记的警告输出

    return user_input, False
