"""持续学习系统类型定义模块。

定义持续学习系统所需的所有类型，包括：
- 知识类型枚举
- 技能类型枚举
- 经验类型枚举
- 学习状态枚举
- 知识数据类
- 技能数据类
- 经验数据类
- 学习结果数据类
- Protocol接口定义
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Protocol


class KnowledgeType(Enum):
    """知识类型枚举。

    定义可学习的知识类型。
    """

    CONCEPT = "concept"  # 概念：抽象的概念定义
    PATTERN = "pattern"  # 模式：可复用的解决方案模式
    RULE = "rule"  # 规则：业务或技术规则
    FACT = "fact"  # 事实：具体的事实信息
    PROCEDURE = "procedure"  # 过程：操作步骤或流程


class SkillType(Enum):
    """技能类型枚举。

    定义可习得的技能类型。
    """

    TOOL_USAGE = "tool_usage"  # 工具使用：各种工具的使用技能
    LANGUAGE = "language"  # 语言：编程语言或自然语言
    FRAMEWORK = "framework"  # 框架：各种框架的使用
    METHODOLOGY = "methodology"  # 方法论：开发方法论
    DOMAIN = "domain"  # 领域：特定领域知识


class ExperienceType(Enum):
    """经验类型枚举。

    定义可积累的经验类型。
    """

    SUCCESS = "success"  # 成功：成功的经验
    FAILURE = "failure"  # 失败：失败的教训
    INSIGHT = "insight"  # 洞察：深刻的见解
    LESSON = "lesson"  # 教训：从错误中学到的


class LearningStatus(Enum):
    """学习状态枚举。

    定义学习项目的状态。
    """

    PENDING = "pending"  # 待学习
    LEARNING = "learning"  # 学习中
    LEARNED = "learned"  # 已学习
    VERIFIED = "verified"  # 已验证
    DEPRECATED = "deprecated"  # 已废弃


@dataclass
class Knowledge:
    """知识数据类。

    表示一条可学习的知识。
    """

    # 知识唯一标识
    id: str
    # 知识类型
    type: KnowledgeType
    # 知识内容
    content: str
    # 知识来源
    source: str
    # 置信度 (0-1)
    confidence: float = 1.0
    # 创建时间
    created_at: datetime = field(default_factory=datetime.now)
    # 更新时间
    updated_at: datetime = field(default_factory=datetime.now)
    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Skill:
    """技能数据类。

    表示一项可习得的技能。
    """

    # 技能唯一标识
    id: str
    # 技能类型
    type: SkillType
    # 技能名称
    name: str
    # 技能描述
    description: str
    # 熟练度 (0-1)
    proficiency: float = 0.0
    # 使用示例
    examples: List[str] = field(default_factory=list)
    # 创建时间
    created_at: datetime = field(default_factory=datetime.now)
    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Experience:
    """经验数据类。

    表示一条可积累的经验。
    """

    # 经验唯一标识
    id: str
    # 经验类型
    type: ExperienceType
    # 经验发生的上下文
    context: str
    # 经验的结果
    outcome: str
    # 从经验中学到的教训
    lessons: List[str] = field(default_factory=list)
    # 创建时间
    created_at: datetime = field(default_factory=datetime.now)
    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LearningResult:
    """学习结果数据类。

    记录一次学习操作的结果。
    """

    # 是否成功
    success: bool
    # 学习的项目数量
    items_learned: int = 0
    # 错误信息列表
    errors: List[str] = field(default_factory=list)
    # 学习耗时（秒）
    duration: float = 0.0
    # 学习的知识列表
    knowledge_items: List[Knowledge] = field(default_factory=list)
    # 学习的技能列表
    skill_items: List[Skill] = field(default_factory=list)
    # 学习的经验列表
    experience_items: List[Experience] = field(default_factory=list)


class KnowledgeSourceProtocol(Protocol):
    """知识来源协议。

    定义知识提取器的标准接口，支持依赖注入。
    """

    def extract(self, context: str) -> List[Knowledge]:
        """从上下文中提取知识。

        Args:
            context: 上下文信息

        Returns:
            提取的知识列表
        """
        ...


class SkillEvaluatorProtocol(Protocol):
    """技能评估器协议。

    定义技能评估器的标准接口，支持依赖注入。
    """

    def evaluate(self, skill: Skill) -> float:
        """评估技能熟练度。

        Args:
            skill: 要评估的技能

        Returns:
            熟练度分数 (0-1)
        """
        ...


class ExperienceMatcherProtocol(Protocol):
    """经验匹配器协议。

    定义经验匹配器的标准接口，支持依赖注入。
    """

    def match(self, context: str) -> List[Experience]:
        """匹配相关经验。

        Args:
            context: 当前上下文

        Returns:
            匹配的经验列表
        """
        ...
