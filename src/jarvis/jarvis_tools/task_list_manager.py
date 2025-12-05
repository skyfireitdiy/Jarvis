# -*- coding: utf-8 -*-
"""任务列表管理工具。

该工具允许 LLM 管理任务列表，包括创建任务列表、添加任务、更新任务状态等。
"""

import json
from typing import Any, Dict

from jarvis.jarvis_utils.config import get_max_input_token_count
from jarvis.jarvis_agent.task_list import (
    DEFAULT_MAX_TASK_OUTPUT_LENGTH,
)


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
            model_group = None
            if agent:
                model_group = getattr(agent, "model_group", None)

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

    description = """管理任务列表的工具。支持创建任务列表、添加任务、获取任务、更新任务状态、更新任务列表、更新任务、获取任务列表摘要、执行任务等功能。
    
    使用场景：
    1. 当用户提出复杂需求时，可以创建任务列表并拆解为多个子任务
    2. 通过任务列表管理任务的执行顺序和依赖关系
    3. 跟踪任务执行状态和结果
    4. 自动为每个任务创建独立的 Agent 执行（根据任务的 agent_type）
    5. 动态更新任务列表和任务属性（如调整优先级、修改描述等）
    
    任务执行说明：
    - agent_type 为 "main": 由主 Agent 直接执行，不创建子 Agent
    - agent_type 为 "sub": 自动创建 CodeAgent 子 Agent 执行任务
    - agent_type 为 "tool": 自动创建通用 Agent 子 Agent 执行任务
    - 执行时会自动处理任务状态转换（pending -> running -> completed/failed）
    - 执行结果会自动保存到任务的 actual_output 字段
    
    更新功能说明：
    - update_task_list: 更新任务列表属性（main_goal、max_active_tasks）
    - update_task: 更新任务属性（task_name、task_desc、priority、expected_output、dependencies、timeout、retry_limit）
    """

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "create_task_list",
                    "add_task",
                    "get_next_task",
                    "update_task_status",
                    "get_task_detail",
                    "get_task_list_summary",
                    "rollback_task_list",
                    "execute_task",
                    "update_task_list",
                    "update_task",
                ],
                "description": "要执行的操作",
            },
            "task_list_id": {
                "type": "string",
                "description": "任务列表ID（create_task_list 操作不需要此参数）",
            },
            "main_goal": {
                "type": "string",
                "description": "用户核心需求（仅 create_task_list 需要）",
            },
            "task_info": {
                "type": "object",
                "description": "任务信息（仅 add_task 需要）",
                "properties": {
                    "task_name": {
                        "type": "string",
                        "description": "任务名称（10-50字符）",
                    },
                    "task_desc": {
                        "type": "string",
                        "description": "任务描述（50-200字符）",
                    },
                    "priority": {
                        "type": "integer",
                        "description": "优先级（1-5，5为最高）",
                    },
                    "expected_output": {"type": "string", "description": "预期输出"},
                    "agent_type": {
                        "type": "string",
                        "enum": ["main", "sub", "tool"],
                        "description": "Agent类型",
                    },
                    "dependencies": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "依赖的任务ID列表（可选）",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "超时时间（秒，默认300）",
                    },
                    "retry_limit": {
                        "type": "integer",
                        "description": "最大重试次数（默认3）",
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
            "task_id": {
                "type": "string",
                "description": "任务ID（execute_task/update_task/update_task_status/get_task_detail 需要）",
            },
            "status": {
                "type": "string",
                "enum": ["pending", "running", "completed", "failed", "abandoned"],
                "description": "任务状态（update_task_status 需要）",
            },
            "actual_output": {
                "type": "string",
                "description": "实际输出（update_task_status 可选）",
            },
            "version": {
                "type": "integer",
                "description": "版本号（rollback_task_list 需要）",
            },
            "task_list_info": {
                "type": "object",
                "description": "任务列表更新信息（update_task_list 需要）",
                "properties": {
                    "main_goal": {
                        "type": "string",
                        "description": "更新后的全局目标（可选）",
                    },
                    "max_active_tasks": {
                        "type": "integer",
                        "description": "更新后的最大活跃任务数（可选，5-20）",
                    },
                },
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
                        "description": "更新后的任务描述（可选）",
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
                    "timeout": {
                        "type": "integer",
                        "description": "更新后的超时时间（可选，秒）",
                    },
                    "retry_limit": {
                        "type": "integer",
                        "description": "更新后的最大重试次数（可选，1-5）",
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

            # 获取 CodeAgent 实例
            code_agent = getattr(agent, "_code_agent", None)
            if not code_agent:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "无法获取 CodeAgent 实例，任务列表功能仅在 CodeAgent 中可用",
                }

            # 获取任务列表管理器
            task_list_manager = getattr(code_agent, "task_list_manager", None)
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
            if action == "create_task_list":
                return self._handle_create_task_list(args, task_list_manager, agent_id)

            elif action == "add_task":
                return self._handle_add_task(args, task_list_manager, agent_id)

            elif action == "get_next_task":
                return self._handle_get_next_task(args, task_list_manager, agent_id)

            elif action == "update_task_status":
                return self._handle_update_task_status(
                    args, task_list_manager, agent_id, is_main_agent
                )

            elif action == "get_task_detail":
                return self._handle_get_task_detail(
                    args, task_list_manager, agent_id, is_main_agent
                )

            elif action == "get_task_list_summary":
                return self._handle_get_task_list_summary(args, task_list_manager)

            elif action == "rollback_task_list":
                return self._handle_rollback_task_list(
                    args, task_list_manager, agent_id
                )

            elif action == "execute_task":
                return self._handle_execute_task(
                    args, task_list_manager, agent_id, is_main_agent, agent
                )

            elif action == "update_task_list":
                return self._handle_update_task_list(args, task_list_manager, agent_id)

            elif action == "update_task":
                return self._handle_update_task(
                    args, task_list_manager, agent_id, is_main_agent
                )

            else:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"未知的操作: {action}",
                }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"执行任务列表操作失败: {str(e)}",
            }

    def _handle_create_task_list(
        self, args: Dict, task_list_manager: Any, agent_id: str
    ) -> Dict[str, Any]:
        """处理创建任务列表"""
        main_goal = args.get("main_goal")
        if not main_goal:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少 main_goal 参数",
            }

        task_list_id, success, error_msg = task_list_manager.create_task_list(
            main_goal=main_goal, agent_id=agent_id
        )

        if success:
            result = {
                "task_list_id": task_list_id,
                "main_goal": main_goal,
                "message": "任务列表创建成功",
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
                "stderr": f"创建任务列表失败: {error_msg}",
            }

    def _handle_add_task(
        self, args: Dict, task_list_manager: Any, agent_id: str
    ) -> Dict[str, Any]:
        """处理添加任务"""
        task_list_id = args.get("task_list_id")
        if not task_list_id:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少 task_list_id 参数",
            }

        task_info = args.get("task_info")
        if not task_info:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少 task_info 参数",
            }

        task_id, success, error_msg = task_list_manager.add_task(
            task_list_id=task_list_id, task_info=task_info, agent_id=agent_id
        )

        if success:
            result = {
                "task_id": task_id,
                "task_list_id": task_list_id,
                "message": "任务添加成功",
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
                "stderr": f"添加任务失败: {error_msg}",
            }

    def _handle_get_next_task(
        self, args: Dict, task_list_manager: Any, agent_id: str
    ) -> Dict[str, Any]:
        """处理获取下一个任务"""
        task_list_id = args.get("task_list_id")
        if not task_list_id:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少 task_list_id 参数",
            }

        task, msg = task_list_manager.get_next_task(
            task_list_id=task_list_id, agent_id=agent_id
        )

        if task:
            result = {
                "task": task.to_dict(),
                "message": "获取任务成功",
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
                "stderr": msg or "获取任务失败",
            }

    def _handle_update_task_status(
        self, args: Dict, task_list_manager: Any, agent_id: str, is_main_agent: bool
    ) -> Dict[str, Any]:
        """处理更新任务状态"""
        task_list_id = args.get("task_list_id")
        task_id = args.get("task_id")
        status = args.get("status")
        actual_output = args.get("actual_output")

        if not task_list_id:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少 task_list_id 参数",
            }

        if not task_id:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少 task_id 参数",
            }

        if not status:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少 status 参数",
            }

        success, msg = task_list_manager.update_task_status(
            task_list_id=task_list_id,
            task_id=task_id,
            status=status,
            agent_id=agent_id,
            is_main_agent=is_main_agent,
            actual_output=actual_output,
        )

        if success:
            result = {
                "task_id": task_id,
                "status": status,
                "message": msg or "任务状态更新成功",
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
                "stderr": msg or "更新任务状态失败",
            }

    def _handle_get_task_detail(
        self, args: Dict, task_list_manager: Any, agent_id: str, is_main_agent: bool
    ) -> Dict[str, Any]:
        """处理获取任务详情"""
        task_list_id = args.get("task_list_id")
        task_id = args.get("task_id")

        if not task_list_id:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少 task_list_id 参数",
            }

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
        self, args: Dict, task_list_manager: Any
    ) -> Dict[str, Any]:
        """处理获取任务列表摘要"""
        task_list_id = args.get("task_list_id")
        if not task_list_id:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少 task_list_id 参数",
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

    def _handle_rollback_task_list(
        self, args: Dict, task_list_manager: Any, agent_id: str
    ) -> Dict[str, Any]:
        """处理回滚任务列表"""
        task_list_id = args.get("task_list_id")
        version = args.get("version")

        if not task_list_id:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少 task_list_id 参数",
            }

        if version is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少 version 参数",
            }

        success, msg = task_list_manager.rollback_task_list(
            task_list_id=task_list_id, version=version, agent_id=agent_id
        )

        if success:
            result = {
                "task_list_id": task_list_id,
                "version": version,
                "message": msg or "任务列表回滚成功",
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
                "stderr": msg or "回滚任务列表失败",
            }

    def _handle_execute_task(
        self,
        args: Dict,
        task_list_manager: Any,
        agent_id: str,
        is_main_agent: bool,
        parent_agent: Any,
    ) -> Dict[str, Any]:
        """处理执行任务（自动创建子 Agent 执行）"""
        task_list_id = args.get("task_list_id")
        task_id = args.get("task_id")

        if not task_list_id:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少 task_list_id 参数",
            }

        if not task_id:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少 task_id 参数",
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
            # 构建任务执行内容
            task_content = f"""任务名称: {task.task_name}

任务描述:
{task.task_desc}

预期输出:
{task.expected_output}
"""

            # 如果有依赖任务，获取依赖任务的输出作为背景信息
            background_parts = []
            if task.dependencies:
                for dep_id in task.dependencies:
                    dep_task, dep_success, _ = task_list_manager.get_task_detail(
                        task_list_id=task_list_id,
                        task_id=dep_id,
                        agent_id=agent_id,
                        is_main_agent=is_main_agent,
                    )
                    if dep_success and dep_task and dep_task.actual_output:
                        background_parts.append(
                            f"依赖任务 [{dep_task.task_name}] 的输出:\n{dep_task.actual_output}"
                        )

            # 获取任务列表的 main_goal 作为全局上下文
            task_list = task_list_manager.get_task_list(task_list_id)
            if task_list:
                background_parts.insert(0, f"全局目标: {task_list.main_goal}")

            background = "\n\n".join(background_parts) if background_parts else ""

            # 根据 agent_type 创建相应的子 Agent 执行任务
            execution_result = None
            if task.agent_type.value == "main":
                # 主 Agent 执行：直接在当前 Agent 中执行（不创建子 Agent）
                # 这里返回任务信息，让主 Agent 自己处理
                result = {
                    "task_id": task_id,
                    "task_name": task.task_name,
                    "task_desc": task.task_desc,
                    "expected_output": task.expected_output,
                    "background": background,
                    "message": "任务已标记为 running，请主 Agent 自行执行",
                    "note": "主 Agent 类型的任务应由当前 Agent 直接执行，而不是创建子 Agent",
                }
                return {
                    "success": True,
                    "stdout": json.dumps(result, ensure_ascii=False, indent=2),
                    "stderr": "",
                }

            elif task.agent_type.value == "sub":
                # 子 Agent 执行：使用 sub_code_agent 工具
                try:
                    # 获取 sub_code_agent 工具
                    tool_registry = parent_agent.get_tool_registry()
                    if not tool_registry:
                        raise Exception("无法获取工具注册表")

                    sub_code_agent_tool = tool_registry.get_tool("sub_code_agent")
                    if not sub_code_agent_tool:
                        raise Exception("sub_code_agent 工具不可用")

                    # 调用 sub_code_agent 执行任务
                    tool_result = sub_code_agent_tool.func(
                        {
                            "task": task_content,
                            "background": background,
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

            elif task.agent_type.value == "tool":
                # 工具类型：使用 sub_agent 工具（通用 Agent）
                try:
                    # 获取 sub_agent 工具
                    tool_registry = parent_agent.get_tool_registry()
                    if not tool_registry:
                        raise Exception("无法获取工具注册表")

                    sub_agent_tool = tool_registry.get_tool("sub_agent")
                    if not sub_agent_tool:
                        raise Exception("sub_agent 工具不可用")

                    # 构建系统提示词和总结提示词
                    system_prompt = f"""你是一个专业的任务执行助手。

当前任务: {task.task_name}

任务描述: {task.task_desc}

预期输出: {task.expected_output}

请专注于完成这个任务，完成后提供清晰的输出结果。
"""

                    summary_prompt = f"总结任务 [{task.task_name}] 的执行结果，包括完成的工作和输出内容。"

                    # 调用 sub_agent 执行任务
                    tool_result = sub_agent_tool.func(
                        {
                            "task": task_content,
                            "background": background,
                            "name": f"task_{task_id}",
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
                            "stderr": f"工具 Agent 执行失败: {tool_result.get('stderr', '未知错误')}",
                        }

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
                        "stderr": f"创建工具 Agent 执行任务失败: {str(e)}",
                    }

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
                print(
                    f"⚠️ 任务 {task_id} 的执行结果过长（{len(execution_result)} 字符），"
                    f"已截断为 {len(truncated_result)} 字符（基于剩余token限制：{max_output_length} 字符）"
                )

            # 执行成功，更新任务状态为 completed
            task_list_manager.update_task_status(
                task_list_id=task_list_id,
                task_id=task_id,
                status="completed",
                agent_id=agent_id,
                is_main_agent=is_main_agent,
                actual_output=processed_result,
            )

            # 构建返回结果（包含摘要信息）
            # 预览长度：基于最大输出长度的10%，但不超过500字符
            preview_length = min(int(max_output_length * 0.1), 500)
            result = {
                "task_id": task_id,
                "task_name": task.task_name,
                "status": "completed",
                "output_length": len(processed_result),
                "output_preview": (
                    processed_result[:preview_length] + "..."
                    if len(processed_result) > preview_length
                    else processed_result
                ),
                "message": "任务执行成功，结果已保存到任务的 actual_output 字段",
                "note": "完整结果可通过 get_task_detail 获取",
            }
            return {
                "success": True,
                "stdout": json.dumps(result, ensure_ascii=False, indent=2),
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

    def _handle_update_task_list(
        self, args: Dict, task_list_manager: Any, agent_id: str
    ) -> Dict[str, Any]:
        """处理更新任务列表属性"""
        task_list_id = args.get("task_list_id")
        task_list_info = args.get("task_list_info", {})

        if not task_list_id:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少 task_list_id 参数",
            }

        if not task_list_info:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少 task_list_info 参数",
            }

        try:
            with task_list_manager._lock:
                if task_list_id not in task_list_manager.task_lists:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "任务列表不存在",
                    }

                task_list = task_list_manager.task_lists[task_list_id]

                # 更新 main_goal
                if "main_goal" in task_list_info:
                    new_main_goal = task_list_info["main_goal"]
                    if not (50 <= len(new_main_goal) <= 200):
                        return {
                            "success": False,
                            "stdout": "",
                            "stderr": "main_goal 长度必须在 50-200 字符之间",
                        }
                    task_list.main_goal = new_main_goal

                # 更新 max_active_tasks
                if "max_active_tasks" in task_list_info:
                    new_max_active = task_list_info["max_active_tasks"]
                    if not (5 <= new_max_active <= 20):
                        return {
                            "success": False,
                            "stdout": "",
                            "stderr": "max_active_tasks 必须在 5-20 之间",
                        }
                    task_list.max_active_tasks = new_max_active

                # 更新版本号
                task_list.version += 1

                # 保存快照
                task_list_manager._save_snapshot(task_list_id, task_list)

                result = {
                    "task_list_id": task_list_id,
                    "version": task_list.version,
                    "main_goal": task_list.main_goal,
                    "max_active_tasks": task_list.max_active_tasks,
                    "message": "任务列表更新成功",
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
                "stderr": f"更新任务列表失败: {str(e)}",
            }

    def _handle_update_task(
        self, args: Dict, task_list_manager: Any, agent_id: str, is_main_agent: bool
    ) -> Dict[str, Any]:
        """处理更新任务属性"""
        task_list_id = args.get("task_list_id")
        task_id = args.get("task_id")
        task_update_info = args.get("task_update_info", {})

        if not task_list_id:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少 task_list_id 参数",
            }

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
                if not (10 <= len(new_name) <= 50):
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "task_name 长度必须在 10-50 字符之间",
                    }
                update_kwargs["task_name"] = new_name

            if "task_desc" in task_update_info:
                new_desc = task_update_info["task_desc"]
                if not (50 <= len(new_desc) <= 200):
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "task_desc 长度必须在 50-200 字符之间",
                    }
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

            if "timeout" in task_update_info:
                new_timeout = task_update_info["timeout"]
                if new_timeout < 60:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "timeout 必须 >= 60 秒",
                    }
                update_kwargs["timeout"] = new_timeout

            if "retry_limit" in task_update_info:
                new_retry_limit = task_update_info["retry_limit"]
                if not (1 <= new_retry_limit <= 5):
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "retry_limit 必须在 1-5 之间",
                    }
                update_kwargs["retry_limit"] = new_retry_limit

            # 执行更新
            if not task_list.update_task(task_id, **update_kwargs):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "更新任务失败",
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
