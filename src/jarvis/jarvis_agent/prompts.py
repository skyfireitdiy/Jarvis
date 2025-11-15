# -*- coding: utf-8 -*-
from jarvis.jarvis_utils.tag import ct, ot

DEFAULT_SUMMARY_PROMPT = """<report>
请生成任务执行的简明总结报告，包括：

<content>
1. 任务目标：任务重述
2. 执行结果：成功/失败
3. 关键信息：执行过程中提取的重要信息
4. 重要发现：任何值得注意的发现
5. 后续建议：如果有的话
</content>

<format>
请使用简洁的要点描述，突出重要信息。
</format>
</report>
"""

SUMMARY_REQUEST_PROMPT = """<summary_request>
<objective>
请对当前对话历史进行简明扼要的总结，提取关键信息和重要决策点。这个总结将作为上下文继续任务，因此需要保留对后续对话至关重要的内容。
</objective>

<guidelines>
1. 提取关键信息：任务目标、已确定的事实、重要决策、达成的共识
2. 保留技术细节：命令、代码片段、文件路径、配置设置等技术细节
3. 记录任务进展：已完成的步骤、当前所处阶段、待解决的问题
4. 包含用户偏好：用户表达的明确偏好、限制条件或特殊要求
5. 省略冗余内容：问候语、重复信息、不相关的讨论
</guidelines>

<format>
- 使用简洁、客观的语言
- 按时间顺序或主题组织信息
- 使用要点列表增强可读性
- 总结应控制在500词以内
</format>
</summary_request>
"""


