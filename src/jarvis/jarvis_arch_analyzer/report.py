"""架构健康度报告生成模块。

提供综合分析报告生成功能，包括健康度评分、风险等级识别、
改进建议生成等。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RiskLevel(Enum):
    """风险等级。"""

    HEALTHY = "healthy"  # 健康 (90-100)
    GOOD = "good"  # 良好 (70-89)
    WARNING = "warning"  # 警告 (50-69)
    DANGER = "danger"  # 危险 (<50)

    @classmethod
    def from_score(cls, score: float) -> RiskLevel:
        """根据评分获取风险等级。

        Args:
            score: 健康度评分 (0-100)

        Returns:
            风险等级
        """
        if score >= 90:
            return cls.HEALTHY
        elif score >= 70:
            return cls.GOOD
        elif score >= 50:
            return cls.WARNING
        else:
            return cls.DANGER


class Priority(Enum):
    """优先级。"""

    P0 = "P0"  # 关键问题，必须立即处理
    P1 = "P1"  # 重要问题，应尽快处理
    P2 = "P2"  # 一般问题，可以逐步改进


@dataclass
class HealthDimension:
    """健康度维度。

    Attributes:
        name: 维度名称
        score: 维度评分 (0-100)
        weight: 权重 (0-1)
        status: 状态
        details: 详细信息
    """

    name: str
    score: float
    weight: float
    status: str
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def weighted_score(self) -> float:
        """计算加权分数。"""
        return self.score * self.weight


@dataclass
class ImprovementSuggestion:
    """改进建议。

    Attributes:
        priority: 优先级
        category: 类别
        description: 描述
        impact: 预期影响
        effort: 实施难度 (low/medium/high)
    """

    priority: Priority
    category: str
    description: str
    impact: str
    effort: str

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "priority": self.priority.value,
            "category": self.category,
            "description": self.description,
            "impact": self.impact,
            "effort": self.effort,
        }


@dataclass
class ArchitectureHealthReport:
    """架构健康度报告。

    Attributes:
        project_path: 项目路径
        overall_score: 总体健康度评分 (0-100)
        risk_level: 风险等级
        dimensions: 各维度评分
        suggestions: 改进建议列表
        summary: 摘要
        timestamp: 生成时间戳
    """

    project_path: str
    overall_score: float
    risk_level: RiskLevel
    dimensions: list[HealthDimension] = field(default_factory=list)
    suggestions: list[ImprovementSuggestion] = field(default_factory=list)
    summary: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "project_path": self.project_path,
            "overall_score": self.overall_score,
            "risk_level": self.risk_level.value,
            "dimensions": [
                {
                    "name": d.name,
                    "score": d.score,
                    "weight": d.weight,
                    "status": d.status,
                    "weighted_score": d.weighted_score,
                    "details": d.details,
                }
                for d in self.dimensions
            ],
            "suggestions": [s.to_dict() for s in self.suggestions],
            "summary": self.summary,
            "timestamp": self.timestamp,
        }

    def to_json(self, indent: int = 2) -> str:
        """转换为JSON字符串。"""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_markdown(self) -> str:
        """转换为Markdown格式。"""
        lines = [
            "# 架构健康度报告",
            f"\n**项目路径**: `{self.project_path}`",
            f"**总体评分**: {self.overall_score:.1f}/100",
            f"**风险等级**: {self._get_risk_level_emoji()} {self.risk_level.value.upper()}",
            f"**生成时间**: {self.timestamp}",
            "\n---\n",
            "## 健康度维度",
        ]

        for dim in self.dimensions:
            status_emoji = self._get_status_emoji(dim.status)
            lines.append(f"\n### {dim.name} ({status_emoji} {dim.status.upper()})")
            lines.append(f"- **评分**: {dim.score:.1f}/100 (权重: {dim.weight:.0%})")
            lines.append(f"- **加权分数**: {dim.weighted_score:.1f}")

        lines.append("\n---\n")
        lines.append("## 改进建议")

        if not self.suggestions:
            lines.append("\n✨ 恭喜！未发现需要改进的问题。")
        else:
            # 按优先级分组
            grouped: dict[str, list[ImprovementSuggestion]] = {}
            for sug in self.suggestions:
                key = sug.priority.value
                if key not in grouped:
                    grouped[key] = []
                grouped[key].append(sug)

            for priority in ["P0", "P1", "P2"]:
                if priority not in grouped:
                    continue
                lines.append(f"\n### {priority} - 优先级")
                for sug in grouped[priority]:
                    lines.append(f"\n#### {sug.category}")
                    lines.append(f"- **描述**: {sug.description}")
                    lines.append(f"- **预期影响**: {sug.impact}")
                    lines.append(f"- **实施难度**: {sug.effort}")

        lines.append("\n---\n")
        lines.append(f"\n{self.summary}")

        return "\n".join(lines)

    def to_html(self) -> str:
        """转换为HTML格式。"""
        html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>架构健康度报告</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 10px; margin-bottom: 30px; }}
        .score-card {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-bottom: 20px; }}
        .risk-healthy {{ background: #d4edda; color: #155724; }}
        .risk-good {{ background: #cce5ff; color: #004085; }}
        .risk-warning {{ background: #fff3cd; color: #856404; }}
        .risk-danger {{ background: #f8d7da; color: #721c24; }}
        .dimension {{ margin-bottom: 15px; padding: 15px; background: #f8f9fa; border-radius: 8px; }}
        .suggestion {{ margin-bottom: 20px; padding: 15px; border-left: 4px solid #667eea; background: #f8f9fa; }}
        .p0 {{ border-color: #dc3545; }}
        .p1 {{ border-color: #ffc107; }}
        .p2 {{ border-color: #28a745; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏗️ 架构健康度报告</h1>
            <p><strong>项目路径</strong>: {self.project_path}</p>
            <p><strong>总体评分</strong>: {self.overall_score:.1f}/100</p>
            <p><strong>风险等级</strong>: {self.risk_level.value.upper()}</p>
            <p><strong>生成时间</strong>: {self.timestamp}</p>
        </div>
"""

        # 健康度维度
        html += '<div class="score-card"><h2>健康度维度</h2>'
        for dim in self.dimensions:
            status_class = f"risk-{dim.status}"
            html += f"""
        <div class="dimension {status_class}">
            <h3>{dim.name} - {dim.score:.1f}/100</h3>
            <p>状态: {dim.status.upper()} | 权重: {dim.weight:.0%} | 加权分数: {dim.weighted_score:.1f}</p>
        </div>
"""
        html += "</div>"

        # 改进建议
        html += '<div class="score-card"><h2>改进建议</h2>'
        if not self.suggestions:
            html += "<p>✨ 恭喜！未发现需要改进的问题。</p>"
        else:
            for sug in self.suggestions:
                priority_class = sug.priority.value.lower()
                html += f"""
        <div class="suggestion {priority_class}">
            <h3>[{sug.priority.value}] {sug.category}</h3>
            <p><strong>描述</strong>: {sug.description}</p>
            <p><strong>预期影响</strong>: {sug.impact}</p>
            <p><strong>实施难度</strong>: {sug.effort}</p>
        </div>
"""
        html += "</div>"

        # 摘要
        html += f"""
        <div class="score-card">
            <h2>摘要</h2>
            <p>{self.summary}</p>
        </div>
    </div>
</body>
</html>
"""

        return html

    def _get_risk_level_emoji(self) -> str:
        """获取风险等级emoji。"""
        emojis = {
            RiskLevel.HEALTHY: "✅",
            RiskLevel.GOOD: "🟢",
            RiskLevel.WARNING: "⚠️",
            RiskLevel.DANGER: "🔴",
        }
        return emojis.get(self.risk_level, "")

    def _get_status_emoji(self, status: str) -> str:
        """获取状态emoji。"""
        emojis = {"pass": "✅", "warning": "⚠️", "fail": "❌"}
        return emojis.get(status, "")


