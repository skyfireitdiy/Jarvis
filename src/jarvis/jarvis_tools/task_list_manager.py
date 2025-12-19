"""任务列表管理工具。

该工具允许 LLM 管理任务列表，包括创建任务列表、添加任务、更新任务状态等。
"""

import json


from jarvis.jarvis_utils.output import PrettyOutput

# -*- coding: utf-8 -*-
from typing import Dict, List, Optional, Any

from jarvis.jarvis_agent.task_list import TaskStatus
from jarvis.jarvis_utils.config import get_max_input_token_count
from jarvis.jarvis_utils.globals import get_global_model_group
from jarvis.jarvis_utils.tag import ot, ct


class DependencyValidationError(Exception):
    """依赖验证错误的基类"""

    pass


class DependencyNotFoundError(DependencyValidationError):
    """依赖任务不存在错误"""

    pass


class DependencyNotCompletedError(DependencyValidationError):
    """依赖任务未完成错误"""

    pass


class DependencyFailedError(DependencyValidationError):
    """依赖任务失败错误"""

    pass


# 任务输出长度限制常量
DEFAULT_MAX_TASK_OUTPUT_LENGTH = 10000  # 默认最大任务输出长度（字符数）


class task_list_manager:
    """任务列表管理工具，供 LLM 调用"""

    name = "task_list_manager"

    def _get_max_output_length(self, agent: Any = None) -> int:
        """获取基于剩余token数量的最大输出长度（字符数）

        参数:
            agent: Agent实例，用于获取模型和剩余token数量

        返回:
            int: 允许的最大字符数（基于剩余token计算，保留安全余量）
        """
        try:
            # 优先使用剩余token数量
            if agent and hasattr(agent, "model"):
                try:
                    remaining_tokens = agent.model.get_remaining_token_count()
                    # 使用剩余token的2/3作为限制，保留1/3作为安全余量
                    # 粗略估算：1个token约等于4个字符（中文可能更少，但保守估计）
                    limit_tokens = int(remaining_tokens * 2 / 3)
                    # 转换为字符数（保守估计：1 token = 4 字符）
                    limit_chars = limit_tokens * 4
                    # 确保至少返回一个合理的值
                    if limit_chars > 0:
                        return limit_chars
                except Exception:
                    pass

            # 回退方案：使用输入窗口的2/3
            # 使用全局模型组（不再从 agent 继承）
            model_group = get_global_model_group()

            max_input_tokens = get_max_input_token_count(model_group)
            # 计算2/3限制的token数，然后转换为字符数
            limit_tokens = int(max_input_tokens * 2 / 3)
            limit_chars = limit_tokens * 4
            return limit_chars
        except Exception:
            # 如果获取失败，使用默认值
            return DEFAULT_MAX_TASK_OUTPUT_LENGTH

    def _get_truncate_lengths(self, max_length: int) -> tuple[int, int]:
        """根据最大长度计算截断时的前缀和后缀长度

        参数:
            max_length: 最大长度（字符数）

        返回:
            tuple[int, int]: (前缀长度, 后缀长度)
        """
        # 前缀占80%，后缀占20%
        prefix_length = int(max_length * 0.8)
        suffix_length = int(max_length * 0.2)
        return prefix_length, suffix_length

    def _get_task_list_id(self, agent: Any) -> Optional[str]:
        """从 Agent 的 user_data 中获取 task_list_id

        参数:
            agent: Agent 实例

        返回:
            Optional[str]: task_list_id，如果不存在则返回 None
        """
        if not agent:
            return None
        try:
            result = agent.get_user_data("__task_list_id__")
            return str(result) if result is not None else None
        except Exception:
            return None

    def _set_task_list_id(self, agent: Any, task_list_id: str) -> None:
        """将 task_list_id 保存到 Agent 的 user_data 中

        参数:
            agent: Agent 实例
            task_list_id: 任务列表 ID
        """
        if not agent:
            return
        try:
            agent.set_user_data("__task_list_id__", task_list_id)
        except Exception:
            pass

    def _determine_agent_type(
        self, agent: Any, task: Any, task_content: str, background: str
    ) -> bool:
        """直接根据agent实例判断是否为代码相关任务

        参数:
            agent: 当前执行的agent实例
            task: 任务对象
            task_content: 任务内容
            background: 背景信息

        返回:
            bool: True 表示代码相关任务，False 表示通用任务
        """
        try:
            # 直接根据agent实例类型判断
            from jarvis.jarvis_code_agent.code_agent import CodeAgent

            return isinstance(agent, CodeAgent)
        except ImportError:
            # 如果导入失败，回退到通用Agent
            return False

    def _create_verification_agent(
        self, task: Any, parent_agent: Any, verification_iteration: int = 1
    ) -> Any:
        """创建验证 Agent，只能使用 read_code 和 execute_script 工具

        参数:
            task: 任务对象
            parent_agent: 父 Agent 实例
            verification_iteration: 验证迭代次数

        返回:
            Agent: 验证 Agent 实例
        """
        from jarvis.jarvis_agent import Agent
        from jarvis.jarvis_utils.globals import get_global_model_group

        # 构建验证任务的系统提示词
        verification_system_prompt = f"""你是一个任务验证专家。你的任务是验证任务是否真正完成，仅验证任务预期输出和产物。

**任务信息：**
- 任务名称：{task.task_name}
- 任务描述：{task.task_desc}
- 预期输出（建议为分条列出的结构化条目，例如 1)、2)、3) 或 markdown 列表 - item）：{task.expected_output}

**验证要求：**
1. 将预期输出解析为一组**逐条的预期结果条目**（例如按换行、编号 1)、2)、3) 或 markdown 列表 - item 进行切分）
2. 对**每一条预期结果条目**分别进行验证：检查对应的代码、文件或其他产物是否真实存在且满足该条要求
3. 使用 read_code 工具验证任务产生的代码或文件是否符合对应条目的要求
4. 仅检查任务明确要求的产物是否存在且正确
5. 不要验证与任务预期输出无关的项目（如整体项目编译、无关测试等）
6. 关注任务描述中明确提到的具体交付物

**验证标准：**
- 每一条预期输出条目是否都已实际生成对应产物
- 每一条条目对应的产物是否符合任务描述中的具体要求
- 不验证无关的编译状态、测试覆盖率或代码风格

**重要限制（强制性）：**
- 只能使用 read_code 和 execute_script 工具进行验证
- 必须基于实际验证结果，不能推测或假设
- 仅验证任务预期输出和直接相关的产物
- 如果验证通过，直接输出 {ot("!!!COMPLETE!!!")}，不要输出其他任何内容。
- **禁止实际修复行为**：严禁执行任何代码修改、文件操作或配置更改
- **允许修复建议**：可以详细分析问题原因并提供具体的修复建议和指导
- **明确区分建议与执行**：可以说明"应该如何修正"，但必须强调这只是建议
"""

        # 构建验证任务的总结提示词（结构化格式要求）
        verification_summary_prompt = f"""请以结构化的格式总结任务验证结果。必须严格按照以下格式输出：

## 任务验证结果

**任务名称**：{task.task_name}

**验证状态**：[PASSED/FAILED]

**最终结论**：[VERIFICATION_PASSED 或 VERIFICATION_FAILED]

**逐条验证结果**：
- 逐条列出每一个预期输出条目及其验证结果，格式示例：
  - 条目1：[PASSED/FAILED] 说明...
  - 条目2：[PASSED/FAILED] 说明...
  - 条目3：[PASSED/FAILED] 说明...

**说明**：
- 如果验证通过：输出 "所有预期输出条目均已验证完成"
- 如果验证失败：详细说明不通过的原因，包括：
  * 哪些预期输出条目未找到或不完整
  * 实际输出与各条目预期不符的具体差异
  * 需要补充或修正的部分

**重要**：
- 必须严格按照上述格式输出
- 验证状态必须是 PASSED 或 FAILED
- 最终结论必须是 "VERIFICATION_PASSED" 或 "VERIFICATION_FAILED"
- **允许修复建议**：可以详细分析问题并提供具体的修复指导
- **禁止实际修复**：严禁执行任何代码修改或文件操作
"""

        # 获取父 Agent 的模型组
        # 优先使用父 Agent 的 model_group，因为全局模型组可能还没有被正确设置（时序问题）
        model_group = None
        try:
            if parent_agent is not None:
                # 优先从父 Agent 获取 model_group
                model_group = getattr(parent_agent, "model_group", None)
        except Exception:
            pass

        # 如果父 Agent 没有 model_group，才使用全局模型组
        if model_group is None:
            model_group = get_global_model_group()

        verification_agent = Agent(
            system_prompt=verification_system_prompt,
            name=f"verification_agent_{task.task_id}_{verification_iteration}",
            description="Task verification agent",
            model_group=model_group,
            summary_prompt=verification_summary_prompt,
            auto_complete=True,
            need_summary=True,
            use_tools=[
                "read_code",
                "execute_script",
                "save_memory",
                "retrieve_memory",
                "clear_memory",
                "methodology",
            ],
            non_interactive=True,
            use_methodology=True,
            use_analysis=True,
        )

        return verification_agent

    def _build_task_content(self, task: Any, additional_info: str = "") -> str:
        """构建任务内容

        参数:
            task: 任务对象
            additional_info: 附加信息

        返回:
            str: 格式化的任务内容
        """
        task_desc = task.task_desc
        if additional_info and str(additional_info).strip():
            separator = "\n" + "=" * 50 + "\n"
            task_desc = f"{task.task_desc}{separator}附加信息:\n{additional_info}"

        return f"""任务名称: {task.task_name}

任务描述:
{task_desc}

预期输出:
{task.expected_output}"""

    def _build_task_background(
        self,
        task_list_manager: Any,
        task_list_id: str,
        task: Any,
        agent_id: str,
        is_main_agent: bool,
        include_completed_summary: bool = True,
    ) -> str:
        """构建任务背景信息

        参数:
            task_list_manager: 任务列表管理器
            task_list_id: 任务列表ID
            task: 任务对象
            agent_id: Agent ID
            is_main_agent: 是否为主Agent
            include_completed_summary: 是否包含其他已完成任务的摘要

        返回:
            str: 格式化的背景信息
        """
        background_parts = []

        # 1. 获取任务列表的 main_goal 作为全局上下文
        task_list = task_list_manager.get_task_list(task_list_id)
        if task_list:
            background_parts.append(f"全局目标: {task_list.main_goal}")

        # 2. 获取依赖任务的输出作为背景信息
        if task.dependencies:
            dep_outputs = []
            for dep_id in task.dependencies:
                dep_task, dep_success, _ = task_list_manager.get_task_detail(
                    task_list_id=task_list_id,
                    task_id=dep_id,
                    agent_id=agent_id,
                    is_main_agent=is_main_agent,
                )
                if dep_success and dep_task:
                    if dep_task.actual_output:
                        dep_outputs.append(
                            f"依赖任务 [{dep_task.task_name}] 的输出:\n{dep_task.actual_output}"
                        )
                    elif dep_task.status == TaskStatus.COMPLETED:
                        # 即使没有输出，也说明依赖任务已完成
                        dep_outputs.append(
                            f"依赖任务 [{dep_task.task_name}] 已完成（状态: {dep_task.status.value}）"
                        )

            if dep_outputs:
                background_parts.append("依赖任务信息:\n" + "\n\n".join(dep_outputs))

        # 3. 获取其他已完成任务的摘要信息（可选）
        if include_completed_summary and task_list:
            completed_tasks = [
                t
                for t in task_list.tasks.values()
                if t.status == TaskStatus.COMPLETED
                and t.task_id != task.task_id
                and t.task_id not in (task.dependencies or [])
            ]
            if completed_tasks:
                # 只包含前3个已完成任务的简要信息，避免上下文过长
                completed_summary = []
                for completed_task in completed_tasks[:3]:
                    summary = (
                        f"- [{completed_task.task_name}]: {completed_task.task_desc}"
                    )
                    if completed_task.actual_output:
                        # 只取输出的前200字符作为摘要
                        output_preview = completed_task.actual_output[:200]
                        if len(completed_task.actual_output) > 200:
                            output_preview += "..."
                        summary += f"\n  输出摘要: {output_preview}"
                    completed_summary.append(summary)

                if completed_summary:
                    background_parts.append(
                        "其他已完成任务（参考信息）:\n" + "\n".join(completed_summary)
                    )

        return "\n\n".join(background_parts) if background_parts else ""

    def _verify_task_completion(
        self,
        task: Any,
        task_content: str,
        background: str,
        parent_agent: Any,
        verification_iteration: int = 1,
    ) -> tuple[bool, str]:
        """验证任务是否真正完成

        参数:
            task: 任务对象
            task_content: 任务内容
            background: 背景信息
            parent_agent: 父 Agent 实例
            verification_iteration: 验证迭代次数

        返回:
            tuple[bool, str]: (是否完成, 验证结果或失败原因)
        """
        try:
            from jarvis.jarvis_utils.output import PrettyOutput

            # 创建验证 Agent
            verification_agent = self._create_verification_agent(
                task, parent_agent, verification_iteration
            )

            # 构建验证任务
            verification_task = f"""请验证以下任务是否真正完成，并且**对预期输出中的每一条条目分别进行验证**：

{task_content}

背景信息：
{background}

请使用 read_code 和 execute_script 工具进行验证，重点检查：
1. 将预期输出解析为多条具体条目（按换行 / 编号 1)、2)、3) / markdown 列表 - item 等方式拆分）
2. 对每一条预期输出条目，检查是否有对应的代码、文件或其他实际产物支撑
3. 如果某条条目无法找到对应产物、产物不完整或与描述不符，需单独标记为 FAILED，并说明原因
4. 仅在**所有预期输出条目**都验证通过时，才可以整体判定为 PASSED

如果存在编译错误、运行时错误、测试失败，或任意一条预期输出条目未满足要求，必须明确标记整体为未完成，并详细说明原因。
"""

            PrettyOutput.auto_print(
                f"🔍 开始验证任务 [{task.task_name}] (第 {verification_iteration} 次验证)..."
            )

            # 执行验证
            verification_result = verification_agent.run(verification_task)

            # 解析验证结果（从结构化的 summary 中提取）
            if verification_result:
                verification_result_str = str(verification_result)

                # 尝试从结构化格式中提取验证状态
                verification_status = None
                final_conclusion = None

                # 查找验证状态
                import re

                status_match = re.search(
                    r"\*\*验证状态\*\*：\s*\[(PASSED|FAILED)\]", verification_result_str
                )
                if status_match:
                    verification_status = status_match.group(1)

                # 查找最终结论
                conclusion_match = re.search(
                    r"\*\*最终结论\*\*：\s*\[(VERIFICATION_PASSED|VERIFICATION_FAILED)\]",
                    verification_result_str,
                )
                if conclusion_match:
                    final_conclusion = conclusion_match.group(1)

                # 判断验证是否通过
                is_passed = False
                if (
                    verification_status == "PASSED"
                    or final_conclusion == "VERIFICATION_PASSED"
                ):
                    is_passed = True
                elif (
                    verification_status == "FAILED"
                    or final_conclusion == "VERIFICATION_FAILED"
                ):
                    is_passed = False
                elif "VERIFICATION_PASSED" in verification_result_str.upper():
                    is_passed = True
                elif "VERIFICATION_FAILED" in verification_result_str.upper():
                    is_passed = False
                else:
                    # 如果无法从结构化格式中提取，尝试查找关键词
                    if (
                        "验证通过" in verification_result_str
                        or "所有验证通过" in verification_result_str
                    ):
                        is_passed = True
                    elif (
                        "验证失败" in verification_result_str
                        or "验证未通过" in verification_result_str
                    ):
                        is_passed = False
                    else:
                        # 默认认为未通过
                        is_passed = False

                if is_passed:
                    PrettyOutput.auto_print(f"✅ 任务 [{task.task_name}] 验证通过")
                    return True, verification_result_str
                else:
                    # 直接使用完整的验证结果作为失败原因
                    PrettyOutput.auto_print(
                        f"❌ 任务 [{task.task_name}] 验证未通过：{verification_result_str[:200]}..."
                    )
                    return False, verification_result_str
            else:
                PrettyOutput.auto_print(
                    f"⚠️ 任务 [{task.task_name}] 验证无结果，默认认为未完成"
                )
                return False, "验证无结果"

        except Exception as e:
            PrettyOutput.auto_print(
                f"⚠️ 验证任务 [{task.task_name}] 时发生异常: {str(e)}"
            )
            return False, f"验证异常: {str(e)}"

    def _print_task_list_status(
        self, task_list_manager: Any, task_list_id: Optional[str] = None
    ) -> None:
        """打印任务列表状态

        参数:
            task_list_manager: 任务列表管理器实例
            task_list_id: 任务列表ID（如果为None，则不打印）
        """
        try:
            from rich.console import Console
            from rich.table import Table

            console = Console()

            # 确定要打印的任务列表
            task_lists_to_print = {}
            if task_list_id:
                task_list = task_list_manager.get_task_list(task_list_id)
                if task_list:
                    task_lists_to_print[task_list_id] = task_list

            if not task_lists_to_print:
                return

            for tlist_id, task_list in task_lists_to_print.items():
                tasks = list(task_list.tasks.values())
                if not tasks:
                    continue

                # 创建表格
                table = Table(
                    title=f"任务列表状态: {tlist_id}",
                    show_header=True,
                    header_style="bold magenta",
                    title_style="bold cyan",
                )
                table.add_column("任务ID", style="cyan", width=12)
                table.add_column("任务名称", style="yellow", width=30)
                table.add_column("状态", style="bold", width=12)
                table.add_column("优先级", justify="center", width=8)
                table.add_column("Agent类型", width=10)
                table.add_column("依赖", width=12)

                # 按优先级和创建时间排序
                sorted_tasks = sorted(tasks, key=lambda t: (-t.priority, t.create_time))

                # 状态颜色映射
                status_colors = {
                    TaskStatus.PENDING: "yellow",
                    TaskStatus.RUNNING: "blue",
                    TaskStatus.COMPLETED: "green",
                    TaskStatus.FAILED: "red",
                    TaskStatus.ABANDONED: "dim",
                }

                for task in sorted_tasks:
                    status_color = status_colors.get(task.status, "white")
                    status_text = (
                        f"[{status_color}]{task.status.value}[/{status_color}]"
                    )

                    # 格式化依赖
                    deps_text = ", ".join(task.dependencies[:3])
                    if len(task.dependencies) > 3:
                        deps_text += f" (+{len(task.dependencies) - 3})"

                    table.add_row(
                        task.task_id,
                        task.task_name[:28] + "..."
                        if len(task.task_name) > 30
                        else task.task_name,
                        status_text,
                        str(task.priority),
                        task.agent_type.value,
                        deps_text if task.dependencies else "-",
                    )

                console.print(table)

                # 打印统计信息
                summary = task_list_manager.get_task_list_summary(tlist_id)
                if summary:
                    stats_text = (
                        f"📊 总计: {summary['total_tasks']} | "
                        f"⏳ 待执行: {summary['pending']} | "
                        f"🔄 执行中: {summary['running']} | "
                        f"✅ 已完成: {summary['completed']} | "
                        f"❌ 失败: {summary['failed']} | "
                        f"🚫 已放弃: {summary['abandoned']}"
                    )
                    console.print(f"[dim]{stats_text}[/dim]")
                    console.print()  # 空行

        except Exception as e:
            # 打印详细错误信息，帮助调试
            import traceback

            PrettyOutput.auto_print(f"⚠️ 打印任务状态失败: {e}")
            PrettyOutput.auto_print(f"   错误详情: {traceback.format_exc()}")

    description = f"""任务列表管理工具，供LLM管理复杂任务拆分和执行。

**核心功能：**
- `add_tasks`: 批量添加任务（推荐PLAN阶段使用）
- `execute_task`: 执行任务（自动创建子Agent）
- `get_task_list_summary`: 查看任务状态

**任务类型选择：**
- `main`: 简单任务（1-3步、单文件）由主Agent直接执行
- `sub`: 复杂任务（多步骤、多文件）自动创建子Agent

**强制要求：**
- execute_task必须提供non-empty additional_info参数
- 禁止过度拆分简单任务
- 每个Agent只能有一个任务列表

**使用场景：**
- PLAN阶段：一次性添加所有子任务
- 数据切分：按目录/文件/模块分批处理
- 依赖管理：自动验证任务依赖关系

**关键原则：**
简单任务用main，复杂任务用sub，避免过度拆分。

**使用示例**
创建任务列表：
```
{ot("TOOL_CALL")}
{{
    "name": "task_list_manager",
    "arguments": {{
        "action": "add_tasks",
        "main_goal": "创建任务列表",
        "background": "背景信息",
        "tasks_info": [
            {{
                "task_name": "任务1",
                "task_desc": "任务1描述",
                "priority": 1,
                "expected_output": "任务1预期输出",
                "agent_type": "main",
                "dependencies": []
            }}
            {{
                "task_name": "任务2",
                "task_desc": "任务2描述",
                "priority": 2,
                "expected_output": "任务2预期输出",
                "agent_type": "sub",
                "dependencies": ["任务1"]
            }}
        ]
    }}
}}
{ct("TOOL_CALL")}
```

执行任务：
```
{ot("TOOL_CALL")}
{{
    "name": "task_list_manager",
    "arguments": {{
        "action": "execute_task",
        "task_id": "任务ID",
        "additional_info": "任务详细信息"
    }}
}}
{ct("TOOL_CALL")}
```

更新任务状态：
```
{ot("TOOL_CALL")}
{{
    "name": "task_list_manager",
    "arguments": {{
        "action": "update_task",
        "task_id": "任务ID",
        "task_update_info": {{
            "status": "completed",
            "actual_output": "任务实际输出"
        }}
    }}
}}
{ct("TOOL_CALL")}
```


"""

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "add_tasks",
                    "get_task_detail",
                    "get_task_list_summary",
                    "execute_task",
                    "update_task",
                ],
                "description": "要执行的操作",
            },
            "main_goal": {
                "type": "string",
                "description": "任务列表的核心目标（必填，仅在首次创建任务列表时使用）。创建新任务列表时必须提供此参数。",
            },
            "background": {
                "type": "string",
                "description": "所有子任务的公共背景信息，将自动添加到每个子任务的描述中。**必须包含以下信息**：1) **全局约束条件**：所有子任务必须遵循的技术约束、环境限制、性能要求等；2) **必须要求**：所有子任务必须完成的要求、必须遵循的规范、必须实现的功能等；3) **禁止事项**：所有子任务执行中禁止的操作、禁止使用的技术、禁止修改的内容等；4) **验证标准**：所有子任务的统一验证方式、验收标准、测试要求等。可用于提供全局上下文、统一规范等公共信息。",
            },
            "tasks_info": {
                "type": "array",
                "description": "任务信息列表（add_tasks 需要，如果任务列表不存在会自动创建）",
                "items": {
                    "type": "object",
                    "properties": {
                        "task_name": {"type": "string", "description": "任务名称"},
                        "task_desc": {
                            "type": "string",
                            "description": "任务描述。**必须包含以下信息**：1) **约束条件**：明确任务执行的技术约束、环境限制、性能要求等；2) **必须要求**：明确任务必须完成的具体要求、必须遵循的规范、必须实现的功能等；3) **禁止事项**：明确任务执行中禁止的操作、禁止使用的技术、禁止修改的内容等；4) **验证标准**：明确任务完成的验证方式、验收标准、测试要求等。任务描述应该清晰、具体、可执行。",
                        },
                        "priority": {
                            "type": "integer",
                            "description": "优先级（1-5，5为最高）",
                        },
                        "expected_output": {
                            "type": "string",
                            "description": "预期输出。**必须使用分条列出的结构化格式**，例如：1) xxx；2) yyy；3) zzz，或使用 markdown 列表 - xxx、- yyy、- zzz。后续验证 Agent 会对每一条预期输出条目分别进行验证。",
                        },
                        "agent_type": {
                            "type": "string",
                            "enum": ["main", "sub"],
                            "description": "Agent类型：**简单任务必须使用 `main`**（由主Agent直接执行，不要拆分为子任务）；**复杂任务使用 `sub`**（系统智能处理复杂任务）",
                        },
                        "dependencies": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "依赖的任务名称或任务ID列表（可选，可以引用本次批次中的任务名称）",
                        },
                    },
                    "required": [
                        "task_name",
                        "task_desc",
                        "priority",
                        "expected_output",
                        "agent_type",
                    ],
                },
            },
            "task_id": {
                "type": "string",
                "description": "任务ID（execute_task/update_task/get_task_detail 需要）",
            },
            "additional_info": {
                "type": "string",
                "description": "附加信息（**仅在 execute_task 时必填**）。必须提供任务的详细上下文信息，包括任务背景、关键信息、约束条件、预期结果等。不能为空字符串或None。",
            },
            "task_update_info": {
                "type": "object",
                "description": "任务更新信息（update_task 需要）",
                "properties": {
                    "task_name": {
                        "type": "string",
                        "description": "更新后的任务名称（可选）",
                    },
                    "task_desc": {
                        "type": "string",
                        "description": "更新后的任务描述（可选）。**必须包含以下信息**：1) **约束条件**：明确任务执行的技术约束、环境限制、性能要求等；2) **必须要求**：明确任务必须完成的具体要求、必须遵循的规范、必须实现的功能等；3) **禁止事项**：明确任务执行中禁止的操作、禁止使用的技术、禁止修改的内容等；4) **验证标准**：明确任务完成的验证方式、验收标准、测试要求等。任务描述应该清晰、具体、可执行。",
                    },
                    "priority": {
                        "type": "integer",
                        "description": "更新后的优先级（可选，1-5）",
                    },
                    "expected_output": {
                        "type": "string",
                        "description": "更新后的预期输出（可选）",
                    },
                    "dependencies": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "更新后的依赖任务ID列表（可选）",
                    },
                    "status": {
                        "type": "string",
                        "enum": [
                            "pending",
                            "running",
                            "completed",
                            "failed",
                            "abandoned",
                        ],
                        "description": "更新后的任务状态（可选，通常不需要手动调用）",
                    },
                    "actual_output": {
                        "type": "string",
                        "description": "更新后的实际输出（可选，通常不需要手动调用）",
                    },
                },
            },
        },
        "required": ["action"],
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行任务列表管理操作"""
        try:
            agent = args.get("agent")
            if not agent:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "无法获取 Agent 实例",
                }

            # 获取任务列表管理器
            task_list_manager = getattr(agent, "task_list_manager", None)
            if not task_list_manager:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "任务列表管理器未初始化",
                }

            # 获取 Agent ID（使用 Agent 名称作为 ID）
            agent_id = getattr(agent, "name", "main_agent")
            is_main_agent = True  # CodeAgent 默认是主 Agent

            action = args.get("action")
            if not action:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "缺少 action 参数",
                }

            # 根据 action 执行相应操作
            result = None
            task_list_id_for_status = None

            if action == "add_tasks":
                result = self._handle_add_tasks(
                    args, task_list_manager, agent_id, agent
                )
                task_list_id_for_status = self._get_task_list_id(agent)

            elif action == "get_task_detail":
                result = self._handle_get_task_detail(
                    args, task_list_manager, agent_id, is_main_agent, agent
                )
                task_list_id_for_status = self._get_task_list_id(agent)

            elif action == "get_task_list_summary":
                result = self._handle_get_task_list_summary(
                    args, task_list_manager, agent
                )
                task_list_id_for_status = self._get_task_list_id(agent)

            elif action == "execute_task":
                result = self._handle_execute_task(
                    args, task_list_manager, agent_id, is_main_agent, agent
                )
                task_list_id_for_status = self._get_task_list_id(agent)

            elif action == "update_task":
                result = self._handle_update_task(
                    args, task_list_manager, agent_id, is_main_agent, agent
                )
                task_list_id_for_status = self._get_task_list_id(agent)

            else:
                result = {
                    "success": False,
                    "stdout": "",
                    "stderr": f"未知的操作: {action}",
                }

            # 打印任务状态（如果操作成功）
            if result and result.get("success"):
                # 如果有 task_list_id，只打印该任务列表；否则打印所有任务列表
                self._print_task_list_status(task_list_manager, task_list_id_for_status)

            return result

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"执行任务列表操作失败: {str(e)}",
            }

    def _handle_add_tasks(
        self, args: Dict[str, Any], task_list_manager: Any, agent_id: str, agent: Any
    ) -> Dict[str, Any]:
        """处理批量添加任务（支持通过任务名称匹配依赖关系）"""
        task_list_id = self._get_task_list_id(agent)
        tasks_info = args.get("tasks_info")

        if not task_list_id:
            # 验证：如果没有task_list且只有一个任务且agent不是main，则拒绝
            if tasks_info and isinstance(tasks_info, list) and len(tasks_info) == 1:
                # 获取第一个任务的agent_type
                first_task = tasks_info[0]
                agent_type = first_task.get("agent_type")
                if agent_type != "main":
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "拒绝添加单个非main类型任务：对于简单任务，agent_type应为main，由主Agent直接执行。如需创建复杂任务，请添加多个任务或修改agent_type为main。",
                    }

            # 自动创建任务列表
            if not tasks_info:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "缺少 tasks_info 参数",
                }

            # 验证 main_goal 是否为必填参数
            main_goal = args.get("main_goal")
            if not main_goal:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "缺少 main_goal 参数：创建任务列表时必须提供 main_goal",
                }

            # 检查是否已有任务列表
            existing_task_list_id = self._get_task_list_id(agent)
            if existing_task_list_id:
                # 检查任务列表是否还存在
                existing_task_list = task_list_manager.get_task_list(
                    existing_task_list_id
                )
                if existing_task_list:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": f"Agent 已存在任务列表（ID: {existing_task_list_id}），每个 Agent 只能有一个任务列表。如需创建新列表，请先完成或放弃当前任务列表。",
                    }

            # 创建任务列表
            task_list_id, success, error_msg = task_list_manager.create_task_list(
                main_goal=main_goal, agent_id=agent_id
            )

            if not success:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"自动创建任务列表失败: {error_msg}",
                }

            # 保存 task_list_id 到 Agent 的 user_data
            self._set_task_list_id(agent, task_list_id)

        tasks_info = args.get("tasks_info")
        if not tasks_info:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少 tasks_info 参数",
            }

        if not isinstance(tasks_info, list):
            return {
                "success": False,
                "stdout": "",
                "stderr": "tasks_info 必须是数组",
            }

        # 获取background参数并处理
        background = args.get("background", "")
        if background and str(background).strip():
            # 将background信息附加到每个子任务的描述中
            processed_tasks_info = []
            for task_info in tasks_info:
                if isinstance(task_info, dict) and "task_desc" in task_info:
                    # 创建新的task_info字典，避免修改原始数据
                    new_task_info = task_info.copy()

                    # 构建新的任务描述，包含background信息
                    original_desc = task_info["task_desc"]
                    separator = "\n" + "=" * 50 + "\n"
                    new_task_info["task_desc"] = (
                        f"{original_desc}{separator}公共背景信息:\n{background}"
                    )
                    processed_tasks_info.append(new_task_info)
                else:
                    processed_tasks_info.append(task_info)
            tasks_info = processed_tasks_info

        # add_tasks 方法已经支持通过任务名称匹配依赖关系
        task_ids, success, error_msg = task_list_manager.add_tasks(
            task_list_id=task_list_id, tasks_info=tasks_info, agent_id=agent_id
        )

        if success:
            result = {
                "task_ids": task_ids,
                "task_count": len(task_ids),
                "task_list_id": task_list_id,
                "message": f"成功批量添加 {len(task_ids)} 个任务",
            }
            return {
                "success": True,
                "stdout": json.dumps(result, ensure_ascii=False, indent=2),
                "stderr": "",
            }
        else:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"批量添加任务失败: {error_msg}",
            }

    def _handle_get_task_detail(
        self,
        args: Dict[str, Any],
        task_list_manager: Any,
        agent_id: str,
        is_main_agent: bool,
        agent: Any,
    ) -> Dict[str, Any]:
        """处理获取任务详情"""
        task_list_id = self._get_task_list_id(agent)
        if not task_list_id:
            return {
                "success": False,
                "stdout": "",
                "stderr": "Agent 还没有任务列表，请先使用 add_tasks 添加任务（会自动创建任务列表）",
            }
        task_id = args.get("task_id")

        if not task_id:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少 task_id 参数",
            }

        task, success, error_msg = task_list_manager.get_task_detail(
            task_list_id=task_list_id,
            task_id=task_id,
            agent_id=agent_id,
            is_main_agent=is_main_agent,
        )

        if success and task:
            result = {
                "task": task.to_dict(),
                "message": "获取任务详情成功",
            }
            return {
                "success": True,
                "stdout": json.dumps(result, ensure_ascii=False, indent=2),
                "stderr": "",
            }
        else:
            return {
                "success": False,
                "stdout": "",
                "stderr": error_msg or "获取任务详情失败",
            }

    def _handle_get_task_list_summary(
        self, args: Dict[str, Any], task_list_manager: Any, agent: Any
    ) -> Dict[str, Any]:
        """处理获取任务列表摘要"""
        task_list_id = self._get_task_list_id(agent)
        if not task_list_id:
            return {
                "success": False,
                "stdout": "",
                "stderr": "Agent 还没有任务列表，请先使用 add_tasks 添加任务（会自动创建任务列表）",
            }

        summary = task_list_manager.get_task_list_summary(task_list_id=task_list_id)

        if summary:
            return {
                "success": True,
                "stdout": json.dumps(summary, ensure_ascii=False, indent=2),
                "stderr": "",
            }
        else:
            return {
                "success": False,
                "stdout": "",
                "stderr": "任务列表不存在",
            }

    def _validate_dependencies_status(
        self,
        task_list_manager: Any,
        task_list_id: str,
        task: Any,
        agent_id: str,
        is_main_agent: bool,
    ) -> None:
        """验证任务的所有依赖是否都已completed

        参数:
            task_list_manager: 任务列表管理器
            task_list_id: 任务列表ID
            task: 要验证的任务对象
            agent_id: Agent ID
            is_main_agent: 是否为主 Agent

        抛出:
            DependencyNotFoundError: 依赖任务不存在
            DependencyNotCompletedError: 依赖任务未完成
            DependencyFailedError: 依赖任务失败
        """
        if not task.dependencies:
            return  # 无依赖，直接返回

        for dep_id in task.dependencies:
            dep_task, success, error_msg = task_list_manager.get_task_detail(
                task_list_id=task_list_id,
                task_id=dep_id,
                agent_id=agent_id,
                is_main_agent=is_main_agent,
            )

            if not success:
                raise DependencyNotFoundError(f"依赖任务 '{dep_id}' 不存在")

            if dep_task.status == TaskStatus.FAILED:
                raise DependencyFailedError(
                    f"依赖任务 '{dep_id}' 执行失败，无法执行当前任务"
                )

            if dep_task.status == TaskStatus.ABANDONED:
                raise DependencyFailedError(
                    f"依赖任务 '{dep_id}' 已被放弃，无法执行当前任务"
                )

            if dep_task.status == TaskStatus.PENDING:
                raise DependencyNotCompletedError(
                    f"依赖任务 '{dep_id}' 尚未开始执行，无法执行当前任务"
                )

            if dep_task.status == TaskStatus.RUNNING:
                raise DependencyNotCompletedError(
                    f"依赖任务 '{dep_id}' 正在执行中，无法执行当前任务"
                )

            if dep_task.status != TaskStatus.COMPLETED:
                raise DependencyNotCompletedError(
                    f"依赖任务 '{dep_id}' 状态为 '{dep_task.status.value}'，不满足执行条件"
                )

    def _handle_execute_task(
        self,
        args: Dict[str, Any],
        task_list_manager: Any,
        agent_id: str,
        is_main_agent: bool,
        parent_agent: Any,
    ) -> Dict[str, Any]:
        """处理执行任务（自动创建子 Agent 执行）

        重要提醒：执行一个任务前，系统会自动验证其所有依赖任务是否已完成（completed状态）。
        如果有任何依赖任务未完成或失败，任务执行将被拒绝并返回相应的错误信息。"""
        task_list_id = self._get_task_list_id(parent_agent)
        if not task_list_id:
            return {
                "success": False,
                "stdout": "",
                "stderr": "Agent 还没有任务列表，请先使用 add_tasks 添加任务（会自动创建任务列表）",
            }
        task_id = args.get("task_id")
        additional_info = args.get("additional_info")

        if not task_id:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少 task_id 参数",
            }

        if additional_info is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少 additional_info 参数",
            }

        if not additional_info or not str(additional_info).strip():
            return {
                "success": False,
                "stdout": "",
                "stderr": "additional_info 参数不能为空",
            }

        # 获取任务详情
        task, success, error_msg = task_list_manager.get_task_detail(
            task_list_id=task_list_id,
            task_id=task_id,
            agent_id=agent_id,
            is_main_agent=is_main_agent,
        )

        if not success or not task:
            return {
                "success": False,
                "stdout": "",
                "stderr": error_msg or "获取任务详情失败",
            }

        # 验证依赖状态
        try:
            self._validate_dependencies_status(
                task_list_manager=task_list_manager,
                task_list_id=task_list_id,
                task=task,
                agent_id=agent_id,
                is_main_agent=is_main_agent,
            )
        except DependencyValidationError as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
            }

        # 检查任务状态
        if task.status.value != "pending":
            return {
                "success": False,
                "stdout": "",
                "stderr": f"任务状态为 {task.status.value}，无法执行（只有 pending 状态的任务可以执行）",
            }

        # 检查是否有正在运行的任务
        try:
            running_tasks = []
            # 获取任务列表实例
            task_list = task_list_manager.get_task_list(task_list_id)
            if task_list:
                # 扫描所有任务，查找运行中的任务
                for task_obj in task_list.tasks.values():
                    if task_obj.status.value == "running":
                        running_tasks.append(
                            {
                                "task_id": task_obj.task_id,
                                "task_name": task_obj.task_name,
                            }
                        )

            if running_tasks:
                running_task_details = []
                for rt in running_tasks:
                    running_task_details.append(
                        f"任务ID: {rt['task_id']}, 任务名称: {rt['task_name']}"
                    )

                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"检测到 {len(running_tasks)} 个任务正在运行，请先完成这些任务后再执行新任务：\n"
                    + "\n".join(running_task_details),
                }

        except Exception:
            # 如果检测失败，记录但不阻止任务执行，避免影响系统稳定性
            pass

        # 更新任务状态为 running
        update_success, update_msg = task_list_manager.update_task_status(
            task_list_id=task_list_id,
            task_id=task_id,
            status="running",
            agent_id=agent_id,
            is_main_agent=is_main_agent,
        )

        if not update_success:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"更新任务状态失败: {update_msg}",
            }

        try:
            # 合并任务描述和附加信息（实际更新任务的desc字段，使打印时可见）
            if additional_info and str(additional_info).strip():
                separator = "\n" + "=" * 50 + "\n"
                task.task_desc = (
                    f"{task.task_desc}{separator}附加信息:\n{additional_info}"
                )

            # 使用公共方法构建任务执行内容
            task_content = self._build_task_content(task)

            # 构建背景信息
            background_parts = []

            # 获取额外的背景信息（如果提供）
            additional_background = args.get("additional_background")
            if additional_background:
                background_parts.append(f"额外背景信息: {additional_background}")

            # 使用公共方法构建标准背景信息
            standard_background = self._build_task_background(
                task_list_manager=task_list_manager,
                task_list_id=task_list_id,
                task=task,
                agent_id=agent_id,
                is_main_agent=is_main_agent,
                include_completed_summary=True,
            )

            if standard_background:
                background_parts.append(standard_background)

            background = "\n\n".join(background_parts) if background_parts else ""

            # 根据 agent_type 创建相应的子 Agent 执行任务
            execution_result = None
            if task.agent_type.value == "main":
                # 主 Agent 执行：直接在当前 Agent 中执行（不创建子 Agent）
                # 注意：主 Agent 类型的任务需要主 Agent 自行执行，执行完成后需要手动调用 update_task_status 更新状态
                result = {
                    "task_id": task_id,
                    "task_name": task.task_name,
                    "task_desc": task.task_desc,
                    "expected_output": task.expected_output,
                    "background": background,
                    "message": "任务已标记为 running，请主 Agent 自行执行",
                    "note": "主 Agent 类型的任务应由当前 Agent 直接执行，执行完成后请调用 update_task 更新任务状态为 completed 或 failed",
                    "warning": "请务必在执行完成后更新任务状态，否则任务将一直保持 running 状态",
                }
                return {
                    "success": True,
                    "stdout": json.dumps(result, ensure_ascii=False, indent=2),
                    "stderr": "",
                }

            elif task.agent_type.value == "sub":
                # 子 Agent 执行：自动识别使用合适的子 Agent 工具
                # 执行后需要验证任务是否真正完成，如果未完成则继续迭代执行
                # 初始化变量，确保在 try-except 外部可以访问
                final_verification_passed = False
                execution_result = None
                iteration = 0

                try:
                    # 直接根据agent实例类型判断任务类型
                    is_code_task = self._determine_agent_type(
                        parent_agent, task, task_content, background
                    )

                    # 迭代执行和验证，直到任务真正完成（无限迭代，直到验证通过）
                    iteration = 0
                    verification_passed = False
                    all_execution_results = []  # 记录所有执行结果
                    all_verification_results: List[str] = []  # 记录所有验证结果

                    while not verification_passed:
                        iteration += 1
                        from jarvis.jarvis_utils.output import PrettyOutput

                        PrettyOutput.auto_print(
                            f"🔄 执行任务 [{task.task_name}] (第 {iteration} 次迭代)..."
                        )

                        if is_code_task:
                            # 代码相关任务：使用 sub_code_agent 工具
                            from jarvis.jarvis_tools.sub_code_agent import (
                                SubCodeAgentTool,
                            )

                            sub_code_agent_tool = SubCodeAgentTool()

                            # 构建子Agent名称：使用任务名称和ID，便于识别
                            agent_name = f"{task.task_name} (task_{task_id})"

                            # 如果是第二次及以后的迭代，添加验证反馈信息
                            enhanced_task_content = task_content
                            if iteration > 1 and all_verification_results:
                                last_verification = all_verification_results[-1]
                                enhanced_task_content = f"""{task_content}

