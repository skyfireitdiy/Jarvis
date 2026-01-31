"""任务分解器模块

将复杂目标分解为可执行的子任务，与现有task_list系统深度整合。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from jarvis.jarvis_autonomous.goal_manager import Goal, GoalPriority


class TaskComplexity(Enum):
    """任务复杂度枚举"""

    SIMPLE = "simple"  # 简单：1-3步，单文件
    MEDIUM = "medium"  # 中等：4-10步，多文件
    COMPLEX = "complex"  # 复杂：10+步，多模块


@dataclass
class DecomposedTask:
    """分解后的任务

    表示分解后的单个任务，格式兼容task_list_manager。
    """

    name: str
    description: str
    expected_output: str
    agent_type: str = "main"  # main 或 sub
    dependencies: list[str] = field(default_factory=list)
    estimated_effort: str = "low"  # low, medium, high
    tags: list[str] = field(default_factory=list)

    def to_task_info(self) -> dict[str, Any]:
        """转换为task_list_manager兼容的格式"""
        return {
            "task_name": self.name,
            "task_desc": self.description,
            "expected_output": self.expected_output,
            "agent_type": self.agent_type,
            "dependencies": self.dependencies,
        }


class TaskDecomposer:
    """任务分解器

    将复杂目标分解为可执行的子任务。
    生成的任务格式与task_list_manager完全兼容。
    """

    def __init__(self) -> None:
        """初始化任务分解器"""
        # 分解策略映射
        self.strategies: dict[str, list[dict[str, Any]]] = {
            "feature_development": [
                {
                    "name": "需求分析",
                    "desc": "分析功能需求，明确输入输出和边界条件",
                    "output": "需求分析文档，包含功能点列表和验收标准",
                    "agent": "main",
                    "effort": "low",
                },
                {
                    "name": "接口设计",
                    "desc": "设计模块接口和数据结构",
                    "output": "接口设计文档，包含类/函数签名",
                    "agent": "main",
                    "effort": "medium",
                },
                {
                    "name": "核心实现",
                    "desc": "实现核心功能逻辑",
                    "output": "核心功能代码实现完成",
                    "agent": "sub",
                    "effort": "high",
                },
                {
                    "name": "单元测试",
                    "desc": "编写单元测试用例",
                    "output": "测试用例通过，覆盖率≥80%",
                    "agent": "sub",
                    "effort": "medium",
                },
                {
                    "name": "集成验证",
                    "desc": "验证功能与现有系统的集成",
                    "output": "集成测试通过，无回归问题",
                    "agent": "main",
                    "effort": "low",
                },
            ],
            "bug_investigation": [
                {
                    "name": "问题复现",
                    "desc": "复现问题，确认问题存在",
                    "output": "问题复现步骤和现象描述",
                    "agent": "main",
                    "effort": "low",
                },
                {
                    "name": "根因分析",
                    "desc": "分析问题根本原因",
                    "output": "根因分析报告，定位到具体代码",
                    "agent": "main",
                    "effort": "medium",
                },
                {
                    "name": "修复实现",
                    "desc": "实现修复方案",
                    "output": "修复代码提交",
                    "agent": "sub",
                    "effort": "medium",
                },
                {
                    "name": "回归验证",
                    "desc": "验证修复效果，确保无副作用",
                    "output": "回归测试通过",
                    "agent": "main",
                    "effort": "low",
                },
            ],
            "code_refactoring": [
                {
                    "name": "代码审查",
                    "desc": "审查现有代码，识别问题点",
                    "output": "代码问题清单",
                    "agent": "main",
                    "effort": "medium",
                },
                {
                    "name": "重构方案",
                    "desc": "设计重构方案",
                    "output": "重构方案文档",
                    "agent": "main",
                    "effort": "medium",
                },
                {
                    "name": "安全重构",
                    "desc": "分步实施重构，确保每步可回退",
                    "output": "重构代码提交",
                    "agent": "sub",
                    "effort": "high",
                },
                {
                    "name": "质量验证",
                    "desc": "验证重构后代码质量",
                    "output": "代码质量报告，测试通过",
                    "agent": "main",
                    "effort": "low",
                },
            ],
            "documentation": [
                {
                    "name": "内容规划",
                    "desc": "规划文档结构和内容",
                    "output": "文档大纲",
                    "agent": "main",
                    "effort": "low",
                },
                {
                    "name": "内容编写",
                    "desc": "编写文档内容",
                    "output": "文档初稿",
                    "agent": "sub",
                    "effort": "medium",
                },
                {
                    "name": "审查完善",
                    "desc": "审查和完善文档",
                    "output": "文档终稿",
                    "agent": "main",
                    "effort": "low",
                },
            ],
        }

    def analyze_complexity(self, goal: Goal) -> TaskComplexity:
        """分析目标复杂度

        Args:
            goal: 目标对象

        Returns:
            任务复杂度
        """
        description = goal.description.lower()
        title = goal.title.lower()

        # 复杂度指标
        complexity_indicators = {
            "complex": [
                "重构",
                "架构",
                "系统",
                "全面",
                "完整",
                "多模块",
                "refactor",
                "architecture",
            ],
            "medium": [
                "功能",
                "模块",
                "实现",
                "开发",
                "feature",
                "implement",
            ],
            "simple": [
                "修复",
                "bug",
                "fix",
                "简单",
                "小",
                "调整",
                "更新",
            ],
        }

        # 检查复杂度指标
        for level, keywords in complexity_indicators.items():
            if any(kw in description or kw in title for kw in keywords):
                return TaskComplexity(level)

        # 根据优先级推断
        if goal.priority == GoalPriority.CRITICAL:
            return TaskComplexity.COMPLEX
        elif goal.priority == GoalPriority.HIGH:
            return TaskComplexity.MEDIUM
        else:
            return TaskComplexity.SIMPLE

    def select_strategy(self, goal: Goal) -> str:
        """选择分解策略

        Args:
            goal: 目标对象

        Returns:
            策略名称
        """
        description = goal.description.lower()
        title = goal.title.lower()

        # 关键词匹配
        if any(
            kw in description or kw in title
            for kw in ["bug", "修复", "fix", "错误", "问题"]
        ):
            return "bug_investigation"
        elif any(
            kw in description or kw in title
            for kw in ["重构", "refactor", "优化代码", "清理"]
        ):
            return "code_refactoring"
        elif any(
            kw in description or kw in title for kw in ["文档", "doc", "说明", "readme"]
        ):
            return "documentation"
        else:
            return "feature_development"

    def decompose(
        self,
        goal: Goal,
        strategy: Optional[str] = None,
        custom_tasks: Optional[list[dict[str, Any]]] = None,
    ) -> list[DecomposedTask]:
        """分解目标为任务列表

        Args:
            goal: 目标对象
            strategy: 分解策略名称（可选）
            custom_tasks: 自定义任务列表（可选）

        Returns:
            分解后的任务列表
        """
        if custom_tasks:
            # 使用自定义任务
            return [
                DecomposedTask(
                    name=t.get("name", "任务"),
                    description=t.get("desc", ""),
                    expected_output=t.get("output", "任务完成"),
                    agent_type=t.get("agent", "main"),
                    dependencies=t.get("dependencies", []),
                    estimated_effort=t.get("effort", "medium"),
                    tags=t.get("tags", []),
                )
                for t in custom_tasks
            ]

        # 选择策略
        if not strategy:
            strategy = self.select_strategy(goal)

        # 获取策略模板
        templates = self.strategies.get(
            strategy, self.strategies["feature_development"]
        )

        # 生成任务
        tasks = []
        prev_task_name: Optional[str] = None

        for template in templates:
            dependencies = []
            if prev_task_name:
                dependencies = [prev_task_name]

            task = DecomposedTask(
                name=template["name"],
                description=template["desc"],
                expected_output=template["output"],
                agent_type=template["agent"],
                dependencies=dependencies,
                estimated_effort=template["effort"],
            )
            tasks.append(task)
            prev_task_name = template["name"]

        return tasks

    def to_task_list_format(
        self, tasks: list[DecomposedTask], background: str = ""
    ) -> dict[str, Any]:
        """转换为task_list_manager的add_tasks格式

        Args:
            tasks: 分解后的任务列表
            background: 背景信息

        Returns:
            task_list_manager.add_tasks的参数格式
        """
        return {
            "action": "add_tasks",
            "background": background,
            "tasks_info": [task.to_task_info() for task in tasks],
        }

    def estimate_total_effort(self, tasks: list[DecomposedTask]) -> str:
        """估算总工作量

        Args:
            tasks: 任务列表

        Returns:
            工作量估算描述
        """
        effort_scores = {"low": 1, "medium": 2, "high": 3}
        total_score = sum(effort_scores.get(t.estimated_effort, 2) for t in tasks)

        if total_score <= 3:
            return "低（预计1-2小时）"
        elif total_score <= 6:
            return "中（预计2-4小时）"
        elif total_score <= 10:
            return "高（预计4-8小时）"
        else:
            return "非常高（预计1天以上）"

    def get_available_strategies(self) -> list[dict[str, str]]:
        """获取可用的分解策略列表

        Returns:
            策略信息列表
        """
        strategy_descriptions = {
            "feature_development": "功能开发：适用于新功能开发",
            "bug_investigation": "Bug调查：适用于问题排查和修复",
            "code_refactoring": "代码重构：适用于代码优化和重构",
            "documentation": "文档编写：适用于文档相关任务",
        }
        return [
            {"name": name, "description": strategy_descriptions.get(name, "")}
            for name in self.strategies.keys()
        ]
