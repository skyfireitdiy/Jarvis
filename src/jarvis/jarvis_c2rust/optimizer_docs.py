# -*- coding: utf-8 -*-
"""文档补充优化模块。"""

import os
from pathlib import Path
from typing import Callable
from typing import List

from jarvis.jarvis_utils.output import PrettyOutput

from jarvis.jarvis_agent.events import AFTER_TOOL_CALL
from jarvis.jarvis_agent.events import BEFORE_TOOL_CALL
from jarvis.jarvis_c2rust.optimizer_options import OptimizeOptions
from jarvis.jarvis_c2rust.optimizer_options import OptimizeStats
from jarvis.jarvis_c2rust.optimizer_progress import ProgressManager
from jarvis.jarvis_c2rust.optimizer_utils import cargo_check_full
from jarvis.jarvis_c2rust.optimizer_utils import run_cargo_fmt
from jarvis.jarvis_code_agent.code_agent import CodeAgent


class DocsOptimizer:
    """文档补充优化器。"""

    def __init__(
        self,
        crate_dir: Path,
        options: OptimizeOptions,
        stats: OptimizeStats,
        progress_manager: ProgressManager,
        append_additional_notes_func: Callable[[str], str],
    ):
        self.crate_dir = crate_dir
        self.options = options
        self.stats = stats
        self.progress_manager = progress_manager
        self.append_additional_notes = append_additional_notes_func

    def codeagent_opt_docs(self, target_files: List[Path]) -> None:
        """
        使用 CodeAgent 进行文档补充。

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

        prompt_lines: List[str] = [
            "你是资深 Rust 代码工程师。请在当前 crate 下执行文档补充优化，并以补丁形式输出修改：",
            f"- crate 根目录：{crate}",
            "",
            "本次优化仅允许修改以下文件范围（严格限制）：",
            *[f"- {rel}" for rel in file_list],
            "",
            "优化目标：",
            "1) 文档补充：",
            "   - 为缺少模块级文档的文件添加 `//! ...` 模块文档注释（放在文件开头）；",
            "   - 为缺少函数文档的公共函数（pub 或 pub(crate)）添加 `/// ...` 文档注释；",
            "   - 文档内容可以是占位注释（如 `//! TODO: Add module-level documentation` 或 `/// TODO: Add documentation`），也可以根据函数签名和实现提供简要说明。",
            "",
            "2) 修复已有实现的问题：",
            "   - 如果在进行文档补充的过程中，发现代码已有的实现有问题（如逻辑错误、潜在 bug、性能问题、内存安全问题等），也需要一并修复；",
            "   - 这些问题可能包括但不限于：不正确的算法实现、未检查的边界条件、资源泄漏、竞态条件等；",
            "   - 修复时应该保持最小改动原则，优先修复最严重的问题。",
            "",
            "约束与范围：",
            "- 仅修改上述列出的文件；除非必须（如修复引用路径），否则不要修改其他文件。",
            "- 保持最小改动，不要进行与文档补充无关的重构或格式化。",
            "- 修改后需保证 `cargo test` 可以通过；如需引入少量配套改动，请一并包含在补丁中以确保通过。",
            "- 输出仅为补丁，不要输出解释或多余文本。",
            "",
            "优先级说明：",
            "- **如果优化过程中出现了测试不通过或编译错误，必须优先解决这些问题**；",
            "- 在进行文档补充之前，先确保代码能够正常编译和通过测试；",
            "- 如果文档补充导致了编译错误或测试失败，必须立即修复这些错误，然后再继续优化。",
            "",
            "自检要求：在每次输出补丁后，请使用 execute_script 工具在 crate 根目录执行 `cargo test -q` 进行验证；",
            "若出现编译错误或测试失败，请优先修复这些问题，然后再继续文档补充；",
            "若未通过，请继续输出新的补丁进行最小修复并再次自检，直至 `cargo test` 通过为止。",
        ]
        prompt = "\n".join(prompt_lines)
        prompt = self.append_additional_notes(prompt)
        # 切换到 crate 目录，确保 CodeAgent 在正确的上下文中创建和执行
        prev_cwd = os.getcwd()
        PrettyOutput.auto_print(
            "📝 [c2rust-optimizer][codeagent][doc] 正在调用 CodeAgent 进行文档补充..."
        )
        try:
            os.chdir(str(crate))
            # 修复前执行 cargo fmt
            run_cargo_fmt(crate)

            # 记录运行前的 commit id
            commit_before = self.progress_manager.get_crate_commit_hash()

            # CodeAgent 在 crate 目录下创建和执行
            agent = CodeAgent(
                name="DocumentationAgent",
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
                self.progress_manager._agent_before_commits[agent_key] = initial_commit
            agent.run(prompt, prefix="[c2rust-optimizer][codeagent][doc]", suffix="")

            # 检测并处理测试代码删除
            if self.progress_manager.check_and_handle_test_deletion(
                commit_before, agent
            ):
                # 如果回退了，需要重新运行 agent
                PrettyOutput.auto_print(
                    "⚠️ [c2rust-optimizer][codeagent][doc] 检测到测试代码删除问题，已回退，重新运行 agent"
                )
                commit_before = self.progress_manager.get_crate_commit_hash()
                agent.run(
                    prompt,
                    prefix="[c2rust-optimizer][codeagent][doc][retry]",
                    suffix="",
                )
                # 再次检测
                if self.progress_manager.check_and_handle_test_deletion(
                    commit_before, agent
                ):
                    PrettyOutput.auto_print(
                        "❌ [c2rust-optimizer][codeagent][doc] 再次检测到测试代码删除问题，已回退"
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
                file_paths = [crate / f for f in file_list if (crate / f).exists()]
                self.progress_manager.save_fix_progress(
                    "doc_opt", "batch", file_paths if file_paths else None
                )
                PrettyOutput.auto_print(
                    "✅ [c2rust-optimizer][codeagent][doc] 文档补充成功，已保存进度"
                )
            else:
                # 测试失败，回退到运行前的 commit
                if commit_before:
                    PrettyOutput.auto_print(
                        f"⚠️ [c2rust-optimizer][codeagent][doc] 文档补充后测试失败，回退到运行前的 commit: {commit_before[:8]}"
                    )
                    if self.progress_manager.reset_to_commit(commit_before):
                        PrettyOutput.auto_print(
                            f"ℹ️ [c2rust-optimizer][codeagent][doc] 已成功回退到 commit: {commit_before[:8]}"
                        )
                    else:
                        PrettyOutput.auto_print(
                            "❌ [c2rust-optimizer][codeagent][doc] 回退失败，请手动检查代码状态"
                        )
                else:
                    PrettyOutput.auto_print(
                        "⚠️ [c2rust-optimizer][codeagent][doc] 文档补充后测试失败，但无法获取运行前的 commit"
                    )
        finally:
            os.chdir(prev_cwd)
