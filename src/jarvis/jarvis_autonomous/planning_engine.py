"""计划制定引擎模块

根据目标自动生成执行计划，与现有task_list系统深度整合。
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from jarvis.jarvis_agent.task_list import Task, TaskList, TaskStatus, AgentType
from jarvis.jarvis_autonomous.goal_manager import Goal


class PlanStatus(Enum):
    """计划状态枚举"""

    DRAFT = "draft"  # 草稿
    ACTIVE = "active"  # 活跃
    COMPLETED = "completed"  # 已完成
    ABANDONED = "abandoned"  # 已放弃


@dataclass
class PlanTemplate:
    """计划模板

    预定义的任务模板，用于快速生成计划。
    """

    name: str
    description: str
    steps: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "description": self.description,
            "steps": self.steps,
        }


@dataclass
class Plan:
    """执行计划

    表示达成目标的完整执行计划，与TaskList关联。
    """

    id: str
    goal_id: str  # 关联的目标ID
    name: str  # 计划名称
    description: str  # 计划描述
    task_list_id: Optional[str] = None  # 关联的TaskList ID
    status: PlanStatus = PlanStatus.DRAFT
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    estimated_completion: Optional[datetime] = None  # 预计完成时间
    actual_completion: Optional[datetime] = None  # 实际完成时间
    version: int = 1  # 计划版本
    metadata: dict[str, Any] = field(default_factory=dict)  # 元数据

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "goal_id": self.goal_id,
            "name": self.name,
            "description": self.description,
            "task_list_id": self.task_list_id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "estimated_completion": (
                self.estimated_completion.isoformat()
                if self.estimated_completion
                else None
            ),
            "actual_completion": (
                self.actual_completion.isoformat() if self.actual_completion else None
            ),
            "version": self.version,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Plan":
        """从字典创建"""
        return cls(
            id=data["id"],
            goal_id=data["goal_id"],
            name=data["name"],
            description=data["description"],
            task_list_id=data.get("task_list_id"),
            status=PlanStatus(data.get("status", "draft")),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            estimated_completion=(
                datetime.fromisoformat(data["estimated_completion"])
                if data.get("estimated_completion")
                else None
            ),
            actual_completion=(
                datetime.fromisoformat(data["actual_completion"])
                if data.get("actual_completion")
                else None
            ),
            version=data.get("version", 1),
            metadata=data.get("metadata", {}),
        )


class PlanningEngine:
    """计划制定引擎

    根据目标自动生成执行计划，生成的任务与现有task_list系统兼容。
    """

    def __init__(self) -> None:
        """初始化计划制定引擎"""
        self.plans: dict[str, Plan] = {}
        self._task_counter = 0  # 任务ID计数器
        # 预定义的计划模板
        self.templates: dict[str, PlanTemplate] = {
            "software_development": PlanTemplate(
                name="软件开发",
                description="标准软件开发流程",
                steps=[
                    {
                        "name": "需求分析",
                        "desc": "分析和理解需求，明确目标和约束",
                        "agent_type": "main",
                    },
                    {
                        "name": "技术设计",
                        "desc": "设计技术方案，确定架构和实现路径",
                        "agent_type": "main",
                    },
                    {
                        "name": "代码实现",
                        "desc": "按照设计方案实现代码",
                        "agent_type": "sub",
                    },
                    {
                        "name": "测试验证",
                        "desc": "编写测试用例，验证功能正确性",
                        "agent_type": "sub",
                    },
                    {
                        "name": "代码审查",
                        "desc": "审查代码质量，确保符合规范",
                        "agent_type": "main",
                    },
                ],
            ),
            "bug_fix": PlanTemplate(
                name="Bug修复",
                description="Bug修复流程",
                steps=[
                    {
                        "name": "问题分析",
                        "desc": "分析问题原因，定位bug位置",
                        "agent_type": "main",
                    },
                    {
                        "name": "修复实现",
                        "desc": "实现修复方案",
                        "agent_type": "sub",
                    },
                    {
                        "name": "测试验证",
                        "desc": "验证修复效果，确保问题解决",
                        "agent_type": "main",
                    },
                ],
            ),
            "refactoring": PlanTemplate(
                name="代码重构",
                description="代码重构流程",
                steps=[
                    {
                        "name": "代码分析",
                        "desc": "分析现有代码结构和问题",
                        "agent_type": "main",
                    },
                    {
                        "name": "重构设计",
                        "desc": "设计重构方案",
                        "agent_type": "main",
                    },
                    {
                        "name": "重构实现",
                        "desc": "实施重构",
                        "agent_type": "sub",
                    },
                    {
                        "name": "回归测试",
                        "desc": "确保重构未破坏现有功能",
                        "agent_type": "sub",
                    },
                ],
            ),
            "research": PlanTemplate(
                name="技术研究",
                description="技术研究和调研流程",
                steps=[
                    {
                        "name": "信息收集",
                        "desc": "收集相关技术文档和资料",
                        "agent_type": "main",
                    },
                    {
                        "name": "方案对比",
                        "desc": "对比分析不同方案的优劣",
                        "agent_type": "main",
                    },
                    {
                        "name": "原型验证",
                        "desc": "必要时进行原型验证",
                        "agent_type": "sub",
                    },
                    {
                        "name": "报告输出",
                        "desc": "输出研究报告和建议",
                        "agent_type": "main",
                    },
                ],
            ),
        }

    def _generate_task_id(self) -> str:
        """生成任务ID，兼容现有task_list格式"""
        self._task_counter += 1
        return f"task-{self._task_counter}"

    def create_plan(
        self,
        goal: Goal,
        template_name: Optional[str] = None,
        custom_steps: Optional[list[dict[str, Any]]] = None,
    ) -> tuple[Plan, TaskList]:
        """创建执行计划

        Args:
            goal: 目标对象
            template_name: 使用的模板名称
            custom_steps: 自定义步骤列表

        Returns:
            (Plan, TaskList): 创建的计划对象和对应的任务列表
        """
        plan_id = str(uuid.uuid4())

        # 确定使用的步骤模板
        if custom_steps:
            step_templates = custom_steps
        elif template_name and template_name in self.templates:
            step_templates = self.templates[template_name].steps
        else:
            # 根据目标自动选择模板
            step_templates = self._auto_select_template(goal)

        # 创建TaskList（兼容现有系统）
        task_list = TaskList(main_goal=goal.title)

        # 重置任务计数器
        self._task_counter = 0

        # 创建任务
        import time

        current_time = int(time.time() * 1000)
        prev_task_id: Optional[str] = None

        for template in step_templates:
            task_id = self._generate_task_id()
            agent_type_str = template.get("agent_type", "main")
            agent_type = AgentType.SUB if agent_type_str == "sub" else AgentType.MAIN

            # 设置依赖关系（默认依赖前一个任务）
            dependencies = template.get("dependencies", [])
            if not dependencies and prev_task_id:
                dependencies = [prev_task_id]

            task = Task(
                task_id=task_id,
                task_name=template.get("name", f"任务{self._task_counter}"),
                task_desc=template.get("desc", ""),
                status=TaskStatus.PENDING,
                expected_output=template.get("expected_output", "任务完成"),
                agent_type=agent_type,
                create_time=current_time,
                update_time=current_time,
                dependencies=dependencies,
            )
            task_list.add_task(task)
            prev_task_id = task_id

        # 创建Plan
        plan = Plan(
            id=plan_id,
            goal_id=goal.id,
            name=f"{goal.title}的执行计划",
            description=f"为达成目标'{goal.title}'制定的执行计划",
            task_list_id=plan_id,  # 使用相同ID关联
        )

        self.plans[plan_id] = plan
        return plan, task_list

    def _auto_select_template(self, goal: Goal) -> list[dict[str, Any]]:
        """根据目标自动选择模板

        Args:
            goal: 目标对象

        Returns:
            选择的模板步骤列表
        """
        description_lower = goal.description.lower()
        title_lower = goal.title.lower()

        # 关键词匹配
        if any(
            kw in description_lower or kw in title_lower
            for kw in ["bug", "修复", "fix", "错误", "问题"]
        ):
            return self.templates["bug_fix"].steps
        elif any(
            kw in description_lower or kw in title_lower
            for kw in ["重构", "refactor", "优化代码"]
        ):
            return self.templates["refactoring"].steps
        elif any(
            kw in description_lower or kw in title_lower
            for kw in ["研究", "调研", "分析", "对比", "research"]
        ):
            return self.templates["research"].steps
        else:
            return self.templates["software_development"].steps

    def get_plan(self, plan_id: str) -> Optional[Plan]:
        """获取计划

        Args:
            plan_id: 计划ID

        Returns:
            计划对象，不存在则返回None
        """
        return self.plans.get(plan_id)

    def get_plans_for_goal(self, goal_id: str) -> list[Plan]:
        """获取目标的所有计划

        Args:
            goal_id: 目标ID

        Returns:
            计划列表
        """
        return [p for p in self.plans.values() if p.goal_id == goal_id]

    def update_plan_status(self, plan_id: str, status: PlanStatus) -> Optional[Plan]:
        """更新计划状态

        Args:
            plan_id: 计划ID
            status: 新状态

        Returns:
            更新后的计划，不存在则返回None
        """
        plan = self.plans.get(plan_id)
        if not plan:
            return None

        plan.status = status
        plan.updated_at = datetime.now()

        if status == PlanStatus.COMPLETED:
            plan.actual_completion = datetime.now()

        return plan

    def generate_tasks_info(
        self, goal: Goal, template_name: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """生成任务信息列表，用于task_list_manager.add_tasks

        这个方法生成的格式可以直接传递给task_list_manager工具。

        Args:
            goal: 目标对象
            template_name: 使用的模板名称

        Returns:
            任务信息列表，格式兼容task_list_manager
        """
        # 确定使用的步骤模板
        if template_name and template_name in self.templates:
            step_templates = self.templates[template_name].steps
        else:
            step_templates = self._auto_select_template(goal)

        tasks_info = []
        prev_task_name: Optional[str] = None

        for template in step_templates:
            task_name = template.get("name", "任务")
            agent_type = template.get("agent_type", "main")

            # 设置依赖关系
            dependencies = []
            if prev_task_name:
                dependencies = [prev_task_name]

            task_info = {
                "task_name": task_name,
                "task_desc": template.get("desc", ""),
                "expected_output": template.get("expected_output", "任务完成"),
                "agent_type": agent_type,
                "dependencies": dependencies,
            }
            tasks_info.append(task_info)
            prev_task_name = task_name

        return tasks_info

    def get_available_templates(self) -> list[dict[str, str]]:
        """获取可用的计划模板列表

        Returns:
            模板信息列表
        """
        return [
            {"name": name, "description": template.description}
            for name, template in self.templates.items()
        ]
