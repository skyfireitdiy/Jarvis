#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
构建验证模块

提供编辑后编译/构建验证功能，支持多种构建系统，具有易扩展性和兜底机制。
"""

# 导出主要接口
from .base import BuildResult
from .base import BuildSystem
from .base import BuildValidatorBase
from .cmake import CMakeBuildValidator
from .detector import BuildSystemDetector
from .fallback import FallbackBuildValidator
from .go import GoBuildValidator
from .java_gradle import JavaGradleBuildValidator
from .java_maven import JavaMavenBuildValidator
from .makefile import MakefileBuildValidator
from .nodejs import NodeJSBuildValidator
from .python import PythonBuildValidator

# 导出各语言验证器（便于扩展）
from .rust import RustBuildValidator
from .validator import BuildValidator

__all__ = [
    # 主要接口
    "BuildSystem",
    "BuildResult",
    "BuildValidatorBase",
    "BuildSystemDetector",
    "BuildValidator",
    # 各语言验证器
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
