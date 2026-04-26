#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
构建验证模块（向后兼容导入）

此文件保持向后兼容，实际实现已迁移到 build_validator 包中。
"""

# 从新模块导入所有内容，保持向后兼容
from jarvis.jarvis_code_agent.code_analyzer.build_validator import BuildResult
from jarvis.jarvis_code_agent.code_analyzer.build_validator import BuildSystem
from jarvis.jarvis_code_agent.code_analyzer.build_validator import BuildSystemDetector
from jarvis.jarvis_code_agent.code_analyzer.build_validator import BuildValidator
from jarvis.jarvis_code_agent.code_analyzer.build_validator import BuildValidatorBase
from jarvis.jarvis_code_agent.code_analyzer.build_validator import CMakeBuildValidator
from jarvis.jarvis_code_agent.code_analyzer.build_validator import (
    FallbackBuildValidator,
)
from jarvis.jarvis_code_agent.code_analyzer.build_validator import GoBuildValidator
from jarvis.jarvis_code_agent.code_analyzer.build_validator import (
    JavaGradleBuildValidator,
)
from jarvis.jarvis_code_agent.code_analyzer.build_validator import (
    JavaMavenBuildValidator,
)
from jarvis.jarvis_code_agent.code_analyzer.build_validator import (
    MakefileBuildValidator,
)
from jarvis.jarvis_code_agent.code_analyzer.build_validator import NodeJSBuildValidator
from jarvis.jarvis_code_agent.code_analyzer.build_validator import PythonBuildValidator
from jarvis.jarvis_code_agent.code_analyzer.build_validator import RustBuildValidator

__all__ = [
    "BuildSystem",
    "BuildResult",
    "BuildValidatorBase",
    "BuildSystemDetector",
    "BuildValidator",
    "RustBuildValidator",
    "PythonBuildValidator",
    "NodeJSBuildValidator",
    "JavaMavenBuildValidator",
    "JavaGradleBuildValidator",
    "GoBuildValidator",
    "CMakeBuildValidator",
    "MakefileBuildValidator",
    "FallbackBuildValidator",
]
