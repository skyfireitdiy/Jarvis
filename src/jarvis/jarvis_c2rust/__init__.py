# -*- coding: utf-8 -*-
"""
Jarvis C2Rust 工具集。

模块:
- scanner: C/C++ 函数扫描器和调用图提取器，将结果存储在
           <scan_root>/.jarvis/c2rust/functions.jsonl 和 types.jsonl 的 JSONL 文件中。

用法:
  python -m jarvis.jarvis_c2rust.scanner --root /path/to/src
"""

__all__ = ["scanner"]