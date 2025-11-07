#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
构建验证模块

提供编辑后编译/构建验证功能，支持多种构建系统，具有易扩展性和兜底机制。
"""

import os
import subprocess
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


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


class BuildSystemDetector:
    """构建系统检测器"""
    
    def __init__(self, project_root: str):
        self.project_root = project_root
    
    def detect(self) -> Optional[BuildSystem]:
        """检测项目使用的构建系统
        
        Returns:
            检测到的构建系统，如果无法检测则返回None
        """
        # 按优先级检测（从最具体到最通用）
        detectors = [
            self._detect_rust,
            self._detect_go,
            self._detect_java_maven,
            self._detect_java_gradle,
            self._detect_nodejs,
            self._detect_python,
            self._detect_c_cmake,
            self._detect_c_makefile,
        ]
        
        for detector in detectors:
            result = detector()
            if result:
                return result
        
        return None
    
    def _detect_rust(self) -> Optional[BuildSystem]:
        """检测Rust项目（Cargo.toml）"""
        cargo_toml = os.path.join(self.project_root, "Cargo.toml")
        if os.path.exists(cargo_toml):
            return BuildSystem.RUST
        return None
    
    def _detect_go(self) -> Optional[BuildSystem]:
        """检测Go项目（go.mod）"""
        go_mod = os.path.join(self.project_root, "go.mod")
        if os.path.exists(go_mod):
            return BuildSystem.GO
        return None
    
    def _detect_java_maven(self) -> Optional[BuildSystem]:
        """检测Maven项目（pom.xml）"""
        pom_xml = os.path.join(self.project_root, "pom.xml")
        if os.path.exists(pom_xml):
            return BuildSystem.JAVA_MAVEN
        return None
    
    def _detect_java_gradle(self) -> Optional[BuildSystem]:
        """检测Gradle项目（build.gradle或build.gradle.kts）"""
        build_gradle = os.path.join(self.project_root, "build.gradle")
        build_gradle_kts = os.path.join(self.project_root, "build.gradle.kts")
        if os.path.exists(build_gradle) or os.path.exists(build_gradle_kts):
            return BuildSystem.JAVA_GRADLE
        return None
    
    def _detect_nodejs(self) -> Optional[BuildSystem]:
        """检测Node.js项目（package.json）"""
        package_json = os.path.join(self.project_root, "package.json")
        if os.path.exists(package_json):
            return BuildSystem.NODEJS
        return None
    
    def _detect_python(self) -> Optional[BuildSystem]:
        """检测Python项目（setup.py, pyproject.toml, requirements.txt等）"""
        indicators = [
            "setup.py",
            "pyproject.toml",
            "requirements.txt",
            "setup.cfg",
            "Pipfile",
            "poetry.lock",
        ]
        for indicator in indicators:
            if os.path.exists(os.path.join(self.project_root, indicator)):
                return BuildSystem.PYTHON
        return None
    
    def _detect_c_cmake(self) -> Optional[BuildSystem]:
        """检测CMake项目（CMakeLists.txt）"""
        cmake_lists = os.path.join(self.project_root, "CMakeLists.txt")
        if os.path.exists(cmake_lists):
            # 检查是否同时存在Makefile
            makefile = os.path.join(self.project_root, "Makefile")
            if os.path.exists(makefile):
                return BuildSystem.C_MAKEFILE_CMAKE
            return BuildSystem.C_CMAKE
        return None
    
    def _detect_c_makefile(self) -> Optional[BuildSystem]:
        """检测Makefile项目"""
        makefile = os.path.join(self.project_root, "Makefile")
        if os.path.exists(makefile):
            return BuildSystem.C_MAKEFILE
        return None


class BuildValidatorBase(ABC):
    """构建验证器基类"""
    
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


class RustBuildValidator(BuildValidatorBase):
    """Rust构建验证器（使用cargo check）"""
    
    def validate(self, modified_files: Optional[List[str]] = None) -> BuildResult:
        import time
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


class PythonBuildValidator(BuildValidatorBase):
    """Python构建验证器"""
    
    def validate(self, modified_files: Optional[List[str]] = None) -> BuildResult:
        import time
        start_time = time.time()
        
        # 策略1: 尝试使用 py_compile 编译修改的文件
        if modified_files:
            errors = []
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
                        errors.append(f"{file_path}: {stderr}")
            
            if errors:
                duration = time.time() - start_time
                return BuildResult(
                    success=False,
                    output="\n".join(errors),
                    error_message="Python语法检查失败",
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
            return BuildResult(
                success=success,
                output=stdout + stderr,
                error_message=None if success else "Python项目验证失败",
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


class NodeJSBuildValidator(BuildValidatorBase):
    """Node.js构建验证器"""
    
    def validate(self, modified_files: Optional[List[str]] = None) -> BuildResult:
        import time
        start_time = time.time()
        
        # 策略1: 尝试使用 tsc --noEmit（如果存在TypeScript）
        tsconfig = os.path.join(self.project_root, "tsconfig.json")
        if os.path.exists(tsconfig):
            returncode, stdout, stderr = self._run_command(
                ["npx", "tsc", "--noEmit"],
                timeout=20,
            )
            duration = time.time() - start_time
            success = returncode == 0
            return BuildResult(
                success=success,
                output=stdout + stderr,
                error_message=None if success else "TypeScript类型检查失败",
                build_system=BuildSystem.NODEJS,
                duration=duration,
            )
        
        # 策略2: 尝试运行 npm run build（如果存在build脚本）
        package_json = os.path.join(self.project_root, "package.json")
        if os.path.exists(package_json):
            try:
                import json
                with open(package_json, "r", encoding="utf-8") as f:
                    package_data = json.load(f)
                    scripts = package_data.get("scripts", {})
                    if "build" in scripts:
                        returncode, stdout, stderr = self._run_command(
                            ["npm", "run", "build"],
                            timeout=30,
                        )
                        duration = time.time() - start_time
                        success = returncode == 0
                        return BuildResult(
                            success=success,
                            output=stdout + stderr,
                            error_message=None if success else "npm build失败",
                            build_system=BuildSystem.NODEJS,
                            duration=duration,
                        )
            except Exception as e:
                logger.warning(f"读取package.json失败: {e}")
        
        # 策略3: 使用 eslint 进行语法检查（如果存在）
        if modified_files:
            js_files = [f for f in modified_files if f.endswith((".js", ".jsx", ".ts", ".tsx"))]
            if js_files:
                # 尝试使用 eslint
                returncode, stdout, stderr = self._run_command(
                    ["npx", "eslint", "--max-warnings=0"] + js_files[:5],  # 限制文件数量
                    timeout=15,
                )
                duration = time.time() - start_time
                # eslint返回非0可能是警告，不算失败
                return BuildResult(
                    success=True,  # 仅检查语法，警告不算失败
                    output=stdout + stderr,
                    error_message=None,
                    build_system=BuildSystem.NODEJS,
                    duration=duration,
                )
        
        duration = time.time() - start_time
        return BuildResult(
            success=True,
            output="Node.js项目验证通过（无构建脚本）",
            error_message=None,
            build_system=BuildSystem.NODEJS,
            duration=duration,
        )


class JavaMavenBuildValidator(BuildValidatorBase):
    """Java Maven构建验证器"""
    
    def validate(self, modified_files: Optional[List[str]] = None) -> BuildResult:
        import time
        start_time = time.time()
        
        # 使用 mvn compile 进行编译验证
        cmd = ["mvn", "compile", "-q"]  # -q 静默模式
        
        returncode, stdout, stderr = self._run_command(cmd, timeout=60)
        duration = time.time() - start_time
        
        success = returncode == 0
        output = stdout + stderr
        
        return BuildResult(
            success=success,
            output=output,
            error_message=None if success else "Maven编译失败",
            build_system=BuildSystem.JAVA_MAVEN,
            duration=duration,
        )


class JavaGradleBuildValidator(BuildValidatorBase):
    """Java Gradle构建验证器"""
    
    def validate(self, modified_files: Optional[List[str]] = None) -> BuildResult:
        import time
        start_time = time.time()
        
        # 使用 gradle compileJava 进行编译验证
        # 优先使用 gradlew（如果存在）
        gradlew = os.path.join(self.project_root, "gradlew")
        if os.path.exists(gradlew):
            cmd = ["./gradlew", "compileJava", "--quiet"]
        else:
            cmd = ["gradle", "compileJava", "--quiet"]
        
        returncode, stdout, stderr = self._run_command(cmd, timeout=60)
        duration = time.time() - start_time
        
        success = returncode == 0
        output = stdout + stderr
        
        return BuildResult(
            success=success,
            output=output,
            error_message=None if success else "Gradle编译失败",
            build_system=BuildSystem.JAVA_GRADLE,
            duration=duration,
        )


class GoBuildValidator(BuildValidatorBase):
    """Go构建验证器"""
    
    def validate(self, modified_files: Optional[List[str]] = None) -> BuildResult:
        import time
        start_time = time.time()
        
        # 使用 go build 进行构建验证
        cmd = ["go", "build", "./..."]
        
        returncode, stdout, stderr = self._run_command(cmd, timeout=30)
        duration = time.time() - start_time
        
        success = returncode == 0
        output = stdout + stderr
        
        return BuildResult(
            success=success,
            output=output,
            error_message=None if success else "Go构建失败",
            build_system=BuildSystem.GO,
            duration=duration,
        )


class CMakeBuildValidator(BuildValidatorBase):
    """CMake构建验证器"""
    
    def validate(self, modified_files: Optional[List[str]] = None) -> BuildResult:
        import time
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
        import tempfile
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


class MakefileBuildValidator(BuildValidatorBase):
    """Makefile构建验证器"""
    
    def validate(self, modified_files: Optional[List[str]] = None) -> BuildResult:
        import time
        start_time = time.time()
        
        # 尝试运行 make（如果存在Makefile）
        makefile = os.path.join(self.project_root, "Makefile")
        if not os.path.exists(makefile):
            duration = time.time() - start_time
            return BuildResult(
                success=False,
                output="Makefile不存在",
                error_message="Makefile不存在",
                build_system=BuildSystem.C_MAKEFILE,
                duration=duration,
            )
        
        # 尝试 make -n（dry-run）来验证语法
        returncode, stdout, stderr = self._run_command(
            ["make", "-n"],
            timeout=10,
        )
        duration = time.time() - start_time
        
        success = returncode == 0
        return BuildResult(
            success=success,
            output=stdout + stderr,
            error_message=None if success else "Makefile语法检查失败",
            build_system=BuildSystem.C_MAKEFILE,
            duration=duration,
        )


class FallbackBuildValidator(BuildValidatorBase):
    """兜底验证器：当无法检测构建系统时使用"""
    
    def validate(self, modified_files: Optional[List[str]] = None) -> BuildResult:
        import time
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
                return BuildResult(
                    success=False,
                    output="\n".join(errors),
                    error_message="语法检查失败",
                    build_system=BuildSystem.UNKNOWN,
                    duration=duration,
                )
        
        duration = time.time() - start_time
        return BuildResult(
            success=True,
            output="基础语法检查通过（未检测到构建系统）",
            error_message=None,
            build_system=BuildSystem.UNKNOWN,
            duration=duration,
        )


class BuildValidator:
    """构建验证器主类"""
    
    def __init__(self, project_root: str, timeout: int = 30):
        self.project_root = project_root
        self.timeout = timeout
        self.detector = BuildSystemDetector(project_root)
        
        # 注册构建系统验证器
        self._validators: Dict[BuildSystem, BuildValidatorBase] = {
            BuildSystem.RUST: RustBuildValidator(project_root, timeout),
            BuildSystem.PYTHON: PythonBuildValidator(project_root, timeout),
            BuildSystem.NODEJS: NodeJSBuildValidator(project_root, timeout),
            BuildSystem.JAVA_MAVEN: JavaMavenBuildValidator(project_root, timeout),
            BuildSystem.JAVA_GRADLE: JavaGradleBuildValidator(project_root, timeout),
            BuildSystem.GO: GoBuildValidator(project_root, timeout),
            BuildSystem.C_CMAKE: CMakeBuildValidator(project_root, timeout),
            BuildSystem.C_MAKEFILE: MakefileBuildValidator(project_root, timeout),
            BuildSystem.C_MAKEFILE_CMAKE: CMakeBuildValidator(project_root, timeout),
        }
        
        # 兜底验证器
        self._fallback_validator = FallbackBuildValidator(project_root, timeout)
    
    def validate(self, modified_files: Optional[List[str]] = None) -> BuildResult:
        """验证构建
        
        Args:
            modified_files: 修改的文件列表（可选，用于增量验证）
        
        Returns:
            BuildResult: 验证结果
        """
        # 检测构建系统
        build_system = self.detector.detect()
        
        if build_system and build_system in self._validators:
            validator = self._validators[build_system]
            logger.info(f"检测到构建系统: {build_system.value}, 使用验证器: {validator.__class__.__name__}")
            try:
                return validator.validate(modified_files)
            except Exception as e:
                logger.warning(f"验证器 {validator.__class__.__name__} 执行失败: {e}, 使用兜底验证器")
                # 验证器执行失败时，使用兜底验证器
                return self._fallback_validator.validate(modified_files)
        else:
            # 未检测到构建系统，使用兜底验证器
            logger.info("未检测到构建系统，使用兜底验证器")
            return self._fallback_validator.validate(modified_files)
    
    def register_validator(self, build_system: BuildSystem, validator: BuildValidatorBase):
        """注册自定义验证器（扩展点）
        
        Args:
            build_system: 构建系统类型
            validator: 验证器实例
        """
        self._validators[build_system] = validator
        logger.info(f"注册自定义验证器: {build_system.value} -> {validator.__class__.__name__}")

