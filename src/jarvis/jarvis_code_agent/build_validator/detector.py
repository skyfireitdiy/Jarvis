#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
构建系统检测器模块

提供构建系统自动检测功能。
"""

import os
from typing import List, Optional

from .base import BuildSystem


class BuildSystemDetector:
    """构建系统检测器"""
    
    def __init__(self, project_root: str):
        self.project_root = project_root
    
    def detect(self) -> Optional[BuildSystem]:
        """检测项目使用的构建系统（兼容旧接口，返回第一个检测到的）
        
        Returns:
            检测到的构建系统，如果无法检测则返回None
        """
        all_systems = self.detect_all()
        return all_systems[0] if all_systems else None
    
    def detect_all(self) -> List[BuildSystem]:
        """检测所有可能的构建系统
        
        Returns:
            检测到的所有构建系统列表（按优先级排序）
        """
        detected = []
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
            if result and result not in detected:
                detected.append(result)
        
        return detected
    
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

