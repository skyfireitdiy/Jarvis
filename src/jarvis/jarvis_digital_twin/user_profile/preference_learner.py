"""偏好学习器模块

学习用户的各种偏好，包括代码风格、技术栈和交互风格。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from jarvis.jarvis_utils.output import PrettyOutput


class CodeStylePreference(Enum):
    """代码风格偏好枚举"""

    CONCISE = "concise"  # 简洁风格
    VERBOSE = "verbose"  # 详细风格
    FUNCTIONAL = "functional"  # 函数式风格
    OOP = "oop"  # 面向对象风格
    MIXED = "mixed"  # 混合风格


class InteractionStylePreference(Enum):
    """交互风格偏好枚举"""

    FORMAL = "formal"  # 正式
    CASUAL = "casual"  # 随意
    TECHNICAL = "technical"  # 技术性
    FRIENDLY = "friendly"  # 友好


@dataclass
class PreferenceConfidence:
    """偏好置信度数据类

    记录单个偏好的置信度信息。
    """

    value: float = 0.5  # 置信度值 0-1
    sample_count: int = 0  # 样本数量
    last_updated: str = ""  # 最后更新时间

    def update(self, positive: bool, weight: float = 1.0) -> None:
        """更新置信度

        Args:
            positive: 是否为正向反馈
            weight: 更新权重
        """
        adjustment = 0.1 * weight if positive else -0.1 * weight
        self.value = max(0.0, min(1.0, self.value + adjustment))
        self.sample_count += 1
        self.last_updated = datetime.now().isoformat()


@dataclass
class CodeStyleDetail:
    """代码风格详细偏好

    记录用户的代码风格详细偏好。
    """

    preferred_style: CodeStylePreference = CodeStylePreference.MIXED
    indentation: str = "spaces"  # spaces 或 tabs
    indent_size: int = 4
    max_line_length: int = 88
    prefer_type_hints: bool = True
    prefer_docstrings: bool = True
    naming_convention: str = "snake_case"  # snake_case, camelCase, PascalCase
    confidence: PreferenceConfidence = field(default_factory=PreferenceConfidence)


@dataclass
class TechStackPreference:
    """技术栈偏好数据类

    记录用户的技术栈偏好。
    """

    preferred_languages: List[str] = field(default_factory=list)
    preferred_frameworks: List[str] = field(default_factory=list)
    preferred_tools: List[str] = field(default_factory=list)
    avoided_technologies: List[str] = field(default_factory=list)
    confidence: PreferenceConfidence = field(default_factory=PreferenceConfidence)


@dataclass
class InteractionStyleDetail:
    """交互风格详细偏好

    记录用户的交互风格详细偏好。
    """

    preferred_style: InteractionStylePreference = InteractionStylePreference.FRIENDLY
    verbosity_level: float = 0.5  # 0-1，详细程度
    prefer_examples: bool = True
    prefer_explanations: bool = True
    response_language: str = "zh"  # 响应语言
    confidence: PreferenceConfidence = field(default_factory=PreferenceConfidence)


@dataclass
class UserPreference:
    """用户偏好数据类

    综合记录用户的各种偏好。
    """

    user_id: str = "default"
    code_style: CodeStyleDetail = field(default_factory=CodeStyleDetail)
    tech_stack: TechStackPreference = field(default_factory=TechStackPreference)
    interaction_style: InteractionStyleDetail = field(
        default_factory=InteractionStyleDetail
    )
    custom_preferences: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        """初始化后处理"""
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "user_id": self.user_id,
            "code_style": {
                "preferred_style": self.code_style.preferred_style.value,
                "indentation": self.code_style.indentation,
                "indent_size": self.code_style.indent_size,
                "max_line_length": self.code_style.max_line_length,
                "prefer_type_hints": self.code_style.prefer_type_hints,
                "prefer_docstrings": self.code_style.prefer_docstrings,
                "naming_convention": self.code_style.naming_convention,
                "confidence": self.code_style.confidence.value,
            },
            "tech_stack": {
                "preferred_languages": self.tech_stack.preferred_languages,
                "preferred_frameworks": self.tech_stack.preferred_frameworks,
                "preferred_tools": self.tech_stack.preferred_tools,
                "avoided_technologies": self.tech_stack.avoided_technologies,
                "confidence": self.tech_stack.confidence.value,
            },
            "interaction_style": {
                "preferred_style": self.interaction_style.preferred_style.value,
                "verbosity_level": self.interaction_style.verbosity_level,
                "prefer_examples": self.interaction_style.prefer_examples,
                "prefer_explanations": self.interaction_style.prefer_explanations,
                "response_language": self.interaction_style.response_language,
                "confidence": self.interaction_style.confidence.value,
            },
            "custom_preferences": self.custom_preferences,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserPreference":
        """从字典创建UserPreference对象"""
        code_style_data = data.get("code_style", {})
        tech_stack_data = data.get("tech_stack", {})
        interaction_style_data = data.get("interaction_style", {})

        # 解析代码风格
        try:
            code_style_enum = CodeStylePreference(
                code_style_data.get("preferred_style", "mixed")
            )
        except ValueError:
            code_style_enum = CodeStylePreference.MIXED

        code_style = CodeStyleDetail(
            preferred_style=code_style_enum,
            indentation=code_style_data.get("indentation", "spaces"),
            indent_size=code_style_data.get("indent_size", 4),
            max_line_length=code_style_data.get("max_line_length", 88),
            prefer_type_hints=code_style_data.get("prefer_type_hints", True),
            prefer_docstrings=code_style_data.get("prefer_docstrings", True),
            naming_convention=code_style_data.get("naming_convention", "snake_case"),
            confidence=PreferenceConfidence(
                value=code_style_data.get("confidence", 0.5)
            ),
        )

        # 解析技术栈偏好
        tech_stack = TechStackPreference(
            preferred_languages=tech_stack_data.get("preferred_languages", []),
            preferred_frameworks=tech_stack_data.get("preferred_frameworks", []),
            preferred_tools=tech_stack_data.get("preferred_tools", []),
            avoided_technologies=tech_stack_data.get("avoided_technologies", []),
            confidence=PreferenceConfidence(
                value=tech_stack_data.get("confidence", 0.5)
            ),
        )

        # 解析交互风格
        try:
            interaction_style_enum = InteractionStylePreference(
                interaction_style_data.get("preferred_style", "friendly")
            )
        except ValueError:
            interaction_style_enum = InteractionStylePreference.FRIENDLY

        interaction_style = InteractionStyleDetail(
            preferred_style=interaction_style_enum,
            verbosity_level=interaction_style_data.get("verbosity_level", 0.5),
            prefer_examples=interaction_style_data.get("prefer_examples", True),
            prefer_explanations=interaction_style_data.get("prefer_explanations", True),
            response_language=interaction_style_data.get("response_language", "zh"),
            confidence=PreferenceConfidence(
                value=interaction_style_data.get("confidence", 0.5)
            ),
        )

        return cls(
            user_id=data.get("user_id", "default"),
            code_style=code_style,
            tech_stack=tech_stack,
            interaction_style=interaction_style,
            custom_preferences=data.get("custom_preferences", {}),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


@dataclass
class InteractionData:
    """交互数据类

    用于传递交互信息给学习器。
    """

    content: str = ""
    interaction_type: str = ""  # command, question, feedback
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self) -> None:
        """初始化后处理"""
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class PreferenceLearner:
    """偏好学习器

    学习用户的各种偏好，包括代码风格、技术栈和交互风格。
    """

    # 代码风格关键词映射
    CODE_STYLE_KEYWORDS: Dict[CodeStylePreference, List[str]] = {
        CodeStylePreference.CONCISE: ["简洁", "简短", "精简", "concise", "short"],
        CodeStylePreference.VERBOSE: ["详细", "完整", "verbose", "detailed"],
        CodeStylePreference.FUNCTIONAL: [
            "函数式",
            "functional",
            "lambda",
            "map",
            "filter",
        ],
        CodeStylePreference.OOP: ["类", "对象", "class", "object", "oop", "继承"],
    }

    # 技术栈关键词
    LANGUAGE_KEYWORDS: List[str] = [
        "python",
        "javascript",
        "typescript",
        "rust",
        "go",
        "java",
        "c++",
        "c#",
    ]

    FRAMEWORK_KEYWORDS: List[str] = [
        "django",
        "flask",
        "fastapi",
        "react",
        "vue",
        "angular",
        "spring",
    ]

    TOOL_KEYWORDS: List[str] = [
        "git",
        "docker",
        "kubernetes",
        "pytest",
        "mypy",
        "ruff",
        "black",
    ]

    # 交互风格关键词
    INTERACTION_STYLE_KEYWORDS: Dict[InteractionStylePreference, List[str]] = {
        InteractionStylePreference.FORMAL: ["正式", "专业", "formal", "professional"],
        InteractionStylePreference.CASUAL: ["随意", "轻松", "casual", "relaxed"],
        InteractionStylePreference.TECHNICAL: ["技术", "详细", "technical", "detailed"],
        InteractionStylePreference.FRIENDLY: ["友好", "亲切", "friendly", "warm"],
    }

    def __init__(self, user_id: str = "default", llm_client: Optional[Any] = None):
        """初始化偏好学习器

        Args:
            user_id: 用户ID
            llm_client: LLM客户端实例（可选）
        """
        self.user_id = user_id
        self.llm_client = llm_client
        self._preference = UserPreference(user_id=user_id)
        self._interaction_history: List[InteractionData] = []

    @property
    def preference(self) -> UserPreference:
        """获取当前用户偏好"""
        return self._preference

    def _llm_analyze_preferences(
        self, interaction: InteractionData
    ) -> Optional[Dict[str, Any]]:
        """使用LLM分析用户偏好

        Args:
            interaction: 交互数据

        Returns:
            Optional[Dict[str, Any]]: 分析结果字典，失败时返回None
        """
        if self.llm_client is None:
            return None

        try:
            # 构建分析上下文
            recent_interactions = (
                self._interaction_history[-5:] if self._interaction_history else []
            )
            interaction_context = "\n".join(
                [f"- {interp.content}" for interp in recent_interactions]
            )

            prompt = f"""你是一个用户偏好分析专家。请分析用户的代码和交互行为，推断其偏好。

