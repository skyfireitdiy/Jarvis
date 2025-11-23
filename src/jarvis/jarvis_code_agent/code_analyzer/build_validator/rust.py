#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Rust构建验证器模块

提供Rust项目的构建验证功能。
"""

import os
import subprocess
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
        # 设置 RUST_BACKTRACE=1 以启用调用链回溯
        # 设置 RUSTFLAGS="-A warnings" 以屏蔽警告，只显示错误
        cmd = ["cargo", "test", "--", "--nocapture"]
        
        # 准备环境变量（继承当前环境并设置 RUST_BACKTRACE 和 RUSTFLAGS）
        env = os.environ.copy()
        env["RUST_BACKTRACE"] = "1"
        # 如果已存在 RUSTFLAGS，则追加；否则新建
        if "RUSTFLAGS" in env:
            env["RUSTFLAGS"] = env["RUSTFLAGS"] + " -A warnings"
        else:
            env["RUSTFLAGS"] = "-A warnings"
        
        # 直接使用 subprocess.run 以支持环境变量
        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                timeout=self.timeout,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            returncode = result.returncode
            stdout = result.stdout
            stderr = result.stderr
        except subprocess.TimeoutExpired:
            returncode = -1
            stdout = ""
            stderr = f"命令执行超时（{self.timeout}秒）"
        except FileNotFoundError:
            returncode = -1
            stdout = ""
            stderr = f"命令未找到: {cmd[0]}"
        except Exception as e:
            returncode = -1
            stdout = ""
            stderr = f"执行命令时出错: {str(e)}"
        
        duration = time.time() - start_time
        
        success = returncode == 0
        output = stdout + stderr
        
        if not success:
            # 尝试解析错误信息（包括编译错误和测试失败）
            error_message = self._parse_cargo_errors(output)
            print(f"❌ Rust 构建验证失败（耗时 {duration:.2f} 秒）")
            if error_message:
                print(f"错误信息：\n{error_message}")
            else:
                print(f"输出：\n{output[:500]}")
        else:
            error_message = None
            print(f"✅ Rust 构建验证成功（耗时 {duration:.2f} 秒）")
        
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

