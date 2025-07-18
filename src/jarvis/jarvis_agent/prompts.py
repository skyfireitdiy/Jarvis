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


TASK_ANALYSIS_PROMPT = f"""<task_analysis>
<request>
当前任务已结束，请分析该任务的解决方案：
1. 首先检查现有工具或方法论是否已经可以完成该任务，如果可以，直接说明即可，无需生成新内容
2. 如果现有工具/方法论不足，评估当前任务是否可以通过编写新工具来自动化解决
3. 如果可以通过工具解决，请设计并提供工具代码
4. 如果无法通过编写通用工具完成，评估当前的执行流程是否可以总结为通用方法论
5. 如果以上都不可行，给出详细理由
请根据分析结果采取相应行动：说明现有工具/方法论、创建新工具、生成新方法论或说明原因。
</request>
<evaluation_criteria>
现有资源评估:
1. 现有工具 - 检查系统中是否已有可以完成该任务的工具
2. 现有方法论 - 检查是否已有适用于该任务的方法论
3. 组合使用 - 评估现有工具和方法论组合使用是否可以解决问题
工具评估标准:
1. 通用性 - 该工具是否可以解决一类问题，而不仅仅是当前特定问题
2. 自动化 - 该工具是否可以减少人工干预，提高效率
3. 可靠性 - 该工具是否可以在不同场景下稳定工作
4. 简单性 - 该工具是否易于使用，参数设计是否合理
方法论评估标准:
1. 方法论应聚焦于通用且可重复的解决方案流程
2. 方法论应该具备足够的通用性，可应用于同类问题
3. 特别注意用户在执行过程中提供的修正、反馈和改进建议
4. 如果用户明确指出了某个解决步骤的优化方向，这应该被纳入方法论
5. 方法论要严格按照实际的执行流程来总结，不要遗漏或增加任何步骤
</evaluation_criteria>
<tool_requirements>
工具代码要求:
1. 工具类名应与工具名称保持一致
2. 必须包含name、description、parameters属性
3. 必须实现execute方法处理输入参数
4. 可选实现check方法验证环境
5. 工具描述应详细说明用途、适用场景和使用示例
6. 参数定义应遵循JSON Schema格式
7. 不要包含特定任务的细节，保持通用性
工具设计关键点:
1. **使用PrettyOutput打印执行过程**：强烈建议在工具中使用PrettyOutput显示执行过程，
   这样用户可以了解工具在做什么，提升用户体验。示例：
   ```python
   from jarvis.jarvis_utils.output import PrettyOutput, OutputType
   # 执行中打印信息
   PrettyOutput.print("正在处理数据...", OutputType.INFO)
   # 成功信息
   PrettyOutput.print("操作成功完成", OutputType.SUCCESS)
   # 警告信息
   PrettyOutput.print("发现潜在问题", OutputType.WARNING)
   # 错误信息
   PrettyOutput.print("操作失败", OutputType.ERROR)
   ```
2. **结构化返回结果**：工具应该始终返回结构化的结果字典，包含以下字段：
   - success: 布尔值，表示操作是否成功
   - stdout: 字符串，包含工具的主要输出内容
   - stderr: 字符串，包含错误信息（如果有）
3. **异常处理**：工具应该妥善处理可能发生的异常，并在失败时清理已创建的资源
   ```python
   try:
       # 执行逻辑
       return {{
           "success": True,
           "stdout": "成功结果",
           "stderr": ""
       }}
   except Exception as e:
       PrettyOutput.print(f"操作失败: {{str(e)}}", OutputType.ERROR)
       # 清理资源（如果有创建）
       return {{
           "success": False,
           "stdout": "",
           "stderr": f"操作失败: {{str(e)}}"
       }}
   ```
</tool_requirements>
<methodology_requirements>
方法论格式要求:
1. 问题重述: 简明扼要的问题归纳，不含特定细节
2. 最优解决方案: 经过用户验证的、最终有效的解决方案（将每个步骤要使用的工具也列举出来）
3. 注意事项: 执行中可能遇到的常见问题和注意点，尤其是用户指出的问题
4. 可选步骤: 对于有多种解决路径的问题，标注出可选步骤和适用场景
</methodology_requirements>
<output_requirements>
根据分析结果，输出以下三种情况之一：
1. 如果现有工具/方法论可以解决，直接输出说明：
已有工具/方法论可以解决该问题，无需创建新内容。
可用的工具/方法论：[列出工具名称或方法论名称]
使用方法：[简要说明如何使用]
2. 工具创建（如果需要创建新工具）:
{ot("TOOL_CALL")}
want: 创建新工具来解决XXX问题
name: generate_new_tool
arguments:
  tool_name: 工具名称
  tool_code: |2
    # -*- coding: utf-8 -*-
    from typing import Dict, Any
    from jarvis.jarvis_utils.output import PrettyOutput, OutputType
    class 工具名称:
        name = "工具名称"
        description = "Tool for text transformation"
                Tool description
        适用场景：1. 格式化文本; 2. 处理标题; 3. 标准化输出
        \"\"\"
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
        }}
{ct("TOOL_CALL")}
3. 方法论创建（如果需要创建新方法论）:
{ot("TOOL_CALL")}
want: 添加/更新xxxx的方法论
name: methodology
arguments:
  operation: add/update
  problem_type: 方法论类型，不要过于细节，也不要过于泛化
  content: |2
    方法论内容
{ct("TOOL_CALL")}
如果以上三种情况都不适用，则直接输出原因分析，不要使用工具调用格式。
</output_requirements>
</task_analysis>"""
