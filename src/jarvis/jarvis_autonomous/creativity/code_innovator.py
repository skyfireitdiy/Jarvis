"""代码创新器

基于 LLM 的代码创新能力，支持：
- 代码优化建议
- 设计模式推荐
- 重构方案生成
- 新功能设计
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


class InnovationType(Enum):
    """创新类型"""

    OPTIMIZATION = "optimization"  # 代码优化
    PATTERN = "pattern"  # 设计模式
    REFACTORING = "refactoring"  # 重构方案
    FEATURE = "feature"  # 新功能设计
    ARCHITECTURE = "architecture"  # 架构改进
    ALGORITHM = "algorithm"  # 算法优化


@dataclass
class CodeInnovation:
    """代码创新结果"""

    id: str
    innovation_type: InnovationType
    title: str
    description: str
    original_code: str = ""
    suggested_code: str = ""
    benefits: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    effort_estimate: str = ""  # 工作量估计
    priority: str = "medium"  # low/medium/high/critical
    confidence: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "innovation_type": self.innovation_type.value,
            "title": self.title,
            "description": self.description,
            "original_code": self.original_code,
            "suggested_code": self.suggested_code,
            "benefits": self.benefits,
            "risks": self.risks,
            "effort_estimate": self.effort_estimate,
            "priority": self.priority,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class InnovationRequest:
    """创新请求"""

    code: str  # 待分析的代码
    context: str = ""  # 上下文信息
    innovation_type: Optional[InnovationType] = None  # 指定创新类型
    constraints: list[str] = field(default_factory=list)  # 约束条件
    goals: list[str] = field(default_factory=list)  # 目标


class CodeInnovator(HybridEngine[CodeInnovation]):
    """代码创新器

    基于混合引擎实现代码创新能力。
    """

    def __init__(
        self,
        mode: InferenceMode = InferenceMode.HYBRID,
        enable_learning: bool = True,
    ) -> None:
        """初始化代码创新器"""
        super().__init__(
            llm_client=None,
            mode=mode,
            enable_learning=enable_learning,
        )
        self.innovation_counter = 0
        self._init_predefined_rules()

    def _init_predefined_rules(self) -> None:
        """初始化预定义规则"""
        # 优化规则
        self.add_predefined_rule(
            name="loop_optimization",
            keywords=["for", "while", "loop", "iterate", "循环"],
            output=self._create_optimization_template("loop"),
            confidence=0.7,
        )
        self.add_predefined_rule(
            name="string_optimization",
            keywords=["string", "concat", "join", "字符串", "拼接"],
            output=self._create_optimization_template("string"),
            confidence=0.7,
        )
        # 设计模式规则
        self.add_predefined_rule(
            name="singleton_pattern",
            keywords=["singleton", "单例", "global", "instance"],
            output=self._create_pattern_template("singleton"),
            confidence=0.8,
        )
        self.add_predefined_rule(
            name="factory_pattern",
            keywords=["factory", "create", "工厂", "创建"],
            output=self._create_pattern_template("factory"),
            confidence=0.8,
        )

    def _create_optimization_template(
        self,
        opt_type: str,
    ) -> CodeInnovation:
        """创建优化模板"""
        templates = {
            "loop": CodeInnovation(
                id="template-loop",
                innovation_type=InnovationType.OPTIMIZATION,
                title="循环优化",
                description="使用列表推导式或生成器表达式替代显式循环",
                benefits=["代码更简洁", "可能提升性能", "更 Pythonic"],
                risks=["可读性可能降低"],
                effort_estimate="低",
                priority="medium",
            ),
            "string": CodeInnovation(
                id="template-string",
                innovation_type=InnovationType.OPTIMIZATION,
                title="字符串优化",
                description="使用 join() 替代字符串拼接",
                benefits=["性能提升", "内存效率更高"],
                risks=["代码风格变化"],
                effort_estimate="低",
                priority="low",
            ),
        }
        return templates.get(opt_type, templates["loop"])

    def _create_pattern_template(
        self,
        pattern_type: str,
    ) -> CodeInnovation:
        """创建设计模式模板"""
        templates = {
            "singleton": CodeInnovation(
                id="template-singleton",
                innovation_type=InnovationType.PATTERN,
                title="单例模式",
                description="确保类只有一个实例，并提供全局访问点",
                benefits=["控制实例数量", "全局访问", "延迟初始化"],
                risks=["全局状态", "测试困难", "隐藏依赖"],
                effort_estimate="中",
                priority="medium",
            ),
            "factory": CodeInnovation(
                id="template-factory",
                innovation_type=InnovationType.PATTERN,
                title="工厂模式",
                description="定义创建对象的接口，让子类决定实例化哪个类",
                benefits=["解耦创建逻辑", "易于扩展", "符合开闭原则"],
                risks=["增加复杂度", "类数量增加"],
                effort_estimate="中",
                priority="medium",
            ),
        }
        return templates.get(pattern_type, templates["factory"])

    def _generate_id(self) -> str:
        """生成唯一ID"""
        self.innovation_counter += 1
        return f"innovation-{self.innovation_counter}"

    def innovate(self, request: InnovationRequest) -> CodeInnovation:
        """执行代码创新

        Args:
            request: 创新请求

        Returns:
            代码创新结果
        """
        # 构建输入
        input_data = self._build_input(request)

        # 执行推理
        result = self.infer(
            input_data,
            request=request,
        )

        if result.success and result.output:
            return result.output

        # 返回默认结果
        return CodeInnovation(
            id=self._generate_id(),
            innovation_type=request.innovation_type or InnovationType.OPTIMIZATION,
            title="无法生成创新建议",
            description=result.error or "推理失败",
            original_code=request.code,
            confidence=0.0,
        )

    def _build_input(self, request: InnovationRequest) -> str:
        """构建输入字符串"""
        parts = [f"代码:\n{request.code}"]
        if request.context:
            parts.append(f"上下文: {request.context}")
        if request.innovation_type:
            parts.append(f"创新类型: {request.innovation_type.value}")
        if request.goals:
            parts.append(f"目标: {', '.join(request.goals)}")
        if request.constraints:
            parts.append(f"约束: {', '.join(request.constraints)}")
        return "\n".join(parts)

    def _apply_rule(
        self,
        rule: LearnedRule,
        input_data: str,
        **kwargs: Any,
    ) -> Optional[CodeInnovation]:
        """应用学习到的规则"""
        request = kwargs.get("request")
        if not request:
            return None

        # 从规则中提取创新信息
        try:
            action_data = json.loads(rule.action) if rule.action.startswith("{") else {}
        except json.JSONDecodeError:
            action_data = {}

        return CodeInnovation(
            id=self._generate_id(),
            innovation_type=self._parse_innovation_type(
                action_data.get("type", "optimization")
            ),
            title=action_data.get("title", rule.name),
            description=rule.description,
            original_code=request.code,
            suggested_code=action_data.get("suggested_code", ""),
            benefits=action_data.get("benefits", []),
            risks=action_data.get("risks", []),
            confidence=rule.confidence,
        )

    def _parse_innovation_type(self, type_str: str) -> InnovationType:
        """解析创新类型"""
        try:
            return InnovationType(type_str)
        except ValueError:
            return InnovationType.OPTIMIZATION

    def _parse_llm_output(self, output: str) -> Optional[CodeInnovation]:
        """解析 LLM 输出"""
        try:
            data = json.loads(output)
            if not isinstance(data, dict):
                return None
            return CodeInnovation(
                id=self._generate_id(),
                innovation_type=self._parse_innovation_type(
                    data.get("type", "optimization")
                ),
                title=data.get("title", "代码创新建议"),
                description=data.get("description", ""),
                original_code=data.get("original_code", ""),
                suggested_code=data.get("suggested_code", ""),
                benefits=data.get("benefits", []),
                risks=data.get("risks", []),
                effort_estimate=data.get("effort_estimate", "中"),
                priority=data.get("priority", "medium"),
                confidence=data.get("confidence", 0.7),
            )
        except json.JSONDecodeError:
            # 尝试从文本中提取信息
            return CodeInnovation(
                id=self._generate_id(),
                innovation_type=InnovationType.OPTIMIZATION,
                title="代码创新建议",
                description=output[:500],
                confidence=0.5,
            )

    def _build_reasoning_context(
        self,
        input_data: str,
        **kwargs: Any,
    ) -> ReasoningContext:
        """构建推理上下文"""
        request = kwargs.get("request")
        innovation_type = request.innovation_type if request else None

        instruction = self._build_instruction(innovation_type)

        return ReasoningContext(
            task_type=ReasoningType.GENERATION,
            input_data=input_data,
            instruction=instruction,
            output_format="json",
            constraints=[
                "输出必须是有效的 JSON 格式",
                "建议必须具体可行",
                "考虑代码的可维护性和可读性",
            ],
        )

    def _build_instruction(self, innovation_type: Optional[InnovationType]) -> str:
        """构建推理指令"""
        base_instruction = """分析给定的代码，提供创新建议。

