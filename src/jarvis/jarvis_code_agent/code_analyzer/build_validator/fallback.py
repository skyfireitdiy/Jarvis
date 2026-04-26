"""
兜底构建验证器模块

当无法检测构建系统时使用的兜底验证器。
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


class FallbackBuildValidator(BuildValidatorBase):
    """兜底验证器：当无法检测构建系统时使用"""

    def validate(self, modified_files: Optional[List[str]] = None) -> BuildResult:
        start_time = time.time()

        # 策略1: 根据文件扩展名进行基本的语法检查
        if modified_files:
            errors = []
            for file_path in modified_files:
                ext = os.path.splitext(file_path)[1].lower()
                full_path = os.path.join(self.project_root, file_path)

                if not os.path.exists(full_path):
                    continue

                # Python文件：使用py_compile
                if ext == ".py":
                    returncode, _, stderr = self._run_command(
                        ["python", "-m", "py_compile", full_path],
                        timeout=5,
                    )
                    if returncode != 0:
                        errors.append(f"{file_path}: {stderr}")

                # JavaScript文件：尝试使用node检查语法
                elif ext in (".js", ".mjs", ".cjs"):
                    returncode, _, stderr = self._run_command(
                        ["node", "--check", full_path],
                        timeout=5,
                    )
                    if returncode != 0:
                        errors.append(f"{file_path}: {stderr}")

            if errors:
                duration = time.time() - start_time
                PrettyOutput.auto_print(
                    f"❌ 基础语法检查失败（耗时 {duration:.2f} 秒）"
                )
                PrettyOutput.auto_print(
                    f"错误信息：语法检查失败\n{chr(10).join(errors[:5])}"
                )
                return BuildResult(
                    success=False,
                    output="\n".join(errors),
                    error_message="语法检查失败",
                    build_system=BuildSystem.UNKNOWN,
                    duration=duration,
                )

        duration = time.time() - start_time
        PrettyOutput.auto_print(
            f"✅ 基础语法检查通过（耗时 {duration:.2f} 秒，未检测到构建系统）"
        )
        return BuildResult(
            success=True,
            output="基础语法检查通过（未检测到构建系统）",
            error_message=None,
            build_system=BuildSystem.UNKNOWN,
            duration=duration,
        )