**之前的验证反馈（需要修复的问题）：**
{last_verification}

请根据以上验证反馈修复问题，确保任务真正完成。
"""

                            # 调用 sub_code_agent 执行任务
                            tool_result = sub_code_agent_tool.execute(
                                {
                                    "task": enhanced_task_content,
                                    "background": background,
                                    "name": agent_name,
                                    "agent": parent_agent,
                                }
                            )
                        else:
                            # 通用任务：使用 sub_agent 工具
                            from jarvis.jarvis_tools.sub_agent import SubAgentTool

                            sub_general_agent_tool = SubAgentTool()

                            # 构建系统提示词和总结提示词
                            system_prompt = f"""你是一个专业的任务执行助手。

当前任务: {task.task_name}

任务描述: {task.task_desc}

预期输出: {task.expected_output}

请专注于完成这个任务，完成后提供清晰的输出结果。
"""
                            summary_prompt = f"总结任务 [{task.task_name}] 的执行结果，包括完成的工作和输出内容。"

                            # 构建子Agent名称：使用任务名称和ID，便于识别
                            agent_name = f"{task.task_name} (task_{task_id})"

                            # 如果是第二次及以后的迭代，添加验证反馈信息
                            enhanced_task_content = task_content
                            if iteration > 1 and all_verification_results:
                                last_verification = all_verification_results[-1]
                                enhanced_task_content = f"""{task_content}

