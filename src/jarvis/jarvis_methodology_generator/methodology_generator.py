"""方法论自动生成器

该模块提供从任务执行过程中自动提取和生成方法论的功能。
包含以下核心功能：
- 从任务上下文中提取方法论
- 生成符合标准格式的方法论内容
- 评估方法论质量
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TaskContext:
    """任务上下文数据类

    存储任务执行过程中的关键信息，用于方法论提取。
    """

    task_description: str = ""  # 任务描述
    execution_steps: List[str] = field(default_factory=list)  # 执行步骤
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)  # 工具调用记录
    decisions: List[str] = field(default_factory=list)  # 关键决策
    verification_steps: List[str] = field(default_factory=list)  # 验证步骤
    actual_output: str = ""  # 实际输出
    success: bool = False  # 任务是否成功


@dataclass
class MethodologyQualityScore:
    """方法论质量评分

    包含各维度的评分和总分。
    """

    completeness: int = 0  # 完整性（30分）
    executability: int = 0  # 可执行性（30分）
    generality: int = 0  # 通用性（20分）
    uniqueness: int = 0  # 独特性（20分）

    @property
    def total(self) -> int:
        """计算总分"""
        return (
            self.completeness + self.executability + self.generality + self.uniqueness
        )

    def is_qualified(self, threshold: int = 70) -> bool:
        """判断是否达到质量阈值"""
        return self.total >= threshold


class MethodologyGenerator:
    """方法论自动生成器

    从任务执行过程中提取方法论，生成符合标准格式的内容，
    并评估方法论质量。
    """

    # 方法论模板
    METHODOLOGY_TEMPLATE = """# {problem_type}方法论

## 规则简介
{introduction}

## 你必须遵守的原则
{principles}

## 你必须执行的操作
{operations}

## 实践指导
{practice_guidance}

