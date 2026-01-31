"""最佳实践推荐模块

该模块提供基于项目上下文的最佳实践推荐功能。
包含以下核心功能：
- 分析代码上下文，识别适用的最佳实践
- 基于规则和方法论系统推荐最佳实践
- 评估实践的相关性和优先级
- 生成可执行的实践建议
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class PracticeCategory(Enum):
    """最佳实践类别"""

    CODE_QUALITY = "code_quality"  # 代码质量
    ARCHITECTURE = "architecture"  # 架构设计
    SECURITY = "security"  # 安全实践
    PERFORMANCE = "performance"  # 性能优化
    TESTING = "testing"  # 测试实践
    DOCUMENTATION = "documentation"  # 文档规范
    DEVOPS = "devops"  # DevOps实践
    COLLABORATION = "collaboration"  # 协作规范


class PracticePriority(Enum):
    """实践优先级"""

    CRITICAL = "critical"  # 关键（必须立即执行）
    HIGH = "high"  # 高（应尽快执行）
    MEDIUM = "medium"  # 中（建议执行）
    LOW = "low"  # 低（可选执行）


@dataclass
class BestPractice:
    """最佳实践数据类"""

    name: str  # 实践名称
    category: PracticeCategory  # 实践类别
    description: str  # 实践描述
    rationale: str  # 推荐理由
    priority: PracticePriority  # 优先级
    actions: List[str] = field(default_factory=list)  # 具体行动
    examples: List[str] = field(default_factory=list)  # 示例
    references: List[str] = field(default_factory=list)  # 参考资料
    relevance_score: float = 0.0  # 相关性得分（0-100）


@dataclass
class PracticeContext:
    """实践推荐上下文"""

    code_snippet: str = ""  # 代码片段
    file_path: str = ""  # 文件路径
    language: str = ""  # 编程语言
    project_type: str = ""  # 项目类型
    current_issues: List[str] = field(default_factory=list)  # 当前问题
    goals: List[str] = field(default_factory=list)  # 目标


@dataclass
class PracticeRecommendation:
    """实践推荐结果"""

    context: PracticeContext  # 上下文
    practices: List[BestPractice] = field(default_factory=list)  # 推荐的实践
    summary: str = ""  # 推荐摘要
    total_practices: int = 0  # 总推荐数


class PracticeAdvisor:
    """最佳实践推荐顾问

    基于项目上下文和知识库推荐最佳实践。
    """

    # 内置最佳实践库
    BUILTIN_PRACTICES: Dict[str, Dict[str, Any]] = {
        # 代码质量实践
        "single_responsibility": {
            "name": "单一职责原则",
            "category": PracticeCategory.CODE_QUALITY,
            "description": "每个类/函数应该只有一个改变的理由",
            "rationale": "提高代码可维护性和可测试性",
            "actions": [
                "检查类/函数是否只做一件事",
                "将多职责的类拆分为多个单职责类",
                "确保函数名准确描述其功能",
            ],
            "keywords": ["类", "函数", "职责", "拆分", "重构"],
        },
        "dry_principle": {
            "name": "DRY原则（不要重复自己）",
            "category": PracticeCategory.CODE_QUALITY,
            "description": "避免代码重复，提取公共逻辑",
            "rationale": "减少维护成本，避免不一致性",
            "actions": [
                "识别重复的代码块",
                "提取公共函数或类",
                "使用继承或组合复用代码",
            ],
            "keywords": ["重复", "复制", "相似", "提取", "复用"],
        },
        "meaningful_names": {
            "name": "有意义的命名",
            "category": PracticeCategory.CODE_QUALITY,
            "description": "使用清晰、有意义的变量和函数名",
            "rationale": "提高代码可读性，减少注释需求",
            "actions": [
                "使用描述性的变量名",
                "避免使用单字母变量（循环变量除外）",
                "函数名应该描述其行为",
            ],
            "keywords": ["命名", "变量名", "函数名", "可读性"],
        },
        "error_handling": {
            "name": "完善的错误处理",
            "category": PracticeCategory.CODE_QUALITY,
            "description": "正确处理异常和错误情况",
            "rationale": "提高系统稳定性和用户体验",
            "actions": [
                "捕获并处理可能的异常",
                "提供有意义的错误信息",
                "避免空的catch块",
                "使用自定义异常类",
            ],
            "keywords": ["异常", "错误", "try", "catch", "exception"],
        },
        # 架构实践
        "dependency_injection": {
            "name": "依赖注入",
            "category": PracticeCategory.ARCHITECTURE,
            "description": "通过依赖注入解耦组件",
            "rationale": "提高可测试性和灵活性",
            "actions": [
                "将依赖通过构造函数或方法参数传入",
                "使用接口而非具体实现",
                "考虑使用依赖注入框架",
            ],
            "keywords": ["依赖", "注入", "解耦", "接口", "测试"],
        },
        "layered_architecture": {
            "name": "分层架构",
            "category": PracticeCategory.ARCHITECTURE,
            "description": "将应用分为表示层、业务层、数据层",
            "rationale": "关注点分离，便于维护和扩展",
            "actions": [
                "定义清晰的层次边界",
                "确保层间单向依赖",
                "使用接口定义层间契约",
            ],
            "keywords": ["分层", "架构", "表示层", "业务层", "数据层"],
        },
        # 安全实践
        "input_validation": {
            "name": "输入验证",
            "category": PracticeCategory.SECURITY,
            "description": "验证所有外部输入",
            "rationale": "防止注入攻击和数据损坏",
            "actions": [
                "验证输入的类型和格式",
                "设置输入长度限制",
                "使用白名单验证",
                "对特殊字符进行转义",
            ],
            "keywords": ["输入", "验证", "校验", "安全", "注入"],
        },
        "secure_authentication": {
            "name": "安全认证",
            "category": PracticeCategory.SECURITY,
            "description": "实现安全的用户认证机制",
            "rationale": "保护用户账户和敏感数据",
            "actions": [
                "使用强密码策略",
                "实现多因素认证",
                "安全存储密码（使用哈希+盐）",
                "实现账户锁定机制",
            ],
            "keywords": ["认证", "登录", "密码", "身份", "授权"],
        },
        # 性能实践
        "caching_strategy": {
            "name": "缓存策略",
            "category": PracticeCategory.PERFORMANCE,
            "description": "合理使用缓存提升性能",
            "rationale": "减少重复计算和数据库访问",
            "actions": [
                "识别可缓存的数据",
                "选择合适的缓存策略（LRU、TTL等）",
                "实现缓存失效机制",
                "监控缓存命中率",
            ],
            "keywords": ["缓存", "性能", "优化", "cache", "redis"],
        },
        "database_optimization": {
            "name": "数据库优化",
            "category": PracticeCategory.PERFORMANCE,
            "description": "优化数据库查询和设计",
            "rationale": "提高数据访问效率",
            "actions": [
                "添加适当的索引",
                "避免N+1查询问题",
                "使用查询分析工具",
                "考虑读写分离",
            ],
            "keywords": ["数据库", "查询", "索引", "SQL", "优化"],
        },
        # 测试实践
        "unit_testing": {
            "name": "单元测试",
            "category": PracticeCategory.TESTING,
            "description": "为核心逻辑编写单元测试",
            "rationale": "确保代码正确性，支持重构",
            "actions": [
                "为每个公共方法编写测试",
                "使用AAA模式（Arrange-Act-Assert）",
                "保持测试独立性",
                "追求高测试覆盖率",
            ],
            "keywords": ["测试", "单元测试", "pytest", "unittest", "覆盖率"],
        },
        "test_driven_development": {
            "name": "测试驱动开发（TDD）",
            "category": PracticeCategory.TESTING,
            "description": "先写测试，再写实现",
            "rationale": "确保代码可测试，提高设计质量",
            "actions": [
                "先编写失败的测试",
                "编写最小代码使测试通过",
                "重构代码保持测试通过",
            ],
            "keywords": ["TDD", "测试驱动", "红绿重构"],
        },
        # 文档实践
        "code_documentation": {
            "name": "代码文档",
            "category": PracticeCategory.DOCUMENTATION,
            "description": "为代码编写清晰的文档",
            "rationale": "提高代码可理解性和可维护性",
            "actions": [
                "为公共API编写文档字符串",
                "解释复杂的算法和业务逻辑",
                "保持文档与代码同步",
            ],
            "keywords": ["文档", "注释", "docstring", "README"],
        },
        "api_documentation": {
            "name": "API文档",
            "category": PracticeCategory.DOCUMENTATION,
            "description": "为API编写完整的文档",
            "rationale": "便于API使用者理解和集成",
            "actions": [
                "使用OpenAPI/Swagger规范",
                "提供请求和响应示例",
                "说明错误码和处理方式",
            ],
            "keywords": ["API", "接口", "文档", "swagger", "openapi"],
        },
        # DevOps实践
        "continuous_integration": {
            "name": "持续集成（CI）",
            "category": PracticeCategory.DEVOPS,
            "description": "自动化构建和测试流程",
            "rationale": "快速发现问题，提高交付效率",
            "actions": [
                "配置自动化构建流程",
                "在每次提交时运行测试",
                "实现代码质量检查",
            ],
            "keywords": ["CI", "持续集成", "自动化", "构建", "流水线"],
        },
        "infrastructure_as_code": {
            "name": "基础设施即代码（IaC）",
            "category": PracticeCategory.DEVOPS,
            "description": "使用代码管理基础设施",
            "rationale": "提高可重复性和可追溯性",
            "actions": [
                "使用Terraform/Ansible等工具",
                "版本控制基础设施配置",
                "实现环境一致性",
            ],
            "keywords": ["IaC", "基础设施", "terraform", "ansible", "docker"],
        },
    }

    def __init__(
        self,
        knowledge_graph: Optional[Any] = None,
        rule_generator: Optional[Any] = None,
        methodology_generator: Optional[Any] = None,
    ):
        """初始化最佳实践推荐顾问

        Args:
            knowledge_graph: 知识图谱实例
            rule_generator: 规则生成器实例
            methodology_generator: 方法论生成器实例
        """
        self.knowledge_graph = knowledge_graph
        self.rule_generator = rule_generator
        self.methodology_generator = methodology_generator

    def recommend_practices(
        self,
        context: PracticeContext,
        categories: Optional[List[PracticeCategory]] = None,
        max_recommendations: int = 10,
    ) -> PracticeRecommendation:
        """推荐最佳实践

        Args:
            context: 实践推荐上下文
            categories: 限定的实践类别（可选）
            max_recommendations: 最大推荐数量

        Returns:
            实践推荐结果
        """
        practices = []

        # 从内置实践库中匹配
        for practice_id, practice_info in self.BUILTIN_PRACTICES.items():
            # 类别过滤
            if categories and practice_info["category"] not in categories:
                continue

            # 计算相关性得分
            relevance = self._calculate_relevance(context, practice_info)

            if relevance > 0:
                practice = BestPractice(
                    name=practice_info["name"],
                    category=practice_info["category"],
                    description=practice_info["description"],
                    rationale=practice_info["rationale"],
                    priority=self._determine_priority(relevance, context),
                    actions=practice_info["actions"],
                    relevance_score=relevance,
                )
                practices.append(practice)

        # 从知识图谱中获取额外实践
        if self.knowledge_graph:
            kg_practices = self._get_practices_from_knowledge_graph(context)
            practices.extend(kg_practices)

        # 按相关性排序并限制数量
        practices.sort(key=lambda x: x.relevance_score, reverse=True)
        practices = practices[:max_recommendations]

        # 生成摘要
        summary = self._generate_summary(practices, context)

        return PracticeRecommendation(
            context=context,
            practices=practices,
            summary=summary,
            total_practices=len(practices),
        )

    def _calculate_relevance(
        self, context: PracticeContext, practice_info: Dict[str, Any]
    ) -> float:
        """计算实践与上下文的相关性

        Args:
            context: 上下文
            practice_info: 实践信息

        Returns:
            相关性得分（0-100）
        """
        score = 0.0
        keywords = practice_info.get("keywords", [])

        # 检查代码片段中的关键词
        code_lower = context.code_snippet.lower()
        for keyword in keywords:
            if keyword.lower() in code_lower:
                score += 15

        # 检查当前问题中的关键词
        issues_text = " ".join(context.current_issues).lower()
        for keyword in keywords:
            if keyword.lower() in issues_text:
                score += 20

        # 检查目标中的关键词
        goals_text = " ".join(context.goals).lower()
        for keyword in keywords:
            if keyword.lower() in goals_text:
                score += 15

        # 根据项目类型调整
        if context.project_type:
            score += self._adjust_by_project_type(
                context.project_type, practice_info["category"]
            )

        # 根据编程语言调整
        if context.language:
            score += self._adjust_by_language(context.language, practice_info)

        return min(score, 100.0)

    def _adjust_by_project_type(
        self, project_type: str, category: PracticeCategory
    ) -> float:
        """根据项目类型调整得分"""
        adjustments = {
            "web": {
                PracticeCategory.SECURITY: 10,
                PracticeCategory.PERFORMANCE: 10,
            },
            "api": {
                PracticeCategory.DOCUMENTATION: 15,
                PracticeCategory.SECURITY: 10,
            },
            "library": {
                PracticeCategory.TESTING: 15,
                PracticeCategory.DOCUMENTATION: 10,
            },
            "microservice": {
                PracticeCategory.DEVOPS: 15,
                PracticeCategory.ARCHITECTURE: 10,
            },
        }

        project_adjustments = adjustments.get(project_type.lower(), {})
        return project_adjustments.get(category, 0)

    def _adjust_by_language(
        self, language: str, practice_info: Dict[str, Any]
    ) -> float:
        """根据编程语言调整得分"""
        # 某些实践对特定语言更相关
        language_relevance = {
            "python": ["unit_testing", "code_documentation", "error_handling"],
            "java": ["dependency_injection", "layered_architecture"],
            "javascript": ["error_handling", "unit_testing"],
            "typescript": ["error_handling", "unit_testing", "api_documentation"],
        }

        relevant_practices = language_relevance.get(language.lower(), [])
        practice_name = practice_info.get("name", "")

        for practice_id in relevant_practices:
            if practice_id in practice_name.lower():
                return 10

        return 0

    def _determine_priority(
        self, relevance: float, context: PracticeContext
    ) -> PracticePriority:
        """确定实践优先级"""
        # 根据相关性和上下文确定优先级
        if relevance >= 80:
            return PracticePriority.CRITICAL
        elif relevance >= 60:
            return PracticePriority.HIGH
        elif relevance >= 40:
            return PracticePriority.MEDIUM
        else:
            return PracticePriority.LOW

    def _get_practices_from_knowledge_graph(
        self, context: PracticeContext
    ) -> List[BestPractice]:
        """从知识图谱获取相关实践"""
        practices: List[BestPractice] = []

        if not self.knowledge_graph:
            return practices

        try:
            # 查询规则类型的节点
            rule_nodes = self.knowledge_graph.query_nodes(node_type="RULE")

            for node in rule_nodes:
                # 检查是否与上下文相关
                if self._is_node_relevant(node, context):
                    practice = self._convert_node_to_practice(node)
                    if practice:
                        practices.append(practice)
        except Exception:
            pass

        return practices

    def _is_node_relevant(self, node: Any, context: PracticeContext) -> bool:
        """检查知识节点是否与上下文相关"""
        if not hasattr(node, "tags") or not hasattr(node, "content"):
            return False

        # 检查标签匹配
        context_keywords = (
            context.code_snippet.lower()
            + " ".join(context.current_issues).lower()
            + " ".join(context.goals).lower()
        )

        for tag in node.tags:
            if tag.lower() in context_keywords:
                return True

        return False

    def _convert_node_to_practice(self, node: Any) -> Optional[BestPractice]:
        """将知识节点转换为最佳实践"""
        try:
            return BestPractice(
                name=getattr(node, "name", "未命名实践"),
                category=PracticeCategory.CODE_QUALITY,
                description=getattr(node, "content", "")[:200],
                rationale="来自知识图谱的推荐",
                priority=PracticePriority.MEDIUM,
                relevance_score=50.0,
            )
        except Exception:
            return None

    def _generate_summary(
        self, practices: List[BestPractice], context: PracticeContext
    ) -> str:
        """生成推荐摘要"""
        if not practices:
            return "未找到与当前上下文相关的最佳实践推荐。"

        # 统计各类别的实践数量
        category_counts: Dict[PracticeCategory, int] = {}
        for practice in practices:
            category_counts[practice.category] = (
                category_counts.get(practice.category, 0) + 1
            )

        # 生成摘要
        summary_parts = [f"共推荐 {len(practices)} 项最佳实践："]

        for category, count in sorted(
            category_counts.items(), key=lambda x: x[1], reverse=True
        ):
            summary_parts.append(f"- {category.value}: {count} 项")

        # 添加高优先级实践提示
        critical_practices = [
            p for p in practices if p.priority == PracticePriority.CRITICAL
        ]
        if critical_practices:
            summary_parts.append(
                f"\n其中 {len(critical_practices)} 项为关键优先级，建议立即执行。"
            )

        return "\n".join(summary_parts)

    def get_practice_by_category(
        self, category: PracticeCategory
    ) -> List[BestPractice]:
        """获取指定类别的所有实践

        Args:
            category: 实践类别

        Returns:
            该类别的所有实践列表
        """
        practices = []

        for practice_id, practice_info in self.BUILTIN_PRACTICES.items():
            if practice_info["category"] == category:
                practice = BestPractice(
                    name=practice_info["name"],
                    category=practice_info["category"],
                    description=practice_info["description"],
                    rationale=practice_info["rationale"],
                    priority=PracticePriority.MEDIUM,
                    actions=practice_info["actions"],
                    relevance_score=50.0,
                )
                practices.append(practice)

        return practices

    def search_practices(self, query: str) -> List[BestPractice]:
        """搜索最佳实践

        Args:
            query: 搜索关键词

        Returns:
            匹配的实践列表
        """
        practices = []
        query_lower = query.lower()

        for practice_id, practice_info in self.BUILTIN_PRACTICES.items():
            # 检查名称、描述和关键词
            if (
                query_lower in practice_info["name"].lower()
                or query_lower in practice_info["description"].lower()
                or any(
                    query_lower in kw.lower()
                    for kw in practice_info.get("keywords", [])
                )
            ):
                practice = BestPractice(
                    name=practice_info["name"],
                    category=practice_info["category"],
                    description=practice_info["description"],
                    rationale=practice_info["rationale"],
                    priority=PracticePriority.MEDIUM,
                    actions=practice_info["actions"],
                    relevance_score=70.0,
                )
                practices.append(practice)

        return practices

    def get_all_categories(self) -> List[PracticeCategory]:
        """获取所有实践类别"""
        return list(PracticeCategory)

    def get_practice_count(self) -> int:
        """获取内置实践总数"""
        return len(self.BUILTIN_PRACTICES)