**之前的验证反馈（需要修复的问题）：**
{last_verification}

请根据以上验证反馈修复问题，确保任务真正完成。
"""

                            # 调用 sub_agent 执行任务
                            tool_result = sub_general_agent_tool.execute(
                                {
                                    "task": enhanced_task_content,
                                    "background": background,
                                    "name": agent_name,
                                    "system_prompt": system_prompt,
                                    "summary_prompt": summary_prompt,
                                    "agent": parent_agent,
                                }
                            )

                        execution_result = tool_result.get("stdout", "")
                        execution_success = tool_result.get("success", False)

                        if not execution_success:
                            # 执行失败，更新任务状态为 failed
                            task_list_manager.update_task_status(
                                task_list_id=task_list_id,
                                task_id=task_id,
                                status="failed",
                                agent_id=agent_id,
                                is_main_agent=is_main_agent,
                                actual_output=f"执行失败: {tool_result.get('stderr', '未知错误')}",
                            )
                            return {
                                "success": False,
                                "stdout": "",
                                "stderr": f"子 Agent 执行失败: {tool_result.get('stderr', '未知错误')}",
                            }

                        # 记录执行结果
                        all_execution_results.append(execution_result)

                        # 验证任务是否真正完成
                        verification_passed, verification_result = (
                            self._verify_task_completion(
                                task,
                                task_content,
                                background,
                                parent_agent,
                                verification_iteration=iteration,
                            )
                        )

                        # 记录验证结果
                        all_verification_results.append(verification_result)

                        if not verification_passed:
                            PrettyOutput.auto_print(
                                f"⚠️ 任务 [{task.task_name}] 验证未通过，将继续迭代修复 (第 {iteration} 次迭代)"
                            )
                        else:
                            PrettyOutput.auto_print(
                                f"✅ 任务 [{task.task_name}] 验证通过，任务真正完成 (共执行 {iteration} 次迭代)"
                            )
                            final_verification_passed = True

                    # 保存最终验证状态（循环退出时 verification_passed 应该为 True）
                    final_verification_passed = verification_passed

                    # 使用最后一次的执行结果
                    execution_result = (
                        all_execution_results[-1]
                        if all_execution_results
                        else "任务执行完成"
                    )
                except Exception as e:
                    # 执行异常，更新任务状态为 failed
                    task_list_manager.update_task_status(
                        task_list_id=task_list_id,
                        task_id=task_id,
                        status="failed",
                        agent_id=agent_id,
                        is_main_agent=is_main_agent,
                        actual_output=f"执行异常: {str(e)}",
                    )
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": f"创建子 Agent 执行任务失败: {str(e)}",
                    }

                # 确保 execution_result 有值
                if execution_result is None:
                    execution_result = "任务执行完成"

            # 处理执行结果：如果结果太长，进行截断并添加提示
            processed_result = execution_result or "任务执行完成"

            # 基于剩余token动态计算最大输出长度
            max_output_length = self._get_max_output_length(parent_agent)

            if len(processed_result) > max_output_length:
                # 根据最大长度计算截断时的前缀和后缀长度
                prefix_length, suffix_length = self._get_truncate_lengths(
                    max_output_length
                )

                # 保留前缀和后缀，中间用省略号连接
                truncated_result = (
                    processed_result[:prefix_length]
                    + "\n\n... [输出内容过长，已截断中间部分] ...\n\n"
                    + processed_result[-suffix_length:]
                )
                processed_result = truncated_result
                execution_result_len = (
                    len(execution_result) if execution_result is not None else 0
                )
                PrettyOutput.auto_print(
                    f"⚠️ 任务 {task_id} 的执行结果过长（{execution_result_len} 字符），"
                    f"已截断为 {len(truncated_result)} 字符（基于剩余token限制：{max_output_length} 字符）"
                )

            # 对于 sub agent 类型的任务，只有在验证通过后才更新为 completed
            # 如果验证未通过但达到最大迭代次数，标记为 failed
            if task.agent_type.value == "sub":
                # 检查最终验证状态
                if final_verification_passed:
                    # 验证通过，更新任务状态为 completed
                    task_list_manager.update_task_status(
                        task_list_id=task_list_id,
                        task_id=task_id,
                        status="completed",
                        agent_id=agent_id,
                        is_main_agent=is_main_agent,
                        actual_output=processed_result,
                    )
                else:
                    # 验证未通过，标记为 failed，并返回详细的验证结果
                    task_list_manager.update_task_status(
                        task_list_id=task_list_id,
                        task_id=task_id,
                        status="failed",
                        agent_id=agent_id,
                        is_main_agent=is_main_agent,
                        actual_output=processed_result,
                    )

                    # 获取最后一次验证结果
                    last_verification = (
                        all_verification_results[-1]
                        if all_verification_results
                        else "验证失败"
                    )

                    # 构建详细的失败报告
                    failure_report = f"""
