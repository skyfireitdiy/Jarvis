#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
构建验证器主模块

提供构建验证器的主类，负责协调各个语言的验证器。
"""

from typing import Dict, List, Optional

from jarvis.jarvis_utils.output import OutputType, PrettyOutput

from .base import BuildSystem, BuildValidatorBase, BuildResult
from .detector import BuildSystemDetector
from .rust import RustBuildValidator
from .python import PythonBuildValidator
from .nodejs import NodeJSBuildValidator
from .java_maven import JavaMavenBuildValidator
from .java_gradle import JavaGradleBuildValidator
from .go import GoBuildValidator
from .cmake import CMakeBuildValidator
from .makefile import MakefileBuildValidator
from .fallback import FallbackBuildValidator


class BuildValidator:
    """构建验证器主类"""
    
    def __init__(self, project_root: str, timeout: int = 30):
        self.project_root = project_root
        self.timeout = timeout
        self.detector = BuildSystemDetector(project_root)
        
        # 导入配置管理器
        from jarvis.jarvis_code_agent.build_validation_config import BuildValidationConfig
        self.config = BuildValidationConfig(project_root)
        
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
    
    def _select_build_system(self, detected_systems: List[BuildSystem]) -> Optional[BuildSystem]:
        """让用户选择构建系统
        
        Args:
            detected_systems: 检测到的所有构建系统列表
        
        Returns:
            用户选择的构建系统，如果用户取消则返回None
        """
        if not detected_systems:
            return None
        
        if len(detected_systems) == 1:
            # 只有一个构建系统，直接返回
            return detected_systems[0]
        
        # 检查配置文件中是否已有选择
        saved_system = self.config.get_selected_build_system()
        if saved_system:
            try:
                saved_enum = BuildSystem(saved_system)
                if saved_enum in detected_systems:
                    PrettyOutput.print(f"使用配置文件中保存的构建系统: {saved_system}", OutputType.INFO)
                    return saved_enum
            except ValueError:
                # 配置文件中保存的构建系统无效，忽略
                pass
        
        # 多个构建系统，需要用户选择
        print("\n检测到多个构建系统，请选择要使用的构建系统：")
        for idx, system in enumerate(detected_systems, start=1):
            print(f"  {idx}. {system.value}")
        print(f"  {len(detected_systems) + 1}. 取消（使用兜底验证器）")
        
        while True:
            try:
                choice = input(f"\n请选择 (1-{len(detected_systems) + 1}): ").strip()
                choice_num = int(choice)
                
                if 1 <= choice_num <= len(detected_systems):
                    selected = detected_systems[choice_num - 1]
                    # 保存用户选择
                    self.config.set_selected_build_system(selected.value)
                    PrettyOutput.print(f"用户选择构建系统: {selected.value}", OutputType.INFO)
                    return selected
                elif choice_num == len(detected_systems) + 1:
                    PrettyOutput.print("用户取消选择，使用兜底验证器", OutputType.INFO)
                    return None
                else:
                    print(f"无效选择，请输入 1-{len(detected_systems) + 1}")
            except ValueError:
                print("请输入有效的数字")
            except (KeyboardInterrupt, EOFError):
                print("\n用户取消，使用兜底验证器")
                return None
    
    def validate(self, modified_files: Optional[List[str]] = None) -> BuildResult:
        """验证构建
        
        Args:
            modified_files: 修改的文件列表（可选，用于增量验证）
        
        Returns:
            BuildResult: 验证结果
        """
        # 检测所有可能的构建系统
        detected_systems = self.detector.detect_all()
        
        if not detected_systems:
            # 未检测到构建系统，使用兜底验证器
            PrettyOutput.print("未检测到构建系统，使用兜底验证器", OutputType.INFO)
            return self._fallback_validator.validate(modified_files)
        
        # 让用户选择构建系统（如果多个）
        build_system = self._select_build_system(detected_systems)
        
        if build_system and build_system in self._validators:
            validator = self._validators[build_system]
            PrettyOutput.print(f"使用构建系统: {build_system.value}, 验证器: {validator.__class__.__name__}", OutputType.INFO)
            try:
                return validator.validate(modified_files)
            except Exception as e:
                PrettyOutput.print(f"验证器 {validator.__class__.__name__} 执行失败: {e}, 使用兜底验证器", OutputType.WARNING)
                # 验证器执行失败时，使用兜底验证器
                return self._fallback_validator.validate(modified_files)
        else:
            # 用户取消或未选择，使用兜底验证器
            PrettyOutput.print("使用兜底验证器", OutputType.INFO)
            return self._fallback_validator.validate(modified_files)
    
    def register_validator(self, build_system: BuildSystem, validator: BuildValidatorBase):
        """注册自定义验证器（扩展点）
        
        Args:
            build_system: 构建系统类型
            validator: 验证器实例
        """
        self._validators[build_system] = validator
        PrettyOutput.print(f"注册自定义验证器: {build_system.value} -> {validator.__class__.__name__}", OutputType.INFO)

