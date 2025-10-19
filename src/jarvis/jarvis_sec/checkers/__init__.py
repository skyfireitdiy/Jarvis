# -*- coding: utf-8 -*-
"""
OpenHarmony 安全演进多Agent套件 —— Checkers 包初始化

说明：
- 统一导出 C/C++ 与 Rust 启发式检查器的对外接口，便于上层工作流按需调用。
- 保持最小依赖，不在此处执行任何扫描逻辑，仅做导入与别名暴露。
"""

from typing import Iterable, List
from pathlib import Path

from .c_checker import (
    analyze_files as analyze_c_files,
    analyze_c_cpp_file,
    analyze_c_cpp_text,
)
from .rust_checker import (
    analyze_files as analyze_rust_files,
    analyze_rust_file,
    analyze_rust_text,
)

__all__ = [
    # C/C++
    "analyze_c_files",
    "analyze_c_cpp_file",
    "analyze_c_cpp_text",
    # Rust
    "analyze_rust_files",
    "analyze_rust_file",
    "analyze_rust_text",
]