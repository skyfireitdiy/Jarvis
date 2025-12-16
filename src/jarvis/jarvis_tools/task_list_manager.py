"""任务列表管理工具。

该工具允许 LLM 管理任务列表，包括创建任务列表、添加任务、更新任务状态等。
"""

import json
from typing import Any

from jarvis.jarvis_utils.output import PrettyOutput

# -*- coding: utf-8 -*-
from typing import Dict
from typing import List
from typing import Optional

from jarvis.jarvis_agent.task_list import TaskStatus
from jarvis.jarvis_utils.config import get_max_input_token_count
from jarvis.jarvis_utils.globals import get_global_model_group
from jarvis.jarvis_utils.tag import ct
from jarvis.jarvis_utils.tag import ot


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
- 预期输出：{task.expected_output}

**验证要求：**
1. 使用 read_code 工具验证任务产生的代码或文件是否符合预期输出要求
2. 仅检查任务明确要求的产物是否存在且正确
3. 不要验证与任务预期输出无关的项目（如整体项目编译、无关测试等）
4. 关注任务描述中明确提到的具体交付物

**验证标准：**
- 任务预期输出是否已实际生成
- 生成的产物是否符合任务描述中的具体要求
- 不验证无关的编译状态、测试覆盖率或代码风格

**重要：**
- 只能使用 read_code 和 execute_script 工具
- 必须基于实际验证结果，不能推测或假设
- 仅验证任务预期输出和直接相关的产物
- 如果验证通过，直接输出 {ot("!!!COMPLETE!!!")}，不要输出其他任何内容。
"""

        # 构建验证任务的总结提示词（结构化格式要求）
        verification_summary_prompt = f"""请以结构化的格式总结任务验证结果。必须严格按照以下格式输出：

## 任务验证结果

**任务名称**：{task.task_name}

**验证状态**：[PASSED/FAILED]

**最终结论**：[VERIFICATION_PASSED 或 VERIFICATION_FAILED]

**说明**：
- 如果验证通过：输出 "任务预期输出已验证完成"
- 如果验证失败：详细说明不通过的原因，包括：
  * 预期输出未找到或不完整
  * 实际输出与预期不符的具体差异
  * 需要补充或修正的部分

**重要**：
- 必须严格按照上述格式输出
- 验证状态必须是 PASSED 或 FAILED
- 最终结论必须是 "VERIFICATION_PASSED" 或 "VERIFICATION_FAILED"
- 仅基于任务预期输出进行验证，不涉及无关检查
"""

        # 获取父 Agent 的模型组
        model_group = get_global_model_group()
        try:
            if parent_agent is not None:
                model_group = getattr(parent_agent, "model_group", model_group)
        except Exception:
            pass

        # 创建验证 Agent，只使用 read_code 和 execute_script 工具
        # 获取父代理所有规则内容并添加到系统提示词
        rules_content, _ = parent_agent.rules_manager.load_all_rules(','.join(parent_agent.loaded_rule_names))

        enhanced_system_prompt = verification_system_prompt + rules_content

        verification_agent = Agent(
            system_prompt=enhanced_system_prompt,
            name=f"verification_agent_{task.task_id}_{verification_iteration}",
            description="Task verification agent",
            model_group=model_group,
            summary_prompt=verification_summary_prompt,
            auto_complete=True,
            need_summary=True,
            use_tools=["read_code", "execute_script"],  # 只使用这两个工具
            non_interactive=True,
        )

        return verification_agent

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
            verification_task = f"""请验证以下任务是否真正完成：

{task_content}

背景信息：
{background}

请使用 read_code 和 execute_script 工具进行验证，检查：
1. 代码是否能够成功编译/构建
2. 功能是否经过实际运行验证
3. 所有测试是否通过
4. 代码是否符合任务描述的要求

