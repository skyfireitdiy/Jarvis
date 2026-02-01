"""需求推理器模块

从显式需求推理隐式需求，支持规则引擎和知识图谱推理。
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol

from jarvis.jarvis_utils.output import PrettyOutput

from jarvis.jarvis_digital_twin.prediction import (
    InferenceResult,
    PredictionContext,
    PredictionType,
)


class InferenceStrategy(Enum):
    """推理策略枚举"""

    RULE_BASED = "rule_based"  # 纯规则推理
    PATTERN_BASED = "pattern_based"  # 模式匹配推理
    HYBRID = "hybrid"  # 混合策略（默认）


class KnowledgeGraphProvider(Protocol):
    """知识图谱提供者协议

    定义知识图谱查询的标准接口，支持依赖注入。
    """

    def query_related(self, concept: str, relation_type: str) -> List[Dict[str, Any]]:
        """查询相关概念"""
        ...

    def get_concept_hierarchy(self, concept: str) -> List[str]:
        """获取概念层级"""
        ...


@dataclass
class InferenceChainStep:
    """推理链步骤"""

    step_number: int
    description: str
    input_data: str
    output_data: str
    confidence: float = 1.0


@dataclass
class EvidenceItem:
    """证据项"""

    content: str
    source: str
    weight: float = 1.0
    is_supporting: bool = True


class RuleBasedInferrer:
    """规则推理引擎

    基于预定义规则进行需求推理。
    """

    # 隐式需求映射：显式需求 -> [(隐式需求, 置信度, 推理依据)]
    IMPLICIT_NEED_RULES: Dict[str, List[tuple[str, float, str]]] = {
        "implement_feature": [
            ("write_tests", 0.9, "功能实现通常需要配套测试"),
            ("update_documentation", 0.7, "新功能需要文档说明"),
            ("code_review", 0.6, "代码需要审查确保质量"),
        ],
        "fix_bug": [
            ("add_regression_test", 0.85, "修复bug应添加回归测试"),
            ("root_cause_analysis", 0.7, "需要分析根本原因防止复发"),
            ("update_changelog", 0.5, "重要修复应记录在变更日志"),
        ],
        "refactor_code": [
            ("run_existing_tests", 0.95, "重构后必须验证现有功能"),
            ("update_documentation", 0.6, "重构可能需要更新文档"),
            ("performance_check", 0.5, "重构后应检查性能影响"),
        ],
        "write_tests": [
            ("setup_test_environment", 0.8, "测试需要配置环境"),
            ("mock_dependencies", 0.7, "测试通常需要模拟依赖"),
            ("coverage_analysis", 0.6, "应分析测试覆盖率"),
        ],
        "debug_issue": [
            ("reproduce_issue", 0.9, "调试前需要复现问题"),
            ("add_logging", 0.7, "调试通常需要添加日志"),
            ("isolate_problem", 0.8, "需要隔离问题范围"),
        ],
        "deploy_application": [
            ("backup_data", 0.85, "部署前应备份数据"),
            ("rollback_plan", 0.9, "需要准备回滚方案"),
            ("health_check", 0.8, "部署后需要健康检查"),
        ],
        "optimize_performance": [
            ("benchmark_baseline", 0.9, "优化前需要基准测试"),
            ("profile_code", 0.85, "需要性能分析定位瓶颈"),
            ("monitor_metrics", 0.7, "优化后需要监控指标"),
        ],
    }

    # 后续任务映射
    FOLLOW_UP_TASK_RULES: Dict[str, List[tuple[str, float, str]]] = {
        "create_file": [
            ("implement_logic", 0.9, "创建文件后需要实现逻辑"),
            ("add_imports", 0.8, "需要添加必要的导入"),
            ("create_test_file", 0.7, "应创建对应的测试文件"),
        ],
        "implement_function": [
            ("write_unit_test", 0.85, "函数实现后应编写单元测试"),
            ("add_docstring", 0.7, "应添加文档字符串"),
            ("type_annotations", 0.6, "应添加类型注解"),
        ],
        "write_test": [
            ("run_test", 0.95, "编写测试后应运行验证"),
            ("check_coverage", 0.7, "应检查测试覆盖率"),
            ("add_edge_cases", 0.6, "应添加边界情况测试"),
        ],
        "fix_error": [
            ("verify_fix", 0.95, "修复后需要验证"),
            ("add_test_case", 0.8, "应添加测试用例防止回归"),
            ("check_related_code", 0.6, "应检查相关代码是否有类似问题"),
        ],
        "code_review": [
            ("address_comments", 0.9, "需要处理审查意见"),
            ("update_code", 0.8, "可能需要更新代码"),
            ("re_review", 0.6, "修改后可能需要再次审查"),
        ],
        "merge_branch": [
            ("delete_branch", 0.7, "合并后可清理分支"),
            ("deploy_staging", 0.6, "可部署到测试环境"),
            ("notify_team", 0.5, "可通知团队成员"),
        ],
    }

    # 根本原因映射
    ROOT_CAUSE_RULES: Dict[str, List[tuple[str, float, str]]] = {
        "import_error": [
            ("missing_dependency", 0.8, "可能缺少依赖包"),
            ("wrong_module_path", 0.7, "模块路径可能错误"),
            ("circular_import", 0.5, "可能存在循环导入"),
        ],
        "type_error": [
            ("wrong_argument_type", 0.8, "参数类型可能错误"),
            ("none_value", 0.7, "可能传入了None值"),
            ("incompatible_types", 0.6, "类型可能不兼容"),
        ],
        "attribute_error": [
            ("typo_in_attribute", 0.7, "属性名可能拼写错误"),
            ("object_not_initialized", 0.6, "对象可能未正确初始化"),
            ("wrong_object_type", 0.5, "对象类型可能错误"),
        ],
        "test_failure": [
            ("logic_error", 0.7, "代码逻辑可能有错误"),
            ("test_data_issue", 0.6, "测试数据可能有问题"),
            ("environment_difference", 0.5, "环境差异可能导致失败"),
        ],
        "performance_issue": [
            ("inefficient_algorithm", 0.7, "算法效率可能较低"),
            ("database_query", 0.6, "数据库查询可能需要优化"),
            ("memory_leak", 0.5, "可能存在内存泄漏"),
        ],
        "connection_error": [
            ("network_issue", 0.7, "网络可能有问题"),
            ("service_down", 0.6, "服务可能已停止"),
            ("wrong_endpoint", 0.5, "端点地址可能错误"),
        ],
    }

    # 关键词映射
    KEYWORD_MAPPINGS: Dict[str, Dict[str, str]] = {
        "need": {
            "implement": "implement_feature",
            "create": "implement_feature",
            "build": "implement_feature",
            "fix": "fix_bug",
            "bug": "fix_bug",
            "error": "fix_bug",
            "refactor": "refactor_code",
            "clean": "refactor_code",
            "test": "write_tests",
            "unittest": "write_tests",
            "debug": "debug_issue",
            "deploy": "deploy_application",
            "release": "deploy_application",
            "optimize": "optimize_performance",
            "performance": "optimize_performance",
        },
        "task": {
            "create": "create_file",
            "new": "create_file",
            "implement": "implement_function",
            "function": "implement_function",
            "method": "implement_function",
            "test": "write_test",
            "fix": "fix_error",
            "review": "code_review",
            "merge": "merge_branch",
        },
        "problem": {
            "import": "import_error",
            "module": "import_error",
            "type": "type_error",
            "typeerror": "type_error",
            "attribute": "attribute_error",
            "attributeerror": "attribute_error",
            "test": "test_failure",
            "fail": "test_failure",
            "slow": "performance_issue",
            "performance": "performance_issue",
            "connection": "connection_error",
            "timeout": "connection_error",
        },
    }

    def infer_implicit_needs(
        self, explicit_need: str
    ) -> List[tuple[str, float, str, List[str]]]:
        """推理隐式需求"""
        need_type = self._identify_type(explicit_need, self.KEYWORD_MAPPINGS["need"])
        if need_type not in self.IMPLICIT_NEED_RULES:
            return []
        results = []
        for implicit_need, confidence, reasoning in self.IMPLICIT_NEED_RULES[need_type]:
            chain = [
                f"识别显式需求类型: {need_type}",
                f"应用规则: {need_type} -> {implicit_need}",
                f"推理依据: {reasoning}",
            ]
            results.append((implicit_need, confidence, reasoning, chain))
        return results

    def infer_follow_up_tasks(
        self, current_task: str
    ) -> List[tuple[str, float, str, List[str]]]:
        """推理后续任务"""
        task_type = self._identify_type(current_task, self.KEYWORD_MAPPINGS["task"])
        if task_type not in self.FOLLOW_UP_TASK_RULES:
            return []
        results = []
        for follow_up, confidence, reasoning in self.FOLLOW_UP_TASK_RULES[task_type]:
            chain = [
                f"识别当前任务类型: {task_type}",
                f"应用规则: {task_type} -> {follow_up}",
                f"推理依据: {reasoning}",
            ]
            results.append((follow_up, confidence, reasoning, chain))
        return results

    def infer_root_cause(self, problem: str) -> List[tuple[str, float, str, List[str]]]:
        """推理根本原因"""
        problem_type = self._identify_type(problem, self.KEYWORD_MAPPINGS["problem"])
        if problem_type not in self.ROOT_CAUSE_RULES:
            return []
        results = []
        for cause, confidence, reasoning in self.ROOT_CAUSE_RULES[problem_type]:
            chain = [
                f"识别问题类型: {problem_type}",
                f"应用规则: {problem_type} -> {cause}",
                f"推理依据: {reasoning}",
            ]
            results.append((cause, confidence, reasoning, chain))
        return results

    def _identify_type(self, text: str, mapping: Dict[str, str]) -> str:
        """识别类型"""
        if not text:
            return "unknown"
        text_lower = text.lower()
        for keyword, type_name in mapping.items():
            if keyword in text_lower:
                return type_name
        return "unknown"


class PatternBasedInferrer:
    """模式推理引擎

    基于用户画像和历史模式进行推理。
    """

    def __init__(self) -> None:
        """初始化模式推理引擎"""
        self._pattern_cache: Dict[str, List[tuple[str, float]]] = {}

    def infer_from_profile(
        self,
        user_profile: Dict[str, Any],
        inference_type: str,
    ) -> List[tuple[str, float, str, List[str]]]:
        """基于用户画像推理"""
        if not user_profile:
            return []
        results: List[tuple[str, float, str, List[str]]] = []

        # 从交互模式中提取推理
        interaction_pattern = user_profile.get("interaction_pattern", {})
        if interaction_pattern:
            pattern_results = self._infer_from_interaction_pattern(
                interaction_pattern, inference_type
            )
            results.extend(pattern_results)

        # 从偏好中提取推理
        preferences = user_profile.get("preferences", {})
        if preferences:
            pref_results = self._infer_from_preferences(preferences, inference_type)
            results.extend(pref_results)

        # 从目标中提取推理
        goals = user_profile.get("goals", [])
        if goals:
            goal_results = self._infer_from_goals(goals, inference_type)
            results.extend(goal_results)

        return results

    def _infer_from_interaction_pattern(
        self,
        pattern: Dict[str, Any],
        inference_type: str,
    ) -> List[tuple[str, float, str, List[str]]]:
        """从交互模式推理"""
        results: List[tuple[str, float, str, List[str]]] = []

        question_pattern = pattern.get("question_pattern", {})
        question_types = question_pattern.get("question_types", {})

        if question_types and inference_type == "implicit_need":
            sorted_types = sorted(
                question_types.items(), key=lambda x: x[1], reverse=True
            )
            for qtype, count in sorted_types[:3]:
                confidence = min(0.8, count / 10)
                chain = [
                    "分析用户问题模式",
                    f"发现常见问题类型: {qtype} (出现{count}次)",
                    "推断可能的隐式需求",
                ]
                results.append(
                    (
                        f"help_with_{qtype}",
                        confidence,
                        f"用户经常询问{qtype}相关问题",
                        chain,
                    )
                )

        command_pattern = pattern.get("command_pattern", {})
        command_categories = command_pattern.get("command_categories", {})

        if command_categories and inference_type == "follow_up":
            sorted_cats = sorted(
                command_categories.items(), key=lambda x: x[1], reverse=True
            )
            for cat, count in sorted_cats[:3]:
                confidence = min(0.7, count / 10)
                chain = [
                    "分析用户命令模式",
                    f"发现常用命令类别: {cat} (使用{count}次)",
                    "推断可能的后续任务",
                ]
                results.append(
                    (f"use_{cat}_tools", confidence, f"用户经常使用{cat}类工具", chain)
                )

        return results

    def _infer_from_preferences(
        self,
        preferences: Dict[str, Any],
        inference_type: str,
    ) -> List[tuple[str, float, str, List[str]]]:
        """从偏好推理"""
        results: List[tuple[str, float, str, List[str]]] = []

        tech_stack = preferences.get("tech_stack", {})
        preferred_languages = tech_stack.get("preferred_languages", [])

        if preferred_languages and inference_type == "implicit_need":
            for lang in preferred_languages[:2]:
                chain = [
                    "分析用户技术栈偏好",
                    f"发现偏好语言: {lang}",
                    "推断相关隐式需求",
                ]
                results.append(
                    (f"{lang}_best_practices", 0.6, f"用户偏好使用{lang}", chain)
                )

        code_style = preferences.get("code_style", {})
        if code_style and inference_type == "implicit_need":
            style_prefs = []
            if code_style.get("prefers_type_hints"):
                style_prefs.append("type_annotations")
            if code_style.get("prefers_docstrings"):
                style_prefs.append("documentation")

            for pref in style_prefs:
                chain = [
                    "分析用户代码风格偏好",
                    f"发现偏好: {pref}",
                    "推断隐式需求",
                ]
                results.append((f"add_{pref}", 0.65, f"用户偏好{pref}", chain))

        return results

    def _infer_from_goals(
        self,
        goals: List[Dict[str, Any]],
        inference_type: str,
    ) -> List[tuple[str, float, str, List[str]]]:
        """从目标推理"""
        results: List[tuple[str, float, str, List[str]]] = []

        for goal in goals[:3]:
            goal_type = goal.get("type", "")
            goal_desc = goal.get("description", "")
            progress = goal.get("progress", 0)

            if inference_type == "follow_up" and progress < 100:
                confidence = 0.5 + (progress / 200)
                chain = [
                    "分析用户目标",
                    f"发现未完成目标: {goal_desc}",
                    f"当前进度: {progress}%",
                    "推断后续任务",
                ]
                results.append(
                    (
                        f"continue_{goal_type}",
                        confidence,
                        f"用户有未完成的{goal_type}目标",
                        chain,
                    )
                )

        return results


class NeedInferrer:
    """需求推理器

    从显式需求推理隐式需求，支持规则引擎和模式匹配混合策略。
    """

    def __init__(
        self,
        strategy: InferenceStrategy = InferenceStrategy.HYBRID,
        knowledge_graph: Optional[KnowledgeGraphProvider] = None,
        llm_client: Optional[Any] = None,
    ) -> None:
        """初始化需求推理器"""
        self._strategy = strategy
        self._rule_inferrer = RuleBasedInferrer()
        self._pattern_inferrer = PatternBasedInferrer()
        self._knowledge_graph = knowledge_graph
        self._llm_client = llm_client

    @property
    def strategy(self) -> InferenceStrategy:
        """获取当前推理策略"""
        return self._strategy

    @strategy.setter
    def strategy(self, value: InferenceStrategy) -> None:
        """设置推理策略"""
        self._strategy = value

    def _llm_infer_implicit_needs(
        self, explicit_need: str
    ) -> List[tuple[str, float, str, List[str]]]:
        """使用LLM推理隐式需求"""
        if not self._llm_client:
            return []

        try:
            prompt = f"""你是一个需求分析专家。请分析用户的显式需求，推理出可能的隐式需求。

