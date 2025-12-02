#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
构建验证模块

提供编辑后编译/构建验证功能，支持多种构建系统，具有易扩展性和兜底机制。
"""

# 导出主要接口
from .base import BuildSystem, BuildResult, BuildValidatorBase
from .detector import BuildSystemDetector
from .validator import BuildValidator

# 导出各语言验证器（便于扩展）
from .rust import RustBuildValidator
from .python import PythonBuildValidator
from .nodejs import NodeJSBuildValidator
from .java_maven import JavaMavenBuildValidator
from .java_gradle import JavaGradleBuildValidator
from .go import GoBuildValidator
from .cmake import CMakeBuildValidator
from .makefile import MakefileBuildValidator
from .fallback import FallbackBuildValidator

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
