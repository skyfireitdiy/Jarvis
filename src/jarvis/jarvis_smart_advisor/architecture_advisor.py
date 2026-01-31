"""架构决策辅助模块。

基于知识图谱和历史决策，提供架构设计建议。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class DecisionType(Enum):
    """决策类型"""

    TECHNOLOGY_CHOICE = "technology_choice"  # 技术选型
    ARCHITECTURE_PATTERN = "architecture_pattern"  # 架构模式
    MODULE_DESIGN = "module_design"  # 模块设计
    API_DESIGN = "api_design"  # API设计
    DATA_MODEL = "data_model"  # 数据模型
    DEPENDENCY_MANAGEMENT = "dependency_management"  # 依赖管理


class DecisionImpact(Enum):
    """决策影响程度"""

    HIGH = "high"  # 高影响，难以逆转
    MEDIUM = "medium"  # 中等影响
    LOW = "low"  # 低影响，容易调整


@dataclass
class ArchitectureOption:
    """架构选项

    Attributes:
        name: 选项名称
        description: 选项描述
        pros: 优点列表
        cons: 缺点列表
        use_cases: 适用场景
        score: 推荐评分（0-100）
        references: 参考资料
    """

    name: str
    description: str
    pros: List[str] = field(default_factory=list)
    cons: List[str] = field(default_factory=list)
    use_cases: List[str] = field(default_factory=list)
    score: float = 50.0
    references: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "description": self.description,
            "pros": self.pros,
            "cons": self.cons,
            "use_cases": self.use_cases,
            "score": self.score,
            "references": self.references,
        }


@dataclass
class ArchitectureDecision:
    """架构决策

    Attributes:
        question: 决策问题
        decision_type: 决策类型
        impact: 影响程度
        context: 上下文信息
        options: 可选方案列表
        recommendation: 推荐方案
        rationale: 推荐理由
    """

    question: str
    decision_type: DecisionType
    impact: DecisionImpact
    context: str = ""
    options: List[ArchitectureOption] = field(default_factory=list)
    recommendation: Optional[ArchitectureOption] = None
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "question": self.question,
            "decision_type": self.decision_type.value,
            "impact": self.impact.value,
            "context": self.context,
            "options": [o.to_dict() for o in self.options],
            "recommendation": self.recommendation.to_dict()
            if self.recommendation
            else None,
            "rationale": self.rationale,
        }

    def to_markdown(self) -> str:
        """转换为Markdown格式"""
        lines = []
        lines.append(f"# 架构决策：{self.question}\n")
        lines.append(f"**决策类型**: {self.decision_type.value}\n")
        lines.append(f"**影响程度**: {self.impact.value}\n")

        if self.context:
            lines.append(f"\n## 上下文\n\n{self.context}\n")

        if self.options:
            lines.append("\n## 可选方案\n")
            for i, option in enumerate(self.options, 1):
                lines.append(f"\n### 方案{i}: {option.name}\n")
                lines.append(f"{option.description}\n")
                lines.append(f"**推荐评分**: {option.score:.1f}/100\n")

                if option.pros:
                    lines.append("\n**优点**:")
                    for pro in option.pros:
                        lines.append(f"- ✅ {pro}")
                    lines.append("")

                if option.cons:
                    lines.append("\n**缺点**:")
                    for con in option.cons:
                        lines.append(f"- ❌ {con}")
                    lines.append("")

                if option.use_cases:
                    lines.append("\n**适用场景**:")
                    for case in option.use_cases:
                        lines.append(f"- {case}")
                    lines.append("")

        if self.recommendation:
            lines.append(f"\n## 推荐方案\n\n**{self.recommendation.name}**\n")
            if self.rationale:
                lines.append(f"\n### 推荐理由\n\n{self.rationale}\n")

        return "\n".join(lines)


class ArchitectureAdvisor:
    """架构决策辅助器

    基于知识图谱和历史决策，提供架构设计建议。
    """

    # 常见架构模式知识库
    ARCHITECTURE_PATTERNS: Dict[str, Dict[str, Any]] = {
        "layered": {
            "name": "分层架构",
            "description": "将系统分为多个层次，每层只与相邻层交互",
            "pros": ["职责分离清晰", "易于理解和维护", "支持团队并行开发"],
            "cons": ["可能导致性能开销", "层间依赖可能变得复杂"],
            "use_cases": ["企业应用", "Web应用", "传统业务系统"],
        },
        "microservices": {
            "name": "微服务架构",
            "description": "将应用拆分为多个独立部署的小服务",
            "pros": ["独立部署和扩展", "技术栈灵活", "故障隔离"],
            "cons": ["运维复杂度高", "分布式系统挑战", "数据一致性难保证"],
            "use_cases": ["大型分布式系统", "需要高可扩展性的应用", "多团队协作项目"],
        },
        "event_driven": {
            "name": "事件驱动架构",
            "description": "通过事件进行组件间通信",
            "pros": ["松耦合", "高可扩展性", "异步处理"],
            "cons": ["调试困难", "事件顺序难保证", "最终一致性"],
            "use_cases": ["实时数据处理", "IoT系统", "消息队列系统"],
        },
        "clean_architecture": {
            "name": "整洁架构",
            "description": "以业务逻辑为核心，外层依赖内层",
            "pros": ["业务逻辑独立", "易于测试", "框架无关"],
            "cons": ["初期开发成本高", "需要更多抽象"],
            "use_cases": ["复杂业务系统", "长期维护项目", "需要高测试覆盖的项目"],
        },
        "hexagonal": {
            "name": "六边形架构",
            "description": "通过端口和适配器隔离核心业务",
            "pros": ["核心业务隔离", "易于替换外部依赖", "测试友好"],
            "cons": ["概念较抽象", "需要更多代码"],
            "use_cases": ["需要多种外部集成的系统", "DDD项目"],
        },
    }

    # 技术选型知识库
    TECHNOLOGY_CHOICES: Dict[str, Dict[str, Any]] = {
        "database": {
            "postgresql": {
                "name": "PostgreSQL",
                "description": "功能强大的开源关系型数据库",
                "pros": ["功能丰富", "ACID支持", "扩展性好", "社区活跃"],
                "cons": ["配置复杂", "水平扩展较难"],
                "use_cases": ["复杂查询", "事务处理", "地理数据"],
            },
            "mysql": {
                "name": "MySQL",
                "description": "流行的开源关系型数据库",
                "pros": ["简单易用", "性能好", "生态丰富"],
                "cons": ["功能相对较少", "某些高级特性需要付费"],
                "use_cases": ["Web应用", "读多写少场景"],
            },
            "mongodb": {
                "name": "MongoDB",
                "description": "流行的文档型NoSQL数据库",
                "pros": ["灵活的数据模型", "水平扩展容易", "开发效率高"],
                "cons": ["不支持复杂事务", "数据一致性较弱"],
                "use_cases": ["快速迭代项目", "非结构化数据", "日志存储"],
            },
            "redis": {
                "name": "Redis",
                "description": "高性能内存数据库",
                "pros": ["极高性能", "丰富数据结构", "支持持久化"],
                "cons": ["内存成本高", "数据量受限"],
                "use_cases": ["缓存", "会话存储", "实时排行榜"],
            },
        },
        "web_framework": {
            "fastapi": {
                "name": "FastAPI",
                "description": "现代高性能Python Web框架",
                "pros": ["高性能", "自动文档", "类型提示支持", "异步支持"],
                "cons": ["相对较新", "生态不如Django丰富"],
                "use_cases": ["API服务", "微服务", "高性能应用"],
            },
            "django": {
                "name": "Django",
                "description": "全功能Python Web框架",
                "pros": ["功能完整", "生态丰富", "文档完善", "安全性好"],
                "cons": ["较重", "灵活性相对较低"],
                "use_cases": ["全栈Web应用", "CMS", "企业应用"],
            },
            "flask": {
                "name": "Flask",
                "description": "轻量级Python Web框架",
                "pros": ["轻量灵活", "易于学习", "扩展性好"],
                "cons": ["需要自己选择组件", "大型项目需要更多规划"],
                "use_cases": ["小型应用", "API服务", "原型开发"],
            },
        },
    }

    def __init__(self, project_dir: str = "."):
        """初始化架构决策辅助器

        Args:
            project_dir: 项目目录路径
        """
        self.project_dir = Path(project_dir)
        self._knowledge_graph: Optional[Any] = None

    @property
    def knowledge_graph(self):
        """懒加载知识图谱"""
        if self._knowledge_graph is None:
            from jarvis.jarvis_knowledge_graph import KnowledgeGraph

            self._knowledge_graph = KnowledgeGraph(str(self.project_dir))
        return self._knowledge_graph

    def get_architecture_options(
        self, decision_type: DecisionType, context: str = ""
    ) -> List[ArchitectureOption]:
        """获取架构选项

        Args:
            decision_type: 决策类型
            context: 上下文信息

        Returns:
            架构选项列表
        """
        options = []

        if decision_type == DecisionType.ARCHITECTURE_PATTERN:
            for pattern_id, pattern_info in self.ARCHITECTURE_PATTERNS.items():
                score = self._calculate_pattern_score(pattern_id, context)
                option = ArchitectureOption(
                    name=pattern_info["name"],
                    description=pattern_info["description"],
                    pros=pattern_info["pros"],
                    cons=pattern_info["cons"],
                    use_cases=pattern_info["use_cases"],
                    score=score,
                )
                options.append(option)

        elif decision_type == DecisionType.TECHNOLOGY_CHOICE:
            # 根据上下文确定技术类别
            category = self._detect_technology_category(context)
            if category and category in self.TECHNOLOGY_CHOICES:
                for tech_id, tech_info in self.TECHNOLOGY_CHOICES[category].items():
                    score = self._calculate_tech_score(tech_id, context)
                    option = ArchitectureOption(
                        name=tech_info["name"],
                        description=tech_info["description"],
                        pros=tech_info["pros"],
                        cons=tech_info["cons"],
                        use_cases=tech_info["use_cases"],
                        score=score,
                    )
                    options.append(option)

        # 按评分排序
        options.sort(key=lambda x: x.score, reverse=True)
        return options

    def _calculate_pattern_score(self, pattern_id: str, context: str) -> float:
        """计算架构模式评分"""
        base_score = 50.0
        context_lower = context.lower()

        # 根据上下文关键词调整评分
        score_adjustments: Dict[str, Dict[str, Any]] = {
            "layered": {
                "keywords": ["简单", "传统", "企业", "web", "simple", "traditional"],
                "boost": 20,
            },
            "microservices": {
                "keywords": ["分布式", "扩展", "独立", "团队", "distributed", "scale"],
                "boost": 20,
            },
            "event_driven": {
                "keywords": ["实时", "异步", "消息", "事件", "realtime", "async"],
                "boost": 20,
            },
            "clean_architecture": {
                "keywords": ["测试", "业务", "复杂", "长期", "test", "business"],
                "boost": 20,
            },
            "hexagonal": {
                "keywords": ["集成", "适配", "ddd", "领域", "integration", "adapter"],
                "boost": 20,
            },
        }

        if pattern_id in score_adjustments:
            adjustment = score_adjustments[pattern_id]
            for keyword in adjustment["keywords"]:
                if keyword in context_lower:
                    base_score += adjustment["boost"]
                    break

        return min(100.0, base_score)

    def _calculate_tech_score(self, tech_id: str, context: str) -> float:
        """计算技术选型评分"""
        base_score = 50.0
        context_lower = context.lower()

        # 根据上下文关键词调整评分
        score_adjustments: Dict[str, Dict[str, Any]] = {
            "postgresql": {
                "keywords": ["复杂查询", "事务", "地理", "complex", "transaction"],
                "boost": 20,
            },
            "mysql": {
                "keywords": ["简单", "web", "读多", "simple"],
                "boost": 20,
            },
            "mongodb": {
                "keywords": ["文档", "灵活", "快速", "document", "flexible"],
                "boost": 20,
            },
            "redis": {
                "keywords": ["缓存", "高性能", "实时", "cache", "performance"],
                "boost": 20,
            },
            "fastapi": {
                "keywords": ["api", "高性能", "异步", "async", "performance"],
                "boost": 20,
            },
            "django": {
                "keywords": ["全栈", "cms", "企业", "fullstack", "enterprise"],
                "boost": 20,
            },
            "flask": {
                "keywords": ["轻量", "简单", "原型", "light", "simple", "prototype"],
                "boost": 20,
            },
        }

        if tech_id in score_adjustments:
            adjustment = score_adjustments[tech_id]
            for keyword in adjustment["keywords"]:
                if keyword in context_lower:
                    base_score += adjustment["boost"]
                    break

        return min(100.0, base_score)

    def _detect_technology_category(self, context: str) -> Optional[str]:
        """检测技术类别"""
        context_lower = context.lower()

        category_keywords = {
            "database": [
                "数据库",
                "存储",
                "database",
                "storage",
                "db",
                "查询",
                "事务",
                "query",
                "transaction",
            ],
            "web_framework": ["框架", "web", "api", "framework", "后端", "backend"],
        }

        for category, keywords in category_keywords.items():
            for keyword in keywords:
                if keyword in context_lower:
                    return category

        return None

    def analyze_decision(
        self, question: str, context: str = ""
    ) -> ArchitectureDecision:
        """分析架构决策

        Args:
            question: 决策问题
            context: 上下文信息

        Returns:
            架构决策分析结果
        """
        # 识别决策类型
        decision_type = self._identify_decision_type(question)

        # 评估影响程度
        impact = self._assess_impact(question, context)

        # 获取可选方案
        options = self.get_architecture_options(decision_type, context)

        # 选择推荐方案
        recommendation = options[0] if options else None

        # 生成推荐理由
        rationale = (
            self._generate_rationale(recommendation, context) if recommendation else ""
        )

        return ArchitectureDecision(
            question=question,
            decision_type=decision_type,
            impact=impact,
            context=context,
            options=options,
            recommendation=recommendation,
            rationale=rationale,
        )

    def _identify_decision_type(self, question: str) -> DecisionType:
        """识别决策类型"""
        question_lower = question.lower()

        # 按优先级排序，架构模式优先于技术选型
        type_keywords = {
            DecisionType.ARCHITECTURE_PATTERN: [
                "架构",
                "模式",
                "设计模式",
                "architecture",
                "pattern",
            ],
            DecisionType.TECHNOLOGY_CHOICE: [
                "技术",
                "数据库",
                "框架",
                "technology",
                "database",
                "framework",
            ],
            DecisionType.MODULE_DESIGN: [
                "模块",
                "组件",
                "拆分",
                "module",
                "component",
                "split",
            ],
            DecisionType.API_DESIGN: [
                "api",
                "接口",
                "endpoint",
                "interface",
            ],
            DecisionType.DATA_MODEL: [
                "数据模型",
                "实体",
                "表结构",
                "data model",
                "entity",
                "schema",
            ],
            DecisionType.DEPENDENCY_MANAGEMENT: [
                "依赖",
                "版本",
                "包",
                "dependency",
                "version",
                "package",
            ],
        }

        for decision_type, keywords in type_keywords.items():
            for keyword in keywords:
                if keyword in question_lower:
                    return decision_type

        return DecisionType.ARCHITECTURE_PATTERN

    def _assess_impact(self, question: str, context: str) -> DecisionImpact:
        """评估决策影响程度"""
        combined = (question + " " + context).lower()

        high_impact_keywords = [
            "核心",
            "基础",
            "全局",
            "重构",
            "迁移",
            "core",
            "foundation",
            "global",
            "refactor",
            "migrate",
        ]

        low_impact_keywords = [
            "局部",
            "小",
            "临时",
            "实验",
            "local",
            "small",
            "temporary",
            "experiment",
        ]

        for keyword in high_impact_keywords:
            if keyword in combined:
                return DecisionImpact.HIGH

        for keyword in low_impact_keywords:
            if keyword in combined:
                return DecisionImpact.LOW

        return DecisionImpact.MEDIUM

    def _generate_rationale(self, option: ArchitectureOption, context: str) -> str:
        """生成推荐理由"""
        parts = []

        parts.append(f"推荐使用 **{option.name}**，主要原因如下：")
        parts.append("")

        if option.pros:
            parts.append("**主要优势**：")
            for i, pro in enumerate(option.pros[:3], 1):
                parts.append(f"{i}. {pro}")
            parts.append("")

        if option.use_cases:
            parts.append("**适用场景**：")
            parts.append("、".join(option.use_cases[:3]))
            parts.append("")

        if option.cons:
            parts.append("**需要注意**：")
            parts.append(option.cons[0] if option.cons else "无特别注意事项")

        return "\n".join(parts)