class HealthScoreCalculator:
    """健康度评分计算器。"""

    # 默认权重配置
    DEFAULT_WEIGHTS = {
        "代码复杂度分析": 0.30,
        "依赖关系分析": 0.35,
        "代码重复度分析": 0.35,
    }

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        """初始化计算器。

        Args:
            weights: 各维度权重配置
        """
        self.weights = weights or self.DEFAULT_WEIGHTS

    def calculate(
        self, results: list[Any], weights: dict[str, float] | None = None
    ) -> tuple[float, list[HealthDimension]]:
        """计算健康度评分。

        Args:
            results: 分析结果列表 (AnalysisResult对象)
            weights: 自定义权重 (可选)

        Returns:
            (总体评分, 维度列表)
        """
        used_weights = weights or self.weights
        dimensions: list[HealthDimension] = []

        for result in results:
            weight = used_weights.get(result.name, 0.1)
            dimension = HealthDimension(
                name=result.name,
                score=result.score,
                weight=weight,
                status=result.status,
                details=result.details,
            )
            dimensions.append(dimension)

        # 计算总体评分（加权平均）
        if dimensions:
            total_weight = sum(d.weight for d in dimensions)
            if total_weight > 0:
                overall_score = sum(d.weighted_score for d in dimensions) / total_weight
            else:
                overall_score = 0.0
        else:
            overall_score = 0.0

        return overall_score, dimensions


