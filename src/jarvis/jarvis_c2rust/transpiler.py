# -*- coding: utf-8 -*-
"""
C2Rust 转译器模块

目标：
- 基于 scanner 生成的 translation_order.jsonl 顺序，逐个函数进行转译
- 为每个函数：
  1) 准备上下文：C 源码片段+位置信息、被调用符号（若已转译则提供Rust模块与符号，否则提供原C位置信息）、crate目录结构
  2) 创建"模块选择与签名Agent"：让其选择合适的Rust模块路径，并在summary输出函数签名
  3) 记录当前进度到 progress.json
  4) 基于上述信息与落盘位置，创建 CodeAgent 生成转译后的Rust函数
  5) 尝试 cargo build，如失败则携带错误上下文创建 CodeAgent 修复，直到构建通过或达到上限
  6) 创建代码审查Agent；若 summary 指出问题，则 CodeAgent 优化，直到 summary 表示无问题
  7) 标记函数已转译，并记录 C 符号 -> Rust 符号/模块映射到 symbol_map.jsonl（JSONL，每行一条映射，支持重复与重载）

说明：
- 本模块提供 run_transpile(...) 作为对外入口，后续在 cli.py 中挂载为子命令
- 尽量复用现有 Agent/CodeAgent 能力，保持最小侵入与稳定性
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import typer

from jarvis.jarvis_code_agent.code_agent import CodeAgent

from jarvis.jarvis_c2rust.constants import (
    C2RUST_DIRNAME,
    CONFIG_JSON,
    DEFAULT_CHECK_MAX_RETRIES,
    DEFAULT_PLAN_MAX_RETRIES,
    DEFAULT_PLAN_MAX_RETRIES_ENTRY,
    DEFAULT_REVIEW_MAX_ITERATIONS,
    DEFAULT_TEST_MAX_RETRIES,
    PROGRESS_JSON,
    SYMBOL_MAP_JSONL,
)
from jarvis.jarvis_c2rust.loaders import _SymbolMapJsonl
from jarvis.jarvis_c2rust.models import FnRecord
from jarvis.jarvis_c2rust.transpiler_agents import AgentManager
from jarvis.jarvis_c2rust.transpiler_config import ConfigManager
from jarvis.jarvis_c2rust.transpiler_compile import CompileCommandsManager
from jarvis.jarvis_c2rust.transpiler_context import ContextCollector
from jarvis.jarvis_c2rust.transpiler_generation import GenerationManager
from jarvis.jarvis_c2rust.transpiler_git import GitManager
from jarvis.jarvis_c2rust.transpiler_modules import ModuleManager
from jarvis.jarvis_c2rust.transpiler_planning import PlanningManager
from jarvis.jarvis_c2rust.transpiler_symbols import SymbolMapper
from jarvis.jarvis_c2rust.transpiler_executor import TranspilerExecutor
from jarvis.jarvis_c2rust.utils import (
    check_and_handle_test_deletion,
    default_crate_dir,
)


class Transpiler:
    def __init__(
        self,
        project_root: Union[str, Path] = ".",
        crate_dir: Optional[Union[str, Path]] = None,
        llm_group: Optional[str] = None,
        plan_max_retries: int = DEFAULT_PLAN_MAX_RETRIES,  # 规划阶段最大重试次数（0表示无限重试）
        max_retries: int = 0,  # 兼容旧接口，如未设置则使用 check_max_retries 和 test_max_retries
        check_max_retries: Optional[
            int
        ] = None,  # cargo check 阶段最大重试次数（0表示无限重试）
        test_max_retries: Optional[
            int
        ] = None,  # cargo test 阶段最大重试次数（0表示无限重试）
        review_max_iterations: int = DEFAULT_REVIEW_MAX_ITERATIONS,  # 审查阶段最大迭代次数（0表示无限重试）
        disabled_libraries: Optional[
            List[str]
        ] = None,  # 禁用库列表（在实现时禁止使用这些库）
        root_symbols: Optional[
            List[str]
        ] = None,  # 根符号列表（这些符号对应的接口实现时要求对外暴露，main除外）
        non_interactive: bool = True,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.data_dir = self.project_root / C2RUST_DIRNAME
        self.progress_path = self.data_dir / PROGRESS_JSON
        self.config_path = self.data_dir / CONFIG_JSON
        # JSONL 路径
        self.symbol_map_path = self.data_dir / SYMBOL_MAP_JSONL
        self.llm_group = llm_group
        self.plan_max_retries = plan_max_retries
        # 兼容旧接口：如果只设置了 max_retries，则同时用于 check 和 test
        if max_retries > 0 and check_max_retries is None and test_max_retries is None:
            self.check_max_retries = max_retries
            self.test_max_retries = max_retries
        else:
            self.check_max_retries = (
                check_max_retries
                if check_max_retries is not None
                else DEFAULT_CHECK_MAX_RETRIES
            )
            self.test_max_retries = (
                test_max_retries
                if test_max_retries is not None
                else DEFAULT_TEST_MAX_RETRIES
            )
        self.max_retries = max(
            self.check_max_retries, self.test_max_retries
        )  # 保持兼容性
        self.review_max_iterations = review_max_iterations
        self.non_interactive = non_interactive

        self.crate_dir = (
            Path(crate_dir) if crate_dir else default_crate_dir(self.project_root)
        )
        # 使用自包含的 order.jsonl 记录构建索引，避免依赖 symbols.jsonl
        self.fn_index_by_id: Dict[int, FnRecord] = {}
        self.fn_name_to_id: Dict[str, int] = {}

        # 断点续跑功能默认始终启用
        self.resume = True

        # 初始化状态变量（需要在初始化管理器之前）
        # 当前函数开始时的 commit id（用于失败回退）
        self._current_function_start_commit: Optional[str] = None
        # 连续修复失败的次数（用于判断是否需要回退）
        self._consecutive_fix_failures: int = 0
        # 每个 Agent 对应的工具调用前的 commit id（用于细粒度检测）
        self._agent_before_commits: Dict[str, Optional[str]] = {}

        # 初始化各个功能模块
        self.config_manager = ConfigManager(self.data_dir, self.progress_path)
        self.progress = self.config_manager.progress

        # 从独立的配置文件加载配置（支持从 progress.json 向后兼容迁移）
        config = self.config_manager.load_config()

        # 如果提供了新的根符号或禁用库，更新配置；否则从配置文件中恢复
        # 优先使用传入的参数，如果为 None 则从配置文件恢复
        if root_symbols is not None:
            # 传入的参数不为 None，使用传入的值并保存
            self.root_symbols = root_symbols
        else:
            # 传入的参数为 None，从配置文件恢复
            # 如果配置文件中有配置则使用，否则使用空列表
            self.root_symbols = config.get("root_symbols", [])

        if disabled_libraries is not None:
            # 传入的参数不为 None，使用传入的值并保存
            self.disabled_libraries = disabled_libraries
        else:
            # 传入的参数为 None，从配置文件恢复
            # 如果配置文件中有配置则使用，否则使用空列表
            self.disabled_libraries = config.get("disabled_libraries", [])

        # 从配置文件读取附加说明（不支持通过参数传入，只能通过配置文件设置）
        self.additional_notes = config.get("additional_notes", "")

        # 保存配置到独立的配置文件
        self.config_manager.save_config(
            self.root_symbols, self.disabled_libraries, self.additional_notes
        )

        # 初始化其他模块
        self.compile_commands_manager = CompileCommandsManager(self.project_root)
        self.git_manager = GitManager(str(self.crate_dir))
        self.module_manager = ModuleManager(self.crate_dir)

        # 初始化 Agent 管理器
        self.agent_manager = AgentManager(
            self.crate_dir,
            self.project_root,
            self.llm_group,
            self.non_interactive,
            self.fn_index_by_id,
            self._get_crate_commit_hash,
            self._agent_before_commits,
        )
        self.agent_manager.set_reset_to_commit_func(self._reset_to_commit)

        # 初始化规划管理器（需要在 AgentManager 之后，因为需要访问 agent_manager 的方法）
        self.planning_manager = PlanningManager(
            self.project_root,
            self.crate_dir,
            self.data_dir,
            self.llm_group,
            self.plan_max_retries,
            self.non_interactive,
            self.disabled_libraries,
            self.root_symbols,
            self._extract_compile_flags,
            self._collect_callees_context,
            self._append_additional_notes,
            self._is_root_symbol,
            self._get_crate_commit_hash,
            self.agent_manager.on_before_tool_call,
            self.agent_manager.on_after_tool_call,
            self._agent_before_commits,
        )

        # 初始化代码生成管理器
        self.generation_manager = GenerationManager(
            self.project_root,
            self.crate_dir,
            self.data_dir,
            self.disabled_libraries,
            self._extract_compile_flags,
            self._append_additional_notes,
            self._is_root_symbol,
            self._get_code_agent,
            self._compose_prompt_with_context,
            self._check_and_handle_test_deletion,
            self._get_crate_commit_hash,
            self._ensure_top_level_pub_mod,
        )

        # 构建管理器将在需要时延迟初始化（因为需要访问其他管理器的方法）
        self.build_manager: Optional[Any] = None
        self._build_loop_has_fixes = False  # 标记构建循环中是否进行了修复

        # 初始化审查管理器（需要在其他管理器之后，因为需要访问它们的方法）
        from jarvis.jarvis_c2rust.transpiler_review import ReviewManager

        self.review_manager = ReviewManager(
            self.crate_dir,
            self.data_dir,
            self.llm_group,
            self.non_interactive,
            self.review_max_iterations,
            self.disabled_libraries,
            self.progress,
            self._save_progress,
            self._read_source_span,
            self._collect_callees_context,
            self._extract_compile_flags,
            self._is_root_symbol,
            self._get_crate_commit_hash,
            lambda: self._current_function_start_commit,
            self._compose_prompt_with_context,
            self._get_code_agent,
            self._check_and_handle_test_deletion,
            self._append_additional_notes,
            self._cargo_build_loop,
            self._get_build_loop_has_fixes,
            self._on_before_tool_call,
            self._on_after_tool_call,
            self._agent_before_commits,
            self.agent_manager._current_agents,
            self._get_git_diff,
        )

        # 在初始化完成后打印日志
        typer.secho(
            f"[c2rust-transpiler][init] 初始化参数: project_root={self.project_root} crate_dir={self.crate_dir} llm_group={self.llm_group} plan_max_retries={self.plan_max_retries} check_max_retries={self.check_max_retries} test_max_retries={self.test_max_retries} review_max_iterations={self.review_max_iterations} disabled_libraries={self.disabled_libraries} root_symbols={self.root_symbols} non_interactive={self.non_interactive}",
            fg=typer.colors.BLUE,
        )
        # 使用 JSONL 存储的符号映射
        self.symbol_map = _SymbolMapJsonl(self.symbol_map_path)

        # 初始化上下文收集器和符号映射器
        self.context_collector = ContextCollector(
            self.project_root,
            self.fn_index_by_id,
            self.fn_name_to_id,
            self.symbol_map,
        )
        self.symbol_mapper = SymbolMapper(
            self.symbol_map,
            self.progress,
            self.config_manager,
            self.git_manager,
        )

    def _extract_compile_flags(self, c_file_path: Union[str, Path]) -> Optional[str]:
        """从 compile_commands.json 中提取指定 C 文件的编译参数（委托给 CompileCommandsManager）"""
        return self.compile_commands_manager.extract_compile_flags(c_file_path)

    def _save_progress(self) -> None:
        """保存进度，使用原子性写入"""
        self.config_manager.save_progress()

    def _load_config(self) -> Dict[str, Any]:
        """从独立的配置文件加载配置（委托给 ConfigManager）"""
        return self.config_manager.load_config()

    def _save_config(self) -> None:
        """保存配置到独立的配置文件（委托给 ConfigManager）"""
        self.config_manager.save_config(
            self.root_symbols, self.disabled_libraries, self.additional_notes
        )

    def _read_source_span(self, rec: FnRecord) -> str:
        """按起止行读取源码片段（忽略列边界，尽量完整）"""
        return self.context_collector.read_source_span(rec)

    def _load_order_index(self, order_jsonl: Path) -> None:
        """从自包含的 order.jsonl 中加载所有 records（委托给 ConfigManager）"""
        self.config_manager.load_order_index(
            order_jsonl, self.fn_index_by_id, self.fn_name_to_id
        )

    def _should_skip(self, rec: FnRecord) -> bool:
        """判断是否应该跳过该函数（委托给 SymbolMapper）"""
        return self.symbol_mapper.should_skip(rec)

    def _collect_callees_context(self, rec: FnRecord) -> List[Dict[str, Any]]:
        """生成被引用符号上下文列表（委托给 ContextCollector）"""
        return self.context_collector.collect_callees_context(rec)

    def _untranslated_callee_symbols(self, rec: FnRecord) -> List[str]:
        """返回尚未转换的被调函数符号（委托给 ContextCollector）"""
        return self.context_collector.untranslated_callee_symbols(rec)

    def _append_additional_notes(self, prompt: str) -> str:
        """在提示词末尾追加附加说明（委托给 ContextCollector）"""
        return self.context_collector.append_additional_notes(
            prompt, self.additional_notes
        )

    def _build_module_selection_prompts(
        self,
        rec: FnRecord,
        c_code: str,
        callees_ctx: List[Dict[str, Any]],
        crate_tree: str,
    ) -> Tuple[str, str, str]:
        """构建模块选择提示词（委托给 PlanningManager）"""
        return self.planning_manager.build_module_selection_prompts(
            rec, c_code, callees_ctx, crate_tree
        )

    def _plan_module_and_signature(
        self, rec: FnRecord, c_code: str
    ) -> Tuple[str, str, bool]:
        """调用 Agent 选择模块与签名（委托给 PlanningManager）"""
        return self.planning_manager.plan_module_and_signature(rec, c_code)

    def _update_progress_current(
        self, rec: FnRecord, module: str, rust_sig: str
    ) -> None:
        """更新当前进度（委托给 AgentManager）"""
        self.agent_manager.update_progress_current(
            rec, module, rust_sig, self.progress, self._save_progress
        )

    # ========= Agent 复用与上下文拼接辅助 =========

    def _compose_prompt_with_context(self, prompt: str) -> str:
        """在复用Agent时，将此前构建的函数上下文头部拼接到当前提示词前（委托给 AgentManager）"""
        return self.agent_manager.compose_prompt_with_context(prompt)

    def _reset_function_context(
        self, rec: FnRecord, module: str, rust_sig: str, c_code: str
    ) -> None:
        """初始化当前函数的上下文与复用Agent缓存（委托给 AgentManager）"""
        # 设置当前函数 ID，以便 AgentManager 可以访问
        self.agent_manager._current_function_id = rec.id
        self.agent_manager.reset_function_context(
            rec,
            module,
            rust_sig,
            c_code,
            self._collect_callees_context,
            self._extract_compile_flags,
        )

    def _on_before_tool_call(self, agent: Any, current_response=None, **kwargs) -> None:
        """工具调用前的事件处理器（委托给 AgentManager）"""
        return self.agent_manager.on_before_tool_call(agent, current_response, **kwargs)

    def _on_after_tool_call(
        self,
        agent: Any,
        current_response=None,
        need_return=None,
        tool_prompt=None,
        **kwargs,
    ) -> None:
        """工具调用后的事件处理器（委托给 AgentManager）"""
        return self.agent_manager.on_after_tool_call(
            agent, current_response, need_return, tool_prompt, **kwargs
        )

    def _get_code_agent(self) -> CodeAgent:
        """获取代码生成/修复Agent（委托给 AgentManager）"""
        return self.agent_manager.get_code_agent()

    def _refresh_compact_context(
        self, rec: FnRecord, module: str, rust_sig: str
    ) -> None:
        """刷新精简上下文头部（委托给 AgentManager）"""
        self.agent_manager.refresh_compact_context(rec, module, rust_sig)

    # ========= 代码生成与修复 =========

    def _is_root_symbol(self, rec: FnRecord) -> bool:
        """判断函数是否为根符号（排除 main）"""
        if not self.root_symbols:
            return False
        # 检查函数名或限定名是否在根符号列表中
        return (rec.name in self.root_symbols) or (rec.qname in self.root_symbols)

    def _build_generate_impl_prompt(
        self,
        rec: FnRecord,
        c_code: str,
        module: str,
        rust_sig: str,
        unresolved: List[str],
    ) -> str:
        """构建代码生成提示词（委托给 GenerationManager）"""
        return self.generation_manager.build_generate_impl_prompt(
            rec, c_code, module, rust_sig, unresolved
        )

    def _codeagent_generate_impl(
        self,
        rec: FnRecord,
        c_code: str,
        module: str,
        rust_sig: str,
        unresolved: List[str],
    ) -> None:
        """使用 CodeAgent 生成/更新目标模块中的函数实现（委托给 GenerationManager）"""
        return self.generation_manager.codeagent_generate_impl(
            rec, c_code, module, rust_sig, unresolved
        )

    def _extract_rust_fn_name_from_sig(self, rust_sig: str) -> str:
        """从 rust 签名中提取函数名（委托给 GenerationManager）"""
        return self.generation_manager.extract_rust_fn_name_from_sig(rust_sig)

    def _ensure_top_level_pub_mod(self, mod_name: str) -> None:
        """在 src/lib.rs 中确保存在 `pub mod <mod_name>;`（委托给 ModuleManager）"""
        self.module_manager.ensure_top_level_pub_mod(mod_name)

    def _ensure_mod_rs_decl(self, dir_path: Path, child_mod: str) -> None:
        """在 dir_path/mod.rs 中确保存在 `pub mod <child_mod>;`（委托给 ModuleManager）"""
        self.module_manager.ensure_mod_rs_decl(dir_path, child_mod)

    def _ensure_mod_chain_for_module(self, module: str) -> None:
        """根据目标模块文件，补齐从该文件所在目录向上的 mod.rs 声明链（委托给 ModuleManager）"""
        self.module_manager.ensure_mod_chain_for_module(module)

    def _module_file_to_crate_path(self, module: str) -> str:
        """将模块文件路径转换为 crate 路径前缀（委托给 ModuleManager）"""
        return self.module_manager.module_file_to_crate_path(module)

    def _resolve_pending_todos_for_symbol(
        self, symbol: str, callee_module: str, callee_rust_fn: str, callee_rust_sig: str
    ) -> None:
        """解析待处理的 todo 占位（委托给 SymbolMapper）"""
        self.symbol_mapper.resolve_pending_todos_for_symbol(
            symbol,
            callee_module,
            callee_rust_fn,
            callee_rust_sig,
            self.crate_dir,
            self._get_code_agent,
            self._compose_prompt_with_context,
            self._check_and_handle_test_deletion,
        )

    def _init_build_manager(self) -> None:
        """初始化构建管理器"""
        if self.build_manager is None:
            from jarvis.jarvis_c2rust.transpiler_build import BuildManager

            self.build_manager = BuildManager(
                self.crate_dir,
                self.project_root,
                self.data_dir,
                self.test_max_retries,
                self.disabled_libraries,
                self.root_symbols,
                self.progress,
                self._save_progress,
                self._extract_compile_flags,
                self._get_current_function_context,
                self._get_code_agent,
                self._compose_prompt_with_context,
                self._check_and_handle_test_deletion,
                self._get_crate_commit_hash,
                self._reset_to_commit,
                self._append_additional_notes,
                lambda: self._consecutive_fix_failures,
                lambda v: setattr(self, "_consecutive_fix_failures", v),
                lambda: self._current_function_start_commit,
                self._get_git_diff,
            )

    def _classify_rust_error(self, text: str) -> List[str]:
        """朴素错误分类（委托给 BuildManager）"""
        if self.build_manager is None:
            self._init_build_manager()
        return self.build_manager.classify_rust_error(text)

    def _get_current_function_context(self) -> Tuple[Dict[str, Any], str, str, str]:
        """
        获取当前函数上下文信息。
        返回: (curr, sym_name, src_loc, c_code)
        """
        try:
            curr = self.progress.get("current") or {}
        except Exception:
            curr = {}
        sym_name = str(curr.get("qualified_name") or curr.get("name") or "")
        src_loc = (
            f"{curr.get('file')}:{curr.get('start_line')}-{curr.get('end_line')}"
            if curr
            else ""
        )
        c_code = ""
        try:
            cf = curr.get("file")
            s = int(curr.get("start_line") or 0)
            e = int(curr.get("end_line") or 0)
            if cf and s:
                p = Path(cf)
                if not p.is_absolute():
                    p = (self.project_root / p).resolve()
                if p.exists():
                    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
                    s0 = max(1, s)
                    e0 = min(len(lines), max(e, s0))
                    c_code = "\n".join(lines[s0 - 1 : e0])
        except Exception:
            c_code = ""
        return curr, sym_name, src_loc, c_code

    def _build_repair_prompt_base(
        self,
        stage: str,
        tags: List[str],
        sym_name: str,
        src_loc: str,
        c_code: str,
        curr: Dict[str, Any],
        symbols_path: str,
        include_output_patch_hint: bool = False,
    ) -> List[str]:
        """构建修复提示词的基础部分（委托给 BuildManager）"""
        if self.build_manager is None:
            self._init_build_manager()
        return self.build_manager.build_repair_prompt_base(
            stage,
            tags,
            sym_name,
            src_loc,
            c_code,
            curr,
            symbols_path,
            include_output_patch_hint,
        )

    def _build_repair_prompt_stage_section(
        self, stage: str, output: str, command: Optional[str] = None
    ) -> List[str]:
        """构建修复提示词的阶段特定部分（委托给 BuildManager）"""
        if self.build_manager is None:
            self._init_build_manager()
        return self.build_manager.build_repair_prompt_stage_section(
            stage, output, command
        )

    def _build_repair_prompt(
        self,
        stage: str,
        output: str,
        tags: List[str],
        sym_name: str,
        src_loc: str,
        c_code: str,
        curr: Dict[str, Any],
        symbols_path: str,
        include_output_patch_hint: bool = False,
        command: Optional[str] = None,
    ) -> str:
        """构建修复提示词（委托给 BuildManager）"""
        if self.build_manager is None:
            self._init_build_manager()
        return self.build_manager.build_repair_prompt(
            stage,
            output,
            tags,
            sym_name,
            src_loc,
            c_code,
            curr,
            symbols_path,
            include_output_patch_hint,
            command,
        )

    def _detect_crate_kind(self) -> str:
        """检测 crate 类型（委托给 BuildManager）"""
        if self.build_manager is None:
            self._init_build_manager()
        return self.build_manager.detect_crate_kind()

    def _run_cargo_fmt(self, workspace_root: str) -> None:
        """执行 cargo fmt 格式化代码（委托给 BuildManager）"""
        if self.build_manager is None:
            self._init_build_manager()
        self.build_manager.run_cargo_fmt(workspace_root)

    def _get_crate_commit_hash(self) -> Optional[str]:
        """获取 crate 目录的当前 commit id（委托给 GitManager）"""
        return self.git_manager.get_crate_commit_hash()

    def _get_git_diff(self, base_commit: Optional[str] = None) -> str:
        """获取 git diff，显示从 base_commit 到当前工作区的变更（委托给 GitManager）"""
        return self.git_manager.get_git_diff(base_commit)

    def _reset_to_commit(self, commit_hash: str) -> bool:
        """回退 crate 目录到指定的 commit（委托给 GitManager）"""
        return self.git_manager.reset_to_commit(commit_hash)

    def _check_and_handle_test_deletion(
        self, before_commit: Optional[str], agent: Any
    ) -> bool:
        """
        检测并处理测试代码删除。

        参数:
            before_commit: agent 运行前的 commit hash
            agent: 代码生成或修复的 agent 实例，使用其 model 进行询问

        返回:
            bool: 如果检测到问题且已回退，返回 True；否则返回 False
        """
        return check_and_handle_test_deletion(
            before_commit, agent, self._reset_to_commit, "[c2rust-transpiler]"
        )

    def _run_cargo_test_and_fix(
        self, workspace_root: str, test_iter: int
    ) -> Tuple[bool, Optional[bool]]:
        """运行 cargo test 并在失败时修复（委托给 BuildManager）"""
        if self.build_manager is None:
            self._init_build_manager()
        return self.build_manager.run_cargo_test_and_fix(workspace_root, test_iter)

    def _cargo_build_loop(self) -> Optional[bool]:
        """在 crate 目录执行构建与测试（委托给 BuildManager）"""
        if self.build_manager is None:
            self._init_build_manager()
        result = self.build_manager.cargo_build_loop()
        # 保存修复标记，供调用方检查
        self._build_loop_has_fixes = getattr(
            self.build_manager, "_build_loop_has_fixes", False
        )
        return result

    def _get_build_loop_has_fixes(self) -> bool:
        """获取构建循环中是否进行了修复"""
        return getattr(self, "_build_loop_has_fixes", False)

    def _review_and_optimize(self, rec: FnRecord, module: str, rust_sig: str) -> None:
        """审查生成的实现（委托给 ReviewManager）"""
        return self.review_manager.review_and_optimize(rec, module, rust_sig)

    def _mark_converted(self, rec: FnRecord, module: str, rust_sig: str) -> None:
        """记录映射：C 符号 -> Rust 符号与模块路径（委托给 SymbolMapper）"""
        self.symbol_mapper.mark_converted(rec, module, rust_sig)

    def transpile(self) -> None:
        """主流程（委托给 TranspilerExecutor）"""
        executor = TranspilerExecutor(
            project_root=self.project_root,
            crate_dir=self.crate_dir,
            progress=self.progress,
            resume=self.resume,
            fn_index_by_id=self.fn_index_by_id,
            load_order_index_func=self._load_order_index,
            should_skip_func=self._should_skip,
            read_source_span_func=self._read_source_span,
            plan_module_and_signature_func=self._plan_module_and_signature,
            update_progress_current_func=self._update_progress_current,
            mark_converted_func=self._mark_converted,
            reset_function_context_func=self._reset_function_context,
            ensure_mod_chain_for_module_func=self._ensure_mod_chain_for_module,
            ensure_top_level_pub_mod_func=self._ensure_top_level_pub_mod,
            get_crate_commit_hash_func=self._get_crate_commit_hash,
            reset_to_commit_func=self._reset_to_commit,
            run_cargo_fmt_func=self._run_cargo_fmt,
            untranslated_callee_symbols_func=self._untranslated_callee_symbols,
            codeagent_generate_impl_func=self._codeagent_generate_impl,
            refresh_compact_context_func=self._refresh_compact_context,
            cargo_build_loop_func=self._cargo_build_loop,
            review_and_optimize_func=self._review_and_optimize,
            extract_rust_fn_name_from_sig_func=self._extract_rust_fn_name_from_sig,
            resolve_pending_todos_for_symbol_func=self._resolve_pending_todos_for_symbol,
            save_progress_func=self._save_progress,
            consecutive_fix_failures_getter=lambda: self._consecutive_fix_failures,
            consecutive_fix_failures_setter=lambda v: setattr(
                self, "_consecutive_fix_failures", v
            ),
            current_function_start_commit_getter=lambda: self._current_function_start_commit,
            current_function_start_commit_setter=lambda v: setattr(
                self, "_current_function_start_commit", v
            ),
            get_build_loop_has_fixes_func=self._get_build_loop_has_fixes,
        )
        executor.execute()


def run_transpile(
    project_root: Union[str, Path] = ".",
    crate_dir: Optional[Union[str, Path]] = None,
    llm_group: Optional[str] = None,
    plan_max_retries: int = DEFAULT_PLAN_MAX_RETRIES_ENTRY,
    max_retries: int = 0,  # 兼容旧接口
    check_max_retries: Optional[int] = None,
    test_max_retries: Optional[int] = None,
    review_max_iterations: int = DEFAULT_REVIEW_MAX_ITERATIONS,
    disabled_libraries: Optional[List[str]] = None,  # None 表示从配置文件恢复
    root_symbols: Optional[List[str]] = None,  # None 表示从配置文件恢复
    non_interactive: bool = True,
) -> None:
    """
    入口函数：执行转译流程
    - project_root: 项目根目录（包含 .jarvis/c2rust/symbols.jsonl）
    - crate_dir: Rust crate 根目录；默认遵循 "<parent>/<cwd_name>_rs"（与当前目录同级，若 project_root 为 ".")
    - llm_group: 指定 LLM 模型组
    - max_retries: 构建与审查迭代的最大次数
    注意: 断点续跑功能默认始终启用
    """
    t = Transpiler(
        project_root=project_root,
        crate_dir=crate_dir,
        llm_group=llm_group,
        plan_max_retries=plan_max_retries,
        max_retries=max_retries,
        check_max_retries=check_max_retries,
        test_max_retries=test_max_retries,
        review_max_iterations=review_max_iterations,
        disabled_libraries=disabled_libraries,
        root_symbols=root_symbols,
        non_interactive=non_interactive,
    )
    t.transpile()
