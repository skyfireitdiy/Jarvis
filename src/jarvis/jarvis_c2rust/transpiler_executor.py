# -*- coding: utf-8 -*-
"""
转译执行器模块

负责执行转译的主流程，包括：
- 初始化 crate 目录和配置
- 加载和处理 order 文件
- 遍历函数并执行转译流程
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Set

import typer

from jarvis.jarvis_c2rust.constants import MAX_FUNCTION_RETRIES
from jarvis.jarvis_c2rust.models import FnRecord
from jarvis.jarvis_c2rust.utils import ensure_order_file, iter_order_steps


class TranspilerExecutor:
    """转译执行器，负责执行转译的主流程"""

    def __init__(
        self,
        project_root: Path,
        crate_dir: Path,
        progress: Dict[str, Any],
        resume: bool,
        fn_index_by_id: Dict[int, FnRecord],
        # 依赖注入的方法
        load_order_index_func,
        should_skip_func,
        read_source_span_func,
        plan_module_and_signature_func,
        update_progress_current_func,
        mark_converted_func,
        reset_function_context_func,
        ensure_mod_chain_for_module_func,
        ensure_top_level_pub_mod_func,
        get_crate_commit_hash_func,
        reset_to_commit_func,
        run_cargo_fmt_func,
        untranslated_callee_symbols_func,
        codeagent_generate_impl_func,
        refresh_compact_context_func,
        cargo_build_loop_func,
        review_and_optimize_func,
        extract_rust_fn_name_from_sig_func,
        resolve_pending_todos_for_symbol_func,
        save_progress_func,
        consecutive_fix_failures_getter,
        consecutive_fix_failures_setter,
        current_function_start_commit_getter,
        current_function_start_commit_setter,
    ) -> None:
        self.project_root = project_root
        self.crate_dir = crate_dir
        self.progress = progress
        self.resume = resume
        self.fn_index_by_id = fn_index_by_id

        # 注入的方法
        self.load_order_index = load_order_index_func
        self.should_skip = should_skip_func
        self.read_source_span = read_source_span_func
        self.plan_module_and_signature = plan_module_and_signature_func
        self.update_progress_current = update_progress_current_func
        self.mark_converted = mark_converted_func
        self.reset_function_context = reset_function_context_func
        self.ensure_mod_chain_for_module = ensure_mod_chain_for_module_func
        self.ensure_top_level_pub_mod = ensure_top_level_pub_mod_func
        self.get_crate_commit_hash = get_crate_commit_hash_func
        self.reset_to_commit = reset_to_commit_func
        self.run_cargo_fmt = run_cargo_fmt_func
        self.untranslated_callee_symbols = untranslated_callee_symbols_func
        self.codeagent_generate_impl = codeagent_generate_impl_func
        self.refresh_compact_context = refresh_compact_context_func
        self.cargo_build_loop = cargo_build_loop_func
        self.review_and_optimize = review_and_optimize_func
        self.extract_rust_fn_name_from_sig = extract_rust_fn_name_from_sig_func
        self.resolve_pending_todos_for_symbol = resolve_pending_todos_for_symbol_func
        self.save_progress = save_progress_func
        self.consecutive_fix_failures_getter = consecutive_fix_failures_getter
        self.consecutive_fix_failures_setter = consecutive_fix_failures_setter
        self.current_function_start_commit_getter = current_function_start_commit_getter
        self.current_function_start_commit_setter = current_function_start_commit_setter

    def execute(self) -> None:
        """执行转译主流程"""
        typer.secho("[c2rust-transpiler][start] 开始转译", fg=typer.colors.BLUE)
        # 切换到 crate 根目录，整个转译过程都在此目录下执行
        prev_cwd = os.getcwd()
        try:
            os.chdir(str(self.crate_dir))
            typer.secho(
                f"[c2rust-transpiler][start] 已切换到 crate 目录: {os.getcwd()}",
                fg=typer.colors.BLUE,
            )
            # 准确性兜底：在未执行 prepare 的情况下，确保 crate 目录与最小 Cargo 配置存在
            self._ensure_crate_structure()

            order_path = ensure_order_file(self.project_root)
            steps = iter_order_steps(order_path)
            if not steps:
                typer.secho(
                    "[c2rust-transpiler] 未找到翻译步骤。", fg=typer.colors.YELLOW
                )
                return

            # 构建自包含 order 索引（id -> FnRecord，name/qname -> id）
            self.load_order_index(order_path)

            # 扁平化顺序，按单个函数处理（保持原有顺序）
            seq: List[int] = []
            for grp in steps:
                seq.extend(grp)

            # 若支持 resume，则跳过 progress['converted'] 中已完成的
            done: Set[int] = set(self.progress.get("converted") or [])
            # 计算需要处理的函数总数（排除已完成的）
            total_to_process = len([fid for fid in seq if fid not in done])
            current_index = 0

            # 恢复时，reset 到最后一个已转换函数的 commit id
            self._handle_resume(seq, done)

            typer.secho(
                f"[c2rust-transpiler][order] 顺序信息: 步骤数={len(steps)} 总ID={sum(len(g) for g in steps)} 已转换={len(done)} 待处理={total_to_process}",
                fg=typer.colors.BLUE,
            )

            for fid in seq:
                if fid in done:
                    continue
                rec = self.fn_index_by_id.get(fid)
                if not rec:
                    continue
                if self.should_skip(rec):
                    typer.secho(
                        f"[c2rust-transpiler][skip] 跳过 {rec.qname or rec.name} (id={rec.id}) 位于 {rec.file}:{rec.start_line}-{rec.end_line}",
                        fg=typer.colors.YELLOW,
                    )
                    continue

                # 更新进度索引
                current_index += 1
                progress_info = (
                    f"({current_index}/{total_to_process})"
                    if total_to_process > 0
                    else ""
                )

                # 处理单个函数
                if not self._process_function(rec, progress_info):
                    # 处理失败，保留当前状态，便于下次 resume
                    return

            typer.secho(
                "[c2rust-transpiler] 所有符合条件的函数均已处理完毕。",
                fg=typer.colors.GREEN,
            )
        finally:
            os.chdir(prev_cwd)
            typer.secho(
                f"[c2rust-transpiler][end] 已恢复工作目录: {os.getcwd()}",
                fg=typer.colors.BLUE,
            )

    def _ensure_crate_structure(self) -> None:
        """确保 crate 目录和最小 Cargo 配置存在"""
        try:
            cd = self.crate_dir.resolve()
            cd.mkdir(parents=True, exist_ok=True)
            cargo = cd / "Cargo.toml"
            src_dir = cd / "src"
            lib_rs = src_dir / "lib.rs"
            # 最小 Cargo.toml（不覆盖已有），edition 使用 2021 以兼容更广环境
            if not cargo.exists():
                pkg_name = cd.name
                content = (
                    f'[package]\nname = "{pkg_name}"\nversion = "0.1.0"\nedition = "2021"\n\n'
                    '[lib]\npath = "src/lib.rs"\n'
                )
                try:
                    cargo.write_text(content, encoding="utf-8")
                    typer.secho(
                        f"[c2rust-transpiler][init] created Cargo.toml at {cargo}",
                        fg=typer.colors.GREEN,
                    )
                except Exception:
                    pass
            # 确保 src/lib.rs 存在
            src_dir.mkdir(parents=True, exist_ok=True)
            if not lib_rs.exists():
                try:
                    lib_rs.write_text(
                        "// Auto-created by c2rust transpiler\n", encoding="utf-8"
                    )
                    typer.secho(
                        f"[c2rust-transpiler][init] created src/lib.rs at {lib_rs}",
                        fg=typer.colors.GREEN,
                    )
                except Exception:
                    pass
        except Exception:
            # 保持稳健，失败不阻塞主流程
            pass

    def _handle_resume(self, seq: List[int], done: Set[int]) -> None:
        """处理恢复逻辑：reset 到最后一个已转换函数的 commit id"""
        if not (self.resume and done):
            return

        converted_commits = self.progress.get("converted_commits") or {}
        if not converted_commits:
            return

        # 找到最后一个已转换函数的 commit id
        last_commit = None
        for fid in reversed(seq):
            if fid in done:
                commit_id = converted_commits.get(str(fid))
                if commit_id:
                    last_commit = commit_id
                    break

        if not last_commit:
            return

        current_commit = self.get_crate_commit_hash()
        if current_commit != last_commit:
            typer.secho(
                f"[c2rust-transpiler][resume] 检测到代码状态不一致，正在 reset 到最后一个已转换函数的 commit: {last_commit}",
                fg=typer.colors.YELLOW,
            )
            if self.reset_to_commit(last_commit):
                typer.secho(
                    f"[c2rust-transpiler][resume] 已 reset 到 commit: {last_commit}",
                    fg=typer.colors.GREEN,
                )
            else:
                typer.secho(
                    "[c2rust-transpiler][resume] reset 失败，继续使用当前代码状态",
                    fg=typer.colors.YELLOW,
                )
        else:
            typer.secho(
                "[c2rust-transpiler][resume] 代码状态一致，无需 reset",
                fg=typer.colors.CYAN,
            )

    def _process_function(self, rec: FnRecord, progress_info: str) -> bool:
        """处理单个函数的转译流程

        返回:
            bool: True 表示成功，False 表示需要停止（失败或达到重试上限）
        """
        # 在每个函数开始转译前执行 cargo fmt
        workspace_root = str(self.crate_dir)
        self.run_cargo_fmt(workspace_root)

        # 读取C函数源码
        typer.secho(
            f"[c2rust-transpiler][read] {progress_info} 读取 C 源码: {rec.qname or rec.name} (id={rec.id}) 来自 {rec.file}:{rec.start_line}-{rec.end_line}",
            fg=typer.colors.BLUE,
        )
        c_code = self.read_source_span(rec)
        typer.secho(
            f"[c2rust-transpiler][read] 已加载 {len(c_code.splitlines()) if c_code else 0} 行",
            fg=typer.colors.BLUE,
        )

        # 若缺少源码片段且缺乏签名/参数信息，则跳过本函数，记录进度以便后续处理
        if not c_code and not (
            getattr(rec, "signature", "") or getattr(rec, "params", None)
        ):
            skipped = self.progress.get("skipped_missing_source") or []
            if rec.id not in skipped:
                skipped.append(rec.id)
            self.progress["skipped_missing_source"] = skipped
            typer.secho(
                f"[c2rust-transpiler] {progress_info} 跳过：缺少源码与签名信息 -> {rec.qname or rec.name} (id={rec.id})",
                fg=typer.colors.YELLOW,
            )
            self.save_progress()
            return True  # 跳过不算失败

        # 1) 规划：模块路径与Rust签名
        typer.secho(
            f"[c2rust-transpiler][plan] {progress_info} 正在规划模块与签名: {rec.qname or rec.name} (id={rec.id})",
            fg=typer.colors.CYAN,
        )
        module, rust_sig, skip_implementation = self.plan_module_and_signature(
            rec, c_code
        )
        typer.secho(
            f"[c2rust-transpiler][plan] 已选择 模块={module}, 签名={rust_sig}",
            fg=typer.colors.CYAN,
        )

        # 记录当前进度
        self.update_progress_current(rec, module, rust_sig)
        typer.secho(
            f"[c2rust-transpiler][progress] 已更新当前进度记录 id={rec.id}",
            fg=typer.colors.CYAN,
        )

        # 如果标记为跳过实现，则直接标记为已转换
        if skip_implementation:
            typer.secho(
                f"[c2rust-transpiler][skip-impl] 函数 {rec.qname or rec.name} 评估为不需要实现，跳过实现阶段",
                fg=typer.colors.CYAN,
            )
            # 直接标记为已转换，跳过代码生成、构建和审查阶段
            self.mark_converted(rec, module, rust_sig)
            typer.secho(
                f"[c2rust-transpiler][mark] 已标记并建立映射: {rec.qname or rec.name} -> {module} (跳过实现，视为已实现)",
                fg=typer.colors.GREEN,
            )
            return True

        # 初始化函数上下文与代码编写与修复Agent复用缓存（只在当前函数开始时执行一次）
        self.reset_function_context(rec, module, rust_sig, c_code)

        # 1.5) 确保模块声明链（提前到生成实现之前，避免生成的代码无法被正确引用）
        self._ensure_module_structure(module)

        # 在处理函数前，记录当前的 commit id（用于失败回退）
        self.current_function_start_commit_setter(self.get_crate_commit_hash())
        if self.current_function_start_commit_getter():
            typer.secho(
                f"[c2rust-transpiler][commit] 记录函数开始时的 commit: {self.current_function_start_commit_getter()}",
                fg=typer.colors.BLUE,
            )
        else:
            typer.secho(
                "[c2rust-transpiler][commit] 警告：无法获取 commit id，将无法在失败时回退",
                fg=typer.colors.YELLOW,
            )

        # 重置连续失败计数（每个新函数开始时重置）
        self.consecutive_fix_failures_setter(0)

        # 使用循环来处理函数，支持失败回退后重新开始
        function_retry_count = 0
        max_function_retries = MAX_FUNCTION_RETRIES
        while function_retry_count <= max_function_retries:
            if function_retry_count > 0:
                typer.secho(
                    f"[c2rust-transpiler][retry] 重新开始处理函数 (第 {function_retry_count} 次重试)",
                    fg=typer.colors.YELLOW,
                )
                # 重新记录 commit id（回退后的新 commit）
                self.current_function_start_commit_setter(self.get_crate_commit_hash())
                if self.current_function_start_commit_getter():
                    typer.secho(
                        f"[c2rust-transpiler][commit] 重新记录函数开始时的 commit: {self.current_function_start_commit_getter()}",
                        fg=typer.colors.BLUE,
                    )
                # 重置连续失败计数（重新开始时重置）
                self.consecutive_fix_failures_setter(0)

            # 2) 生成实现
            unresolved = self.untranslated_callee_symbols(rec)
            typer.secho(
                f"[c2rust-transpiler][deps] {progress_info} 未解析的被调符号: {', '.join(unresolved) if unresolved else '(none)'}",
                fg=typer.colors.BLUE,
            )
            typer.secho(
                f"[c2rust-transpiler][gen] {progress_info} 正在为 {rec.qname or rec.name} 生成 Rust 实现",
                fg=typer.colors.GREEN,
            )
            self.codeagent_generate_impl(rec, c_code, module, rust_sig, unresolved)
            typer.secho(
                f"[c2rust-transpiler][gen] 已在 {module} 生成或更新实现",
                fg=typer.colors.GREEN,
            )
            # 刷新精简上下文（防止签名/模块调整后提示不同步）
            try:
                self.refresh_compact_context(rec, module, rust_sig)
            except Exception:
                pass

            # 3) 构建与修复
            typer.secho(
                "[c2rust-transpiler][build] 开始 cargo 测试循环",
                fg=typer.colors.MAGENTA,
            )
            ok = self.cargo_build_loop()

            # 检查是否需要重新开始（回退后）
            if ok is None:
                # 需要重新开始
                function_retry_count += 1
                if function_retry_count > max_function_retries:
                    typer.secho(
                        f"[c2rust-transpiler] 函数重新开始次数已达上限({max_function_retries})，停止处理该函数",
                        fg=typer.colors.RED,
                    )
                    # 保留当前状态，便于下次 resume
                    return False
                # 重置连续失败计数
                self.consecutive_fix_failures_setter(0)
                # 继续循环，重新开始处理
                continue

            typer.secho(
                f"[c2rust-transpiler][build] 构建结果: {'通过' if ok else '失败'}",
                fg=typer.colors.MAGENTA,
            )
            if not ok:
                typer.secho(
                    "[c2rust-transpiler] 在重试次数限制内未能成功构建，已停止。",
                    fg=typer.colors.RED,
                )
                # 保留当前状态，便于下次 resume
                return False

            # 构建成功，跳出循环继续后续流程
            break

        # 4) 审查与优化（复用 Review Agent）
        typer.secho(
            f"[c2rust-transpiler][review] {progress_info} 开始代码审查: {rec.qname or rec.name}",
            fg=typer.colors.MAGENTA,
        )
        self.review_and_optimize(rec, module, rust_sig)
        typer.secho("[c2rust-transpiler][review] 代码审查完成", fg=typer.colors.MAGENTA)

        # 5) 标记已转换与映射记录（JSONL）
        self.mark_converted(rec, module, rust_sig)
        typer.secho(
            f"[c2rust-transpiler][mark] {progress_info} 已标记并建立映射: {rec.qname or rec.name} -> {module}",
            fg=typer.colors.GREEN,
        )

        # 6) 若此前有其它函数因依赖当前符号而在源码中放置了 todo!("<symbol>")，则立即回头消除（复用代码编写与修复Agent）
        current_rust_fn = self.extract_rust_fn_name_from_sig(rust_sig)
        # 收集需要处理的符号（去重，避免 qname 和 name 相同时重复处理）
        symbols_to_resolve = []
        if rec.qname:
            symbols_to_resolve.append(rec.qname)
        if rec.name and rec.name != rec.qname:  # 如果 name 与 qname 不同，才添加
            symbols_to_resolve.append(rec.name)
        # 处理每个符号（去重后）
        for sym in symbols_to_resolve:
            typer.secho(
                f"[c2rust-transpiler][todo] 清理 todo!('{sym}') 的出现位置",
                fg=typer.colors.BLUE,
            )
            self.resolve_pending_todos_for_symbol(
                sym, module, current_rust_fn, rust_sig
            )
        # 如果有处理任何符号，统一运行一次 cargo test（避免重复运行）
        if symbols_to_resolve:
            typer.secho(
                "[c2rust-transpiler][build] 处理 todo 后重新运行 cargo test",
                fg=typer.colors.MAGENTA,
            )
            self.cargo_build_loop()

        return True

    def _ensure_module_structure(self, module: str) -> None:
        """确保模块声明链和顶层模块导出"""
        try:
            self.ensure_mod_chain_for_module(module)
            typer.secho(
                f"[c2rust-transpiler][mod] 已补齐 {module} 的 mod.rs 声明链",
                fg=typer.colors.GREEN,
            )
            # 确保顶层模块在 src/lib.rs 中被公开
            mp = Path(module)
            crate_root = self.crate_dir.resolve()
            rel = (
                mp.resolve().relative_to(crate_root)
                if mp.is_absolute()
                else Path(module)
            )
            rel_s = str(rel).replace("\\", "/")
            if rel_s.startswith("./"):
                rel_s = rel_s[2:]
            if rel_s.startswith("src/"):
                parts = rel_s[len("src/") :].strip("/").split("/")
                if parts and parts[0]:
                    top_mod = parts[0]
                    # 过滤掉 "mod" 关键字和 .rs 文件
                    if top_mod != "mod" and not top_mod.endswith(".rs"):
                        self.ensure_top_level_pub_mod(top_mod)
                        typer.secho(
                            f"[c2rust-transpiler][mod] 已在 src/lib.rs 确保顶层 pub mod {top_mod}",
                            fg=typer.colors.GREEN,
                        )
            cur = self.progress.get("current") or {}
            cur["mod_chain_fixed"] = True
            cur["mod_visibility_fixed"] = True
            self.progress["current"] = cur
            self.save_progress()
        except Exception:
            pass
