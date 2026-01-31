"""方案设计引擎

基于混合引擎的方案设计，支持多方案并行生成、对比分析和最优推荐。
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from jarvis.jarvis_autonomous.intelligence import (
    HybridEngine,
    InferenceMode,
    ReasoningContext,
    ReasoningType,
)
from jarvis.jarvis_autonomous.intelligence.rule_learner import LearnedRule


class SolutionStatus(Enum):
    """方案状态"""

    DRAFT = "draft"
    PROPOSED = "proposed"
    EVALUATED = "evaluated"
    SELECTED = "selected"
    REJECTED = "rejected"
    IMPLEMENTED = "implemented"


@dataclass
class SolutionRank:
    """方案排名"""

    solution_id: str
    overall_score: float
    rank: int
    scores: dict[str, float] = field(default_factory=dict)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "solution_id": self.solution_id,
            "overall_score": self.overall_score,
            "rank": self.rank,
            "scores": self.scores,
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
        }


@dataclass
class SolutionComparison:
    """方案对比"""

    solution_a_id: str
    solution_b_id: str
    winner: Optional[str]
    comparison_dimensions: dict[str, str] = field(default_factory=dict)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "solution_a_id": self.solution_a_id,
            "solution_b_id": self.solution_b_id,
            "winner": self.winner,
            "comparison_dimensions": self.comparison_dimensions,
            "summary": self.summary,
        }


@dataclass
class Solution:
    """方案"""

    id: str
    name: str
    description: str
    problem: str
    approach: str
    status: SolutionStatus = SolutionStatus.DRAFT
    pros: list[str] = field(default_factory=list)
    cons: list[str] = field(default_factory=list)
    complexity: str = "medium"
    estimated_effort: str = "medium"
    risk_level: str = "medium"
    dependencies: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "problem": self.problem,
            "approach": self.approach,
            "status": self.status.value,
            "pros": self.pros,
            "cons": self.cons,
            "complexity": self.complexity,
            "estimated_effort": self.estimated_effort,
            "risk_level": self.risk_level,
            "dependencies": self.dependencies,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


class SolutionDesigner(HybridEngine[Solution]):
    """方案设计引擎

    基于混合引擎实现方案设计，支持：
    - 快路径：基于模板的规则匹配
    - 慢路径：LLM 智能推理生成方案
    - 学习机制：从成功的方案中学习新规则
    """

    def __init__(
        self,
        mode: InferenceMode = InferenceMode.HYBRID,
        enable_learning: bool = True,
    ) -> None:
        """初始化方案设计器"""
        super().__init__(
            llm_client=None,
            mode=mode,
            enable_learning=enable_learning,
        )
        self.solutions: dict[str, Solution] = {}
        self.solution_counter = 0
        self._init_dimension_weights()
        self._init_predefined_rules()

    def _init_dimension_weights(self) -> None:
        """初始化评估维度权重"""
        self.dimension_weights: dict[str, float] = {
            "feasibility": 0.25,
            "effectiveness": 0.25,
            "efficiency": 0.20,
            "maintainability": 0.15,
            "risk": 0.15,
        }

    def _init_predefined_rules(self) -> None:
        """初始化预定义规则"""
        # 重构方案
        self.add_predefined_rule(
            name="refactoring_solution",
            keywords=["重构", "refactor", "整理", "清理"],
            output=Solution(
                id="template-refactor",
                name="代码重构方案",
                description="通过代码重构解决问题",
                problem="",
                approach="代码重构",
                pros=["提高代码质量", "降低维护成本"],
                cons=["需要时间投入", "可能引入新bug"],
                complexity="medium",
            ),
            confidence=0.75,
        )
        # 性能优化方案
        self.add_predefined_rule(
            name="optimization_solution",
            keywords=["性能", "优化", "慢", "performance"],
            output=Solution(
                id="template-optimize",
                name="性能优化方案",
                description="通过性能优化解决问题",
                problem="",
                approach="性能优化",
                pros=["提升系统性能", "改善用户体验"],
                cons=["可能增加复杂度", "需要性能测试"],
                complexity="medium",
            ),
            confidence=0.75,
        )
        # 新功能方案
        self.add_predefined_rule(
            name="new_feature_solution",
            keywords=["新功能", "实现", "开发", "feature"],
            output=Solution(
                id="template-feature",
                name="新功能开发方案",
                description="通过新功能开发解决问题",
                problem="",
                approach="新功能开发",
                pros=["满足新需求", "增加系统能力"],
                cons=["开发周期长", "需要测试验证"],
                complexity="high",
            ),
            confidence=0.7,
        )

    def _generate_id(self) -> str:
        """生成唯一ID"""
        self.solution_counter += 1
        return f"solution-{self.solution_counter}"

    def generate_solutions(
        self,
        problem: str,
        constraints: Optional[list[str]] = None,
        max_solutions: int = 3,
    ) -> list[Solution]:
        """生成多个解决方案"""
        solutions: list[Solution] = []

        # 使用混合引擎推理
        result = self.infer(
            problem,
            constraints=constraints,
        )

        if result.success and result.output:
            solution = result.output
            solution.id = self._generate_id()
            solution.problem = problem
            solution.dependencies = constraints or []
            solutions.append(solution)
            self.solutions[solution.id] = solution

        # 生成更多方案
        while len(solutions) < max_solutions:
            supplementary = self._generate_supplementary_solution(
                problem, constraints, solutions
            )
            if supplementary:
                solutions.append(supplementary)
                self.solutions[supplementary.id] = supplementary
            else:
                break

        return solutions[:max_solutions]

    def _generate_supplementary_solution(
        self,
        problem: str,
        constraints: Optional[list[str]],
        existing: list[Solution],
    ) -> Optional[Solution]:
        """生成补充方案"""
        used_approaches = {s.approach for s in existing}
        templates = [
            ("代码重构", "refactoring"),
            ("性能优化", "optimization"),
            ("新功能开发", "new_feature"),
            ("系统集成", "integration"),
        ]

        for approach, tag in templates:
            if approach not in used_approaches:
                return Solution(
                    id=self._generate_id(),
                    name=f"{approach}方案",
                    description=f"通过{approach}解决问题",
                    problem=problem,
                    approach=approach,
                    pros=self._get_default_pros(tag),
                    cons=self._get_default_cons(tag),
                    complexity="medium",
                    dependencies=constraints or [],
                    tags=[tag],
                )
        return None

    def _get_default_pros(self, template: str) -> list[str]:
        """获取默认优点"""
        pros_map = {
            "refactoring": ["提高代码质量", "降低维护成本"],
            "optimization": ["提升系统性能", "改善用户体验"],
            "new_feature": ["满足新需求", "增加系统能力"],
            "integration": ["复用现有能力", "快速实现"],
        }
        return pros_map.get(template, [])

    def _get_default_cons(self, template: str) -> list[str]:
        """获取默认缺点"""
        cons_map = {
            "refactoring": ["需要时间投入", "可能引入新bug"],
            "optimization": ["可能增加复杂度", "需要性能测试"],
            "new_feature": ["开发周期长", "需要测试验证"],
            "integration": ["依赖外部系统", "接口兼容性"],
        }
        return cons_map.get(template, [])

    def _apply_rule(
        self,
        rule: LearnedRule,
        input_data: str,
        **kwargs: Any,
    ) -> Optional[Solution]:
        """应用学习到的规则"""
        try:
            action_data = json.loads(rule.action) if rule.action.startswith("{") else {}
        except json.JSONDecodeError:
            action_data = {}

        return Solution(
            id=self._generate_id(),
            name=action_data.get("name", rule.name),
            description=rule.description,
            problem=input_data,
            approach=action_data.get("approach", "通用方案"),
            pros=action_data.get("pros", []),
            cons=action_data.get("cons", []),
            complexity=action_data.get("complexity", "medium"),
            tags=rule.tags,
        )

    def _parse_llm_output(self, output: str) -> Optional[Solution]:
        """解析 LLM 输出"""
        try:
            data = json.loads(output)
            if not isinstance(data, dict):
                return None

            return Solution(
                id=self._generate_id(),
                name=data.get("name", "解决方案"),
                description=data.get("description", ""),
                problem=data.get("problem", ""),
                approach=data.get("approach", ""),
                pros=data.get("pros", []),
                cons=data.get("cons", []),
                complexity=data.get("complexity", "medium"),
                estimated_effort=data.get("estimated_effort", "medium"),
                risk_level=data.get("risk_level", "medium"),
                tags=data.get("tags", []),
            )
        except json.JSONDecodeError:
            return Solution(
                id=self._generate_id(),
                name="解决方案",
                description=output[:500],
                problem="",
                approach="通用方案",
            )

    def _build_reasoning_context(
        self,
        input_data: str,
        **kwargs: Any,
    ) -> ReasoningContext:
        """构建推理上下文"""
        constraints = kwargs.get("constraints", [])
        constraints_text = (
            f"\n约束条件: {', '.join(constraints)}" if constraints else ""
        )

        instruction = f"""基于以下问题描述，设计一个解决方案。{constraints_text}

