#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Rust构建验证器模块

提供Rust项目的构建验证功能。
"""

import time
from typing import List, Optional

from .base import BuildValidatorBase, BuildResult, BuildSystem


class RustBuildValidator(BuildValidatorBase):
    """Rust构建验证器（使用cargo check）"""
    
    def validate(self, modified_files: Optional[List[str]] = None) -> BuildResult:
        start_time = time.time()
        
        # 使用 cargo check 进行增量检查（比 cargo build 更快）
        cmd = ["cargo", "check", "--message-format=json"]
        
        returncode, stdout, stderr = self._run_command(cmd)
        duration = time.time() - start_time
        
        success = returncode == 0
        output = stdout + stderr
        
        if not success:
            # 尝试解析JSON格式的错误信息
            error_message = self._parse_cargo_errors(output)
        else:
            error_message = None
        
        return BuildResult(
            success=success,
            output=output,
            error_message=error_message,
            build_system=BuildSystem.RUST,
            duration=duration,
        )
    
    def _parse_cargo_errors(self, output: str) -> str:
        """解析cargo的错误输出"""
        # 简化处理：提取关键错误信息
        lines = output.split("\n")
        errors = []
        for line in lines:
            if "error[" in line or "error:" in line.lower():
                errors.append(line.strip())
        return "\n".join(errors[:10]) if errors else output[:500]  # 限制长度

