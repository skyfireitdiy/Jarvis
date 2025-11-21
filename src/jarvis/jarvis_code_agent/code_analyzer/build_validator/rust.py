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
    """Rust构建验证器（使用cargo test，包括编译和测试）"""
    
    BUILD_SYSTEM_NAME = "Cargo"
    SUPPORTED_LANGUAGES = ["rust"]
    
    def validate(self, modified_files: Optional[List[str]] = None) -> BuildResult:
        start_time = time.time()
        
        # 使用 cargo test 进行构建和测试验证（会自动编译并运行测试）
        cmd = ["cargo", "test", "--", "--nocapture"]
        
        returncode, stdout, stderr = self._run_command(cmd)
        duration = time.time() - start_time
        
        success = returncode == 0
        output = stdout + stderr
        
        if not success:
            # 尝试解析错误信息（包括编译错误和测试失败）
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
        """解析cargo的错误输出（包括编译错误和测试失败）"""
        # 简化处理：提取关键错误信息
        lines = output.split("\n")
        errors = []
        for line in lines:
            # 匹配编译错误
            if "error[" in line or "error:" in line.lower():
                errors.append(line.strip())
            # 匹配测试失败
            elif "test" in line.lower() and ("failed" in line.lower() or "panic" in line.lower()):
                errors.append(line.strip())
            # 匹配断言失败
            elif "assertion" in line.lower() and "failed" in line.lower():
                errors.append(line.strip())
        return "\n".join(errors[:10]) if errors else output[:500]  # 限制长度

