# -*- coding: utf-8 -*-
"""
C2Rust 转译器常量定义
"""

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

