# -*- coding: utf-8 -*-
"""Clippy 告警修复模块。"""

import json
import os
import subprocess
from pathlib import Path
from typing import Callable, Dict, List

import typer

from jarvis.jarvis_agent.events import AFTER_TOOL_CALL, BEFORE_TOOL_CALL
from jarvis.jarvis_code_agent.code_agent import CodeAgent
from jarvis.jarvis_c2rust.optimizer_options import OptimizeOptions, OptimizeStats
from jarvis.jarvis_c2rust.optimizer_progress import ProgressManager
from jarvis.jarvis_c2rust.optimizer_utils import (
    cargo_check_full,
    check_clippy_warnings,
    git_toplevel,
    iter_rust_files,
    run_cargo_fmt,
    run_cmd,
)


class ClippyOptimizer:
    """Clippy 告警修复优化器。"""

    def __init__(
        self,
        crate_dir: Path,
        options: OptimizeOptions,
        stats: OptimizeStats,
        progress_manager: ProgressManager,
        append_additional_notes_func: Callable[[str], str],
        verify_and_fix_after_step_func: Callable[[str, List[Path]], bool],
    ):
        self.crate_dir = crate_dir
        self.options = options
        self.stats = stats
        self.progress_manager = progress_manager
        self.append_additional_notes = append_additional_notes_func
        self.verify_and_fix_after_step = verify_and_fix_after_step_func

    def try_clippy_auto_fix(self) -> bool:
        """
        尝试使用 `cargo clippy --fix` 自动修复 clippy 告警。
        修复时同时包含测试代码（--tests），避免删除测试中使用的变量。
        修复后运行测试验证，如果测试失败则撤销修复。

        返回：
            True: 自动修复成功且测试通过
            False: 自动修复失败或测试未通过（已撤销修复）
        """
        crate = self.crate_dir.resolve()
        typer.secho(
            "[c2rust-optimizer][clippy-auto-fix] 尝试使用 clippy --fix 自动修复（包含测试代码）...",
            fg=typer.colors.CYAN,
        )

        # 记录修复前的 commit id
        commit_before = self.progress_manager.get_crate_commit_hash()
        if not commit_before:
            typer.secho(
                "[c2rust-optimizer][clippy-auto-fix] 无法获取 commit id，跳过自动修复",
                fg=typer.colors.YELLOW,
            )
            return False

        # 执行 cargo clippy --fix，添加 --tests 标志以包含测试代码
        try:
            res = subprocess.run(
                [
                    "cargo",
                    "clippy",
                    "--fix",
                    "--tests",
                    "--allow-dirty",
                    "--allow-staged",
                    "--",
                    "-W",
                    "clippy::all",
                ],
                capture_output=True,
                text=True,
                check=False,
                cwd=str(crate),
                timeout=300,  # 5 分钟超时
            )

            if res.returncode != 0:
                typer.secho(
                    f"[c2rust-optimizer][clippy-auto-fix] clippy --fix 执行失败（返回码: {res.returncode}）",
                    fg=typer.colors.YELLOW,
                )
                if res.stderr:
                    typer.secho(
                        f"[c2rust-optimizer][clippy-auto-fix] 错误输出: {res.stderr[:500]}",
                        fg=typer.colors.YELLOW,
                    )
                return False

            # 检查是否有文件被修改（通过 git status 或直接检查）
            # 如果没有修改，说明 clippy --fix 没有修复任何问题
            repo_root = git_toplevel(crate)
            has_changes = False
            if repo_root:
                try:
                    code, out, _ = run_cmd(
                        ["git", "diff", "--quiet", "--exit-code"], repo_root
                    )
                    has_changes = code != 0  # 非零表示有修改
                except Exception:
                    # 如果无法检查 git 状态，假设有修改
                    has_changes = True
            else:
                # 不在 git 仓库中，假设有修改
                has_changes = True

            if not has_changes:
                typer.secho(
                    "[c2rust-optimizer][clippy-auto-fix] clippy --fix 未修改任何文件",
                    fg=typer.colors.CYAN,
                )
                return False

            typer.secho(
                "[c2rust-optimizer][clippy-auto-fix] clippy --fix 已执行，正在验证测试...",
                fg=typer.colors.CYAN,
            )

            # 运行 cargo test 验证
            ok, diag_full = cargo_check_full(
                self.crate_dir,
                self.stats,
                self.options.max_checks,
                timeout=self.options.cargo_test_timeout,
            )

            if ok:
                typer.secho(
                    "[c2rust-optimizer][clippy-auto-fix] 自动修复成功且测试通过",
                    fg=typer.colors.GREEN,
                )
                return True
            else:
                typer.secho(
                    "[c2rust-optimizer][clippy-auto-fix] 自动修复后测试失败，正在撤销修复...",
                    fg=typer.colors.YELLOW,
                )
                # 撤销修复：回退到修复前的 commit
                if commit_before and self.progress_manager.reset_to_commit(
                    commit_before
                ):
                    typer.secho(
                        f"[c2rust-optimizer][clippy-auto-fix] 已成功撤销自动修复，回退到 commit: {commit_before[:8]}",
                        fg=typer.colors.CYAN,
                    )
                else:
                    typer.secho(
                        "[c2rust-optimizer][clippy-auto-fix] 撤销修复失败，请手动检查代码状态",
                        fg=typer.colors.RED,
                    )
                return False

        except subprocess.TimeoutExpired:
            typer.secho(
                "[c2rust-optimizer][clippy-auto-fix] clippy --fix 执行超时，正在检查是否有修改并撤销...",
                fg=typer.colors.YELLOW,
            )
            # 检查是否有修改，如果有则回退
            if commit_before:
                repo_root = git_toplevel(crate)
                if repo_root:
                    try:
                        code, _, _ = run_cmd(
                            ["git", "diff", "--quiet", "--exit-code"], repo_root
                        )
                        has_changes = code != 0  # 非零表示有修改
                        if has_changes:
                            if self.progress_manager.reset_to_commit(commit_before):
                                typer.secho(
                                    f"[c2rust-optimizer][clippy-auto-fix] 已撤销超时前的修改，回退到 commit: {commit_before[:8]}",
                                    fg=typer.colors.CYAN,
                                )
                            else:
                                typer.secho(
                                    "[c2rust-optimizer][clippy-auto-fix] 撤销修改失败，请手动检查代码状态",
                                    fg=typer.colors.RED,
                                )
                    except Exception:
                        # 无法检查状态，尝试直接回退
                        self.progress_manager.reset_to_commit(commit_before)
            return False
        except Exception as e:
            typer.secho(
                f"[c2rust-optimizer][clippy-auto-fix] clippy --fix 执行异常: {e}，正在检查是否有修改并撤销...",
                fg=typer.colors.YELLOW,
            )
            # 检查是否有修改，如果有则回退
            if commit_before:
                repo_root = git_toplevel(crate)
                if repo_root:
                    try:
                        code, _, _ = run_cmd(
                            ["git", "diff", "--quiet", "--exit-code"], repo_root
                        )
                        has_changes = code != 0  # 非零表示有修改
                        if has_changes:
                            if self.progress_manager.reset_to_commit(commit_before):
                                typer.secho(
                                    f"[c2rust-optimizer][clippy-auto-fix] 已撤销异常前的修改，回退到 commit: {commit_before[:8]}",
                                    fg=typer.colors.CYAN,
                                )
                            else:
                                typer.secho(
                                    "[c2rust-optimizer][clippy-auto-fix] 撤销修改失败，请手动检查代码状态",
                                    fg=typer.colors.RED,
                                )
                    except Exception:
                        # 无法检查状态，尝试直接回退
                        self.progress_manager.reset_to_commit(commit_before)
            return False

    def codeagent_eliminate_clippy_warnings(
        self, target_files: List[Path], clippy_output: str
    ) -> bool:
        """
        使用 CodeAgent 消除 clippy 告警。
        按文件修复，每次修复单个文件的前10个告警（不足10个就全部给出），修复后重新扫描，不断迭代。

        注意：CodeAgent 必须在 crate 目录下创建和执行，以确保所有文件操作和命令执行都在正确的上下文中进行。

        返回：
            True: 所有告警已消除
            False: 仍有告警未消除（达到最大迭代次数或无法提取告警）
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

            # 循环修复告警，按文件处理
            while True:
                iteration += 1

                # 检查当前告警
                has_warnings, current_clippy_output = check_clippy_warnings(crate)
                if not has_warnings:
                    typer.secho(
                        f"[c2rust-optimizer][codeagent][clippy] 所有告警已消除（共迭代 {iteration - 1} 次）",
                        fg=typer.colors.GREEN,
                    )
                    return True  # 所有告警已消除

                # 按文件提取告警
                warnings_by_file = self.extract_warnings_by_file(current_clippy_output)
                if not warnings_by_file:
                    typer.secho(
                        "[c2rust-optimizer][codeagent][clippy] 无法提取告警，停止修复",
                        fg=typer.colors.YELLOW,
                    )
                    return False  # 仍有告警未消除

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

                # 获取该文件的前10个告警（不足10个就全部给出）
                warnings_to_fix = (
                    target_warnings[:10] if target_warnings is not None else []
                )
                warning_count = len(warnings_to_fix)
                total_warnings_in_file = (
                    len(target_warnings) if target_warnings is not None else 0
                )

                typer.secho(
                    f"[c2rust-optimizer][codeagent][clippy] 第 {iteration} 次迭代：修复文件 {target_file_path} 的前 {warning_count} 个告警（共 {total_warnings_in_file} 个）",
                    fg=typer.colors.CYAN,
                )

                # 格式化告警信息
                formatted_warnings = self.format_warnings_for_prompt(
                    warnings_to_fix, max_count=10
                )

                # 构建提示词，修复该文件的前10个告警
                prompt_lines: List[str] = [
                    "你是资深 Rust 代码工程师。请在当前 crate 下修复指定文件中的 Clippy 告警，并以补丁形式输出修改：",
                    f"- crate 根目录：{crate}",
                    "",
                    "本次修复仅允许修改以下文件（严格限制，只处理这一个文件）：",
                    f"- {target_file_path}",
                    "",
                    f"重要：本次修复仅修复该文件中的前 {warning_count} 个告警，不要修复其他告警。",
                    "",
                    "优化目标：",
                    f"1) 修复文件 {target_file_path} 中的 {warning_count} 个 Clippy 告警：",
                    "   - 根据以下 Clippy 告警信息，修复这些告警；",
                    "   - 告警信息包含文件路径、行号、警告类型、消息和建议，请根据这些信息进行修复；",
                    "   - 对于无法自动修复的告警，请根据 Clippy 的建议进行手动修复；",
                    "   - **如果确认是误报**（例如：告警建议的修改会导致性能下降、代码可读性降低、或与项目设计意图不符），可以添加 `#[allow(clippy::...)]` 注释来屏蔽该告警；",
                    "   - 使用 `#[allow(...)]` 时，必须在注释中说明为什么这是误报，例如：`#[allow(clippy::unnecessary_wraps)] // 保持 API 一致性，返回值类型需要与接口定义一致`；",
                    "   - 优先尝试修复告警，只有在确认是误报时才使用 `#[allow(...)]` 屏蔽。",
                    "",
                    "2) 修复已有实现的问题：",
                    "   - 如果在修复告警的过程中，发现代码已有的实现有问题（如逻辑错误、潜在 bug、性能问题、内存安全问题等），也需要一并修复；",
                    "   - 这些问题可能包括但不限于：空指针解引用、数组越界、未初始化的变量、资源泄漏、竞态条件等；",
                    "   - 修复时应该保持最小改动原则，优先修复最严重的问题。",
                    "",
                    "约束与范围：",
                    f"- **仅修改文件 {target_file_path}，不要修改其他文件**；除非必须（如修复引用路径），否则不要修改其他文件。",
                    "- 保持最小改动，不要进行与消除告警无关的重构或格式化。",
                    f"- **只修复该文件中的前 {warning_count} 个告警，不要修复其他告警**。",
                    "- 修改后需保证 `cargo test` 可以通过；如需引入少量配套改动，请一并包含在补丁中以确保通过。",
                    "- 输出仅为补丁，不要输出解释或多余文本。",
                    "",
                    "优先级说明：",
                    "- **如果优化过程中出现了测试不通过或编译错误，必须优先解决这些问题**；",
                    "- 在修复告警之前，先确保代码能够正常编译和通过测试；",
                    "- 如果修复告警导致了编译错误或测试失败，必须立即修复这些错误，然后再继续优化。",
                    "",
                    "自检要求：在每次输出补丁后，请使用 execute_script 工具在 crate 根目录执行 `cargo test -q` 进行验证；",
                    "若出现编译错误或测试失败，请优先修复这些问题，然后再继续修复告警；",
                    "若未通过，请继续输出新的补丁进行最小修复并再次自检，直至 `cargo test` 通过为止。",
                    "",
                    f"文件 {target_file_path} 中的 Clippy 告警信息如下：",
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
                    name=f"ClippyWarningEliminator-iter{iteration}",
                    need_summary=False,
                    non_interactive=self.options.non_interactive,
                    model_group=self.options.llm_group,
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
                    prompt, prefix="[c2rust-optimizer][codeagent][clippy]", suffix=""
                )

                # 检测并处理测试代码删除
                if self.progress_manager.check_and_handle_test_deletion(
                    commit_before, agent
                ):
                    # 如果回退了，需要重新运行 agent
                    typer.secho(
                        f"[c2rust-optimizer][codeagent][clippy] 检测到测试代码删除问题，已回退，重新运行 agent (iter={iteration})",
                        fg=typer.colors.YELLOW,
                    )
                    commit_before = self.progress_manager.get_crate_commit_hash()
                    agent.run(
                        prompt,
                        prefix="[c2rust-optimizer][codeagent][clippy][retry]",
                        suffix="",
                    )
                    # 再次检测
                    if self.progress_manager.check_and_handle_test_deletion(
                        commit_before, agent
                    ):
                        typer.secho(
                            f"[c2rust-optimizer][codeagent][clippy] 再次检测到测试代码删除问题，已回退 (iter={iteration})",
                            fg=typer.colors.RED,
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
                                "clippy_elimination",
                                f"{target_file_path}-iter{iteration}",
                                [file_path_to_save],
                            )
                        else:
                            self.progress_manager.save_fix_progress(
                                "clippy_elimination",
                                f"{target_file_path}-iter{iteration}",
                                None,
                            )
                    except Exception:
                        self.progress_manager.save_fix_progress(
                            "clippy_elimination",
                            f"{target_file_path}-iter{iteration}",
                            None,
                        )
                    typer.secho(
                        f"[c2rust-optimizer][codeagent][clippy] 文件 {target_file_path} 的前 {warning_count} 个告警修复成功，已保存进度",
                        fg=typer.colors.GREEN,
                    )
                else:
                    # 测试失败，回退到运行前的 commit
                    if commit_before:
                        typer.secho(
                            f"[c2rust-optimizer][codeagent][clippy] 文件 {target_file_path} 修复后测试失败，回退到运行前的 commit: {commit_before[:8]}",
                            fg=typer.colors.YELLOW,
                        )
                        if self.progress_manager.reset_to_commit(commit_before):
                            typer.secho(
                                f"[c2rust-optimizer][codeagent][clippy] 已成功回退到 commit: {commit_before[:8]}",
                                fg=typer.colors.CYAN,
                            )
                        else:
                            typer.secho(
                                "[c2rust-optimizer][codeagent][clippy] 回退失败，请手动检查代码状态",
                                fg=typer.colors.RED,
                            )
                    else:
                        typer.secho(
                            f"[c2rust-optimizer][codeagent][clippy] 文件 {target_file_path} 修复后测试失败，但无法获取运行前的 commit，继续修复",
                            fg=typer.colors.YELLOW,
                        )

                # 修复后再次检查告警，如果告警数量没有减少，可能需要停止
                has_warnings_after, _ = check_clippy_warnings(crate)
                if not has_warnings_after:
                    typer.secho(
                        f"[c2rust-optimizer][codeagent][clippy] 所有告警已消除（共迭代 {iteration} 次）",
                        fg=typer.colors.GREEN,
                    )
                    return True  # 所有告警已消除
        finally:
            os.chdir(prev_cwd)

        # 默认返回 False（仍有告警）
        return False

    def extract_warnings_by_file(
        self, clippy_json_output: str
    ) -> Dict[str, List[Dict]]:
        """
        从 clippy JSON 输出中提取所有告警并按文件分组。

        Returns:
            字典，键为文件路径，值为该文件的告警列表
        """
        if not clippy_json_output:
            return {}

        warnings_by_file: Dict[str, List[Dict]] = {}

        for line in clippy_json_output.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                # 只处理 warning 类型的消息
                if (
                    msg.get("reason") == "compiler-message"
                    and msg.get("message", {}).get("level") == "warning"
                ):
                    message = msg.get("message", {})
                    spans = message.get("spans", [])
                    if spans:
                        primary_span = spans[0]
                        file_path = primary_span.get("file_name", "")
                        if file_path:
                            if file_path not in warnings_by_file:
                                warnings_by_file[file_path] = []
                            warnings_by_file[file_path].append(msg)
            except (json.JSONDecodeError, KeyError, TypeError):
                continue

        return warnings_by_file

    def format_warnings_for_prompt(
        self, warnings: List[Dict], max_count: int = 10
    ) -> str:
        """
        格式化告警列表，用于提示词。

        Args:
            warnings: 告警消息列表
            max_count: 最多格式化多少个告警（默认10个）

        Returns:
            格式化后的告警信息字符串
        """
        if not warnings:
            return ""

        # 只取前 max_count 个告警
        warnings_to_format = warnings[:max_count]
        formatted_warnings = []

        for idx, warning_msg in enumerate(warnings_to_format, 1):
            message = warning_msg.get("message", {})
            spans = message.get("spans", [])

            warning_parts = [f"告警 {idx}:"]

            # 警告类型和消息
            code = message.get("code", {})
            code_str = code.get("code", "") if code else ""
            message_text = message.get("message", "")
            warning_parts.append(f"  警告类型: {code_str}")
            warning_parts.append(f"  消息: {message_text}")

            # 文件位置
            if spans:
                primary_span = spans[0]
                line_start = primary_span.get("line_start", 0)
                column_start = primary_span.get("column_start", 0)
                line_end = primary_span.get("line_end", 0)
                column_end = primary_span.get("column_end", 0)

                if line_start == line_end:
                    warning_parts.append(
                        f"  位置: {line_start}:{column_start}-{column_end}"
                    )
                else:
                    warning_parts.append(
                        f"  位置: {line_start}:{column_start} - {line_end}:{column_end}"
                    )

                # 代码片段
                label = primary_span.get("label", "")
                if label:
                    warning_parts.append(f"  代码: {label}")

            # 建议（help 消息）
            children = message.get("children", [])
            for child in children:
                if child.get("level") == "help":
                    help_message = child.get("message", "")
                    help_spans = child.get("spans", [])
                    if help_message:
                        warning_parts.append(f"  建议: {help_message}")
                    if help_spans:
                        help_span = help_spans[0]
                        help_label = help_span.get("label", "")
                        if help_label:
                            warning_parts.append(f"  建议代码: {help_label}")

            formatted_warnings.append("\n".join(warning_parts))

        if len(warnings) > max_count:
            formatted_warnings.append(
                f"\n（该文件还有 {len(warnings) - max_count} 个告警，将在后续迭代中处理）"
            )

        return "\n\n".join(formatted_warnings)

    def handle_clippy_after_auto_fix(
        self, clippy_targets: List[Path], clippy_output: str
    ) -> bool:
        """
        处理自动修复后的 clippy 告警检查。
        如果仍有告警，使用 CodeAgent 继续修复。

        Args:
            clippy_targets: 目标文件列表
            clippy_output: 当前的 clippy 输出

        Returns:
            True: 所有告警已消除
            False: 仍有告警未消除（步骤未完成）
        """
        typer.secho(
            "[c2rust-optimizer] 自动修复后仍有告警，继续使用 CodeAgent 修复...",
            fg=typer.colors.CYAN,
        )
        all_warnings_eliminated = self.codeagent_eliminate_clippy_warnings(
            clippy_targets, clippy_output
        )

        # 验证修复后是否还有告警
        if not self.verify_and_fix_after_step("clippy_elimination", clippy_targets):
            return False

        # 再次检查是否还有告警
        has_warnings_after, _ = check_clippy_warnings(self.crate_dir)
        if not has_warnings_after and all_warnings_eliminated:
            typer.secho(
                "[c2rust-optimizer] Clippy 告警已全部消除", fg=typer.colors.GREEN
            )
            self.progress_manager.save_step_progress(
                "clippy_elimination", clippy_targets
            )
            return True
        else:
            typer.secho(
                "[c2rust-optimizer] 仍有部分 Clippy 告警无法自动消除，步骤未完成，停止后续优化步骤",
                fg=typer.colors.YELLOW,
            )
            return False

    def run_clippy_elimination_step(self) -> bool:
        """
        执行 Clippy 告警修复步骤（第 0 步）。

        Returns:
            True: 步骤完成（无告警或已修复）
            False: 步骤未完成（仍有告警未修复，应停止后续步骤）
        """
        if self.options.dry_run:
            return True

        typer.secho("[c2rust-optimizer] 检查 Clippy 告警...", fg=typer.colors.CYAN)
        has_warnings, clippy_output = check_clippy_warnings(self.crate_dir)

        # 如果步骤已标记为完成，但仍有告警，说明之前的完成标记是错误的，需要清除
        if (
            "clippy_elimination" in self.progress_manager.steps_completed
            and has_warnings
        ):
            typer.secho(
                "[c2rust-optimizer] 检测到步骤已标记为完成，但仍有 Clippy 告警，清除完成标记并继续修复",
                fg=typer.colors.YELLOW,
            )
            self.progress_manager.steps_completed.discard("clippy_elimination")
            if "clippy_elimination" in self.progress_manager._step_commits:
                del self.progress_manager._step_commits["clippy_elimination"]

        if not has_warnings:
            typer.secho(
                "[c2rust-optimizer] 未发现 Clippy 告警，跳过消除步骤",
                fg=typer.colors.CYAN,
            )
            # 如果没有告警，标记 clippy_elimination 为完成（跳过状态）
            if "clippy_elimination" not in self.progress_manager.steps_completed:
                clippy_targets = list(iter_rust_files(self.crate_dir))
                if clippy_targets:
                    self.progress_manager.save_step_progress(
                        "clippy_elimination", clippy_targets
                    )
            return True

        # 有告警，需要修复
        typer.secho(
            "\n[c2rust-optimizer] 第 0 步：消除 Clippy 告警（必须完成此步骤才能继续其他优化）",
            fg=typer.colors.MAGENTA,
        )
        self.progress_manager.snapshot_commit()

        clippy_targets = list(iter_rust_files(self.crate_dir))
        if not clippy_targets:
            typer.secho(
                "[c2rust-optimizer] 警告：未找到任何 Rust 文件，无法修复 Clippy 告警",
                fg=typer.colors.YELLOW,
            )
            return False

        # 先尝试使用 clippy --fix 自动修复
        auto_fix_success = self.try_clippy_auto_fix()
        if auto_fix_success:
            typer.secho(
                "[c2rust-optimizer] clippy 自动修复成功，继续检查是否还有告警...",
                fg=typer.colors.GREEN,
            )
            # 重新检查告警
            has_warnings, clippy_output = check_clippy_warnings(self.crate_dir)
            if not has_warnings:
                typer.secho(
                    "[c2rust-optimizer] 所有 Clippy 告警已通过自动修复消除",
                    fg=typer.colors.GREEN,
                )
                self.progress_manager.save_step_progress(
                    "clippy_elimination", clippy_targets
                )
                return True
            else:
                # 仍有告警，使用 CodeAgent 继续修复
                return self.handle_clippy_after_auto_fix(clippy_targets, clippy_output)
        else:
            # 自动修复失败或未执行，继续使用 CodeAgent 修复
            typer.secho(
                "[c2rust-optimizer] clippy 自动修复未成功，继续使用 CodeAgent 修复...",
                fg=typer.colors.CYAN,
            )
            all_warnings_eliminated = self.codeagent_eliminate_clippy_warnings(
                clippy_targets, clippy_output
            )

            # 验证修复后是否还有告警
            if not self.verify_and_fix_after_step("clippy_elimination", clippy_targets):
                return False

            # 再次检查是否还有告警
            has_warnings_after, _ = check_clippy_warnings(self.crate_dir)
            if not has_warnings_after and all_warnings_eliminated:
                typer.secho(
                    "[c2rust-optimizer] Clippy 告警已全部消除", fg=typer.colors.GREEN
                )
                self.progress_manager.save_step_progress(
                    "clippy_elimination", clippy_targets
                )
                return True
            else:
                typer.secho(
                    "[c2rust-optimizer] 仍有部分 Clippy 告警无法自动消除，步骤未完成，停止后续优化步骤",
                    fg=typer.colors.YELLOW,
                )
                return False