❌ **任务执行失败报告**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 **任务信息**
   任务ID: {task_id}
   任务名称: {task.task_name}
   任务类型: sub
   最终状态: failed

⚠️ **执行情况**
   迭代次数: {iteration} 次
   验证结果: ❌ 验证未通过

📋 **最后一次验证报告**
{last_verification}

📊 **执行输出**
{processed_result[:1000]}{"..." if len(processed_result) > 1000 else ""}

💡 **后续建议**
   • 任务已标记为 failed 状态
   • 请仔细阅读验证报告，了解具体失败原因
   • 可以修改任务描述或预期输出后重新执行
   • 或者根据实际情况调整任务目标

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
任务 [{task.task_name}] 执行失败，已标记为 failed 状态。
"""
                    return {
                        "success": False,
                        "stdout": failure_report.strip(),
                        "stderr": "子任务执行验证未通过，已标记为failed",
                    }
            else:
                # 对于 main agent 类型的任务，直接更新为 completed（由主 Agent 自行管理状态）
                # 这里不更新状态，由主 Agent 自行调用 update_task 更新
                pass

            # 构建格式化的任务完成通知
            import datetime

            # 获取当前时间作为完成时间
            completion_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 预览长度：基于最大输出长度的50%
            preview_length = int(max_output_length * 0.5)

            # 创建格式化的完成通知
            formatted_notification = f"""
