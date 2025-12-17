# -*- coding: utf-8 -*-
"""优化器选项和统计数据结构。"""

from dataclasses import dataclass
from typing import List
from typing import Optional


@dataclass
class OptimizeOptions:
    """优化器选项配置。"""

    enable_unsafe_cleanup: bool = True
    enable_visibility_opt: bool = True
    enable_doc_opt: bool = True
    max_checks: int = 0  # 0 表示不限；用于限制 cargo check 次数（防止过慢）
    dry_run: bool = False
    # 大项目分批优化控制
    include_patterns: Optional[str] = (
        None  # 逗号分隔的 glob，相对 crate 根（支持 src/**.rs）
    )
    exclude_patterns: Optional[str] = None  # 逗号分隔的 glob
    max_files: int = 0  # 本次最多处理的文件数（0 不限）
    resume: bool = True  # 断点续跑：跳过已处理文件
    reset_progress: bool = False  # 重置进度（清空 processed 列表）
    build_fix_retries: int = 3  # 构建失败时的修复重试次数
    # Git 保护：优化前快照 commit，失败时自动 reset 回快照
    git_guard: bool = True
    llm_group: Optional[str] = None
    cargo_test_timeout: int = 300  # cargo test 超时（秒）
    non_interactive: bool = True


@dataclass
class OptimizeStats:
    """优化统计信息。"""

    files_scanned: int = 0
    unsafe_removed: int = 0
    unsafe_annotated: int = 0
    visibility_downgraded: int = 0
    docs_added: int = 0
    cargo_checks: int = 0
    errors: Optional[List[str]] = None

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []
