#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Go构建验证器模块

提供Go项目的构建验证功能。
"""

import time
from typing import List, Optional

from .base import BuildValidatorBase, BuildResult, BuildSystem


class GoBuildValidator(BuildValidatorBase):
    """Go构建验证器"""
    
    def validate(self, modified_files: Optional[List[str]] = None) -> BuildResult:
        start_time = time.time()
        
        # 使用 go build 进行构建验证
        cmd = ["go", "build", "./..."]
        
        returncode, stdout, stderr = self._run_command(cmd, timeout=30)
        duration = time.time() - start_time
        
        success = returncode == 0
        output = stdout + stderr
        
        return BuildResult(
            success=success,
            output=output,
            error_message=None if success else "Go构建失败",
            build_system=BuildSystem.GO,
            duration=duration,
        )

