#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
自定义构建验证器模块

支持用户在配置文件中定义自定义构建命令进行验证。
"""

import time
from typing import List
from typing import Optional

from jarvis.jarvis_utils.output import PrettyOutput

from .base import BuildResult
from .base import BuildSystem
from .base import BuildValidatorBase


class CustomBuildValidator(BuildValidatorBase):
    """自定义构建验证器"""

    BUILD_SYSTEM_NAME = "Custom"
    SUPPORTED_LANGUAGES = ["*"]  # 支持所有语言

    def __init__(
        self, project_root: str, timeout: int = 30, command: Optional[str] = None
    ):
        super().__init__(project_root, timeout)
        self.custom_command = command
        # 导入配置管理器
        from jarvis.jarvis_code_agent.build_validation_config import (
            BuildValidationConfig,
        )

        self.config = BuildValidationConfig(project_root)
        # 如果没有传入命令，从配置文件读取
        if self.custom_command is None:
            self.custom_command = self.config.get_custom_build_command()

    def validate(self, modified_files: Optional[List[str]] = None) -> BuildResult:
        """验证构建

        Args:
            modified_files: 修改的文件列表（此验证器不使用此参数）

        Returns:
            BuildResult: 验证结果
        """
        start_time = time.time()

        # 检查是否配置了自定义命令
        if not self.custom_command:
            duration = time.time() - start_time
            error_msg = "未配置自定义构建命令，请在 .jarvis/build_validation_config.yaml 中设置 custom_build_command"
            PrettyOutput.auto_print(f"❌ {error_msg}")
            return BuildResult(
                success=False,
                output="",
                error_message=error_msg,
                build_system=BuildSystem.CUSTOM,
                duration=duration,
            )

        PrettyOutput.auto_print(f"🔧 执行自定义构建命令: {self.custom_command}")

        # 解析命令（支持复杂命令，如 "make && make test"）
        try:
            # 使用 bash 执行命令，以支持 shell 特性（如 &&、||、管道等）
            returncode, stdout, stderr = self._run_command(
                ["bash", "-c", self.custom_command],
                cwd=self.project_root,
                timeout=self.timeout,
                capture_output=True,
            )
        except Exception as e:
            duration = time.time() - start_time
            error_msg = f"执行自定义构建命令时出错: {str(e)}"
            PrettyOutput.auto_print(f"❌ {error_msg}")
            return BuildResult(
                success=False,
                output="",
                error_message=error_msg,
                build_system=BuildSystem.CUSTOM,
                duration=duration,
            )

        duration = time.time() - start_time
        success = returncode == 0
        output = stdout + stderr

        if success:
            PrettyOutput.auto_print(f"✅ 自定义构建验证成功（耗时 {duration:.2f} 秒）")
        else:
            PrettyOutput.auto_print(
                f"❌ 自定义构建验证失败（耗时 {duration:.2f} 秒，返回码: {returncode}）"
            )
            # 显示输出（限制长度）
            output_preview = output[:1000] if len(output) > 1000 else output
            PrettyOutput.auto_print(f"输出：\n{output_preview}")
            if len(output) > 1000:
                PrettyOutput.auto_print(
                    f"...（输出已截断，完整输出共 {len(output)} 字符）"
                )

        return BuildResult(
            success=success,
            output=output,
            error_message=None
            if success
            else f"自定义构建命令返回错误码: {returncode}",
            build_system=BuildSystem.CUSTOM,
            duration=duration,
        )