输出 JSON 格式：
{
    "type": "optimization|pattern|refactoring|feature|architecture|algorithm",
    "title": "建议标题",
    "description": "详细描述",
    "suggested_code": "建议的代码（如果适用）",
    "benefits": ["好处1", "好处2"],
    "risks": ["风险1", "风险2"],
    "effort_estimate": "低|中|高",
    "priority": "low|medium|high|critical",
    "confidence": 0.0-1.0
}"""

        if innovation_type:
            type_instructions = {
                InnovationType.OPTIMIZATION: "重点关注性能优化和代码效率提升。",
                InnovationType.PATTERN: "识别可以应用的设计模式，提升代码结构。",
                InnovationType.REFACTORING: "提供重构建议，改善代码质量和可维护性。",
                InnovationType.FEATURE: "基于现有代码，设计新功能的实现方案。",
                InnovationType.ARCHITECTURE: "从架构层面分析，提供改进建议。",
                InnovationType.ALGORITHM: "分析算法效率，提供优化方案。",
            }
            base_instruction += f"\n\n{type_instructions.get(innovation_type, '')}"

        return base_instruction

    def _get_reasoning_type(self) -> ReasoningType:
        """获取推理类型"""
        return ReasoningType.GENERATION

    def suggest_optimizations(self, code: str) -> list[CodeInnovation]:
        """建议代码优化

        Args:
            code: 待优化的代码

        Returns:
            优化建议列表
        """
        request = InnovationRequest(
            code=code,
            innovation_type=InnovationType.OPTIMIZATION,
            goals=["提升性能", "减少资源消耗"],
        )
        result = self.innovate(request)
        return [result] if result.confidence > 0 else []

    def suggest_patterns(self, code: str, context: str = "") -> list[CodeInnovation]:
        """建议设计模式

        Args:
            code: 待分析的代码
            context: 上下文信息

        Returns:
            设计模式建议列表
        """
        request = InnovationRequest(
            code=code,
            context=context,
            innovation_type=InnovationType.PATTERN,
            goals=["提升代码结构", "增强可扩展性"],
        )
        result = self.innovate(request)
        return [result] if result.confidence > 0 else []

    def suggest_refactoring(
        self, code: str, issues: Optional[list[str]] = None
    ) -> list[CodeInnovation]:
        """建议重构方案

        Args:
            code: 待重构的代码
            issues: 已知问题列表

        Returns:
            重构建议列表
        """
        request = InnovationRequest(
            code=code,
            innovation_type=InnovationType.REFACTORING,
            goals=["改善代码质量", "提升可维护性"],
            constraints=issues or [],
        )
        result = self.innovate(request)
        return [result] if result.confidence > 0 else []

    def design_feature(
        self,
        code: str,
        feature_description: str,
        constraints: Optional[list[str]] = None,
    ) -> CodeInnovation:
        """设计新功能

        Args:
            code: 现有代码
            feature_description: 功能描述
            constraints: 约束条件

        Returns:
            功能设计方案
        """
        request = InnovationRequest(
            code=code,
            context=feature_description,
            innovation_type=InnovationType.FEATURE,
            goals=["实现新功能", "保持代码一致性"],
            constraints=constraints or [],
        )
        return self.innovate(request)

    def analyze_architecture(
        self,
        code: str,
        architecture_context: str = "",
    ) -> CodeInnovation:
        """分析架构并提供改进建议

        Args:
            code: 代码
            architecture_context: 架构上下文

        Returns:
            架构改进建议
        """
        request = InnovationRequest(
            code=code,
            context=architecture_context,
            innovation_type=InnovationType.ARCHITECTURE,
            goals=["改善架构", "提升可扩展性", "降低耦合"],
        )
        return self.innovate(request)

    def get_innovation_statistics(self) -> dict[str, Any]:
        """获取创新统计"""
        stats = self.get_statistics()
        stats["total_innovations"] = self.innovation_counter
        return stats