输出 JSON 格式：
{{
    "name": "方案名称",
    "description": "详细描述",
    "approach": "解决方法",
    "pros": ["优点1", "优点2"],
    "cons": ["缺点1", "缺点2"],
    "complexity": "low|medium|high",
    "estimated_effort": "low|medium|high",
    "risk_level": "low|medium|high",
    "tags": ["标签1", "标签2"]
}}"""

        return ReasoningContext(
            task_type=ReasoningType.GENERATION,
            input_data=input_data,
            instruction=instruction,
            output_format="json",
            constraints=[
                "方案必须具体可行",
                "需要列出优缺点",
                "评估复杂度和风险",
            ],
        )

    def _get_reasoning_type(self) -> ReasoningType:
        """获取推理类型"""
        return ReasoningType.GENERATION

    def evaluate_solution(self, solution_id: str) -> SolutionRank:
        """评估单个方案"""
        solution = self.solutions.get(solution_id)
        if not solution:
            return SolutionRank(
                solution_id=solution_id,
                overall_score=0,
                rank=0,
                strengths=[],
                weaknesses=["方案不存在"],
            )

        scores = self._calculate_dimension_scores(solution)
        overall_score = sum(
            scores[dim] * weight for dim, weight in self.dimension_weights.items()
        )
        solution.status = SolutionStatus.EVALUATED

        return SolutionRank(
            solution_id=solution_id,
            overall_score=overall_score,
            rank=0,
            scores=scores,
            strengths=solution.pros,
            weaknesses=solution.cons,
        )

    def _calculate_dimension_scores(self, solution: Solution) -> dict[str, float]:
        """计算各维度得分"""
        scores: dict[str, float] = {}
        complexity_scores = {"low": 90, "medium": 70, "high": 50}
        effort_scores = {"low": 90, "medium": 70, "high": 50}
        risk_scores = {"low": 90, "medium": 70, "high": 50}

        scores["feasibility"] = complexity_scores.get(solution.complexity, 70)
        scores["effectiveness"] = min(50 + len(solution.pros) * 15, 100)
        scores["efficiency"] = effort_scores.get(solution.estimated_effort, 70)
        scores["maintainability"] = max(
            100
            - len(solution.dependencies) * 10
            - (20 if solution.complexity == "high" else 0),
            30,
        )
        base_risk = risk_scores.get(solution.risk_level, 70)
        scores["risk"] = max(base_risk - len(solution.cons) * 10, 30)

        return scores

    def compare_solutions(
        self,
        solution_a_id: str,
        solution_b_id: str,
    ) -> SolutionComparison:
        """对比两个方案"""
        rank_a = self.evaluate_solution(solution_a_id)
        rank_b = self.evaluate_solution(solution_b_id)

        comparison_dimensions: dict[str, str] = {}
        for dim in self.dimension_weights:
            score_a = rank_a.scores.get(dim, 0)
            score_b = rank_b.scores.get(dim, 0)
            if score_a > score_b:
                comparison_dimensions[dim] = solution_a_id
            elif score_b > score_a:
                comparison_dimensions[dim] = solution_b_id
            else:
                comparison_dimensions[dim] = "tie"

        winner = None
        if rank_a.overall_score > rank_b.overall_score:
            winner = solution_a_id
        elif rank_b.overall_score > rank_a.overall_score:
            winner = solution_b_id

        summary = self._generate_comparison_summary(
            solution_a_id, solution_b_id, rank_a, rank_b, winner
        )

        return SolutionComparison(
            solution_a_id=solution_a_id,
            solution_b_id=solution_b_id,
            winner=winner,
            comparison_dimensions=comparison_dimensions,
            summary=summary,
        )

    def _generate_comparison_summary(
        self,
        solution_a_id: str,
        solution_b_id: str,
        rank_a: SolutionRank,
        rank_b: SolutionRank,
        winner: Optional[str],
    ) -> str:
        """生成对比总结"""
        if winner == solution_a_id:
            return f"方案A（{solution_a_id}）综合得分{rank_a.overall_score:.1f}，优于方案B（{rank_b.overall_score:.1f}）"
        elif winner == solution_b_id:
            return f"方案B（{solution_b_id}）综合得分{rank_b.overall_score:.1f}，优于方案A（{rank_a.overall_score:.1f}）"
        else:
            return f"两个方案得分相近（A: {rank_a.overall_score:.1f}, B: {rank_b.overall_score:.1f}），建议根据具体情况选择"

    def rank_solutions(self, solution_ids: list[str]) -> list[SolutionRank]:
        """对多个方案进行排名"""
        ranks = [self.evaluate_solution(sid) for sid in solution_ids]
        ranks.sort(key=lambda r: r.overall_score, reverse=True)
        for i, rank in enumerate(ranks):
            rank.rank = i + 1
        return ranks

    def recommend_solution(self, solution_ids: list[str]) -> Optional[Solution]:
        """推荐最优方案"""
        if not solution_ids:
            return None
        ranks = self.rank_solutions(solution_ids)
        if not ranks:
            return None
        best_id = ranks[0].solution_id
        best_solution = self.solutions.get(best_id)
        if best_solution:
            best_solution.status = SolutionStatus.SELECTED
        return best_solution

    def get_solution(self, solution_id: str) -> Optional[Solution]:
        """获取方案"""
        return self.solutions.get(solution_id)

    def get_all_solutions(self) -> list[Solution]:
        """获取所有方案"""
        return list(self.solutions.values())

    def clear_solutions(self) -> None:
        """清空方案"""
        self.solutions.clear()