✅ **任务完成通知**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 **任务信息**
   任务ID: {task_id}
   任务名称: {task.task_name}
   优先级: {task.priority}/5
   完成时间: {completion_time}

📊 **执行结果**
   状态: ✅ 已完成
   输出长度: {len(processed_result)} 字符
   
📝 **执行摘要**
{processed_result[:preview_length]}{"..." if len(processed_result) > preview_length else ""}

📋 **后续操作**
   • 完整结果已保存到任务的 actual_output 字段
   • 可通过 get_task_detail 获取完整详情
   • 依赖此任务的其他任务现在可以开始执行
   • ⚠️ 在开始后续任务前，请评估任务执行的必要性 - 如果前面的任务已经多做了，可以废弃后续任务

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
任务 [{task.task_name}] 已成功完成！
"""

            # 直接返回格式化的任务完成通知
            return {
                "success": True,
                "stdout": formatted_notification.strip(),
                "stderr": "",
            }

        except Exception as e:
            # 发生异常，更新任务状态为 failed
            try:
                task_list_manager.update_task_status(
                    task_list_id=task_list_id,
                    task_id=task_id,
                    status="failed",
                    agent_id=agent_id,
                    is_main_agent=is_main_agent,
                    actual_output=f"执行异常: {str(e)}",
                )
            except Exception:
                pass

            return {
                "success": False,
                "stdout": "",
                "stderr": f"执行任务失败: {str(e)}",
            }

    def _check_dependencies_completed(
        self,
        task_list_manager: Any,
        task_list_id: str,
        dependencies: List[str],
        agent_id: str,
        is_main_agent: bool,
    ) -> Dict[str, Any]:
        """验证依赖任务状态。

        参数:
            task_list_manager: 任务列表管理器
            task_list_id: 任务列表 ID
            dependencies: 依赖任务 ID 列表
            agent_id: Agent ID
            is_main_agent: 是否为主 Agent

        返回:
            Dict: 验证结果，包含 success 状态和错误信息
        """
        if not dependencies:
            return {"success": True, "stdout": "", "stderr": ""}

        incomplete_deps = []
        failed_deps = []
        not_found_deps = []

        for dep_id in dependencies:
            dep_task, dep_success, error_msg = task_list_manager.get_task_detail(
                task_list_id=task_list_id,
                task_id=dep_id,
                agent_id=agent_id,
                is_main_agent=is_main_agent,
            )

            if not dep_success or not dep_task:
                not_found_deps.append(dep_id)
                continue

            if dep_task.status == TaskStatus.COMPLETED:
                continue  # 依赖已完成，继续检查下一个
            elif dep_task.status in (TaskStatus.FAILED, TaskStatus.ABANDONED):
                failed_deps.append((dep_id, dep_task.task_name, dep_task.status.value))
            else:  # PENDING 或 RUNNING
                incomplete_deps.append(
                    (dep_id, dep_task.task_name, dep_task.status.value)
                )

        # 构建错误信息
        error_messages = []

        if not_found_deps:
            error_messages.append(f"依赖任务不存在: {', '.join(not_found_deps)}")

        if failed_deps:
            for dep_id, task_name, status in failed_deps:
                error_messages.append(
                    f"依赖任务 [{task_name}] 状态为 {status}，无法执行"
                )

        if incomplete_deps:
            for dep_id, task_name, status in incomplete_deps:
                error_messages.append(
                    f"依赖任务 [{task_name}] 状态为 {status}，需要为 completed"
                )

        if error_messages:
            return {
                "success": False,
                "stdout": "",
                "stderr": "任务执行失败：依赖验证未通过\n"
                + "\n".join(f"- {msg}" for msg in error_messages),
            }

        return {"success": True, "stdout": "", "stderr": ""}

    def _handle_update_task(
        self,
        args: Dict[str, Any],
        task_list_manager: Any,
        agent_id: str,
        is_main_agent: bool,
        agent: Any,
    ) -> Dict[str, Any]:
        """处理更新任务属性"""
        task_list_id = self._get_task_list_id(agent)
        if not task_list_id:
            return {
                "success": False,
                "stdout": "",
                "stderr": "Agent 还没有任务列表，请先使用 add_tasks 添加任务（会自动创建任务列表）",
            }
        task_id = args.get("task_id")
        task_update_info = args.get("task_update_info", {})

        if not task_id:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少 task_id 参数",
            }

        if not task_update_info:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少 task_update_info 参数",
            }

        try:
            # 权限检查
            if not task_list_manager._check_agent_permission(
                agent_id, task_id, is_main_agent
            ):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "权限不足：无法访问该任务",
                }

            # 获取任务列表
            task_list = task_list_manager.get_task_list(task_list_id)
            if not task_list:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "任务列表不存在",
                }

            # 获取任务
            task = task_list.get_task(task_id)
            if not task:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "任务不存在",
                }

            # 验证并更新任务属性
            update_kwargs = {}

            if "task_name" in task_update_info:
                new_name = task_update_info["task_name"]
                update_kwargs["task_name"] = new_name

            if "task_desc" in task_update_info:
                new_desc = task_update_info["task_desc"]
                update_kwargs["task_desc"] = new_desc

            if "priority" in task_update_info:
                new_priority = task_update_info["priority"]
                if not isinstance(new_priority, int):
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": f"priority 必须是整数类型: {type(new_priority).__name__}",
                    }
                update_kwargs["priority"] = new_priority

            if "expected_output" in task_update_info:
                update_kwargs["expected_output"] = task_update_info["expected_output"]

            if "dependencies" in task_update_info:
                # 验证依赖关系
                new_deps = task_update_info["dependencies"]
                for dep_id in new_deps:
                    if dep_id not in task_list.tasks:
                        return {
                            "success": False,
                            "stdout": "",
                            "stderr": f"依赖任务 {dep_id} 不存在",
                        }
                update_kwargs["dependencies"] = new_deps

            # 处理状态更新（如果提供）
            status = task_update_info.get("status")
            actual_output = task_update_info.get("actual_output")

            if status is not None:
                # 对于 main 类型任务，在更新为 completed 状态时进行验证
                # 但如果任务已经是 completed 状态，则不需要重新验证
                if (
                    status == "completed"
                    and task.agent_type.value == "main"
                    and task.status.value != "completed"
                ):
                    # 使用公共方法构建任务内容
                    task_content = self._build_task_content(task)

                    # 使用公共方法构建背景信息
                    background = self._build_task_background(
                        task_list_manager=task_list_manager,
                        task_list_id=task_list_id,
                        task=task,
                        agent_id=agent_id,
                        is_main_agent=is_main_agent,
                        include_completed_summary=False,  # main任务验证时不需要其他已完成任务摘要
                    )

                    # 执行验证
                    from jarvis.jarvis_utils.output import PrettyOutput

                    PrettyOutput.auto_print(
                        f"🔍 开始验证 main 类型任务 [{task.task_name}] 的完成情况..."
                    )

                    verification_passed, verification_result = (
                        self._verify_task_completion(
                            task,
                            task_content,
                            background,
                            agent,
                            verification_iteration=1,
                        )
                    )

                    if not verification_passed:
                        # 验证未通过，不更新状态，返回失败原因给agent
                        PrettyOutput.auto_print(
                            f"❌ 任务 [{task.task_name}] 验证未通过，状态未更新"
                        )

                        # 构建详细的失败报告，返回给agent
                        failure_report = f"""
