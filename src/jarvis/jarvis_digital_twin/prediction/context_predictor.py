"""上下文预测器模块

基于当前对话和代码修改预测下一步操作。
支持规则引擎和LLM混合预测策略。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, Tuple

from jarvis.jarvis_digital_twin.prediction import (
    PredictionContext,
    PredictionResult,
    PredictionType,
)


class PredictionStrategy(Enum):
    """预测策略枚举"""

    RULE_BASED = "rule_based"  # 纯规则引擎
    LLM_BASED = "llm_based"  # 纯LLM推理
    HYBRID = "hybrid"  # 混合策略（默认）


class LLMProvider(Protocol):
    """LLM提供者协议

    定义LLM调用的标准接口，支持依赖注入。
    """

    def complete(self, prompt: str, **kwargs: Any) -> str:
        """调用LLM生成回复"""
        ...


@dataclass
class PatternMatch:
    """模式匹配结果"""

    pattern_name: str
    confidence: float
    evidence: List[str] = field(default_factory=list)


class BasePredictionEngine(ABC):
    """预测引擎基类"""

    @abstractmethod
    def predict(
        self,
        context: PredictionContext,
        prediction_type: PredictionType,
    ) -> List[Tuple[str, float, str]]:
        """执行预测

        Args:
            context: 预测上下文
            prediction_type: 预测类型

        Returns:
            预测结果列表，每项为 (预测内容, 置信度, 推理依据)
        """
        pass


class RuleBasedEngine(BasePredictionEngine):
    """规则引擎

    基于预定义模式进行快速预测。
    """

    # 问题模式映射
    QUESTION_PATTERNS: Dict[str, List[Tuple[str, float]]] = {
        "how_to_implement": [
            ("how_to_test", 0.7),
            ("how_to_optimize", 0.5),
            ("debug_error", 0.4),
        ],
        "debug_error": [
            ("how_to_fix", 0.8),
            ("why_error", 0.6),
            ("how_to_test", 0.4),
        ],
        "how_to_test": [
            ("how_to_run_test", 0.7),
            ("debug_test_failure", 0.5),
            ("how_to_mock", 0.4),
        ],
        "code_review": [
            ("how_to_refactor", 0.6),
            ("how_to_optimize", 0.5),
            ("how_to_document", 0.4),
        ],
        "architecture": [
            ("how_to_implement", 0.7),
            ("design_pattern", 0.5),
            ("dependency_question", 0.4),
        ],
        "deployment": [
            ("config_question", 0.6),
            ("debug_deployment", 0.5),
            ("monitoring_question", 0.4),
        ],
    }

    # 操作模式映射
    ACTION_PATTERNS: Dict[str, List[Tuple[str, float]]] = {
        "create_file": [
            ("edit_file", 0.8),
            ("create_test", 0.6),
            ("run_test", 0.4),
        ],
        "edit_file": [
            ("run_test", 0.7),
            ("edit_file", 0.5),
            ("commit", 0.4),
        ],
        "run_test": [
            ("fix_test", 0.6),
            ("edit_file", 0.5),
            ("commit", 0.4),
        ],
        "debug": [
            ("edit_file", 0.8),
            ("run_test", 0.5),
            ("add_logging", 0.4),
        ],
        "refactor": [
            ("run_test", 0.8),
            ("edit_file", 0.5),
            ("code_review", 0.4),
        ],
        "commit": [
            ("push", 0.7),
            ("create_pr", 0.5),
            ("next_task", 0.4),
        ],
    }

    # 帮助类型映射
    HELP_PATTERNS: Dict[str, List[Tuple[str, float]]] = {
        "new_project": [
            ("setup_guide", 0.8),
            ("architecture_advice", 0.6),
            ("best_practices", 0.5),
        ],
        "debugging": [
            ("error_explanation", 0.8),
            ("fix_suggestion", 0.7),
            ("debugging_tips", 0.5),
        ],
        "testing": [
            ("test_coverage", 0.7),
            ("test_strategy", 0.6),
            ("mock_guidance", 0.5),
        ],
        "deployment": [
            ("deployment_checklist", 0.8),
            ("config_review", 0.6),
            ("rollback_plan", 0.5),
        ],
        "performance": [
            ("profiling_guide", 0.7),
            ("optimization_tips", 0.6),
            ("caching_strategy", 0.5),
        ],
    }

    # 关键词映射
    KEYWORD_MAPPINGS: Dict[str, Dict[str, str]] = {
        "question": {
            "implement": "how_to_implement",
            "create": "how_to_implement",
            "build": "how_to_implement",
            "error": "debug_error",
            "bug": "debug_error",
            "fail": "debug_error",
            "test": "how_to_test",
            "unittest": "how_to_test",
            "pytest": "how_to_test",
            "review": "code_review",
            "refactor": "code_review",
            "architecture": "architecture",
            "design": "architecture",
            "deploy": "deployment",
            "release": "deployment",
        },
        "action": {
            "create": "create_file",
            "new": "create_file",
            "edit": "edit_file",
            "modify": "edit_file",
            "change": "edit_file",
            "test": "run_test",
            "pytest": "run_test",
            "debug": "debug",
            "fix": "debug",
            "refactor": "refactor",
            "optimize": "refactor",
            "commit": "commit",
            "git": "commit",
        },
        "state": {
            "init": "new_project",
            "setup": "new_project",
            "start": "new_project",
            "error": "debugging",
            "exception": "debugging",
            "traceback": "debugging",
            "test": "testing",
            "coverage": "testing",
            "deploy": "deployment",
            "release": "deployment",
            "slow": "performance",
            "optimize": "performance",
        },
    }

    def predict(
        self,
        context: PredictionContext,
        prediction_type: PredictionType,
    ) -> List[Tuple[str, float, str]]:
        """基于规则进行预测"""
        if prediction_type == PredictionType.NEXT_QUESTION:
            return self._predict_question(context)
        elif prediction_type == PredictionType.NEXT_ACTION:
            return self._predict_action(context)
        elif prediction_type == PredictionType.NEEDED_HELP:
            return self._predict_help(context)
        return []

    def _predict_question(
        self, context: PredictionContext
    ) -> List[Tuple[str, float, str]]:
        """预测下一个问题"""
        current_type = self._identify_type(
            context.current_message, self.KEYWORD_MAPPINGS["question"]
        )

        if current_type not in self.QUESTION_PATTERNS:
            return []

        results = []
        for next_type, confidence in self.QUESTION_PATTERNS[current_type]:
            reasoning = f"规则匹配: {current_type} -> {next_type}"
            results.append((next_type, confidence, reasoning))

        return results

    def _predict_action(
        self, context: PredictionContext
    ) -> List[Tuple[str, float, str]]:
        """预测下一步操作"""
        current_action = self._identify_action(context.code_context)

        if current_action not in self.ACTION_PATTERNS:
            return []

        results = []
        for next_action, confidence in self.ACTION_PATTERNS[current_action]:
            reasoning = f"规则匹配: {current_action} -> {next_action}"
            results.append((next_action, confidence, reasoning))

        return results

    def _predict_help(self, context: PredictionContext) -> List[Tuple[str, float, str]]:
        """预测需要的帮助"""
        project_state = self._identify_type(
            str(context.project_state.get("current_state", "")),
            self.KEYWORD_MAPPINGS["state"],
        )

        # 检查错误状态
        if context.project_state.get("has_errors", False):
            project_state = "debugging"
        elif context.project_state.get("running_tests", False):
            project_state = "testing"

        if project_state not in self.HELP_PATTERNS:
            return []

        results = []
        for help_type, confidence in self.HELP_PATTERNS[project_state]:
            reasoning = f"规则匹配: 项目状态 {project_state} -> {help_type}"
            results.append((help_type, confidence, reasoning))

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

    def _identify_action(self, code_context: Dict[str, Any]) -> str:
        """识别操作类型"""
        if not code_context:
            return "unknown"

        action = code_context.get("last_action", "")
        if action:
            return self._identify_type(action, self.KEYWORD_MAPPINGS["action"])

        modified_files = code_context.get("modified_files", [])
        if modified_files:
            if any("test" in f.lower() for f in modified_files):
                return "run_test"
            return "edit_file"

        return "unknown"


class LLMBasedEngine(BasePredictionEngine):
    """LLM推理引擎

    使用大语言模型进行智能预测。
    """

    # 预测提示词模板
    PROMPT_TEMPLATES: Dict[PredictionType, str] = {
        PredictionType.NEXT_QUESTION: """基于以下上下文，预测用户接下来最可能提出的问题。