如果存在编译错误、运行时错误或测试失败，必须明确标记为未完成，并详细说明原因。
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
                detailed_explanation = None

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

                # 提取说明（可能是"详细说明"或"说明"）
                explanation_match = re.search(
                    r"\*\*说明\*\*：\s*\n(.*?)(?=\n\n|\*\*|$)",
                    verification_result_str,
                    re.DOTALL,
                )
                if explanation_match:
                    detailed_explanation = explanation_match.group(1).strip()
                else:
                    # 尝试查找"详细说明"
                    explanation_match = re.search(
                        r"\*\*详细说明\*\*：\s*\n(.*?)(?=\n\n|\*\*|$)",
                        verification_result_str,
                        re.DOTALL,
                    )
                    if explanation_match:
                        detailed_explanation = explanation_match.group(1).strip()

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
                    # 使用详细说明作为失败原因，如果没有则使用整个结果
                    failure_reason = (
                        detailed_explanation
                        if detailed_explanation
                        else verification_result_str
                    )
                    PrettyOutput.auto_print(
                        f"❌ 任务 [{task.task_name}] 验证未通过：{failure_reason[:200]}..."
                    )
                    return False, failure_reason
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
    ):
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

    description = f"""任务列表管理工具。用于在 PLAN 阶段拆分复杂任务为多个子任务，并管理任务执行。

**⚠️ 重要：任务描述和背景信息要求**
- **任务描述（task_desc）必须包含**：
  - **约束条件**：明确任务执行的技术约束、环境限制、性能要求等
  - **必须要求**：明确任务必须完成的具体要求、必须遵循的规范、必须实现的功能等
  - **禁止事项**：明确任务执行中禁止的操作、禁止使用的技术、禁止修改的内容等
  - **验证标准**：明确任务完成的验证方式、验收标准、测试要求等
- **背景信息（background）必须包含**：
  - **全局约束条件**：所有子任务必须遵循的技术约束、环境限制、性能要求等
  - **必须要求**：所有子任务必须完成的要求、必须遵循的规范、必须实现的功能等
  - **禁止事项**：所有子任务执行中禁止的操作、禁止使用的技术、禁止修改的内容等
  - **验证标准**：所有子任务的统一验证方式、验收标准、测试要求等
- 任务描述和背景信息应该清晰、具体、可执行，确保任务执行者有明确的指导

**基本使用流程：**
1. `add_tasks`: 添加任务（如果 Agent 还没有任务列表，会自动创建；推荐在 PLAN 阶段使用，一次性添加所有子任务。创建任务列表时必须提供 main_goal 参数）
2. `execute_task`: 执行任务（自动创建子 Agent 执行，**执行完成后会自动更新任务状态为 completed 或 failed**）
3. `get_task_list_summary`: 查看任务列表状态

**重要说明：每个 Agent 只有一个任务列表**
- 每个 Agent 只能拥有一个任务列表，系统会自动管理
- **不需要提供 `task_list_id` 参数**，系统会自动从 Agent 的上下文中获取
- 如果 Agent 还没有任务列表，调用 `add_tasks` 时会自动创建（使用第一个任务的名称作为 main_goal）

**任务状态自动管理：**
- 执行开始时：任务状态自动更新为 `running`
- 执行完成时：任务状态自动更新为 `completed`，执行结果保存到 `actual_output`
- 执行失败时：任务状态自动更新为 `failed`，错误信息保存到 `actual_output`
- 可通过 `update_task` 手动更新任务状态和其他属性

**核心操作：**
- `add_tasks`: 添加任务（支持单个或多个任务，推荐在 PLAN 阶段使用，一次性添加所有子任务；如果任务列表不存在会自动创建，可使用 main_goal 指定核心目标）
- `execute_task`: 执行任务（根据 agent_type 自动创建子 Agent，**执行完成后会自动更新任务状态**）
- `update_task`: 更新任务属性（包括任务名称、描述、优先级、预期输出、依赖关系、状态和实际输出）
- `get_task_detail`: 获取任务详情
- `get_task_list_summary`: 获取任务列表摘要

**任务类型（agent_type）选择规则：**
- **简单任务使用 `main`**：对于简单、直接的任务（如单次文件读取、简单的单步操作、单一工具调用等），**必须使用 `main`**，由主 Agent 直接执行，**不要将简单任务拆分为子任务**。避免对简单任务进行不必要的拆分，防止出现无限拆分的问题。
- **复杂任务使用 `sub`**：对于**真正复杂**的任务（需要多个步骤、涉及多个文件、需要协调多个子任务、有明确的依赖关系等），应该使用 `sub` 类型，系统会自动处理任务执行。
  - `main`: 由主 Agent 直接执行（**简单任务必须使用此类型**）
  - `sub`: 由系统智能处理复杂任务（**复杂任务推荐使用此类型**）

**⚠️ 重要提醒：避免过度拆分**
- **不要过度拆分任务**：任务拆分应该保持合理的粒度，避免将简单任务拆分成过多过细的子任务
- **平衡信息传递与效率**：过度拆分会增加信息传递负担，可能导致上下文丢失和执行效率降低
- **优先考虑主Agent执行**：对于可以在1-2步内完成的任务，优先使用 `main` 类型由主Agent直接执行
- **评估拆分必要性**：在拆分任务前，评估是否真的需要创建子Agent，是否可以由主Agent更高效地完成

**📊 数据量切分策略（避免长上下文目标偏移）**
- **按数据切分任务**：当任务涉及大量数据时（如处理多个文件、多个目录、大量代码文件等），应该按照数据维度切分为多个子任务，由 sub agent 分别完成
- **切分维度示例**：
  - **按文件目录切分**：如果需要对多个目录进行处理，每个目录创建一个子任务（如"处理 src/auth/ 目录"、"处理 src/api/ 目录"）
  - **按文件列表切分**：如果需要对大量文件进行处理，将文件列表分批切分（如"处理文件列表1-50"、"处理文件列表51-100"）
  - **按功能模块切分**：如果涉及多个功能模块，每个模块创建一个子任务（如"处理用户认证模块"、"处理权限管理模块"）
  - **按数据范围切分**：如果涉及大量数据，按数据范围切分（如"处理前1000条记录"、"处理后1000条记录"）
- **切分的好处**：
  - ✅ **避免长上下文目标偏移**：每个子任务专注于处理部分数据，上下文更聚焦，避免在处理大量数据时偏离目标
  - ✅ **提高执行效率**：多个子任务可以并行执行（如果无依赖关系），提高整体执行效率
  - ✅ **降低单次任务复杂度**：每个子任务处理的数据量更小，更容易成功完成
  - ✅ **便于错误恢复**：如果某个子任务失败，只需重试该子任务，不影响其他已完成的任务
- **切分示例**：
  ```json
  {{
    "action": "add_tasks",
    "main_goal": "重构整个项目的错误处理机制",
    "tasks_info": [
      {{
        "task_name": "重构 src/auth/ 目录的错误处理",
        "task_desc": "处理 src/auth/ 目录下的所有文件，统一错误处理机制",
        "priority": 5,
        "expected_output": "src/auth/ 目录下所有文件的错误处理已重构",
        "agent_type": "sub"
      }},
      {{
        "task_name": "重构 src/api/ 目录的错误处理",
        "task_desc": "处理 src/api/ 目录下的所有文件，统一错误处理机制",
        "priority": 5,
        "expected_output": "src/api/ 目录下所有文件的错误处理已重构",
        "agent_type": "sub"
      }},
      {{
        "task_name": "重构 src/utils/ 目录的错误处理",
        "task_desc": "处理 src/utils/ 目录下的所有文件，统一错误处理机制",
        "priority": 4,
        "expected_output": "src/utils/ 目录下所有文件的错误处理已重构",
        "agent_type": "sub"
      }}
    ]
  }}
  ```
- **切分原则**：
  - 每个子任务处理的数据量应该适中（建议每个子任务处理10-50个文件，或单个目录）
  - 子任务之间应该相对独立，减少依赖关系
  - 如果子任务之间有依赖，使用 `dependencies` 参数明确指定
  - 切分后的子任务都应该使用 `agent_type: "sub"`，由系统自动创建子 Agent 执行

**全局背景信息：**
- 使用 `background` 参数为所有子任务提供统一的背景信息，这些信息会自动附加到每个子任务的描述中
- **必须包含以下信息**：
  - **全局约束条件**：所有子任务必须遵循的技术约束、环境限制、性能要求等
  - **必须要求**：所有子任务必须完成的要求、必须遵循的规范、必须实现的功能等
  - **禁止事项**：所有子任务执行中禁止的操作、禁止使用的技术、禁止修改的内容等
  - **验证标准**：所有子任务的统一验证方式、验收标准、测试要求等
- 适用于提供全局上下文、统一规范等公共信息

**依赖关系：**
- 在 `add_tasks` 时，任务的 `dependencies` 可以引用本次批次中的任务名称（系统会自动匹配）
- 或者引用已存在的任务ID

**使用示例（推荐）：**

示例1：功能模块拆分
{ot("TOOL_CALL")}
{{
  "want": "添加用户登录功能相关任务",
  "name": "task_list_manager",
  "arguments": {{
    "action": "add_tasks",
    "main_goal": "实现完整的用户登录功能模块",  // ⚠️ 必填：任务列表的核心目标
    "tasks_info": [
      {{
        "task_name": "设计数据库表结构",
        "task_desc": "创建用户表和会话表",
        "priority": 5,
        "expected_output": "数据库表结构设计文档",
        "agent_type": "sub"
      }},
      {{
        "task_name": "实现登录接口",
        "task_desc": "实现用户登录API",
        "priority": 4,
        "expected_output": "登录接口代码",
        "agent_type": "sub",
        "dependencies": ["设计数据库表结构"]
      }}
    ]
  }}
}}
{ct("TOOL_CALL")}

示例2：按数据量切分（处理大量文件/目录）
{ot("TOOL_CALL")}
{{
  "want": "重构整个项目的错误处理机制",
  "name": "task_list_manager",
  "arguments": {{
    "action": "add_tasks",
    "main_goal": "重构整个项目的错误处理机制，统一错误处理方式",
    "tasks_info": [
      {{
        "task_name": "重构 src/auth/ 目录的错误处理",
        "task_desc": "处理 src/auth/ 目录下的所有文件，统一错误处理机制",
        "priority": 5,
        "expected_output": "src/auth/ 目录下所有文件的错误处理已重构",
        "agent_type": "sub"
      }},
      {{
        "task_name": "重构 src/api/ 目录的错误处理",
        "task_desc": "处理 src/api/ 目录下的所有文件，统一错误处理机制",
        "priority": 5,
        "expected_output": "src/api/ 目录下所有文件的错误处理已重构",
        "agent_type": "sub"
      }},
      {{
        "task_name": "重构 src/utils/ 目录的错误处理",
        "task_desc": "处理 src/utils/ 目录下的所有文件，统一错误处理机制",
        "priority": 4,
        "expected_output": "src/utils/ 目录下所有文件的错误处理已重构",
        "agent_type": "sub"
      }}
    ]
  }}
}}
{ct("TOOL_CALL")}

🚨 **强制执行规范：additional_info 参数**

## ❗ 绝对必要：execute_task 时必须提供 additional_info

**⚠️ 警告：如果未提供有效的 additional_info 参数，任务执行将立即失败并返回错误**

---

## 🎯 强制执行规则

### 1️⃣ 零容忍政策
- **不能为空字符串**：`""` ❌ 会导致："additional_info 参数不能为空"
- **不能为None值**：`None` ❌ 会导致："缺少 additional_info 参数"  
- **不能为纯空白**：`"   "` ❌ 会导致：执行失败
- **必须包含实际内容**：最少10个有意义字符 ✅

### 2️⃣ 执行前强制检查清单
在使用 `execute_task` 前，必须确认：
- ✅ `additional_info` 已定义为非空字符串
- ✅ 内容包含任务的实际上下文信息
- ✅ 长度在合理范围内（建议50-1000字符）
- ✅ 使用场景相关的具体内容

---

## 📋 标准格式模板

### 🚀 execute_task 时的 additional_info 模板：
```
任务背景：[具体描述当前要解决的核心问题]

关键信息：
- 目标文件：[具体文件路径和行号范围]
- 功能需求：[要新增/修改/修复的具体功能]
- 约束条件：[技术限制、兼容性要求等]
- 预期结果：[完成后的具体表现]

特殊要求：
- [任何特殊的实现要求或注意事项]
```


---

## 🎯 实际使用示例

### ✅ 正确示例（任务执行）：
```json
{{
        "action": "execute_task",
  "task_id": "task_123",
  "additional_info": "任务背景：修复用户登录功能的JWT token验证问题. 关键信息：目标文件src/auth/jwt_handler.py第45-67行, 功能需求是修复token过期后未正确刷新的bug, 约束条件必须兼容Python3.8+且不能修改API接口, 预期结果token过期时自动刷新并重定向到首页. 特殊要求：保留现有token格式不变, 添加适当的单元测试"
}}
```

### ❌ 错误示例（会导致失败）：
```json
{{
        "action": "execute_task",
  "task_id": "task_123",
  "additional_info": ""  // ❌ 空字符串，立即失败
}}

{{
        "action": "execute_task",
  "task_id": "task_123",
  "additional_info": "修复bug"  // ❌ 过于简单，缺乏上下文
}}
```

### ✅ 正确示例（获取详情）：
```json
{{
        "action": "get_task_detail",
  "task_id": "task_123"
}}
```

---

## 🔧 常见错误预防

| 错误模式 | 系统响应 | 立即修复方法 |
|---------|----------|-------------|
| `additional_info: null` | ❌ "缺少 additional_info 参数" | 提供字符串内容 |
| `additional_info: ""` | ❌ "additional_info 参数不能为空" | 添加有意义内容 |
| `additional_info: "test"` | ⚠️ 内容不足影响执行效果 | 提供详细上下文 |

---

## 🚀 执行前强制检查口诀

**每次执行前必须确认：**
> "execute_task 三步检查：
>  1️⃣ 有任务ID ✅
>  2️⃣ 有additional_info ✅
>  3️⃣ 内容具体有意义 ✅"

**快速验证：**
```python
# 执行前自问：
additional_info = "..."  # 实际内容
assert additional_info and len(additional_info.strip()) > 10, "内容不足"
```

**重要提醒：简单任务不需要拆分，必须使用 `main` 类型**
- 简单任务判断标准：如果任务可以在1-3步内完成、只涉及单个文件修改、或只需要单次工具调用
- 简单任务无需拆分：对于简单任务，绝对不要创建任务列表，直接使用 agent_type: "main" 由主 Agent 立即执行
- 禁止过度拆分：简单任务创建子Agent会导致不必要的上下文切换和信息传递负担，大幅降低执行效率
- 快速执行原则：简单任务应该立即执行，避免任何任务管理开销
- 只有真正复杂的任务（需要多个步骤、涉及多个文件、需要协调多个子任务等）才使用子Agent"""

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
                            "description": "预期输出",
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
        self, args: Dict, task_list_manager: Any, agent_id: str, agent: Any
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
        args: Dict,
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
        self, args: Dict, task_list_manager: Any, agent: Any
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
        args: Dict,
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
            # 合并任务描述和附加信息
            merged_description = task.task_desc
            if additional_info and str(additional_info).strip():
                # 使用清晰的分隔符合并原有描述和附加信息
                separator = "\n" + "=" * 50 + "\n"
                merged_description = (
                    f"{task.task_desc}{separator}附加信息:\n{additional_info}"
                )

                # 实际更新任务的desc字段，使打印时可见
                task.task_desc = merged_description

            # 构建任务执行内容
            task_content = f"""任务名称: {task.task_name}

任务描述:
{merged_description}

预期输出:
{task.expected_output}"""

            # 构建背景信息
            background_parts = []

            # 获取额外的背景信息（如果提供）
            additional_background = args.get("additional_background")
            if additional_background:
                background_parts.append(f"额外背景信息: {additional_background}")

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
                    background_parts.append(
                        "依赖任务信息:\n" + "\n\n".join(dep_outputs)
                    )

            # 3. 获取其他已完成任务的摘要信息（作为额外上下文，帮助理解整体进度）
            if task_list:
                completed_tasks = [
                    t
                    for t in task_list.tasks.values()
                    if t.status == TaskStatus.COMPLETED
                    and t.task_id != task_id
                    and t.task_id not in (task.dependencies or [])
                ]
                if completed_tasks:
                    # 只包含前3个已完成任务的简要信息，避免上下文过长
                    completed_summary = []
                    for completed_task in completed_tasks[:3]:
                        summary = f"- [{completed_task.task_name}]: {completed_task.task_desc}"
                        if completed_task.actual_output:
                            # 只取输出的前200字符作为摘要
                            output_preview = completed_task.actual_output[:200]
                            if len(completed_task.actual_output) > 200:
                                output_preview += "..."
                            summary += f"\n  输出摘要: {output_preview}"
                        completed_summary.append(summary)

                    if completed_summary:
                        background_parts.append(
                            "其他已完成任务（参考信息）:\n"
                            + "\n".join(completed_summary)
                        )

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
                    # 验证未通过，标记为 failed
                    task_list_manager.update_task_status(
                        task_list_id=task_list_id,
                        task_id=task_id,
                        status="failed",
                        agent_id=agent_id,
                        is_main_agent=is_main_agent,
                        actual_output=processed_result,
                    )
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
        args: Dict,
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
                if not (1 <= new_priority <= 5):
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "priority 必须在 1-5 之间",
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