显式需求：{explicit_need}

请返回JSON格式的推理结果，每个结果包含：
- implicit_need: 隐式需求描述
- confidence: 置信度（0-1之间的浮点数）
- reasoning: 推理依据
- inference_chain: 推理步骤列表

返回格式示例：
[
  {{
    "implicit_need": "编写单元测试",
    "confidence": 0.9,
    "reasoning": "功能实现通常需要配套测试",
    "inference_chain": ["识别到功能开发需求", "根据最佳实践推断需要测试", "得出结论"]
  }}
]

请仅返回JSON数组，不要包含其他解释文字。"""

            response = self._llm_client.complete(prompt)

            # 解析JSON响应
            import json
            import re

            # 提取JSON数组部分
            json_match = re.search(r"\[.*\]", response, re.DOTALL)
            if not json_match:
                return []

            json_str = json_match.group(0)
            data = json.loads(json_str)

            results = []
            for item in data:
                implicit_need = item.get("implicit_need", "")
                confidence = float(item.get("confidence", 0.5))
                reasoning = item.get("reasoning", "LLM推理")
                inference_chain = item.get("inference_chain", ["LLM智能推理"])

                if implicit_need:
                    results.append(
                        (implicit_need, confidence, reasoning, inference_chain)
                    )

            return results

        except Exception:
            # LLM推理失败时返回空列表，将降级到规则推理
            return []

    def set_knowledge_graph(self, provider: KnowledgeGraphProvider) -> None:
        """设置知识图谱提供者"""
        self._knowledge_graph = provider

    def infer_implicit_needs(
        self,
        context: PredictionContext,
        explicit_need: str,
    ) -> List[InferenceResult]:
        """从显式需求推理隐式需求"""
        if not explicit_need:
            return []

        all_inferences: List[tuple[str, float, str, List[str]]] = []
        inference_mode = "规则"

        # LLM推理（优先）
        if self._llm_client is not None:
            llm_results = self._llm_infer_implicit_needs(explicit_need)
            if llm_results:
                all_inferences.extend(llm_results)
                inference_mode = "LLM"
            else:
                # LLM推理失败，降级到规则推理
                inference_mode = "规则(降级)"

        # 规则推理（LLM失败时或作为补充）
        if self._strategy in (InferenceStrategy.RULE_BASED, InferenceStrategy.HYBRID):
            if not all_inferences or self._strategy == InferenceStrategy.HYBRID:
                rule_results = self._rule_inferrer.infer_implicit_needs(explicit_need)
                all_inferences.extend(rule_results)

        # 模式推理
        if self._strategy in (
            InferenceStrategy.PATTERN_BASED,
            InferenceStrategy.HYBRID,
        ):
            pattern_results = self._pattern_inferrer.infer_from_profile(
                context.user_profile, "implicit_need"
            )
            adjusted_results = [
                (content, confidence * 0.9, reasoning, chain)
                for content, confidence, reasoning, chain in pattern_results
            ]
            all_inferences.extend(adjusted_results)

        # 应用用户画像调整
        all_inferences = self._apply_profile_adjustment(
            all_inferences, context.user_profile
        )

        # 收集证据
        supporting_evidence = self._collect_supporting_evidence(
            context, explicit_need, "implicit_need"
        )
        opposing_evidence = self._collect_opposing_evidence(
            context, explicit_need, "implicit_need"
        )

        # 构建结果
        results = self._build_inference_results(
            all_inferences,
            PredictionType.IMPLICIT_NEED,
            supporting_evidence,
            opposing_evidence,
        )

        results.sort(key=lambda x: x.confidence_score, reverse=True)

        # 过程打印
        PrettyOutput.auto_print(
            f"📚 需求推理: {len(results)}个结果 (模式: {inference_mode})"
        )

        return results

    def infer_follow_up_tasks(
        self,
        context: PredictionContext,
        current_task: str,
    ) -> List[InferenceResult]:
        """从当前任务推理后续任务"""
        if not current_task:
            return []

        all_inferences: List[tuple[str, float, str, List[str]]] = []

        # 规则推理
        if self._strategy in (InferenceStrategy.RULE_BASED, InferenceStrategy.HYBRID):
            rule_results = self._rule_inferrer.infer_follow_up_tasks(current_task)
            all_inferences.extend(rule_results)

        # 模式推理
        if self._strategy in (
            InferenceStrategy.PATTERN_BASED,
            InferenceStrategy.HYBRID,
        ):
            pattern_results = self._pattern_inferrer.infer_from_profile(
                context.user_profile, "follow_up"
            )
            adjusted_results = [
                (content, confidence * 0.85, reasoning, chain)
                for content, confidence, reasoning, chain in pattern_results
            ]
            all_inferences.extend(adjusted_results)

        all_inferences = self._apply_profile_adjustment(
            all_inferences, context.user_profile
        )

        supporting_evidence = self._collect_supporting_evidence(
            context, current_task, "follow_up"
        )
        opposing_evidence = self._collect_opposing_evidence(
            context, current_task, "follow_up"
        )

        results = self._build_inference_results(
            all_inferences,
            PredictionType.FOLLOW_UP_TASK,
            supporting_evidence,
            opposing_evidence,
        )

        results.sort(key=lambda x: x.confidence_score, reverse=True)
        return results

    def infer_root_cause(
        self,
        context: PredictionContext,
        problem: str,
    ) -> InferenceResult:
        """从问题描述推理根本原因"""
        if not problem:
            return InferenceResult(
                inference_type=PredictionType.ROOT_CAUSE,
                content="无法推理根本原因",
                confidence_score=0.0,
                reasoning_chain=["问题描述为空"],
            )

        all_inferences: List[tuple[str, float, str, List[str]]] = []

        # 规则推理
        if self._strategy in (InferenceStrategy.RULE_BASED, InferenceStrategy.HYBRID):
            rule_results = self._rule_inferrer.infer_root_cause(problem)
            all_inferences.extend(rule_results)

        # 模式推理（从历史问题中学习）
        if self._strategy in (
            InferenceStrategy.PATTERN_BASED,
            InferenceStrategy.HYBRID,
        ):
            pattern_results = self._infer_root_cause_from_history(context, problem)
            all_inferences.extend(pattern_results)

        if not all_inferences:
            return InferenceResult(
                inference_type=PredictionType.ROOT_CAUSE,
                content="无法确定根本原因",
                confidence_score=0.1,
                reasoning_chain=[
                    f"分析问题: {problem[:100]}",
                    "未找到匹配的问题模式",
                    "建议进一步调查",
                ],
            )

        all_inferences = self._apply_profile_adjustment(
            all_inferences, context.user_profile
        )

        supporting_evidence = self._collect_supporting_evidence(
            context, problem, "root_cause"
        )
        opposing_evidence = self._collect_opposing_evidence(
            context, problem, "root_cause"
        )

        best = max(all_inferences, key=lambda x: x[1])
        content, confidence, reasoning, chain = best

        related = self._build_inference_results(
            all_inferences[1:4],
            PredictionType.ROOT_CAUSE,
            supporting_evidence,
            opposing_evidence,
        )

        return InferenceResult(
            inference_type=PredictionType.ROOT_CAUSE,
            content=content,
            confidence_score=confidence,
            reasoning_chain=chain,
            supporting_evidence=supporting_evidence,
            opposing_evidence=opposing_evidence,
            related_inferences=related,
        )

    def _infer_root_cause_from_history(
        self,
        context: PredictionContext,
        problem: str,
    ) -> List[tuple[str, float, str, List[str]]]:
        """从历史记录推理根本原因"""
        results: List[tuple[str, float, str, List[str]]] = []
        project_state = context.project_state
        if project_state:
            error_history = project_state.get("error_history", [])
            for error in error_history[-5:]:
                error_type = error.get("type", "")
                error_solution = error.get("solution", "")
                if error_type and self._is_similar_problem(problem, error_type):
                    chain = [
                        "分析历史错误记录",
                        f"发现类似问题: {error_type}",
                        f"历史解决方案: {error_solution}",
                    ]
                    results.append(
                        (error_solution, 0.75, "历史上类似问题的解决方案", chain)
                    )
        return results

    def _is_similar_problem(self, problem1: str, problem2: str) -> bool:
        """检查两个问题是否相似"""
        p1 = problem1.lower()
        p2 = problem2.lower()
        keywords1 = set(p1.split())
        keywords2 = set(p2.split())
        common = keywords1 & keywords2
        if len(common) >= 2:
            return True
        return p1 in p2 or p2 in p1

    def _apply_profile_adjustment(
        self,
        inferences: List[tuple[str, float, str, List[str]]],
        user_profile: Dict[str, Any],
    ) -> List[tuple[str, float, str, List[str]]]:
        """应用用户画像调整置信度"""
        if not user_profile or not inferences:
            return inferences

        adjusted: List[tuple[str, float, str, List[str]]] = []
        preferences = user_profile.get("preferences", {})
        tech_stack = preferences.get("tech_stack", {})
        preferred_langs = tech_stack.get("preferred_languages", [])

        for content, confidence, reasoning, chain in inferences:
            boost = 0.0
            content_lower = content.lower()
            for lang in preferred_langs:
                if lang.lower() in content_lower:
                    boost = max(boost, 0.05)
            new_confidence = min(1.0, confidence + boost)
            adjusted.append((content, new_confidence, reasoning, chain))

        return adjusted

    def _collect_supporting_evidence(
        self,
        context: PredictionContext,
        input_text: str,
        inference_type: str,
    ) -> List[str]:
        """收集支持证据"""
        evidence: List[str] = []

        if input_text:
            evidence.append(f"输入: {input_text[:100]}")

        if context.conversation_history:
            evidence.append(f"对话历史长度: {len(context.conversation_history)}")

        if inference_type == "implicit_need" and context.code_context:
            modified = context.code_context.get("modified_files", [])
            if modified:
                evidence.append(f"修改的文件: {', '.join(modified[:3])}")

        if inference_type == "root_cause" and context.project_state:
            if context.project_state.get("has_errors"):
                evidence.append("检测到错误状态")

        return evidence

    def _collect_opposing_evidence(
        self,
        context: PredictionContext,
        input_text: str,
        inference_type: str,
    ) -> List[str]:
        """收集反对证据"""
        evidence: List[str] = []

        if not context.user_profile:
            evidence.append("缺少用户画像数据")

        if not context.conversation_history:
            evidence.append("缺少对话历史")

        if inference_type == "follow_up" and not context.code_context:
            evidence.append("缺少代码上下文")

        return evidence

    def _build_inference_results(
        self,
        inferences: List[tuple[str, float, str, List[str]]],
        inference_type: PredictionType,
        supporting_evidence: List[str],
        opposing_evidence: List[str],
    ) -> List[InferenceResult]:
        """构建推理结果列表"""
        results: List[InferenceResult] = []
        for content, confidence, reasoning, chain in inferences:
            results.append(
                InferenceResult(
                    inference_type=inference_type,
                    content=content,
                    confidence_score=confidence,
                    reasoning_chain=chain,
                    supporting_evidence=supporting_evidence.copy(),
                    opposing_evidence=opposing_evidence.copy(),
                )
            )
        return results
