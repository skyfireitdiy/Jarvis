# -*- coding: utf-8 -*-
"""
Jarvis C2Rust 工具集。

核心数据:
- 统一符号表（JSONL）：<project_root>/.jarvis/c2rust/symbols.jsonl（后续流程的主输入）
- 原始符号表（JSONL）：<project_root>/.jarvis/c2rust/symbols_raw.jsonl
- 其他产物：translation_order.jsonl、library_replacements.jsonl、progress.json、config.json、symbol_map.jsonl 等

推荐用法（CLI）:
  - 配置管理:       jarvis-c2rust config --files <hdrs...> [--root-list-syms ...] [--disabled-libs ...]
  - 扫描:           jarvis-c2rust scan
  - 库替代评估:     jarvis-c2rust lib-replace [-g <llm-group>]
  - 规划/落盘:      jarvis-c2rust prepare [-g <llm-group>]
  - 转译:           jarvis-c2rust transpile [-g <llm-group>] [-m <max-retries>]（断点续跑默认始终启用）
  - 代码优化:       jarvis-c2rust optimize [--crate-dir ...] [--unsafe/--no-unsafe] [--structure/--no-structure] [--visibility/--no-visibility] [--doc/--no-doc] [-m N] [--dry-run]
  - 一键流水线:     jarvis-c2rust run [-g <llm-group>] [-m <max-retries>]

或（模块方式）:
  python -m jarvis.jarvis_c2rust.cli <subcommand>

说明:
- 所有路径均推荐使用 <project_root>/.jarvis/c2rust 下的标准文件名，便于断点续跑与复用。
"""

__all__ = ["scanner", "optimizer"]