当前消息: {current_message}
对话历史: {conversation_history}
用户偏好: {user_preferences}

请分析用户的意图和需求，预测3个最可能的后续问题。
对于每个预测，提供：
1. 预测的问题内容
2. 置信度（0-1之间的数值）
3. 推理依据

以JSON格式返回：
[
  {{"content": "问题内容", "confidence": 0.8, "reasoning": "推理依据"}},
  ...
]""",
        PredictionType.NEXT_ACTION: """基于以下上下文，预测用户接下来最可能执行的操作。

当前消息: {current_message}
代码上下文: {code_context}
用户偏好: {user_preferences}

请分析用户的工作流程，预测3个最可能的后续操作。
对于每个预测，提供：
1. 预测的操作内容
2. 置信度（0-1之间的数值）
3. 推理依据

以JSON格式返回：
[
  {{"content": "操作内容", "confidence": 0.8, "reasoning": "推理依据"}},
  ...
]""",
        PredictionType.NEEDED_HELP: """基于以下上下文，预测用户可能需要的帮助。

当前消息: {current_message}
项目状态: {project_state}
用户偏好: {user_preferences}

请分析用户的当前处境，预测3个最可能需要的帮助类型。
对于每个预测，提供：
1. 帮助类型和具体内容
2. 置信度（0-1之间的数值）
3. 推理依据

