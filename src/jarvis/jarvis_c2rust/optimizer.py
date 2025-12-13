# -*- coding: utf-8 -*-
"""
Rust 代码优化器：对转译或生成后的 Rust 项目执行若干保守优化步骤。

所有优化步骤均使用 CodeAgent 完成，确保智能、准确且可回退。

目标与策略（保守、可回退）:
1) unsafe 清理：
   - 使用 CodeAgent 识别可移除的 `unsafe { ... }` 包裹，移除后执行 `cargo test` 验证
   - 若必须保留 unsafe，缩小范围并在紧邻位置添加 `/// SAFETY: ...` 文档注释说明理由
2) 可见性优化（尽可能最小可见性）：
   - 使用 CodeAgent 将 `pub fn` 降为 `pub(crate) fn`（如果函数仅在 crate 内部使用）
   - 保持对外接口（跨 crate 使用的接口，如 lib.rs 中的顶层导出）为 `pub`
3) 文档补充：
   - 使用 CodeAgent 为缺少模块级文档的文件添加 `//! ...` 模块文档注释
   - 为缺少函数文档的公共函数添加 `/// ...` 文档注释（可以是占位注释或简要说明）

实现说明：
- 所有优化步骤均通过 CodeAgent 完成，每个步骤后执行 `cargo test` 进行验证
- 若验证失败，进入构建修复循环（使用 CodeAgent 进行最小修复），直到通过或达到重试上限
- 所有修改保留最小必要的文本变动，失败时自动回滚到快照（git_guard 启用时）
- 结果摘要与日志输出到 <crate_dir>/.jarvis/c2rust/optimize_report.json
- 进度记录（断点续跑）：<crate_dir>/.jarvis/c2rust/optimize_progress.json
  - 字段 processed: 已优化完成的文件（相对 crate 根的路径，posix 斜杠）

限制：
- 依赖 CodeAgent 的智能分析能力，复杂语法与宏、条件编译等情况由 CodeAgent 处理
- 所有优化步骤均通过 `cargo test` 验证，确保修改后代码可正常编译和运行
- 提供 Git 保护（git_guard），失败时自动回滚到快照

使用入口：
- optimize_project(project_root: Optional[Path], crate_dir: Optional[Path], ...) 作为对外简单入口
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional

import typer

from jarvis.jarvis_c2rust.optimizer_build_fix import BuildFixOptimizer
from jarvis.jarvis_c2rust.optimizer_clippy import ClippyOptimizer
from jarvis.jarvis_c2rust.optimizer_config import (
    append_additional_notes as append_notes,
)
from jarvis.jarvis_c2rust.optimizer_config import load_additional_notes
from jarvis.jarvis_c2rust.optimizer_docs import DocsOptimizer

# 导入拆分后的模块
from jarvis.jarvis_c2rust.optimizer_options import OptimizeOptions
from jarvis.jarvis_c2rust.optimizer_options import OptimizeStats
from jarvis.jarvis_c2rust.optimizer_progress import ProgressManager
from jarvis.jarvis_c2rust.optimizer_report import get_report_display_path
from jarvis.jarvis_c2rust.optimizer_report import write_final_report
from jarvis.jarvis_c2rust.optimizer_unsafe import UnsafeOptimizer
from jarvis.jarvis_c2rust.optimizer_utils import compute_target_files
from jarvis.jarvis_c2rust.optimizer_utils import detect_crate_dir
from jarvis.jarvis_c2rust.optimizer_utils import ensure_report_dir
from jarvis.jarvis_c2rust.optimizer_utils import find_project_root
from jarvis.jarvis_c2rust.optimizer_utils import iter_rust_files
from jarvis.jarvis_c2rust.optimizer_visibility import VisibilityOptimizer

# 工具函数已迁移到 optimizer_utils.py


class Optimizer:
    def __init__(
        self,
        crate_dir: Path,
        options: OptimizeOptions,
        project_root: Optional[Path] = None,
    ):
        self.crate_dir = crate_dir
        self.project_root = (
            project_root if project_root else crate_dir.parent
        )  # 默认使用 crate_dir 的父目录
        self.options = options
        self.stats = OptimizeStats()
        # 进度文件
        self.report_dir = ensure_report_dir(self.crate_dir)
        self.progress_path = self.report_dir / "optimize_progress.json"
        self._target_files: List[Path] = []

        # 初始化进度管理器
        self.progress_manager = ProgressManager(
            self.crate_dir, self.options, self.progress_path
        )
        self.progress_manager.load_or_reset_progress()

        # 读取附加说明
        self.additional_notes = load_additional_notes(self.crate_dir)

        # 初始化各个优化器模块
        self.build_fix_optimizer = BuildFixOptimizer(
            self.crate_dir,
            self.options,
            self.stats,
            self.progress_manager,
            lambda p: append_notes(p, self.additional_notes),
        )

        self.clippy_optimizer = ClippyOptimizer(
            self.crate_dir,
            self.options,
            self.stats,
            self.progress_manager,
            lambda p: append_notes(p, self.additional_notes),
            self.build_fix_optimizer.verify_and_fix_after_step,
        )

        self.unsafe_optimizer = UnsafeOptimizer(
            self.crate_dir,
            self.options,
            self.stats,
            self.progress_manager,
            lambda p: append_notes(p, self.additional_notes),
            self.clippy_optimizer.extract_warnings_by_file,
            self.clippy_optimizer.format_warnings_for_prompt,
        )

        self.visibility_optimizer = VisibilityOptimizer(
            self.crate_dir,
            self.options,
            self.stats,
            self.progress_manager,
            lambda p: append_notes(p, self.additional_notes),
        )

        self.docs_optimizer = DocsOptimizer(
            self.crate_dir,
            self.options,
            self.stats,
            self.progress_manager,
            lambda p: append_notes(p, self.additional_notes),
        )

    # 配置加载相关方法已迁移到 optimizer_config.py
    # Git 快照相关方法已迁移到 ProgressManager
    # 文件选择相关方法已迁移到 optimizer_utils.py
    # 报告相关方法已迁移到 optimizer_report.py
    # 验证和修复相关方法已迁移到 BuildFixOptimizer

    def _run_optimization_step(
        self,
        step_name: str,
        step_display_name: str,
        step_num: int,
        target_files: List[Path],
        opt_func,
    ) -> Optional[int]:
        """
        执行单个优化步骤（unsafe_cleanup, visibility_opt, doc_opt）。

        Args:
            step_name: 步骤名称（用于进度保存和错误消息）
            step_display_name: 步骤显示名称（用于日志）
            step_num: 步骤编号
            target_files: 目标文件列表
            opt_func: 优化函数（接受 target_files 作为参数）

        Returns:
            下一个步骤编号，如果失败则返回 None
        """
        typer.secho(
            f"\n[c2rust-optimizer] 第 {step_num} 步：{step_display_name}",
            fg=typer.colors.MAGENTA,
        )
        self.progress_manager.snapshot_commit()
        if not self.options.dry_run:
            opt_func(target_files)
            if not self.build_fix_optimizer.verify_and_fix_after_step(
                step_name, target_files
            ):
                # 验证失败，已回滚，返回 None 表示失败
                return None
            # 保存步骤进度
            self.progress_manager.save_step_progress(step_name, target_files)
        return step_num + 1

    # Clippy 相关方法已迁移到 ClippyOptimizer

    def run(self) -> OptimizeStats:
        """
        执行优化流程的主入口。

        Returns:
            优化统计信息
        """
        report_path = self.report_dir / "optimize_report.json"
        typer.secho(
            f"[c2rust-optimizer][start] 开始优化 Crate: {self.crate_dir}",
            fg=typer.colors.BLUE,
        )
        try:
            # 批次开始前记录快照
            self.progress_manager.snapshot_commit()

            # ========== 第 0 步：Clippy 告警修复（必须第一步，且必须完成） ==========
            # 注意：clippy 告警修复不依赖于是否有新文件需要处理，即使所有文件都已处理，也应该检查并修复告警
            if not self.clippy_optimizer.run_clippy_elimination_step():
                # Clippy 告警修复未完成，停止后续步骤
                return self.stats

            # ========== 后续优化步骤（只有在 clippy 告警修复完成后才执行） ==========
            # 计算本次批次的目标文件列表（按 include/exclude/resume/max_files）
            targets = compute_target_files(
                self.crate_dir, self.options, self.progress_manager.processed
            )
            self._target_files = targets

            # 检查是否有未完成的步骤需要执行
            has_pending_steps = False
            if (
                self.options.enable_unsafe_cleanup
                and "unsafe_cleanup" not in self.progress_manager.steps_completed
            ):
                has_pending_steps = True
            if (
                self.options.enable_visibility_opt
                and "visibility_opt" not in self.progress_manager.steps_completed
            ):
                has_pending_steps = True
            if (
                self.options.enable_doc_opt
                and "doc_opt" not in self.progress_manager.steps_completed
            ):
                has_pending_steps = True

            # 如果没有新文件但有未完成的步骤，使用所有 Rust 文件作为目标
            if not targets and has_pending_steps:
                typer.secho(
                    "[c2rust-optimizer] 无新文件需要处理，但检测到未完成的步骤，使用所有 Rust 文件作为目标。",
                    fg=typer.colors.CYAN,
                )
                targets = list(iter_rust_files(self.crate_dir))

            if not targets:
                typer.secho(
                    "[c2rust-optimizer] 根据当前选项，无新文件需要处理，且所有步骤均已完成。",
                    fg=typer.colors.CYAN,
                )
            else:
                typer.secho(
                    f"[c2rust-optimizer] 本次批次发现 {len(targets)} 个待处理文件。",
                    fg=typer.colors.BLUE,
                )

                # 所有优化步骤都使用 CodeAgent
                step_num = 1

                if self.options.enable_unsafe_cleanup:
                    result_step_num = self._run_optimization_step(
                        "unsafe_cleanup",
                        "unsafe 清理",
                        step_num,
                        targets,
                        self.unsafe_optimizer.codeagent_opt_unsafe_cleanup,
                    )
                    if result_step_num is None:  # 步骤失败，已回滚
                        return self.stats
                    step_num = result_step_num

                if self.options.enable_visibility_opt:
                    result_step_num = self._run_optimization_step(
                        "visibility_opt",
                        "可见性优化",
                        step_num,
                        targets,
                        self.visibility_optimizer.codeagent_opt_visibility,
                    )
                    if result_step_num is None:  # 步骤失败，已回滚
                        return self.stats
                    step_num = result_step_num

                if self.options.enable_doc_opt:
                    result_step_num = self._run_optimization_step(
                        "doc_opt",
                        "文档补充",
                        step_num,
                        targets,
                        self.docs_optimizer.codeagent_opt_docs,
                    )
                    if result_step_num is None:  # 步骤失败，已回滚
                        return self.stats
                    step_num = result_step_num

                # 最终保存进度（确保所有步骤的进度都已记录）
                self.progress_manager.save_progress_for_batch(targets)

        except Exception as e:
            if self.stats.errors is not None:
                self.stats.errors.append(f"fatal: {e}")
        finally:
            # 写出简要报告
            report_display = get_report_display_path(
                report_path, self.project_root, self.crate_dir
            )
            typer.secho(
                f"[c2rust-optimizer] 优化流程结束。报告已生成于: {report_display}",
                fg=typer.colors.GREEN,
            )
            write_final_report(report_path, self.stats)
        return self.stats

    # Clippy、Unsafe、Visibility、Docs 和 BuildFix 相关方法已迁移到各自的模块
    # 向后兼容方法已删除，请直接使用各模块中的对应方法


def optimize_project(
    project_root: Optional[Path] = None,
    crate_dir: Optional[Path] = None,
    enable_unsafe_cleanup: bool = True,
    enable_visibility_opt: bool = True,
    enable_doc_opt: bool = True,
    max_checks: int = 0,
    dry_run: bool = False,
    include_patterns: Optional[str] = None,
    exclude_patterns: Optional[str] = None,
    max_files: int = 0,
    resume: bool = True,
    reset_progress: bool = False,
    build_fix_retries: int = 3,
    git_guard: bool = True,
    llm_group: Optional[str] = None,
    cargo_test_timeout: int = 300,
    non_interactive: bool = True,
) -> Dict:
    """
    对指定 crate 执行优化。返回结果摘要 dict。
    - project_root: 原 C 项目根目录（包含 .jarvis/c2rust）；为 None 时自动检测
    - crate_dir: crate 根目录（包含 Cargo.toml）；为 None 时自动检测
    - enable_*: 各优化步骤开关
    - max_checks: 限制 cargo check 调用次数（0 不限）
    - dry_run: 不写回，仅统计潜在修改
    - include_patterns/exclude_patterns: 逗号分隔的 glob；相对 crate 根（如 src/**/*.rs）
    - max_files: 本次最多处理文件数（0 不限）
    - resume: 启用断点续跑（跳过已处理文件）
    - reset_progress: 清空进度（processed 列表）
    """
    # 如果 project_root 为 None，尝试从当前目录查找
    if project_root is None:
        project_root = find_project_root()
        if project_root is None:
            # 如果找不到项目根目录，使用当前目录
            project_root = Path(".").resolve()
    else:
        project_root = Path(project_root).resolve()

    # 如果 crate_dir 为 None，使用 detect_crate_dir 自动检测
    # detect_crate_dir 内部已经包含了从项目根目录推断的逻辑
    crate = detect_crate_dir(crate_dir)
    opts = OptimizeOptions(
        enable_unsafe_cleanup=enable_unsafe_cleanup,
        enable_visibility_opt=enable_visibility_opt,
        enable_doc_opt=enable_doc_opt,
        max_checks=max_checks,
        dry_run=dry_run,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        max_files=max_files,
        resume=resume,
        reset_progress=reset_progress,
        build_fix_retries=build_fix_retries,
        git_guard=git_guard,
        llm_group=llm_group,
        cargo_test_timeout=cargo_test_timeout,
        non_interactive=non_interactive,
    )
    optimizer = Optimizer(crate, opts, project_root=project_root)
    stats = optimizer.run()
    return asdict(stats)
