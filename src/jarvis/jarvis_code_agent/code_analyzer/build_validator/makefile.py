"""
Makefile构建验证器模块

提供Makefile项目的构建验证功能。
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


class MakefileBuildValidator(BuildValidatorBase):
    """Makefile构建验证器"""

    BUILD_SYSTEM_NAME = "Makefile"
    SUPPORTED_LANGUAGES = ["c", "cpp"]

    def validate(self, modified_files: Optional[List[str]] = None) -> BuildResult:
        start_time = time.time()

        # 尝试运行 make（如果存在Makefile）
        makefile = os.path.join(self.project_root, "Makefile")
        if not os.path.exists(makefile):
            duration = time.time() - start_time
            PrettyOutput.auto_print(
                f"❌ Makefile 构建验证失败（耗时 {duration:.2f} 秒）"
            )
            PrettyOutput.auto_print("错误信息：Makefile不存在")
            return BuildResult(
                success=False,
                output="Makefile不存在",
                error_message="Makefile不存在",
                build_system=BuildSystem.C_MAKEFILE,
                duration=duration,
            )

        # 尝试 make -n（dry-run）来验证语法
        returncode, stdout, stderr = self._run_command(
            ["make", "-n"],
            timeout=10,
        )
        duration = time.time() - start_time

        success = returncode == 0
        output = stdout + stderr
        if success:
            PrettyOutput.auto_print(
                f"✅ Makefile 构建验证成功（耗时 {duration:.2f} 秒）"
            )
        else:
            PrettyOutput.auto_print(
                f"❌ Makefile 构建验证失败（耗时 {duration:.2f} 秒）"
            )
            PrettyOutput.auto_print(f"错误信息：Makefile语法检查失败\n{output[:500]}")
        return BuildResult(
            success=success,
            output=output,
            error_message=None if success else "Makefile语法检查失败",
            build_system=BuildSystem.C_MAKEFILE,
            duration=duration,
        )
