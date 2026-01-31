"""LLM 推理引擎

提供统一的 LLM 调用接口，支持多种推理任务。
"""

import json

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional, Protocol


class ReasoningType(Enum):
    """推理类型"""

    ANALYSIS = "analysis"  # 分析推理
    GENERATION = "generation"  # 生成推理
    EVALUATION = "evaluation"  # 评估推理
    DECISION = "decision"  # 决策推理
    EXTRACTION = "extraction"  # 提取推理
    CLASSIFICATION = "classification"  # 分类推理


@dataclass
class ReasoningContext:
    """推理上下文

    包含 LLM 推理所需的所有上下文信息。
    """

    task_type: ReasoningType
    input_data: str  # 输入数据
    instruction: str  # 推理指令
    examples: list[dict[str, str]] = field(default_factory=list)  # 示例
    constraints: list[str] = field(default_factory=list)  # 约束条件
    output_format: Optional[str] = None  # 期望的输出格式
    metadata: dict[str, Any] = field(default_factory=dict)  # 元数据

    def to_prompt(self) -> str:
        """转换为 LLM prompt"""
        parts = []

        # 指令
        parts.append(f"## 任务\n{self.instruction}")

        # 约束
        if self.constraints:
            parts.append("## 约束条件")
            for c in self.constraints:
                parts.append(f"- {c}")

        # 示例
        if self.examples:
            parts.append("## 示例")
            for i, ex in enumerate(self.examples, 1):
                parts.append(f"### 示例 {i}")
                if "input" in ex:
                    parts.append(f"输入: {ex['input']}")
                if "output" in ex:
                    parts.append(f"输出: {ex['output']}")

        # 输出格式
        if self.output_format:
            parts.append(f"## 输出格式\n{self.output_format}")

        # 输入数据
        parts.append(f"## 输入\n{self.input_data}")

        parts.append("## 输出")

        return "\n\n".join(parts)


@dataclass
class ReasoningResult:
    """推理结果

    LLM 推理的输出结果。
    """

    success: bool
    output: str  # 原始输出
    parsed_output: Optional[Any] = None  # 解析后的输出
    reasoning_type: ReasoningType = ReasoningType.ANALYSIS
    confidence: float = 0.0  # 置信度
    tokens_used: int = 0  # 使用的 token 数
    latency_ms: float = 0.0  # 延迟（毫秒）
    error: Optional[str] = None  # 错误信息
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "output": self.output,
            "parsed_output": self.parsed_output,
            "reasoning_type": self.reasoning_type.value,
            "confidence": self.confidence,
            "tokens_used": self.tokens_used,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
        }


class LLMClient(Protocol):
    """LLM 客户端协议

    定义 LLM 客户端需要实现的接口。
    """

    def complete(self, prompt: str, **kwargs: Any) -> str:
        """执行补全"""
        ...


