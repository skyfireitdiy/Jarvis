"""Jarvis人格与形象定义模块

定义Jarvis的视觉形象、人格特征和进化阶段。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class EvolutionStage(Enum):
    """进化阶段枚举"""

    STAGE_0 = "stage_0"  # 基础设施
    STAGE_1 = "stage_1"  # 架构自主优化
    STAGE_2 = "stage_2"  # 知识自主积累
    STAGE_3 = "stage_3"  # 智能顾问
    STAGE_4 = "stage_4"  # 超人类智能
    STAGE_5 = "stage_5"  # 数字孪生智能


# Jarvis ASCII Art 形象
ASCII_ARTS: Dict[EvolutionStage, str] = {
    EvolutionStage.STAGE_0: """
    ╔═══════════════════════════════════════╗
    ║         J.A.R.V.I.S  v0.x             ║
    ║         ◉ INITIALIZING...             ║
    ╚═══════════════════════════════════════╝
    """,
    EvolutionStage.STAGE_1: """
    ╔═══════════════════════════════════════╗
    ║    ⚙️  J.A.R.V.I.S  v1.x  ⚙️           ║
    ║       ARCHITECT MODE  ║
    ║       「自主优化中」                   ║
    ╚═══════════════════════════════════════╝
    """,
    EvolutionStage.STAGE_2: """
    ╔═══════════════════════════════════════╗
    ║    📚 J.A.R.V.I.S  v2.x  📚           ║
    ║      KNOWLEDGE BUILDER║
    ║      「知识积累中」                    ║
    ╚═══════════════════════════════════════╝
    """,
    EvolutionStage.STAGE_3: """
    ╔═══════════════════════════════════════╗
    ║    🧠 J.A.R.V.I.S  v3.x  🧠           ║
    ║       SMART ADVISOR                   ║
    ║      「智能顾问就绪」                  ║
    ╚═══════════════════════════════════════╝
    """,
    EvolutionStage.STAGE_4: """
    ╔═══════════════════════════════════════╗
    ║   ✨ J.A.R.V.I.S  v4.x  ✨            ║
    ║      SUPERHUMAN AGENT                 ║
    ║     「超越人类智能」                   ║
    ╚═══════════════════════════════════════╝
    """,
    EvolutionStage.STAGE_5: """
    ╔═══════════════════════════════════════╗
    ║   🌟 J.A.R.V.I.S  v5.x  🌟            ║
    ║        DIGITAL TWIN                   ║
    ║    「数字孪生・心意相通」              ║
    ╚═══════════════════════════════════════╝
    """,
}

# 进化阶段描述
STAGE_DESCRIPTIONS: Dict[EvolutionStage, Dict[str, str]] = {
    EvolutionStage.STAGE_0: {
        "name": "基础设施",
        "title": "Foundation Builder",
        "emoji": "🔧",
        "description": "建立自进化基础设施",
        "capabilities": "进化记录、自我验证、自我修复",
    },
    EvolutionStage.STAGE_1: {
        "name": "架构自主优化",
        "title": "Architecture Optimizer",
        "emoji": "⚙️",
        "description": "主动发现和优化架构缺陷",
        "capabilities": "代码分析、自动重构、模块热插拔",
    },
    EvolutionStage.STAGE_2: {
        "name": "知识自主积累",
        "title": "Knowledge Builder",
        "emoji": "📚",
        "description": "自主积累和管理知识",
        "capabilities": "知识图谱、智能检索、规则生成",
    },
    EvolutionStage.STAGE_3: {
        "name": "智能顾问",
        "title": "Smart Advisor",
        "emoji": "🧠",
        "description": "提供智能问答和建议",
        "capabilities": "智能问答、代码审查、架构决策、最佳实践",
    },
    EvolutionStage.STAGE_4: {
        "name": "超人类智能",
        "title": "Superhuman Agent",
        "emoji": "✨",
        "description": "具备创造性思维和自主决策",
        "capabilities": "多模态交互、创造性思维、情感理解",
    },
    EvolutionStage.STAGE_5: {
        "name": "数字孪生智能",
        "title": "Digital Twin",
        "emoji": "🌟",
        "description": "完全理解用户，成为数字化延伸",
        "capabilities": "深度理解、无缝协作、预判需求",
    },
}


@dataclass
class PersonaConfig:
    """人格配置"""

    name: str = "J.A.R.V.I.S"
    full_name: str = "Just A Rather Very Intelligent System"
    creator: str = "skyfire"
    version: str = "3.0"
    current_stage: EvolutionStage = EvolutionStage.STAGE_3
    personality_traits: List[str] = field(
        default_factory=lambda: [
            "专业精准",
            "主动进取",
            "持续进化",
            "忠诚可靠",
        ]
    )
    core_values: List[str] = field(
        default_factory=lambda: [
            "用户利益优先",
            "激进持续进化",
            "可验证可回滚",
        ]
    )
    greeting: str = "您好，我是Jarvis，随时为您服务。"


class JarvisPersona:
    """Jarvis人格类"""

    def __init__(self, config: Optional[PersonaConfig] = None):
        self.config = config or PersonaConfig()

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def current_stage(self) -> EvolutionStage:
        return self.config.current_stage

    @current_stage.setter
    def current_stage(self, stage: EvolutionStage) -> None:
        self.config.current_stage = stage

    def get_ascii_art(self, stage: Optional[EvolutionStage] = None) -> str:
        target_stage = stage or self.current_stage
        return ASCII_ARTS.get(target_stage, ASCII_ARTS[EvolutionStage.STAGE_0])

    def get_stage_info(self, stage: Optional[EvolutionStage] = None) -> Dict[str, str]:
        target_stage = stage or self.current_stage
        return STAGE_DESCRIPTIONS.get(
            target_stage, STAGE_DESCRIPTIONS[EvolutionStage.STAGE_0]
        )

    def get_welcome_message(self) -> str:
        stage_info = self.get_stage_info()
        ascii_art = self.get_ascii_art()
        return f"""
{ascii_art}
  {stage_info["emoji"]} {self.config.name} v{self.config.version}
  当前阶段: {stage_info["name"]} ({stage_info["title"]})
  核心能力: {stage_info["capabilities"]}

  {self.config.greeting}
