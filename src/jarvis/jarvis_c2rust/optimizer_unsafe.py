# -*- coding: utf-8 -*-
"""Unsafe 清理优化模块。"""

import os
from pathlib import Path
from typing import Callable
from typing import Dict
from typing import List

from jarvis.jarvis_utils.output import PrettyOutput

from jarvis.jarvis_agent.events import AFTER_TOOL_CALL
from jarvis.jarvis_agent.events import BEFORE_TOOL_CALL
from jarvis.jarvis_c2rust.optimizer_options import OptimizeOptions
from jarvis.jarvis_c2rust.optimizer_options import OptimizeStats
from jarvis.jarvis_c2rust.optimizer_progress import ProgressManager
from jarvis.jarvis_c2rust.optimizer_utils import cargo_check_full
from jarvis.jarvis_c2rust.optimizer_utils import check_missing_safety_doc_warnings
from jarvis.jarvis_c2rust.optimizer_utils import run_cargo_fmt
from jarvis.jarvis_code_agent.code_agent import CodeAgent


class UnsafeOptimizer:
    """Unsafe 清理优化器。"""

    def __init__(
        self,
        crate_dir: Path,
        options: OptimizeOptions,
        stats: OptimizeStats,
        progress_manager: ProgressManager,
        append_additional_notes_func: Callable[[str], str],
        extract_warnings_by_file_func: Callable[[str], Dict[str, List[Dict]]],
        format_warnings_for_prompt_func: Callable[[List[Dict], int], str],
    ):
        self.crate_dir = crate_dir
        self.options = options
        self.stats = stats
        self.progress_manager = progress_manager
        self.append_additional_notes = append_additional_notes_func
        self.extract_warnings_by_file = extract_warnings_by_file_func
        self.format_warnings_for_prompt = format_warnings_for_prompt_func

    def codeagent_opt_unsafe_cleanup(self, target_files: List[Path]) -> None:
        """
        使用 CodeAgent 进行 unsafe 清理优化。
        使用 clippy 的 missing_safety_doc checker 来查找 unsafe 告警，按文件处理，每次处理一个文件的所有告警。

        注意：CodeAgent 必须在 crate 目录下创建和执行，以确保所有文件操作和命令执行都在正确的上下文中进行。
        """
        crate = self.crate_dir.resolve()
        file_list: List[str] = []
        for p in target_files:
            try:
                rel = p.resolve().relative_to(crate).as_posix()
            except Exception:
                rel = p.as_posix()
            file_list.append(rel)
            self.stats.files_scanned += 1

        # 切换到 crate 目录，确保 CodeAgent 在正确的上下文中创建和执行
        prev_cwd = os.getcwd()
        iteration = 0

        try:
            os.chdir(str(crate))

            # 循环修复 unsafe 告警，按文件处理
            while True:
                iteration += 1

                # 检查当前 missing_safety_doc 告警
                has_warnings, current_clippy_output = check_missing_safety_doc_warnings(
                    crate
                )
                if not has_warnings:
                    PrettyOutput.auto_print(
                        f"[c2rust-optimizer][codeagent][unsafe-cleanup] 所有 missing_safety_doc 告警已消除（共迭代 {iteration - 1} 次）"
                    )
                    return  # 所有告警已消除

                # 按文件提取告警
                warnings_by_file = self.extract_warnings_by_file(current_clippy_output)
                if not warnings_by_file:
                    PrettyOutput.auto_print(
                        "[c2rust-optimizer][codeagent][unsafe-cleanup] 无法提取告警，停止修复"
                    )
                    return  # 仍有告警未消除

                # 找到第一个有告警的文件（优先处理目标文件列表中的文件）
                target_file_path = None
                target_warnings = None

                # 优先处理目标文件列表中的文件
                for file_rel in file_list:
                    # 尝试匹配文件路径（可能是相对路径或绝对路径）
                    for file_path, warnings in warnings_by_file.items():
                        if file_rel in file_path or file_path.endswith(file_rel):
                            target_file_path = file_path
                            target_warnings = warnings
                            break
                    if target_file_path:
                        break

                # 如果目标文件列表中没有告警，选择第一个有告警的文件
                if not target_file_path:
                    target_file_path = next(iter(warnings_by_file.keys()))
                    target_warnings = warnings_by_file[target_file_path]

                # 获取该文件的所有告警（一次处理一个文件的所有告警）
                warnings_to_fix = target_warnings
                warning_count = (
                    len(warnings_to_fix) if warnings_to_fix is not None else 0
                )

                PrettyOutput.auto_print(
                    f"[c2rust-optimizer][codeagent][unsafe-cleanup] 第 {iteration} 次迭代：修复文件 {target_file_path} 的 {warning_count} 个 missing_safety_doc 告警"
                )

                # 格式化告警信息
                formatted_warnings = self.format_warnings_for_prompt(
                    warnings_to_fix or [], warning_count
                )

                # 构建提示词，修复该文件的所有 missing_safety_doc 告警
                prompt_lines: List[str] = [
                    "你是资深 Rust 代码工程师。请在当前 crate 下修复指定文件中的 missing_safety_doc 告警，并以补丁形式输出修改：",
                    f"- crate 根目录：{crate}",
                    "",
                    "本次优化仅允许修改以下文件（严格限制，只处理这一个文件）：",
                    f"- {target_file_path}",
                    "",
                    f"重要：本次修复仅修复该文件中的 {warning_count} 个 missing_safety_doc 告警。",
                    "",
                    "优化目标：",
                    f"1) 修复文件 {target_file_path} 中的 {warning_count} 个 missing_safety_doc 告警：",
                    "   **修复原则：能消除就消除，不能消除才增加 SAFETY 注释**",
                    "",
                    "   优先级 1（优先尝试）：消除 unsafe",
                    "   - 如果 unsafe 函数或方法实际上不需要是 unsafe 的，应该移除 unsafe 关键字；",
                    "   - 如果 unsafe 块可以移除，应该移除整个 unsafe 块；",
                    "   - 如果 unsafe 块可以缩小范围，应该缩小范围；",
                    "   - 仔细分析代码，判断是否真的需要 unsafe，如果可以通过安全的方式实现，优先使用安全的方式。",
                    "",
                    "   优先级 2（无法消除时）：添加 SAFETY 注释",
                    "   - 只有在确认无法消除 unsafe 的情况下，才为 unsafe 函数或方法添加 `/// SAFETY: ...` 文档注释；",
                    "   - SAFETY 注释必须详细说明为什么该函数或方法是 unsafe 的，包括：",
                    "     * 哪些不变量必须由调用者维护；",
                    "     * 哪些前提条件必须满足；",
                    "     * 可能导致未定义行为的情况；",
                    "     * 为什么不能使用安全的替代方案；",
                    "   - 如果 unsafe 块无法移除但可以缩小范围，应该缩小范围并在紧邻位置添加 `/// SAFETY: ...` 注释。",
                    "",
                    "2) 修复已有实现的问题：",
                    "   - 如果在修复 missing_safety_doc 告警的过程中，发现代码已有的实现有问题（如逻辑错误、潜在 bug、性能问题、内存安全问题等），也需要一并修复；",
                    "   - 这些问题可能包括但不限于：不正确的 unsafe 使用、未检查的边界条件、资源泄漏、竞态条件、数据竞争等；",
                    "   - 修复时应该保持最小改动原则，优先修复最严重的问题。",
                    "",
                    "约束与范围：",
                    f"- **仅修改文件 {target_file_path}，不要修改其他文件**；除非必须（如修复引用路径），否则不要修改其他文件。",
                    "- 保持最小改动，不要进行与修复 missing_safety_doc 告警无关的重构或格式化。",
                    f"- **只修复该文件中的 {warning_count} 个 missing_safety_doc 告警，不要修复其他告警**。",
                    "- 修改后需保证 `cargo test` 可以通过；如需引入少量配套改动，请一并包含在补丁中以确保通过。",
                    "- 输出仅为补丁，不要输出解释或多余文本。",
                    "",
                    "优先级说明：",
                    "- **修复 unsafe 的优先级：能消除就消除，不能消除才增加 SAFETY 注释**；",
                    "- 对于每个 unsafe，首先尝试分析是否可以安全地移除，只有在确认无法移除时才添加 SAFETY 注释；",
                    "- **如果优化过程中出现了测试不通过或编译错误，必须优先解决这些问题**；",
                    "- 在修复告警之前，先确保代码能够正常编译和通过测试；",
                    "- 如果修复告警导致了编译错误或测试失败，必须立即修复这些错误，然后再继续优化。",
                    "",
                    "自检要求：在每次输出补丁后，请使用 execute_script 工具在 crate 根目录执行 `cargo test -q` 进行验证；",
                    "若出现编译错误或测试失败，请优先修复这些问题，然后再继续修复告警；",
                    "若未通过，请继续输出新的补丁进行最小修复并再次自检，直至 `cargo test` 通过为止。",
                    "",
                    f"文件 {target_file_path} 中的 missing_safety_doc 告警信息如下：",
                    "<WARNINGS>",
                    formatted_warnings,
                    "</WARNINGS>",
                ]
                prompt = "\n".join(prompt_lines)
                prompt = self.append_additional_notes(prompt)

                # 修复前执行 cargo fmt
                run_cargo_fmt(crate)

                # 记录运行前的 commit id
                commit_before = self.progress_manager.get_crate_commit_hash()

                # CodeAgent 在 crate 目录下创建和执行
                agent = CodeAgent(
                    name=f"UnsafeCleanupAgent-iter{iteration}",
                    need_summary=False,
                    non_interactive=self.options.non_interactive,
                    model_group=self.options.llm_group,
                    enable_task_list_manager=False,
                    disable_review=True,
                )
                # 订阅 BEFORE_TOOL_CALL 和 AFTER_TOOL_CALL 事件，用于细粒度检测测试代码删除
                agent.event_bus.subscribe(
                    BEFORE_TOOL_CALL, self.progress_manager.on_before_tool_call
                )
                agent.event_bus.subscribe(
                    AFTER_TOOL_CALL, self.progress_manager.on_after_tool_call
                )
                # 记录 Agent 创建时的 commit id（作为初始值）
                agent_id = id(agent)
                agent_key = f"agent_{agent_id}"
                initial_commit = self.progress_manager.get_crate_commit_hash()
                if initial_commit:
                    self.progress_manager._agent_before_commits[agent_key] = (
                        initial_commit
                    )
                agent.run(
                    prompt,
                    prefix=f"[c2rust-optimizer][codeagent][unsafe-cleanup][iter{iteration}]",
                    suffix="",
                )

                # 检测并处理测试代码删除
                if self.progress_manager.check_and_handle_test_deletion(
                    commit_before, agent
                ):
                    # 如果回退了，需要重新运行 agent
                    PrettyOutput.auto_print(
                        f"[c2rust-optimizer][codeagent][unsafe-cleanup] 检测到测试代码删除问题，已回退，重新运行 agent (iter={iteration})"
                    )
                    commit_before = self.progress_manager.get_crate_commit_hash()
                    agent.run(
                        prompt,
                        prefix=f"[c2rust-optimizer][codeagent][unsafe-cleanup][iter{iteration}][retry]",
                        suffix="",
                    )
                    # 再次检测
                    if self.progress_manager.check_and_handle_test_deletion(
                        commit_before, agent
                    ):
                        PrettyOutput.auto_print(
                            f"[c2rust-optimizer][codeagent][unsafe-cleanup] 再次检测到测试代码删除问题，已回退 (iter={iteration})"
                        )

                # 验证修复是否成功（通过 cargo test）
                ok, _ = cargo_check_full(
                    crate,
                    self.stats,
                    self.options.max_checks,
                    timeout=self.options.cargo_test_timeout,
                )
                if ok:
                    # 修复成功，保存进度和 commit id
                    try:
                        # 确保 target_file_path 是 Path 对象
                        target_file_path_obj = Path(target_file_path)
                        file_path_to_save: Path = (
                            crate / target_file_path_obj
                            if not target_file_path_obj.is_absolute()
                            else target_file_path_obj
                        )
                        if file_path_to_save.exists():
                            self.progress_manager.save_fix_progress(
                                "unsafe_cleanup",
                                f"{target_file_path}-iter{iteration}",
                                [file_path_to_save],
                            )
                        else:
                            self.progress_manager.save_fix_progress(
                                "unsafe_cleanup",
                                f"{target_file_path}-iter{iteration}",
                                None,
                            )
                    except Exception:
                        self.progress_manager.save_fix_progress(
                            "unsafe_cleanup",
                            f"{target_file_path}-iter{iteration}",
                            None,
                        )
                    PrettyOutput.auto_print(
                        f"[c2rust-optimizer][codeagent][unsafe-cleanup] 文件 {target_file_path} 的 {warning_count} 个告警修复成功，已保存进度"
                    )
                else:
                    # 测试失败，回退到运行前的 commit
                    if commit_before:
                        PrettyOutput.auto_print(
                            f"[c2rust-optimizer][codeagent][unsafe-cleanup] 文件 {target_file_path} 修复后测试失败，回退到运行前的 commit: {commit_before[:8]}"
                        )
                        if self.progress_manager.reset_to_commit(commit_before):
                            PrettyOutput.auto_print(
                                f"[c2rust-optimizer][codeagent][unsafe-cleanup] 已成功回退到 commit: {commit_before[:8]}"
                            )
                        else:
                            PrettyOutput.auto_print(
                                "[c2rust-optimizer][codeagent][unsafe-cleanup] 回退失败，请手动检查代码状态"
                            )
                    else:
                        PrettyOutput.auto_print(
                            f"[c2rust-optimizer][codeagent][unsafe-cleanup] 文件 {target_file_path} 修复后测试失败，但无法获取运行前的 commit，继续修复"
                        )

                # 修复后再次检查告警
                has_warnings_after, _ = check_missing_safety_doc_warnings(crate)
                if not has_warnings_after:
                    PrettyOutput.auto_print(
                        f"[c2rust-optimizer][codeagent][unsafe-cleanup] 所有 missing_safety_doc 告警已消除（共迭代 {iteration} 次）"
                    )
                    return  # 所有告警已消除

        finally:
            os.chdir(prev_cwd)