def get_task_analysis_prompt(
    has_save_memory: bool = False,
    has_generate_new_tool: bool = False
) -> str:
    """根据配置返回任务分析提示词
    
    参数:
        has_save_memory: 是否有 save_memory 工具（工具可用性）
        has_generate_new_tool: 是否有 generate_new_tool 工具
    """
    # 第一步：记忆保存部分
    if not has_save_memory:
        # 如果没有 save_memory 工具，说明无法保存记忆
        memory_step = """第一步：记忆值得保存的信息
1. 识别任务中的关键信息和知识点
2. 评估是否有值得保存的项目长期记忆或全局长期记忆
3. 注意：当前环境不支持 save_memory 工具，无法保存记忆。请直接说明识别到的关键信息即可。"""
    else:
        # 有 save_memory 工具
        memory_step = """第一步：记忆值得保存的信息
1. 识别任务中的关键信息和知识点
2. 评估是否有值得保存的项目长期记忆或全局长期记忆
3. 如果有价值，使用 save_memory 工具保存有价值的信息：
   - project_long_term: 保存与当前项目相关的长期信息（如项目配置、架构决策、开发规范等）
   - global_long_term: 保存通用的信息、用户偏好、知识或方法（如技术知识、最佳实践、用户习惯等）"""
    
    # 第二步：工具/方法论分析部分
    if has_generate_new_tool:
        solution_step = """第二步：分析任务解决方案
1. 检查现有工具或方法论是否已经可以完成该任务，如果可以，直接说明即可，无需生成新内容
2. 如果现有工具/方法论不足，评估当前任务是否可以通过编写新工具来自动化解决
3. 如果可以通过工具解决，请使用 generate_new_tool 工具创建新工具：
   - 使用 generate_new_tool 工具，传入 tool_name 和 tool_code 参数
   - tool_code 应包含完整的工具类定义，遵循工具代码要求
4. 如果无法通过编写通用工具完成，评估当前的执行流程是否可以总结为通用方法论
5. 如果以上都不可行，给出详细理由"""
    else:
        solution_step = """第二步：分析任务解决方案
1. 检查现有工具或方法论是否已经可以完成该任务，如果可以，直接说明即可，无需生成新内容
2. 如果现有工具/方法论不足，评估当前任务是否可以通过编写新工具来自动化解决
3. 如果可以通过工具解决，请设计并提供工具代码（注意：当前环境不支持 generate_new_tool 工具，需要手动创建工具文件）
4. 如果无法通过编写通用工具完成，评估当前的执行流程是否可以总结为通用方法论
5. 如果以上都不可行，给出详细理由"""
    
    # 输出要求部分
    if has_generate_new_tool:
        output_requirements = f"""<output_requirements>
根据分析结果，输出以下三种情况之一：
1. 如果现有工具/方法论可以解决，直接输出说明：
已有工具/方法论可以解决该问题，无需创建新内容。
可用的工具/方法论：[列出工具名称或方法论名称]
使用方法：[简要说明如何使用]
2. 工具创建（如果需要创建新工具）:
{ot("TOOL_CALL")}
{{
  "want": "创建新工具来解决XXX问题",
  "name": "generate_new_tool",
  "arguments": {{
    "tool_name": "工具名称",
    "tool_code": `# -*- coding: utf-8 -*-
from typing import Dict, Any
from jarvis.jarvis_utils.output import PrettyOutput, OutputType

class 工具名称:
    name = "工具名称"
    description = "Tool description"
    parameters = {{
        "type": "object",
        "properties": {{
            # 参数定义
        }},
        "required": []
    }}
    @staticmethod
    def check() -> bool:
        return True
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # 使用PrettyOutput显示执行过程
            PrettyOutput.print("开始执行操作...", OutputType.INFO)
            # 实现逻辑
            # ...
            PrettyOutput.print("操作已完成", OutputType.SUCCESS)
            return {{
                "success": True,
                "stdout": "结果输出",
                "stderr": ""
            }}
        except Exception as e:
            PrettyOutput.print(f"操作失败: {{str(e)}}", OutputType.ERROR)
            return {{
                "success": False,
                "stdout": "",
                "stderr": f"操作失败: {{str(e)}}"
            }}`
  }}
}}
{ct("TOOL_CALL")}

注意：tool_code 参数推荐使用 ||| 分隔符包裹多行代码，直接换行无需转义，支持保留缩进。
3. 方法论创建（如果需要创建新方法论）:
{ot("TOOL_CALL")}
{{
  "want": "添加/更新xxxx的方法论",
  "name": "methodology",
  "arguments": {{
    "operation": "add/update",
    "problem_type": "方法论类型，不要过于细节，也不要过于泛化",
    "content": |||
方法论内容
可以包含多行内容
推荐使用 ||| 分隔符包裹多行字符串，直接换行无需转义，支持保留缩进
包含"双引号"和'单引号'都无需转义
    |||
  }}
}}
{ct("TOOL_CALL")}

注意：如果 content 参数包含多行内容，推荐使用 ||| 分隔符包裹，直接换行无需转义，支持保留缩进。
如果以上三种情况都不适用，则直接输出原因分析，不要使用工具调用格式。
</output_requirements>"""
    else:
        output_requirements = f"""<output_requirements>
根据分析结果，输出以下三种情况之一：
1. 如果现有工具/方法论可以解决，直接输出说明：
已有工具/方法论可以解决该问题，无需创建新内容。
可用的工具/方法论：[列出工具名称或方法论名称]
使用方法：[简要说明如何使用]
2. 工具创建（如果需要创建新工具）:
注意：当前环境不支持 generate_new_tool 工具。如果需要创建新工具，请提供完整的工具代码和说明，用户需要手动创建工具文件。
3. 方法论创建（如果需要创建新方法论）:
{ot("TOOL_CALL")}
{{
  "want": "添加/更新xxxx的方法论",
  "name": "methodology",
  "arguments": {{
    "operation": "add/update",
    "problem_type": "方法论类型，不要过于细节，也不要过于泛化",
    "content": |||
方法论内容
可以包含多行内容
推荐使用 ||| 分隔符包裹多行字符串，直接换行无需转义，支持保留缩进
包含"双引号"和'单引号'都无需转义
    |||
  }}
}}
{ct("TOOL_CALL")}

注意：如果 content 参数包含多行内容，推荐使用 ||| 分隔符包裹，直接换行无需转义，支持保留缩进。
如果以上三种情况都不适用，则直接输出原因分析，不要使用工具调用格式。
</output_requirements>"""
    
    return f"""<task_analysis>
<request>
当前任务已结束，请按以下步骤分析该任务：

{memory_step}

{solution_step}

请根据分析结果采取相应行动。

重要提示：每次只能执行一个操作！
- 如果有记忆需要保存，可以调用一次 save_memory 批量保存多条记忆
- 保存完所有记忆后，再进行工具/方法论的创建或说明
- 不要在一次响应中同时调用多个工具（如同时保存记忆和创建工具/方法论）
</request>
<evaluation_criteria>
现有资源评估: 检查现有工具/方法论/组合使用是否可解决问题
工具评估: 通用性、自动化、可靠性、简单性
方法论评估: 聚焦通用可重复流程，纳入用户反馈，面向未来复用
</evaluation_criteria>
<tool_requirements>
工具代码要求:
1. 工具类名与工具名称一致，包含name、description、parameters属性，实现execute方法
2. 参数定义遵循JSON Schema，工具调用使用Jsonnet格式（支持 ||| 分隔符多行字符串、尾随逗号）
3. 使用PrettyOutput显示执行过程，返回{{success, stdout, stderr}}结构化结果
4. 妥善处理异常，失败时清理资源。如需调用大模型，创建独立实例避免干扰主流程
</tool_requirements>
<methodology_requirements>
方法论格式: 问题重述、可复用解决流程（步骤化+工具）、注意事项、可选步骤
</methodology_requirements>
{output_requirements}
</task_analysis>"""


# 为了向后兼容，保留原来的常量（使用默认参数，假设有 save_memory 工具）
TASK_ANALYSIS_PROMPT = get_task_analysis_prompt(has_save_memory=True)