## 检查清单
{checklist}
"""

    # 必需的章节
    REQUIRED_SECTIONS = [
        "规则简介",
        "你必须遵守的原则",
        "你必须执行的操作",
    ]

    # 可选的章节
    OPTIONAL_SECTIONS = [
        "实践指导",
        "检查清单",
    ]

    def __init__(self, existing_methodologies: Optional[List[str]] = None):
        """初始化方法论生成器

        Args:
            existing_methodologies: 现有方法论列表，用于去重和独特性评估
        """
        self.existing_methodologies = existing_methodologies or []

    def extract_methodology_from_task(
        self, task_context: TaskContext
    ) -> Optional[Dict[str, Any]]:
        """从任务上下文中提取方法论

        Args:
            task_context: 任务上下文

        Returns:
            提取的方法论字典，包含problem_type和content，
            如果无法提取则返回None
        """
        # 验证任务上下文
        if not self._validate_task_context(task_context):
            return None

        # 提取问题类型
        problem_type = self._extract_problem_type(task_context)
        if not problem_type:
            return None

        # 提取关键步骤
        steps = self._extract_steps(task_context)

        # 提取关键决策
        decisions = self._extract_decisions(task_context)

        # 生成方法论内容
        content = self.generate_methodology_content(
            problem_type=problem_type,
            steps=steps,
            decisions=decisions,
            verification_steps=task_context.verification_steps,
        )

        # 评估质量
        quality_score = self.evaluate_methodology_quality(content)
        if not quality_score.is_qualified():
            return None

        return {
            "problem_type": problem_type,
            "content": content,
            "quality_score": quality_score.total,
        }

    def generate_methodology_content(
        self,
        problem_type: str,
        steps: List[str],
        decisions: List[str],
        verification_steps: Optional[List[str]] = None,
    ) -> str:
        """生成方法论内容

        Args:
            problem_type: 问题类型
            steps: 执行步骤列表
            decisions: 关键决策列表
            verification_steps: 验证步骤列表

        Returns:
            生成的方法论内容（Markdown格式）
        """
        # 生成简介
        introduction = self._generate_introduction(problem_type, steps)

        # 生成原则
        principles = self._generate_principles(decisions)

        # 生成操作
        operations = self._generate_operations(steps)

        # 生成实践指导
        practice_guidance = self._generate_practice_guidance(decisions)

        # 生成检查清单
        checklist = self._generate_checklist(verification_steps or [])

        # 使用模板生成内容
        content = self.METHODOLOGY_TEMPLATE.format(
            problem_type=problem_type,
            introduction=introduction,
            principles=principles,
            operations=operations,
            practice_guidance=practice_guidance,
            checklist=checklist,
        )

        return content.strip()

    def evaluate_methodology_quality(self, content: str) -> MethodologyQualityScore:
        """评估方法论质量

        Args:
            content: 方法论内容

        Returns:
            质量评分对象
        """
        score = MethodologyQualityScore()

        # 评估完整性（30分）
        score.completeness = self._evaluate_completeness(content)

        # 评估可执行性（30分）
        score.executability = self._evaluate_executability(content)

        # 评估通用性（20分）
        score.generality = self._evaluate_generality(content)

        # 评估独特性（20分）
        score.uniqueness = self._evaluate_uniqueness(content)

        return score

    def _validate_task_context(self, task_context: TaskContext) -> bool:
        """验证任务上下文是否有效"""
        # 必须有任务描述
        if not task_context.task_description:
            return False

        # 必须有执行步骤或工具调用
        if not task_context.execution_steps and not task_context.tool_calls:
            return False

        # 任务必须成功
        if not task_context.success:
            return False

        return True

    def _extract_problem_type(self, task_context: TaskContext) -> str:
        """从任务描述中提取问题类型"""
        description = task_context.task_description

        # 尝试从描述中提取关键词作为问题类型
        # 移除常见的动词前缀
        prefixes = ["实现", "创建", "修复", "优化", "重构", "添加", "删除", "更新"]
        for prefix in prefixes:
            if description.startswith(prefix):
                description = description[len(prefix) :]
                break

        # 截取前20个字符作为问题类型
        problem_type = description[:20].strip()

        # 如果为空，使用默认值
        if not problem_type:
            problem_type = "通用任务"

        return problem_type

    def _extract_steps(self, task_context: TaskContext) -> List[str]:
        """提取执行步骤"""
        steps = []

        # 优先使用显式的执行步骤
        if task_context.execution_steps:
            steps.extend(task_context.execution_steps)

        # 从工具调用中提取步骤
        for tool_call in task_context.tool_calls:
            tool_name = tool_call.get("name", "")
            if tool_name:
                steps.append(f"使用 {tool_name} 工具")

        return steps

    def _extract_decisions(self, task_context: TaskContext) -> List[str]:
        """提取关键决策"""
        decisions = []

        # 使用显式的决策
        if task_context.decisions:
            decisions.extend(task_context.decisions)

        return decisions

    def _generate_introduction(self, problem_type: str, steps: List[str]) -> str:
        """生成规则简介"""
        step_count = len(steps)
        return (
            f"本方法论提供{problem_type}的标准化解决流程，包含{step_count}个关键步骤。"
        )

    def _generate_principles(self, decisions: List[str]) -> str:
        """生成原则部分"""
        if not decisions:
            return "- **必须**：遵循标准化流程\n- **禁止**：跳过验证步骤"

        principles = []
        for i, decision in enumerate(decisions, 1):
            principles.append(f"### 原则{i}\n\n**要求说明：**\n- {decision}")

        return "\n\n".join(principles)

    def _generate_operations(self, steps: List[str]) -> str:
        """生成操作部分"""
        if not steps:
            return "1. 分析问题\n2. 制定方案\n3. 执行操作\n4. 验证结果"

        operations = []
        for i, step in enumerate(steps, 1):
            operations.append(f"{i}. **步骤{i}**：{step}")

        return "\n".join(operations)

    def _generate_practice_guidance(self, decisions: List[str]) -> str:
        """生成实践指导"""
        if not decisions:
            return (
                "- 在执行前充分理解需求\n- 保持代码风格一致\n- 及时验证每个步骤的结果"
            )

        guidance = []
        for decision in decisions:
            guidance.append(f"- {decision}")

        return "\n".join(guidance)

    def _generate_checklist(self, verification_steps: List[str]) -> str:
        """生成检查清单"""
        if not verification_steps:
            return "- [ ] 功能正确实现\n- [ ] 代码通过静态检查\n- [ ] 测试覆盖充分"

        checklist = []
        for step in verification_steps:
            checklist.append(f"- [ ] {step}")

        return "\n".join(checklist)

    def _evaluate_completeness(self, content: str) -> int:
        """评估完整性（30分）"""
        score = 0

        # 检查必需章节（每个10分）
        for section in self.REQUIRED_SECTIONS:
            if section in content:
                score += 10

        return min(score, 30)

    def _evaluate_executability(self, content: str) -> int:
        """评估可执行性（30分）"""
        score = 0

        # 检查是否有编号步骤（15分）
        if re.search(r"\d+\.\s+", content):
            score += 15

        # 检查是否有具体操作描述（15分）
        action_keywords = ["执行", "创建", "修改", "验证", "检查", "使用"]
        for keyword in action_keywords:
            if keyword in content:
                score += 3
                if score >= 30:
                    break

        return min(score, 30)

    def _evaluate_generality(self, content: str) -> int:
        """评估通用性（20分）"""
        score = 10  # 基础分

        # 检查是否避免了过于具体的内容
        specific_patterns = [
            r"\b[a-f0-9]{32}\b",  # MD5哈希
            r"\b\d{4}-\d{2}-\d{2}\b",  # 日期
            r"/home/\w+/",  # 绝对路径
        ]

        for pattern in specific_patterns:
            if re.search(pattern, content):
                score -= 5

        return max(score, 0)

    def _evaluate_uniqueness(self, content: str) -> int:
        """评估独特性（20分）"""
        if not self.existing_methodologies:
            return 15  # 没有现有方法论时给予较高分数

        # 计算与现有方法论的相似度
        max_similarity: float = 0.0
        for existing in self.existing_methodologies:
            similarity = self._calculate_similarity(content, existing)
            max_similarity = max(max_similarity, similarity)

        # 相似度越低，独特性越高
        if max_similarity > 0.8:
            return 0
        elif max_similarity > 0.6:
            return 10
        elif max_similarity > 0.4:
            return 15
        else:
            return 20

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """计算两个文本的相似度（简单的Jaccard相似度）"""
        words1 = set(text1.split())
        words2 = set(text2.split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0
