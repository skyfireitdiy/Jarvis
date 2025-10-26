# -*- coding: utf-8 -*-
"""
Jarvis C2Rust 工具集。

核心数据:
- 统一符号表（JSONL）：<project_root>/.jarvis/c2rust/symbols.jsonl（后续流程的主输入）
- 原始符号表（JSONL）：<project_root>/.jarvis/c2rust/symbols_raw.jsonl
- 其他产物：translation_order.jsonl、library_replacements.jsonl、progress.json、symbol_map.jsonl 等

推荐用法（CLI）:
  - 扫描:           jarvis-c2rust scan
  - 库替代评估:     jarvis-c2rust lib-replace --root-list-file roots.txt [--disabled-libs ...]
  - 规划/落盘:      jarvis-c2rust prepare [-g <llm-group>]
  - 转译:           jarvis-c2rust transpile [-g <llm-group>] [--only ...] [--max-retries N] [--resume/--no-resume]
  - 头文件收集:     jarvis-c2rust collect <hdrs...> -o roots.txt
  - 一键流水线:     jarvis-c2rust run [--files <hdrs...> -o roots.txt | --root-list-syms ...] [-g <llm-group>] [--disabled-libs ...]

或（模块方式）:
  python -m jarvis.jarvis_c2rust.cli <subcommand>

说明:
- 所有路径均推荐使用 <project_root>/.jarvis/c2rust 下的标准文件名，便于断点续跑与复用。
"""

__all__ = ["scanner"]