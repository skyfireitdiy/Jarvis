#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CMake构建验证器模块

提供CMake项目的构建验证功能。
"""

import os
import tempfile
import time
from typing import List, Optional

from .base import BuildValidatorBase, BuildResult, BuildSystem


class CMakeBuildValidator(BuildValidatorBase):
    """CMake构建验证器"""
    
    def validate(self, modified_files: Optional[List[str]] = None) -> BuildResult:
        start_time = time.time()
        
        # 策略1: 尝试使用 cmake --build（如果已有构建目录）
        build_dirs = ["build", "cmake-build-debug", "cmake-build-release"]
        for build_dir in build_dirs:
            build_path = os.path.join(self.project_root, build_dir)
            if os.path.exists(build_path):
                returncode, stdout, stderr = self._run_command(
                    ["cmake", "--build", build_path],
                    timeout=60,
                )
                duration = time.time() - start_time
                success = returncode == 0
                return BuildResult(
                    success=success,
                    output=stdout + stderr,
                    error_message=None if success else "CMake构建失败",
                    build_system=BuildSystem.C_CMAKE,
                    duration=duration,
                )
        
        # 策略2: 仅验证CMakeLists.txt语法
        with tempfile.TemporaryDirectory(prefix="cmake_check_") as tmpdir:
            returncode, stdout, stderr = self._run_command(
                ["cmake", "-S", ".", "-B", tmpdir],
                timeout=10,
            )
        duration = time.time() - start_time
        
        success = returncode == 0
        return BuildResult(
            success=success,
            output=stdout + stderr,
            error_message=None if success else "CMake配置失败",
            build_system=BuildSystem.C_CMAKE,
            duration=duration,
        )

