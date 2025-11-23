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
    """Go构建验证器（使用go test，包括编译和测试）"""
    
    BUILD_SYSTEM_NAME = "Go Build"
    SUPPORTED_LANGUAGES = ["go"]
    
    def validate(self, modified_files: Optional[List[str]] = None) -> BuildResult:
        start_time = time.time()
        
        # 使用 go test 进行构建和测试验证（会自动编译并运行测试）
        cmd = ["go", "test", "./..."]
        
        returncode, stdout, stderr = self._run_command(cmd, timeout=30)
        duration = time.time() - start_time
        
        success = returncode == 0
        output = stdout + stderr
        
        if not success:
            # 尝试解析错误信息（包括编译错误和测试失败）
            error_message = self._parse_go_errors(output)
            print(f"❌ Go 构建验证失败（耗时 {duration:.2f} 秒）")
            if error_message:
                print(f"错误信息：\n{error_message}")
            else:
                print(f"输出：\n{output[:500]}")
        else:
            error_message = None
            print(f"✅ Go 构建验证成功（耗时 {duration:.2f} 秒）")
        
        return BuildResult(
            success=success,
            output=output,
            error_message=error_message,
            build_system=BuildSystem.GO,
            duration=duration,
        )
    
    def _parse_go_errors(self, output: str) -> str:
        """解析Go的错误输出（包括编译错误和测试失败）"""
        # 简化处理：提取关键错误信息
        lines = output.split("\n")
        errors = []
        for line in lines:
            # 匹配编译错误
            if "error:" in line.lower() or "cannot" in line.lower():
                errors.append(line.strip())
            # 匹配测试失败
            elif "--- FAIL:" in line or "FAIL" in line:
                errors.append(line.strip())
            # 匹配断言失败
            elif "got" in line.lower() and "want" in line.lower():
                errors.append(line.strip())
        return "\n".join(errors[:10]) if errors else output[:500]  # 限制长度