以JSON格式返回：
[
  {{"content": "帮助内容", "confidence": 0.8, "reasoning": "推理依据"}},
  ...
]""",
    }

    def __init__(self, llm_provider: Optional[LLMProvider] = None) -> None:
        """初始化LLM引擎

        Args:
            llm_provider: LLM提供者，如果为None则使用默认实现
        """
        self._llm_provider = llm_provider

    def set_llm_provider(self, provider: LLMProvider) -> None:
        """设置LLM提供者"""
        self._llm_provider = provider

    def predict(
        self,
        context: PredictionContext,
        prediction_type: PredictionType,
    ) -> List[Tuple[str, float, str]]:
        """使用LLM进行预测"""
        if self._llm_provider is None:
            return []

        prompt = self._build_prompt(context, prediction_type)
        if not prompt:
            return []

        try:
            response = self._llm_provider.complete(prompt)
            return self._parse_response(response)
        except Exception:
            return []

    def _build_prompt(
        self,
        context: PredictionContext,
        prediction_type: PredictionType,
    ) -> str:
        """构建提示词"""
        template = self.PROMPT_TEMPLATES.get(prediction_type)
        if not template:
            return ""

        user_prefs = self._extract_user_preferences(context.user_profile)
        history_str = self._format_conversation_history(context.conversation_history)

        return template.format(
            current_message=context.current_message or "无",
            conversation_history=history_str,
            code_context=str(context.code_context) if context.code_context else "无",
            project_state=str(context.project_state) if context.project_state else "无",
            user_preferences=user_prefs,
        )

    def _extract_user_preferences(self, user_profile: Dict[str, Any]) -> str:
        """提取用户偏好摘要"""
        if not user_profile:
            return "无用户画像数据"

        prefs = []
        interaction = user_profile.get("preferences", {}).get("interaction_style", {})
        if interaction:
            style = interaction.get("preferred_style", "")
            if style:
                prefs.append(f"交互风格: {style}")

        tech = user_profile.get("preferences", {}).get("tech_stack", {})
        if tech:
            langs = tech.get("preferred_languages", [])
            if langs:
                prefs.append(f"偏好语言: {', '.join(langs[:3])}")

        question_pattern = user_profile.get("interaction_pattern", {}).get(
            "question_pattern", {}
        )
        question_types = question_pattern.get("question_types", {})
        if question_types:
            top_types = sorted(
                question_types.items(), key=lambda x: x[1], reverse=True
            )[:3]
            prefs.append(f"常见问题类型: {', '.join([t[0] for t in top_types])}")

        return "; ".join(prefs) if prefs else "无特定偏好"

    def _format_conversation_history(self, history: List[Dict[str, Any]]) -> str:
        """格式化对话历史"""
        if not history:
            return "无历史记录"

        recent = history[-5:]
        formatted = []
        for item in recent:
            role = item.get("role", "unknown")
            content = item.get("content", "")[:100]
            formatted.append(f"[{role}]: {content}")

        return "\n".join(formatted)

    def _parse_response(self, response: str) -> List[Tuple[str, float, str]]:
        """解析LLM响应"""
        import json

        results = []
        try:
            start = response.find("[")
            end = response.rfind("]") + 1
            if start >= 0 and end > start:
                json_str = response[start:end]
                predictions = json.loads(json_str)

                for pred in predictions:
                    content = pred.get("content", "")
                    confidence = float(pred.get("confidence", 0.5))
                    reasoning = pred.get("reasoning", "LLM推理")
                    confidence = min(1.0, max(0.0, confidence))
                    results.append((content, confidence, reasoning))
        except (json.JSONDecodeError, ValueError, KeyError):
            pass

        return results


class ContextPredictor:
    """上下文预测器

    基于当前对话和代码修改预测下一步操作。
    支持规则引擎和LLM混合预测策略。
    """

    # 内容生成模板
    QUESTION_TEMPLATES: Dict[str, str] = {
        "how_to_implement": "如何实现这个功能？",
        "how_to_test": "如何为这段代码编写测试？",
        "how_to_optimize": "如何优化这段代码的性能？",
        "debug_error": "这个错误是什么原因导致的？",
        "how_to_fix": "如何修复这个问题？",
        "why_error": "为什么会出现这个错误？",
        "how_to_run_test": "如何运行这些测试？",
        "debug_test_failure": "测试失败的原因是什么？",
        "how_to_mock": "如何模拟这个依赖？",
        "how_to_refactor": "如何重构这段代码？",
        "how_to_document": "如何为这段代码编写文档？",
        "design_pattern": "应该使用什么设计模式？",
        "dependency_question": "如何处理这个依赖关系？",
        "config_question": "如何配置这个选项？",
        "debug_deployment": "部署失败的原因是什么？",
        "monitoring_question": "如何监控这个服务？",
    }

    ACTION_TEMPLATES: Dict[str, str] = {
        "create_file": "创建新文件",
        "edit_file": "编辑文件",
        "create_test": "创建测试文件",
        "run_test": "运行测试",
        "fix_test": "修复测试",
        "commit": "提交代码",
        "push": "推送代码",
        "create_pr": "创建 Pull Request",
        "next_task": "开始下一个任务",
        "debug": "调试代码",
        "add_logging": "添加日志",
        "refactor": "重构代码",
        "code_review": "代码审查",
    }

    HELP_TEMPLATES: Dict[str, str] = {
        "setup_guide": "项目设置指南",
        "architecture_advice": "架构设计建议",
        "best_practices": "最佳实践推荐",
        "error_explanation": "错误原因解释",
        "fix_suggestion": "修复建议",
        "debugging_tips": "调试技巧",
        "test_coverage": "测试覆盖率分析",
        "test_strategy": "测试策略建议",
        "mock_guidance": "Mock 使用指南",
        "deployment_checklist": "部署检查清单",
        "config_review": "配置审查",
        "rollback_plan": "回滚计划",
        "profiling_guide": "性能分析指南",
        "optimization_tips": "优化建议",
        "caching_strategy": "缓存策略",
    }

    def __init__(
        self,
        strategy: PredictionStrategy = PredictionStrategy.HYBRID,
        llm_provider: Optional[LLMProvider] = None,
    ) -> None:
        """初始化上下文预测器

        Args:
            strategy: 预测策略
            llm_provider: LLM提供者（可选）
        """
        self._strategy = strategy
        self._rule_engine = RuleBasedEngine()
        self._llm_engine = LLMBasedEngine(llm_provider)
        self._prediction_cache: Dict[str, PredictionResult] = {}

    @property
    def strategy(self) -> PredictionStrategy:
        """获取当前预测策略"""
        return self._strategy

    @strategy.setter
    def strategy(self, value: PredictionStrategy) -> None:
        """设置预测策略"""
        self._strategy = value

    def set_llm_provider(self, provider: LLMProvider) -> None:
        """设置LLM提供者"""
        self._llm_engine.set_llm_provider(provider)

    def predict_next_question(self, context: PredictionContext) -> PredictionResult:
        """预测下一个问题

        基于当前对话预测用户可能提出的下一个问题。

        Args:
            context: 预测上下文

        Returns:
            预测结果
        """
        predictions = self._get_predictions(context, PredictionType.NEXT_QUESTION)

        if not predictions:
            return PredictionResult(
                prediction_type=PredictionType.NEXT_QUESTION,
                content="无法预测下一个问题",
                confidence_score=0.0,
                reasoning="没有足够的上下文信息进行预测",
            )

        best = max(predictions, key=lambda x: x[1])
        content, confidence, reasoning = best

        if content in self.QUESTION_TEMPLATES:
            content = self.QUESTION_TEMPLATES[content]

        alternatives = self._build_alternatives(
            predictions[1:4], PredictionType.NEXT_QUESTION, self.QUESTION_TEMPLATES
        )
        evidence = self._collect_evidence(context, "question")

        return PredictionResult(
            prediction_type=PredictionType.NEXT_QUESTION,
            content=content,
            confidence_score=confidence,
            reasoning=reasoning,
            evidence=evidence,
            alternatives=alternatives,
        )

    def predict_next_action(self, context: PredictionContext) -> PredictionResult:
        """预测下一步操作

        基于代码修改预测用户可能执行的下一步操作。

        Args:
            context: 预测上下文

        Returns:
            预测结果
        """
        predictions = self._get_predictions(context, PredictionType.NEXT_ACTION)

        if not predictions:
            return PredictionResult(
                prediction_type=PredictionType.NEXT_ACTION,
                content="无法预测下一步操作",
                confidence_score=0.0,
                reasoning="没有足够的上下文信息进行预测",
            )

        best = max(predictions, key=lambda x: x[1])
        content, confidence, reasoning = best

        if content in self.ACTION_TEMPLATES:
            content = self.ACTION_TEMPLATES[content]

        alternatives = self._build_alternatives(
            predictions[1:4], PredictionType.NEXT_ACTION, self.ACTION_TEMPLATES
        )
        evidence = self._collect_evidence(context, "action")

        return PredictionResult(
            prediction_type=PredictionType.NEXT_ACTION,
            content=content,
            confidence_score=confidence,
            reasoning=reasoning,
            evidence=evidence,
            alternatives=alternatives,
        )

    def predict_needed_help(self, context: PredictionContext) -> List[PredictionResult]:
        """预测需要的帮助

        基于项目状态预测用户可能需要的帮助。

        Args:
            context: 预测上下文

        Returns:
            预测结果列表
        """
        predictions = self._get_predictions(context, PredictionType.NEEDED_HELP)

        if not predictions:
            return []

        results: List[PredictionResult] = []
        evidence = self._collect_evidence(context, "help")

        for content, confidence, reasoning in predictions:
            if content in self.HELP_TEMPLATES:
                content = self.HELP_TEMPLATES[content]

            results.append(
                PredictionResult(
                    prediction_type=PredictionType.NEEDED_HELP,
                    content=content,
                    confidence_score=confidence,
                    reasoning=reasoning,
                    evidence=evidence,
                )
            )

        results.sort(key=lambda x: x.confidence_score, reverse=True)
        return results

    def _get_predictions(
        self,
        context: PredictionContext,
        prediction_type: PredictionType,
    ) -> List[Tuple[str, float, str]]:
        """获取预测结果"""
        predictions: List[Tuple[str, float, str]] = []

        if self._strategy == PredictionStrategy.RULE_BASED:
            predictions = self._rule_engine.predict(context, prediction_type)
        elif self._strategy == PredictionStrategy.LLM_BASED:
            predictions = self._llm_engine.predict(context, prediction_type)
        elif self._strategy == PredictionStrategy.HYBRID:
            rule_predictions = self._rule_engine.predict(context, prediction_type)
            llm_predictions = self._llm_engine.predict(context, prediction_type)

            predictions = rule_predictions.copy()
            for content, confidence, reasoning in llm_predictions:
                if not any(self._is_similar(content, p[0]) for p in predictions):
                    adjusted_confidence = confidence * 0.95
                    predictions.append((content, adjusted_confidence, reasoning))

        predictions = self._apply_user_profile_boost(
            predictions, context.user_profile, prediction_type
        )
        predictions.sort(key=lambda x: x[1], reverse=True)

        return predictions

    def _is_similar(self, text1: str, text2: str) -> bool:
        """检查两个文本是否相似"""
        t1 = text1.lower().strip()
        t2 = text2.lower().strip()
        return t1 == t2 or t1 in t2 or t2 in t1

    def _apply_user_profile_boost(
        self,
        predictions: List[Tuple[str, float, str]],
        user_profile: Dict[str, Any],
        prediction_type: PredictionType,
    ) -> List[Tuple[str, float, str]]:
        """应用用户画像调整置信度"""
        if not user_profile or not predictions:
            return predictions

        adjusted: List[Tuple[str, float, str]] = []
        prefs = self._extract_preferences(user_profile, prediction_type)

        for content, confidence, reasoning in predictions:
            boost = 0.0
            content_lower = content.lower()
            for pref_key, pref_weight in prefs.items():
                if pref_key.lower() in content_lower:
                    boost = max(boost, pref_weight * 0.1)

            new_confidence = min(1.0, confidence + boost)
            adjusted.append((content, new_confidence, reasoning))

        return adjusted

    def _extract_preferences(
        self, user_profile: Dict[str, Any], prediction_type: PredictionType
    ) -> Dict[str, float]:
        """提取用户偏好"""
        prefs: Dict[str, float] = {}

        if prediction_type == PredictionType.NEXT_QUESTION:
            question_pattern = user_profile.get("interaction_pattern", {}).get(
                "question_pattern", {}
            )
            question_types = question_pattern.get("question_types", {})
            total = sum(question_types.values()) if question_types else 1
            for qtype, count in question_types.items():
                prefs[qtype] = count / total

        elif prediction_type == PredictionType.NEXT_ACTION:
            command_pattern = user_profile.get("interaction_pattern", {}).get(
                "command_pattern", {}
            )
            categories = command_pattern.get("command_categories", {})
            total = sum(categories.values()) if categories else 1
            for cat, count in categories.items():
                prefs[cat] = count / total

        return prefs

    def _build_alternatives(
        self,
        predictions: List[Tuple[str, float, str]],
        prediction_type: PredictionType,
        templates: Dict[str, str],
    ) -> List[PredictionResult]:
        """构建备选预测"""
        alternatives = []
        for content, confidence, reasoning in predictions:
            if content in templates:
                content = templates[content]
            alternatives.append(
                PredictionResult(
                    prediction_type=prediction_type,
                    content=content,
                    confidence_score=confidence,
                    reasoning=reasoning,
                )
            )
        return alternatives

    def _collect_evidence(
        self, context: PredictionContext, evidence_type: str
    ) -> List[str]:
        """收集预测证据"""
        evidence: List[str] = []

        if context.current_message:
            evidence.append(f"当前消息: {context.current_message[:100]}...")

        if context.conversation_history:
            evidence.append(f"对话历史长度: {len(context.conversation_history)}")

        if evidence_type == "action" and context.code_context:
            modified = context.code_context.get("modified_files", [])
            if modified:
                evidence.append(f"修改的文件: {', '.join(modified[:3])}")

        if evidence_type == "help" and context.project_state:
            if context.project_state.get("has_errors"):
                evidence.append("检测到错误状态")
            if context.project_state.get("running_tests"):
                evidence.append("正在运行测试")

        return evidence
