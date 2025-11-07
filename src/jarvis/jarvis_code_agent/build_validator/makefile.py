#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Makefile构建验证器模块

提供Makefile项目的构建验证功能。
"""

import os
import time
from typing import List, Optional

from .base import BuildValidatorBase, BuildResult, BuildSystem


class MakefileBuildValidator(BuildValidatorBase):
    """Makefile构建验证器"""
    
    def validate(self, modified_files: Optional[List[str]] = None) -> BuildResult:
        start_time = time.time()
        
        # 尝试运行 make（如果存在Makefile）
        makefile = os.path.join(self.project_root, "Makefile")
        if not os.path.exists(makefile):
            duration = time.time() - start_time
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
        return BuildResult(
            success=success,
            output=stdout + stderr,
            error_message=None if success else "Makefile语法检查失败",
            build_system=BuildSystem.C_MAKEFILE,
            duration=duration,
        )

