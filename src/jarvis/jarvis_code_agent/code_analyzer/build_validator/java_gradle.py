#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Java Gradle构建验证器模块

提供Java Gradle项目的构建验证功能。
"""

import os
import time
from typing import List, Optional

from .base import BuildValidatorBase, BuildResult, BuildSystem


class JavaGradleBuildValidator(BuildValidatorBase):
    """Java Gradle构建验证器"""
    
    BUILD_SYSTEM_NAME = "Gradle"
    SUPPORTED_LANGUAGES = ["java"]
    
    def validate(self, modified_files: Optional[List[str]] = None) -> BuildResult:
        start_time = time.time()
        
        # 使用 gradle compileJava 进行编译验证
        # 优先使用 gradlew（如果存在）
        gradlew = os.path.join(self.project_root, "gradlew")
        if os.path.exists(gradlew):
            cmd = ["./gradlew", "compileJava", "--quiet"]
        else:
            cmd = ["gradle", "compileJava", "--quiet"]
        
        returncode, stdout, stderr = self._run_command(cmd, timeout=60)
        duration = time.time() - start_time
        
        success = returncode == 0
        output = stdout + stderr
        
        return BuildResult(
            success=success,
            output=output,
            error_message=None if success else "Gradle编译失败",
            build_system=BuildSystem.JAVA_GRADLE,
            duration=duration,
        )

