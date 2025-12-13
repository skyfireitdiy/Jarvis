#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
构建验证器基础模块

提供基础类和枚举定义。
"""

import subprocess
from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import List
from typing import Optional
from typing import Tuple


class BuildSystem(Enum):
    """支持的构建系统类型"""

    UNKNOWN = "unknown"
    PYTHON = "python"
    NODEJS = "nodejs"
    RUST = "rust"
    JAVA_MAVEN = "java_maven"
    JAVA_GRADLE = "java_gradle"
    GO = "go"
    C_MAKEFILE = "c_makefile"
    C_CMAKE = "c_cmake"
    C_MAKEFILE_CMAKE = "c_makefile_cmake"  # 同时存在Makefile和CMakeLists.txt


@dataclass
class BuildResult:
    """构建验证结果"""

    success: bool
    output: str
    error_message: Optional[str] = None
    build_system: Optional[BuildSystem] = None
    duration: float = 0.0  # 验证耗时（秒）


class BuildValidatorBase(ABC):
    """构建验证器基类"""

    # 子类需要定义的类变量
    BUILD_SYSTEM_NAME: str = ""  # 构建系统名称，如 "CMake", "Makefile", "Cargo"
    SUPPORTED_LANGUAGES: List[str] = []  # 支持的语言列表，如 ["c", "cpp"]

    def __init__(self, project_root: str, timeout: int = 30):
        self.project_root = project_root
        self.timeout = timeout

    @abstractmethod
    def validate(self, modified_files: Optional[List[str]] = None) -> BuildResult:
        """验证构建

        Args:
            modified_files: 修改的文件列表（可选，用于增量验证）

        Returns:
            BuildResult: 验证结果
        """
        pass

    def _run_command(
        self,
        cmd: List[str],
        cwd: Optional[str] = None,
        timeout: Optional[int] = None,
        capture_output: bool = True,
    ) -> Tuple[int, str, str]:
        """运行命令

        Args:
            cmd: 命令列表
            cwd: 工作目录
            timeout: 超时时间（秒）
            capture_output: 是否捕获输出

        Returns:
            (返回码, stdout, stderr)
        """
        if cwd is None:
            cwd = self.project_root
        if timeout is None:
            timeout = self.timeout

        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                timeout=timeout,
                capture_output=capture_output,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            stdout = result.stdout if capture_output else ""
            stderr = result.stderr if capture_output else ""
            return result.returncode, stdout, stderr
        except subprocess.TimeoutExpired:
            return -1, "", f"命令执行超时（{timeout}秒）"
        except FileNotFoundError:
            return -1, "", f"命令未找到: {cmd[0]}"
        except Exception as e:
            return -1, "", f"执行命令时出错: {str(e)}"
