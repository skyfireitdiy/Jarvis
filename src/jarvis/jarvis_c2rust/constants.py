# -*- coding: utf-8 -*-
"""
C2Rust 转译器常量定义
"""

from typing import Set

# 数据文件常量
C2RUST_DIRNAME = ".jarvis/c2rust"

SYMBOLS_JSONL = "symbols.jsonl"
ORDER_JSONL = "translation_order.jsonl"
PROGRESS_JSON = "progress.json"
CONFIG_JSON = "config.json"
SYMBOL_MAP_JSONL = "symbol_map.jsonl"

# 配置常量
ERROR_SUMMARY_MAX_LENGTH = 2000  # 错误信息摘要最大长度
DEFAULT_PLAN_MAX_RETRIES = 0  # 规划阶段默认最大重试次数（0表示无限重试）
DEFAULT_REVIEW_MAX_ITERATIONS = 0  # 审查阶段最大迭代次数（0表示无限重试）
DEFAULT_CHECK_MAX_RETRIES = 0  # cargo check 阶段默认最大重试次数（0表示无限重试）
DEFAULT_TEST_MAX_RETRIES = 0  # cargo test 阶段默认最大重试次数（0表示无限重试）

# 回退与重试常量
CONSECUTIVE_FIX_FAILURE_THRESHOLD = 10  # 连续修复失败次数阈值，达到此值将触发回退
MAX_FUNCTION_RETRIES = 10  # 函数重新开始处理的最大次数
DEFAULT_PLAN_MAX_RETRIES_ENTRY = 5  # run_transpile 入口函数的 plan_max_retries 默认值

# 文件扩展名常量
SOURCE_EXTS: Set[str] = {
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".C",
    ".h",
    ".hh",
    ".hpp",
    ".hxx",
}
HEADER_EXTS = {".h", ".hh", ".hpp", ".hxx"}

# AST节点类型常量
TYPE_KINDS: Set[str] = {
    "STRUCT_DECL",
    "UNION_DECL",
    "ENUM_DECL",
    "CXX_RECORD_DECL",  # C++ class/struct/union
    "TYPEDEF_DECL",
    "TYPE_ALIAS_DECL",
}

# 运行状态文件
RUN_STATE_JSON = "run_state.json"

# Library Replacer 相关常量
# LLM评估重试配置
MAX_LLM_RETRIES = 3  # LLM评估最大重试次数

# 源码片段读取配置
DEFAULT_SOURCE_SNIPPET_MAX_LINES = 200  # 默认源码片段最大行数
SUBTREE_SOURCE_SNIPPET_MAX_LINES = 120  # 子树提示词中源码片段最大行数

# 子树提示词构建配置
MAX_SUBTREE_NODES_META = 200  # 子树节点元数据列表最大长度
MAX_SUBTREE_EDGES = 400  # 子树边列表最大长度
MAX_DOT_EDGES = 200  # DOT图边数阈值（超过此值不生成DOT）
MAX_CHILD_SAMPLES = 2  # 子节点采样数量
MAX_SOURCE_SAMPLES = 3  # 代表性源码样本最大数量（注释说明）

# 显示配置
MAX_NOTES_DISPLAY_LENGTH = 200  # 备注显示最大长度

# 输出文件路径配置
DEFAULT_SYMBOLS_OUTPUT = "symbols_library_pruned.jsonl"  # 默认符号表输出文件名
DEFAULT_MAPPING_OUTPUT = "library_replacements.jsonl"  # 默认替代映射输出文件名
SYMBOLS_PRUNE_OUTPUT = "symbols_prune.jsonl"  # 兼容符号表输出文件名
ORDER_PRUNE_OUTPUT = "translation_order_prune.jsonl"  # 剪枝阶段转译顺序输出文件名
ORDER_ALIAS_OUTPUT = "translation_order.jsonl"  # 通用转译顺序输出文件名
DEFAULT_CHECKPOINT_FILE = "library_replacer_checkpoint.json"  # 默认检查点文件名

# Checkpoint配置
DEFAULT_CHECKPOINT_INTERVAL = 1  # 默认检查点保存间隔（每评估N个节点保存一次）

# JSON格式化配置
JSON_INDENT = 2  # JSON格式化缩进空格数
