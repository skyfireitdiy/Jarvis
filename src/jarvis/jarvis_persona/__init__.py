"""Jarvis人格与形象模块

该模块定义Jarvis的人格特征、视觉形象和交互风格。
包含以下核心功能：
- Agent形象定义（ASCII Art + Emoji）
- 启动欢迎界面
- 进化阶段展示
- 人格特征配置
"""

from .persona import (
    JarvisPersona,
    EvolutionStage,
    PersonaConfig,
    ASCII_ARTS,
    STAGE_DESCRIPTIONS,
    get_welcome_message,
    get_ascii_art,
    get_stage_description,
)

__all__ = [
    "JarvisPersona",
    "EvolutionStage",
    "PersonaConfig",
    "ASCII_ARTS",
    "STAGE_DESCRIPTIONS",
    "get_welcome_message",
    "get_ascii_art",
    "get_stage_description",
]

__version__ = "0.1.0"
