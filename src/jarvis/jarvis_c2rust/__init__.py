# -*- coding: utf-8 -*-
"""
Jarvis C2Rust 工具集。

数据产物（扫描后）:
- 统一符号表（JSONL）：<project_root>/.jarvis/c2rust/symbols.jsonl
- 原始符号表（JSONL）：<project_root>/.jarvis/c2rust/symbols_raw.jsonl
- 元数据（JSON）：<project_root>/.jarvis/c2rust/meta.json

推荐用法（CLI）:
  jarvis-c2rust scan

或（模块方式）:
  python -m jarvis.jarvis_c2rust.cli scan
"""

__all__ = ["scanner"]