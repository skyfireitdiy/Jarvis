"""
Java Gradle构建验证器模块

提供Java Gradle项目的构建验证功能。
"""

import os
import time
from typing import List

from jarvis.jarvis_utils.output import PrettyOutput

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional

from .base import BuildResult
from .base import BuildSystem
from .base import BuildValidatorBase


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

        if success:
            PrettyOutput.auto_print(f"✅ Gradle 构建验证成功（耗时 {duration:.2f} 秒）")
        else:
            PrettyOutput.auto_print(f"❌ Gradle 构建验证失败（耗时 {duration:.2f} 秒）")
            PrettyOutput.auto_print(f"错误信息：Gradle编译失败\n{output[:500]}")

        return BuildResult(
            success=success,
            output=output,
            error_message=None if success else "Gradle编译失败",
            build_system=BuildSystem.JAVA_GRADLE,
            duration=duration,
        )
