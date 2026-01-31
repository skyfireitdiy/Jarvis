"""创意生成引擎

基于混合引擎的创意生成，支持规则匹配和 LLM 推理。
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


class IdeaCategory(Enum):
    """创意类别"""

    FEATURE = "feature"  # 新功能
    OPTIMIZATION = "optimization"  # 优化改进
    REFACTORING = "refactoring"  # 重构建议
    ARCHITECTURE = "architecture"  # 架构设计
    ALGORITHM = "algorithm"  # 算法创新
    PATTERN = "pattern"  # 设计模式
    INTEGRATION = "integration"  # 集成方案
    AUTOMATION = "automation"  # 自动化


@dataclass
class KnowledgeAssociation:
    """知识关联"""

    source: str
    target: str
    relation: str
    strength: float = 1.0
    context: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "source": self.source,
            "target": self.target,
            "relation": self.relation,
            "strength": self.strength,
            "context": self.context,
        }


@dataclass
class Idea:
    """创意"""

    id: str
    title: str
    description: str
    category: IdeaCategory
    confidence: float = 0.5
    source_knowledge: list[str] = field(default_factory=list)
    associations: list[KnowledgeAssociation] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "category": self.category.value,
            "confidence": self.confidence,
            "source_knowledge": self.source_knowledge,
            "associations": [a.to_dict() for a in self.associations],
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


class CreativityEngine(HybridEngine[Idea]):
    """创意生成引擎

    基于混合引擎实现创意生成，支持：
    - 快路径：基于领域关键词和模板的规则匹配
    - 慢路径：LLM 智能推理生成创意
    - 学习机制：从成功的创意中学习新规则
    """

    def __init__(
        self,
        mode: InferenceMode = InferenceMode.HYBRID,
        enable_learning: bool = True,
    ) -> None:
        """初始化创意引擎"""
        super().__init__(
            llm_client=None,
            mode=mode,
            enable_learning=enable_learning,
        )
        self.ideas: list[Idea] = []
        self.idea_counter = 0
        self._init_domain_keywords()
        self._init_predefined_rules()

    def _init_domain_keywords(self) -> None:
        """初始化领域关键词"""
        self.domain_keywords: dict[str, list[str]] = {
            "web": ["http", "api", "rest", "frontend", "backend", "html", "css"],
            "database": ["sql", "nosql", "query", "index", "transaction"],
            "ml": ["model", "training", "prediction", "neural", "learning"],
            "security": ["auth", "encrypt", "token", "permission", "secure"],
            "performance": ["cache", "optimize", "speed", "memory", "cpu"],
            "testing": ["test", "mock", "assert", "coverage", "unit"],
        }

    def _init_predefined_rules(self) -> None:
        """初始化预定义规则"""
        # API 相关创意
        self.add_predefined_rule(
            name="api_feature",
            keywords=["api", "接口", "rest"],
            output=Idea(
                id="template-api",
                title="添加API版本管理功能",
                description="实现API版本控制，支持多版本并行，确保向后兼容性",
                category=IdeaCategory.FEATURE,
                confidence=0.7,
                tags=["api", "feature"],
            ),
            confidence=0.7,
        )
        # 性能优化创意
        self.add_predefined_rule(
            name="performance_optimization",
            keywords=["性能", "performance", "slow", "慢"],
            output=Idea(
                id="template-perf",
                title="性能优化方案",
                description="通过缓存、异步处理、算法优化等手段提升系统性能",
                category=IdeaCategory.OPTIMIZATION,
                confidence=0.8,
                tags=["performance", "optimization"],
            ),
            confidence=0.8,
        )
        # 数据库优化创意
        self.add_predefined_rule(
            name="database_optimization",
            keywords=["sql", "database", "数据库", "query"],
            output=Idea(
                id="template-db",
                title="数据库查询优化",
                description="优化SQL查询、添加索引、使用连接池提升数据库性能",
                category=IdeaCategory.OPTIMIZATION,
                confidence=0.75,
                tags=["database", "optimization"],
            ),
            confidence=0.75,
        )

    def _generate_id(self) -> str:
        """生成唯一ID"""
        self.idea_counter += 1
        return f"idea-{self.idea_counter}"

    def generate_ideas(
        self,
        context: str,
        category: Optional[IdeaCategory] = None,
        max_ideas: int = 5,
    ) -> list[Idea]:
        """生成创意

        Args:
            context: 上下文描述
            category: 指定创意类别
            max_ideas: 最大创意数量

        Returns:
            生成的创意列表
        """
        ideas: list[Idea] = []

        # 使用混合引擎推理
        result = self.infer(
            context,
            category=category,
            max_ideas=max_ideas,
        )

        if result.success and result.output:
            idea = result.output
            # 更新 ID
            idea.id = self._generate_id()
            # 如果指定了类别，更新类别
            if category:
                idea.category = category
            ideas.append(idea)
            self.ideas.append(idea)

        # 如果需要更多创意，继续生成
        while len(ideas) < max_ideas:
            # 生成补充创意
            supplementary = self._generate_supplementary_idea(context, category, ideas)
            if supplementary:
                ideas.append(supplementary)
                self.ideas.append(supplementary)
            else:
                break

        return ideas[:max_ideas]

    def _generate_supplementary_idea(
        self,
        context: str,
        category: Optional[IdeaCategory],
        existing: list[Idea],
    ) -> Optional[Idea]:
        """生成补充创意"""
        # 识别相关领域
        domains = self._identify_domains(context.lower())

        # 选择未使用的类别
        used_categories = {idea.category for idea in existing}
        available_categories = [
            cat for cat in IdeaCategory if cat not in used_categories
        ]

        if category and category not in used_categories:
            target_category = category
        elif available_categories:
            target_category = available_categories[0]
        else:
            return None

        # 生成创意
        title, description = self._create_idea_content(
            context, target_category, domains
        )
        if not title:
            return None

        return Idea(
            id=self._generate_id(),
            title=title,
            description=description,
            category=target_category,
            confidence=self._calculate_confidence(context, target_category),
            source_knowledge=domains,
            tags=domains + [target_category.value],
        )

    def _identify_domains(self, context: str) -> list[str]:
        """识别上下文相关的领域"""
        domains = []
        for domain, keywords in self.domain_keywords.items():
            if any(kw in context for kw in keywords):
                domains.append(domain)
        return domains if domains else ["general"]

    def _create_idea_content(
        self,
        context: str,
        category: IdeaCategory,
        domains: list[str],
    ) -> tuple[str, str]:
        """创建创意内容"""
        content_map = {
            IdeaCategory.FEATURE: (
                "扩展核心功能",
                f"基于{', '.join(domains)}领域知识，扩展系统核心能力",
            ),
            IdeaCategory.OPTIMIZATION: (
                "系统优化建议",
                "分析系统瓶颈，提供针对性的优化方案",
            ),
            IdeaCategory.REFACTORING: (
                "代码重构建议",
                "识别代码异味，应用设计模式，提高代码可维护性",
            ),
            IdeaCategory.ARCHITECTURE: (
                "架构改进方案",
                "评估当前架构，提出分层、解耦、微服务化等改进建议",
            ),
            IdeaCategory.ALGORITHM: (
                "算法创新建议",
                "分析现有算法，提出更高效的实现方案",
            ),
            IdeaCategory.PATTERN: (
                "设计模式应用",
                "识别适用的设计模式，提升代码结构和可扩展性",
            ),
            IdeaCategory.INTEGRATION: (
                "系统集成方案",
                "设计与外部系统的集成接口和数据交换方案",
            ),
            IdeaCategory.AUTOMATION: (
                "自动化改进",
                "识别可自动化的流程，减少人工干预",
            ),
        }
        return content_map.get(category, ("", ""))

    def _calculate_confidence(self, context: str, category: IdeaCategory) -> float:
        """计算创意置信度"""
        base_confidence = 0.5
        if len(context) > 100:
            base_confidence += 0.1
        if len(context) > 200:
            base_confidence += 0.1
        if category in [IdeaCategory.OPTIMIZATION, IdeaCategory.REFACTORING]:
            base_confidence += 0.1
        return min(base_confidence, 1.0)

    def _apply_rule(
        self,
        rule: LearnedRule,
        input_data: str,
        **kwargs: Any,
    ) -> Optional[Idea]:
        """应用学习到的规则"""
        try:
            action_data = json.loads(rule.action) if rule.action.startswith("{") else {}
        except json.JSONDecodeError:
            action_data = {}

        category_str = action_data.get("category", "feature")
        try:
            category = IdeaCategory(category_str)
        except ValueError:
            category = IdeaCategory.FEATURE

        return Idea(
            id=self._generate_id(),
            title=action_data.get("title", rule.name),
            description=rule.description,
            category=category,
            confidence=rule.confidence,
            tags=rule.tags,
        )

    def _parse_llm_output(self, output: str) -> Optional[Idea]:
        """解析 LLM 输出"""
        try:
            data = json.loads(output)
            if not isinstance(data, dict):
                return None

            category_str = data.get("category", "feature")
            try:
                category = IdeaCategory(category_str)
            except ValueError:
                category = IdeaCategory.FEATURE

            return Idea(
                id=self._generate_id(),
                title=data.get("title", "创意建议"),
                description=data.get("description", ""),
                category=category,
                confidence=data.get("confidence", 0.6),
                source_knowledge=data.get("source_knowledge", []),
                tags=data.get("tags", []),
            )
        except json.JSONDecodeError:
            # 从文本中提取
            return Idea(
                id=self._generate_id(),
                title="创意建议",
                description=output[:500],
                category=IdeaCategory.FEATURE,
                confidence=0.5,
            )

    def _build_reasoning_context(
        self,
        input_data: str,
        **kwargs: Any,
    ) -> ReasoningContext:
        """构建推理上下文"""
        category = kwargs.get("category")
        category_hint = f"\n创意类别要求: {category.value}" if category else ""

        instruction = f"""基于以下上下文，生成一个创意或建议。{category_hint}