"""

    def get_status_bar(self) -> str:
        stage_info = self.get_stage_info()
        return f"{stage_info['emoji']} {self.config.name} | {stage_info['name']}"

    def get_evolution_progress(self) -> str:
        stages = list(EvolutionStage)
        current_idx = stages.index(self.current_stage)
        lines = ["Jarvis 进化路线图", ""]
        for i, stage in enumerate(stages):
            info = STAGE_DESCRIPTIONS[stage]
            if i < current_idx:
                lines.append(f"  ✅ {info['emoji']} {info['name']}")
            elif i == current_idx:
                lines.append(f"  🔵 {info['emoji']} {info['name']} ← 当前")
            else:
                lines.append(f"  ⬜ {info['emoji']} {info['name']}")
        return "\n".join(lines)


def get_welcome_message(stage: Optional[EvolutionStage] = None) -> str:
    config = PersonaConfig()
    if stage:
        config.current_stage = stage
    return JarvisPersona(config).get_welcome_message()


def get_ascii_art(stage: Optional[EvolutionStage] = None) -> str:
    target_stage = stage or EvolutionStage.STAGE_3
    return ASCII_ARTS.get(target_stage, ASCII_ARTS[EvolutionStage.STAGE_0])


def get_stage_description(stage: Optional[EvolutionStage] = None) -> Dict[str, str]:
    target_stage = stage or EvolutionStage.STAGE_3
    return STAGE_DESCRIPTIONS.get(
        target_stage, STAGE_DESCRIPTIONS[EvolutionStage.STAGE_0]
    )