class ReportGenerator:
    """报告生成器。"""

    def __init__(self) -> None:
        """初始化报告生成器。"""
        self.calculator = HealthScoreCalculator()

    def generate(
        self,
        project_path: str,
        results: list[Any],
        weights: dict[str, float] | None = None,
    ) -> ArchitectureHealthReport:
        """生成健康度报告。

        Args:
            project_path: 项目路径
            results: 分析结果列表
            weights: 自定义权重 (可选)

        Returns:
            架构健康度报告
        """
        # 计算健康度评分
        overall_score, dimensions = self.calculator.calculate(results, weights)

        # 识别风险等级
        risk_level = RiskLevel.from_score(overall_score)

        # 生成改进建议
        suggestions = self._generate_suggestions(results)

        # 生成摘要
        summary = self._generate_summary(
            overall_score, risk_level, dimensions, suggestions
        )

        return ArchitectureHealthReport(
            project_path=project_path,
            overall_score=overall_score,
            risk_level=risk_level,
            dimensions=dimensions,
            suggestions=suggestions,
            summary=summary,
            timestamp=self._get_timestamp(),
        )

    def _generate_suggestions(self, results: list[Any]) -> list[ImprovementSuggestion]:
        """生成改进建议。

        Args:
            results: 分析结果列表

        Returns:
            改进建议列表（按优先级排序）
        """
        suggestions: list[ImprovementSuggestion] = []

        for result in results:
            # 根据不同分析类型生成建议
            if result.name == "依赖关系分析":
                suggestions.extend(self._generate_dependency_suggestions(result))
            elif result.name == "代码复杂度分析":
                suggestions.extend(self._generate_complexity_suggestions(result))
            elif result.name == "代码重复度分析":
                suggestions.extend(self._generate_duplication_suggestions(result))

        # 按优先级排序
        priority_order = {Priority.P0: 0, Priority.P1: 1, Priority.P2: 2}
        suggestions.sort(key=lambda s: priority_order[s.priority])

        return suggestions

    def _generate_dependency_suggestions(
        self, result: Any
    ) -> list[ImprovementSuggestion]:
        """生成依赖分析相关建议。"""
        suggestions: list[ImprovementSuggestion] = []
        details = result.details

        # 循环依赖 (P0)
        circular_count = details.get("circular_dependencies_count", 0)
        if circular_count > 0:
            suggestions.append(
                ImprovementSuggestion(
                    priority=Priority.P0,
                    category="依赖关系",
                    description=f"发现 {circular_count} 个循环依赖，必须立即消除",
                    impact="显著提升架构稳定性，避免潜在的设计问题",
                    effort="medium",
                )
            )

        # 高耦合度 (P1)
        avg_coupling = details.get("average_coupling", 0)
        if avg_coupling > 3:
            suggestions.append(
                ImprovementSuggestion(
                    priority=Priority.P1,
                    category="模块耦合",
                    description=f"平均耦合度过高 ({avg_coupling:.1f})，建议降低模块间依赖",
                    impact="提升代码可维护性和可测试性",
                    effort="high",
                )
            )

        return suggestions

    def _generate_complexity_suggestions(
        self, result: Any
    ) -> list[ImprovementSuggestion]:
        """生成复杂度分析相关建议。"""
        suggestions: list[ImprovementSuggestion] = []
        details = result.details

        # 高复杂度函数 (P1)
        high_count = details.get("high_complexity_count", 0)
        if high_count > 0:
            avg_cyclomatic = details.get("average_cyclomatic", 0)
            suggestions.append(
                ImprovementSuggestion(
                    priority=Priority.P1,
                    category="代码复杂度",
                    description=f"发现 {high_count} 个高复杂度函数（平均圈复杂度: {avg_cyclomatic:.1f}），建议重构",
                    impact="显著提升代码可读性和可维护性",
                    effort="medium",
                )
            )

        return suggestions

    def _generate_duplication_suggestions(
        self, result: Any
    ) -> list[ImprovementSuggestion]:
        """生成重复度分析相关建议。"""
        suggestions: list[ImprovementSuggestion] = []
        details = result.details

        # 高重复率 (P0)
        duplication_rate = details.get("duplication_rate", 0)
        if duplication_rate > 0.15:
            dup_count = details.get("duplicated_functions", 0)
            suggestions.append(
                ImprovementSuggestion(
                    priority=Priority.P0,
                    category="代码重复",
                    description=f"重复率过高 ({duplication_rate:.1%}, {dup_count}个函数)，建议提取公共函数",
                    impact="减少维护成本，降低bug修复风险",
                    effort="low",
                )
            )
        elif duplication_rate > 0.05:
            suggestions.append(
                ImprovementSuggestion(
                    priority=Priority.P2,
                    category="代码重复",
                    description=f"存在代码重复 ({duplication_rate:.1%})，建议逐步优化",
                    impact="提升代码质量，减少冗余",
                    effort="low",
                )
            )

        return suggestions

    def _generate_summary(
        self,
        overall_score: float,
        risk_level: RiskLevel,
        dimensions: list[HealthDimension],
        suggestions: list[ImprovementSuggestion],
    ) -> str:
        """生成报告摘要。

        Args:
            overall_score: 总体评分
            risk_level: 风险等级
            dimensions: 维度列表
            suggestions: 建议列表

        Returns:
            摘要文本
        """
        lines = [
            "## 总体评估",
            f"项目架构健康度评分为 **{overall_score:.1f}/100**，风险等级为 **{risk_level.value.upper()}**。",
            "",
            "### 维度分析",
        ]

        for dim in dimensions:
            status_text = {
                "pass": "✅ 通过",
                "warning": "⚠️ 警告",
                "fail": "❌ 失败",
            }.get(dim.status, dim.status)
            lines.append(f"- **{dim.name}**: {dim.score:.1f}/100 - {status_text}")

        lines.append("")
        lines.append("### 关键发现")

        p0_count = sum(1 for s in suggestions if s.priority == Priority.P0)
        p1_count = sum(1 for s in suggestions if s.priority == Priority.P1)
        p2_count = sum(1 for s in suggestions if s.priority == Priority.P2)

        if p0_count == 0 and p1_count == 0 and p2_count == 0:
            lines.append("✨ 未发现关键问题，项目架构健康！")
        else:
            if p0_count > 0:
                lines.append(f"- 🔴 **P0关键问题**: {p0_count} 个")
            if p1_count > 0:
                lines.append(f"- 🟡 **P1重要问题**: {p1_count} 个")
            if p2_count > 0:
                lines.append(f"- 🟢 **P2一般问题**: {p2_count} 个")

        lines.append("")
        lines.append("### 改进方向")

        if risk_level == RiskLevel.HEALTHY:
            lines.append("继续保持优秀的代码质量，定期进行架构审查。")
        elif risk_level == RiskLevel.GOOD:
            lines.append("关注建议的改进方向，持续优化架构设计。")
        elif risk_level == RiskLevel.WARNING:
            lines.append("建议优先处理P0和P1问题，防止架构进一步恶化。")
        else:
            lines.append("⚠️ 架构存在严重问题，建议立即启动重构计划！")

        return "\n".join(lines)

    def _get_timestamp(self) -> str:
        """获取当前时间戳。"""
        from datetime import datetime

        return datetime.now().isoformat()