当前输入：{interaction.content}
交互类型：{interaction.interaction_type}
标签：{", ".join(interaction.tags)}

最近的交互历史：
{interaction_context if interaction_context else "无"}

请返回JSON格式的分析结果：
{{
  "code_style": "concise/verbose/functional/oop/mixed",
  "interaction_style": "formal/casual/technical/friendly",
  "verbosity_level": 0.7,
  "prefer_examples": true,
  "preferred_languages": ["python", "rust"],
  "reasoning": "分析依据",
  "confidence": 0.85
}}

只返回JSON，不要其他内容。"""

            # 调用LLM
            response = self.llm_client.complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500,
            )

            # 解析响应
            import json
            import re

            # 提取JSON内容
            json_match = re.search(r"\{[^}]+\}", response.content, re.DOTALL)
            if json_match:
                result: Dict[str, Any] = json.loads(json_match.group())
                return result
            else:
                return None

        except Exception:
            # LLM调用失败时返回None，将降级到规则模式
            return None

    def learn_from_interaction(self, interaction: InteractionData) -> None:
        """从交互中学习偏好

        Args:
            interaction: 交互数据
        """
        self._interaction_history.append(interaction)

        # 优先尝试使用LLM分析
        llm_result = self._llm_analyze_preferences(interaction)
        mode = "LLM" if llm_result else "规则"

        if llm_result:
            # LLM模式：使用LLM分析结果
            try:
                # 更新代码风格
                if "code_style" in llm_result:
                    try:
                        code_style = CodeStylePreference(llm_result["code_style"])
                        self._preference.code_style.preferred_style = code_style
                    except ValueError:
                        pass

                # 更新交互风格
                if "interaction_style" in llm_result:
                    try:
                        interaction_style = InteractionStylePreference(
                            llm_result["interaction_style"]
                        )
                        self._preference.interaction_style.preferred_style = (
                            interaction_style
                        )
                    except ValueError:
                        pass

                # 更新详细程度
                if "verbosity_level" in llm_result:
                    self._preference.interaction_style.verbosity_level = llm_result[
                        "verbosity_level"
                    ]

                # 更新示例偏好
                if "prefer_examples" in llm_result:
                    self._preference.interaction_style.prefer_examples = llm_result[
                        "prefer_examples"
                    ]

                # 更新语言偏好
                if "preferred_languages" in llm_result:
                    for lang in llm_result["preferred_languages"]:
                        if lang not in self._preference.tech_stack.preferred_languages:
                            self._preference.tech_stack.preferred_languages.append(lang)

                # 提升置信度
                self._preference.code_style.confidence.update(True)
                self._preference.interaction_style.confidence.update(True)
                self._preference.tech_stack.confidence.update(True)

            except Exception:
                # LLM结果解析失败，降级到规则模式
                mode = "规则"
                self._learn_code_style(interaction)
                self._learn_tech_stack(interaction)
                self._learn_interaction_style(interaction)
        else:
            # 规则模式：使用关键词匹配
            self._learn_code_style(interaction)
            self._learn_tech_stack(interaction)
            self._learn_interaction_style(interaction)

        # 过程打印
        code_style_str: str = self._preference.code_style.preferred_style.value
        interaction_style_str: str = (
            self._preference.interaction_style.preferred_style.value
        )
        PrettyOutput.auto_print(
            f"👤 偏好学习: 代码风格={code_style_str}, 交互风格={interaction_style_str} (模式: {mode})"
        )

        # 更新时间戳
        self._preference.updated_at = datetime.now().isoformat()

    def _learn_code_style(self, interaction: InteractionData) -> None:
        """从交互中学习代码风格偏好"""
        content_lower = interaction.content.lower()

        # 检测代码风格偏好
        for style, keywords in self.CODE_STYLE_KEYWORDS.items():
            if any(kw in content_lower for kw in keywords):
                self._preference.code_style.preferred_style = style
                self._preference.code_style.confidence.update(True)
                break

        # 检测类型注解偏好
        if "type hint" in content_lower or "类型注解" in content_lower:
            self._preference.code_style.prefer_type_hints = True
            self._preference.code_style.confidence.update(True)
        elif "no type" in content_lower or "不要类型" in content_lower:
            self._preference.code_style.prefer_type_hints = False
            self._preference.code_style.confidence.update(True)

        # 检测文档字符串偏好
        if "docstring" in content_lower or "文档字符串" in content_lower:
            self._preference.code_style.prefer_docstrings = True
            self._preference.code_style.confidence.update(True)

    def _learn_tech_stack(self, interaction: InteractionData) -> None:
        """从交互中学习技术栈偏好"""
        content_lower = interaction.content.lower()
        tags_lower = [t.lower() for t in interaction.tags]

        # 检测语言偏好
        for lang in self.LANGUAGE_KEYWORDS:
            if lang in content_lower or lang in tags_lower:
                if lang not in self._preference.tech_stack.preferred_languages:
                    self._preference.tech_stack.preferred_languages.append(lang)
                    self._preference.tech_stack.confidence.update(True)

        # 检测框架偏好
        for framework in self.FRAMEWORK_KEYWORDS:
            if framework in content_lower or framework in tags_lower:
                if framework not in self._preference.tech_stack.preferred_frameworks:
                    self._preference.tech_stack.preferred_frameworks.append(framework)
                    self._preference.tech_stack.confidence.update(True)

        # 检测工具偏好
        for tool in self.TOOL_KEYWORDS:
            if tool in content_lower or tool in tags_lower:
                if tool not in self._preference.tech_stack.preferred_tools:
                    self._preference.tech_stack.preferred_tools.append(tool)
                    self._preference.tech_stack.confidence.update(True)

    def _learn_interaction_style(self, interaction: InteractionData) -> None:
        """从交互中学习交互风格偏好"""
        content_lower = interaction.content.lower()

        # 检测交互风格偏好
        for style, keywords in self.INTERACTION_STYLE_KEYWORDS.items():
            if any(kw in content_lower for kw in keywords):
                self._preference.interaction_style.preferred_style = style
                self._preference.interaction_style.confidence.update(True)
                break

        # 检测详细程度偏好
        if "详细" in content_lower or "detailed" in content_lower:
            self._preference.interaction_style.verbosity_level = min(
                1.0, self._preference.interaction_style.verbosity_level + 0.1
            )
        elif "简洁" in content_lower or "concise" in content_lower:
            self._preference.interaction_style.verbosity_level = max(
                0.0, self._preference.interaction_style.verbosity_level - 0.1
            )

        # 检测示例偏好
        if "例子" in content_lower or "example" in content_lower:
            self._preference.interaction_style.prefer_examples = True
            self._preference.interaction_style.confidence.update(True)

    def get_code_style_preference(self) -> CodeStyleDetail:
        """获取代码风格偏好

        Returns:
            CodeStyleDetail: 代码风格详细偏好
        """
        return self._preference.code_style

    def get_tech_preference(self) -> TechStackPreference:
        """获取技术栈偏好

        Returns:
            TechStackPreference: 技术栈偏好
        """
        return self._preference.tech_stack

    def get_interaction_style_preference(self) -> InteractionStyleDetail:
        """获取交互风格偏好

        Returns:
            InteractionStyleDetail: 交互风格详细偏好
        """
        return self._preference.interaction_style

    def update_preference(
        self,
        preference_type: str,
        key: str,
        value: Any,
        confidence_boost: bool = True,
    ) -> bool:
        """更新特定偏好

        Args:
            preference_type: 偏好类型 (code_style, tech_stack, interaction_style, custom)
            key: 偏好键
            value: 偏好值
            confidence_boost: 是否提升置信度

        Returns:
            bool: 是否更新成功
        """
        try:
            if preference_type == "code_style":
                if hasattr(self._preference.code_style, key):
                    setattr(self._preference.code_style, key, value)
                    if confidence_boost:
                        self._preference.code_style.confidence.update(True)
                    self._preference.updated_at = datetime.now().isoformat()
                    return True
            elif preference_type == "tech_stack":
                if hasattr(self._preference.tech_stack, key):
                    setattr(self._preference.tech_stack, key, value)
                    if confidence_boost:
                        self._preference.tech_stack.confidence.update(True)
                    self._preference.updated_at = datetime.now().isoformat()
                    return True
            elif preference_type == "interaction_style":
                if hasattr(self._preference.interaction_style, key):
                    setattr(self._preference.interaction_style, key, value)
                    if confidence_boost:
                        self._preference.interaction_style.confidence.update(True)
                    self._preference.updated_at = datetime.now().isoformat()
                    return True
            elif preference_type == "custom":
                self._preference.custom_preferences[key] = value
                self._preference.updated_at = datetime.now().isoformat()
                return True

            return False
        except (AttributeError, TypeError):
            return False

    def get_preference_confidence(self, preference_type: str) -> float:
        """获取特定偏好的置信度

        Args:
            preference_type: 偏好类型

        Returns:
            float: 置信度值 (0-1)
        """
        if preference_type == "code_style":
            return self._preference.code_style.confidence.value
        elif preference_type == "tech_stack":
            return self._preference.tech_stack.confidence.value
        elif preference_type == "interaction_style":
            return self._preference.interaction_style.confidence.value
        return 0.0

    def get_overall_confidence(self) -> float:
        """获取整体偏好置信度

        Returns:
            float: 整体置信度 (0-1)
        """
        confidences = [
            self._preference.code_style.confidence.value,
            self._preference.tech_stack.confidence.value,
            self._preference.interaction_style.confidence.value,
        ]
        return sum(confidences) / len(confidences)

    def reset_preference(self, preference_type: Optional[str] = None) -> None:
        """重置偏好

        Args:
            preference_type: 要重置的偏好类型，None表示重置所有
        """
        if preference_type is None or preference_type == "code_style":
            self._preference.code_style = CodeStyleDetail()
        if preference_type is None or preference_type == "tech_stack":
            self._preference.tech_stack = TechStackPreference()
        if preference_type is None or preference_type == "interaction_style":
            self._preference.interaction_style = InteractionStyleDetail()
        if preference_type is None or preference_type == "custom":
            self._preference.custom_preferences = {}

        self._preference.updated_at = datetime.now().isoformat()

    def export_preference(self) -> Dict[str, Any]:
        """导出用户偏好

        Returns:
            Dict[str, Any]: 偏好字典
        """
        return self._preference.to_dict()

    def import_preference(self, data: Dict[str, Any]) -> None:
        """导入用户偏好

        Args:
            data: 偏好字典
        """
        self._preference = UserPreference.from_dict(data)
        self._preference.user_id = self.user_id

    def get_interaction_history_count(self) -> int:
        """获取交互历史数量

        Returns:
            int: 交互历史数量
        """
        return len(self._interaction_history)

    def clear_interaction_history(self) -> None:
        """清除交互历史"""
        self._interaction_history = []
