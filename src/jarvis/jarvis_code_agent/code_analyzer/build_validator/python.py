"""
Python构建验证器模块

提供Python项目的构建验证功能。
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


class PythonBuildValidator(BuildValidatorBase):
    """Python构建验证器（包括编译和测试）"""

    BUILD_SYSTEM_NAME = "Python"
    SUPPORTED_LANGUAGES = ["python"]

    def _extract_python_errors(self, output: str) -> str:
        """提取Python错误信息（包括编译错误和测试失败）"""
        if not output:
            return ""

        lines = output.split("\n")
        errors = []
        in_error = False

        for line in lines:
            line_lower = line.lower()
            # 检测错误关键词（包括编译错误和测试失败）
            if any(
                keyword in line_lower
                for keyword in [
                    "error",
                    "failed",
                    "exception",
                    "traceback",
                    "syntaxerror",
                    "indentationerror",
                    "assertionerror",
                    "failed:",
                    "failures:",
                    "test",
                    "assert",
                ]
            ):
                in_error = True
                errors.append(line.strip())
            elif in_error and line.strip():
                # 继续收集错误相关的行
                if line.strip().startswith(
                    ("File", "  File", "    ", "E ", "FAILED", "FAILURES", "assert")
                ):
                    errors.append(line.strip())
                elif not line.strip().startswith("="):
                    # 如果遇到非错误相关的行，停止收集
                    if len(errors) > 0 and not any(
                        keyword in line_lower
                        for keyword in [
                            "error",
                            "failed",
                            "exception",
                            "assert",
                            "test",
                        ]
                    ):
                        break

        # 如果收集到错误，返回前20行（限制长度）
        if errors:
            error_text = "\n".join(errors[:20])
            # 如果太长，截断
            if len(error_text) > 1000:
                error_text = error_text[:1000] + "\n... (错误信息已截断)"
            return error_text

        # 如果没有提取到结构化错误，返回原始输出的前500字符
        return output[:500] if output else ""

    def validate(self, modified_files: Optional[List[str]] = None) -> BuildResult:
        start_time = time.time()

        # 策略1: 尝试使用 py_compile 编译修改的文件
        if modified_files:
            errors = []
            error_outputs = []
            for file_path in modified_files:
                if not file_path.endswith(".py"):
                    continue
                full_path = os.path.join(self.project_root, file_path)
                if os.path.exists(full_path):
                    returncode, stdout, stderr = self._run_command(
                        ["python", "-m", "py_compile", full_path],
                        timeout=5,
                    )
                    if returncode != 0:
                        file_error_msg = f"{file_path}: {stderr}".strip()
                        errors.append(file_error_msg)
                        error_outputs.append(stdout + stderr)

            if errors:
                duration = time.time() - start_time
                # 合并所有错误输出
                full_output = "\n".join(error_outputs)
                # 提取关键错误信息
                error_message = self._extract_python_errors(full_output)
                if not error_message:
                    # 如果没有提取到结构化错误，使用简化的错误列表
                    error_message = "\n".join(errors[:5])  # 最多显示5个文件的错误
                    if len(errors) > 5:
                        error_message += f"\n... 还有 {len(errors) - 5} 个文件存在错误"
                PrettyOutput.auto_print(
                    f"❌ Python 构建验证失败（耗时 {duration:.2f} 秒）"
                )
                PrettyOutput.auto_print(f"错误信息：\n{error_message}")
                return BuildResult(
                    success=False,
                    output=full_output,
                    error_message=error_message,
                    build_system=BuildSystem.PYTHON,
                    duration=duration,
                )

        # 策略2: 尝试运行 pytest（会自动编译并运行测试，即使没有配置文件也会自动发现测试）
        # 首先尝试 pytest
        returncode, stdout, stderr = self._run_command(
            ["python", "-m", "pytest", "-v"],
            timeout=30,
        )
        # 如果 pytest 命令本身失败（如未安装），尝试 unittest
        if returncode == 1 and "No module named pytest" in stderr:
            # pytest 未安装，尝试使用 unittest
            returncode, stdout, stderr = self._run_command(
                ["python", "-m", "unittest", "discover", "-v"],
                timeout=30,
            )

        duration = time.time() - start_time
        success = returncode == 0
        output = stdout + stderr

        # 如果失败，提取关键错误信息（包括编译错误和测试失败）
        error_msg: Optional[str] = None
        if not success:
            error_msg = self._extract_python_errors(output)
            if not error_msg:
                # 检查是否是"没有找到测试"的情况（这不算失败）
                if (
                    "no tests ran" in output.lower()
                    or "no tests found" in output.lower()
                ):
                    # 没有测试文件，但语法检查通过，视为成功
                    PrettyOutput.auto_print(
                        f"✅ Python 构建验证成功（耗时 {duration:.2f} 秒，未发现测试文件）"
                    )
                    return BuildResult(
                        success=True,
                        output="Python语法检查通过（未发现测试文件）",
                        error_message=None,
                        build_system=BuildSystem.PYTHON,
                        duration=duration,
                    )
                error_msg = "Python项目验证失败（编译或测试失败）"
            PrettyOutput.auto_print(f"❌ Python 构建验证失败（耗时 {duration:.2f} 秒）")
            if error_msg:
                PrettyOutput.auto_print(f"错误信息：\n{error_msg}")
            else:
                PrettyOutput.auto_print(f"输出：\n{output[:500]}")
        else:
            PrettyOutput.auto_print(f"✅ Python 构建验证成功（耗时 {duration:.2f} 秒）")

        return BuildResult(
            success=success,
            output=output,
            error_message=error_msg,
            build_system=BuildSystem.PYTHON,
            duration=duration,
        )
