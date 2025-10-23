# -*- coding: utf-8 -*-
"""
Jarvis C2Rust utilities.

Modules:
- scanner: C/C++ function scanner and call graph extractor that stores results
           into JSONL at <scan_root>/.jarvis/c2rust/functions.jsonl and types.jsonl.

Usage:
  python -m jarvis.jarvis_c2rust.scanner --root /path/to/src
"""

__all__ = ["scanner"]