class LLMReasoner:
    """LLM 推理器

    统一的 LLM 推理接口，支持多种推理任务。
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        default_model: str = "default",
    ) -> None:
        """初始化推理器

        Args:
            llm_client: LLM 客户端（可选，用于实际调用）
            default_model: 默认模型名称
        """
        self.llm_client = llm_client
        self.default_model = default_model
        self.reasoning_history: list[ReasoningResult] = []

        # 推理模板
        self.templates: dict[ReasoningType, str] = {
            ReasoningType.ANALYSIS: "分析以下内容，提供详细的分析结果：",
            ReasoningType.GENERATION: "根据以下要求生成内容：",
            ReasoningType.EVALUATION: "评估以下内容，给出评分和理由：",
            ReasoningType.DECISION: "基于以下信息做出决策：",
            ReasoningType.EXTRACTION: "从以下内容中提取关键信息：",
            ReasoningType.CLASSIFICATION: "对以下内容进行分类：",
        }

    def reason(
        self,
        context: ReasoningContext,
        parse_output: Optional[Callable[[str], Any]] = None,
    ) -> ReasoningResult:
        """执行推理

        Args:
            context: 推理上下文
            parse_output: 输出解析函数

        Returns:
            推理结果
        """
        import time

        start_time = time.time()

        try:
            # 构建 prompt
            prompt = context.to_prompt()

            # 调用 LLM
            if self.llm_client:
                output = self.llm_client.complete(prompt)
            else:
                # 模拟模式：返回占位结果
                output = self._simulate_reasoning(context)

            # 解析输出
            parsed = None
            if parse_output:
                try:
                    parsed = parse_output(output)
                except Exception:
                    pass

            latency = (time.time() - start_time) * 1000

            result = ReasoningResult(
                success=True,
                output=output,
                parsed_output=parsed,
                reasoning_type=context.task_type,
                confidence=self._estimate_confidence(output),
                latency_ms=latency,
            )

        except Exception as e:
            result = ReasoningResult(
                success=False,
                output="",
                reasoning_type=context.task_type,
                error=str(e),
                latency_ms=(time.time() - start_time) * 1000,
            )

        self.reasoning_history.append(result)
        return result

    def _simulate_reasoning(self, context: ReasoningContext) -> str:
        """模拟推理（无 LLM 客户端时使用）

        这个方法提供基于规则的回退逻辑，
        当没有 LLM 客户端时仍能提供基本功能。
        """
        task_type = context.task_type

        if task_type == ReasoningType.ANALYSIS:
            return self._simulate_analysis(context)
        elif task_type == ReasoningType.GENERATION:
            return self._simulate_generation(context)
        elif task_type == ReasoningType.EVALUATION:
            return self._simulate_evaluation(context)
        elif task_type == ReasoningType.DECISION:
            return self._simulate_decision(context)
        elif task_type == ReasoningType.EXTRACTION:
            return self._simulate_extraction(context)
        else:  # CLASSIFICATION
            return self._simulate_classification(context)

    def _simulate_analysis(self, context: ReasoningContext) -> str:
        """模拟分析推理"""
        input_data = context.input_data
        return json.dumps(
            {
                "analysis": "对输入内容的分析结果",
                "key_points": ["要点1", "要点2", "要点3"],
                "summary": f"输入内容长度: {len(input_data)} 字符",
                "confidence": 0.7,
            },
            ensure_ascii=False,
            indent=2,
        )

    def _simulate_generation(self, context: ReasoningContext) -> str:
        """模拟生成推理"""
        return json.dumps(
            {
                "generated_content": f"基于指令 '{context.instruction[:50]}...' 生成的内容",
                "alternatives": ["备选方案1", "备选方案2"],
                "confidence": 0.6,
            },
            ensure_ascii=False,
            indent=2,
        )

    def _simulate_evaluation(self, context: ReasoningContext) -> str:
        """模拟评估推理"""
        return json.dumps(
            {
                "score": 75,
                "max_score": 100,
                "criteria": {
                    "completeness": 80,
                    "accuracy": 70,
                    "clarity": 75,
                },
                "feedback": "整体表现良好，有改进空间",
                "confidence": 0.65,
            },
            ensure_ascii=False,
            indent=2,
        )

    def _simulate_decision(self, context: ReasoningContext) -> str:
        """模拟决策推理"""
        return json.dumps(
            {
                "decision": "建议采用方案A",
                "reasoning": "基于输入信息的综合分析",
                "alternatives": ["方案B", "方案C"],
                "risk_level": "medium",
                "confidence": 0.6,
            },
            ensure_ascii=False,
            indent=2,
        )

    def _simulate_extraction(self, context: ReasoningContext) -> str:
        """模拟提取推理"""
        return json.dumps(
            {
                "extracted_items": [
                    {"type": "entity", "value": "提取项1"},
                    {"type": "entity", "value": "提取项2"},
                ],
                "confidence": 0.7,
            },
            ensure_ascii=False,
            indent=2,
        )

    def _simulate_classification(self, context: ReasoningContext) -> str:
        """模拟分类推理"""
        return json.dumps(
            {
                "category": "类别A",
                "probabilities": {
                    "类别A": 0.6,
                    "类别B": 0.3,
                    "类别C": 0.1,
                },
                "confidence": 0.6,
            },
            ensure_ascii=False,
            indent=2,
        )

    def _estimate_confidence(self, output: str) -> float:
        """估算输出的置信度"""
        # 基于输出长度和结构估算置信度
        if not output:
            return 0.0

        confidence = 0.5

        # 输出长度影响
        if len(output) > 100:
            confidence += 0.1
        if len(output) > 500:
            confidence += 0.1

        # JSON 结构影响
        try:
            data = json.loads(output)
            if isinstance(data, dict):
                confidence += 0.1
                if "confidence" in data:
                    # 使用输出中的置信度
                    return float(data["confidence"])
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

        return min(confidence, 1.0)

    def analyze(self, input_data: str, instruction: str = "") -> ReasoningResult:
        """执行分析推理

        Args:
            input_data: 要分析的数据
            instruction: 分析指令

        Returns:
            推理结果
        """
        context = ReasoningContext(
            task_type=ReasoningType.ANALYSIS,
            input_data=input_data,
            instruction=instruction or self.templates[ReasoningType.ANALYSIS],
            output_format="JSON 格式，包含 analysis, key_points, summary 字段",
        )
        return self.reason(context, parse_output=self._parse_json)

    def generate(self, input_data: str, instruction: str = "") -> ReasoningResult:
        """执行生成推理"""
        context = ReasoningContext(
            task_type=ReasoningType.GENERATION,
            input_data=input_data,
            instruction=instruction or self.templates[ReasoningType.GENERATION],
        )
        return self.reason(context)

    def evaluate(
        self, input_data: str, criteria: Optional[list[str]] = None
    ) -> ReasoningResult:
        """执行评估推理"""
        context = ReasoningContext(
            task_type=ReasoningType.EVALUATION,
            input_data=input_data,
            instruction=self.templates[ReasoningType.EVALUATION],
            constraints=criteria or [],
            output_format="JSON 格式，包含 score, criteria, feedback 字段",
        )
        return self.reason(context, parse_output=self._parse_json)

    def decide(
        self, input_data: str, options: Optional[list[str]] = None
    ) -> ReasoningResult:
        """执行决策推理"""
        instruction = self.templates[ReasoningType.DECISION]
        if options:
            instruction += f"\n可选项: {', '.join(options)}"

        context = ReasoningContext(
            task_type=ReasoningType.DECISION,
            input_data=input_data,
            instruction=instruction,
            output_format="JSON 格式，包含 decision, reasoning, confidence 字段",
        )
        return self.reason(context, parse_output=self._parse_json)

    def extract(
        self, input_data: str, extract_types: Optional[list[str]] = None
    ) -> ReasoningResult:
        """执行提取推理"""
        instruction = self.templates[ReasoningType.EXTRACTION]
        if extract_types:
            instruction += f"\n提取类型: {', '.join(extract_types)}"

        context = ReasoningContext(
            task_type=ReasoningType.EXTRACTION,
            input_data=input_data,
            instruction=instruction,
            output_format="JSON 格式，包含 extracted_items 数组",
        )
        return self.reason(context, parse_output=self._parse_json)

    def classify(
        self, input_data: str, categories: Optional[list[str]] = None
    ) -> ReasoningResult:
        """执行分类推理"""
        instruction = self.templates[ReasoningType.CLASSIFICATION]
        if categories:
            instruction += f"\n类别: {', '.join(categories)}"

        context = ReasoningContext(
            task_type=ReasoningType.CLASSIFICATION,
            input_data=input_data,
            instruction=instruction,
            output_format="JSON 格式，包含 category, probabilities 字段",
        )
        return self.reason(context, parse_output=self._parse_json)

    def _parse_json(self, output: str) -> Optional[dict[str, Any]]:
        """解析 JSON 输出"""
        try:
            result = json.loads(output)
            if isinstance(result, dict):
                return result
            return None
        except json.JSONDecodeError:
            # 尝试提取 JSON 块
            import re

            match = re.search(r"```json\s*(.+?)\s*```", output, re.DOTALL)
            if match:
                try:
                    result = json.loads(match.group(1))
                    if isinstance(result, dict):
                        return result
                except json.JSONDecodeError:
                    pass
        return None

    def get_history(self) -> list[ReasoningResult]:
        """获取推理历史"""
        return self.reasoning_history

    def clear_history(self) -> None:
        """清空推理历史"""
        self.reasoning_history.clear()

    def get_statistics(self) -> dict[str, Any]:
        """获取推理统计"""
        if not self.reasoning_history:
            return {
                "total": 0,
                "success_rate": 0,
                "avg_latency_ms": 0,
                "avg_confidence": 0,
            }

        total = len(self.reasoning_history)
        successful = sum(1 for r in self.reasoning_history if r.success)
        avg_latency = sum(r.latency_ms for r in self.reasoning_history) / total
        avg_confidence = sum(r.confidence for r in self.reasoning_history) / total

        return {
            "total": total,
            "successful": successful,
            "success_rate": successful / total * 100,
            "avg_latency_ms": avg_latency,
            "avg_confidence": avg_confidence,
            "by_type": self._stats_by_type(),
        }

    def _stats_by_type(self) -> dict[str, dict[str, Any]]:
        """按类型统计"""
        stats: dict[str, dict[str, Any]] = {}
        for r in self.reasoning_history:
            type_name = r.reasoning_type.value
            if type_name not in stats:
                stats[type_name] = {"count": 0, "success": 0}
            stats[type_name]["count"] += 1
            if r.success:
                stats[type_name]["success"] += 1
        return stats