❌ **任务验证失败报告**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 **任务信息**
   任务ID: {task_id}
   任务名称: {task.task_name}
   任务类型: main
   当前状态: {task.status.value}

⚠️ **验证结果**
   状态: ❌ 验证未通过
   原因: 任务未能满足预期输出要求

📋 **详细验证报告**
{verification_result}

💡 **后续建议**
   • 请仔细阅读上述验证报告，了解具体哪些预期输出条目未完成
   • 根据验证反馈修复相关问题
   • 修复完成后再次调用 update_task 更新状态为 completed
   • 任务状态将保持为 {task.status.value}，不会更新为 completed

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
任务 [{task.task_name}] 验证未通过，请根据上述反馈进行修复。
"""
                        return {
                            "success": False,
                            "stdout": failure_report.strip(),
                            "stderr": "任务验证未通过，状态未更新",
                        }
                    else:
                        PrettyOutput.auto_print(
                            f"✅ 任务 [{task.task_name}] 验证通过，更新状态为completed"
                        )

                # 使用 update_task_status 方法更新状态
                status_success, status_msg = task_list_manager.update_task_status(
                    task_list_id=task_list_id,
                    task_id=task_id,
                    status=status,
                    agent_id=agent_id,
                    is_main_agent=is_main_agent,
                    actual_output=actual_output,
                )
                if not status_success:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": f"更新任务状态失败: {status_msg}",
                    }

            # 执行其他属性更新（如果有）
            if update_kwargs:
                if not task_list.update_task(task_id, **update_kwargs):
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "更新任务属性失败",
                    }

            # 保存快照
            task_list_manager._save_snapshot(task_list_id, task_list)

            # 获取更新后的任务信息
            updated_task = task_list.get_task(task_id)
            result = {
                "task_id": task_id,
                "task": updated_task.to_dict() if updated_task else None,
                "message": "任务更新成功",
            }
            return {
                "success": True,
                "stdout": json.dumps(result, ensure_ascii=False, indent=2),
                "stderr": "",
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"更新任务失败: {str(e)}",
            }
