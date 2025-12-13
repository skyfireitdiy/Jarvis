"""
Java Maven构建验证器模块

提供Java Maven项目的构建验证功能。
"""

import time
from typing import List
from typing import Optional
from jarvis.jarvis_utils.output import PrettyOutput

#!/usr/bin/env python3
# -*- coding: utf-8 -*-


from .base import BuildResult
from .base import BuildSystem
from .base import BuildValidatorBase


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
            PrettyOutput.auto_print(f"✅ Maven 构建验证成功（耗时 {duration:.2f} 秒）")
        else:
            PrettyOutput.auto_print(f"❌ Maven 构建验证失败（耗时 {duration:.2f} 秒）")
            PrettyOutput.auto_print(f"错误信息：Maven编译失败\n{output[:500]}")

        return BuildResult(
            success=success,
            output=output,
            error_message=None if success else "Maven编译失败",
            build_system=BuildSystem.JAVA_MAVEN,
            duration=duration,
        )