输出 JSON 格式：
{{
    "title": "创意标题",
    "description": "详细描述",
    "category": "feature|optimization|refactoring|architecture|algorithm|pattern|integration|automation",
    "confidence": 0.0-1.0,
    "source_knowledge": ["相关领域1", "相关领域2"],
    "tags": ["标签1", "标签2"]
}}"""

        return ReasoningContext(
            task_type=ReasoningType.GENERATION,
            input_data=input_data,
            instruction=instruction,
            output_format="json",
            constraints=[
                "创意必须具体可行",
                "描述要清晰明确",
                "置信度要合理",
            ],
        )

    def _get_reasoning_type(self) -> ReasoningType:
        """获取推理类型"""
        return ReasoningType.GENERATION

    def associate_knowledge(
        self,
        source: str,
        target: str,
        relation: str = "related_to",
        context: str = "",
    ) -> KnowledgeAssociation:
        """创建知识关联"""
        strength = self._calculate_association_strength(source, target, context)
        return KnowledgeAssociation(
            source=source,
            target=target,
            relation=relation,
            strength=strength,
            context=context,
        )

    def _calculate_association_strength(
        self,
        source: str,
        target: str,
        context: str,
    ) -> float:
        """计算关联强度"""
        strength = 0.5
        source_domains = self._identify_domains(source.lower())
        target_domains = self._identify_domains(target.lower())
        common_domains = set(source_domains) & set(target_domains)
        if common_domains:
            strength += 0.2 * len(common_domains)
        if context:
            if source.lower() in context.lower() or target.lower() in context.lower():
                strength += 0.1
        return min(strength, 1.0)

    def cross_domain_transfer(
        self,
        source_domain: str,
        target_domain: str,
        concept: str,
    ) -> list[Idea]:
        """跨领域知识迁移"""
        idea = Idea(
            id=self._generate_id(),
            title=f"将{source_domain}的{concept}应用到{target_domain}",
            description=f"借鉴{source_domain}领域中{concept}的实现思路，"
            f"在{target_domain}领域中创新应用",
            category=IdeaCategory.INTEGRATION,
            confidence=0.6,
            source_knowledge=[source_domain, target_domain],
            associations=[
                KnowledgeAssociation(
                    source=source_domain,
                    target=target_domain,
                    relation="transfer",
                    strength=0.7,
                    context=concept,
                )
            ],
            tags=[source_domain, target_domain, "cross-domain", concept],
        )
        self.ideas.append(idea)
        return [idea]

    def get_ideas_by_category(self, category: IdeaCategory) -> list[Idea]:
        """按类别获取创意"""
        return [idea for idea in self.ideas if idea.category == category]

    def get_ideas_by_tag(self, tag: str) -> list[Idea]:
        """按标签获取创意"""
        return [idea for idea in self.ideas if tag in idea.tags]

    def get_high_confidence_ideas(self, threshold: float = 0.7) -> list[Idea]:
        """获取高置信度创意"""
        return [idea for idea in self.ideas if idea.confidence >= threshold]

    def clear_ideas(self) -> None:
        """清空创意列表"""
        self.ideas.clear()
