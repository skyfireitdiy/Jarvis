# -*- coding: utf-8 -*-
"""构建修复循环模块。"""

import os
import subprocess
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


class BuildFixOptimizer:
    """构建修复循环优化器。"""

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

    def build_fix_loop(self, scope_files: List[Path]) -> bool:
        """
        循环执行 cargo check 并用 CodeAgent 进行最小修复，直到通过或达到重试上限或检查预算耗尽。
        仅允许（优先）修改 scope_files（除非确有必要），以支持分批优化。
        返回 True 表示修复成功构建通过；False 表示未能在限制内修复。

        注意：CodeAgent 必须在 crate 目录下创建和执行，以确保所有文件操作和命令执行都在正确的上下文中进行。
        """
        maxr = int(self.options.build_fix_retries or 0)
        if maxr <= 0:
            return False
        crate = self.crate_dir.resolve()
        allowed: List[str] = []
        for p in scope_files:
            try:
                rel = p.resolve().relative_to(crate).as_posix()
            except Exception:
                rel = p.as_posix()
            allowed.append(rel)

        attempt = 0
        while True:
            # 检查预算
            if (
                self.options.max_checks
                and self.stats.cargo_checks >= self.options.max_checks
            ):
                return False
            # 执行构建
            output = ""
            try:
                res = subprocess.run(
                    ["cargo", "test", "-q"],
                    capture_output=True,
                    text=True,
                    check=False,
                    cwd=str(crate),
                    timeout=self.options.cargo_test_timeout
                    if self.options.cargo_test_timeout > 0
                    else None,
                )
                self.stats.cargo_checks += 1
                if res.returncode == 0:
                    PrettyOutput.auto_print(
                        "✅ [c2rust-optimizer][build-fix] 构建修复成功。"
                    )
                    return True
                output = ((res.stdout or "") + ("\n" + (res.stderr or ""))).strip()
            except subprocess.TimeoutExpired as e:
                self.stats.cargo_checks += 1
                out_s = e.stdout.decode("utf-8", errors="ignore") if e.stdout else ""
                err_s = e.stderr.decode("utf-8", errors="ignore") if e.stderr else ""
                output = f"cargo test timed out after {self.options.cargo_test_timeout} seconds"
                full_output = (out_s + ("\n" + err_s if err_s else "")).strip()
                if full_output:
                    output += f"\nOutput:\n{full_output}"
            except Exception as e:
                self.stats.cargo_checks += 1
                output = f"cargo test exception: {e}"

            # 达到重试上限则失败
            attempt += 1
            if attempt > maxr:
                PrettyOutput.auto_print(
                    "❌ [c2rust-optimizer][build-fix] 构建修复重试次数已用尽。"
                )
                return False

            PrettyOutput.auto_print(
                f"⚠️ [c2rust-optimizer][build-fix] 构建失败。正在尝试使用 CodeAgent 进行修复 (第 {attempt}/{maxr} 次尝试)..."
            )
            # 生成最小修复提示
            prompt_lines = [
                "请根据以下测试/构建错误对 crate 进行最小必要的修复以通过 `cargo test`：",
                f"- crate 根目录：{crate}",
                "",
                "本次修复优先且仅允许修改以下文件（除非确有必要，否则不要修改范围外文件）：",
                *[f"- {rel}" for rel in allowed],
                "",
                "约束与范围：",
                "- 保持最小改动，不要进行与错误无关的重构或格式化；",
                "- 仅输出补丁，不要输出解释或多余文本。",
                "",
                "优化目标：",
                "1) 修复构建/测试错误：",
                "   - 必须优先解决所有编译错误和测试失败问题；",
                "   - 修复时应该先解决编译错误，然后再解决测试失败；",
                "   - 如果修复过程中引入了新的错误，必须立即修复这些新错误。",
                "",
                "2) 修复已有实现的问题：",
                "   - 如果在修复构建/测试错误的过程中，发现代码已有的实现有问题（如逻辑错误、潜在 bug、性能问题、内存安全问题等），也需要一并修复；",
                "   - 这些问题可能包括但不限于：不正确的算法实现、未检查的边界条件、资源泄漏、竞态条件、数据竞争等；",
                "   - 修复时应该保持最小改动原则，优先修复最严重的问题。",
                "",
                "优先级说明：",
                "- **必须优先解决所有编译错误和测试失败问题**；",
                "- 修复时应该先解决编译错误，然后再解决测试失败；",
                "- 如果修复过程中引入了新的错误，必须立即修复这些新错误。",
                "",
                "自检要求：在每次输出补丁后，请使用 execute_script 工具在 crate 根目录执行 `cargo test -q` 进行验证；",
                "若出现编译错误或测试失败，请优先修复这些问题；",
                "若未通过，请继续输出新的补丁进行最小修复并再次自检，直至 `cargo test` 通过为止。",
                "",
                "构建错误如下：",
                "<BUILD_ERROR>",
                output,
                "</BUILD_ERROR>",
            ]
            prompt = "\n".join(prompt_lines)
            prompt = self.append_additional_notes(prompt)
            # 切换到 crate 目录，确保 CodeAgent 在正确的上下文中创建和执行
            prev_cwd = os.getcwd()
            try:
                os.chdir(str(crate))
                # 修复前执行 cargo fmt
                run_cargo_fmt(crate)

                # 记录运行前的 commit id
                commit_before = self.progress_manager.get_crate_commit_hash()

                # CodeAgent 在 crate 目录下创建和执行
                agent = CodeAgent(
                    name=f"BuildFixAgent-iter{attempt}",
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
                    prefix=f"[c2rust-optimizer][build-fix iter={attempt}]",
                    suffix="",
                )

                # 检测并处理测试代码删除
                if self.progress_manager.check_and_handle_test_deletion(
                    commit_before, agent
                ):
                    # 如果回退了，需要重新运行 agent
                    PrettyOutput.auto_print(
                        f"⚠️ [c2rust-optimizer][build-fix] 检测到测试代码删除问题，已回退，重新运行 agent (iter={attempt})"
                    )
                    commit_before = self.progress_manager.get_crate_commit_hash()
                    agent.run(
                        prompt,
                        prefix=f"[c2rust-optimizer][build-fix iter={attempt}][retry]",
                        suffix="",
                    )
                    # 再次检测
                    if self.progress_manager.check_and_handle_test_deletion(
                        commit_before, agent
                    ):
                        PrettyOutput.auto_print(
                            f"❌ [c2rust-optimizer][build-fix] 再次检测到测试代码删除问题，已回退 (iter={attempt})"
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
                    file_paths = [crate / f for f in allowed if (crate / f).exists()]
                    self.progress_manager.save_fix_progress(
                        "build_fix",
                        f"iter{attempt}",
                        file_paths if file_paths else None,
                    )
                    PrettyOutput.auto_print(
                        f"✅ [c2rust-optimizer][build-fix] 第 {attempt} 次修复成功，已保存进度"
                    )
                    # 返回 True 表示修复成功
                    return True
                else:
                    # 测试失败，回退到运行前的 commit
                    if commit_before:
                        PrettyOutput.auto_print(
                            f"⚠️ [c2rust-optimizer][build-fix] 第 {attempt} 次修复后测试失败，回退到运行前的 commit: {commit_before[:8]}"
                        )
                        if self.progress_manager.reset_to_commit(commit_before):
                            PrettyOutput.auto_print(
                                f"ℹ️ [c2rust-optimizer][build-fix] 已成功回退到 commit: {commit_before[:8]}"
                            )
                        else:
                            PrettyOutput.auto_print(
                                "❌ [c2rust-optimizer][build-fix] 回退失败，请手动检查代码状态"
                            )
                    else:
                        PrettyOutput.auto_print(
                            f"⚠️ [c2rust-optimizer][build-fix] 第 {attempt} 次修复后测试失败，但无法获取运行前的 commit，继续尝试"
                        )
            finally:
                os.chdir(prev_cwd)

    def verify_and_fix_after_step(
        self, step_name: str, target_files: List[Path]
    ) -> bool:
        """
        验证步骤执行后的测试，如果失败则尝试修复。

        Args:
            step_name: 步骤名称（用于错误消息）
            target_files: 目标文件列表（用于修复范围）

        Returns:
            True: 测试通过或修复成功
            False: 测试失败且修复失败（已回滚）
        """
        ok, diag_full = cargo_check_full(
            self.crate_dir,
            self.stats,
            self.options.max_checks,
            timeout=self.options.cargo_test_timeout,
        )
        if not ok:
            fixed = self.build_fix_loop(target_files)
            if not fixed:
                first = (
                    diag_full.splitlines()[0]
                    if isinstance(diag_full, str) and diag_full
                    else "failed"
                )
                if self.stats.errors is not None:
                    self.stats.errors.append(f"test after {step_name} failed: {first}")
                try:
                    self.progress_manager.reset_to_snapshot()
                finally:
                    return False
        return True
