#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Java Maven构建验证器模块

提供Java Maven项目的构建验证功能。
"""

import time
from typing import List, Optional

from .base import BuildValidatorBase, BuildResult, BuildSystem


class JavaMavenBuildValidator(BuildValidatorBase):
    """Java Maven构建验证器"""

    BUILD_SYSTEM_NAME = "Maven"
    SUPPORTED_LANGUAGES = ["java"]

    def validate(self, modified_files: Optional[List[str]] = None) -> BuildResult:
        start_time = time.time()

        # 使用 mvn compile 进行编译验证
        cmd = ["mvn", "compile", "-q"]  # -q 静默模式

        returncode, stdout, stderr = self._run_command(cmd, timeout=60)
        duration = time.time() - start_time

        success = returncode == 0
        output = stdout + stderr

        if success:
            print(f"✅ Maven 构建验证成功（耗时 {duration:.2f} 秒）")
        else:
            print(f"❌ Maven 构建验证失败（耗时 {duration:.2f} 秒）")
            print(f"错误信息：Maven编译失败\n{output[:500]}")

        return BuildResult(
            success=success,
            output=output,
            error_message=None if success else "Maven编译失败",
            build_system=BuildSystem.JAVA_MAVEN,
            duration=duration,
        )
