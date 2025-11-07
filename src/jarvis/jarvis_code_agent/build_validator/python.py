#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Python构建验证器模块

提供Python项目的构建验证功能。
"""

import os
import time
from typing import List, Optional

from .base import BuildValidatorBase, BuildResult, BuildSystem


class PythonBuildValidator(BuildValidatorBase):
    """Python构建验证器"""
    
    def _extract_python_errors(self, output: str) -> str:
        """提取Python错误信息"""
        if not output:
            return ""
        
        lines = output.split("\n")
        errors = []
        in_error = False
        
        for line in lines:
            line_lower = line.lower()
            # 检测错误关键词
            if any(keyword in line_lower for keyword in ["error", "failed", "exception", "traceback", "syntaxerror", "indentationerror"]):
                in_error = True
                errors.append(line.strip())
            elif in_error and line.strip():
                # 继续收集错误相关的行
                if line.strip().startswith(("File", "  File", "    ", "E ", "FAILED")):
                    errors.append(line.strip())
                elif not line.strip().startswith("="):
                    # 如果遇到非错误相关的行，停止收集
                    if len(errors) > 0 and not any(keyword in line_lower for keyword in ["error", "failed", "exception"]):
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
                        error_msg = f"{file_path}: {stderr}".strip()
                        errors.append(error_msg)
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
                return BuildResult(
                    success=False,
                    output=full_output,
                    error_message=error_message,
                    build_system=BuildSystem.PYTHON,
                    duration=duration,
                )
        
        # 策略2: 尝试运行 pytest --collect-only（如果存在）
        if os.path.exists(os.path.join(self.project_root, "pytest.ini")) or \
           os.path.exists(os.path.join(self.project_root, "setup.py")):
            returncode, stdout, stderr = self._run_command(
                ["python", "-m", "pytest", "--collect-only", "-q"],
                timeout=10,
            )
            duration = time.time() - start_time
            success = returncode == 0
            output = stdout + stderr
            # 如果失败，提取关键错误信息
            if not success:
                error_msg = self._extract_python_errors(output)
                if not error_msg:
                    error_msg = "Python项目验证失败"
            else:
                error_msg = None
            return BuildResult(
                success=success,
                output=output,
                error_message=error_msg,
                build_system=BuildSystem.PYTHON,
                duration=duration,
            )
        
        # 策略3: 如果没有测试框架，仅验证语法（已在上面的策略1中完成）
        duration = time.time() - start_time
        return BuildResult(
            success=True,
            output="Python语法检查通过",
            error_message=None,
            build_system=BuildSystem.PYTHON,
            duration=duration,
        )

